# Light-Theme Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the black "Quiet Terminal" look with a light-first, system-font design that follows the OS light/dark setting and offers a non-persisted per-page-view toggle, WCAG 2.1 AA throughout.

**Architecture:** All colors live as CSS custom properties in `static/style.css` (one light block, the dark block repeated under `prefers-color-scheme` and `[data-theme="dark"]`), together with every shared component (top bar, card, buttons, inputs, result list, status pill, footer, legal prose). Each page's `<style>` block shrinks to page-only layout that references tokens only. A tiny deferred `static/theme.js` flips `data-theme` on `<html>` on click; nothing is stored.

**Tech Stack:** Hand-written HTML/CSS/vanilla JS served by FastAPI `StaticFiles`; pytest + FastAPI TestClient; ruff.

**Spec:** `docs/superpowers/specs/2026-10-06-light-theme-redesign-design.md`

## Global Constraints

- No web fonts: no `@font-face`, no `fonts.googleapis`/`fonts.gstatic`, no `.woff`/`.woff2` files. Only these stacks:
  - `--font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;`
  - `--font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;`
- No storage of the theme: `static/theme.js` must not use `localStorage`, `sessionStorage`, `document.cookie`, or `indexedDB`. (The existing GoatCounter opt-out script on the privacy pages keeps using `localStorage["skipgc"]` — that is unrelated and stays.)
- Hex color literals appear only on `--token:` lines in `static/style.css`. Page `<style>` blocks contain no hex.
- No `Courier` anywhere; no `<span aria-hidden="true">// </span>` heading prefixes; no `class="back"` links.
- Preserve on every page: skip link, all `aria-live` / `role="alert"` / `role="status"` regions, the GoatCounter `<script data-goatcounter="/count" async src="/count.js"></script>` line and `<noscript>` pixel byte-for-byte, `lang` attributes on legal links. `tests/test_analytics.py` must keep passing.
- Do not touch `static/cidr-logic.js`, `main.py`, `upcheck.py`, `geo.py`, nginx configs, Docker files.
- Light status colors are the deeper set `--ok: #116329`, `--warn: #7d4e00`, `--err: #a40e26` (stricter than the spec's first draft — the spec's lighter set only reached 4.52–4.67:1 on the status tints; these reach ≥6.58:1 everywhere they are used).
- Tooling: activate the venv first (`source .venv/bin/activate`). Never install tools ad hoc. `node` is **not installed** on this machine — `node --test` cannot be run here; say so in the final report rather than installing it. `static/cidr-logic.js` is untouched, so its tests are unaffected.
- This work must not be deployed mid-plan: after Task 1 the not-yet-migrated pages are unreadable (light background, light-gray inline text) until their own task lands.

## Review Focus

