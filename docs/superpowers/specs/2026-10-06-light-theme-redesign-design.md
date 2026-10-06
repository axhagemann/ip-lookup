# Light-theme redesign — design

Date: 2026-10-06
Status: approved in brainstorming, pending spec review

## Goal

Replace the "Quiet Terminal" look (pure black, grayscale, Courier everywhere,
`// ` headings, square corners) with a conventional, light-first design that
follows the visitor's OS light/dark preference and offers a per-page-view
toggle. WCAG 2.1 AA remains a hard constraint. No web fonts are downloaded.

## Decisions

| Topic | Decision |
|---|---|
| Direction | Full move away from the terminal aesthetic, not just a background swap |
| Theme | Light by default; dark when `prefers-color-scheme: dark`; plus a manual toggle |
| Toggle persistence | **None.** No `localStorage`, `sessionStorage`, or cookie. Override lasts for the current page view only; every page load starts from the OS theme |
| Fonts | System stacks only — no `@font-face`, no font files, no Google Fonts. Sans for UI, mono only for technical values |
| Color | Neutral grays + one blue accent; green/amber/red reserved for Is It Up? status |
| Shape | 6–8px radius, white cards on a light-gray page, at most one very subtle shadow (light theme only) |
| Architecture | Shared tokens + shared components in `static/style.css`; per-page `<style>` blocks keep only page layout and use tokens only |

## 1. Color tokens

Defined once in `static/style.css`. Ratios computed with the WCAG relative-luminance formula, against `--surface` / `--bg`.

| Token | Use | Light | Dark |
|---|---|---|---|
| `--bg` | page background | `#f6f7f9` | `#0f1115` |
| `--surface` | cards, inputs, secondary buttons | `#ffffff` | `#171a21` |
| `--text` | primary text | `#1a1d21` (16.9 / 15.8) | `#e6e8eb` (14.2 / 15.4) |
| `--text-muted` | descriptions, labels | `#57606a` (6.4 / 6.0) | `#9aa4b2` (6.9 / 7.5) |
| `--border` | card outlines, dividers — **decorative only** | `#d8dee4` | `#2a2f38` |
| `--border-strong` | input/button boundaries (≥3:1) | `#7d8590` (3.7 / 3.5) | `#6b7380` (3.6 / 4.0) |
| `--accent` | links, focus ring, primary button bg | `#1d4ed8` (6.7 / 6.3) | `#7aa7ff` (7.3 / 7.9) |
| `--on-accent` | text on primary button | `#ffffff` (6.7) | `#0f1115` (7.9) |
| `--ok` | status "up" | `#1a7f37` (5.1 / 4.7) | `#3fb950` (6.9 / 7.4) |
| `--warn` | status "blocked"/warning | `#9a6700` (4.9 / 4.5) | `#d29922` (6.9 / 7.5) |
| `--err` | status "down", errors | `#cf222e` (5.4 / 5.0) | `#ff6b61` (6.2 / 6.8) |

Usage rules that the palette alone does not guarantee:

1. **Inline links in running text are underlined.** Accent vs body text is only 2.5:1 (light) / 1.9:1 (dark), below the 3:1 needed for color-only link identification (WCAG 1.4.1). Nav, top-bar, and footer links may omit the underline (identified by position).
2. **`--border` never alone defines an input's or control's boundary** (≈1.3:1). Inputs and secondary buttons use `--border-strong`.
3. **Status is never conveyed by color alone** — the status text ("Up", "Down", "Blocked", stage name) always appears.
4. Light `--warn` text sits on `--surface` only (4.87:1), not directly on `--bg` (4.54:1, too close to the limit).
5. No hex values outside the token definitions in `style.css`.

## 2. Typography

```css
--font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
--font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
```

Mono is used only for technical values: IP addresses, CIDR start/end, URLs in Is It Up? results, `<code>`, and the IP/URL input fields.

| Role | Spec |
|---|---|
| h1 | 1.75rem / 650, sentence case |
| h2 | 1.125rem / 600 |
| Body | 1rem / 400, line-height 1.6, max ~65ch |
| Label / meta | 0.875rem / 500, `--text-muted` |
| Value | 1.5rem / 600, mono, `font-variant-numeric: tabular-nums`, `overflow-wrap: anywhere` |
| Small | 0.8125rem (footer, hints) |

All sizes in `rem`. No fixed-height text containers (1.4.4 Resize Text, 1.4.12 Text Spacing). Long IPv6 values wrap at 320px width (1.4.10 Reflow).

Removed: the `// ` heading prefix, uppercase letter-spaced labels, per-page `← ` back links, and the blinking `_` loading cursor.

## 3. Shared components (`static/style.css`)

