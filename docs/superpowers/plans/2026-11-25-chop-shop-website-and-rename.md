# Chop Shop Website and Rename Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put a Chop Shop marketing website online that sells clips through Stripe Payment Links in founding-customer mode, rename the app's user-facing surface to Chop Shop, and let the app ingest Twitch VOD links.

**Architecture:** The website is static HTML and CSS in a new top-level `site/` folder with no server and no build step; every price and link comes from one `site/config.js`. Orders are taken by Stripe Payment Links (which collect the stream link as a checkout custom field) and fulfilled by the owner in the existing local app. The app keeps its `autoclip` package name and gains a `chopshop` command and Chop Shop branding.

**Tech Stack:** Plain HTML/CSS/vanilla JS for the site; existing Python 3.11 FastAPI + React/Tailwind app; pytest.

**Spec:** `docs/superpowers/specs/2026-11-25-chop-shop-service-design.md` (steps 3 and 4 of its "Order of work"). Step 5, self-serve, gets its own plan after founding mode has produced real throughput and pricing data. Copy and positioning come from the "Chop Shop Marketing Plan" and prices from the "Chop Shop Business Plan" documents; the values needed are copied below.

## Global Constraints

- Python package name `autoclip`, env vars `AUTOCLIP_*` and data folder `~/.autoclip` do not change.
- `LICENSE` and the original author's credit stay untouched.
- Never run `autoclip serve --reload`. Use the `api-test` launch config (port 8001, no worker) for manual checks.
- Never push to `origin`; the push remote is `fork`. Commit only when the owner asks.
- Python 3.11/3.12 only. Line length 100 (ruff).
- The site has no framework, no bundler and no new dependency.
- Site copy never promises views or virality, never names a competitor, and shows only clips the owner has permission to show.
- Brand: black background, gold accent, off-white text; logo and banner in `chopShop art/`.
- Prices (exact): Free 1 clip/day with end tag; $2 per clip; packs 10 for $15 and 30 for $36; Starter $9/month (3/day, 40/month); Pro $19/month (10/day, 150/month); Managed $149/month (max 10 customers). Free and Starter orders cover 60 minutes of stream; Pro and Managed 2 hours.
- Founding offer copy: "The first 50 subscribers keep their price for as long as they stay."

## Review Focus

1. A Stripe link is still a placeholder at launch → that buy button must not render as a working link; it shows "Coming soon" and the page still works.
2. `examples` in config is empty (true on day one) → the examples section is hidden entirely, not shown blank.
3. JavaScript disabled or `config.js` fails to load → headline, explanation, FAQ and contact email are still readable from the HTML.
4. Phone-width screen (360px) → no horizontal scroll, pricing cards stack, buttons are tappable.
5. A Twitch link that is a channel page or live stream, not a VOD → ingest refuses with a message saying a VOD link is needed, before any download starts.

---

### Task 1: Site skeleton, config and link check

**Files:**
- Create: `site/index.html`, `site/styles.css`, `site/config.js`, `site/main.js`, `site/assets/` (copy `Chop Shop logo.png` → `logo.png`, `Chop Shop banner v2.png` → `banner.png`)
- Create: `tests/test_site.py`
- Modify: `.claude/launch.json` (add config `site`: `.venv/Scripts/python.exe -m http.server 8080 --directory site`, port 8080)

**Interfaces:**
- Produces: `window.CHOPSHOP` in `site/config.js`:
  `{ contactEmail, discordUrl, freeClipUrl, links: { clip, pack10, pack30, starter, pro }, managedUrl, examples: [{ streamer, channelUrl, videoUrl }] }`.
  Unset values are the empty string. `main.js` reads it; later tasks only add markup.
- Produces: markup contract — any element with `data-link="<key>"` gets its `href` from config; with an empty value it becomes a disabled "Coming soon" control. An element with `data-requires="examples"` is removed when `examples` is empty.

- [ ] **Step 1: Write the failing test** in `tests/test_site.py`

```python
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
```

- [ ] **Step 2: Run** `.venv/Scripts/python.exe -m pytest tests/test_site.py -v` — expected: FAIL, "site has no pages".
- [ ] **Step 3: Create the files.** `index.html` holds all copy as real HTML (Review Focus 3) with sections `#why`, `#how`, `#examples` (`data-requires="examples"`), `#pricing`, `#faq`, and a footer. `main.js` implements the two `data-` contracts above and nothing else. Prices are written in the HTML; `config.js` holds links only.
- [ ] **Step 4: Run the test** — expected: PASS.
- [ ] **Step 5: Start the `site` preview** and confirm in the browser: with all links empty every buy button reads "Coming soon" (Review Focus 1), the examples section is absent (Review Focus 2), and no console errors.

