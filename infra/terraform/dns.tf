resource "cloudflare_dns_record" "app" {
  zone_id = var.cloudflare_zone_id
  name    = var.app_domain # full name avoids a perpetual diff
  type    = "A"
  content = aws_lightsail_static_ip.app.ip_address
  proxied = true
  ttl     = 1 # 1 = automatic (required when proxied)
  comment = "weather-aware-truck-routing (managed by Terraform)"
}

# The zone-wide SSL mode is deliberately not managed here: it affects every other host on the domain.
