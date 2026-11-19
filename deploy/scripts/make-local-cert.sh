#!/usr/bin/env bash
# Self-signed certificate for testing the stack on https://localhost. Not for production.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p certs
openssl req -x509 -newkey rsa:2048 -nodes -days 365 \
  -subj "/CN=localhost" -addext "subjectAltName=DNS:localhost,IP:127.0.0.1" \
  -keyout certs/origin.key -out certs/origin.pem
chmod 600 certs/origin.key
echo "Wrote deploy/certs/origin.pem and deploy/certs/origin.key"
