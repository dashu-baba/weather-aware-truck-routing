provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project   = "weather-aware-truck-routing"
      ManagedBy = "terraform"
    }
  }
}

provider "cloudflare" {} # reads CLOUDFLARE_API_TOKEN from the environment
