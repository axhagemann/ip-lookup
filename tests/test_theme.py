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

# Every page is on the design system; a new page is covered automatically.
THEMED: list[str] = sorted(p.name for p in STATIC.glob("*.html"))

THEMED_TOKENS = (
    "--bg",
    "--surface",
    "--text",
    "--text-muted",
    "--border",
    "--border-strong",
    "--accent",
    "--accent-hover",
    "--on-accent",
    "--ok",
    "--ok-bg",
    "--warn",
    "--warn-bg",
    "--err",
    "--err-bg",
    "--neutral-bg",
    "--shadow",
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


def test_german_pages_label_the_toggle_in_german():
    for name in ("impressum.html", "datenschutz.html"):
        html = page_html(name)
        assert '<span class="visually-hidden">Dunkelmodus</span>' in html
        assert 'aria-label="Rechtliches"' in html


def test_privacy_opt_out_uses_shared_button():
    for name in ("datenschutz.html", "privacy.html"):
        assert '<button type="button" id="optout-toggle" class="btn btn-secondary">' in page_html(name)


def test_getip_shows_visible_loading_text_and_keeps_live_regions():
    html = page_html("getip.html")
    for v in ("v4", "v6"):
        assert f'<div class="value loading" id="ip-{v}" aria-live="polite" aria-atomic="true">Loading…</div>' in html
        assert f'<div id="geo-{v}" aria-live="polite"></div>' in html
    assert 'btn.className = "btn btn-secondary copy-btn";' in html
    # The visible "Loading…" text is the label now; an aria-label would hide it.
    assert 'setAttribute("aria-label", "Loading")' not in html


def test_cidr_keeps_script_hooks_and_labels():
    html = page_html("cidr.html")
    for hook in (
        'id="cidr-form"',
        'id="ip-input"',
        'id="prefix-input"',
        'id="error-msg"',
        'id="result"',
        'id="result-start"',
        'id="result-end"',
    ):
        assert hook in html
    assert '<label for="ip-input">' in html
    assert '<label for="prefix-input">' in html
    assert '<p class="error" id="error-msg" role="alert"></p>' in html
    assert '<script src="/cidr-logic.js"></script>' in html


def test_up_has_visible_label_and_status_pill():
    html = page_html("up.html")
    assert '<label for="url">' in html
    assert 'aria-label="URL to check"' not in html  # replaced by the visible label
    assert 'badge.className = "status status-" + status;' in html
    assert '<div class="result" id="result" aria-live="polite" hidden>' in html


def test_every_page_is_themed():
    assert len(THEMED) == 7


def test_cidr_prefix_input_can_shrink_inside_its_wrapper():
    # A flex child keeps its intrinsic width unless min-width is lifted, which
    # would push the prefix field past its column (WCAG 1.4.10 Reflow).
    css = STYLE_BLOCK.findall(page_html("cidr.html"))[0]
    rule = css.split(".prefix-input-wrap input {")[1].split("}")[0]
    assert "min-width: 0" in rule
    assert "flex: 1" in rule
