from html.parser import HTMLParser
from pathlib import Path

SITE = Path(__file__).resolve().parents[1] / "site"


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.refs = []

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if name in ("href", "src") and value:
                self.refs.append(value)


def test_local_links_resolve():
    pages = sorted(SITE.glob("*.html"))
    assert pages, "site has no pages"
    for page in pages:
        parser = _Refs()
        parser.feed(page.read_text(encoding="utf-8"))
        for ref in parser.refs:
            if ref.startswith(("http", "mailto:", "#", "data:")):
                continue
            assert (SITE / ref.split("#")[0]).exists(), f"{page.name}: broken link {ref}"


def test_prices_and_branding():
    html = (SITE / "index.html").read_text(encoding="utf-8")
    for price in ("$2", "$15", "$36", "$9", "$19", "$149"):
        assert price in html, f"missing price {price}"
    assert "AutoClip" not in html
