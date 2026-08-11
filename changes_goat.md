# GoatCounter rollout — record of changes

Implementation of `GOATCOUNTER_PLAN.md`, 2026-08-11.

**Repo changes only — nothing was deployed.** No DNS records were created, no certbot
run was issued, no `docker compose up` was executed.

---

## What changed

| File | Change |
|---|---|
| `docker-compose.yml` | `goatcounter` service on `arp242/goatcounter:2.7.0`, `serve -automigrate -listen=:8081`, bound to `127.0.0.1:8081`, `goatcounter_data` named volume |
| `nginx.docker.conf` | `stats.` vhost (8080 ACME/redirect + 8443 proxy), `count` rate-limit zone (60r/m, burst 20), first-party `/count` + `/count.js` blocks on the main domain, `$analytics_optout` map for DNT/GPC, and a `location = /count` split out of the stats vhost so the guard applies there too |
| `bootstrap.sh` | `-d stats.$DOMAIN` added to the certbot invocation |
| `static/*.html` (7 pages) | Tracker snippet + `<noscript>` pixel carrying each page's own path |
| `static/datenschutz.html`, `static/privacy.html` | §5 rewritten from "no tracking" to a full analytics section, plus two opt-out mechanisms (DNT/GPC server-side, and a toggle button) |
| `tests/test_analytics.py` | New — snippet shape, per-page pixel path, no third-party host, policy coverage, opt-out control, DNT/GPC guard on every `/count` block |
| `README.md`, `CLAUDE.md` | Analytics section, DNS table, `--expand` procedure, data-collection toggles, opt-out, backups, upgrade path |

The snippet on every page:

```html
<script data-goatcounter="/count" async src="/count.js"></script>
<noscript><img src="/count?p=/cidr" alt="" aria-hidden="true" width="1" height="1" style="position:absolute"></noscript>
```

---

## Corrections to the plan

### GoatCounter picks the site by `Host` header

The plan specified `proxy_pass http://127.0.0.1:8081;` for `/count` on the main domain.
That would have forwarded `Host: alexander-hagemann.de`, which matches no site, and
pageviews would have silently vanished with no error anywhere. Both first-party blocks
now set `proxy_set_header Host stats.alexander-hagemann.de;` — the vhost the site is
created under.

### Spoofable real-IP headers

