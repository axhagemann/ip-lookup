# "Is It Up?" — Input Sanitization and SSRF Hardening

**Date:** 2026-09-13
**Status:** Approved design, awaiting spec review
**Scope:** `upcheck.py`, `static/up.html`, tests

## Problem

`/api/up` makes the server fetch a URL chosen by the visitor. Today's protection
(`_normalize_url` + `_guard_ssrf`) checks only the URL as typed:

1. **Redirect bypass.** httpx follows up to 5 redirects to any host. A public site
   redirecting to `http://127.0.0.1:8081` makes the server request GoatCounter.
2. **Any port.** `example.com:22` works, turning the tool into a port scanner.
3. **Credentials** in URLs (`https://user:pass@host`) are accepted and forwarded.
4. **DNS rebinding.** httpx resolves the host again after the guard approved it.
5. **Two parsers.** The guard uses `urlsplit`, httpx uses its own parser. A probe
   found no host mismatch, but they disagree on spaces, tabs and invalid ports.

## Decisions

| Topic | Decision |
|---|---|
| Scope | Full hardening: input rules, every redirect hop re-checked, connection pinned to the checked IP |
| Allowed ports | 80, 443, 8080, 8443 |
| Rejection feedback | Specific reason shown to the visitor |
| Approach | Manual redirect loop with pinned connections, all inside `upcheck.py`, no new dependencies |
| Credentials in URL | Rejected, not stripped |
| IDN hostnames | Accepted, converted to ASCII (punycode) |
| Non-canonical numeric hosts (`2130706433`, `0x7f.1`, `127.1`) | Rejected |
| Client-side validation | `maxlength="2048"` only; the server is the only gatekeeper |

## 1. Input rules — `_parse_target(raw) -> httpx.URL | Rejection`

Replaces `_normalize_url`. Parses **once, with `httpx.URL`**, so the validated host is
the host that gets contacted. Rules run in order; the first failure returns its message.

| # | Rule | Rejected example | Message |
|---|---|---|---|
| 1 | Strip surrounding whitespace; non-empty; ≤ 2048 characters | `""`, 3000 chars | "Enter a URL to check" / "URL is too long" |
| 2 | No whitespace or ASCII control characters inside (checked before parsing) | `exa mple.com`, `example.com\t/` | "URL contains spaces or control characters" |
| 3 | Prepend `https://` if the input has no `://`; must parse with `httpx.URL` (includes invalid IDNA) | `https://[zz]/` | "Not a valid URL" |
| 4 | Scheme is `http` or `https` | `ftp://…`, `file:///…` | "Only http and https URLs can be checked" |
| 5 | No userinfo (non-empty `url.userinfo`) | `https://user:pass@host` | "URLs with a username or password aren't accepted" |
| 6 | Host is a standard IP address accepted by `ipaddress.ip_address` **or** a DNS name: ASCII form, one trailing dot allowed and ignored, labels 1–63 chars of `[a-z0-9-]` not starting or ending with `-`, total ≤ 253 chars, at least two labels, last label not purely numeric | `localhost`, `intranet`, `2130706433`, `0x7f.1`, `127.1` | "Not a public hostname or IP address" |
| 7 | Port is unset or in {80, 443, 8080, 8443}. httpx drops default ports, so `https://host:443` has no explicit port | `:22`, `:0`, `:99999` | "Port 22 isn't allowed — only 80, 443, 8080 and 8443" |
| 8 | Drop the fragment; keep path and query | — | — |

Rule 6 only stops unusual host forms from reaching DNS. Anything it accepts still has to
pass section 2.

Redirect targets go through the same function after `current_url.join(location)`.

## 2. Resolve, check, pin

### `_resolve_public(url) -> list[str] | Rejection`

- IP-address hosts skip DNS and are checked as given.
- DNS names resolve via `socket.getaddrinfo` in the default executor, wrapped in a
  **5-second** `asyncio.wait_for`. No result or timeout → DNS failure.
- **Every** resolved address must satisfy `is_global`. For IPv6 addresses that embed an
  IPv4 address — IPv4-mapped (`::ffff:0:0/96`), 6to4 (`2002::/16`), NAT64
  (`64:ff9b::/96`) — the embedded IPv4 address must also be global.
- Returns addresses deduplicated, **IPv4 first**, then IPv6, each group in resolver order.

### Pinned request, per hop

- Connect to the **first** returned address. Other addresses are not tried; a failed
  connect reports "Server unreachable". (Accepted trade-off: slightly less forgiving than
  today for hosts with a dead first A record.)
- Request URL = original URL with the host replaced by that address (IPv6 in brackets),
  same scheme, port, path and query.
- `Host` header = original ASCII host, plus `:port` when a non-default port is set.
- HTTPS to a DNS name: `extensions={"sni_hostname": ascii_host}`. Certificate
  verification stays enabled and is checked against that name. IP-address hosts send no
  SNI extension.
- `follow_redirects=False`. The existing HEAD → GET fallback (on 403/405/501 or any
  `httpx.HTTPError` from HEAD) applies to each hop.
- A response is a redirect when its status is 301, 302, 303, 307 or 308 **and** it has a
  `Location` header. A 3xx without `Location` is treated as the final response.
