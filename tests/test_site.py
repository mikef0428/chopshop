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
            elif name == "srcset" and value:
                self.refs += [e.split()[0] for e in value.split(",") if e.strip()]


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
    for price in (
        "1 clip a day, free",
        "$2 per clip",
        "10 clips for $15",
        "30 clips for $36",
        "$9/month",
        "3 clips a day, 40 a month",
        "$19/month",
        "10 clips a day, 150 a month",
        "$149/month",
        "The first 50 subscribers keep their price for as long as they stay.",
    ):
        assert price in html, f"missing price {price}"
    assert "AutoClip" not in html