GoatCounter's real-IP middleware prefers `Cf-Connecting-Ip`, `Fly-Client-Ip`, and
`X-Azure-Socketip` *ahead of* `X-Real-IP`
([realip.go](https://github.com/arp242/zhttp/blob/master/mware/realip.go)). All three are
client-settable, so a visitor could forge their own country and poison the session key
described below. nginx now blanks them out. `X-Real-IP`/`X-Forwarded-For` are *set*, never appended.

### The "rotating hash" in the plan does not exist in GoatCounter 2.x

`GOATCOUNTER_PLAN.md` §3.1/§3.2 describes "a non-identifiable rotating hash" / "a
short-lived non-reversible hash used to distinguish unique visits". That was GoatCounter
1.x, which used a daily-rotating salted hash. In 2.7 the session key is the **literal
string** `User-Agent + "-" + IP + "-" + siteID`
([`memstore.go:374`](https://github.com/arp242/goatcounter/blob/release-2.7/memstore.go)) —
no hashing, trivially reversible, because it *is* the IP.

It is held in an in-memory map, evicted 8 hours after the last request
(`SessionTime = 8 * time.Hour`, cycled every minute), and `StoreSessions` writes the whole
map to the SQLite `store` table on shutdown, restoring it on startup — so full IPs and
User-Agents can briefly touch disk. Only the random session ID reaches the statistics
tables.

The first draft of both privacy policies repeated the plan's wording and was therefore
factually wrong. Both were rewritten to describe the real mechanism, including the 8-hour
window and the restart persistence.

### Region collection is on by default

`CollectLocationRegion` is in GoatCounter's default flag set
([`settings.go:358`](https://github.com/arp242/goatcounter/blob/release-2.7/settings.go)),
so a fresh site collects region, not just country — contradicting the policy text. It must
be switched off in Settings → Data collection. (With the built-in country database it
cannot resolve regions anyway, but the setting should still match the promise.)

`CollectLanguage` and `CollectHits` are *off* by default, which is why `Accept-Language`
and individual pageview records are absent from the policy's data list. Leave them off, or
the policy stops being accurate.

### "No localStorage" was not accurate

`count.js` **reads** `localStorage.skipgc` in its `filter()` before sending anything, and
writes it only on an explicit opt-out action. Rather than paper over it, both privacy
policies state this and rely on § 25 Abs. 2 Nr. 2 TDDDG (strictly necessary to honour an
objection), and §5 of each carries a working opt-out control.

### DNT / Global Privacy Control is honoured in nginx

Not in the plan. The `<noscript>` pixel counts exactly the visitors who cannot use a
`localStorage`-based opt-out, so the objection mechanism had a hole. `nginx.docker.conf`
now maps `DNT` / `Sec-GPC` to `$analytics_optout` and returns `204` from every
`location = /count` before the request reaches the rate limiter or GoatCounter. Being
request headers, this covers the beacon and the pixel alike, needs no client storage, and
works without JavaScript.

```nginx
# http context
map $http_dnt$http_sec_gpc $analytics_optout {
    default 0;
    "~1"    1;
}

# in every `location = /count`
if ($analytics_optout) {
    return 204;
}
```

`if` runs in the rewrite phase and `limit_req` in preaccess, so an opted-out request is
dropped before both the rate limiter and the upstream. `return` is one of the two
documented-safe uses of `if` inside a location.

Basis: Art. 21 Abs. 5 DSGVO (objection "mittels automatisierter Verfahren") and
[LG Berlin, 24.08.2023, 16 O 420/19](https://dejure.org/dienste/vernetzung/rechtsprechung?Gericht=LG+Berlin&Datum=24.08.2023&Aktenzeichen=16+O+420/19),
which held a DNT signal is a valid objection that may not be declared irrelevant.

**Accepted trade-off:** Brave sends `Sec-GPC: 1` by default and Firefox exposes a GPC
toggle, so pageview counts will under-represent privacy-conscious visitors, plausibly by
several percent. This was chosen deliberately over dropping the pixel. If the map is ever
removed, the corresponding claim must come out of both policies.

### The opt-out does not use count.js's own `#toggle-goatcounter` link

Upstream's mechanism evaluates `location.hash` once, at script-load time. Wiring a plain
`<a href="#toggle-goatcounter">` to it (the first draft did) has two defects:

1. After the first click the hash is already set, so clicking again fires no `hashchange`
   and nothing happens — the opt-out is one-way.
2. Worse, the hash stays in the URL, so **any ordinary refresh re-runs the toggle and
   silently re-enables tracking**, undoing the visitor's objection.

Both policies now use their own toggle button that writes `localStorage.skipgc` directly —
the same key `count.js` reads, so the contract is unchanged. No reload, no native
`alert()`, state announced through a `role="status"` region only on user action, and the
control stays hidden when the browser blocks site storage.

### Relative endpoints instead of absolute

The plan specified `data-goatcounter="https://yourdomain.com/count"`. Relative `/count`
and `/count.js` are used instead: it guarantees first-party regardless of host, and
removes a seventh place needing a domain substitution on redeploy.

### Scope the plan missed

- It listed 5 pages; the site has **7** (`up.html` and `privacy.html` were omitted).
- `privacy.html` and `datenschutz.html` both asserted *"no analysis or tracking services"*,
  which the change makes false. Both had to be rewritten, not just `datenschutz.html`.

### Smaller findings

- `2.7.0` is the actual latest tag (the plan guessed `2.7`); no images exist before `2.6`.
- `logrotate.conf` needs no change — `access_log off;` is at http level, so the new vhost
  creates no log file. Container logs are already covered by the docker json-file rotation.
- `certbot/conf/renewal-hooks/deploy/fix-permissions.sh` globs all lineages, so it still
  covers the expanded certificate. No change needed.
- `nginx.conf` (bare-metal, non-Docker) was left untouched — it is already stale and
  missing `/api/up`, so it is evidently not maintained.
- Location resolution uses the country-level database compiled into GoatCounter, not the
  GeoLite2 City volume used by `/ip`, so analytics never records finer than a country.

---

## Not verified

**The test suite was not run, and `nginx -t` was not run.** This machine has no `ruff`,
`pytest`, `node`, or `nginx` — only a bare `python3`. Stdlib-only consistency checks were
done instead and passed:

- all 7 pages carry the snippet, each pixel path matches the route the page is served on,
  and no page references `gc.zgo.at` or `goatcounter.com`;
- `$analytics_optout` is defined at http level (not nested inside a `server` block), all
  `location = /count` blocks consult it, and braces balance;
- both policies carry the opt-out button, the `skipgc` key, the DNT/GPC paragraph, and no
  leftover `href="#toggle-goatcounter"`.

Still to run:

```bash
ruff check .
python -m pytest
node --test
docker compose exec nginx nginx -t
```

After deploy, confirm the DNT/GPC guard actually fires — this is the one behaviour the
privacy policies promise that no offline check can prove:

```bash
curl -si -H 'DNT: 1'     'https://alexander-hagemann.de/count?p=/test' | head -1   # 204
curl -si -H 'Sec-GPC: 1' 'https://alexander-hagemann.de/count?p=/test' | head -1   # 204
curl -si                 'https://alexander-hagemann.de/count?p=/test' | head -1   # 200, image/gif
```

Only the third should appear in the dashboard.

---

## Manual steps remaining

1. **DNS** — add `A` and `AAAA` records for `stats.alexander-hagemann.de`.

2. **Expand the certificate** — do this *before* relying on the stats vhost, otherwise the
   browser gets a name mismatch:

   ```bash
   docker compose run --rm --entrypoint certbot certbot certonly \
     --webroot -w /var/www/certbot --expand \
     -d alexander-hagemann.de -d ip4.alexander-hagemann.de \
     -d ip6.alexander-hagemann.de -d stats.alexander-hagemann.de
   docker compose restart nginx
   ```

   Then re-apply the cert file permissions (README § "Certificate file permissions") — the
   deploy hook covers automatic renewals, not this manual run.

3. **Create the site** (prompts for a password):

   ```bash
   docker compose up -d
   docker compose exec goatcounter goatcounter db create site \
     -vhost=stats.alexander-hagemann.de -user.email=mail@alexander-hagemann.de
   ```

   `-smtp` defaults to `stdout`, so password-reset mails appear in
   `docker compose logs goatcounter` rather than being sent.

4. **Fix the data-collection toggles** in Settings → Data collection (full table in the
   README). Two are not optional, because the privacy policies already promise them:
   **turn Region off** (it is on by default), and **set data retention to 365 days**.
   Leave Language and Individual pageviews off.

5. Confirm under Settings → Site that the dashboard is **not** public.

6. **Verify the DNT/GPC guard** with the three `curl` calls above, and check that only the
   unsignalled one shows up in the dashboard.

---

## Acceptance criteria status

| # | Criterion | Status |
|---|---|---|
| 1 | `stats.` serves the dashboard over TLS, login required, internal port not public | Config in place; needs deploy to confirm |
| 2 | All tracking requests stay first-party | Enforced by relative endpoints; verify in devtools after deploy |
| 3 | No cookies or storage set | Holds — with the documented `skipgc` read caveat |
| 4 | Pageviews register with JS disabled | `<noscript>` pixel on all 7 pages; needs deploy to confirm. Deliberately **not** when the browser sends DNT/GPC — see the trade-off above |
| 5 | `datenschutz.html` documents the processing; impressum unchanged | Done (`privacy.html` too) |
| 6 | Accessibility scan shows zero new violations | Not run — no tooling on this machine |
| 7 | `down && up -d` preserves data | Named volume declared; needs deploy to confirm |
| 8 | README updated; tests pass; lint clean | README done; tests/lint **not run** |

Two things here go beyond the plan and are worth an explicit decision from the owner, since
both trade data completeness for a stronger objection mechanism:

- **DNT/GPC returns 204**, suppressing a real slice of traffic (Brave defaults to
  `Sec-GPC: 1`). Removing the map means removing the claim from both policies.
- **The opt-out button** replaces the plan's plain link, because the upstream
  `#toggle-goatcounter` mechanism re-enables tracking on refresh.
