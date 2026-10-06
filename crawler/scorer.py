"""
Heuristic relevance scoring engine for Wikipedia link candidates.
Evaluates semantic similarity, structural graph centrality, direct feeder backlinks,
and penalizes narrow dead-end topics.
"""

import re
from typing import Iterable, List, Optional, Set, Tuple

from .config import (
    DEAD_END_PATTERNS,
    HIGH_CENTRALITY_HUBS,
    HUB_BOOST_MAX_DEPTH,
    HUB_EARLY_BONUS,
    HUB_LATE_PENALTY,
    INDEX_PREFIXES,
)
from .semantic import cosine_similarity, stem, stem_tokens

# Below this cosine similarity a candidate is considered semantically unrelated
LOW_SIMILARITY = 0.25


def compute_relevance_score(
    link_title: str,
    link_slug: str,
    target_title: str,
    target_slug: str,
    target_keywords: Set[str],
    target_backlinks: Set[str],
    depth: int = 0,
    algorithm: str = "heuristic",
    target_context: Optional[Iterable[str]] = None,
    target_summary: str = "",
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
            "⭐ Direct Feeder",
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

    # 4. Stemmed token overlap with target title and slug ("Polish"/"Poles"/"Poland" unify)
    target_tokens = stem_tokens(target_lower + " " + target_s_lower.replace("_", " "))
    link_tokens = stem_tokens(link_lower + " " + slug_lower.replace("_", " "))
    overlap = target_tokens.intersection(link_tokens)

    # Embedding similarity between candidate and target (None if model unavailable)
    similarity = cosine_similarity(link_title, target_summary or target_title) if target_summary or target_title else None

    if overlap:
        overlap_pts = len(overlap) * 120.0
        # Lexical match with no semantic support (e.g. Quantum mechanics -> Quantum-Systems drone company)
        if similarity is not None and similarity < LOW_SIMILARITY:
            overlap_pts *= 0.4
            reasons.append(f"Token overlap discounted: low semantic similarity ({similarity:.2f})")
        score += overlap_pts
        reasons.append(f"Stemmed token overlap with target: {', '.join(sorted(overlap))} (+{overlap_pts:.0f} pts)")
        if not primary_badge or primary_badge == "Candidate Neighbor":
            primary_badge = f"Keywords ({', '.join(sorted(overlap)[:2])})"
            badge_class = "bg-primary text-white"

    if similarity is not None and similarity > LOW_SIMILARITY:
        sim_pts = (similarity - LOW_SIMILARITY) * 400.0
        score += sim_pts
        reasons.append(f"Embedding similarity to target {similarity:.2f} (+{sim_pts:.0f} pts)")
        if primary_badge == "Candidate Neighbor":
            primary_badge = "Semantic Match"
            badge_class = "bg-secondary text-white"

    # 5. Overlap with target categories & summary keywords (stemmed)
    stemmed_keywords = {stem(k) for k in target_keywords}
    keyword_overlap = stemmed_keywords.intersection(link_tokens)
    if keyword_overlap:
        score += len(keyword_overlap) * 16.0
        reasons.append(
            f"Semantic category/context overlap: {', '.join(sorted(keyword_overlap)[:3])} (+{len(keyword_overlap)*16} pts)"
        )
        if primary_badge == "Candidate Neighbor":
            primary_badge = "Semantic Match"
            badge_class = "bg-secondary text-white"

    # 6. High-Centrality Hubs (inverted weighting: boost early to escape niche
    #    territory, penalize later so the search zooms in on granular topics)
    is_hub = slug_lower in HIGH_CENTRALITY_HUBS
    if is_hub:
        if depth <= HUB_BOOST_MAX_DEPTH:
            score += HUB_EARLY_BONUS
            reasons.append(f"Broad connector hub at early hop {depth}: escapes niche territory (+{HUB_EARLY_BONUS:.0f} pts)")
            if primary_badge == "Candidate Neighbor":
                primary_badge = "Global Connector Hub"
                badge_class = "bg-info text-dark"
        else:
            score -= HUB_LATE_PENALTY
            reasons.append(f"Broad hub at late hop {depth}: scatters search, zoom in instead (-{HUB_LATE_PENALTY:.0f} pts)")

    # 7. Penalize dead-end narrow topics (highways, elementary schools, etc.)
    #    unless the pattern is relevant to the target's own categories / lead text.
    context = {stem(t) for t in target_context} if target_context else set()
    for pattern in DEAD_END_PATTERNS:
        if pattern in link_lower or pattern in slug_lower:
            pattern_stems = {stem(t) for t in re.findall(r"[a-z]+", pattern)}
            if pattern_stems & context:
                reasons.append(f"Dead-end pattern '{pattern}' not penalized: relevant to target context")
                continue
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
