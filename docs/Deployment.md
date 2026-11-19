# Deployment

The app runs on one small server, in four Docker containers, behind Cloudflare. Terraform creates the server
and the DNS record, and GitHub Actions tests, builds and deploys every push to `main`.

## Architecture

```
Browser
  │  https://truckroute.<domain>
  ▼
Cloudflare (DNS record, proxied; terminates the public TLS connection)
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
pacing that keeps the app under Open-Meteo's per-minute, hourly and daily limits, then happens in exactly one
process. The web process stays free to answer status polls while a long download runs. The backend runs one
gunicorn process for the same reason: the plan cache and the request throttles are per process.

The three Python containers share the `app-data` volume. SQLite runs in WAL mode, which is safe across
containers on one host with one writer at a time. This is also why the app needs one machine with a disk
rather than several instances.

## nginx

- **Port 80:** `/healthz` returns `ok` (the container health check). Everything else is a `301` to HTTPS.
- **Port 443, `/api/`:** proxied to `backend:8000`, keeping the `/api` prefix. 60-second read timeout.
- **Port 443, `/assets/`:** hashed file names, so `Cache-Control: public, max-age=31536000, immutable`.
- **Port 443, `/`:** the React app. `index.html` is never cached (`no-cache`), and unknown paths fall back to it.
- Every location sends `X-Content-Type-Options`, `Referrer-Policy` and `X-Frame-Options`. They are included from
  a snippet into each location because nginx drops inherited `add_header` lines in a location that sets its own.
- There is no Content-Security-Policy yet. MapLibre needs `blob:` workers and the OpenFreeMap tile host, so add
  one only together with a check of the map.

## Request path and real client IPs

Browser → Cloudflare → nginx → Django.

Behind Cloudflare, every connection reaches the server from a Cloudflare address. To keep the visitor's address
(the rate limits are per client):

1. nginx trusts `CF-Connecting-IP` only when the connection comes from a Cloudflare range
   (`frontend/nginx/snippets/cloudflare-realip.conf`). Regenerate the list with
   `deploy/scripts/update-cloudflare-ips.sh`.
2. nginx then sends `X-Forwarded-For: <client address>`, overwriting any value the client sent.
3. Django runs with `NUM_PROXIES=1` and reads that single entry.

A client therefore cannot spoof its address with its own `X-Forwarded-For` header.

## TLS

- Visitors connect to Cloudflare, which presents its own certificate.
- Between Cloudflare and nginx, traffic uses a **Cloudflare Origin Certificate**, stored as
  `/opt/truckroute/certs/origin.pem` and `origin.key` (created by the deploy job from GitHub secrets). It is valid
  for years, so nothing renews on the server.
- The Cloudflare zone's SSL mode must be **Full** or **Full (strict)**. Terraform does not set it, because it
  applies to every host on the domain.
- By default the firewall accepts ports 80 and 443 only from Cloudflare's address ranges, so the server cannot be
  reached directly.

## CI/CD (`.github/workflows/ci-cd.yml`)

| Stage | When | What |
|---|---|---|
| `backend` | every push and PR | `ruff check`, `pytest` |
| `frontend` | every push and PR | `npm run lint`, `npm test`, `npm run build` |
| `terraform` | every push and PR | `terraform fmt -check`, `init -backend=false`, `validate` (no cloud credentials) |
| `images` | push to `main`, after the three above | Build the backend and web images for `linux/amd64` and push them to `ghcr.io` |
| `deploy` | after `images` | Copy the compose file, `deploy.sh`, the `.env` and the certificate to the server, run `deploy.sh`, then smoke-test `https://<domain>/api/health` and `/` |

`deploy.sh` (on the server) pulls the images, runs `migrate`, starts the stack, waits up to 90 seconds for the
backend health check, and records the tag in `/opt/truckroute/DEPLOYED_TAG`. If the backend does not become
healthy, it prints the backend log and fails the run.

Pull requests run the three checks only. Runs on `main` are never cancelled by newer pushes, and the deploy job
has its own group, so a running deploy always finishes.

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
token that can read packages. Rolling back does not undo database migrations. Migrations here only add tables
and columns, so older code keeps working, but check before rolling back past a migration.

## Secrets

| Where | What |
|---|---|
| GitHub environment `production`, secrets | `DEPLOY_SSH_KEY`, `DEPLOY_KNOWN_HOSTS`, `DJANGO_SECRET_KEY`, `TOMTOM_API_KEY`, `CF_ORIGIN_CERT`, `CF_ORIGIN_KEY` |
| GitHub environment `production`, variables | `APP_DOMAIN`, `DEPLOY_HOST`, `DEPLOY_USER` |
| Server | `/opt/truckroute/.env` and `certs/origin.key`, both mode 600, written by the deploy job |

Secrets never go in git, in an image, in the frontend bundle or in a workflow log. The deploy job builds the
server `.env` from the GitHub secrets, passes the registry token only through `ssh` standard input, checks the
server's host key against the stored `known_hosts`, and deletes its local key files when it ends. The `web`
container gets no environment file, so the TomTom key never enters it.

## Infrastructure (`infra/terraform/`)

| Resource | Purpose |
|---|---|
| `aws_lightsail_instance` | Ubuntu 24.04, plan `small_3_0` (2 GB RAM, 2 vCPU), `us-east-1`. First boot installs Docker, adds the deploy SSH key, creates `/opt/truckroute`, and adds a 1 GB swap file. |
| `aws_lightsail_static_ip` and attachment | A fixed public address. |
| `aws_lightsail_instance_public_ports` | SSH (22) with key-only login. Ports 80 and 443 only from Cloudflare's ranges (`restrict_web_to_cloudflare`). SSH over IPv6 is closed unless set. |
| `cloudflare_dns_record` | Proxied `A` record for the app domain. |

State is stored in an S3 bucket with native locking. See `infra/terraform/README.md` for the one-time setup and
the commands.

## Cost

About **$12 per month**: the Lightsail 2 GB plan, with the static IP and data transfer included. Cloudflare's
free plan covers DNS and the proxy, and GitHub Container Registry and Actions are free at this size. The state
bucket costs cents.

## Teardown

```bash
cd infra/terraform
terraform destroy
```

This removes the server (and the data on it), the static IP and the DNS record, and stops the charges. Also
delete the S3 state bucket, the container images on `ghcr.io`, and the GitHub secrets if they are no longer
needed.

## Running the same stack locally

```bash
cd deploy
cp .env.example .env                 # set IMAGE_OWNER=local, APP_DOMAIN=localhost, your TomTom key,
                                     # DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,backend
./scripts/make-local-cert.sh         # self-signed certificate for https://localhost
docker compose -f docker-compose.yml -f docker-compose.local.yml up --build -d
docker compose -f docker-compose.yml -f docker-compose.local.yml run --rm backend python manage.py migrate --noinput
open https://localhost               # accept the browser's certificate warning
```

Stop it with `docker compose -f docker-compose.yml -f docker-compose.local.yml down`.

## Limits

- One server and one gunicorn process: there is no failover, and a deploy restarts the containers (a brief
  outage). That fits a demo; a larger setup would move the records to a shared database first.
- Open-Meteo's free tier (600 locations a minute, 5,000 an hour, 10,000 a day) is the capacity limit. The app
  paces itself under it and the rate limits protect it from a single client.
