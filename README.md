# Personal Tools

A self-hosted collection of small network utilities, served as a single FastAPI + static-site app.

## IP Lookup

Displays a visitor's IPv4 and IPv6 addresses along with geolocation data (country, region, city, ISP, coordinates, timezone).

### How it works

A single FastAPI backend serves one `/ip` endpoint. Two DNS subdomains — one with only an `A` record, one with only an `AAAA` record — force the browser to connect via each protocol separately. Nginx runs with `network_mode: host` so `$remote_addr` is always the real client IP (not a Docker-internal address). Geolocation is resolved server-side using a local [MaxMind GeoLite2](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data) database (City + ASN), updated weekly by the `geoipupdate` container.

```
Browser
  ├── GET https://ip4.yourdomain.com/ip  →  Nginx (IPv4 only)  →  FastAPI  →  { ip: "1.2.3.4", geo: ... }
  └── GET https://ip6.yourdomain.com/ip  →  Nginx (IPv6 only)  →  FastAPI  →  { ip: "2001:...", geo: ... }
```

Nginx listens on ports `8080`/`8443` internally. Host-level iptables rules forward `80→8080` and `443→8443`, allowing the unprivileged nginx container to handle public traffic without root.

## CIDR Calculator

Given an IPv4 or IPv6 address and a prefix length (e.g. `192.168.1.10` / `24`), computes the start (network) and end (broadcast/last) address of that range.

Served at `/cidr` (`static/cidr.html`). The calculation runs entirely client-side in JavaScript — no backend request is made, so it works even if the GeoLite2 databases or geo cache are unavailable.

## Analytics

