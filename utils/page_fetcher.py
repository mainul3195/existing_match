from bs4 import BeautifulSoup


def _fetch_with_playwright(url: str, timeout: int = 60000) -> str:
    """Fetch a page using Playwright Chromium.

    Uses headed mode since Akamai/advanced bot protection detects headless.
    The browser window opens briefly and closes after the page loads.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=timeout)
        html = page.content()
        browser.close()
    return html


def fetch_page(url: str, timeout: int = 60000) -> BeautifulSoup:
    """Fetch a webpage using Playwright and return a parsed BeautifulSoup object."""
    html = _fetch_with_playwright(url, timeout=timeout)
    soup = BeautifulSoup(html, "html.parser")

    # Detect bot protection / security challenge pages
    title = (soup.title.string or "") if soup.title else ""
    body_text = soup.get_text(separator=" ", strip=True)[:2000].lower()

    block_signals = [
        "access denied" in title.lower(),
        "blocked" in title.lower(),
        "just a moment" in title.lower(),  # Cloudflare
        "attention required" in title.lower(),  # Cloudflare
        "security check" in title.lower(),
        "performing security verification" in body_text,
        "security service to protect" in body_text,
        "verify you are human" in body_text,
        "enable javascript and cookies" in body_text,
        "ray id" in body_text and "cloudflare" in body_text,
        "checking your browser" in body_text,
        "ddos protection" in body_text,
    ]

    if any(block_signals):
        raise RuntimeError(
            "Blocked by bot/security protection (Cloudflare or similar). "
            "The site may require manual interaction or CAPTCHA solving."
        )

    # Detect broken/dead pages
    broken_signals = [
        "not a web page matching your entry" in body_text,
        "page not found" in title.lower(),
        "404 not found" in title.lower(),
        "this page isn't available" in body_text,
        "this site can't be reached" in body_text,
    ]

    if any(broken_signals):
        raise RuntimeError("Broken or dead page — content not available.")

    return soup
