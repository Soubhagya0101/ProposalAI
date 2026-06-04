from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "public" / "index.html").read_text(encoding="utf-8")
SERVER = (ROOT / "server.py").read_text(encoding="utf-8")
SEO_DIR = ROOT / "public" / "seo"

SEO_SLUGS = ['free-ai-proposal-generator-for-freelancers', 'upwork-proposal-generator', 'web-design-proposal-generator', 'consulting-proposal-generator', 'examples/freelance-proposal-examples', 'examples/upwork-proposal-examples', 'templates/web-design-proposal-template', 'templates/consulting-proposal-template', 'guides/upwork-proposals-no-replies', 'guides/follow-up-after-proposal', 'tools/proposal-opener-checker', 'tools/scope-creep-checker']


def test_homepage_has_search_friendly_title_description_and_canonical():
    assert "Free Proposal Generator for Freelancers" in INDEX
    assert 'meta name="description"' in INDEX
    assert 'rel="canonical" href="https://proposalai-xv14.onrender.com/"' in INDEX


def test_seo_routes_are_registered_in_server():
    for slug in SEO_SLUGS:
        assert f'"/{slug}"' in SERVER
        assert f'"{slug.replace("/", "__")}.html"' in SERVER
    assert '"/sitemap.xml"' in SERVER
    assert '"/robots.txt"' in SERVER


def test_seo_pages_have_core_tags_internal_links_and_cta():
    for slug in SEO_SLUGS:
        html = (SEO_DIR / f"{slug.replace('/', '__')}.html").read_text(encoding="utf-8")
        assert "<title>" in html
        assert 'meta name="description"' in html
        assert f'rel="canonical" href="https://proposalai-xv14.onrender.com/{slug}"' in html
        assert 'application/ld+json' in html
        assert 'href="/"' in html
        assert "Paste a brief and draft one" in html
        assert "Related proposal resources" in html


def test_tool_pages_have_client_side_checkers():
    for slug in ["tools/proposal-opener-checker", "tools/scope-creep-checker"]:
        html = (SEO_DIR / f"{slug.replace('/', '__')}.html").read_text(encoding="utf-8")
        assert "textarea" in html
        assert "checkBtn" in html
        assert "Consider adding:" in html


def test_sitemap_lists_all_seo_urls():
    sitemap = (ROOT / "public" / "sitemap.xml").read_text(encoding="utf-8")
    for slug in SEO_SLUGS:
        assert f"https://proposalai-xv14.onrender.com/{slug}" in sitemap
    robots = (ROOT / "public" / "robots.txt").read_text(encoding="utf-8")
    assert "Sitemap: https://proposalai-xv14.onrender.com/sitemap.xml" in robots


def test_indexnow_key_file_is_served_by_server():
    assert 'INDEXNOW_KEY = "proposalai-indexnow-20260604"' in SERVER
    assert (ROOT / "public" / "proposalai-indexnow-20260604.txt").read_text(encoding="utf-8").strip() == "proposalai-indexnow-20260604"
    assert 'f"/{INDEXNOW_KEY}.txt"' in SERVER
