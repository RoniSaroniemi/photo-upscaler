# browser-navigate

Navigate websites, take screenshots, and interact with web pages using Playwright (headless Chromium).

## When to Use

- **Competitor research** — screenshot competitor sites, capture pricing pages, analyze UI patterns
- **Visual verification** — capture your own site's UI to verify layout, styling, and flow
- **E2E testing** — navigate through a user flow (upload, click, submit) and verify each step
- **Web scraping** — extract content from pages that require JavaScript rendering

## Quick Screenshot

```python
python3 << 'EOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto("https://example.com", timeout=20000)
    page.wait_for_load_state("networkidle", timeout=15000)
    page.screenshot(path="/tmp/screenshot.png", full_page=False)
    browser.close()
EOF
```

Then read the screenshot: `Read /tmp/screenshot.png`

## Multi-Page Navigation

```python
python3 << 'EOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    # Page 1
    page.goto("https://example.com")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/tmp/page1.png")

    # Click a link and capture next page
    page.click("a:text('Pricing')")
    page.wait_for_load_state("networkidle")
    page.screenshot(path="/tmp/page2.png")

    browser.close()
EOF
```

## Interact with Forms

```python
python3 << 'EOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("https://example.com/upload")
    page.wait_for_load_state("networkidle")

    # Fill a form
    page.fill("input[name='email']", "test@example.com")

    # Upload a file
    page.set_input_files("input[type='file']", "/path/to/image.jpg")

    # Click submit
    page.click("button[type='submit']")
    page.wait_for_load_state("networkidle")

    # Capture result
    page.screenshot(path="/tmp/result.png")
    browser.close()
EOF
```

## Verify UI Elements

```python
python3 << 'EOF'
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    page.goto("http://localhost:3000")
    page.wait_for_load_state("networkidle")

    # Check element exists
    assert page.query_selector("h1"), "Missing h1"
    assert page.query_selector("button#upload"), "Missing upload button"

    # Check text content
    title = page.text_content("h1")
    assert "Upscale" in title, f"Unexpected title: {title}"

    # Check element count
    cards = page.query_selector_all(".pricing-card")
    assert len(cards) >= 1, "No pricing cards found"

    print("All UI checks passed")
    browser.close()
EOF
```

## Notes

- **Headless only** — runs without a display, suitable for agent sessions and CI
- **Parallel-safe** — multiple agents can run Playwright simultaneously (separate browser instances)
- **Screenshots are viewable** — use the `Read` tool on PNG files to see them
- **Timeouts** — set reasonable timeouts (15-20s for page load, 30s for interactions). Some sites are slow or geo-blocked.
- **Cookie popups** — many sites show cookie consent that blocks content. Either dismiss it (`page.click("button:text('Accept')")`) or ignore it.
- **Installed at** — Chromium browser cached at `~/Library/Caches/ms-playwright/`
