"""Compare DOM trees using multi-signal structural similarity.

Combines several complementary signals, each targeting a different aspect
of CMS/template similarity:

**Distribution signals** (content-invariant, scale-invariant):
1. Tag frequency cosine — proportion of each tag type
2. Parent->child tag-pair cosine — nesting patterns
3. Depth histogram cosine — tree shape profile
4. Attribute-key vocabulary Jaccard — data-*, aria-*, custom attrs

**Shingle signals** (structural topology):
5. Root-path shingles (last 3 hops) — where tags sit in hierarchy
6. Sibling-window shingles (size 3) — child ordering patterns

All combined via weighted average into a single [0, 1] score.
"""
from __future__ import annotations

import math
from collections import Counter

from utils.dom_tree import DOMNode


# ── Weights ──────────────────────────────────────────────────────────────

WEIGHTS = {
    "depth_profile_cosine": 12,  # tree shape — strongest, most consistent CMS discriminator
    "tag_freq_cosine":      10,  # tag distribution — reliably high for same-CMS matches
    "attr_key_jaccard":     6,   # attribute vocabulary — separates same-CMS from similar-looking sites
    "root_path":            4,   # hierarchy position — stable across same-platform sites
    "parent_child_cosine":  3,   # nesting patterns — useful but variable across sites
    "sibling":              2,   # sibling ordering
}


# ── Math helpers ─────────────────────────────────────────────────────────

def _jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def _cosine(counter_a: Counter, counter_b: Counter) -> float:
    """Cosine similarity between two Counter objects."""
    if not counter_a or not counter_b:
        return 0.0
    keys = set(counter_a.keys()) | set(counter_b.keys())
    dot = sum(counter_a.get(k, 0) * counter_b.get(k, 0) for k in keys)
    mag_a = math.sqrt(sum(v * v for v in counter_a.values()))
    mag_b = math.sqrt(sum(v * v for v in counter_b.values()))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


# ── Distribution signals ────────────────────────────────────────────────

def _count_tag_frequencies(node: DOMNode) -> Counter:
    """Count occurrences of each tag in the tree (ignoring #text)."""
    counter = Counter()

    def _walk(n: DOMNode):
        if n.tag != "#text":
            counter[n.tag] += 1
        for child in n.children:
            _walk(child)

    _walk(node)
    return counter


def _count_parent_child_pairs(node: DOMNode) -> Counter:
    """Count (parent_tag, child_tag) pairs across the tree."""
    counter = Counter()

    def _walk(n: DOMNode):
        for child in n.children:
            if child.tag != "#text":
                counter[(n.tag, child.tag)] += 1
            _walk(child)

    _walk(node)
    return counter


def _depth_histogram(node: DOMNode) -> Counter:
    """Count nodes at each depth level."""
    counter = Counter()

    def _walk(n: DOMNode, depth: int):
        if n.tag != "#text":
            counter[depth] += 1
        for child in n.children:
            _walk(child, depth + 1)

    _walk(node, 0)
    return counter


def _collect_attribute_keys(node: DOMNode) -> set[str]:
    """Collect the set of all attribute keys used in the tree.

    Ignores 'class' and 'id' (handled separately), focuses on
    structural attributes like data-*, aria-*, role, etc.
    """
    keys = set()

    def _walk(n: DOMNode):
        for attr_key in n.attributes:
            if attr_key not in ("class", "id"):
                keys.add(attr_key)
        for child in n.children:
            _walk(child)

    _walk(node)
    return keys


# ── Shingle signals ─────────────────────────────────────────────────────


def _collect_root_paths(node: DOMNode, path: tuple = (), max_hops: int = 3) -> set:
    current_path = path + (node.tag,)
    trimmed = current_path[-max_hops:]
    paths = {"->".join(trimmed)}
    for child in node.children:
        paths |= _collect_root_paths(child, current_path, max_hops)
    return paths


def _collect_sibling_windows(node: DOMNode, window: int = 3) -> set:
    shingles = set()
    if len(node.children) >= window:
        child_tags = [c.tag for c in node.children]
        for i in range(len(child_tags) - window + 1):
            shingles.add("|".join(child_tags[i:i + window]))
    for child in node.children:
        shingles |= _collect_sibling_windows(child, window)
    return shingles


# ── Feature extraction ───────────────────────────────────────────────────

def _extract_features(node: DOMNode) -> dict:
    """Extract all feature families from a tree."""
    return {
        "tag_freq":       _count_tag_frequencies(node),
        "parent_child":   _count_parent_child_pairs(node),
        "depth_profile":  _depth_histogram(node),
        "attr_keys":      _collect_attribute_keys(node),
        "root_path":      _collect_root_paths(node),
        "sibling":        _collect_sibling_windows(node),
    }


def _compute_signal_scores(fa: dict, fb: dict) -> dict:
    """Compute individual signal scores between two feature sets."""
    return {
        "tag_freq_cosine":      _cosine(fa["tag_freq"], fb["tag_freq"]),
        "parent_child_cosine":  _cosine(fa["parent_child"], fb["parent_child"]),
        "depth_profile_cosine": _cosine(fa["depth_profile"], fb["depth_profile"]),
        "attr_key_jaccard":     _jaccard(fa["attr_keys"], fb["attr_keys"]),
        "root_path":            _jaccard(fa["root_path"], fb["root_path"]),
        "sibling":              _jaccard(fa["sibling"], fb["sibling"]),
    }


def _weighted_average(scores: dict) -> float:
    """Compute weighted average of signal scores."""
    total_score = 0.0
    total_weight = 0.0
    for name, w in WEIGHTS.items():
        total_score += scores[name] * w
        total_weight += w
    return total_score / total_weight if total_weight > 0 else 0.0


# ── Public API ───────────────────────────────────────────────────────────

def compute_similarity(a: DOMNode, b: DOMNode) -> float:
    """Multi-signal structural similarity between two DOM trees.

    Returns a score in [0, 1].
    """
    fa = _extract_features(a)
    fb = _extract_features(b)
    scores = _compute_signal_scores(fa, fb)
    return _weighted_average(scores)


def compute_similarity_detailed(a: DOMNode, b: DOMNode) -> dict:
    """Like compute_similarity but returns individual signal scores for debugging."""
    fa = _extract_features(a)
    fb = _extract_features(b)
    scores = _compute_signal_scores(fa, fb)
    scores["_combined"] = _weighted_average(scores)
    scores["_weights"] = dict(WEIGHTS)
    return scores
