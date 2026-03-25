import re
from bs4 import BeautifulSoup, Comment

EVENT_HANDLER_RE = re.compile(r"^on\w+", re.IGNORECASE)
REMOVE_TAGS = {"script", "style", "noscript", "meta", "link", "header", "footer", "nav"}


def clean_html(soup: BeautifulSoup) -> BeautifulSoup:
    """Remove scripts, styles, comments, event handlers, and empty text nodes."""
    # Remove unwanted tags
    for tag in soup.find_all(REMOVE_TAGS):
        tag.decompose()

    # Remove HTML comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Remove inline event handlers
    for tag in soup.find_all(True):
        attrs_to_remove = [
            attr for attr in tag.attrs if EVENT_HANDLER_RE.match(attr)
        ]
        for attr in attrs_to_remove:
            del tag[attr]

    # Remove empty/whitespace-only text nodes
    for text_node in soup.find_all(string=True):
        if not text_node.strip():
            text_node.extract()

    return soup
