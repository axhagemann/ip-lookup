#!/bin/bash
# First-time Let's Encrypt certificate issuance.
# Run this once on a fresh server before starting docker compose.
set -e

EMAIL="mail@alexander-hagemann.de"
DOMAIN="alexander-hagemann.de"

mkdir -p certbot/www certbot/conf

echo "==> Starting temporary nginx for ACME challenges..."
docker run -d --rm \
  --name nginx-init \
  -p 80:80 \
  -v "$(pwd)/certbot/www:/var/www/certbot:ro" \
  -v "$(pwd)/nginx.init.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginx:alpine

echo "==> Issuing certificates..."
docker run --rm \
  -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  -d "ipv4.$DOMAIN" \
  -d "ipv6.$DOMAIN" \
  --email "$EMAIL" --agree-tos --no-eff-email

echo "==> Stopping temporary nginx..."
docker stop nginx-init

echo "==> Starting full stack..."
docker compose up -d

echo "==> Done. Certificates are in certbot/conf/live/$DOMAIN/"
