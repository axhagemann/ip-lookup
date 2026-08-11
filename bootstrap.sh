#!/bin/bash
# First-time Let's Encrypt certificate issuance.
# Run this once on a fresh server before starting docker compose.
set -e

EMAIL="mail@alexander-hagemann.de"
DOMAIN="alexander-hagemann.de"

mkdir -p certbot/www certbot/conf

echo "==> Setting up port forwarding (80→8080, 443→8443)..."
# Scoped to eth0 so Docker container outbound traffic on these ports is not redirected
sudo iptables  -t nat -C PREROUTING -i eth0 -p tcp --dport 80  -j REDIRECT --to-port 8080 2>/dev/null || \
  sudo iptables  -t nat -A PREROUTING -i eth0 -p tcp --dport 80  -j REDIRECT --to-port 8080
sudo iptables  -t nat -C PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8443 2>/dev/null || \
  sudo iptables  -t nat -A PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8443
sudo ip6tables -t nat -C PREROUTING -i eth0 -p tcp --dport 80  -j REDIRECT --to-port 8080 2>/dev/null || \
  sudo ip6tables -t nat -A PREROUTING -i eth0 -p tcp --dport 80  -j REDIRECT --to-port 8080
sudo ip6tables -t nat -C PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8443 2>/dev/null || \
  sudo ip6tables -t nat -A PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8443

echo "==> Starting temporary nginx for ACME challenges..."
docker run -d --rm \
  --name nginx-init \
  --network host \
  -v "$(pwd)/certbot/www:/var/www/certbot:ro" \
  -v "$(pwd)/nginx.init.conf:/etc/nginx/conf.d/default.conf:ro" \
  nginxinc/nginx-unprivileged:alpine

echo "==> Issuing certificates..."
docker run --rm \
  -v "$(pwd)/certbot/conf:/etc/letsencrypt" \
  -v "$(pwd)/certbot/www:/var/www/certbot" \
  certbot/certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN" \
  -d "ip4.$DOMAIN" \
  -d "ip6.$DOMAIN" \
  -d "stats.$DOMAIN" \
  --email "$EMAIL" --agree-tos --no-eff-email

echo "==> Stopping temporary nginx..."
docker stop nginx-init

echo "==> Installing logrotate config for Docker logs..."
sudo cp logrotate.conf /etc/logrotate.d/ipinfo
sudo chmod 644 /etc/logrotate.d/ipinfo

echo "==> Starting full stack..."
docker compose up -d

echo ""
echo "==> Done. Certificates are in certbot/conf/live/$DOMAIN/"
echo ""
echo "    To persist iptables rules across reboots:"
echo "      sudo apt install iptables-persistent"
echo "      sudo netfilter-persistent save"
