# Backlog

Open items from the site review of alexander-hagemann.de (2026-11-19). Nothing here is implemented yet.

## Infrastructure

- [ ] Switch SSL/TLS certificate issuance to Actalis, the owner's desired European provider. Certificates are currently issued by Let's Encrypt via certbot (per bootstrap.sh and README). Research prerequisites before migrating: confirm Actalis supports ACME (or another automatable issuance flow), check compatibility with the existing certbot setup and renewal automation, then plan the cutover. Recorded as an intention; no changes made.

## Fixes

- [ ] Add DNS for www.alexander-hagemann.de and redirect it to the canonical domain. Currently www. does not resolve.
- [ ] Replace raw JSON 404 responses (`{"detail":"Not Found"}`) with a styled 404 page that links back to the tools.
- [ ] Fix a stray "o" rendering on its own line under the Coordinates value on /getip (looks like an orphaned degree symbol).
- [ ] Cron page: the accessibility tree exposes the explanation sentence twice while it renders once; check for a duplicated element.

## SEO and sharing

- [ ] Give the homepage a descriptive `<title>` (currently just "alexander-hagemann.de"), e.g. "Network & Cron Tools | Alexander Hagemann".
- [ ] Add Open Graph tags (and a canonical link) so shared links get proper previews. A meta description already exists.

## Minor

- [ ] Dark mode toggle: the accessible name stays "Dark mode" in both states even though the icon flips; expose the current state.

## Under consideration (optional)

- [ ] Personal / About section. Owner is still deciding. If added: keep the tools front and center, add a short "About this project" (who built it, why, what was learned) rather than a full portfolio.