Visit counting is handled by a self-hosted [GoatCounter](https://www.goatcounter.com) instance — a single Go binary with a SQLite database, chosen over Umami/Plausible/Matomo because it is cookieless, has an accessibility-focused UI, and adds one small container instead of a stack. No cookie banner is needed and no data leaves the server.

### First-party by design

Both the tracker script and the beacon are served from the main domain, so a visitor's browser never contacts another host:

```
Browser
  ├── GET https://yourdomain.com/count.js       →  Nginx  →  GoatCounter (127.0.0.1:8081)
  └── GET https://yourdomain.com/count?p=/cidr  →  Nginx  →  GoatCounter (127.0.0.1:8081)
```

GoatCounter selects the site by `Host` header, so those two `location` blocks in `nginx.docker.conf` rewrite `Host` to `stats.yourdomain.com` — the vhost the site is created under. They also set `X-Real-IP`/`X-Forwarded-For` from `$remote_addr` and blank out the `Cf-Connecting-Ip`, `Fly-Client-Ip`, and `X-Azure-Socketip` headers, which GoatCounter's real-IP middleware trusts ahead of `X-Real-IP` and a client could otherwise forge.

The pages carry this snippet (see `static/*.html`), with a `<noscript>` pixel so counting also works with JavaScript disabled:

```html
<script data-goatcounter="/count" async src="/count.js"></script>
<noscript><img src="/count?p=/cidr" alt="" aria-hidden="true" width="1" height="1" style="position:absolute"></noscript>
```

The endpoints are relative, so nothing needs a domain substitution when the site is redeployed elsewhere.

### Opt-out

Two independent mechanisms, both documented in `datenschutz.html` / `privacy.html`:

1. **`DNT` / `Sec-GPC` request headers**, honoured in nginx via the `$analytics_optout` map — `/count` returns `204` and never reaches GoatCounter. Because these are request headers, this covers the beacon *and* the `<noscript>` pixel, so it is the only opt-out that works for visitors without JavaScript. Treating these as an objection follows Art. 21 Abs. 5 DSGVO and [LG Berlin, 24.08.2023, 16 O 420/19](https://dejure.org/dienste/vernetzung/rechtsprechung?Gericht=LG+Berlin&Datum=24.08.2023&Aktenzeichen=16+O+420/19).

   **This suppresses real traffic.** Brave sends `Sec-GPC: 1` by default and Firefox exposes a GPC toggle, so expect your numbers to under-represent privacy-conscious visitors — plausibly by several percent. That is the deliberate trade-off; if you ever remove the map, remove the claim from both policies too.

2. **A toggle button** in §5 of each policy, writing the `skipgc` key in `localStorage` that `count.js` checks in its `filter()`. Not GoatCounter's own `#toggle-goatcounter` link — that acts at script-load time, so the hash it leaves behind re-toggles tracking on every refresh.

To exclude **your own** visits, use **Settings → Ignore IPs** in the dashboard rather than the button; it is the purpose-built mechanism and survives clearing browser data.

### One-time setup

The dashboard lives at `https://stats.yourdomain.com` and requires a login. Create the site and owner account once, after the stack is up:

```bash
docker compose exec goatcounter goatcounter db create site \
  -vhost=stats.yourdomain.com -user.email=you@example.com
```

It prompts for a password — do not put one in the repo. GoatCounter's `-smtp` default is `stdout`, so password-reset mails are printed to `docker compose logs goatcounter` rather than sent.

### Privacy settings

Under **Settings → Data collection**, the checkboxes must match what the privacy policy claims:

| Toggle | Setting | Why |
|---|---|---|
| Individual pageviews | **off** (default) | Keeps the DB aggregate-only |
| Sessions | on (default) | Unique-visit counting; see the caveat below |
| Referrer | on (default) | Documented in the policy |
| User-Agent | on (default) | Browser/OS class only — the raw header is not stored |
| Size | on (default) | Documented in the policy |
| Country | on (default) | Documented in the policy |
| **Region** | **turn off** — on by default | The policy promises country-level only |
| Language | **leave off** (default) | Not documented in the policy |

Then set **data retention to 365 days** — that is the 12 months the policy promises. Under **Settings → Site**, confirm the dashboard is not public.

Location resolution uses the country-level database compiled into GoatCounter, not the GeoLite2 City database used by `/ip`, so analytics cannot record anything finer than a country even if Region were enabled.

**Session caveat worth knowing:** with Sessions on, GoatCounter keys its 8-hour session table on the literal string `User-Agent + IP + site ID` ([`memstore.go`](https://github.com/arp242/goatcounter/blob/release-2.7/memstore.go)). It is not a hash. That table lives in memory, is evicted 8 hours after the last request, and is written to the SQLite `store` table on shutdown and read back on startup — so full IPs can briefly touch disk. Only the random session ID ever reaches the statistics tables. Both privacy policies describe this accurately; if you turn Sessions off, reload the wording too.

### Backups

The SQLite database lives in the `goatcounter_data` named volume:

```bash
docker run --rm -v ip-lookup_goatcounter_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/goatcounter-$(date +%F).tar.gz -C /data .
```

### Upgrades

Bump the image tag in `docker-compose.yml`, then `docker compose pull && docker compose up -d`. The service runs with `-automigrate`, so schema migrations apply on startup.

## Development

```bash
pip install -r requirements-dev.txt

ruff check .            # lint
ruff format .           # format
python -m pytest        # Python tests (main.py)
node --test             # CIDR calculator JS tests (static/cidr-logic.js)
```

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
| `A` | `stats.yourdomain.com` | your server's IPv4 |
| `AAAA` | `stats.yourdomain.com` | your server's IPv6 |

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

**`nginx.docker.conf`** — `server_name` directives, plus the `proxy_set_header Host stats.…` lines in the `/count` and `/count.js` blocks  
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
docker compose logs -f goatcounter # Analytics
```

## HTTPS

HTTPS is handled automatically. Certbot issues a Let's Encrypt certificate during `bootstrap.sh` covering all four domains (`yourdomain.com`, `ip4.yourdomain.com`, `ip6.yourdomain.com`, `stats.yourdomain.com`) and renews it automatically every 12 hours (renews when within 30 days of expiry).

Certificates are stored in `certbot/conf/` (excluded from git via `.gitignore`).

### Adding a domain to an existing certificate

An already-deployed server has a certificate without `stats.yourdomain.com`. Add it once with `--expand` (the DNS records must resolve first, and the stack must be running so nginx can answer the ACME challenge):

```bash
docker compose run --rm --entrypoint certbot certbot certonly --webroot -w /var/www/certbot --expand \
  -d yourdomain.com -d ip4.yourdomain.com -d ip6.yourdomain.com -d stats.yourdomain.com
docker compose restart nginx
```

Then re-check the file permissions below; the `fix-permissions.sh` deploy hook covers automatic renewals but not this manual run.

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
├── docker-compose.yml      # Orchestrates app + nginx + certbot + geoipupdate + goatcounter
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
├── requirements-dev.txt    # + pytest, httpx, ruff
├── pyproject.toml          # ruff + pytest config
├── tests/                  # pytest (main.py) + Node test (cidr-logic.js)
└── static/
    ├── index.html          # Landing page
    ├── getip.html          # IP lookup tool
    ├── cidr.html           # CIDR range calculator
    ├── cidr-logic.js       # CIDR parsing/math, shared with the JS tests
    ├── up.html             # Reachability checker
    ├── impressum.html
    ├── datenschutz.html    # German privacy policy
    ├── privacy.html        # English privacy policy
    └── style.css
```
