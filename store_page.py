import sys

from utils.page_fetcher import fetch_page
from utils.html_cleaner import clean_html
from utils.dom_tree import build_tree, deduplicate_children
from utils.tree_store import save_tree, count_nodes


def main():
    if len(sys.argv) < 2:
        print("Usage: python store_page.py <url> [scraper_name]")
        sys.exit(1)

    url = sys.argv[1]
    scraper_name = sys.argv[2] if len(sys.argv) > 2 else ""

    print(f"Fetching {url} ...")

    soup = fetch_page(url)
    print("Cleaning HTML ...")

    cleaned = clean_html(soup)
    print("Building DOM tree ...")

    tree = build_tree(cleaned)
    print("Deduplicating repeated subtrees ...")
    tree = deduplicate_children(tree, max_same=5)
    save_tree(url, tree, scraper_name=scraper_name)

    total = count_nodes(tree)
    print(f"Saved tree for {url} (scraper: {scraper_name or 'N/A'}) — {total} nodes, root: {tree}")


if __name__ == "__main__":
    main()
