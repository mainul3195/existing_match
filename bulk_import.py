"""Bulk import URLs from a CSV into the database.

Usage:
    python bulk_import.py scraper_base_urls_train.csv
    python bulk_import.py scraper_base_urls_train.csv --workers 16
"""

from __future__ import annotations

import csv
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Tuple

from utils.page_fetcher import fetch_page
from utils.html_cleaner import clean_html
from utils.dom_tree import build_tree, deduplicate_children
from utils.tree_store import save_tree

DEFAULT_WORKERS = 8


def fetch_and_store_page(row: dict) -> Tuple[str, str, str | None]:
    """Fetch, parse, and save a single URL. Returns (url, scraper_name, error_or_None)."""
    url = row["url"]
    scraper_name = row.get("scraper_name", "")
    try:
        soup = fetch_page(url)
        cleaned = clean_html(soup)
        tree = build_tree(cleaned)
        tree = deduplicate_children(tree, max_same=5)
        save_tree(url, tree, scraper_name=scraper_name)
        return (url, scraper_name, None)
    except Exception as e:
        return (url, scraper_name, str(e))


def main():
    if len(sys.argv) < 2:
        print("Usage: python bulk_import.py <csv_file> [--workers N]")
        sys.exit(1)

    csv_path = sys.argv[1]
    workers = DEFAULT_WORKERS

    args = sys.argv[2:]
    for i, arg in enumerate(args):
        if arg == "--workers" and i + 1 < len(args):
            workers = int(args[i + 1])

    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    total = len(rows)
    success = 0
    failed = 0

    print(f"Importing {total} URLs from {csv_path} with {workers} workers ...\n")
    start = time.time()

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_and_store_page, row): i for i, row in enumerate(rows, 1)}

        for future in as_completed(futures):
            idx = futures[future]
            url, scraper_name, error = future.result()
            if error is None:
                success += 1
                print(f"  [{idx}/{total}] OK  {scraper_name:<30} {url}")
            else:
                failed += 1
                print(f"  [{idx}/{total}] FAIL {scraper_name:<30} {url} — {error}")

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s. {success} imported, {failed} failed out of {total}.")


if __name__ == "__main__":
    main()