- The app container has no IPv6 (`enable_ipv6: false`), so IPv6-only targets fail to
  connect exactly as they do today.

### Limits

- At most 5 redirects. A sixth → "More than 5 redirects".
- **12-second** total budget for all DNS lookups and requests (`asyncio.timeout`). nginx
  gives up on `/api/up` after 15 s, so the tool must answer first.
- Per-operation httpx timeout `_TIMEOUT` (10 s) stays.

### Reviewed, no extra rule needed

The server's own public IP passes the check; on the allowed ports it only reaches nginx's
public vhosts. GoatCounter (`127.0.0.1:8081`) and the app (`127.0.0.1:8000`) are not
reachable that way. Self-referencing loops through `/api/up` are bounded by the nginx
`upcheck` rate limit.

## 3. Response and page

### API response

Fields stay: `status`, `stage`, `detail`, `http_status`, `response_time_ms`,
`final_url`, `redirects`, `resolved_ips`, `ip_geo`.

| Situation | `status` | `stage` | `detail` |
|---|---|---|---|
| Section 1 rule fails on the entered URL | `invalid` | `input` | Rule message |
| Entered host has a non-public address | `invalid` | `input` | "Target resolves to a non-public address" |
| Entered host does not resolve | `down` | `dns` | "Domain does not resolve" (unchanged) |
| Redirect target fails a section 1 rule or has a non-public address | **`blocked`** (new) | **`redirect`** (new) | "Redirected to a URL that can't be checked: " + lower-cased rule message, or "Redirected to a non-public address" |
| Redirect target does not resolve | `down` | `dns` | "Redirect target does not resolve" |
| More than 5 redirects | `degraded` | `http` | "More than 5 redirects" |
| 12-second budget exceeded | `down` | `http` | "Check took too long" |
| Connect errors, read timeouts, normal results | unchanged | unchanged | unchanged |

Rules:

- `redirects` = every URL that answered with a redirect, in order — the same meaning as
  today's `response.history`. On `blocked` it therefore ends with the hop whose
  `Location` was rejected; the rejected target itself is not included.
- `final_url` = URL of the final response; omitted on `blocked`.
- URLs in `final_url` and `redirects` are always the hostname form, never the pinned IP form.
- `resolved_ips` / `ip_geo` describe the **entered** host, as today, and are omitted
  when the entered URL is rejected in section 1 or 2.
- `response_time_ms` = total across all hops.
- **No new logging.** Neither the raw input nor any rejection detail is logged, keeping
  the privacy policy's statement that checked URLs are not stored.

### `static/up.html`

- Input gets `maxlength="2048"`.
- `STATUS_LABELS` gains `blocked: "Can't be checked"`; `STAGE_LABELS` gains
  `redirect: "Redirect"`.
- `.status-blocked` uses the same grey as `.status-invalid` (`#c0c0c0`); no new colour.
- Server-provided strings are rendered only via `textContent` (already true; now a
  stated requirement).

## 4. Testing

Test seam: `_http_check` accepts an optional `transport` argument (default: real
network) so tests can pass `httpx.MockTransport`. Tests are written before the
implementation.

### `tests/test_upcheck.py` (no network)

- `_parse_target`, parametrized per rule, asserting exact messages. Accepted:
  `example.com` → `https://example.com`; explicit `http://` kept; `bücher.de` →
  `xn--bcher-kva.de`; `[2001:db8::1]:8443`; `example.com:8080`; `example.com.`.
- `_resolve_public` with a fake `socket.getaddrinfo`: public + private mix → blocked;
  `::ffff:127.0.0.1`, `2002:7f00:1::`, `64:ff9b::7f00:1` → blocked; mixed families →
  IPv4 first; resolver hanging past the timeout → DNS failure.
- Redirect loop with `MockTransport` + fake resolver:
  - pinned request targets the checked IP, `Host` is the original name, `sni_hostname`
    set for HTTPS names and absent for IP-address hosts;
  - redirect to `http://127.0.0.1:8081` → `blocked`/`redirect`, and the transport
    receives **no** request for it;
  - relative `Location` resolved and followed; `final_url`/`redirects` contain hostnames;
  - 6 redirects → `degraded`, "More than 5 redirects";
  - rebinding: resolver returns a public IP first and `127.0.0.1` afterwards → one
    resolution per hop, connection goes to the public IP;
  - budget exceeded (shortened in test, slow handler) → "Check took too long".
- `static/up.html` contains `maxlength="2048"` and a `blocked` status label.

### `tests/test_routes.py`

- `/api/up?url=example.com:22` and `/api/up?url=user:pass@example.com` return
  `invalid`/`input` with their messages, without DNS.

### `tests/test_privacy.py`

- A rejected URL containing a unique marker produces no log record containing the marker
  (`caplog`).

### Manual smoke checks after deploy (optional, use third-party services)

- `127.0.0.1.nip.io` → `invalid`/`input`, "Target resolves to a non-public address".
- `httpbin.org/redirect-to?url=http://127.0.0.1:8081` → `blocked`/`redirect`.

## Out of scope

- Network-level egress filtering for the app container.
- Enabling IPv6 in the app container.
- nginx changes (the `upcheck` rate limit already covers every route to `/api/up`).
