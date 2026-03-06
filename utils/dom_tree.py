from __future__ import annotations

from bs4 import BeautifulSoup, NavigableString, Tag


class DOMNode:
    """Represents a single node in a DOM tree."""

    def __init__(
        self,
        tag: str,
        attributes: dict | None = None,
        text: str | None = None,
        children: list[DOMNode] | None = None,
    ):
        self.tag = tag
        self.attributes = attributes or {}
        self.text = text
        self.children = children or []

    def to_dict(self) -> dict:
        """Serialize to a JSON-compatible dict."""
        data: dict = {"tag": self.tag}
        if self.attributes:
            data["attributes"] = self.attributes
        if self.text:
            data["text"] = self.text
        if self.children:
            data["children"] = [child.to_dict() for child in self.children]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> DOMNode:
        """Deserialize from a dict."""
        children = [cls.from_dict(c) for c in data.get("children", [])]
        return cls(
            tag=data["tag"],
            attributes=data.get("attributes", {}),
            text=data.get("text"),
            children=children,
        )

    def __repr__(self) -> str:
        parts = [f"<DOMNode tag={self.tag!r}"]
        if self.text:
            preview = self.text[:40] + ("..." if len(self.text) > 40 else "")
            parts.append(f" text={preview!r}")
        if self.children:
            parts.append(f" children={len(self.children)}")
        parts.append(">")
        return "".join(parts)


def _structural_signature(node: DOMNode) -> str:
    """Return a string representing the tag-only structure of a subtree.

    Two subtrees have the same structure if they share the same hierarchy of
    tags (and attribute *keys*), regardless of attribute values or text content.
    """
    parts = [node.tag]
    if node.attributes:
        parts.append("(" + ",".join(sorted(node.attributes.keys())) + ")")
    if node.children:
        child_sigs = [_structural_signature(c) for c in node.children]
        parts.append("{" + ";".join(child_sigs) + "}")
    return "".join(parts)


def deduplicate_children(node: DOMNode, max_same: int = 5) -> DOMNode:
    """Recursively limit siblings that share the same structure to *max_same*.

    For each parent, children are grouped by structural signature.  If more
    than *max_same* consecutive-or-scattered children share the same signature,
    only the first *max_same* are kept.
    """
    # Recurse first so subtrees are already pruned
    node.children = [deduplicate_children(c, max_same) for c in node.children]

    # Count and filter
    sig_counts: dict[str, int] = {}
    kept: list[DOMNode] = []
    for child in node.children:
        sig = _structural_signature(child)
        sig_counts[sig] = sig_counts.get(sig, 0) + 1
        if sig_counts[sig] <= max_same:
            kept.append(child)
    node.children = kept
    return node


def build_tree(soup: BeautifulSoup) -> DOMNode:
    """Recursively build a DOMNode tree from a BeautifulSoup object."""
    root_tag = soup.find("html")
    if root_tag and isinstance(root_tag, Tag):
        return _build_node(root_tag)
    # Fallback: wrap everything in a virtual root
    return _build_node(soup)


def _build_node(element) -> DOMNode:
    """Convert a single BS4 element into a DOMNode."""
    if isinstance(element, NavigableString):
        text = element.strip()
        return DOMNode(tag="#text", text=text if text else None)

    tag = element.name or "#document"
    attributes = {k: (v if isinstance(v, str) else " ".join(v))
                  for k, v in (element.attrs or {}).items()}

    children = []
    for child in element.children:
        if isinstance(child, NavigableString):
            text = child.strip()
            if text:
                children.append(DOMNode(tag="#text", text=text))
        elif isinstance(child, Tag):
            children.append(_build_node(child))

    return DOMNode(tag=tag, attributes=attributes, children=children)
