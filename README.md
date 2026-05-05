# ipinfo

A self-hosted webpage that displays a visitor's IPv4 and IPv6 addresses along with geolocation data (country, region, city, ISP, coordinates, timezone).

## How it works

A single FastAPI backend serves one `/ip` endpoint. Two DNS subdomains — one with only an `A` record, one with only an `AAAA` record — force the browser to connect via each protocol separately. Nginx passes the real client IP via `X-Forwarded-For`. Geolocation is resolved server-side via [ipapi.co](https://ipapi.co).

```
Browser
  ├── GET https://ipv4.yourdomain.com/ip  →  Nginx (IPv4 only)  →  FastAPI  →  { ip: "1.2.3.4", geo: ... }
  └── GET https://ipv6.yourdomain.com/ip  →  Nginx (IPv6 only)  →  FastAPI  →  { ip: "2001:...", geo: ... }
```

## Prerequisites

- A server with a **public IPv4 and IPv6 address**
- Docker and Docker Compose installed
- A domain with DNS management access
- Ports `80` and `443` open in your firewall

Verify your server has both addresses:

```bash
curl -4 ifconfig.me   # should return an IPv4 address
curl -6 ifconfig.me   # should return an IPv6 address
```

## Configuration

### 1. DNS records

Add the following records in your DNS provider (replace the IP addresses with your server's):

| Type | Name | Value |
|------|------|-------|
| `A` | `yourdomain.com` | `203.0.113.10` |
| `AAAA` | `yourdomain.com` | `2001:db8::1` |
| `A` | `ipv4.yourdomain.com` | `203.0.113.10` |
| `AAAA` | `ipv6.yourdomain.com` | `2001:db8::1` |

> **Important:** `ipv4.yourdomain.com` must have **only** an `A` record (no `AAAA`).
> `ipv6.yourdomain.com` must have **only** an `AAAA` record (no `A`).
> This forces each subdomain to be reachable via one protocol only.

### 2. Update domain references

Replace `yourdomain.com` in both files:

**`nginx.docker.conf`** — three `server_name` directives:
```nginx
server_name yourdomain.com;
server_name ipv4.yourdomain.com;
server_name ipv6.yourdomain.com;
```

**`static/index.html`** — two endpoint constants:
```js
const IPV4_ENDPOINT = "https://ipv4.yourdomain.com/ip";
const IPV6_ENDPOINT = "https://ipv6.yourdomain.com/ip";
```

### 3. Enable IPv6 in Docker

Docker's default bridge network is IPv4-only. Add the following to `/etc/docker/daemon.json` on the host (create the file if it doesn't exist):

```json
{
  "ipv6": true,
  "fixed-cidr-v6": "fd00::/80"
}
```

Restart Docker:

```bash
sudo systemctl restart docker
```

## Deployment

### Start

```bash
docker compose up -d
```

### Rebuild after code changes

```bash
docker compose up -d --build
```

### Stop

```bash
docker compose down
```

### View logs

```bash
docker compose logs -f          # all services
docker compose logs -f app      # FastAPI only
docker compose logs -f nginx    # Nginx only
```

## HTTPS (recommended)

HTTPS is required for the frontend to call the subdomain endpoints from a secure origin. Use [Certbot](https://certbot.eff.org/) with the Nginx plugin.

Install Certbot on the host:

```bash
sudo apt install certbot python3-certbot-nginx
```

Stop the Docker Nginx container temporarily (it holds port 80):

```bash
docker compose stop nginx
```

Obtain certificates for all three domains:

```bash
sudo certbot certonly --standalone \
  -d yourdomain.com \
  -d ipv4.yourdomain.com \
  -d ipv6.yourdomain.com
```

Update `nginx.docker.conf` to listen on port 443 and reference the certificates:

```nginx
server {
    listen 443 ssl;
    server_name yourdomain.com;
    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;
    ...
}
```

Mount the certificates directory in `docker-compose.yml`:

```yaml
nginx:
  volumes:
    - ./nginx.docker.conf:/etc/nginx/conf.d/default.conf:ro
    - /etc/letsencrypt:/etc/letsencrypt:ro
```

Restart:

```bash
docker compose up -d
```

## Rate limiting

Rate limiting is applied at two layers.

### Nginx (request layer)

Configured in `nginx.docker.conf`:

| Setting | Value | Effect |
|---|---|---|
| `rate` | `20r/m` per IP | ~1 request every 3 seconds on `/ip` |
| `burst` | `5` | allows a short spike (e.g. first page load triggers 2 requests) |
| `limit_conn` | `5` on subdomains, `10` on main | max concurrent connections per IP |
| `proxy_read_timeout` | `10s` | drops slow/stalled connections |

When the limit is exceeded Nginx returns **HTTP 429** before the request reaches Python.

To tighten or loosen the rate, edit the `rate=` value in `nginx.docker.conf` and restart the nginx container:

```bash
docker compose restart nginx
```

### FastAPI (geo cache layer)

`main.py` caches geolocation results in memory for **30 seconds** (up to 1,000 unique IPs). Repeated requests from the same IP skip the external ipapi.co call entirely, which:

- Reduces outbound HTTP calls on a low-resource VPS
- Stays well within ipapi.co's 1,000 requests/day free tier
- Cuts response latency for returning visitors

Both limits and the TTL can be adjusted via the constants at the top of `main.py`:

```python
_GEO_TTL = 30     # cache lifetime in seconds
_GEO_MAX = 1000   # max IPs to keep in memory
```

## Geolocation limits

Geolocation is provided by [ipapi.co](https://ipapi.co). The free tier allows **1,000 requests per day**. For higher volume, either subscribe to a paid plan or replace the provider in `main.py` with a self-hosted [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) database (requires free registration).

## Project structure

```
ipinfo/
├── Dockerfile              # FastAPI app image (non-root)
├── docker-compose.yml      # Orchestrates app + nginx
├── nginx.docker.conf       # Nginx reverse proxy config
├── .dockerignore
├── main.py                 # FastAPI app
├── requirements.txt
└── static/
    └── index.html          # Frontend
```
