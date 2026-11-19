output "static_ip" {
  description = "Public IP of the server."
  value       = aws_lightsail_static_ip.app.ip_address
}

output "app_url" {
  description = "Where the app is served."
  value       = "https://${var.app_domain}"
}

output "ssh_command" {
  description = "Log in as the deploy user."
  value       = "ssh -i ~/.ssh/truckroute_deploy ubuntu@${aws_lightsail_static_ip.app.ip_address}"
}
