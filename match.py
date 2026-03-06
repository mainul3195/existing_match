"""CLI: fetch a URL, build its DOM tree, and find the top-5 most similar
pages already stored in the database.

Usage:
    python match.py <url>                    # whole-tree + subtree matching
    python match.py <url> --subtree-detail   # also show individual subtree matches
"""

import sys

from utils.parser import fetch_page
from utils.cleaner import clean_html
from utils.dom_tree import build_tree, deduplicate_children
from utils.db import load_all_trees
from utils.matcher import tree_similarity
from utils.subtree_matcher import (
    find_best_subtree_match,
    subtree_similarity,
)


def _format_node(node, max_len=60) -> str:
    """Short human-readable description of a DOMNode."""
    desc = f"<{node.tag}>"
    if node.text:
        preview = node.text[:30].replace("\n", " ")
        desc += f' "{preview}..."'
    if node.children:
        desc += f" ({len(node.children)} children)"
    return desc[:max_len]


def main():
    if len(sys.argv) < 2:
        print("Usage: python match.py <url> [--subtree-detail]")
        sys.exit(1)

    url = sys.argv[1]
    show_detail = "--subtree-detail" in sys.argv

    # Build tree for the input URL
    print(f"Fetching {url} ...")
    soup = fetch_page(url)
    cleaned = clean_html(soup)
    tree = build_tree(cleaned)
    tree = deduplicate_children(tree, max_same=5)

    # Load all stored trees
    stored = load_all_trees()
    if not stored:
        print("Database is empty — nothing to compare against.")
        print("Run  python main.py <url>  first to populate the database.")
        sys.exit(0)

    # Score against every stored tree
    results = []
    for stored_url, stored_tree in stored.items():
        whole_score = tree_similarity(tree, stored_tree)
        sub_score = subtree_similarity(tree, stored_tree)
        combined = 0.5 * whole_score + 0.5 * sub_score
        results.append(
            {
                "url": stored_url,
                "whole": whole_score,
                "subtree": sub_score,
                "combined": combined,
            }
        )

    # Sort by combined score descending, take top 5
    results.sort(key=lambda r: r["combined"], reverse=True)
    top = results[:5]

    print(f"\nTop {len(top)} matches for: {url}\n")
    print(f"{'Rank':<6}{'Combined':<10}{'Whole':<10}{'Subtree':<10}{'URL'}")
    print("-" * 80)
    for i, r in enumerate(top, 1):
        print(
            f"{i:<6}{r['combined']:<10.4f}{r['whole']:<10.4f}"
            f"{r['subtree']:<10.4f}{r['url']}"
        )

    # Detailed subtree matching for the best match
    if show_detail and top:
        best_url = top[0]["url"]
        best_tree = stored[best_url]
        matches = find_best_subtree_match(tree, best_tree, top_k=5)

        print(f"\n{'=' * 80}")
        print(f"Subtree matches vs best page: {best_url}")
        print(f"{'=' * 80}\n")

        if not matches:
            print("  No significant subtree matches found.")
        else:
            for i, m in enumerate(matches, 1):
                print(f"  Match #{i}")
                print(f"    Path:       {m.path}")
                print(f"    STM Score:  {m.score} matched nodes")
                print(f"    Depth:      {m.depth} levels")
                print(f"    Similarity: {m.similarity:.4f}")
                print(f"    Subtree A:  {_format_node(m.node_a)} ({m.size_a} nodes)")
                print(f"    Subtree B:  {_format_node(m.node_b)} ({m.size_b} nodes)")
                print()


if __name__ == "__main__":
    main()
