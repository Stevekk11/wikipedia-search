"""
Heuristic relevance scoring engine for Wikipedia link candidates.
Evaluates semantic similarity, structural graph centrality, direct feeder backlinks,
and penalizes narrow dead-end topics.
"""

import re
from typing import List, Set, Tuple

from .config import DEAD_END_PATTERNS, HIGH_CENTRALITY_HUBS, INDEX_PREFIXES


def compute_relevance_score(
    link_title: str,
    link_slug: str,
    target_title: str,
    target_slug: str,
    target_keywords: Set[str],
    target_backlinks: Set[str],
    depth: int = 0,
    algorithm: str = "heuristic",
) -> Tuple[float, bool, List[str], str, str, str]:
    """
    Advanced heuristic score for a candidate link.

    Returns:
        (score, is_backlink_hit, reasons, primary_badge, badge_class, explanation)
    """
    link_lower = link_title.lower()
    slug_lower = link_slug.lower()
    target_lower = target_title.lower()
    target_s_lower = target_slug.lower()

    reasons: List[str] = []

    # If algorithm is BFS, score is purely depth-based (FIFO queue order)
    if algorithm == "bfs":
        score = -float(depth)
        reasons = [
            f"Queued in level-by-level breadth-first search at hop depth {depth}",
            "Standard FIFO queue order",
        ]
        badge = f"BFS Level {depth}"
        badge_class = "bg-secondary text-white"
        explanation = f"Systematically enqueued in breadth-first FIFO traversal order at hop depth {depth}."
        return score, False, reasons, badge, badge_class, explanation

    # 1. Direct Target Match
    if target_lower == link_lower or target_s_lower == slug_lower:
        reasons.append("Exact target match")
        return (
            10000.0,
            False,
            reasons,
            "🎯 Target Match",
            "bg-success text-white",
            f"Matches target article '{target_title}' directly.",
        )

    # 2. Backlink Hit: Candidate links DIRECTLY to target!
    is_backlink_hit = slug_lower in target_backlinks or link_lower in target_backlinks
    if is_backlink_hit:
        score = 5000.0 - (depth * 10.0)
        reasons.append("Direct Feeder Backlink: Guarantees 1-hop path to target (+5,000 pts)")
        reasons.append("Identified in target incoming backlinks graph")
        return (
            score,
            True,
            reasons,
            "⭐ Direct Feeder (+5,000)",
            "bg-warning text-dark",
            f"Selected with highest priority: '{link_title}' was identified in the pre-mapped incoming backlinks graph as an immediate 1-hop feeder to '{target_title}'.",
        )

    score = 0.0
    primary_badge = "Candidate Neighbor"
    badge_class = "bg-secondary text-white"

    # 3. Substring match
    if target_lower in link_lower or target_s_lower in slug_lower:
        score += 150.0
        reasons.append("Target title substring match (+150 pts)")
        primary_badge = "Title Match"
        badge_class = "bg-primary text-white"
    elif link_lower in target_lower or slug_lower in target_s_lower:
        score += 90.0
        reasons.append("Title partial match (+90 pts)")
        primary_badge = "Partial Title Match"
        badge_class = "bg-primary text-white"

    # 4. Token overlap with target title and slug
    target_tokens = set(re.findall(r"\w+", target_lower + " " + target_s_lower.replace("_", " ")))
    link_tokens = set(re.findall(r"\w+", link_lower + " " + slug_lower.replace("_", " ")))
    overlap = target_tokens.intersection(link_tokens)
    if overlap:
        score += len(overlap) * 120.0
        reasons.append(f"Token overlap with target: {', '.join(overlap)} (+{len(overlap)*120} pts)")
        if not primary_badge or primary_badge == "Candidate Neighbor":
            primary_badge = f"Keywords ({', '.join(list(overlap)[:2])})"
            badge_class = "bg-primary text-white"

    # 5. Overlap with target categories & summary keywords
    keyword_overlap = target_keywords.intersection(link_tokens)
    if keyword_overlap:
        score += len(keyword_overlap) * 16.0
        reasons.append(
            f"Semantic category/context overlap: {', '.join(list(keyword_overlap)[:3])} (+{len(keyword_overlap)*16} pts)"
        )
        if primary_badge == "Candidate Neighbor":
            primary_badge = "Semantic Match"
            badge_class = "bg-secondary text-white"

    # 6. High-Centrality Hubs
    is_hub = slug_lower in HIGH_CENTRALITY_HUBS or any(slug_lower == h for h in HIGH_CENTRALITY_HUBS)
    if is_hub:
        score += 45.0
        reasons.append("High-centrality global connector hub spanning multiple domains (+45 pts)")
        if primary_badge == "Candidate Neighbor":
            primary_badge = "🌐 Global Connector Hub"
            badge_class = "bg-info text-dark"

    # 7. Penalize dead-end narrow topics (highways, elementary schools, etc.)
    for pattern in DEAD_END_PATTERNS:
        if pattern in link_lower or pattern in slug_lower:
            score -= 40.0
            reasons.append(f"Penalized narrow local pattern '{pattern}' (-40 pts)")
            break

    if any(slug_lower.startswith(p) for p in INDEX_PREFIXES):
        score -= 25.0
        reasons.append("Penalized list/timeline index page (-25 pts)")

    # 8. Slight depth penalty so shallower discoveries are preferred
    if depth > 0:
        penalty = depth * 5.0
        score -= penalty
        reasons.append(f"Depth penalty at hop {depth} (-{penalty:.0f} pts)")

    if not reasons:
        reasons.append("Base relevance baseline (0 pts)")

    # Build human-readable rationale explanation
    if is_hub and not overlap:
        explanation = (
            f"Prioritized as a high-centrality global connector hub ('{link_title}') "
            "bridging regional topics into international culture, governance, and foundational disciplines."
        )
    elif overlap:
        explanation = (
            f"Selected due to strong keyword alignment with target '{target_title}': "
            f"overlapping with {', '.join(overlap)}."
        )
    elif keyword_overlap:
        explanation = (
            f"Selected for semantic alignment with target categories and contextual topics "
            f"({', '.join(list(keyword_overlap)[:3])})."
        )
    else:
        explanation = "Selected as the top-ranking candidate link on this branch based on structural network centrality."

    return score, False, reasons, primary_badge, badge_class, explanation
