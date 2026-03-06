"""Compare DOM trees using traversal-based structural shingling.

Approach — three complementary shingle families, all **tag-only** (attribute
keys are ignored so that two sites on the same CMS but with different themes
still match on their shared tag hierarchy):

1. **Subtree shingles** — Bounded-depth (2, 3, 4) pre-order serialization
   at every node.  Captures *what* structural patterns exist.

2. **Root-path shingles** — Tag path from root to each node (last 3 hops).
   Captures *where* in the hierarchy a tag appears.

3. **Sibling-window shingles** — Sliding window (size 3) over each node's
   children tags.  Captures sibling *ordering*.

All collected into **sets** (not multisets) → scale-invariant.
Final score = weighted Jaccard across families.
"""
from __future__ import annotations

from utils.dom_tree import DOMNode


# ---------------------------------------------------------------------------
# 1. Subtree shingles (bounded-depth pre-order, tag-only)
# ---------------------------------------------------------------------------

def _serialize(node: DOMNode, max_depth: int, depth: int) -> str:
    tag = node.tag
    if node.tag == "#text" or depth >= max_depth or not node.children:
        return tag
    children_str = ";".join(
        _serialize(c, max_depth, depth + 1) for c in node.children
    )
    return f"{tag}{{{children_str}}}"


def _collect_subtree_shingles(node: DOMNode, max_depth: int = 3) -> set:
    shingles = {_serialize(node, max_depth, 0)}
    for child in node.children:
        shingles |= _collect_subtree_shingles(child, max_depth)
    return shingles


# ---------------------------------------------------------------------------
# 2. Root-path shingles (tag-only, last N hops)
# ---------------------------------------------------------------------------

def _collect_root_paths(node: DOMNode, path: tuple = (), max_hops: int = 3) -> set:
    current_path = path + (node.tag,)
    trimmed = current_path[-max_hops:]
    paths = {"->".join(trimmed)}
    for child in node.children:
        paths |= _collect_root_paths(child, current_path, max_hops)
    return paths


# ---------------------------------------------------------------------------
# 3. Sibling-window shingles (tag-only)
# ---------------------------------------------------------------------------

def _collect_sibling_windows(node: DOMNode, window: int = 3) -> set:
    shingles = set()
    if len(node.children) >= window:
        child_tags = [c.tag for c in node.children]
        for i in range(len(child_tags) - window + 1):
            shingles.add("|".join(child_tags[i:i + window]))
    for child in node.children:
        shingles |= _collect_sibling_windows(child, window)
    return shingles


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

WEIGHTS = {
    "subtree_d2": 3,
    "subtree_d3": 1,
    "subtree_d4": 0,    # too specific — content divergence hurts
    "root_path":  4,    # strongest signal — where tags sit in the hierarchy
    "sibling":    3,    # strong — sibling ordering is CMS-characteristic
}


def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def tree_similarity(a: DOMNode, b: DOMNode) -> float:
    """Weighted Jaccard across multiple traversal-based shingle families."""
    families_a = {
        "subtree_d2": _collect_subtree_shingles(a, max_depth=2),
        "subtree_d3": _collect_subtree_shingles(a, max_depth=3),
        "subtree_d4": _collect_subtree_shingles(a, max_depth=4),
        "root_path":  _collect_root_paths(a),
        "sibling":    _collect_sibling_windows(a),
    }
    families_b = {
        "subtree_d2": _collect_subtree_shingles(b, max_depth=2),
        "subtree_d3": _collect_subtree_shingles(b, max_depth=3),
        "subtree_d4": _collect_subtree_shingles(b, max_depth=4),
        "root_path":  _collect_root_paths(b),
        "sibling":    _collect_sibling_windows(b),
    }

    total_score = 0.0
    total_weight = 0.0
    for name, w in WEIGHTS.items():
        j = _jaccard(families_a[name], families_b[name])
        total_score += j * w
        total_weight += w

    return total_score / total_weight if total_weight > 0 else 0.0
