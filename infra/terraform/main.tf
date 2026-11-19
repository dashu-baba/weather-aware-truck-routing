resource "aws_lightsail_instance" "app" {
  name              = var.instance_name
  availability_zone = var.availability_zone
  blueprint_id      = var.blueprint_id
  bundle_id         = var.bundle_id

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    deploy_ssh_public_key = var.deploy_ssh_public_key
  })

  lifecycle {
    ignore_changes = [user_data] # editing the boot script must not replace the server (and its data)
  }
}

resource "aws_lightsail_static_ip" "app" {
  name = "${var.instance_name}-ip"
}

resource "aws_lightsail_static_ip_attachment" "app" {
  static_ip_name = aws_lightsail_static_ip.app.name
  instance_name  = aws_lightsail_instance.app.name
}

data "cloudflare_ip_ranges" "cf" {}

locals {
  web_ipv4 = var.restrict_web_to_cloudflare ? data.cloudflare_ip_ranges.cf.ipv4_cidrs : ["0.0.0.0/0"]
  web_ipv6 = var.restrict_web_to_cloudflare ? data.cloudflare_ip_ranges.cf.ipv6_cidrs : ["::/0"]
}

# Replaces ALL port rules on the instance.
resource "aws_lightsail_instance_public_ports" "app" {
  instance_name = aws_lightsail_instance.app.name

  port_info {
    protocol   = "tcp"
    from_port  = 22
    to_port    = 22
    cidrs      = var.ssh_allowed_cidrs
    ipv6_cidrs = var.ssh_allowed_ipv6_cidrs
  }

  port_info {
    protocol   = "tcp"
    from_port  = 80
    to_port    = 80
    cidrs      = local.web_ipv4
    ipv6_cidrs = local.web_ipv6
  }

  port_info {
    protocol   = "tcp"
    from_port  = 443
    to_port    = 443
    cidrs      = local.web_ipv4
    ipv6_cidrs = local.web_ipv6
  }
}