1. **Theme toggle when the OS theme changes while the page is open** — with no click, `aria-pressed` must follow the OS; after a click the forced theme must stick for the rest of the page view. Covered by manual check in Task 6 (no JS runtime available for automated tests).
2. **Long IPv6 values at 320px width / 200% zoom** (getip hero value, cidr start/end, up resolved IPs) — must wrap, never cause horizontal scroll. `overflow-wrap: anywhere` on `.value` and `.result-list dd`; manual check in Task 6.
3. **`hidden` toggle button overridden by CSS `display`** — `.theme-toggle` sets `display: inline-flex`, which would beat the `hidden` attribute and show a dead button to no-JS users. Pinned by `.theme-toggle[hidden] { display: none; }` and a stylesheet test in Task 1.
4. **No-JS visitors** — must get the OS theme via CSS alone and never see the toggle. Pinned by the `hidden` attribute test in every page test (Tasks 2–5) plus Task 6 manual check with JS disabled.
5. **Loading indicator accessibility** — the animated part must not reduce text contrast (animate a decorative dot, never the text's opacity) and must stop under `prefers-reduced-motion`. Pinned by stylesheet test in Task 1.

---

## File Map

| File | Responsibility | Task |
|---|---|---|
| `tests/test_theme.py` (create) | Shape guards for tokens, fonts, toggle markup, no-storage | 1, extended 2–6 |
| `static/style.css` (rewrite) | Tokens + all shared components | 1 |
| `static/theme.js` (create) | Toggle behavior | 1 |
| `static/index.html` | Home tiles | 2 |
| `static/impressum.html`, `datenschutz.html`, `privacy.html` | Legal pages | 2 |
| `static/getip.html` | IP lookup | 3 |
| `static/cidr.html` | CIDR calculator | 4 |
| `static/up.html` | Is It Up? | 5 |
| `DESIGN.md`, `PRODUCT.md`, `CLAUDE.md` | Docs | 6 |

## Shared markup snippets (used verbatim by Tasks 2–5)

**HEAD** — replaces the existing `<link rel="stylesheet" href="/style.css" />` line (and the page's old `<style>` block where a task says so):

```html
  <meta name="color-scheme" content="light dark" />
  <link rel="stylesheet" href="/style.css" />
  <script defer src="/theme.js"></script>
```

**TOPBAR_EN** — directly after the skip link:

```html
  <header class="topbar">
    <a class="site-name" href="/">alexander-hagemann.de</a>
    <button type="button" class="theme-toggle" aria-pressed="false" title="Toggle dark mode" hidden>
      <svg class="icon-moon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg class="icon-sun" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
      <span class="visually-hidden">Dark mode</span>
    </button>
  </header>
```

**TOPBAR_DE** — identical except `title="Dunkelmodus umschalten"` and `<span class="visually-hidden">Dunkelmodus</span>`.

**FOOTER_EN**:

```html
  <footer class="site-footer">
    <nav class="footer-links" aria-label="Legal">
      <a href="/impressum.html" lang="de">Impressum</a>
      <a href="/datenschutz.html" lang="de">Datenschutz</a>
      <a href="/privacy.html" lang="en">Privacy</a>
    </nav>
  </footer>
```

**FOOTER_DE** — identical except `aria-label="Rechtliches"`.

---

### Task 1: Design tokens, shared components, theme toggle script

**Files:**
- Create: `tests/test_theme.py`
- Rewrite: `static/style.css`
- Create: `static/theme.js`

**Interfaces:**
- Produces (CSS classes later tasks use): `.topbar`, `.site-name`, `.theme-toggle`, `.icon-moon`, `.icon-sun`, `.visually-hidden`, `.skip-link`, `.description`, `.note`, `.card`, `.card-header`, `.tool-link`, `.btn`, `.btn-primary`, `.btn-secondary`, `input.mono`, `.mono`, `.error`, `.result-list`, `.value`, `.loading`, `.status`, `.status-up|degraded|down|invalid|blocked`, `.site-footer`, `.footer-links`, `main.prose`, `#optout-state`.
- Produces (tokens): `--bg --surface --text --text-muted --border --border-strong --accent --accent-hover --on-accent --ok --ok-bg --warn --warn-bg --err --err-bg --neutral-bg --shadow` (themed), `--font-sans --font-mono --radius --radius-sm` (theme-independent).
- Produces (test module): `tests/test_theme.py` with module-level `THEMED: list[str]` that Tasks 2–5 append to, and helper `page_html(name) -> str`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_theme.py`:

```python
"""Guards for the light/dark design system.

See docs/superpowers/specs/2026-10-06-light-theme-redesign-design.md. Like
test_analytics.py these check shape, not exact markup: every page wires up the
shared theme, no page brings its own colors or fonts, and the toggle never
stores anything.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"
CSS = (STATIC / "style.css").read_text(encoding="utf-8")

# Pages already moved to the new design system. Grows task by task until it
# is every page on disk (see test_every_page_is_themed, added last).
THEMED: list[str] = []

THEMED_TOKENS = (
    "--bg", "--surface", "--text", "--text-muted", "--border", "--border-strong",
    "--accent", "--accent-hover", "--on-accent", "--ok", "--ok-bg", "--warn",
    "--warn-bg", "--err", "--err-bg", "--neutral-bg", "--shadow",
)

HEX = re.compile(r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")
STYLE_BLOCK = re.compile(r"<style>(.*?)</style>", re.S)
FONT_DOWNLOADS = ("@font-face", "fonts.googleapis", "fonts.gstatic", ".woff")


def page_html(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


# ── Stylesheet ──────────────────────────────────────────────────


def test_stylesheet_defines_light_system_dark_and_forced_dark():
    assert ":root {" in CSS
    assert "@media (prefers-color-scheme: dark)" in CSS
    assert ':root:not([data-theme="light"])' in CSS
    assert ':root[data-theme="dark"]' in CSS


@pytest.mark.parametrize("token", THEMED_TOKENS)
def test_every_themed_token_is_set_in_all_three_blocks(token):
    assert len(re.findall(rf"^\s*{re.escape(token)}:", CSS, re.M)) == 3


def test_stylesheet_hex_only_on_token_lines():
    for line in CSS.splitlines():
        if HEX.search(line):
            assert line.strip().startswith("--"), line


def test_stylesheet_uses_system_fonts_only():
    assert "system-ui" in CSS
    assert "ui-monospace" in CSS
    assert "Courier" not in CSS
    for marker in FONT_DOWNLOADS:
        assert marker not in CSS


def test_hidden_toggle_stays_hidden():
    # .theme-toggle sets display, which would otherwise beat the hidden attribute.
    assert ".theme-toggle[hidden] { display: none; }" in CSS


def test_loading_animation_respects_reduced_motion_and_spares_text():
    assert ".loading::after" in CSS
    reduced = CSS.split("@media (prefers-reduced-motion: reduce)")[1].split("}")[0]
    assert ".loading::after" in reduced
    # The pulse animates a decorative dot; the text itself must keep full contrast.
    loading_rule = CSS.split(".loading {")[1].split("}")[0]
    assert "animation" not in loading_rule
    assert "opacity" not in loading_rule


# ── Toggle script ───────────────────────────────────────────────


def test_theme_js_stores_nothing():
    js = (STATIC / "theme.js").read_text(encoding="utf-8")
    for api in ("localStorage", "sessionStorage", "document.cookie", "indexedDB"):
        assert api not in js


def test_theme_js_drives_data_theme_and_aria_pressed():
    js = (STATIC / "theme.js").read_text(encoding="utf-8")
    assert "prefers-color-scheme: dark" in js
    assert "data-theme" in js
    assert "aria-pressed" in js


# ── Every page, migrated or not ─────────────────────────────────


@pytest.mark.parametrize("name", sorted(p.name for p in STATIC.glob("*.html")))
def test_no_page_downloads_fonts(name):
    html = page_html(name)
    for marker in FONT_DOWNLOADS:
        assert marker not in html


# ── Migrated pages ──────────────────────────────────────────────


@pytest.fixture(params=THEMED, ids=THEMED)
def themed(request):
    return request.param, page_html(request.param)


def test_page_declares_color_scheme(themed):
    _, html = themed
    assert '<meta name="color-scheme" content="light dark"' in html


def test_page_loads_stylesheet_and_deferred_theme_js(themed):
    _, html = themed
    assert '<link rel="stylesheet" href="/style.css" />' in html
    assert '<script defer src="/theme.js"></script>' in html


def test_page_has_topbar_with_home_link(themed):
    _, html = themed
    assert '<header class="topbar">' in html
    assert '<a class="site-name" href="/">alexander-hagemann.de</a>' in html


def test_toggle_markup(themed):
    _, html = themed
    assert '<button type="button" class="theme-toggle" aria-pressed="false"' in html
    button = html.split('class="theme-toggle"')[1].split("</button>")[0]
    opening_tag = button.split(">")[0]
    assert " hidden" in opening_tag  # theme.js reveals it; no-JS users never see it
    assert 'class="visually-hidden"' in button  # fixed accessible name
    assert button.count('aria-hidden="true"') == 2  # both icons decorative


def test_page_has_site_footer_with_legal_links(themed):
    _, html = themed
    assert '<footer class="site-footer">' in html
    for href in ("/impressum.html", "/datenschutz.html", "/privacy.html"):
        assert f'href="{href}"' in html


def test_page_dropped_terminal_conventions(themed):
    _, html = themed
    assert '<span aria-hidden="true">// </span>' not in html
    assert 'class="back"' not in html
    assert "Courier" not in html


def test_page_styles_use_tokens_only(themed):
    _, html = themed
    for block in STYLE_BLOCK.findall(html):
        assert not HEX.search(block), HEX.search(block).group(0)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `source .venv/bin/activate && python -m pytest tests/test_theme.py -v`
Expected: FAIL — token/selector tests fail (old `style.css` has none of them), `test_theme_js_*` fail with `FileNotFoundError` for `static/theme.js`. The `themed` tests are reported as skipped (empty parameter set). `test_no_page_downloads_fonts` passes for all 7 pages.

- [ ] **Step 3: Rewrite `static/style.css`**

Replace the whole file with:

```css
/* Design tokens. Light is the default; dark applies when the OS asks for it
   (unless the toggle forced light) or when the toggle forced dark. The dark
   block is repeated on purpose: one rule can't sit both inside a media query
   and outside it. Hex values belong on these token lines and nowhere else —
   every pairing is checked against WCAG 2.1 AA (see DESIGN.md). */
:root {
  color-scheme: light;
  --bg: #f6f7f9;
  --surface: #ffffff;
  --text: #1a1d21;
  --text-muted: #57606a;
  --border: #d8dee4;
  --border-strong: #7d8590;
  --accent: #1d4ed8;
  --accent-hover: #1e40af;
  --on-accent: #ffffff;
  --ok: #116329;
  --ok-bg: #dafbe1;
  --warn: #7d4e00;
  --warn-bg: #fff8c5;
  --err: #a40e26;
  --err-bg: #ffebe9;
  --neutral-bg: #eff2f5;
  --shadow: 0 1px 2px rgb(0 0 0 / 0.05);

  --font-sans: system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, "Liberation Mono", monospace;
  --radius: 8px;
  --radius-sm: 6px;
}

@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    color-scheme: dark;
    --bg: #0f1115;
    --surface: #171a21;
    --text: #e6e8eb;
    --text-muted: #9aa4b2;
    --border: #2a2f38;
    --border-strong: #6b7380;
    --accent: #7aa7ff;
    --accent-hover: #a5c3ff;
    --on-accent: #0f1115;
    --ok: #3fb950;
    --ok-bg: #12261a;
    --warn: #d29922;
    --warn-bg: #2b2111;
    --err: #ff6b61;
    --err-bg: #2d1416;
    --neutral-bg: #222731;
    --shadow: none;
  }
}

:root[data-theme="dark"] {
  color-scheme: dark;
  --bg: #0f1115;
  --surface: #171a21;
  --text: #e6e8eb;
  --text-muted: #9aa4b2;
  --border: #2a2f38;
  --border-strong: #6b7380;
  --accent: #7aa7ff;
  --accent-hover: #a5c3ff;
  --on-accent: #0f1115;
  --ok: #3fb950;
  --ok-bg: #12261a;
  --warn: #d29922;
  --warn-bg: #2b2111;
  --err: #ff6b61;
  --err-bg: #2d1416;
  --neutral-bg: #222731;
  --shadow: none;
}

/* ── Base ─────────────────────────────────────────────────── */

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: var(--font-sans);
  font-size: 1rem;
  line-height: 1.6;
  background: var(--bg);
  color: var(--text);
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

main {
  flex: 1;
  width: 100%;
  max-width: 720px;
  margin: 0 auto;
  padding: 2rem 1rem 3rem;
  display: flex;
  flex-direction: column;
  gap: 1.5rem;
}

h1 { font-size: 1.75rem; font-weight: 650; line-height: 1.25; }
h2 { font-size: 1.125rem; font-weight: 600; line-height: 1.35; }

/* Inline links are underlined: blue vs body text is under 3:1, so color
   alone can't mark them (WCAG 1.4.1). */
a { color: var(--accent); text-decoration: underline; text-underline-offset: 0.15em; }
a:hover { color: var(--accent-hover); }

.mono, code { font-family: var(--font-mono); }

code {
  font-size: 0.9em;
  background: var(--neutral-bg);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 0.1em 0.35em;
  overflow-wrap: anywhere;
}

:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  margin: -1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  white-space: nowrap;
  border: 0;
}

.skip-link {
  position: absolute;
  left: -9999px;
  top: 1rem;
}
.skip-link:focus {
  left: 1rem;
  z-index: 9999;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  padding: 0.5rem 1rem;
}

/* ── Top bar ──────────────────────────────────────────────── */

/* Full-width rule, content aligned with the 720px main column. */
.topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 0.5rem max(1rem, calc((100% - 720px) / 2 + 1rem));
  background: var(--surface);
  border-bottom: 1px solid var(--border);
}

.site-name { color: var(--text); font-weight: 600; text-decoration: none; }
.site-name:hover { color: var(--text); text-decoration: underline; }

.theme-toggle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  min-height: 44px;
  background: transparent;
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.theme-toggle[hidden] { display: none; }
.theme-toggle:hover { background: var(--neutral-bg); }

/* Moon while light (click → dark), sun while dark (click → light). */
.theme-toggle[aria-pressed="true"] .icon-moon,
.theme-toggle[aria-pressed="false"] .icon-sun { display: none; }

/* ── Text helpers ─────────────────────────────────────────── */

.description { color: var(--text-muted); max-width: 65ch; }
.note { font-size: 0.8125rem; color: var(--text-muted); }

/* ── Card ─────────────────────────────────────────────────── */

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 1.5rem;
}

.card-header {
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border);
}

.tool-link {
  display: block;
  color: var(--text);
  text-decoration: none;
  transition: border-color 0.1s;
}
.tool-link h2 { margin-bottom: 0.25rem; }
.tool-link p { color: var(--text-muted); }
.tool-link:hover { color: var(--text); border-color: var(--accent); }
.tool-link:hover h2 { text-decoration: underline; }

/* ── Forms ────────────────────────────────────────────────── */

label {
  display: block;
  font-size: 0.875rem;
  font-weight: 500;
  color: var(--text-muted);
  margin-bottom: 0.375rem;
}

input {
  font: inherit;
  width: 100%;
  min-height: 44px;
  padding: 0.5rem 0.75rem;
  background: var(--surface);
  color: var(--text);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
}
input.mono { font-family: var(--font-mono); }
input::placeholder { color: var(--text-muted); opacity: 1; }

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.4rem;
  min-height: 44px;
  padding: 0.5rem 1rem;
  font: inherit;
  font-weight: 600;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  cursor: pointer;
}
.btn-primary { background: var(--accent); color: var(--on-accent); }
.btn-primary:hover:not(:disabled) { background: var(--accent-hover); }
.btn-primary:disabled { opacity: 0.6; cursor: default; }
.btn-secondary { background: var(--surface); color: var(--text); border-color: var(--border-strong); }
.btn-secondary:hover { background: var(--neutral-bg); }

.error {
  color: var(--err);
  background: var(--err-bg);
  border-radius: var(--radius-sm);
  padding: 0.6rem 0.8rem;
}

/* ── Results ──────────────────────────────────────────────── */

.result-list {
  display: grid;
  grid-template-columns: max-content 1fr;
  gap: 0.5rem 1.25rem;
}
.result-list dt { font-size: 0.875rem; font-weight: 500; color: var(--text-muted); padding-top: 0.1rem; }
.result-list dd { font-family: var(--font-mono); overflow-wrap: anywhere; }

@media (max-width: 480px) {
  .result-list { grid-template-columns: 1fr; gap: 0.125rem; }
  .result-list dd + dt { margin-top: 0.6rem; }
}

.value {
  font-family: var(--font-mono);
  font-size: 1.5rem;
  font-weight: 600;
  line-height: 1.3;
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}

/* Status pill: the text carries the meaning, the color only reinforces it. */
.status {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.25rem 0.75rem;
  border-radius: 999px;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--text-muted);
  background: var(--neutral-bg);
}
.status::before {
  content: "";
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: currentColor;
}
.status-up { color: var(--ok); background: var(--ok-bg); }
.status-degraded { color: var(--warn); background: var(--warn-bg); }
.status-down { color: var(--err); background: var(--err-bg); }

/* Loading: the text stays at full contrast; only a decorative dot pulses. */
.loading { color: var(--text-muted); }
.loading::after {
  content: "";
  display: inline-block;
  width: 0.5em;
  height: 0.5em;
  margin-left: 0.5em;
  border-radius: 50%;
  background: currentColor;
  vertical-align: middle;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  50% { opacity: 0.2; }
}

@media (prefers-reduced-motion: reduce) {
  .loading::after { animation: none; }
  .tool-link { transition: none; }
}

/* ── Footer ───────────────────────────────────────────────── */

.site-footer {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem 1.5rem;
  padding: 1.5rem max(1rem, calc((100% - 720px) / 2 + 1rem));
  border-top: 1px solid var(--border);
  font-size: 0.8125rem;
  color: var(--text-muted);
}

.footer-links { display: flex; flex-wrap: wrap; gap: 0.5rem 1.5rem; }
.footer-links a { color: var(--text-muted); text-decoration: none; }
.footer-links a:hover { color: var(--text); text-decoration: underline; }

/* ── Legal pages ──────────────────────────────────────────── */

main.prose { max-width: calc(65ch + 2rem); }

.prose .card { display: flex; flex-direction: column; gap: 1.75rem; }
.prose section h2 { margin-bottom: 0.5rem; }
.prose section p + p,
.prose section p + ul,
.prose section ul + p { margin-top: 0.75rem; }
.prose ul { padding-left: 1.25rem; list-style: disc; }
.prose li + li { margin-top: 0.25rem; }

#optout-state:empty { display: none; }
```

- [ ] **Step 4: Create `static/theme.js`**

```js
// Theme toggle. Every page starts in the OS theme, which CSS applies on its own
// (prefers-color-scheme), so there is no flash to prevent. A click overrides it
// for this page view only — nothing is stored, by design: switching away from
// the OS look is a deliberate per-visit choice.
(function () {
  var root = document.documentElement;
  var media = window.matchMedia("(prefers-color-scheme: dark)");
  var btn = document.querySelector(".theme-toggle");
  if (!btn) return;

  function isDark() {
    var forced = root.getAttribute("data-theme");
    return forced ? forced === "dark" : media.matches;
  }

  function sync() {
    btn.setAttribute("aria-pressed", isDark() ? "true" : "false");
  }

  btn.addEventListener("click", function () {
    root.setAttribute("data-theme", isDark() ? "light" : "dark");
    sync();
  });

  // Keeps aria-pressed honest if the OS theme flips while nothing is forced.
  media.addEventListener("change", sync);

  sync();
  btn.hidden = false;
})();
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python -m pytest tests/test_theme.py -v`
Expected: all non-`themed` tests PASS; `themed` tests still skipped (empty `THEMED`).

- [ ] **Step 6: Run the full suite and lint**

Run: `python -m pytest && ruff check . && ruff format --check .`
Expected: all PASS. If `ruff format --check` flags `tests/test_theme.py`, run `ruff format tests/test_theme.py` and re-run.

- [ ] **Step 7: Commit**

```bash
git add tests/test_theme.py static/style.css static/theme.js
git commit -m "Add light/dark design tokens, shared components and theme toggle"
```

---

### Task 2: Home page and legal pages

**Files:**
- Rewrite: `static/index.html`
- Modify: `static/impressum.html`, `static/datenschutz.html`, `static/privacy.html`
- Modify: `tests/test_theme.py` (`THEMED`)

**Interfaces:**
- Consumes: HEAD, TOPBAR_EN/DE, FOOTER_EN/DE snippets; classes `.card .tool-link .description main.prose .btn .btn-secondary` from Task 1.

- [ ] **Step 1: Extend the tests**

In `tests/test_theme.py` change:

```python
THEMED: list[str] = []
```

to:

```python
THEMED: list[str] = ["datenschutz.html", "impressum.html", "index.html", "privacy.html"]
```

and append at the end of the file:

```python
def test_german_pages_label_the_toggle_in_german():
    for name in ("impressum.html", "datenschutz.html"):
        html = page_html(name)
        assert '<span class="visually-hidden">Dunkelmodus</span>' in html
        assert 'aria-label="Rechtliches"' in html


def test_privacy_opt_out_uses_shared_button():
    for name in ("datenschutz.html", "privacy.html"):
        assert '<button type="button" id="optout-toggle" class="btn btn-secondary">' in page_html(name)
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_theme.py -v`
Expected: FAIL for the four pages (no color-scheme meta, no topbar, `// ` present, hex in style blocks) and for the two new tests.

- [ ] **Step 3: Rewrite `static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Self-hosted tools and utilities by Alexander Hagemann." />
  <title>alexander-hagemann.de</title>
  <meta name="color-scheme" content="light dark" />
  <link rel="stylesheet" href="/style.css" />
  <script defer src="/theme.js"></script>
  <style>
    .tools { display: flex; flex-direction: column; gap: 1rem; }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="topbar">
    <a class="site-name" href="/">alexander-hagemann.de</a>
    <button type="button" class="theme-toggle" aria-pressed="false" title="Toggle dark mode" hidden>
      <svg class="icon-moon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg class="icon-sun" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
      <span class="visually-hidden">Dark mode</span>
    </button>
  </header>

  <main id="main">
    <h1>Tools</h1>

    <p class="description">
      Personal collection of self-hosted tools.
    </p>

    <div class="tools">
      <a class="card tool-link" href="/getip">
        <h2>IP Lookup</h2>
        <p>Check your public IPv4 and IPv6 addresses along with geolocation data (country, region, city, ISP, coordinates, timezone).</p>
      </a>

      <a class="card tool-link" href="/cidr">
        <h2>CIDR Calculator</h2>
        <p>Enter an IPv4 or IPv6 address and a prefix length to get the start and end address of that range.</p>
      </a>

      <a class="card tool-link" href="/up">
        <h2>Is It Up?</h2>
        <p>Check whether a website is reachable, with response time, HTTP status, and the exact stage a failed check broke down at.</p>
      </a>
    </div>
  </main>

  <footer class="site-footer">
    <nav class="footer-links" aria-label="Legal">
      <a href="/impressum.html" lang="de">Impressum</a>
      <a href="/datenschutz.html" lang="de">Datenschutz</a>
      <a href="/privacy.html" lang="en">Privacy</a>
    </nav>
  </footer>

  <!-- Self-hosted GoatCounter: first-party endpoints only, cookieless, no third party. -->
  <script data-goatcounter="/count" async src="/count.js"></script>
  <noscript><img src="/count?p=/" alt="" aria-hidden="true" width="1" height="1" style="position:absolute"></noscript>
</body>
</html>
```

(The h1 changes from the domain to "Tools" because the top bar now carries the domain; repeating it as the heading would read twice.)

- [ ] **Step 4: Migrate `static/impressum.html`**

1. Replace

```html
  <link rel="stylesheet" href="/style.css" />
  <style>
    body { padding: 3rem 2rem; }
  </style>
```

with the HEAD snippet.

2. Replace

```html
  <div class="container">
    <a class="back" href="/"><span aria-hidden="true">← </span>Zurück</a>

    <main id="main">
```

with TOPBAR_DE followed by a blank line and `  <main id="main" class="prose">`.

3. Replace

```html
    </main>
  </div>
```

with `  </main>`, a blank line, then FOOTER_DE.

4. Remove every heading prefix:

```bash
sed -i 's|<span aria-hidden="true">// </span>||g' static/impressum.html
```

- [ ] **Step 5: Migrate `static/datenschutz.html`**

1. Replace the whole block from `  <link rel="stylesheet" href="/style.css" />` through the closing `  </style>` (lines 8–32: the `body` padding rule, the `.container section` spacing rules and the `#optout-toggle` rules — all now in `style.css`) with the HEAD snippet.
2. Same `<div class="container">…<main id="main">` replacement as Step 4.2 (TOPBAR_DE, `<main id="main" class="prose">`). The back link text there is `Zurück`.
3. Same `</main>\n  </div>` replacement as Step 4.3 with FOOTER_DE.
4. Replace `<button type="button" id="optout-toggle"></button>` with `<button type="button" id="optout-toggle" class="btn btn-secondary"></button>`.
5. `sed -i 's|<span aria-hidden="true">// </span>||g' static/datenschutz.html`

Leave the opt-out `<script>` at the bottom exactly as it is.

- [ ] **Step 6: Migrate `static/privacy.html`**

Same as Step 5 but with TOPBAR_EN, FOOTER_EN, and the back link text `Back`:

1. Replace lines 8–32 (`<link …style.css />` through `</style>`) with the HEAD snippet.
2. Replace the `<div class="container">` / `<a class="back" …>Back</a>` / `<main id="main">` block with TOPBAR_EN and `<main id="main" class="prose">`.
3. Replace `    </main>\n  </div>` with `  </main>` + FOOTER_EN.
4. Add `class="btn btn-secondary"` to `#optout-toggle`.
5. `sed -i 's|<span aria-hidden="true">// </span>||g' static/privacy.html`

- [ ] **Step 7: Run the tests**

Run: `python -m pytest tests/test_theme.py tests/test_analytics.py -v`
Expected: PASS (analytics tests confirm tracker, pixel and opt-out are intact).

- [ ] **Step 8: Eyeball both themes**

Run: `uvicorn main:app --port 8000` (background), open `http://localhost:8000/`, `/impressum.html`, `/datenschutz.html`, `/privacy.html`. Toggle the theme on each; confirm the opt-out button still flips its label on click. Stop the server.

- [ ] **Step 9: Commit**

```bash
git add static/index.html static/impressum.html static/datenschutz.html static/privacy.html tests/test_theme.py
git commit -m "Move home and legal pages to the light/dark design"
```

---

### Task 3: IP Lookup page

**Files:**
- Rewrite: `static/getip.html`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Consumes: `.card .card-header .value .loading .btn .btn-secondary .note .description code .site-footer` from Task 1.
- JS contract kept: element ids `ip-v4 geo-v4 ip-v6 geo-v6`, endpoints `https://ip4.alexander-hagemann.de/ip` / `https://ip6.alexander-hagemann.de/ip`, `aria-live` + `aria-atomic` on the value, `aria-busy` while loading.

- [ ] **Step 1: Extend the tests**

Add `"getip.html"` to `THEMED` (keep the list sorted):

```python
THEMED: list[str] = ["datenschutz.html", "getip.html", "impressum.html", "index.html", "privacy.html"]
```

Append:

```python
def test_getip_shows_visible_loading_text_and_keeps_live_regions():
    html = page_html("getip.html")
    for v in ("v4", "v6"):
        assert (
            f'<div class="value loading" id="ip-{v}" aria-live="polite" aria-atomic="true">Loading…</div>' in html
        )
        assert f'<div id="geo-{v}" aria-live="polite"></div>' in html
    assert 'btn.className = "btn btn-secondary copy-btn";' in html
    # The visible "Loading…" text is the label now; an aria-label would hide it.
    assert 'setAttribute("aria-label", "Loading")' not in html
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_theme.py -k getip -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite `static/getip.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Look up your public IPv4 and IPv6 addresses with geolocation data. Returns JSON via HTTP GET." />
  <title>IPv4 and IPv6 Lookup</title>
  <meta name="color-scheme" content="light dark" />
  <link rel="stylesheet" href="/style.css" />
  <script defer src="/theme.js"></script>
  <style>
    .api-hint { font-size: 0.875rem; color: var(--text-muted); line-height: 1.9; }

    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
      gap: 1rem;
    }

    .value.unavailable {
      font-family: var(--font-sans);
      font-size: 1rem;
      font-weight: 400;
      color: var(--text-muted);
    }

    .geo-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 0.75rem 1rem;
      margin-top: 1.25rem;
    }
    .geo-item dt { font-size: 0.8125rem; font-weight: 500; color: var(--text-muted); }
    .geo-item dd { overflow-wrap: anywhere; }

    @media (max-width: 400px) {
      .geo-grid { grid-template-columns: 1fr; }
    }

    .copy-btn { margin-top: 1.25rem; }
    .copy-btn.copied { color: var(--ok); border-color: var(--ok); }
    .copy-btn.failed { color: var(--err); border-color: var(--err); }
    .copy-btn.copied::before { content: "✓"; content: "✓" / ""; }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="topbar">
    <a class="site-name" href="/">alexander-hagemann.de</a>
    <button type="button" class="theme-toggle" aria-pressed="false" title="Toggle dark mode" hidden>
      <svg class="icon-moon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg class="icon-sun" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
      <span class="visually-hidden">Dark mode</span>
    </button>
  </header>

  <main id="main">
    <h1>Your IP address</h1>

    <p class="description">
      Detects your public IPv4 and IPv6 addresses with geolocation data.
      Both are resolved independently — dual-stack connections show both.
    </p>

    <div class="cards">
      <section class="card" id="card-v4" aria-labelledby="label-v4">
        <div class="card-header">
          <h2 id="label-v4">IPv4</h2>
        </div>
        <div class="value loading" id="ip-v4" aria-live="polite" aria-atomic="true">Loading…</div>
        <div id="geo-v4" aria-live="polite"></div>
      </section>

      <section class="card" id="card-v6" aria-labelledby="label-v6">
        <div class="card-header">
          <h2 id="label-v6">IPv6</h2>
        </div>
        <div class="value loading" id="ip-v6" aria-live="polite" aria-atomic="true">Loading…</div>
        <div id="geo-v6" aria-live="polite"></div>
      </section>
    </div>

    <p class="note">
      Geolocation is approximate — IP-based lookups can be off by city or region.
      Treat results as a best guess, not an exact location.
    </p>

    <p class="api-hint">
      Returns JSON via HTTP GET:<br>
      <code>GET https://ip4.alexander-hagemann.de/ip</code><br>
      <code>GET https://ip6.alexander-hagemann.de/ip</code>
    </p>
  </main>

  <footer class="site-footer">
    <p>This product includes GeoLite2 data created by MaxMind, available from <a href="https://www.maxmind.com" target="_blank" rel="noopener" aria-label="maxmind.com (opens in a new tab)">maxmind.com</a></p>
    <nav class="footer-links" aria-label="Legal">
      <a href="/impressum.html" lang="de">Impressum</a>
      <a href="/datenschutz.html" lang="de">Datenschutz</a>
      <a href="/privacy.html" lang="en">Privacy</a>
    </nav>
  </footer>

  <script>
    const IPV4_ENDPOINT = "https://ip4.alexander-hagemann.de/ip";
    const IPV6_ENDPOINT = "https://ip6.alexander-hagemann.de/ip";

    function renderGeo(geo) {
      if (!geo || Object.keys(geo).length === 0) return null;
      const fields = [
        ["Country", geo.country],
        ["Region", geo.region],
        ["City", geo.city],
        ["ISP", geo.isp],
        ["Timezone", geo.timezone],
        ["Coordinates", geo.latitude && geo.longitude
          ? `${geo.latitude}, ${geo.longitude}` : null],
      ];
      const dl = document.createElement("dl");
      dl.className = "geo-grid";
      fields.filter(([, v]) => v).forEach(([label, value]) => {
        const div = document.createElement("div");
        div.className = "geo-item";
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = value;
        div.append(dt, dd);
        dl.appendChild(div);
      });
      return dl;
    }

    function makeCopyBtn(ip, version) {
      const btn = document.createElement("button");
      btn.className = "btn btn-secondary copy-btn";
      btn.textContent = "Copy IP";
      btn.setAttribute("aria-label", `Copy ${version} address ${ip}`);
      btn.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(ip);
          btn.removeAttribute("aria-label");
          btn.textContent = "Copied";
          btn.classList.add("copied");
          setTimeout(() => {
            btn.textContent = "Copy IP";
            btn.setAttribute("aria-label", `Copy ${version} address ${ip}`);
            btn.classList.remove("copied");
          }, 1500);
        } catch {
          btn.setAttribute("aria-label", `Copy failed for ${version} address ${ip}`);
          btn.textContent = "Copy failed";
          btn.classList.add("failed");
          setTimeout(() => {
            btn.textContent = "Copy IP";
            btn.setAttribute("aria-label", `Copy ${version} address ${ip}`);
            btn.classList.remove("failed");
          }, 1500);
        }
      });
      return btn;
    }

    async function fetchIP(endpoint, ipEl, geoEl, version) {
      ipEl.setAttribute("aria-busy", "true");
      try {
        const res = await fetch(endpoint);
        if (!res.ok) throw new Error();
        const { ip, geo } = await res.json();
        ipEl.textContent = ip;
        ipEl.classList.remove("loading");
        ipEl.removeAttribute("aria-busy");
        geoEl.replaceChildren(...[renderGeo(geo), makeCopyBtn(ip, version)].filter(Boolean));
      } catch {
        const message = version === "IPv6"
          ? "No IPv6 route detected on this network."
          : "Couldn't reach the server. Check your connection and try again.";
        ipEl.textContent = message;
        ipEl.classList.add("unavailable");
        ipEl.classList.remove("loading");
        ipEl.removeAttribute("aria-busy");
      }
    }

    fetchIP(IPV4_ENDPOINT, document.getElementById("ip-v4"), document.getElementById("geo-v4"), "IPv4");
    fetchIP(IPV6_ENDPOINT, document.getElementById("ip-v6"), document.getElementById("geo-v6"), "IPv6");
  </script>

  <!-- Self-hosted GoatCounter: first-party endpoints only, cookieless, no third party. -->
  <script data-goatcounter="/count" async src="/count.js"></script>
  <noscript><img src="/count?p=/getip" alt="" aria-hidden="true" width="1" height="1" style="position:absolute"></noscript>
</body>
</html>
```

Changes inside the script, for the reviewer: copy button gets the shared button classes; "Copied!" → "Copied" (the ✓ comes from CSS with empty alt text); the `aria-label="Loading"` set/remove pairs are gone because the element now contains visible "Loading…" text; the error path uses `textContent` instead of `innerHTML` with a terminal-style `! ` prefix.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_theme.py tests/test_analytics.py tests/test_routes.py -v`
Expected: PASS (`test_getip_serves_html` still finds "IPv4").

- [ ] **Step 5: Eyeball**

Start `uvicorn main:app --port 8000`, open `/getip`. Locally both endpoints are cross-origin production URLs, so expect real values or the error text; check the loading dot pulses, the error text is readable, and the Copy button's three states look right in both themes (DevTools → force `prefers-color-scheme`, or use the toggle). Stop the server.

- [ ] **Step 6: Commit**

```bash
git add static/getip.html tests/test_theme.py
git commit -m "Move IP lookup page to the light/dark design"
```

---

### Task 4: CIDR calculator page

**Files:**
- Rewrite: `static/cidr.html`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Consumes: `.card .btn .btn-primary input.mono .error .result-list .description` from Task 1; `CidrCalc.computeRange(ipStr, prefix) -> {start, end} | {error}` from the untouched `static/cidr-logic.js`.
- JS contract kept: ids `cidr-form ip-input prefix-input error-msg result result-start result-end`; classes `.visible` on `.error` and `.result`.

- [ ] **Step 1: Extend the tests**

`THEMED` becomes:

```python
THEMED: list[str] = [
    "cidr.html", "datenschutz.html", "getip.html", "impressum.html", "index.html", "privacy.html",
]
```

Append:

```python
def test_cidr_keeps_script_hooks_and_labels():
    html = page_html("cidr.html")
    for hook in ('id="cidr-form"', 'id="ip-input"', 'id="prefix-input"', 'id="error-msg"',
                 'id="result"', 'id="result-start"', 'id="result-end"'):
        assert hook in html
    assert '<label for="ip-input">' in html
    assert '<label for="prefix-input">' in html
    assert '<p class="error" id="error-msg" role="alert"></p>' in html
    assert '<script src="/cidr-logic.js"></script>' in html
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_theme.py -k cidr -v`
Expected: FAIL (cidr.html not yet migrated).

- [ ] **Step 3: Rewrite `static/cidr.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Calculate the start and end address of an IPv4 or IPv6 CIDR range." />
  <title>CIDR Range Calculator</title>
  <meta name="color-scheme" content="light dark" />
  <link rel="stylesheet" href="/style.css" />
  <script defer src="/theme.js"></script>
  <style>
    form { display: flex; flex-direction: column; gap: 1rem; }

    .field-row { display: flex; flex-wrap: wrap; gap: 0.75rem; }
    .field-ip { flex: 3 1 12rem; }
    .field-prefix { flex: 1 1 6rem; }

    /* The "/" glyph sits inside the field's border, so the wrapper carries the
       border and the focus ring instead of the input. */
    .prefix-input-wrap {
      display: flex;
      align-items: center;
      background: var(--surface);
      border: 1px solid var(--border-strong);
      border-radius: var(--radius-sm);
    }
    .prefix-input-wrap span { padding-left: 0.75rem; color: var(--text-muted); font-family: var(--font-mono); }
    .prefix-input-wrap input { border: none; padding-left: 0.25rem; }
    .prefix-input-wrap input:focus-visible { outline: none; }
    .prefix-input-wrap:focus-within { outline: 2px solid var(--accent); outline-offset: 2px; }

    form .btn { align-self: flex-start; }

    .error { display: none; margin-top: 1rem; }
    .error.visible { display: block; }

    .result {
      display: none;
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
    }
    .result.visible { display: block; }
    .result-list dd { font-size: 1.125rem; font-weight: 600; }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="topbar">
    <a class="site-name" href="/">alexander-hagemann.de</a>
    <button type="button" class="theme-toggle" aria-pressed="false" title="Toggle dark mode" hidden>
      <svg class="icon-moon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg class="icon-sun" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
      <span class="visually-hidden">Dark mode</span>
    </button>
  </header>

  <main id="main">
    <h1>CIDR range calculator</h1>

    <p class="description">
      Enter an IPv4 or IPv6 address and a prefix length to get the first
      and last address of that range.
    </p>

    <div class="card">
      <form id="cidr-form" novalidate>
        <div class="field-row">
          <div class="field-ip">
            <label for="ip-input">IP address</label>
            <input class="mono" type="text" id="ip-input" name="ip" placeholder="192.168.1.10" autocomplete="off" spellcheck="false" required />
          </div>
          <div class="field-prefix">
            <label for="prefix-input">Prefix</label>
            <div class="prefix-input-wrap">
              <span aria-hidden="true">/</span>
              <input class="mono" type="number" id="prefix-input" name="prefix" placeholder="24" min="0" max="128" inputmode="numeric" required />
            </div>
          </div>
        </div>

        <button class="btn btn-primary" type="submit">Calculate</button>
      </form>

      <p class="error" id="error-msg" role="alert"></p>

      <div class="result" id="result">
        <dl class="result-list">
          <dt>Start of range</dt>
          <dd id="result-start"></dd>
          <dt>End of range</dt>
          <dd id="result-end"></dd>
        </dl>
      </div>
    </div>
  </main>

  <footer class="site-footer">
    <nav class="footer-links" aria-label="Legal">
      <a href="/impressum.html" lang="de">Impressum</a>
      <a href="/datenschutz.html" lang="de">Datenschutz</a>
      <a href="/privacy.html" lang="en">Privacy</a>
    </nav>
  </footer>

  <script src="/cidr-logic.js"></script>
  <script>
    const { computeRange } = CidrCalc;

    const form = document.getElementById("cidr-form");
    const ipInput = document.getElementById("ip-input");
    const prefixInput = document.getElementById("prefix-input");
    const errorMsg = document.getElementById("error-msg");
    const result = document.getElementById("result");
    const resultStart = document.getElementById("result-start");
    const resultEnd = document.getElementById("result-end");

    form.addEventListener("submit", (e) => {
      e.preventDefault();

      const ipStr = ipInput.value.trim();
      const prefixStr = prefixInput.value.trim().replace(/^\//, "");
      const prefix = parseInt(prefixStr, 10);

      const outcome = computeRange(ipStr, prefix);

      if (outcome.error) {
        errorMsg.textContent = outcome.error;
        errorMsg.classList.add("visible");
        result.classList.remove("visible");
        return;
      }

      errorMsg.classList.remove("visible");
      resultStart.textContent = outcome.start;
      resultEnd.textContent = outcome.end;
      result.classList.add("visible");
    });
  </script>

  <!-- Self-hosted GoatCounter: first-party endpoints only, cookieless, no third party. -->
  <script data-goatcounter="/count" async src="/count.js"></script>
  <noscript><img src="/count?p=/cidr" alt="" aria-hidden="true" width="1" height="1" style="position:absolute"></noscript>
</body>
</html>
```

The calculator script is unchanged. The `<dl>` loses its wrapper `<div>`s so it can use the shared two-column `.result-list`.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_theme.py tests/test_analytics.py tests/test_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Eyeball**

Start the server, open `/cidr`. Try `192.168.1.10` / `24` (expect `192.168.1.0` – `192.168.1.255`), `2001:db8:abcd:1234:5678:9abc:def0:1234` / `64` at 320px width (values wrap, no horizontal scroll), and `foo` / `24` (error shows in red on a red tint). Tab through: the focus ring wraps the whole prefix field including "/". Check both themes. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add static/cidr.html tests/test_theme.py
git commit -m "Move CIDR calculator to the light/dark design"
```

---

### Task 5: Is It Up? page

**Files:**
- Rewrite: `static/up.html`
- Modify: `tests/test_theme.py`

**Interfaces:**
- Consumes: `.card .btn .btn-primary input.mono .result-list .status .status-* .note .description` from Task 1; `GET /api/up?url=` response fields `status detail ignored_path http_status response_time_ms redirects final_url resolved_ips ip_geo stage` (unchanged).
- JS contract kept: ids `url check result badge detail fields`.

- [ ] **Step 1: Extend the tests**

`THEMED` becomes:

```python
THEMED: list[str] = [
    "cidr.html", "datenschutz.html", "getip.html", "impressum.html", "index.html", "privacy.html", "up.html",
]
```

Append:

```python
def test_up_has_visible_label_and_status_pill():
    html = page_html("up.html")
    assert '<label for="url">' in html
    assert 'aria-label="URL to check"' not in html  # replaced by the visible label
    assert 'badge.className = "status status-" + status;' in html
    assert '<div class="result" id="result" aria-live="polite" hidden>' in html
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/test_theme.py -k up -v`
Expected: FAIL.

- [ ] **Step 3: Rewrite `static/up.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <meta name="description" content="Check whether a website is reachable and how it responds." />
  <title>Is It Up? — alexander-hagemann.de</title>
  <meta name="color-scheme" content="light dark" />
  <link rel="stylesheet" href="/style.css" />
  <script defer src="/theme.js"></script>
  <style>
    .input-row { display: flex; gap: 0.75rem; }
    .input-row input { flex: 1; min-width: 0; }

    .result {
      margin-top: 1.5rem;
      padding-top: 1.5rem;
      border-top: 1px solid var(--border);
    }

    .status-note { margin-top: 0.75rem; }

    .result-list { margin-top: 1rem; }
    .result-list:empty { margin-top: 0; }

    .ip-line + .ip-line { margin-top: 0.5rem; }
    .ip-geo {
      display: block;
      font-family: var(--font-sans);
      font-size: 0.8125rem;
      color: var(--text-muted);
    }
  </style>
</head>
<body>
  <a class="skip-link" href="#main">Skip to main content</a>

  <header class="topbar">
    <a class="site-name" href="/">alexander-hagemann.de</a>
    <button type="button" class="theme-toggle" aria-pressed="false" title="Toggle dark mode" hidden>
      <svg class="icon-moon" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>
      <svg class="icon-sun" viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>
      <span class="visually-hidden">Dark mode</span>
    </button>
  </header>

  <main id="main">
    <h1>Is It Up?</h1>

    <p class="description">
      Check whether a website is reachable, with response time, HTTP status,
      and the exact stage a failed check broke down at.
      Only the domain is checked &mdash; anything after it is ignored.
    </p>

    <div class="card">
      <label for="url">Website</label>
      <div class="input-row">
        <input class="mono" type="text" id="url" placeholder="example.com"
               maxlength="2048" autocomplete="off" spellcheck="false" />
        <button class="btn btn-primary" id="check">Check</button>
      </div>

      <div class="result" id="result" aria-live="polite" hidden>
        <h2 id="badge"></h2>
        <p class="status-note" id="detail"></p>
        <dl class="result-list" id="fields"></dl>
      </div>
    </div>

    <p class="note">
      Geolocation is approximate — IP-based lookups can be off by city or region,
      and large sites answer from whichever edge node is nearest to this server.
    </p>
  </main>

  <footer class="site-footer">
    <nav class="footer-links" aria-label="Legal">
      <a href="/impressum.html" lang="de">Impressum</a>
      <a href="/datenschutz.html" lang="de">Datenschutz</a>
      <a href="/privacy.html" lang="en">Privacy</a>
    </nav>
  </footer>

  <script>
    const input = document.getElementById("url");
    const button = document.getElementById("check");
    const result = document.getElementById("result");
    const badge = document.getElementById("badge");
    const detail = document.getElementById("detail");
    const fields = document.getElementById("fields");

    const STATUS_LABELS = {
      up: "Up",
      degraded: "Reachable, but erroring",
      down: "Down",
      invalid: "Invalid input",
      blocked: "Can't be checked",
    };

    const STAGE_LABELS = {
      dns: "DNS resolution",
      connect: "TCP connection",
      http: "HTTP request",
      input: "Input validation",
      redirect: "Redirect",
    };

    function addField(label, value) {
      if (value == null || value === "") return;
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.textContent = value;
      fields.append(dt, dd);
    }

    function addFieldNode(label, node) {
      if (!node) return;
      const dt = document.createElement("dt");
      dt.textContent = label;
      const dd = document.createElement("dd");
      dd.append(node);
      fields.append(dt, dd);
    }

    // One block per resolved IP: the address, and under it whatever geo we have.
    function renderIps(ips, geoList) {
      if (!ips || !ips.length) return null;

      const byIp = new Map((geoList || []).map((entry) => [entry.ip, entry]));
      const frag = document.createDocumentFragment();

      for (const ip of ips) {
        const geo = byIp.get(ip) || {};
        const line = document.createElement("div");
        line.className = "ip-line";
        line.textContent = ip;

        const place = [geo.city, geo.region, geo.country].filter(Boolean).join(", ");
        const meta = [place, geo.isp].filter(Boolean).join(" · ");
        if (meta) {
          const span = document.createElement("span");
          span.className = "ip-geo";
          span.textContent = meta;
          line.append(span);
        }
        frag.append(line);
      }
      return frag;
    }

    function show(status, message) {
      badge.textContent = STATUS_LABELS[status] || status;
      badge.className = "status status-" + status;
      detail.textContent = message || "";
      result.hidden = false;
    }

    async function check() {
      const url = input.value.trim();
      if (!url) return;

      button.disabled = true;
      button.textContent = "Checking";
      fields.replaceChildren();
      result.hidden = true;

      try {
        const res = await fetch("/api/up?url=" + encodeURIComponent(url));
        if (res.status === 429) {
          throw new Error("Rate limit reached — wait a moment and try again.");
        }
        const data = await res.json();

        show(data.status, data.detail || (data.status === "up" ? "Site responded normally" : ""));

        addField("Ignored", data.ignored_path
          ? data.ignored_path + " — only the domain is checked" : null);
        addField("HTTP status", data.http_status);
        addField("Response time", data.response_time_ms != null ? data.response_time_ms + " ms" : null);
        if (data.redirects && data.redirects.length) {
          addField("Final URL", data.final_url);
          addField("Redirects", data.redirects.join(" → "));
        }
        addFieldNode("Resolved IPs", renderIps(data.resolved_ips, data.ip_geo));
        addField("Failed at", data.stage && data.stage !== "done"
          ? (STAGE_LABELS[data.stage] || data.stage) : null);
      } catch (err) {
        fields.replaceChildren();
        show("invalid", err.message);
      } finally {
        button.disabled = false;
        button.textContent = "Check";
      }
    }

    button.addEventListener("click", check);
    input.addEventListener("keydown", (e) => { if (e.key === "Enter") check(); });
  </script>

  <!-- Self-hosted GoatCounter: first-party endpoints only, cookieless, no third party. -->
  <script data-goatcounter="/count" async src="/count.js"></script>
  <noscript><img src="/count?p=/up" alt="" aria-hidden="true" width="1" height="1" style="position:absolute"></noscript>
</body>
</html>
```

The only script change is `badge.className = "status status-" + status;`. The bottom back link is removed (the top bar links home). `invalid` and `blocked` get the neutral pill from the base `.status` rule.

- [ ] **Step 4: Run the tests**

Run: `python -m pytest tests/test_theme.py tests/test_analytics.py tests/test_routes.py tests/test_upcheck.py -v`
Expected: PASS.

- [ ] **Step 5: Eyeball**

Start the server, open `/up`. Check `example.com` (expect "Up" pill, green), a nonexistent domain like `doesnotexist.invalid` (expect neutral "Invalid input" or red "Down" depending on backend classification), and an empty submit (nothing happens). Confirm the pill text, the result list at 320px width (labels stack above values), and both themes. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add static/up.html tests/test_theme.py
git commit -m "Move Is It Up? page to the light/dark design"
```

---

### Task 6: Lock coverage, update docs, full verification

**Files:**
- Modify: `tests/test_theme.py`
- Rewrite: `DESIGN.md`
- Modify: `PRODUCT.md`, `CLAUDE.md`

- [ ] **Step 1: Make every page mandatory**

In `tests/test_theme.py` replace the `THEMED` list and its comment with:

```python
# Every page is on the design system; a new page is covered automatically.
THEMED: list[str] = sorted(p.name for p in STATIC.glob("*.html"))
```

and append:

```python
def test_every_page_is_themed():
    assert len(THEMED) == 7
```

Run: `python -m pytest tests/test_theme.py -v` — Expected: PASS.

- [ ] **Step 2: Rewrite `DESIGN.md`**

Replace the whole file with:

````markdown
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
````

- [ ] **Step 3: Update `PRODUCT.md`**

Replace the `## Brand Personality` section body with:

```markdown
Calm, conventional and precise. The site should feel like a well-made native utility: light by default, follows the visitor's light/dark preference, uses their system font, and gets out of the way. Confidence comes from accuracy and restraint, not decoration.
```

In `## Design Principles` replace the bullet `- Restraint over spectacle: retro/terminal flavor is one accent at a time, never the whole surface.` with:

```markdown
- Familiar over clever: conventional layout, one blue accent, system fonts — nothing a first-time visitor has to learn.
```

In `## Accessibility & Inclusion` replace the sentence beginning `Maintain and extend the existing baseline` through the end of that paragraph with:

```markdown
Maintain and extend the existing baseline — skip links, `aria-live` regions on dynamic content, visible focus states, and `prefers-reduced-motion` handling — in both the light and dark theme, and compute contrast ratios for any new color pairing (see DESIGN.md §2).
```

- [ ] **Step 4: Update `CLAUDE.md`**

Replace the paragraph in `## Architecture` that starts `This is a single FastAPI app` — specifically its sentence `There is no build step or frontend framework — every page is hand-written HTML/CSS/vanilla JS, self-contained (styles inline in a \`<style>\` block per page), sharing only \`static/style.css\` for base resets/typography.` — with:

```markdown
There is no build step or frontend framework — every page is hand-written HTML/CSS/vanilla JS. `static/style.css` holds the design tokens and every shared component; each page's `<style>` block holds only page-specific layout and references tokens (no hex). `static/theme.js` drives the light/dark toggle.
```

In the "When adding a new tool page" sentence, append: ` Include the color-scheme meta, \`<script defer src="/theme.js">\`, the top bar and the site footer — copy them from an existing page; \`tests/test_theme.py\` enforces them.`

Replace the entire `## Design constraints (see PRODUCT.md / DESIGN.md for full detail)` section with:

```markdown
## Design constraints (see PRODUCT.md / DESIGN.md for full detail)

A light-first, conventional utility look that follows the visitor's OS theme:
- Colors only via the CSS custom properties in `static/style.css`. Light tokens on `:root`; dark tokens repeated under `@media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) }` and `:root[data-theme="dark"]`. A new token goes in all three blocks, with its contrast checked.
- One blue accent; green/amber/red are reserved for status and errors and never carry meaning alone.
- System fonts only (`--font-sans`, `--font-mono`) — never add `@font-face`, font files, or Google Fonts. Mono is for technical values only.
- The theme toggle overrides the OS theme for the current page view only. **Do not persist it** (no localStorage/cookies) — deliberate decision, 2026-10-06.
- 8px card / 6px control radius, at most the one subtle light-theme shadow, no gradients or hover lifts.
- Inline links are underlined (accent vs body text is below 3:1).
- WCAG 2.1 AA is a hard constraint: skip links, `aria-live` on dynamic content, visible focus states, visible labels on inputs, and `prefers-reduced-motion` fallbacks for any animation are expected on every page, in both themes.
```

- [ ] **Step 5: Full automated verification**

Run:

```bash
python -m pytest -v
ruff check .
ruff format --check .
command -v node >/dev/null && node --test || echo "node not installed — cidr-logic.js tests not run (file unchanged)"
grep -rn "Courier\|@font-face\|fonts.googleapis" static/ || echo "clean"
```

Expected: pytest all PASS, ruff clean, the node line prints the "not installed" message on this machine, grep prints `clean`.

- [ ] **Step 6: Manual verification (record results in the final report)**

Start `uvicorn main:app --port 8000` and for each of the 7 pages:

1. OS light → page light, toggle shows moon, `aria-pressed="false"`. Click → dark, sun, `aria-pressed="true"`. Click → light again.
2. OS dark (DevTools → Rendering → emulate `prefers-color-scheme: dark`) → page dark without a click, `aria-pressed="true"`.
3. Without clicking, switch the emulation light↔dark → page and `aria-pressed` follow. Then click the toggle and switch the emulation again → page stays on the clicked theme.
4. Reload after toggling → page is back in the OS theme (nothing stored). DevTools → Application → Local Storage shows no theme key.
5. JavaScript disabled → OS theme applies, no toggle button visible.
6. 320px viewport and 200% zoom → no horizontal scroll, footer never overlaps content, long IPv6 values wrap.
7. Keyboard only → skip link appears on first Tab, focus ring visible on every control in both themes, toggle operable with Enter/Space.
8. Emulate `prefers-reduced-motion: reduce` on `/getip` → loading dot is static.

Stop the server.

- [ ] **Step 7: Accessibility review**

Dispatch the `ux-accessibility-reviewer` agent over `static/style.css`, `static/theme.js` and the 7 pages. Fix anything it confirms as a WCAG 2.1 AA failure (re-run Step 5 after fixes); list anything else in the final report for the user to decide.

- [ ] **Step 8: Commit**

```bash
git add tests/test_theme.py DESIGN.md PRODUCT.md CLAUDE.md
git commit -m "Document the light/dark design system and require it on every page"
```
