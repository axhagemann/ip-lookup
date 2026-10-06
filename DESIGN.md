---
name: alexander-hagemann.de tools
description: Self-hosted, ad-free network tools with a light-first, system-native look
colors:
  light:
    bg: "#f6f7f9"
    surface: "#ffffff"
    text: "#1a1d21"
    text-muted: "#57606a"
    border: "#d8dee4"
    border-strong: "#7d8590"
    accent: "#1d4ed8"
    accent-hover: "#1e40af"
    on-accent: "#ffffff"
    ok: "#116329"
    ok-bg: "#dafbe1"
    warn: "#7d4e00"
    warn-bg: "#fff8c5"
    err: "#a40e26"
    err-bg: "#ffebe9"
    neutral-bg: "#eff2f5"
  dark:
    bg: "#0f1115"
    surface: "#171a21"
    text: "#e6e8eb"
    text-muted: "#9aa4b2"
    border: "#2a2f38"
    border-strong: "#6b7380"
    accent: "#7aa7ff"
    accent-hover: "#a5c3ff"
    on-accent: "#0f1115"
    ok: "#3fb950"
    ok-bg: "#12261a"
    warn: "#d29922"
    warn-bg: "#2b2111"
    err: "#ff6b61"
    err-bg: "#2d1416"
    neutral-bg: "#222731"
typography:
  sans: 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
  mono: 'ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace'
rounded:
  sm: "6px"
  md: "8px"
---

# Design System

## 1. Overview

A calm, conventional utility look: light gray page, white cards, one blue accent, the visitor's own system font. It follows the OS light/dark setting, and a toggle in the top bar flips the current page view. The site still refuses everything the ad-heavy "what's my ip" sites do — no banners, no trackers, no filler.

## 2. Color

All colors are CSS custom properties in `static/style.css`. Hex values appear only on those token lines; page `<style>` blocks use `var(--…)` only (enforced by `tests/test_theme.py`).

Theme wiring: light tokens on `:root`; dark tokens under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` and again under `:root[data-theme="dark"]`. `static/theme.js` sets `data-theme` on click.

Contrast (WCAG 2.1 AA, computed with the WCAG relative-luminance formula):

| Pair | Light | Dark |
|---|---|---|
| text on surface / bg | 16.9 / 15.8 | 14.2 / 15.4 |
| text-muted on surface / bg | 6.4 / 6.0 | 6.9 / 7.5 |
| accent on surface / bg | 6.7 / 6.3 | 7.3 / 7.9 |
| on-accent on accent / accent-hover | 6.7 / 8.7 | 7.9 / 10.7 |
| ok / warn / err on their tint | 6.6 / 6.6 / 6.9 | 6.3 / 6.3 / 6.2 |
| border-strong on surface / bg / neutral-bg | 3.7 / 3.5 / 3.3 | 3.6 / 4.0 / 3.1 |

Rules:
- **Inline links are underlined.** Accent vs body text is only 2.5:1 (light) / 1.9:1 (dark), so color alone can't identify a link (1.4.1). Top-bar and footer links may drop the underline; their position identifies them.
- **`--border` is decorative** (~1.3:1). Inputs and secondary buttons use `--border-strong`.
- **Status is never color-only.** The pill always carries text ("Up", "Down", …).
- Any new token pairing gets its ratio computed and added to the table above.

## 3. Typography

System fonts only — no `@font-face`, no font files, no Google Fonts. Sans for all UI; mono only for technical values (IP addresses, CIDR results, URLs, `<code>`, IP/URL inputs).

| Role | Spec |
|---|---|
| h1 | 1.75rem / 650, sentence case |
| h2 | 1.125rem / 600 |
| Body | 1rem / 400, line-height 1.6, max ~65ch |
| Label / meta | 0.875rem / 500, muted |
| Value | 1.5rem / 600 mono, tabular numbers, wraps anywhere |
| Small | 0.8125rem (footer, notes) |

All sizes in `rem`; no fixed-height text boxes; long IPv6 values wrap at 320px.

## 4. Shape and depth

Cards: 8px radius, 1px `--border`, `--surface` background on the `--bg` page, `0 1px 2px rgb(0 0 0 / .05)` shadow in light and none in dark (the lighter surface carries depth). Controls: 6px radius. No gradients, no hover lift.

## 5. Components

All in `static/style.css`:

- **Top bar** (`.topbar`): site name linking home, theme toggle. Every page has it; there are no per-page back links.
- **Theme toggle** (`.theme-toggle`): `aria-pressed` + fixed visually-hidden name ("Dark mode" / "Dunkelmodus"), moon/sun SVG icons, 44×44px, `hidden` until `theme.js` runs. Override lasts for the current page view; nothing is stored.
- **Card** (`.card`, `.card-header`), **tool tile** (`.card.tool-link`).
- **Buttons**: `.btn.btn-primary` (accent fill), `.btn.btn-secondary` (surface + strong border). Min height 44px.
- **Inputs**: always with a visible `<label>`; `input.mono` for addresses and URLs.
- **Error** (`.error`): err text on err tint, announced via `role="alert"`.
- **Result list** (`.result-list`): label/value two-column `dl`, stacking below 480px.
- **Status pill** (`.status .status-up|degraded|down|invalid|blocked`).
- **Loading** (`.loading`): visible "Loading…" text at full contrast plus a pulsing decorative dot; static under `prefers-reduced-motion`.
- **Footer** (`.site-footer`): legal links, normal flow (never fixed).
- **Legal prose** (`main.prose`): 65ch column, sections inside one card.

## 6. Do's and don'ts

Do:
- Use tokens for every color; add new tokens to all three theme blocks.
- Keep the skip link, `aria-live` regions, focus ring and reduced-motion fallbacks on every page.
- Add the top bar, footer, color-scheme meta and deferred `theme.js` to any new page (`tests/test_theme.py` checks it).

Don't:
- Load web fonts or any third-party asset.
- Persist the theme choice (no `localStorage`, cookies, etc.).
- Animate text opacity, add hover lifts, gradients, or more accent colors.
- Use color as the only signal for links or status.
