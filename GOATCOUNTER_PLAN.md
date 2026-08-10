# Plan: Add Self-Hosted GoatCounter Analytics to ip-lookup

> **Context for the executing agent (Claude Code or similar):**
> This repo (github.com/axhagemann/ip-lookup) is a self-hosted FastAPI + static-site
> app behind an nginx reverse proxy in Docker (`network_mode: host`, nginx listens on
> 8080/8443 as unprivileged user, iptables forwards 80→8080 and 443→8443).
> TLS is handled by certbot (Let's Encrypt) covering `yourdomain.com`,
> `ip4.yourdomain.com`, `ip6.yourdomain.com`. Geolocation uses local MaxMind
> GeoLite2 databases updated by a `geoipupdate` container.
> The owner wants **visit counting only** (no funnels/segmentation), fully
> self-hosted, GDPR-compliant (Germany/EU), and the frontend must remain
> **WCAG 2.2 AAA** compliant. GoatCounter was deliberately chosen over
> Umami/Plausible/Matomo for its minimalism (single Go binary, SQLite,
> official Docker image `arp242/goatcounter`, accessibility-focused UI,
> cookieless tracking).

---

## Decisions already made (do not re-litigate)

| Decision | Choice | Rationale |
|---|---|---|
| Analytics tool | GoatCounter (self-hosted) | Lightest option, matches project minimalism, cookieless, accessibility-focused |
| Database | SQLite (default) | No extra Postgres container; traffic is small; DB lives in a named Docker volume |
| TLS for stats | Existing nginx + certbot | Do NOT use GoatCounter's built-in ACME; reuse the established cert workflow |
| Hostname | `stats.yourdomain.com` | New subdomain, reverse-proxied like ip4/ip6 |
| Tracking method | First-party proxied JS script (preferred) with `<noscript>` pixel fallback | Serve `count.js` from own domain, not `gc.zgo.at`, to avoid third-party requests and adblock false positives |
| Dashboard access | Owner only (GoatCounter login) | Not public |

---

## Phase 1 — Infrastructure

### 1.1 DNS
Add records (document in README's DNS table):
- `A    stats.yourdomain.com  → server IPv4`
- `AAAA stats.yourdomain.com  → server IPv6`

### 1.2 TLS certificate
Extend the certbot certificate to include `stats.yourdomain.com`:
- Update the certbot invocation in `bootstrap.sh` (add `-d stats.yourdomain.com`).
- For the already-deployed server, run certbot `--expand` once manually; note this in README.
- Verify the `fix-permissions.sh` deploy hook still covers the cert paths.

### 1.3 docker-compose.yml — new service
Add a `goatcounter` service:
- Image: `arp242/goatcounter` (pin a release tag, e.g. `arp242/goatcounter:2.7`, not `latest`).
- Named volume `goatcounter-data:/home/goatcounter/goatcounter-data` (holds SQLite DB).
- Listen on an internal port that does not collide with 8080/8443 (e.g. `GOATCOUNTER_LISTEN=:8081`).
- Because nginx runs with `network_mode: host`, either run goatcounter with host networking too and bind to `127.0.0.1:8081`, or publish `127.0.0.1:8081:8081`. **Bind to localhost only** — the container must not be directly reachable from the internet.
- Add `-automigrate` (via `GOATCOUNTER_AUTOMIGRATE` or command args) so upgrades run DB migrations on startup.
- `restart: unless-stopped`, consistent with existing services.
- Declare the named volume at the bottom of the compose file.

### 1.4 First-site creation (one-time)
Document in README:
```
docker compose exec goatcounter goatcounter db create site \
  -vhost=stats.yourdomain.com -user.email=<owner-email>
```
(Prompts for password; do not hardcode one in the repo.)

### 1.5 nginx.docker.conf — new server block
Add a `server` block for `stats.yourdomain.com`, modeled on the existing subdomain blocks:
- Listen 8443 ssl (and 8080 → 301 redirect to https, matching existing pattern).
- `proxy_pass http://127.0.0.1:8081;`
- **Critical:** pass the real client IP so GoatCounter's location stats work:
  `proxy_set_header X-Real-IP $remote_addr;` and `X-Forwarded-For`, `X-Forwarded-Proto`.
- Apply sensible rate limiting consistent with existing config (reuse or adapt the existing `limit_req`/`limit_conn` zones; the `/count` endpoint receives one request per pageview, so keep limits looser than `/ip`).
- Also proxy two paths **on the main domain** (`yourdomain.com`) to goatcounter for first-party tracking:
  - `location = /count.js { proxy_pass http://127.0.0.1:8081/count.js; }` (or serve a vendored copy from `static/`, see 2.1)
  - `location = /count   { proxy_pass http://127.0.0.1:8081/count; }`
  This keeps all visitor-facing requests on the first-party domain.

### 1.6 bootstrap.sh
- Add `stats.yourdomain.com` to the cert domains.
- No new iptables rules needed (traffic enters via existing 443→8443).

---

## Phase 2 — Frontend integration

### 2.1 Tracking snippet
Add to every user-facing page (`static/index.html`, `static/getip.html`,
`static/cidr.html`, `static/impressum.html`, `static/datenschutz.html`):

```html
<script data-goatcounter="https://yourdomain.com/count"
        async src="/count.js"></script>
<noscript>
  <img src="https://yourdomain.com/count?p=/PAGE_PATH" alt="">
</noscript>
```
- Use the **first-party** `/count.js` and `/count` endpoints from 1.5.
- The `<noscript>` pixel must use the correct per-page path in `p=`.
- `alt=""` on the pixel (decorative) — required for WCAG.
- Alternative: vendor `count.js` into `static/` and serve it directly; if so, document the update procedure. Proxying is simpler to keep current — prefer proxying.

### 2.2 WCAG AAA constraints (must hold after changes)
- The tracking script must not introduce any visible UI, focus traps, or motion.
- The noscript pixel: `alt=""`, no layout shift (width/height 1, or CSS-hidden).
- No cookies, no localStorage — GoatCounter is cookieless by design; verify nothing else is added.
- Run an accessibility check (e.g. axe / pa11y if available) on the modified pages; zero new violations.

---

## Phase 3 — GDPR / German-law compliance

### 3.1 GoatCounter data-collection settings
In GoatCounter site settings (and document in README):
- Collection is already cookieless and uses a **non-identifiable rotating hash** for unique-visit counting — no consent banner is required for this.
- Review the "which data is collected" toggles; collect only what's needed: page path, referrer, browser/OS class, country-level location, screen size. Disable anything finer if offered.
- Set a **data retention period** in settings if available; otherwise document a manual/cron pruning approach. Recommendation: 12 months max for aggregate stats.

### 3.2 datenschutz.html updates (German)
Add a section covering the analytics processing. Must include:
- **What:** pageview counting via self-hosted GoatCounter on the operator's own server; no data leaves the server; no third parties.
- **Data processed:** requested page, referrer, approximate location (country, derived from IP), browser/device class, screen size; a short-lived non-reversible hash used to distinguish unique visits; **no cookies, no persistent identifiers, no cross-site tracking**.
- **Legal basis:** Art. 6 Abs. 1 lit. f DSGVO (berechtigtes Interesse: Reichweitenmessung und Betrieb der Website). Because no cookies or device storage are accessed, § 25 TDDDG consent is not triggered — state this reasoning.
- **Retention:** the configured retention period from 3.1.
- **Rights:** standard DSGVO rights section should already exist; ensure it references this processing too.
- Keep language consistent with the existing datenschutz.html style; German language.

### 3.3 Interaction with existing IP processing
- The site already processes visitor IPs for the core lookup function (legitimate interest, core functionality). Analytics is a **separate purpose** — it must have its own entry in the Datenschutzerklärung; do not merge the two justifications.
- Verify nginx access logs for the new `stats.` vhost and `/count` endpoints follow the same retention policy as existing logs (logrotate.conf — DSK guidance favors short retention, ~7 days, for security logs). Extend logrotate config if the new vhost logs to a new file.

### 3.4 Dashboard privacy
- The stats dashboard at `stats.yourdomain.com` must require login (GoatCounter default). Confirm public access to stats is disabled in site settings.

---

## Phase 4 — Docs, tests, housekeeping

### 4.1 README.md
- Add an "Analytics" section: what GoatCounter is, why chosen, SQLite volume, how to create the first site, how to access the dashboard, retention policy, and the first-party proxy design.
- Update the DNS table (1.1), project structure tree (new compose service), and common-commands section (`docker compose logs -f goatcounter`).

### 4.2 Tests
- Extend existing pytest/httpx tests minimally: assert that user-facing pages contain the tracking snippet (simple string/DOM check on static files).
- If there's a CI workflow in `.github/workflows`, ensure it still passes; no network calls to goatcounter in tests.

### 4.3 Backups
- Document that `goatcounter-data` named volume contains the SQLite DB and should be included in any backup routine (a simple `docker run --rm -v goatcounter-data:/data alpine tar ...` example is enough).

### 4.4 Upgrade path
- Document: bump image tag in compose, `docker compose pull && docker compose up -d`; `-automigrate` handles schema migrations.

---

## Acceptance criteria

1. `https://stats.yourdomain.com` serves the GoatCounter dashboard over TLS, login required, not reachable via plain internal port from outside.
2. Visiting any page on `yourdomain.com` registers a pageview; **all** requests (script + beacon) go to first-party domain only — verify with browser devtools that no request leaves `yourdomain.com`.
3. No cookies or storage are set by the site (verify in devtools → Application).
4. Pageviews register with JS disabled (noscript pixel).
5. datenschutz.html documents the analytics processing per 3.2; impressum unchanged.
6. Accessibility scan of modified pages shows zero new violations; pages still meet AAA contrast/keyboard requirements.
7. `docker compose down && up -d` preserves analytics data (named volume).
8. README updated; tests pass; lint (`ruff`) clean.

## Explicit non-goals
- No Umami/Plausible/Matomo. No cookie banner. No public stats page.
- No funnels, events, or campaign tracking in this iteration.
- No changes to the `/ip` endpoint, geolocation logic, or rate-limit values for `/ip`.
