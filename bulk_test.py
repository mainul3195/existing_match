"""Bulk test URLs against the database and produce an evaluation CSV.

Usage:
    python bulk_test.py scraper_base_urls_test.csv
    python bulk_test.py scraper_base_urls_test.csv --workers 20
"""

from __future__ import annotations

import csv
import sys
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict

from utils.page_fetcher import fetch_page
from utils.html_cleaner import clean_html
from utils.dom_tree import build_tree, deduplicate_children
from utils.tree_store import load_all_trees
from utils.dom_similarity import compute_similarity

DEFAULT_WORKERS = 20
MATCH_THRESHOLD = 0.77

# Scraper aliases — names that should be treated as equivalent
SCRAPER_ALIASES = {
    "DocumentCenterScraper": "DocumentCenterScraper",
    "DocumentCenterAgendaMinutesScraper": "DocumentCenterScraper",
    "SibleyCountyScraper": "DocumentCenterScraper",
    "FortLauderdale": "CityOfHawthorneScraper",
    "CityOfHawthorneScraper": "CityOfHawthorneScraper",
    "SuwaneeScraper": "CityOfHawthorneScraper",
    "SedonaAZScraper": "CityOfHawthorneScraper",
    "UpperMacungieScraper": "CityOfHawthorneScraper",
    "GilbertAZScraper": "CityOfHawthorneScraper",
    "CrystalLakeScraper": "CityOfHawthorneScraper",
    "HollisterScraper": "GovMeetingTableScraper",
    "GovMeetingTableScraper": "GovMeetingTableScraper",
    "SantaFeSpringsScraper": "GovMeetingTableScraper",
    "CaisoTPDScraper": "CaisoLibraryScraper",
    "CaisoLibraryScraper": "CaisoLibraryScraper",
    "YavapaiAZPlanningZoningScraper": "StCharlesILScraper",
    "StCharlesILScraper": "StCharlesILScraper",
    "GroupTemplateScraper": "StCharlesILScraper",
    "VintonScraper": "DavenportScraper",
    "DavenportScraper": "DavenportScraper",
    "ClintonCountyScraper": "DesMoinesCountyScraper",
    "DesMoinesCountyScraper": "DesMoinesCountyScraper",
    "VillageLakewoodScraper": "BolingbrookScraper",
    "BolingbrookScraper": "BolingbrookScraper",
    "EnnisTxScraper": "OrangeCountyScraper",
    "OrangeCountyScraper": "OrangeCountyScraper",
    "ChicagoZBAScraper": "ChicagoPlanCommissionScraper",
    "ChicagoPlanCommissionScraper": "ChicagoPlanCommissionScraper",
    "LaQuintaScraper": "LaQuintaScraper",
    "ElSegundoScraper": "LaQuintaScraper",
}

# Lock for thread-safe CSV writing
_write_lock = threading.Lock()


def _normalize_scraper(name: str) -> str:
    """Resolve scraper name to its canonical form via aliases."""
    return SCRAPER_ALIASES.get(name, name)


def evaluate_page_match(
    row: dict,
    stored: Dict[str, dict],
    db_scraper_names: set,
) -> dict:
    """Fetch a test URL, match against stored trees, return result dict."""
    url = row["url"]
    actual_scraper = row.get("scraper_name", "")

    actual_normalized = _normalize_scraper(actual_scraper)
    in_db = any(_normalize_scraper(name) == actual_normalized for name in db_scraper_names)

    result = {
        "test_url": url,
        "actual_scraper": actual_scraper,
        "highest_score": 0.0,
        "predicted_scraper": "",
        "in_db": "present" if in_db else "not present",
        "result": "",
        "error": "",
    }

    try:
        soup = fetch_page(url)
        cleaned = clean_html(soup)
        tree = build_tree(cleaned)
        tree = deduplicate_children(tree, max_same=5)

        best_score = 0.0
        best_scraper = ""

        for stored_url, entry in stored.items():
            score = compute_similarity(tree, entry["tree"])
            if score > best_score:
                best_score = score
                best_scraper = entry["scraper_name"]

        result["highest_score"] = round(best_score, 4)
        result["predicted_scraper"] = best_scraper

        # Determine ok/not ok (compare using normalized names)
        predicted_normalized = _normalize_scraper(best_scraper)
        if actual_normalized == predicted_normalized:
            result["result"] = "ok"
        elif not in_db and best_score < MATCH_THRESHOLD:
            result["result"] = "ok"
        else:
            result["result"] = "not ok"

    except Exception as e:
        result["error"] = str(e)
        result["result"] = "error"

    return result


def main():
    if len(sys.argv) < 2:
        print("Usage: python bulk_test.py <csv_file> [--workers N]")
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
    print(f"Loading all stored trees from DB ...")
    stored = load_all_trees()
    db_scraper_names = {entry["scraper_name"] for entry in stored.values()}
    print(f"Loaded {len(stored)} trees ({len(db_scraper_names)} unique scrapers)\n")

    print(f"Testing {total} URLs with {workers} workers ...\n")
    start = time.time()

    output_path = csv_path.replace(".csv", "_results.csv")
    fieldnames = [
        "test_url", "actual_scraper", "highest_score",
        "predicted_scraper", "in_db", "result", "error",
    ]

    # Write header
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

    ok_count = 0
    not_ok_count = 0
    error_count = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(evaluate_page_match, row, stored, db_scraper_names): i
            for i, row in enumerate(rows, 1)
        }

        for future in as_completed(futures):
            idx = futures[future]
            result = future.result()

            # Thread-safe write to CSV
            with _write_lock:
                with open(output_path, "a", newline="") as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writerow(result)

            status = result["result"]
            if status == "ok":
                ok_count += 1
                label = "OK"
            elif status == "error":
                error_count += 1
                label = "ERR"
            else:
                not_ok_count += 1
                label = "FAIL"

            print(
                f"  [{idx}/{total}] {label:4s} "
                f"score={result['highest_score']:.4f}  "
                f"actual={result['actual_scraper']:<30s} "
                f"predicted={result['predicted_scraper']:<30s} "
                f"{result['in_db']}"
            )

    elapsed = time.time() - start
    print(f"\nDone in {elapsed:.1f}s.")
    print(f"  OK:     {ok_count}")
    print(f"  NOT OK: {not_ok_count}")
    print(f"  ERROR:  {error_count}")
    print(f"  Total:  {total}")
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
