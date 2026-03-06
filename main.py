import sys

from utils.parser import fetch_page
from utils.cleaner import clean_html
from utils.dom_tree import build_tree, deduplicate_children
from utils.db import save_tree


def _count_nodes(node) -> int:
    return 1 + sum(_count_nodes(c) for c in node.children)


def main():
    if len(sys.argv) < 2:
        print("Usage: python main.py <url>")
        sys.exit(1)

    url = sys.argv[1]
    print(f"Fetching {url} ...")

    soup = fetch_page(url)
    print("Cleaning HTML ...")

    cleaned = clean_html(soup)
    print("Building DOM tree ...")

    tree = build_tree(cleaned)
    print("Deduplicating repeated subtrees ...")
    tree = deduplicate_children(tree, max_same=5)
    save_tree(url, tree)

    total = _count_nodes(tree)
    print(f"Saved tree for {url} — {total} nodes, root: {tree}")


if __name__ == "__main__":
    main()
