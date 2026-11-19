variable "aws_region" {
  description = "AWS region for the Lightsail server."
  type        = string
  default     = "us-east-1"
}

variable "availability_zone" {
  description = "Availability zone inside aws_region."
  type        = string
  default     = "us-east-1a"
}

variable "instance_name" {
  description = "Name of the Lightsail instance (the static IP is named after it)."
  type        = string
  default     = "truckroute"
}

variable "bundle_id" {
  description = "Lightsail plan. small_3_0 is 2 GB RAM, 2 vCPU, about $12/month. Confirm with `aws lightsail get-bundles`."
  type        = string
  default     = "small_3_0"
}

variable "blueprint_id" {
  description = "Lightsail OS image."
  type        = string
  default     = "ubuntu_24_04"
}

variable "deploy_ssh_public_key" {
  description = "Public half of the GitHub Actions deploy key. It is added to the ubuntu user on first boot."
  type        = string
}

variable "ssh_allowed_cidrs" {
  description = "IPv4 ranges allowed to reach port 22. GitHub-hosted runners have no fixed IPs, so the default is open; login is key-only."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "ssh_allowed_ipv6_cidrs" {
  description = "IPv6 ranges allowed to reach port 22. Empty by default: GitHub runners and most admins connect over IPv4."
  type        = list(string)
  default     = []
}

variable "cloudflare_zone_id" {
  description = "Cloudflare zone ID of the domain."
  type        = string
}

variable "app_domain" {
  description = "Full host name for the app, for example truckroute.example.com."
  type        = string
}

variable "restrict_web_to_cloudflare" {
  description = "When true, ports 80 and 443 accept only Cloudflare IP ranges."
  type        = bool
  default     = true
}
