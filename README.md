# ipinfo

A self-hosted webpage that displays a visitor's IPv4 and IPv6 addresses along with geolocation data (country, region, city, ISP, coordinates, timezone).

## How it works

A single FastAPI backend serves one `/ip` endpoint. Two DNS subdomains — one with only an `A` record, one with only an `AAAA` record — force the browser to connect via each protocol separately. Nginx runs with `network_mode: host` so `$remote_addr` is always the real client IP (not a Docker-internal address). Geolocation is resolved server-side using a local [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) database (City + ASN), updated weekly by the `geoipupdate` container.

```
Browser
  ├── GET https://ip4.yourdomain.com/ip  →  Nginx (IPv4 only)  →  FastAPI  →  { ip: "1.2.3.4", geo: ... }
  └── GET https://ip6.yourdomain.com/ip  →  Nginx (IPv6 only)  →  FastAPI  →  { ip: "2001:...", geo: ... }
```

Nginx listens on ports `8080`/`8443` internally. Host-level iptables rules forward `80→8080` and `443→8443`, allowing the unprivileged nginx container to handle public traffic without root.

## Prerequisites

- A server with a **public IPv4 and IPv6 address**
- Docker and Docker Compose installed
- A domain with DNS management access
- Ports `80` and `443` open in your firewall
- A free [MaxMind account](https://www.maxmind.com/en/geolite2/signup) with a GeoLite2 license key

Verify your server has both addresses:

```bash
curl -4 ifconfig.me   # should return an IPv4 address
curl -6 ifconfig.me   # should return an IPv6 address
```

## Configuration

### 1. DNS records

| Type | Name | Value |
|------|------|-------|
| `A` | `yourdomain.com` | your server's IPv4 |
| `AAAA` | `yourdomain.com` | your server's IPv6 |
| `A` | `ip4.yourdomain.com` | your server's IPv4 |
| `AAAA` | `ip6.yourdomain.com` | your server's IPv6 |

> **Important:** `ip4.yourdomain.com` must have **only** an `A` record (no `AAAA`).
> `ip6.yourdomain.com` must have **only** an `AAAA` record (no `A`).
> This forces each subdomain to be reachable via one protocol only.

### 2. MaxMind credentials

Create a `.env` file from the example and fill in your MaxMind account ID and license key:

```bash
cp .env.example .env
nano .env
```

Or set both values in one command:

```bash
cat > .env << EOF
MAXMIND_ACCOUNT_ID=your_account_id
MAXMIND_LICENSE_KEY=your_license_key
EOF
```

You can find your account ID and generate a license key in the [MaxMind portal](https://www.maxmind.com/en/account) under **Services → My License Key**.

### 3. Update domain references

Replace `yourdomain.com` in:

**`nginx.docker.conf`** — `server_name` directives  
**`static/getip.html`** — two endpoint constants  
**`bootstrap.sh`** — `DOMAIN` variable

## Deployment

### First-time setup

`bootstrap.sh` handles everything in order: iptables port forwarding, Let's Encrypt certificate issuance, and starting the stack.

```bash
./bootstrap.sh
```

After it completes, make the iptables rules persistent across reboots:

```bash
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

### Subsequent deploys

```bash
git pull
docker compose up -d --build
```

### Common commands

```bash
docker compose up -d          # start
docker compose down           # stop
docker compose restart nginx  # reload nginx config
docker compose logs -f        # all logs
docker compose logs -f app    # FastAPI only
docker compose logs -f nginx       # Nginx only
docker compose logs -f geoipupdate # GeoLite2 database update
```

## HTTPS

HTTPS is handled automatically. Certbot issues a Let's Encrypt certificate during `bootstrap.sh` covering all three domains (`yourdomain.com`, `ip4.yourdomain.com`, `ip6.yourdomain.com`) and renews it automatically every 12 hours (renews when within 30 days of expiry).

Certificates are stored in `certbot/conf/` (excluded from git via `.gitignore`).

### Certificate file permissions

Certbot creates certificate files owned by root. The unprivileged nginx container needs read access. Fix after issuance and after any manual renewal:

```bash
sudo chmod -R 755 certbot/conf/live certbot/conf/archive
sudo chmod 644 certbot/conf/archive/yourdomain.com/privkey*.pem
```

A deploy hook at `certbot/conf/renewal-hooks/deploy/fix-permissions.sh` runs this automatically after each automatic renewal.

## Port forwarding

Nginx listens on `8080` (HTTP) and `8443` (HTTPS) as an unprivileged user. iptables redirects public ports to these:

```bash
# Set up (already done by bootstrap.sh)
# Scoped to eth0 so Docker container outbound traffic is not affected
sudo iptables  -t nat -A PREROUTING -i eth0 -p tcp --dport 80  -j REDIRECT --to-port 8080
sudo iptables  -t nat -A PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8443
sudo ip6tables -t nat -A PREROUTING -i eth0 -p tcp --dport 80  -j REDIRECT --to-port 8080
sudo ip6tables -t nat -A PREROUTING -i eth0 -p tcp --dport 443 -j REDIRECT --to-port 8443

# Persist across reboots
sudo apt install iptables-persistent
sudo netfilter-persistent save
```

## Rate limiting

### Nginx (request layer)

| Setting | Value | Effect |
|---|---|---|
| `rate` | `20r/m` per IP | ~1 request every 3 seconds on `/ip` |
| `burst` | `5` | allows a short spike (e.g. first page load triggers 2 requests) |
| `limit_conn` | `5` on subdomains, `10` on main | max concurrent connections per IP |
| `proxy_read_timeout` | `10s` | drops slow/stalled connections |

When the limit is exceeded Nginx returns **HTTP 429** before the request reaches Python.

### FastAPI (geo cache layer)

`main.py` caches geolocation results in memory for **1 hour** (up to 1,000 unique IPs). Repeated requests from the same IP reuse the cached result.

```python
_GEO_TTL = 3600   # cache lifetime in seconds
_GEO_MAX = 1000   # max IPs to keep in memory
```

## Geolocation

Geolocation uses local [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) databases (City + ASN). Two `.mmdb` files are stored in a Docker volume and refreshed weekly by the `geoipupdate` container. No external API calls are made at request time.

GeoLite2 is free but requires attribution. This database incorporates GeoLite2 data created by MaxMind, available from [maxmind.com](https://www.maxmind.com).

## Server housekeeping

### Update packages

```bash
sudo apt update && sudo apt upgrade -y && sudo apt autoremove -y
```

### Update Docker images

```bash
docker compose pull
docker compose up -d
```

### Non-root user (recommended)

```bash
adduser alex
usermod -aG sudo alex
usermod -aG docker alex
# copy SSH key, then:
sudo rm -rf /root/.ssh
echo "PasswordAuthentication no" | sudo tee -a /etc/ssh/sshd_config
sudo systemctl restart ssh
```

## Project structure

```
ipinfo/
├── Dockerfile              # FastAPI app image (non-root)
├── docker-compose.yml      # Orchestrates app + nginx + certbot + geoipupdate
├── nginx.docker.conf       # Nginx reverse proxy (host network, ports 8080/8443)
├── nginx.init.conf         # Minimal HTTP config used only during bootstrap
├── nginx.conf              # Nginx config for non-Docker deployments
├── bootstrap.sh            # First-time setup: iptables + certs + stack start
├── .env                    # MaxMind credentials (not in git)
├── .env.example            # Credential template
├── .dockerignore
├── .gitignore
├── main.py                 # FastAPI app
├── requirements.txt
└── static/
    ├── index.html          # Landing page
    ├── getip.html          # IP lookup tool
    ├── impressum.html
    ├── datenschutz.html
    └── style.css
```
