# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

Local development (no test suite or linter is configured in this repo):

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000   # serves static/ + API on http://localhost:8000
curl http://localhost:8000/health
```

Docker (mirrors production):

```bash
docker compose up -d --build
docker compose logs -f app     # FastAPI only
docker compose logs -f nginx
```

`./bootstrap.sh` is one-time, first-server-setup only (iptables port forwarding, Let's Encrypt issuance via a temporary nginx container) — never run it as part of normal iteration.

## Architecture

This is a single FastAPI app (`main.py`) serving a static multi-tool site (`static/*.html`) for `alexander-hagemann.de`. There is no build step or frontend framework — every page is hand-written HTML/CSS/vanilla JS, self-contained (styles inline in a `<style>` block per page), sharing only `static/style.css` for base resets/typography.

**Two tools live behind explicit FastAPI routes** (`/getip` → `static/getip.html`, `/cidr` → `static/cidr.html`); everything else is served by the `StaticFiles` mount at the end of `main.py`. When adding a new tool page, follow this same pattern: add the HTML under `static/`, add a `@app.get("/<name>")` route returning `FileResponse`, and add a tile linking to it from `static/index.html`.

**IP Lookup (`/ip` endpoint + `getip.html`)** is the one tool with real backend logic, and its design only makes sense together:
- The site resolves IPv4 and IPv6 *independently* using two DNS subdomains (`ip4.`/`ip6.` — one has only an `A` record, the other only `AAAA`), so a dual-stack visitor gets both addresses from two separate same-origin-restricted requests rather than one ambiguous lookup. `getip.html` hardcodes both subdomain endpoints and fetches both in parallel.
- Nginx runs with `network_mode: host` specifically so `$remote_addr`/`X-Forwarded-For` is the real client IP, not a Docker bridge address — don't "fix" this by putting nginx on the compose bridge network.
- `main.py`'s root `/` route branches on `_is_browser()` (User-Agent sniffing): browsers get `index.html`, everything else (curl, scripts) gets a raw JSON `{timestamp, ipv4, ipv6}` — this is a deliberate dual-purpose endpoint, not an oversight.
- Geolocation is resolved server-side from local MaxMind GeoLite2 `.mmdb` files (loaded once at startup into module-level `_city_reader`/`_asn_reader`; retried every 30s via a background task if missing, since `geoipupdate` may not have populated the volume yet on first boot) and cached in-process per-IP for 1 hour (`_geo_cache`, capped at 1000 entries, evicted oldest-first). No external geo API calls happen at request time.
- IPs are truncated to /24 (v4) or /48 (v6) before logging (`_truncate_ip`) — never log full client IPs.

**CIDR Calculator (`/cidr` + `cidr.html`)** is intentionally backend-free: all IPv4/IPv6 parsing, prefix-mask math, and address formatting (including `::` compression and embedded IPv4-mapped addresses) is done client-side in JS using `BigInt`, so it works even if GeoLite2/the geo cache is down. Don't add a server round-trip for this.

**Nginx configs are environment-specific, not interchangeable:** `nginx.conf` is for a bare-metal (non-Docker) deployment; `nginx.docker.conf` is the real one used by `docker-compose.yml` (listens on unprivileged 8080/8443, host network mode); `nginx.init.conf` is a minimal bootstrap-only config used solely to serve ACME challenges before real certs exist. When changing routing/rate-limit rules, `nginx.docker.conf` is almost always the one that matters.

## Design constraints (see PRODUCT.md / DESIGN.md for full detail)

This is a deliberately monochrome, ad-free "quiet terminal" aesthetic — not generic SaaS styling:
- Pure black background, grayscale ink only, zero hue anywhere (one reserved retro accent color is planned but *not yet* in the codebase — don't add color piecemeal).
- Square corners everywhere (`border-radius: 0`), no shadows — grouping/elevation is conveyed only via 1px borders.
- Single font family end-to-end: `"Courier New", Courier, monospace`.
- Every page heading is prefixed with an `aria-hidden` `// `; back-links use an `aria-hidden` `← ` — keep both conventions on new pages.
- WCAG 2.1 AA is a hard constraint: skip links, `aria-live` on dynamic content, visible focus states, and `prefers-reduced-motion` fallbacks for any animation (e.g. the blinking-cursor loading state) are expected on every new page, not just the existing ones.
