# Deployment

The app runs on one small server, in four Docker containers, behind Cloudflare. Terraform creates the server
and the DNS record, and GitHub Actions tests, builds and deploys every push to `main`.

Contents: [Architecture](#architecture) · [Containers](#the-four-containers) · [nginx](#nginx) ·
[Client IPs](#request-path-and-real-client-ips) · [TLS](#tls-and-cloudflare-settings) · [CI/CD](#cicd) ·
[Rollback](#image-tags-and-rollback) · [Secrets](#secrets-and-configuration) · [Infrastructure](#infrastructure) ·
[First-time setup](#first-time-setup) · [Operations](#operating-the-server) ·
[Troubleshooting](#troubleshooting) · [Cost](#cost) · [Teardown](#teardown) · [Limits](#limits)

## Architecture

```
Browser
  │  https://truckroute.<your-domain>
  ▼
Cloudflare (proxied DNS record; public TLS)
  │  HTTPS, Cloudflare Origin Certificate
  ▼
Lightsail server (Ubuntu 24.04, 2 GB, static IP, /opt/truckroute)
  └─ Docker Compose
       web      nginx + the React build        ports 80, 443
         ├─ /      → static files (index.html, /assets/*)
         └─ /api/  → http://backend:8000
       backend  gunicorn, 1 process, 4 threads  (Django API)
       worker   manage.py run_jobs              (weather downloads)
       cleanup  manage.py cleanup_plans, hourly
       volume app-data → /data  (SQLite file and plan JSON files)
```

The browser talks to one origin. The React app calls `/api/...` on the same host, so there is no CORS and
`VITE_API_URL` stays empty. The TomTom key lives only in the Python containers; the browser never sees it.

## The four containers

| Service | Image | What it does |
|---|---|---|
| `web` | `truckroute-web` | nginx. Serves the React build, redirects HTTP to HTTPS, proxies `/api/` to `backend`. The only service with published ports. |
| `backend` | `truckroute-backend` | gunicorn with **one** process and four threads. Handles API requests. |
| `worker` | `truckroute-backend` | `manage.py run_jobs`. Downloads the forecast for queued weather jobs. |
| `cleanup` | `truckroute-backend` | Runs `manage.py cleanup_plans` every hour, so expired plans and files go even on an idle server. |

**Why the worker is separate.** The backend runs with `JOB_WORKER=external`. Every Open-Meteo call, and the
pacing that keeps the app under Open-Meteo's limits, then happens in exactly one process, and the web process
stays free to answer status polls during a long download. The backend runs one gunicorn process for the same
reason: the plan cache and the request throttles are per process.

The three Python containers share the `app-data` volume (`/data`: the SQLite file and the plan JSON files).
SQLite runs in WAL mode, which is safe across containers on one host with one writer at a time. This is also why
the app needs one machine with a disk rather than several instances.

## nginx

- **Port 80:** `/healthz` returns `ok` (the container health check). Everything else is a `301` to HTTPS.
- **Port 443, `/api/`:** proxied to `backend:8000`, keeping the `/api` prefix. 60-second read timeout.
- **Port 443, `/assets/`:** hashed file names, so `Cache-Control: public, max-age=31536000, immutable`.
- **Port 443, `/`:** the React app. `index.html` is never cached (`no-cache`), and unknown paths fall back to it.
- Every location sends `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`. They are included from
  a snippet into each location because nginx drops inherited `add_header` lines in a location that sets its own.
  On `/api/`, nginx first drops the `X-Content-Type-Options` and `Referrer-Policy` headers that Django also sets
  (`proxy_hide_header`), so each header appears once.
- There is no Content-Security-Policy yet. MapLibre needs `blob:` workers and the OpenFreeMap tile host, so add
  one only together with a check of the map.

## Request path and real client IPs

Browser → Cloudflare → nginx → Django.

Behind Cloudflare, every connection reaches the server from a Cloudflare address. To keep the visitor's address
(the rate limits are per client):

1. nginx trusts `CF-Connecting-IP` only when the connection comes from a Cloudflare range
   (`frontend/nginx/snippets/cloudflare-realip.conf`). Regenerate the list with
   `deploy/scripts/update-cloudflare-ips.sh` when Cloudflare changes its ranges, then rebuild and redeploy.
2. nginx then sends `X-Forwarded-For: <client address>`, overwriting any value the client sent.
3. Django runs with `NUM_PROXIES=1` and reads that single entry.

A client therefore cannot spoof its address with its own `X-Forwarded-For` header.

## TLS and Cloudflare settings

- Visitors connect to Cloudflare, which presents its own certificate.
- Between Cloudflare and nginx, traffic uses a **Cloudflare Origin Certificate**, stored on the server as
  `/opt/truckroute/certs/origin.pem` and `origin.key` (written by the deploy job from GitHub secrets). It is valid
  for the period chosen when it was created, and nothing renews on the server. Note its expiry date.
- **SSL mode must be Full (strict) for this host.** With Full (strict), Cloudflare requires an unexpired
  certificate that matches the host name, and Cloudflare's Origin CA is accepted. If the zone hosts other sites that
  still run on Flexible, do not change the whole zone: they would break if their origins cannot meet those
  requirements. Instead add a rule that applies to this host only:
  **Rules → Overview → Create rule → Configuration Rule**, condition *Hostname equals* `truckroute.<your-domain>`, setting
  **SSL → Strict**, then **Deploy**. Terraform does not manage the SSL mode, because it affects every host on the
  zone.
- By default the firewall accepts ports 80 and 443 only from Cloudflare's address ranges, so the server cannot be
  reached directly. Port 22 (SSH) accepts key-only logins from any IPv4 address, because GitHub-hosted runners have
  no fixed addresses; narrow `ssh_allowed_cidrs` if you deploy from fixed addresses.

## CI/CD

The workflow is `.github/workflows/ci-cd.yml`.

| Stage | When | What |
|---|---|---|
| `backend` | every push and PR | `ruff check`, `pytest` |
| `frontend` | every push and PR | `npm run lint`, `npm test`, `npm run build` |
| `terraform` | every push and PR | `terraform fmt -check`, `init -backend=false`, `validate` (no cloud credentials) |
| `images` | push to `main`, after the three above | Build the backend and web images for `linux/amd64` and push them to `ghcr.io` |
| `deploy` | after `images` | Copy the compose file, `deploy.sh`, the `.env` and the certificate to the server and run `deploy.sh`. Then smoke-test `/api/health` and `/` on the server over SSH (a failure fails the run). A last step requests `https://<domain>/api/health` through Cloudflare and only warns, because Cloudflare may challenge requests from GitHub's IP ranges. |

`deploy.sh` (on the server) pulls the images, runs `migrate`, starts the stack, waits up to 90 seconds for the
backend health check, and records the tag in `/opt/truckroute/DEPLOYED_TAG`. If the backend does not become
healthy, it prints the backend log and fails the run.

Pull requests run the three checks only. Runs on `main` are never cancelled by newer pushes, and the deploy job
has its own group, so a running deploy always finishes. Actions that handle the package-write token are pinned to
commit SHAs, and `.github/dependabot.yml` opens a weekly pull request to update them.

## Image tags and rollback

Each build on `main` is pushed as `ghcr.io/<owner>/truckroute-backend` and `truckroute-web` with two tags:
`sha-<full commit sha>` and `latest`. A deploy always names the exact `sha-` tag, never `latest`.

To roll back, log in to the server and deploy an earlier tag:

```bash
cd /opt/truckroute
cat DEPLOYED_TAG                       # what is running now
IMAGE_TAG=sha-<older commit> ./deploy.sh
```

The registry login from the last deploy is removed when it finishes, so run `docker login ghcr.io` first with a
token that can read packages. Rolling back does not undo database migrations. The current migrations only add
tables and columns, so older code keeps working, but check this before rolling back past a new migration.

## Secrets and configuration

| Where | What |
|---|---|
| GitHub secrets (environment `production`) | `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `DJANGO_SECRET_KEY`, `TOMTOM_API_KEY`, `CF_ORIGIN_CERT`, `CF_ORIGIN_KEY` |
| GitHub variables (repository or environment) | `APP_DOMAIN`, `DEPLOY_HOST`, `DEPLOY_USER` |
| Server | `/opt/truckroute/.env` and `certs/origin.key`, both mode 600, written by the deploy job |

Secrets never go in git, in an image, in the frontend bundle or in a workflow log. The deploy job builds the
server `.env` from the GitHub secrets, passes the registry token only through `ssh` standard input, checks the
server's host key against the stored `known_hosts`, and deletes its local key files when it ends. The `web`
container gets no environment file, so the TomTom key never enters it.

Restrict the `production` environment to the `main` branch (**Settings → Environments → production →
Deployment branches**), so that only `main` can use these secrets.

`deploy/.env.example` lists the server's variables: `APP_DOMAIN`, `IMAGE_OWNER` (the lowercase GitHub owner),
`DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (must include `127.0.0.1` and `backend`, which the health check uses),
`CORS_ALLOWED_ORIGINS` (empty: same origin), `TOMTOM_API_KEY` and `LOG_LEVEL`.

## Infrastructure

Everything is in `infra/terraform/`.

| Resource | Purpose |
|---|---|
| `aws_lightsail_instance` | Ubuntu 24.04, plan `small_3_0` (2 GB RAM, 2 vCPU), `us-east-1`. First boot installs Docker, adds the deploy SSH key, creates `/opt/truckroute`, and adds a 1 GB swap file. |
| `aws_lightsail_static_ip` and attachment | A fixed public address. |
| `aws_lightsail_instance_public_ports` | SSH (22) with key-only login. Ports 80 and 443 only from Cloudflare's ranges (`restrict_web_to_cloudflare`). SSH over IPv6 is closed unless `ssh_allowed_ipv6_cidrs` is set. |
| `cloudflare_dns_record` | Proxied `A` record for the app domain. |

State is stored in an S3 bucket with native locking. The first-boot script runs once, when the server is created.
Changes to it are ignored afterwards, so editing it never replaces the server. If the instance is replaced, the
IP attachment and the firewall rules are recreated with it. A replaced server has a new SSH host key (update
`DEPLOY_KNOWN_HOSTS`) and an empty data volume.

## First-time setup

You need: a domain whose DNS is on Cloudflare, an AWS account, this repository on GitHub, a TomTom API key, and on
your machine the AWS CLI, Terraform 1.10 or newer and the GitHub CLI (`gh`, logged in). Use your own values
wherever this page shows `<…>`.

**1. AWS credentials.** Create an IAM user with this policy (Lightsail, plus the state bucket only), create an
access key for it and run `aws configure` (region `us-east-1`). Check with `aws sts get-caller-identity`.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    { "Effect": "Allow", "Action": "lightsail:*", "Resource": "*" },
    { "Effect": "Allow",
      "Action": ["s3:CreateBucket", "s3:ListBucket", "s3:GetBucketVersioning", "s3:PutBucketVersioning",
                 "s3:GetBucketPublicAccessBlock", "s3:PutBucketPublicAccessBlock"],
      "Resource": "arn:aws:s3:::truckroute-tfstate-*" },
    { "Effect": "Allow", "Action": ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"],
      "Resource": "arn:aws:s3:::truckroute-tfstate-*/*" }
  ]
}
```

**2. State bucket.**

```bash
BUCKET=truckroute-tfstate-$(openssl rand -hex 4)
aws s3api create-bucket --bucket "$BUCKET" --region us-east-1
aws s3api put-bucket-versioning --bucket "$BUCKET" --versioning-configuration Status=Enabled
aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
echo "$BUCKET"
```

**3. Cloudflare.**
- **Zone ID:** dashboard → Domains → your domain → Overview → the **API** section near the bottom.
- **API token:** My Profile → API Tokens → *Edit zone DNS* template, limited to your zone. Export it in the terminal
  you will run Terraform in: `export CLOUDFLARE_API_TOKEN=...`
- **Origin Certificate:** SSL/TLS → Origin Server → Create Certificate, RSA 2048, host name
  `truckroute.<your-domain>`. Save the certificate and the private key to files outside the repository. The key is
  shown only once.
- **SSL mode:** set Full (strict) for this host, as described in [TLS and Cloudflare settings](#tls-and-cloudflare-settings).

**4. Deploy SSH key.** `ssh-keygen -t ed25519 -f ~/.ssh/truckroute_deploy -N "" -C github-actions-deploy`. Only the
`.pub` line is ever shared; the private file becomes a GitHub secret.

**5. Create the server.** In `infra/terraform/`, copy `backend.hcl.example` to `backend.hcl` (set the bucket) and
`terraform.tfvars.example` to `terraform.tfvars` (set the public key, zone ID and domain). Then:

```bash
terraform init -backend-config=backend.hcl
terraform plan          # expect: 5 to add
terraform apply
```

**6. Wait for the first boot** (a few minutes: it installs Docker), then check from your machine:
`ssh -i ~/.ssh/truckroute_deploy ubuntu@<static_ip> 'cloud-init status'` should print `status: done`.

**7. Save the host key** (do this right after the server is created, over a network you trust):
`ssh-keyscan -t ed25519 <static_ip> > ~/.ssh/truckroute_known_hosts`

**8. Configure GitHub.** In the repository, create the `production` environment (Settings → Environments → New environment), then set the variables and secrets. `gh secret set`
reads the value from standard input, so secrets never appear on screen or in shell history:

```bash
R=<owner>/<repo>
gh variable set APP_DOMAIN  --repo $R --body truckroute.<your-domain>
gh variable set DEPLOY_HOST --repo $R --body <static_ip>
gh variable set DEPLOY_USER --repo $R --body ubuntu
gh secret set DEPLOY_SSH_KEY     --env production --repo $R < ~/.ssh/truckroute_deploy
gh secret set DEPLOY_KNOWN_HOSTS --env production --repo $R < ~/.ssh/truckroute_known_hosts
gh secret set CF_ORIGIN_CERT     --env production --repo $R < <origin certificate file>
gh secret set CF_ORIGIN_KEY      --env production --repo $R < <origin private key file>
python3 -c "import secrets; print(secrets.token_urlsafe(50), end='')" | gh secret set DJANGO_SECRET_KEY --env production --repo $R
gh secret set TOMTOM_API_KEY     --env production --repo $R    # prompts for the value
```

**9. Deploy.** Push to `main` and watch the run in the Actions tab. Then open the site and plan a trip.

## Operating the server

```bash
ssh -i ~/.ssh/truckroute_deploy ubuntu@<static_ip>
cd /opt/truckroute
cat DEPLOYED_TAG                          # the running version
docker compose ps                         # state and health of the four services
docker compose logs --tail=100 backend    # also: worker, cleanup, web
docker compose restart worker             # restart one service
```

**Data.** The database and plan files are in the Docker volume `truckroute_app-data`. They are a cache of plans
and weather downloads, which expire after 6 to 24 hours, so losing them costs only re-downloaded forecasts. They
are lost if the server is replaced or destroyed. For a copy of the volume (taken while the app runs, so it is
best effort):

```bash
docker run --rm -v truckroute_app-data:/data:ro alpine tar czf - -C /data . > app-data.tgz
```

**Rotating secrets.** Change the GitHub secret, then push or re-run the workflow; the deploy job rewrites
`/opt/truckroute/.env` and the certificate files. To change the Cloudflare Origin Certificate, update
`CF_ORIGIN_CERT` and `CF_ORIGIN_KEY` the same way.

## Troubleshooting

| Symptom | Likely cause | What to do |
|---|---|---|
| `Permission denied (publickey)` soon after the server is created | The first-boot script has not finished, or it failed before adding the key | Wait a few minutes. Otherwise open the instance's browser SSH in the Lightsail console and run `sudo cloud-init status --long` and `sudo tail -40 /var/log/cloud-init-output.log`. |
| Browser shows too many redirects | The SSL mode for the host is Flexible: Cloudflare connects over HTTP and nginx redirects HTTP to HTTPS | Set SSL to Full (strict) for the host. |
| Error 526 from Cloudflare | Full (strict) needs a valid origin certificate, and Cloudflare rejected the one it received | Check the certificate's expiry and host name, and that `CF_ORIGIN_CERT` and `CF_ORIGIN_KEY` match. |
| The deploy's public check warns with HTTP 403 | Cloudflare answering requests from GitHub's runners | The server check passed, so the app is fine. Find the rule in Cloudflare → Security → Analytics → Events. |
| `deploy.sh` fails with the backend unhealthy | The new image does not start | Read the log it prints, or `docker compose logs backend`. Roll back to the previous tag. |
| 400 from `/api/health` | The `Host` header is not in `DJANGO_ALLOWED_HOSTS` | Check the server `.env` (the domain, `localhost`, `127.0.0.1` and `backend` are required). |
| Every visitor shares one rate limit | The real client IP is not reaching Django | Check that nginx still has the Cloudflare ranges and that `NUM_PROXIES=1`. |

## Cost

The server is the Lightsail 2 GB plan, about **$12 per month**, which includes the static IP and a data transfer
allowance. Other costs depend on your plans with Cloudflare, AWS (the state bucket) and GitHub; check their
current pricing. `terraform destroy` stops the Lightsail charge.

## Teardown

```bash
cd infra/terraform
terraform destroy
```

This removes the server (and the data on it), the static IP and the DNS record. Also delete the S3 state bucket,
the container images on `ghcr.io`, the Cloudflare configuration rule and Origin Certificate, and the GitHub
secrets if you no longer need them.

## Limits

- One server and one gunicorn process: there is no failover, and a deploy restarts the containers (a brief
  outage). That fits a demo; a larger setup would move the records to a shared database first.
- Open-Meteo's free tier (600 locations a minute, 5,000 an hour, 10,000 a day) is the capacity limit. The app
  paces itself under it, and the per-client rate limits protect it from a single user.

To run the same stack on your own machine, see "Running with Docker" in the [README](../Readme.md).