### Task 2: Landing page copy and design

**Files:**
- Modify: `site/index.html`, `site/styles.css`

**Interfaces:**
- Consumes: Task 1's `data-link` and `data-requires` contracts.

- [ ] **Step 1: Research the "why short clips" facts.** Find three to four statistics about Shorts, Reels or TikTok reach from primary sources (platform press pages or official blogs), open each page, and record the figure, date and URL. A statistic that cannot be opened at a primary source is not used; the section then makes the argument without numbers.
- [ ] **Step 2: Write the copy** into `index.html`, using these fixed lines:
  - Headline: "Your stream already has the moments."
  - Subhead: "We cut them into Shorts, Reels and TikToks while you sleep. First clip every day is free."
  - Primary button: "Get my free clip" (`data-link="freeClipUrl"`).
  - How it works, three steps: "Send your stream link" / "We find and cut the best moments, with captions, titles and hashtags" / "Download and post".
  - Pricing: six tiers from Global Constraints; packs presented before subscriptions; Managed is "By invitation — ask us" (`data-link="managedUrl"`).
  - FAQ entries: who owns the clips (you do); how long it takes (within 24 hours); which platforms (YouTube and Twitch VOD links); music and game cutscenes can still be claimed on your uploads; what the end tag is; refunds (no-questions in the first 90 days); who runs this (one person and an AI, stated plainly).
  - Each statistic links to its source.
- [ ] **Step 3: Design pass.** Invoke the `impeccable` skill for the visual design within the brand in Global Constraints. Layout must work at 360px (Review Focus 4).
- [ ] **Step 4: Verify in the preview** at desktop and mobile width: no horizontal scroll, readable contrast, all in-page links land on their sections. Run `pytest tests/test_site.py` — expected: PASS.

### Task 3: Terms and privacy drafts

**Files:**
- Create: `site/terms.html`, `site/privacy.html`
- Modify: `site/index.html` (footer links)

- [ ] **Step 1: Write both pages**, each headed "Draft — not yet reviewed by a lawyer". Terms cover: you must own or control the content you submit; we may refuse and refund any order; refunds on request in the first 90 days; clips are deleted after 30 days; free clips carry an end tag; no guarantee of views. Privacy covers: what is collected (email, channel, stream links, payment handled by Stripe), where clips are stored, the 30-day deletion, and the contact email from config.
- [ ] **Step 2: Run** `pytest tests/test_site.py` — expected: PASS (footer links resolve).

### Task 4: Rename the user-facing surface to Chop Shop

**Files:**
- Modify: `pyproject.toml` (`[project.scripts]` add `chopshop = "autoclip.cli:app"`; description; `[project.urls]` to `https://github.com/mikef0428/autoclip`)
- Modify: `backend/autoclip/app.py` (FastAPI `title="Chop Shop"`, startup log line)
- Modify: `backend/autoclip/cli.py` (Typer `name`, help strings and printed messages that say "AutoClip")
- Modify: `frontend/index.html` (`<title>`), `frontend/src/App.tsx:25-27` (masthead wordmark: "Chop" + italic gold "Shop"), and user-visible "AutoClip" strings in `frontend/src/components/ClipPlayer.tsx`, `frontend/src/components/StreamLayoutEditor.tsx`
- Modify: `README.md` (title, intro, a "Fork of AutoClip by Jad Ghazi" credit line, clone URL), `docs/ARCHITECTURE.md` title line
- Test: `tests/test_api.py`

Not changed: module docstrings and comments, `paths.py`, env var names, the error text matched by `tests/test_db.py:46`, upstream `Issues` references inside code comments.

- [ ] **Step 1: Write the failing test** in `tests/test_api.py`, using that file's existing client fixture:

```python
def test_api_is_branded_chop_shop(client):
    assert client.get("/openapi.json").json()["info"]["title"] == "Chop Shop"
```