- **Top bar** (every page): site name "alexander-hagemann.de" linking to `/` on the left, theme toggle on the right. Replaces all per-page back links (today inconsistent: top "← Home" on cidr/getip, bottom "← Back" with spoken arrow on up).
- **Layout**: centered column, `max-width: 720px` for tools, `65ch` for legal text, 16px side padding on narrow screens.
- **Footer**: normal document flow (no `position: fixed` — it can overlap content at small widths / 200% zoom). Legal links (Impressum, Datenschutz, Privacy, keeping their `lang` attributes); MaxMind notice on the IP page.
- **Card** (`.card`): `--surface` bg, 1px `--border`, `border-radius: 8px`, padding 1.5rem; light theme `box-shadow: 0 1px 2px rgb(0 0 0 / .05)`, dark theme no shadow.
- **Tool tile** (index): card as link; title `--text` 600, description muted; hover → border `--accent` + title underline; no transform/lift.
- **Primary button**: `--accent` bg, `--on-accent` text, 6px radius, min 44×44px.
- **Secondary button** (Copy IP): `--surface` bg, 1px `--border-strong`, `--text`. "Copied" = ✓ + text in `--ok`; "Copy failed" = text in `--err`; both announced via the existing live region.
- **Input**: `--surface` bg, 1px `--border-strong`, 6px radius; every input has a visible `<label>`. Errors in `--err` below the field with `role="alert"`.
- **Result list** (`dl`): label (muted) / value (mono) in two columns on wide screens, stacked on narrow.
- **Status badge** (Is It Up?): pill with dot + text, text in status color on a light tint of it; tint must keep the text ≥4.5:1 (verify when implementing).
- **Focus**: `:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }` everywhere.
- **Skip link**: unchanged behavior, restyled.
- **Loading**: muted "Loading…" with a gentle opacity pulse; static under `prefers-reduced-motion: reduce`.
- **`.visually-hidden`** utility class for screen-reader-only text.

## 4. Theme toggle

CSS (in `style.css`):

```css
:root { color-scheme: light; /* light tokens */ }
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) { color-scheme: dark; /* dark tokens */ }
}
:root[data-theme="dark"] { color-scheme: dark; /* dark tokens */ }
```

Each page `<head>`: `<meta name="color-scheme" content="light dark">`.

Markup (static, in the top bar of every page):

```html
<button type="button" class="theme-toggle" aria-pressed="false" title="Toggle dark mode" hidden>
  <svg aria-hidden="true" focusable="false">…</svg>
  <span class="visually-hidden">Dark mode</span>
</button>
```

`static/theme.js` (loaded with `<script defer src="/theme.js">`):

- Unhides the button (no-JS visitors never see a dead control; they still get the OS theme via CSS).
- Effective theme = `data-theme` on `<html>` if set, else `matchMedia("(prefers-color-scheme: dark)")`.
- Click → set `data-theme` to the opposite of the effective theme; update `aria-pressed` (`true` when dark).
- `matchMedia` change listener updates `aria-pressed` while no `data-theme` is set.
- **No storage of any kind.** Each page load starts from the OS preference. No FOUC handling needed, since the first paint is always correct from CSS.
- No color transition on theme switch.
- Fixed accessible name "Dark mode" + `aria-pressed`; icon swaps sun/moon visually only. Min 44×44px.

No privacy-page changes are needed (nothing is stored).

## 5. Scope of changes

New:
- `static/theme.js`

Rewritten:
- `static/style.css` — tokens, fonts, type scale, components, theme rules.

Every page — `index.html`, `getip.html`, `cidr.html`, `up.html`, `impressum.html`, `datenschutz.html`, `privacy.html`:
- Add color-scheme meta, top bar with toggle, deferred `theme.js`.
- Remove `// ` prefixes, uppercase-label styling, per-page back links.
- Reduce the page `<style>` block to page-specific layout using tokens only (no hex).
- Preserve: skip link, `aria-live` regions, `role="alert"` errors, GoatCounter snippet and `<noscript>` pixel exactly, `lang` attributes on legal links, all existing JS behavior.

Page-specific:
- `up.html`: add a visible `<label>` for the URL input; status badge uses `--ok`/`--warn`/`--err`.
- `getip.html`: Copy button states per §3; pulse loading replaces blinking cursor.

Not touched: `static/cidr-logic.js`, `main.py`, nginx configs, Docker files.

Docs:
- `DESIGN.md` — rewritten for the new system.
- `PRODUCT.md` — Brand Personality and principles updated (drop the terminal/retro-accent plan).
- `CLAUDE.md` — replace "Design constraints": tokens only, no web fonts, no persisted theme, light/dark via `prefers-color-scheme` + per-view toggle, AA rules above.

## 6. Testing

Automated (new `tests/test_theme.py`, TestClient-based like the rest):
- Every page route returns HTML that includes `theme.js`, the `color-scheme` meta, and a `.theme-toggle` button with `aria-pressed`.
- No page or `style.css` contains `@font-face`, `fonts.googleapis`, or `fonts.gstatic`.
- No hex color literal inside any page's `<style>` block (tokens only).
- `theme.js` contains no `localStorage`, `sessionStorage`, or `document.cookie`.

Must stay green: `python -m pytest`, `node --test`, `ruff check .`.

Manual:
- Each page in light, dark (OS), and toggled states.
- 320px width and 200% zoom: no horizontal scroll, no overlap.
- Keyboard-only pass: skip link, focus ring visible in both themes, toggle operable.
- Final review with the `ux-accessibility-reviewer` agent.

## Out of scope

- Persisting the theme choice across pages or visits.
- Any new tool, backend, or analytics change.
- Self-hosted or third-party web fonts.
