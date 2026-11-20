# Terraform: server and DNS

Creates the production host for the app:

- one Amazon Lightsail instance (Ubuntu 24.04, the 2 GB plan `small_3_0`) in `us-east-1`;
- a static IP attached to it;
- firewall rules: SSH (22) for the deploy key, HTTP/HTTPS (80, 443) open only to Cloudflare's IP ranges
  (set `restrict_web_to_cloudflare = false` to open them to everyone);
- a proxied Cloudflare `A` record for the app's domain.

On first boot the server installs Docker, adds the deploy SSH key to the `ubuntu` user, creates `/opt/truckroute`
and adds a 1 GB swap file. The application itself is deployed later by GitHub Actions.

Not managed here: the Cloudflare SSL mode. It must be **Full (strict)** for this host. Set it with a Configuration
Rule for the host name, or on the zone if nothing else on the domain needs a different mode (see
[docs/Deployment.md](../../docs/Deployment.md#tls-and-cloudflare-settings)).

## One-time prerequisites

1. **State bucket.** An S3 bucket for Terraform state, versioning and encryption on. Copy `backend.hcl.example`
   to `backend.hcl` and set the bucket name.
2. **AWS credentials** that can manage Lightsail and read/write that bucket (for example `aws configure`).
3. **Cloudflare API token** with *Zone: DNS: Edit* on the domain's zone, exported as `CLOUDFLARE_API_TOKEN`.
4. **Deploy SSH key.** Generate a key pair for GitHub Actions:
   `ssh-keygen -t ed25519 -f ~/.ssh/truckroute_deploy -C truckroute-deploy`. The public half goes in
   `terraform.tfvars`; the private half becomes a GitHub secret.
5. Copy `terraform.tfvars.example` to `terraform.tfvars` and fill in the placeholders. Both `backend.hcl` and
   `terraform.tfvars` are git-ignored.

## Commands

```bash
cd infra/terraform
terraform init -backend-config=backend.hcl
terraform plan
terraform apply
terraform output            # static_ip, app_url, ssh_command
terraform destroy           # removes the server, IP and DNS record (and the data on the server)
```

Without cloud credentials you can still check the configuration:

```bash
terraform fmt -check -recursive
terraform init -backend=false
terraform validate
```

## Cost

About **$12 per month** for the Lightsail plan, with the static IP and a data transfer allowance included. The state
bucket and DNS are billed separately by AWS and Cloudflare; check their current pricing. `terraform destroy` stops
the Lightsail charge.

## After `apply`

1. Wait a few minutes for the first boot (it installs Docker), then check
   `ssh -i ~/.ssh/truckroute_deploy ubuntu@<static_ip> 'cloud-init status'` prints `status: done`.
2. Save the server's host key: `ssh-keyscan -t ed25519 <static_ip> > ~/.ssh/truckroute_known_hosts`. It becomes the
   `DEPLOY_KNOWN_HOSTS` GitHub secret.
3. Continue with the GitHub setup in [docs/Deployment.md](../../docs/Deployment.md#first-time-setup).

## Notes

- `user_data` runs once, at first boot, and changes to it are ignored afterwards, so editing the boot script never
  replaces the server. Change a running server over SSH, or replace it with
  `terraform apply -replace=aws_lightsail_instance.app`.
- Replacing the server deletes the data on it and gives it a new SSH host key (update `DEPLOY_KNOWN_HOSTS`). The IP
  attachment and firewall rules are recreated with it.
- The first-boot script runs under `sh`, not bash. Keep it POSIX (no `set -o pipefail`).
- If `apply` rejects the number of firewall ranges, set `restrict_web_to_cloudflare = false`. Cloudflare still
  hides the origin; the firewall is just less strict.
