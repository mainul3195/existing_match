"""Stage 1a: URL pattern matching for known government platforms.

Zero HTTP requests — tests the incoming URL against regex patterns for
known platform domains and path structures. The cheapest possible check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from urllib.parse import urlparse


@dataclass
class URLMatchResult:
    """Result of URL pattern matching."""
    platform: str
    confidence: float
    matched_pattern: str
    details: str = ""


# Each rule: (platform_name, compiled_regex, confidence, description)
@dataclass
class _URLRule:
    platform: str
    pattern: re.Pattern
    confidence: float
    description: str


_URL_RULES: list[_URLRule] = [
    # --- Legistar ---
    _URLRule(
        platform="legistar",
        pattern=re.compile(
            r"https?://[^/]*\.legistar\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="Legistar subdomain",
    ),
    _URLRule(
        platform="legistar",
        pattern=re.compile(
            r"https?://[^/]+/(?:Calendar|MeetingDetail|LegislationDetail)\.aspx",
            re.IGNORECASE,
        ),
        confidence=0.85,
        description="Legistar .aspx page pattern",
    ),
    # --- CivicPlus ---
    _URLRule(
        platform="civicplus",
        pattern=re.compile(
            r"https?://[^/]*\.civicplus\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="CivicPlus subdomain",
    ),
    _URLRule(
        platform="civicplus",
        pattern=re.compile(
            r"https?://[^/]+/AgendaCenter",
            re.IGNORECASE,
        ),
        confidence=0.90,
        description="CivicPlus AgendaCenter path",
    ),
    # --- BoardDocs ---
    _URLRule(
        platform="boarddocs",
        pattern=re.compile(
            r"https?://go\.boarddocs\.com/[^/]+/[^/]+/Board\.nsf",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="BoardDocs .nsf path",
    ),
    _URLRule(
        platform="boarddocs",
        pattern=re.compile(
            r"https?://[^/]*boarddocs\.com",
            re.IGNORECASE,
        ),
        confidence=0.90,
        description="BoardDocs domain",
    ),
    # --- Granicus ---
    _URLRule(
        platform="granicus",
        pattern=re.compile(
            r"https?://[^/]*\.granicus\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="Granicus subdomain",
    ),
    _URLRule(
        platform="granicus",
        pattern=re.compile(
            r"https?://[^/]+/(?:MediaPlayer|MetaViewer)\.php",
            re.IGNORECASE,
        ),
        confidence=0.85,
        description="Granicus PHP page pattern",
    ),
    # --- NovusAgenda ---
    _URLRule(
        platform="novusagenda",
        pattern=re.compile(
            r"https?://[^/]*\.novusagenda\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="NovusAgenda subdomain",
    ),
    _URLRule(
        platform="novusagenda",
        pattern=re.compile(
            r"https?://[^/]+/AgendaPublic",
            re.IGNORECASE,
        ),
        confidence=0.85,
        description="NovusAgenda AgendaPublic path",
    ),
    # --- Municode ---
    _URLRule(
        platform="municode",
        pattern=re.compile(
            r"https?://library\.municode\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="Municode library domain",
    ),
    # --- PrimeGov ---
    _URLRule(
        platform="primegov",
        pattern=re.compile(
            r"https?://[^/]*\.primegov\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="PrimeGov subdomain",
    ),
    # --- iCompass ---
    _URLRule(
        platform="icompass",
        pattern=re.compile(
            r"https?://[^/]*\.icompass\.com",
            re.IGNORECASE,
        ),
        confidence=0.95,
        description="iCompass subdomain",
    ),
    # --- WordPress ---
    _URLRule(
        platform="wordpress",
        pattern=re.compile(
            r"https?://[^/]+/wp-(?:content|admin|includes)/",
            re.IGNORECASE,
        ),
        confidence=0.80,
        description="WordPress wp-* path",
    ),
    # --- Drupal ---
    _URLRule(
        platform="drupal",
        pattern=re.compile(
            r"https?://[^/]+/(?:sites/default/files|node/\d+)",
            re.IGNORECASE,
        ),
        confidence=0.75,
        description="Drupal path pattern",
    ),
]


def match_url(url: str) -> URLMatchResult | None:
    """Test a URL against all known platform patterns.

    Returns the highest-confidence match, or None if no pattern matches.
    """
    best: URLMatchResult | None = None

    for rule in _URL_RULES:
        if rule.pattern.search(url):
            result = URLMatchResult(
                platform=rule.platform,
                confidence=rule.confidence,
                matched_pattern=rule.pattern.pattern,
                details=rule.description,
            )
            if best is None or result.confidence > best.confidence:
                best = result

    return best
