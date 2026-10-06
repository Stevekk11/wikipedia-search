"""
Wikipedia Link Hop Crawler Package.
Provides automated bidirectional pathfinding and hop calculation between Wikipedia articles.
"""

import io
import sys

# Ensure UTF-8 stdout/stderr encoding on Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from .config import (
    DEAD_END_PATTERNS,
    DISALLOWED_PREFIXES,
    HIGH_CENTRALITY_HUBS,
)
from .api import (
    fetch_article_assessments,
    fetch_random_article_pair,
    fetch_random_article_title,
    fetch_target_backlinks,
    fetch_target_categories,
    get_wikipedia_info,
    normalize_slug_or_title,
)
from .scorer import compute_relevance_score
from .browser import launch_playwright_browser
from .extractor import (
    enrich_final_steps_context,
    extract_outgoing_links,
    extract_page_summary,
    extract_target_link_context,
    get_page_backlinks,
)
from .engine import WikipediaCrawler

__all__ = [
    "WikipediaCrawler",
    "get_wikipedia_info",
    "normalize_slug_or_title",
    "fetch_random_article_pair",
    "fetch_random_article_title",
    "fetch_target_backlinks",
    "fetch_target_categories",
    "fetch_article_assessments",
    "compute_relevance_score",
    "launch_playwright_browser",
    "extract_page_summary",
    "extract_outgoing_links",
    "get_page_backlinks",
    "extract_target_link_context",
    "enrich_final_steps_context",
    "DISALLOWED_PREFIXES",
    "HIGH_CENTRALITY_HUBS",
    "DEAD_END_PATTERNS",
]
