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


ASSET_REF = re.compile(r'(?:href|src)="/(style\.css|theme\.js)\?v=([\w.-]+)"')


def test_page_loads_stylesheet_and_deferred_theme_js(themed):
    _, html = themed
    assert re.search(r'<link rel="stylesheet" href="/style\.css\?v=[\w.-]+" />', html)
    assert re.search(r'<script defer src="/theme\.js\?v=[\w.-]+"></script>', html)


def test_shared_assets_carry_one_cache_busting_version():
    # Every page depends on style.css; a stale cached copy after a deploy would
    # pair new markup with old styles. Bump ?v= on every page when they change.
    versions = {v for name in THEMED for _, v in ASSET_REF.findall(page_html(name))}
    assert len(versions) == 1, versions


@pytest.mark.parametrize(
    "path", ["/", "/getip", "/cidr", "/cron", "/up", "/impressum.html", "/datenschutz.html", "/privacy.html"]
)
def test_routes_serve_themed_pages_and_their_assets(client, path):
    res = client.get(path, headers={"User-Agent": "Mozilla/5.0"})
    assert res.status_code == 200
    assert 'class="theme-toggle"' in res.text
    refs = ASSET_REF.findall(res.text)
    assert sorted(asset for asset, _ in refs) == ["style.css", "theme.js"]
    for asset, version in refs:
        assert client.get(f"/{asset}?v={version}").status_code == 200


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
    assert len(THEMED) == 8


def test_cidr_prefix_input_can_shrink_inside_its_wrapper():
    # A flex child keeps its intrinsic width unless min-width is lifted, which
    # would push the prefix field past its column (WCAG 1.4.10 Reflow).
    css = STYLE_BLOCK.findall(page_html("cidr.html"))[0]
    rule = css.split(".prefix-input-wrap input {")[1].split("}")[0]
    assert "min-width: 0" in rule
    assert "flex: 1" in rule


CRON_IDS = (
    "cron-form",
    "flavour-select",
    "expr-input",
    "field-hint",
    "expr-error",
    "result",
    "explanation",
    "next-runs",
    "utc-note",
    "builder",
    "target-select",
    "convert-btn",
    "convert-result",
    "convert-output",
    "copy-btn",
    "copy-status",
    "convert-warnings",
    "convert-error",
)


def test_cron_keeps_script_hooks_and_labels():
    html = page_html("cron.html")
    for hook in CRON_IDS:
        assert f'id="{hook}"' in html, hook
    for label in ("flavour-select", "expr-input", "target-select"):
        assert f'<label for="{label}">' in html
    assert '<script src="/cron-logic.js"></script>' in html
    assert 'id="expr-error" aria-live="polite"' in html
    assert "All times are UTC." in html
    error_tag = html.split('id="expr-error"')[1].split(">")[0]
    assert 'role="alert"' not in error_tag
    assert 'id="copy-status" aria-live="polite"' in html


def test_cron_has_no_html_injection_sinks():
    sinks = ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function")
    for path in (STATIC / "cron.html", STATIC / "cron-logic.js"):
        text = path.read_text(encoding="utf-8")
        for sink in sinks:
            assert sink not in text, (path.name, sink)
        assert re.search(r"setTimeout\(\s*['\"`]", text) is None
    tag = re.search(r"<input[^>]*id=\"expr-input\"[^>]*>", page_html("cron.html")).group(0)
    assert 'maxlength="512"' in tag


def test_cron_result_is_not_live_and_status_region_is_separate():
    html = page_html("cron.html")
    result_tag = re.search(r'<div[^>]*id="result"[^>]*>', html).group(0)
    assert "aria-live" not in result_tag
    status = re.search(r'<p[^>]*id="result-status"[^>]*>', html).group(0)
    assert 'aria-live="polite"' in status
    assert "visually-hidden" in status
    inside = html.split('id="result"')[1].split('id="builder"')[0]
    assert 'id="result-status"' not in inside


def test_cron_error_region_stays_rendered_and_is_linked():
    html = page_html("cron.html")
    css = "".join(STYLE_BLOCK.findall(html))
    for rule in re.findall(r"([^{}]*)\{([^}]*)\}", css):
        if ".error" in rule[0] or "#expr-error" in rule[0]:
            assert "display: none" not in rule[1] and "display:none" not in rule[1], rule
    assert "aria-describedby" in html
    assert 'setAttribute("aria-invalid", "true")' in html


