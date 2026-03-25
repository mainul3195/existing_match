"""Pipeline controller — orchestrates the matching stages.

Stages run in order, short-circuiting when confidence is high enough:
  1. URL pattern matching (free, <1ms)
  2. Structural similarity — multi-signal heuristics
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bs4 import BeautifulSoup

from utils.url_pattern import match_url, URLMatchResult
from utils.confidence import (
    StageSignal,
    ConfidenceResult,
    compute_confidence,
    Action,
)
from utils.page_fetcher import fetch_page
from utils.html_cleaner import clean_html
from utils.dom_tree import build_tree, deduplicate_children
from utils.tree_store import load_all_trees
from utils.dom_similarity import compute_similarity_detailed


SHORT_CIRCUIT_THRESHOLD = 0.85
TOP_CANDIDATES = 5


@dataclass
class PipelineResult:
    """Full result from the matching pipeline."""

    url: str
    confidence: ConfidenceResult
    url_match: URLMatchResult | None = None
    structural_scores: list[dict] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"Pipeline result for: {self.url}",
            f"  Final confidence: {self.confidence.score:.4f}",
            f"  Action: {self.confidence.action_label}",
        ]
        if self.confidence.matched_platform:
            lines.append(f"  Platform: {self.confidence.matched_platform}")
        if self.confidence.is_novel:
            lines.append("  ** NOVEL site — new scraper likely needed **")

        lines.append(f"\n  Signals ({len(self.confidence.signals)}):")
        for sig in self.confidence.signals:
            lines.append(
                f"    [{sig.stage}] confidence={sig.confidence:.4f} "
                f"weight={sig.weight:.1f}"
            )
            for k, v in sig.details.items():
                lines.append(f"      {k}: {v}")

        if self.structural_scores:
            lines.append(
                f"\n  Structural similarity (top {len(self.structural_scores)}):"
            )
            for s in self.structural_scores:
                scraper_label = (
                    f" [scraper: {s['scraper_name']}]" if s.get("scraper_name") else ""
                )
                lines.append(f"    {s['url']}: score={s['score']:.4f}{scraper_label}")
                if "metrics" in s and "weights" in s:
                    for metric, val in sorted(
                        s["metrics"].items(),
                        key=lambda x: -s["weights"].get(x[0], 0),
                    ):
                        w = s["weights"].get(metric, 0)
                        lines.append(f"      {metric:<25} {val:.4f}  (weight {w})")

        return "\n".join(lines)


class MatchingPipeline:
    """Multi-stage cascading pipeline for matching new URLs to existing scrapers.

    Usage:
        pipeline = MatchingPipeline()
        result = pipeline.run("https://example.gov/meetings")
        print(result.summary())
    """

    def __init__(
        self,
        short_circuit_threshold: float = SHORT_CIRCUIT_THRESHOLD,
    ):
        self.short_circuit_threshold = short_circuit_threshold

    def run(
        self,
        url: str,
        soup: BeautifulSoup | None = None,
        skip_stages: set[str] | None = None,
    ) -> PipelineResult:
        """Run the full matching pipeline for a URL."""
        skip = skip_stages or set()
        signals: list[StageSignal] = []
        result = PipelineResult(
            url=url,
            confidence=ConfidenceResult(
                score=0.0,
                action=Action.NO_MATCH,
                matched_platform=None,
                signals=[],
                is_novel=True,
            ),
        )

        if "url_pattern" not in skip:
            url_match = match_url(url)
            result.url_match = url_match
            if url_match:
                signals.append(
                    StageSignal(
                        stage="url_pattern",
                        confidence=url_match.confidence,
                        details={
                            "platform": url_match.platform,
                            "pattern": url_match.matched_pattern,
                            "description": url_match.details,
                        },
                    )
                )

        current = compute_confidence(signals)
        if current.score >= self.short_circuit_threshold and signals:
            result.confidence = current
            return result

        if soup is None:
            try:
                soup = fetch_page(url)
            except Exception:
                result.confidence = compute_confidence(signals)
                return result

        if "structural_similarity" not in skip:
            cleaned = clean_html(soup)
            tree = build_tree(cleaned)
            tree = deduplicate_children(tree, max_same=5)

            stored = load_all_trees()
            if stored:
                scores = []
                for stored_url, entry in stored.items():
                    detailed = compute_similarity_detailed(tree, entry["tree"])
                    weights = detailed.pop("_weights")
                    combined = detailed.pop("_combined")
                    scores.append(
                        {
                            "url": stored_url,
                            "scraper_name": entry["scraper_name"],
                            "score": combined,
                            "metrics": detailed,
                            "weights": weights,
                        }
                    )
                scores.sort(key=lambda s: s["score"], reverse=True)
                result.structural_scores = scores[:TOP_CANDIDATES]

                if scores:
                    best = scores[0]
                    metric_details = {
                        "best_match": best["url"],
                        "scraper_name": best["scraper_name"],
                        "score": f"{best['score']:.4f}",
                    }
                    for metric_name, metric_val in best["metrics"].items():
                        metric_details[metric_name] = f"{metric_val:.4f}"
                    signals.append(
                        StageSignal(
                            stage="structural_similarity",
                            confidence=best["score"],
                            details=metric_details,
                        )
                    )

        result.confidence = compute_confidence(signals)
        return result
