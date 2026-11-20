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

  # The instance name stays the same when the server is replaced, so Terraform would not notice that the
  # new server has no static IP. Redo the attachment whenever the instance is replaced.
  lifecycle {
    replace_triggered_by = [aws_lightsail_instance.app.id]
  }
}

data "cloudflare_ip_ranges" "cf" {}

locals {
  web_ipv4 = var.restrict_web_to_cloudflare ? data.cloudflare_ip_ranges.cf.ipv4_cidrs : ["0.0.0.0/0"]
  web_ipv6 = var.restrict_web_to_cloudflare ? data.cloudflare_ip_ranges.cf.ipv6_cidrs : ["::/0"]
}

# Replaces ALL port rules on the instance.
resource "aws_lightsail_instance_public_ports" "app" {
  instance_name = aws_lightsail_instance.app.name

  # Same reason: a replaced server starts with Lightsail's default firewall, so apply the rules again.
  lifecycle {
    replace_triggered_by = [aws_lightsail_instance.app.id]
  }

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
