"""The analytics snippet is hand-copied into every page, so guard it here.

The checks are deliberately about *shape*, not exact markup: the endpoints must
stay relative (first-party, no third-party request), the noscript pixel must
carry the page's own path so JS and no-JS views land on the same entry, and no
page may reach out to GoatCounter's CDN.
"""

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "static"

# Page file -> the path it is served under, which is what the pixel must report.
PAGES = {
    "index.html": "/",
    "getip.html": "/getip",
    "cidr.html": "/cidr",
    "up.html": "/up",
    "impressum.html": "/impressum.html",
    "datenschutz.html": "/datenschutz.html",
    "privacy.html": "/privacy.html",
}


@pytest.fixture(params=sorted(PAGES), ids=sorted(PAGES))
def page(request):
    return request.param, (STATIC / request.param).read_text(encoding="utf-8")


def test_every_static_page_is_covered():
    """A new page must be added to PAGES, not silently skipped."""
    on_disk = {p.name for p in STATIC.glob("*.html")}
    assert on_disk == set(PAGES)


def test_page_loads_tracker(page):
    _, html = page
    assert '<script data-goatcounter="/count" async src="/count.js"></script>' in html


def test_noscript_pixel_uses_own_path(page):
    name, html = page
    assert f'<img src="/count?p={PAGES[name]}"' in html


def test_noscript_pixel_is_decorative(page):
    _, html = page
    pixel = html.split('<img src="/count?p=')[1].split(">")[0]
    assert 'alt=""' in pixel
    assert 'aria-hidden="true"' in pixel
    # Out of flow, so it cannot shift the layout.
    assert "position:absolute" in pixel


def test_no_third_party_analytics_host(page):
    _, html = page
    assert "gc.zgo.at" not in html
    assert "goatcounter.com" not in html


def test_privacy_policies_document_analytics():
    for name in ("datenschutz.html", "privacy.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert "GoatCounter" in html
        assert "TDDDG" in html


def test_privacy_policies_offer_a_working_opt_out():
    """Opt-out per Art. 21 GDPR, driven by the localStorage key count.js reads.

    Not count.js's own #toggle-goatcounter link: that acts at script-load time,
    so the hash it leaves in the URL re-toggles tracking on every refresh.
    """
    for name in ("datenschutz.html", "privacy.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert 'id="optout-toggle"' in html
        assert '"skipgc"' in html
        assert 'href="#toggle-goatcounter"' not in html


def test_dnt_and_gpc_are_honoured_in_nginx():
    """Both policies promise the signal is honoured; keep nginx able to deliver.

    This is the only opt-out reachable without JavaScript, so it must cover the
    <noscript> pixel — i.e. live in nginx, not in count.js.
    """
    conf = (ROOT / "nginx.docker.conf").read_text(encoding="utf-8")
    assert "map $http_dnt$http_sec_gpc $analytics_optout" in conf
    # Every location that can record a pageview must consult it.
    assert conf.count("location = /count {") == conf.count("if ($analytics_optout)")

    for name in ("datenschutz.html", "privacy.html"):
        html = (STATIC / name).read_text(encoding="utf-8")
        assert "GPC" in html and ("DNT" in html or "Do Not Track" in html)
