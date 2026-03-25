"""Subtree matching between DOM trees using three complementary strategies.

Implements the algorithms described in the design doc:

1. **Multi-Depth Hashing** — For each node, compute depth-bounded hashes
   (d=0..k). Two nodes that share the same hash at depth d are structurally
   identical up to d levels.  The pair with the highest matching depth is the
   best match.  Good for batch/indexed comparison across many trees.

2. **Simple Tree Matching (STM)** — DP-based recursive algorithm that scores
   how many nodes two subtrees share (order-preserving child alignment).
   Naturally handles leaf-level differences because unmatched leaves simply
   don't contribute rather than ruining a hash.

3. **Tag-Path Anchoring** — Narrows the search space by only comparing nodes
   that sit at the same root-to-node tag path (e.g. ``html>body>div>ul``).
   Pages sharing a template will have many overlapping paths, so this
   dramatically reduces the number of candidate pairs fed into STM.

The recommended combined approach for same-template pages:
   Tag-path anchoring → STM on candidate pairs → highest-scoring pair.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

from utils.dom_tree import DOMNode


# Data structures


@dataclass
class MatchResult:
    """Describes the best subtree match found between two trees."""

    node_a: DOMNode
    node_b: DOMNode
    score: int  # number of matched nodes (STM score)
    depth: int  # how many levels the match extends
    path: str  # tag-path at which the match was anchored
    size_a: int = 0  # number of nodes in subtree A
    size_b: int = 0  # number of nodes in subtree B

    @property
    def similarity(self) -> float:
        """Normalised similarity in [0, 1]."""
        total = self.size_a + self.size_b
        if total == 0:
            return 0.0
        # Dice-style: 2 * matched / (|A| + |B|)
        return 2 * self.score / total


# Helpers


def _subtree_size(node: DOMNode) -> int:
    """Count number of nodes in a subtree (including root)."""
    return 1 + sum(_subtree_size(c) for c in node.children)


def _tag_path(node: DOMNode, path: tuple[str, ...] = ()) -> str:
    """Root-to-node path as ``html>body>div>...`` string."""
    return ">".join(path + (node.tag,))


# 1. Multi-Depth Hashing


def _compute_depth_hashes(
    node: DOMNode,
    max_depth: int,
) -> dict[DOMNode, list[str]]:
    """Return {node: [hash_d0, hash_d1, ..., hash_dk]} for every node.

    hash_d0 = hash(tagName)
    hash_di = hash(tagName + children's hash_d(i-1)s)
    """
    result: dict[int, list[str]] = {}  # id(node) → hashes
    node_map: dict[int, DOMNode] = {}  # id(node) → node

    def _walk(n: DOMNode) -> list[str]:
        hashes: list[str] = []
        for d in range(max_depth + 1):
            if d == 0:
                h = hashlib.md5(n.tag.encode(), usedforsecurity=False).hexdigest()
            else:
                child_parts = []
                for c in n.children:
                    c_hashes = result.get(id(c))
                    if c_hashes is None:
                        c_hashes = _walk(c)
                    # Use child's hash at depth d-1
                    idx = min(d - 1, len(c_hashes) - 1)
                    child_parts.append(c_hashes[idx])
                combined = n.tag + "|" + ",".join(child_parts)
                h = hashlib.md5(combined.encode(), usedforsecurity=False).hexdigest()
            hashes.append(h)
        result[id(n)] = hashes
        node_map[id(n)] = n
        return hashes

    _walk(node)
    # Re-key by actual node objects
    return {node_map[nid]: hashes for nid, hashes in result.items()}


def multi_depth_match(
    tree_a: DOMNode,
    tree_b: DOMNode,
    max_depth: int = 6,
) -> Optional[MatchResult]:
    """Find the node pair sharing the highest matching depth.

    Returns ``None`` if no tag-level match exists at all.
    """
    hashes_a = _compute_depth_hashes(tree_a, max_depth)
    hashes_b = _compute_depth_hashes(tree_b, max_depth)

    # Build inverted index: (depth, hash) → [nodes_from_B]
    index_b: dict[tuple[int, str], list[DOMNode]] = {}
    for node, hlist in hashes_b.items():
        for d, h in enumerate(hlist):
            index_b.setdefault((d, h), []).append(node)

    best_depth = -1
    best_pair: Optional[tuple[DOMNode, DOMNode]] = None

    for node_a, hlist_a in hashes_a.items():
        for d in range(len(hlist_a) - 1, -1, -1):  # scan deepest first
            if d <= best_depth:
                break  # can't beat current best from this node
            matches = index_b.get((d, hlist_a[d]))
            if matches:
                best_depth = d
                best_pair = (node_a, matches[0])
                break

    if best_pair is None:
        return None

    na, nb = best_pair
    return MatchResult(
        node_a=na,
        node_b=nb,
        score=best_depth + 1,  # depth is 0-indexed
        depth=best_depth,
        path=na.tag,
        size_a=_subtree_size(na),
        size_b=_subtree_size(nb),
    )


# 2. Simple Tree Matching (STM)


def _stm_score(node_a: DOMNode, node_b: DOMNode, memo: dict) -> int:
    """Compute Simple Tree Matching score between two subtrees.

    Score = number of matched nodes (order-preserving child alignment).

    Uses memoisation keyed on ``(id(node_a), id(node_b))``.
    """
    key = (id(node_a), id(node_b))
    if key in memo:
        return memo[key]

    if node_a.tag != node_b.tag:
        memo[key] = 0
        return 0

    m = len(node_a.children)
    n = len(node_b.children)

    if m == 0 or n == 0:
        # Leaf or no-child match — just the root itself
        memo[key] = 1
        return 1

    # DP table for order-preserving child alignment
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            dp[i][j] = max(
                dp[i - 1][j],
                dp[i][j - 1],
                dp[i - 1][j - 1]
                + _stm_score(
                    node_a.children[i - 1],
                    node_b.children[j - 1],
                    memo,
                ),
            )

    score = 1 + dp[m][n]  # +1 for matching root
    memo[key] = score
    return score


def stm_match(node_a: DOMNode, node_b: DOMNode) -> int:
    """Public API: run STM and return the match score."""
    memo: dict[tuple[int, int], int] = {}
    return _stm_score(node_a, node_b, memo)


def _stm_aligned_depth(node_a: DOMNode, node_b: DOMNode, memo: dict) -> int:
    """Return the maximum depth to which two subtrees remain aligned."""
    if node_a.tag != node_b.tag:
        return 0

    if not node_a.children or not node_b.children:
        return 1

    # Find best-matching child pair and recurse
    max_child_depth = 0
    for ca in node_a.children:
        for cb in node_b.children:
            if ca.tag == cb.tag:
                key = (id(ca), id(cb))
                if key not in memo:
                    memo[key] = _stm_aligned_depth(ca, cb, memo)
                max_child_depth = max(max_child_depth, memo[key])

    return 1 + max_child_depth


# 3. Tag-Path Anchoring


def _collect_nodes_by_path(
    node: DOMNode,
    path: tuple[str, ...] = (),
) -> dict[str, list[DOMNode]]:
    """Walk the tree and group nodes by their root-to-node tag path."""
    current_path = path + (node.tag,)
    path_str = ">".join(current_path)

    result: dict[str, list[DOMNode]] = {path_str: [node]}

    for child in node.children:
        child_paths = _collect_nodes_by_path(child, current_path)
        for p, nodes in child_paths.items():
            result.setdefault(p, []).extend(nodes)

    return result


# Combined: Tag-Path Anchoring → STM → Best Pair


def find_best_subtree_match(
    tree_a: DOMNode,
    tree_b: DOMNode,
    min_size: int = 3,
    top_k: int = 5,
) -> list[MatchResult]:
    """Find the best matching subtrees between two trees.

    Strategy:
    1. Index nodes in both trees by tag-path.
    2. For each shared path, run STM on every candidate pair.
    3. Return the *top_k* highest-scoring pairs.

    Parameters
    ----------
    tree_a, tree_b : DOMNode
        Root nodes of the two DOM trees to compare.
    min_size : int
        Ignore subtrees with fewer nodes than this (avoids noisy
        leaf-level matches).
    top_k : int
        How many of the best matches to return.

    Returns
    -------
    list[MatchResult]
        Up to *top_k* results, sorted by score descending.
    """
    paths_a = _collect_nodes_by_path(tree_a)
    paths_b = _collect_nodes_by_path(tree_b)

    # Shared paths (tag-path anchoring narrows the search)
    shared_paths = set(paths_a.keys()) & set(paths_b.keys())

    # Pre-compute subtree sizes to skip tiny subtrees
    size_cache: dict[int, int] = {}

    def _cached_size(n: DOMNode) -> int:
        nid = id(n)
        if nid not in size_cache:
            size_cache[nid] = _subtree_size(n)
        return size_cache[nid]

    # STM memo shared across all runs for efficiency
    stm_memo: dict[tuple[int, int], int] = {}
    depth_memo: dict[tuple[int, int], int] = {}

    results: list[MatchResult] = []

    for path in shared_paths:
        nodes_a = paths_a[path]
        nodes_b = paths_b[path]

        for na in nodes_a:
            sa = _cached_size(na)
            if sa < min_size:
                continue
            for nb in nodes_b:
                sb = _cached_size(nb)
                if sb < min_size:
                    continue

                score = _stm_score(na, nb, stm_memo)
                if score < min_size:
                    continue

                depth = _stm_aligned_depth(na, nb, depth_memo)

                results.append(
                    MatchResult(
                        node_a=na,
                        node_b=nb,
                        score=score,
                        depth=depth,
                        path=path,
                        size_a=sa,
                        size_b=sb,
                    )
                )

    # Sort by score descending, break ties by depth, then similarity
    results.sort(key=lambda r: (r.score, r.depth, r.similarity), reverse=True)

    # De-duplicate: if a parent pair already covers a child pair, skip it.
    # We use a simple heuristic: skip results whose node_a AND node_b are
    # both descendants (by id check in path) of an already-selected pair.
    selected: list[MatchResult] = []
    seen_a: set[int] = set()
    seen_b: set[int] = set()

    for r in results:
        a_id, b_id = id(r.node_a), id(r.node_b)
        if a_id in seen_a and b_id in seen_b:
            continue
        selected.append(r)
        # Mark all nodes in these subtrees as seen
        _mark_descendants(r.node_a, seen_a)
        _mark_descendants(r.node_b, seen_b)
        if len(selected) >= top_k:
            break

    return selected


def _mark_descendants(node: DOMNode, seen: set[int]) -> None:
    """Add node and all its descendants' ids to *seen*."""
    seen.add(id(node))
    for child in node.children:
        _mark_descendants(child, seen)


# Convenience: combined similarity score


def subtree_similarity(tree_a: DOMNode, tree_b: DOMNode) -> float:
    """Return a [0, 1] similarity score based on the best subtree match.

    This is a drop-in companion to ``dom_similarity.compute_similarity`` but focuses
    on the *best matching region* rather than the whole-tree fingerprint.
    """
    matches = find_best_subtree_match(tree_a, tree_b, top_k=1)
    if not matches:
        return 0.0
    return matches[0].similarity
