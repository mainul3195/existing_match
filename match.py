"""CLI: Match a URL against existing scrapers using the multi-stage pipeline.

Usage:
    python match.py <url>
    python match.py <url> --skip structural_similarity
"""

import sys

from pipeline import MatchingPipeline
from utils.confidence import Action


def main():
    if len(sys.argv) < 2:
        print("Usage: python match.py <url> [--skip STAGE ...]")
        sys.exit(1)

    url = sys.argv[1]

    skip_stages = set()
    args = sys.argv[2:]
    i = 0
    while i < len(args):
        if args[i] == "--skip" and i + 1 < len(args):
            skip_stages.add(args[i + 1])
            i += 2
        else:
            i += 1

    print(f"Running matching pipeline for: {url}\n")

    pipeline = MatchingPipeline()
    result = pipeline.run(url, skip_stages=skip_stages)

    print(result.summary())

    print()
    action = result.confidence.action
    if action == Action.AUTO_DEPLOY:
        print("RECOMMENDATION: This URL can be auto-assigned to an existing scraper.")
    elif action == Action.HUMAN_REVIEW:
        print("RECOMMENDATION: Probable match — review before deploying.")
    elif action == Action.FLAG_FOR_INSPECTION:
        print("RECOMMENDATION: Partial match — scraper variant may be needed.")
    else:
        print("RECOMMENDATION: No existing scraper matches — new scraper required.")


if __name__ == "__main__":
    main()
