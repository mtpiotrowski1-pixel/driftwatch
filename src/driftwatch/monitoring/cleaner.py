"""Reduce captured HTML to its stable, content-bearing core.

Remove non-content elements and explicitly volatile attributes. Visible values
and document URLs are preserved: an order number and a Unix timestamp can have
the same shape, so guessing which one is noise would hide real changes. Sites
can exclude genuinely volatile regions using ``ignore_selectors``.
"""

from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup, Comment

# Elements that are structurally present but never carry watched content.
NON_CONTENT_TAGS: frozenset[str] = frozenset(
    {
        "script",
        "style",
        "noscript",
        "template",
        "svg",
        "canvas",
        "nav",
        "header",
        "footer",
        "aside",
        "form",
        "iframe",
        "object",
        "embed",
        "video",
        "audio",
        "button",
        "select",
    }
)

# Attributes whose values churn between renders without reflecting content.
VOLATILE_ATTRIBUTES: frozenset[str] = frozenset(
    {
        "nonce",
        "data-reactid",
        "data-react-checksum",
        "data-timestamp",
        "data-nonce",
        "data-request-id",
        "data-session",
        "data-csrf",
        "jscontroller",
        "jsaction",
    }
)


def volatile_value_patterns() -> list[str]:
    """No value-pattern guessing is applied to visible content."""
    return []


def clean_dom(
    html: str,
    *,
    ignore_selectors: list[str] | None = None,
    base_url: str | None = None,
) -> str:
    """Return content HTML with chrome and volatile tokens removed.

    ``ignore_selectors`` is an optional list of CSS selectors (for example
    ``[".cookie-banner", "#ads"]``) removed in addition to the built-in
    non-content tags, letting a site exclude regions that are noise for it.
    """
    if not html or not html.strip():
        return ""

    soup = BeautifulSoup(html, "html.parser")

    # The capture adapter supplies document.baseURI, already including redirects
    # and <base>. Resolving <base> again could duplicate a relative directory.
    if base_url is not None:
        for anchor in soup.find_all("a", href=True):
            href = anchor.get("href")
            if isinstance(href, str) and not href.startswith("#"):
                anchor["href"] = urljoin(base_url, href)
    for base in soup.find_all("base"):
        base.decompose()

    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    for element in soup.find_all(NON_CONTENT_TAGS):
        element.decompose()

    for selector in ignore_selectors or []:
        for element in soup.select(selector):
            element.decompose()

    for element in soup.find_all(True):
        for attribute in list(element.attrs):
            if attribute in VOLATILE_ATTRIBUTES or attribute.startswith("data-v-"):
                del element[attribute]

    body = soup.body or soup
    return body.decode()
