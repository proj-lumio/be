"""Website text extraction via httpx + stdlib HTMLParser."""

import logging
import re
from html.parser import HTMLParser

import httpx

logger = logging.getLogger(__name__)

SCRAPE_TIMEOUT = 15
MAX_CONTENT_SIZE = 500_000


class _TextExtractor(HTMLParser):
    """Strips HTML tags, keeps visible text."""

    SKIP_TAGS = {"script", "style", "noscript", "svg", "head"}

    def __init__(self):
        super().__init__()
        self._parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag.lower() in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag.lower() in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0:
            self._parts.append(data)

    def get_text(self) -> str:
        raw = " ".join(self._parts)
        return re.sub(r"\s+", " ", raw).strip()


async def scrape_website(url: str) -> str:
    """Fetch URL and extract visible text.

    Raises ValueError on failure with a descriptive message.
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LumioBot/1.0)",
        "Accept": "text/html",
    }

    try:
        async with httpx.AsyncClient(timeout=SCRAPE_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(url, headers=headers)
    except httpx.TimeoutException:
        raise ValueError("Website took too long to respond")
    except httpx.ConnectError:
        raise ValueError("Could not reach website")
    except httpx.RequestError as e:
        raise ValueError(f"Request failed: {e}")

    if resp.status_code != 200:
        raise ValueError(f"Website returned HTTP {resp.status_code}")

    content_type = resp.headers.get("content-type", "")
    if "text/html" not in content_type and "text/plain" not in content_type:
        raise ValueError(f"Expected HTML, got {content_type}")

    body = resp.text
    if len(body) > MAX_CONTENT_SIZE:
        body = body[:MAX_CONTENT_SIZE]

    extractor = _TextExtractor()
    extractor.feed(body)
    text = extractor.get_text()

    if not text:
        raise ValueError("No text content found on the page")

    return text
