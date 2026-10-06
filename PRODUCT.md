# Product

## Register

product

## Platform

web

## Users

Primarily the site owner, plus friends and colleagues the owner shares links with to check their own public IP. Usage is occasional and task-focused: someone opens the page (or hits the API endpoint from a script) to get an accurate answer and leave, not to browse or return regularly.

## Product Purpose

A self-hosted IP-lookup tool that detects a visitor's public IPv4 and IPv6 addresses independently, alongside geolocation data (country, region, city, ISP, coordinates, timezone). It exists as a privacy-respecting, ad-free alternative to commercial "what's my ip" sites. Success is a fast, accurate answer with no third-party trackers, ads, or filler content in the way.

## Positioning

It resolves IPv4 and IPv6 independently and shows both at once — dual-stack precision that generic "what's my ip" sites don't offer.

## Brand Personality

Calm, conventional and precise. The site should feel like a well-made native utility: light by default, follows the visitor's light/dark preference, uses their system font, and gets out of the way. Confidence comes from accuracy and restraint, not decoration.

## Anti-references

Ad-heavy "what's my ip" sites: banner ads, trackers, and SEO filler text wrapped around a simple lookup.

## Design Principles

- Quiet confidence: precision is the pitch; the design shouldn't need to work hard to look trustworthy.
- Familiar over clever: conventional layout, one blue accent, system fonts — nothing a first-time visitor has to learn.
- Function before flourish: every visual addition must earn its place against the core dual-stack lookup.
- No ads, no trackers, no filler: the thing this project explicitly refuses to be.
- Legible under formal scrutiny: accessibility is a hard constraint on every color and motion decision, not a follow-up pass.

## Accessibility & Inclusion

WCAG 2.1 AA is the formal target. Maintain and extend the existing baseline — skip links, `aria-live` regions on dynamic content, visible focus states, and `prefers-reduced-motion` handling — in both the light and dark theme, and compute contrast ratios for any new color pairing (see DESIGN.md §2).