def test_cron_builder_and_convert_wiring():
    html = page_html("cron.html")
    for name in ("toBuilder", "fromBuilder", "builderModes", "convert"):
        assert name in html, name
    assert "<fieldset" in html or 'createElement("fieldset")' in html
    assert 'createElement("legend")' in html
    assert 'id="copy-status" aria-live="polite"' in html
    assert 'id="switch-warnings"' in html
    assert "arrives in the next update" not in html
    # Live regions are never nested: the convert wrapper is not itself live
    # and the copy status does not sit inside a hidden ancestor.
    wrapper = re.search(r'<div[^>]*id="convert-result"[^>]*>', html).group(0)
    assert "aria-live" not in wrapper and "hidden" not in wrapper
    status_ctx = html.split('id="copy-status"')[0].rsplit('id="convert-result"', 1)[1]
    status_ctx = re.sub(r'<div[^>]*id="convert-output-row"[^>]*>.*?</div>', "", status_ctx, flags=re.S)
    assert "hidden" not in status_ctx


def test_cron_flavour_switch_always_converts_and_announces_warnings():
    html = page_html("cron.html")
    body = html.split("function onFlavourChange()")[1].split("fillOptions(flavourSelect);")[0]
    assert "CronCalc.switchFlavour(" in body or "switchFlavour(" in body
    assert 'action === "reparse"' in body or '"reparse"' in body
    assert "Converted to " in body and "Warning: " in body
    run = html.split("function runConvert()")[1].split("function selectOutput()")[0]
    assert "Warning: " in run
    assert '" warning"' not in run  # no count-only announcement


def test_cron_builder_errors_are_per_field_and_do_not_move_the_result():
    html = page_html("cron.html")
    render = html.split("function renderField(")[1].split("function renderBuilder()")[0]
    assert '"-err"' in render and 'className = "error"' in render
    assert 'setAttribute("aria-live", "polite")' in render
    assert "aria-describedby" in render
    show = html.split("function showBuilderError(")[1].split("function applyModel(")[0]
    assert 'setAttribute("aria-invalid", "true")' in show
    assert "result.hidden" not in show and "exprInput" not in show
    assert "validity.badInput" in html and 'el.value === ""' in html


def test_cron_refused_switch_snaps_back_to_the_source_flavour():
    html = page_html("cron.html")
    body = html.split("function onFlavourChange()")[1].split("fillOptions(flavourSelect);")[0]
    assert "flavourSelect.value = previousFlavour" in body
    assert '"refused"' in body
    assert "The expression stays in " in body
    refuse = body.split("flavourSelect.value = previousFlavour")[1]
    assert "defaultModel" not in refuse and "result.hidden" not in refuse
    assert 'setAttribute("aria-invalid"' not in refuse
    assert "setTimeout(" in refuse  # message set in a later tick so the live region announces it


def test_cron_names_and_noscript_note():
    html = page_html("cron.html")
    controls = html.split("function modeControls(")[1].split("function renderField(")[0]
    assert '"Interval"' in controls and '"Every N"' not in controls
    assert 'aria-label", FIELD_LABELS[name] + " mode"' in html
    assert '<noscript><p class="note">This calculator needs JavaScript.</p></noscript>' in html


def test_cron_delayed_messages_are_cancellable():
    html = page_html("cron.html")
    assert "refusalTimer = setTimeout(" in html and "copyTimer = setTimeout(" in html
    update = html.split("function update()")[1].split("function ", 1)[0]
    assert "clearTimeout(refusalTimer)" in update
    assert "clearTimeout(copyTimer)" in html.split("function clearConvert()")[1].split("function ", 1)[0]


def test_cron_unparseable_text_does_not_block_a_flavour_switch():
    html = page_html("cron.html")
    body = html.split("function onFlavourChange()")[1].split("fillOptions(flavourSelect);")[0]
    for action in ('"empty"', '"reparse"', '"converted"', '"refused"'):
        assert action in body
    assert "convert(exprInput" not in body  # the page never converts directly on a switch


def test_cron_far_future_schedule_is_not_called_never():
    html = page_html("cron.html")
    assert "This expression never runs" not in html
    assert "No runs in the next 5 years." in html


def test_cron_changing_the_target_clears_a_stale_conversion():
    html = page_html("cron.html")
    assert 'targetSelect.addEventListener("change", clearConvert)' in html