- [ ] **Step 2: Run it** — expected: FAIL, title is "AutoClip".
- [ ] **Step 3: Make the edits** listed under Files.
- [ ] **Step 4: Run** `.venv/Scripts/python.exe -m pytest -m "not slow and not e2e and not golden"` — expected: PASS. Run `npm --prefix frontend run build` — expected: builds with no type errors.
- [ ] **Step 5: Reinstall and check the command:** `uv pip install -e .` then `.venv/Scripts/chopshop.exe --help` — expected: help text titled Chop Shop; `autoclip --help` still works.
- [ ] **Step 6: Check the UI** with the `api-test` preview on port 8001: masthead reads "Chop Shop", tab title reads "Chop Shop".

### Task 5: Accept Twitch VOD links

**Files:**
- Modify: `backend/autoclip/pipeline/ingest.py` (`is_youtube_url` at line 56 and its callers)
- Modify: `backend/autoclip/api/sources.py:134` (the `/youtube` ingest route's validation message), `frontend/src/pages/Ingest.tsx:86` (placeholder text)
- Test: `tests/test_ingest_sections.py`

**Interfaces:**
- Produces: `is_supported_url(url: str) -> bool` and `twitch_vod_id(url: str) -> str | None` in `ingest.py`. `is_youtube_url` stays as-is for the YouTube-only paths (bot-check hints, popular moments).

- [ ] **Step 1: Write the failing tests**

```python
from autoclip.pipeline import ingest


def test_twitch_vod_links_are_supported():
    assert ingest.is_supported_url("https://www.twitch.tv/videos/2301234567")
    assert ingest.twitch_vod_id("https://www.twitch.tv/videos/2301234567") == "2301234567"
    assert ingest.twitch_vod_id("https://m.twitch.tv/videos/2301234567?t=1h2m") == "2301234567"


def test_twitch_channel_and_live_links_are_refused():
    assert ingest.twitch_vod_id("https://www.twitch.tv/somestreamer") is None
    assert not ingest.is_supported_url("https://www.twitch.tv/somestreamer")
    assert not ingest.is_supported_url("https://example.com/videos/1")


def test_youtube_links_still_supported():
    assert ingest.is_supported_url("https://youtu.be/dQw4w9WgXcQ")
```

- [ ] **Step 2: Run them** — expected: FAIL, `is_supported_url` not defined.
- [ ] **Step 3: Implement.** Twitch hosts: `twitch.tv`, `www.twitch.tv`, `m.twitch.tv`; a VOD path is `/videos/<digits>`. The URL-ingest entry point accepts any `is_supported_url`; a Twitch non-VOD link raises `IngestError("That is a Twitch channel or live link.", hint="Paste the link to a past broadcast, like twitch.tv/videos/123456789.")` before yt-dlp is called (Review Focus 5). Twitch sources are stored with `type="youtube"`; add the comment `# ponytail: 'youtube' means "fetched by yt-dlp"; add a 'twitch' type with a table-rebuild migration when the self-serve site needs to tell them apart.` Popular-moments lookup returns an empty list for Twitch links.
- [ ] **Step 4: Run** `pytest tests/test_ingest_sections.py -v` — expected: PASS.
- [ ] **Step 5: Real-world check.** With the owner's go-ahead (it starts a real job on the main server), ingest one public Twitch VOD with a 5-minute section through the UI and confirm clips come out. If yt-dlp cannot cut sections from Twitch, record that in the task notes and fall back to full download plus the existing trim.

### Task 6: Launch checklist for the owner

**Files:**
- Create: `site/README.md`

- [ ] **Step 1: Write the checklist**, in order, with the exact fields to fill:
  1. Stripe: create five products with the prices in Global Constraints (two recurring, three one-time; the single clip with adjustable quantity). For each, create a Payment Link with two required custom text fields, "Your channel link" and "Stream link (YouTube or Twitch VOD)", and tick the terms-of-service consent box. Paste the five URLs into `site/config.js`.
  2. Free clips: create a Discord server or a form for free-clip requests; paste its URL as `freeClipUrl`.
  3. Hosting: deploy the `site/` folder to a static host (Cloudflare Pages: connect the `fork` repository, build command empty, output directory `site`).
  4. Domain: buy it and point it at the static host.
  5. Examples: add `{ streamer, channelUrl, videoUrl }` entries to `config.js` only for clips whose owner agreed in writing.
  6. Replace the "Draft" banner on terms and privacy after review.
- [ ] **Step 2: Run** the full fast test suite once more — expected: PASS.
