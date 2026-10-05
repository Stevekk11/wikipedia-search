"""
Wikipedia Link Hop Crawler using Playwright.
Navigates Wikipedia pages to find the shortest or heuristic link path
between two articles, reports intermediate visited pages in real-time,
extracts 150 words of context before and after the connecting links,
and records the algorithmic rationale behind each intermediate link selected.
"""

import asyncio
import base64
import html
import io
import logging
import re
import sys
import urllib.parse
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple

# Ensure UTF-8 stdout/stderr encoding on Windows
if sys.platform.startswith("win"):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger("wikipedia_crawler")
logging.basicConfig(level=logging.INFO)

DISALLOWED_PREFIXES = [
    "File:",
    "Talk:",
    "Special:",
    "Wikipedia:",
    "Help:",
    "Category:",
    "Portal:",
    "Template:",
    "Template_talk:",
    "User:",
    "User_talk:",
    "MediaWiki:",
    "Draft:",
    "TimedText:",
    "Module:",
    "Book:",
]

# High-centrality connector hubs that span broad subjects in Wikipedia
HIGH_CENTRALITY_HUBS = {
    "united_states", "united_kingdom", "europe", "north_america", "asia", "africa",
    "world", "earth", "country", "city", "history", "geography", "government",
    "economy", "culture", "society", "human", "biology", "science", "technology",
    "medicine", "law", "philosophy", "psychology", "politics", "education",
    "demographics_of_the_united_states", "human_sexuality", "culture_of_the_united_states"
}

# Narrow, dead-end patterns to penalize
DEAD_END_PATTERNS = [
    "road", "highway", "state_road", "interstate", "route", "airport",
    "railway", "station", "school", "high_school", "elementary", "middle_school",
    "district", "season", "championship", "tournament", "cup", "election"
]


def normalize_slug_or_title(raw_input: str) -> str:
    """Extract and normalize a Wikipedia slug or title from URL or user text."""
    text = raw_input.strip()
    if not text:
        return ""
    
    if "wikipedia.org/wiki/" in text:
        parts = text.split("wikipedia.org/wiki/")
        text = parts[-1].split("?")[0].split("#")[0]
        text = urllib.parse.unquote(text)
    
    slug = text.strip().replace(" ", "_")
    return slug


def get_wikipedia_info(title_or_slug: str) -> Dict[str, str]:
    """
    Query the Wikipedia REST / Action API to resolve redirects,
    get canonical title, slug, summary snippet, and thumbnail.
    """
    clean = normalize_slug_or_title(title_or_slug)
    encoded = urllib.parse.quote(clean)
    
    headers = {
        "User-Agent": "WikiHopBot/1.0 (https://github.com/example/wikipedia-search; contact@example.com)"
    }
    
    rest_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        r = requests.get(rest_url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            canonical_title = data.get("title", clean.replace("_", " "))
            canonical_slug = urllib.parse.unquote(data.get("titles", {}).get("canonical", canonical_title.replace(" ", "_")))
            description = data.get("description", "")
            extract = data.get("extract", "")
            thumbnail = data.get("thumbnail", {}).get("source", "")
            return {
                "title": canonical_title,
                "slug": canonical_slug,
                "url": f"https://en.wikipedia.org/wiki/{canonical_slug}",
                "description": description,
                "extract": extract[:250] + ("..." if len(extract) > 250 else ""),
                "thumbnail": thumbnail,
            }
    except Exception as e:
        logger.warning(f"Failed to query summary API for {clean}: {e}")

    api_url = (
        f"https://en.wikipedia.org/w/api.php?action=query&titles={encoded}"
        f"&redirects=1&format=json"
    )
    try:
        r = requests.get(api_url, headers=headers, timeout=5)
        if r.status_code == 200:
            pages = r.json().get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if pid != "-1":
                    t = pdata.get("title", clean.replace("_", " "))
                    s = t.replace(" ", "_")
                    return {
                        "title": t,
                        "slug": s,
                        "url": f"https://en.wikipedia.org/wiki/{s}",
                        "description": "",
                        "extract": "",
                        "thumbnail": "",
                    }
    except Exception as e:
        logger.warning(f"Failed to query action API for {clean}: {e}")

    title = clean.replace("_", " ")
    return {
        "title": title,
        "slug": clean,
        "url": f"https://en.wikipedia.org/wiki/{clean}",
        "description": "",
        "extract": "",
        "thumbnail": "",
    }


def fetch_target_backlinks(target_slug: str, limit: int = 1000) -> Set[str]:
    """
    Fetch articles that link directly to the target article (What Links Here).
    Any page linking to these backlinks is guaranteed to be 1 hop away from target!
    """
    backlinks = set()
    headers = {"User-Agent": "WikiHopBot/1.0 (contact@example.com)"}
    url = f"https://en.wikipedia.org/w/api.php?action=query&prop=linkshere&titles={urllib.parse.quote(target_slug)}&lhlimit=500&lhnamespace=0&format=json"
    try:
        r = requests.get(url, headers=headers, timeout=5).json()
        pages = r.get("query", {}).get("pages", {})
        for pid, p in pages.items():
            for item in p.get("linkshere", []):
                t = item.get("title", "")
                if t:
                    backlinks.add(t.lower())
                    backlinks.add(t.lower().replace(" ", "_"))
    except Exception as e:
        logger.warning(f"Failed to fetch target backlinks for {target_slug}: {e}")
    return backlinks


def fetch_target_categories(target_slug: str) -> Set[str]:
    """
    Fetch Wikipedia categories of the target article to enrich semantic keywords.
    """
    cat_words = set()
    headers = {"User-Agent": "WikiHopBot/1.0 (contact@example.com)"}
    url = f"https://en.wikipedia.org/w/api.php?action=query&prop=categories&titles={urllib.parse.quote(target_slug)}&cllimit=50&format=json"
    try:
        r = requests.get(url, headers=headers, timeout=4).json()
        pages = r.get("query", {}).get("pages", {})
        for pid, p in pages.items():
            for cat in p.get("categories", []):
                c_title = cat.get("title", "").replace("Category:", "")
                if any(ign in c_title.lower() for ign in ["articles", "all", "use", "pages", "cs1", "commons", "short", "statements", "webarchive"]):
                    continue
                words = re.findall(r"\w+", c_title.lower())
                cat_words.update(w for w in words if len(w) > 3)
    except Exception as e:
        logger.warning(f"Failed to fetch categories for {target_slug}: {e}")
    return cat_words


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
    Advanced heuristic score for a candidate link:
    Returns: (score, is_backlink_hit, reasons, primary_badge, badge_class, explanation)
    """
    link_lower = link_title.lower()
    slug_lower = link_slug.lower()
    target_lower = target_title.lower()
    target_s_lower = target_slug.lower()

    reasons: List[str] = []

    # If algorithm is BFS, score is purely depth-based
    if algorithm == "bfs":
        score = -float(depth)
        reasons = [
            f"Queued in level-by-level breadth-first search at hop depth {depth}",
            "Standard FIFO queue order"
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
            f"Matches target article '{target_title}' directly."
        )

    # 2. Backlink Hit: Candidate links DIRECTLY to target!
    is_backlink_hit = (slug_lower in target_backlinks or link_lower in target_backlinks)
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
            f"Selected with highest priority: '{link_title}' was identified in the pre-mapped incoming backlinks graph as an immediate 1-hop feeder to '{target_title}'."
        )

    score = 0.0
    primary_badge = "Candidate Neighbor"
    badge_class = "bg-secondary text-white"

    # 3. Substring match
    if target_lower in link_lower or target_s_lower in slug_lower:
        score += 150.0
        reasons.append(f"Target title substring match (+150 pts)")
        primary_badge = "Title Match"
        badge_class = "bg-primary text-white"
    elif link_lower in target_lower or slug_lower in target_s_lower:
        score += 90.0
        reasons.append(f"Title partial match (+90 pts)")
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
        reasons.append(f"Semantic category/context overlap: {', '.join(list(keyword_overlap)[:3])} (+{len(keyword_overlap)*16} pts)")
        if primary_badge == "Candidate Neighbor":
            primary_badge = f"Semantic Match"
            badge_class = "bg-secondary text-white"

    # 6. High-Centrality Hubs
    is_hub = (slug_lower in HIGH_CENTRALITY_HUBS or any(slug_lower == h for h in HIGH_CENTRALITY_HUBS))
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

    if any(slug_lower.startswith(p) for p in ["list_of", "timeline_of"]):
        score -= 25.0
        reasons.append("Penalized list/timeline index page (-25 pts)")

    # 8. Slight depth penalty so shallower discoveries are preferred
    score -= depth * 5.0

    # Build human explanation
    if is_hub and not overlap:
        explanation = f"Prioritized as a high-centrality global connector hub ('{link_title}') bridging regional topics into international culture, governance, and foundational disciplines."
    elif overlap:
        explanation = f"Selected due to strong keyword alignment with target '{target_title}': overlapping with {', '.join(overlap)}."
    elif keyword_overlap:
        explanation = f"Selected for semantic alignment with target categories and contextual topics ({', '.join(list(keyword_overlap)[:3])})."
    else:
        explanation = f"Selected as the top-ranking candidate link on this branch based on structural network centrality."

    return score, False, reasons, primary_badge, badge_class, explanation


async def launch_playwright_browser(playwright_instance, headless: bool = True) -> Browser:
    """Launch Chromium browser with robust fallbacks."""
    for channel in ["msedge", "chrome", None]:
        try:
            kwargs = {"headless": headless}
            if channel:
                kwargs["channel"] = channel
            browser = await playwright_instance.chromium.launch(**kwargs)
            logger.info(f"Successfully launched browser with channel={channel}")
            return browser
        except Exception as e:
            logger.warning(f"Could not launch browser with channel={channel}: {e}")
            continue
    raise RuntimeError("Could not launch any browser (msedge, chrome, or chromium).")


async def get_page_backlinks(page: Page, slug: str, limit: int = 150) -> List[Dict[str, str]]:
    """
    Fetch incoming backlinks to a Wikipedia article.
    First tries Wikipedia Action API; falls back to Playwright Special:WhatLinksHere.
    """
    clean_slug = slug.strip().replace(" ", "_")
    encoded = urllib.parse.quote(clean_slug.replace("_", " "))
    headers = {
        "User-Agent": "WikipediaHopFinder/2.0 (BidirectionalCrawler/1.0; contact@example.com)"
    }
    api_url = f"https://en.wikipedia.org/w/api.php?action=query&list=backlinks&bltitle={encoded}&bllimit={limit}&blnamespace=0&format=json"
    
    try:
        r = requests.get(api_url, headers=headers, timeout=4)
        if r.status_code == 200:
            data = r.json()
            bl_list = data.get("query", {}).get("backlinks", [])
            if bl_list:
                return [
                    {
                        "title": b["title"],
                        "slug": b["title"].replace(" ", "_"),
                    }
                    for b in bl_list
                    if not any(b["title"].startswith(p) for p in DISALLOWED_PREFIXES)
                ]
    except Exception as e:
        logger.debug(f"Action API backlinks failed for {clean_slug}: {e}")

    # Fallback to Playwright Special:WhatLinksHere
    try:
        what_url = f"https://en.wikipedia.org/wiki/Special:WhatLinksHere/{clean_slug}?limit={limit}&namespace=0"
        await page.goto(what_url, wait_until="domcontentloaded", timeout=12000)
        items = await page.evaluate("""() => {
            const list = document.querySelector('#mw-whatlinkshere-list');
            if (!list) return [];
            const results = [];
            const seen = new Set();
            const disallowedPrefixes = [
                'File:', 'Talk:', 'Special:', 'Wikipedia:', 'Help:',
                'Category:', 'Portal:', 'Template:', 'Template_talk:',
                'User:', 'User_talk:', 'MediaWiki:', 'Draft:', 'TimedText:', 'Module:', 'Book:'
            ];
            const lis = Array.from(list.querySelectorAll('li > bdi > a'));
            for (const a of lis) {
                const rawHref = a.getAttribute('href') || '';
                let s = '';
                if (rawHref.startsWith('/wiki/')) s = rawHref.substring(6);
                else if (rawHref.startsWith('https://en.wikipedia.org/wiki/')) s = rawHref.substring(30);
                s = s.split('#')[0].split('?')[0];
                if (!s || s === 'Main_Page') continue;
                try { s = decodeURIComponent(s); } catch(e) {}
                if (disallowedPrefixes.some(p => s.startsWith(p))) continue;
                const k = s.toLowerCase();
                if (!seen.has(k)) {
                    seen.add(k);
                    const title = a.getAttribute('title') || a.innerText.trim() || s.replace(/_/g, ' ');
                    results.push({ slug: s, title: title });
                }
            }
            return results;
        }""")
        return items
    except Exception as e:
        logger.warning(f"Playwright WhatLinksHere failed for {clean_slug}: {e}")
        return []


async def extract_target_link_context(page: Page, source_slug: str, target_slug: str, target_title: str, words_count: int = 150) -> Dict:
    """Extract up to words_count before and after the target link on source_slug."""
    try:
        cur_url = page.url or ""
        if f"/wiki/{source_slug}" not in cur_url:
            await page.goto(f"https://en.wikipedia.org/wiki/{source_slug}", wait_until="domcontentloaded", timeout=12000)
            
        extracted_context = await page.evaluate(
            """args => {
                const targetSlug = args.targetSlug.toLowerCase();
                const wordsBeforeCount = args.wordsBeforeCount;
                const wordsAfterCount = args.wordsAfterCount;
                const body = document.querySelector('#bodyContent') || document.body;
                
                const anchors = Array.from(body.querySelectorAll('a[href]'));
                let targetAnchor = anchors.find(a => {
                    const href = (a.getAttribute('href') || '').toLowerCase();
                    return href.includes('/wiki/' + targetSlug) || href.endsWith('/' + targetSlug);
                });

                if (!targetAnchor) {
                    targetAnchor = anchors.find(a => {
                        const text = (a.innerText || '').toLowerCase().trim();
                        const title = (a.getAttribute('title') || '').toLowerCase().trim();
                        const cleanSlug = targetSlug.replace(/_/g, ' ');
                        return text === cleanSlug || title === cleanSlug;
                    });
                }

                if (!targetAnchor) return null;

                const walkerBefore = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null, false);
                walkerBefore.currentNode = targetAnchor;
                const wordsBefore = [];
                let prevNode;
                while (wordsBefore.length < wordsBeforeCount && (prevNode = walkerBefore.previousNode())) {
                    const parent = prevNode.parentElement;
                    if (!parent || parent.closest('script, style, #mw-navigation, #footer')) continue;
                    const txt = prevNode.textContent.trim();
                    if (!txt) continue;
                    const tokens = txt.split(/\\s+/).filter(Boolean);
                    for (let i = tokens.length - 1; i >= 0 && wordsBefore.length < wordsBeforeCount; i--) {
                        wordsBefore.unshift(tokens[i]);
                    }
                }

                const walkerAfter = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null, false);
                walkerAfter.currentNode = targetAnchor;
                const wordsAfter = [];
                let nextNode;
                while (wordsAfter.length < wordsAfterCount && (nextNode = walkerAfter.nextNode())) {
                    if (targetAnchor.contains(nextNode)) continue;
                    const parent = nextNode.parentElement;
                    if (!parent || parent.closest('script, style, #mw-navigation, #footer')) continue;
                    const txt = nextNode.textContent.trim();
                    if (!txt) continue;
                    const tokens = txt.split(/\\s+/).filter(Boolean);
                    for (let i = 0; i < tokens.length && wordsAfter.length < wordsAfterCount; i++) {
                        wordsAfter.push(tokens[i]);
                    }
                }

                return {
                    anchorText: targetAnchor.innerText.trim() || targetAnchor.getAttribute('title') || '',
                    wordsBefore: wordsBefore.join(' '),
                    wordsAfter: wordsAfter.join(' '),
                    beforeCount: wordsBefore.length,
                    afterCount: wordsAfter.length
                };
            }""",
            {
                "targetSlug": target_slug,
                "wordsBeforeCount": words_count,
                "wordsAfterCount": words_count,
            }
        )
        if extracted_context:
            return {
                "source_slug": source_slug,
                "source_url": f"https://en.wikipedia.org/wiki/{source_slug}",
                "target_title": target_title,
                "target_slug": target_slug,
                "target_url": f"https://en.wikipedia.org/wiki/{target_slug}",
                "words_before": extracted_context.get("wordsBefore", ""),
                "anchor_text": extracted_context.get("anchorText", target_title),
                "words_after": extracted_context.get("wordsAfter", ""),
                "before_count": extracted_context.get("beforeCount", 0),
                "after_count": extracted_context.get("afterCount", 0),
                "requested_words": words_count,
            }
    except Exception as e:
        logger.warning(f"Error extracting target link context: {e}")
    return {
        "source_slug": source_slug,
        "source_url": f"https://en.wikipedia.org/wiki/{source_slug}",
        "target_title": target_title,
        "target_slug": target_slug,
        "target_url": f"https://en.wikipedia.org/wiki/{target_slug}",
        "words_before": "",
        "anchor_text": target_title,
        "words_after": "",
        "before_count": 0,
        "after_count": 0,
        "requested_words": words_count,
    }


class WikipediaCrawler:
    """
    Orchestrates the Wikipedia hop counting traversal using Playwright
    with true simultaneous Bidirectional Search (searching from both sides at once)
    until both frontiers meet in the middle.
    """

    def __init__(
        self,
        start_input: str,
        target_input: str,
        algorithm: str = "heuristic",  # 'heuristic' or 'bfs'
        max_pages: int = 35,
        max_depth: int = 5,
        headless: bool = True,
        capture_screenshots: bool = True,
        context_words: int = 150,
    ):
        self.start_input = start_input
        self.target_input = target_input
        self.algorithm = algorithm.lower()
        self.max_pages = max(5, min(max_pages, 1000))
        self.max_depth = max(1, min(max_depth, 50))
        self.headless = headless
        self.capture_screenshots = capture_screenshots
        self.context_words = max(20, min(context_words, 500))
        self.cancel_requested = False

    def cancel(self):
        """Signal the crawler to cancel traversal."""
        self.cancel_requested = True

    async def search(self) -> AsyncGenerator[Dict, None]:
        """Executes simultaneous bidirectional search and yields JSON-serializable events."""
        start_info = get_wikipedia_info(self.start_input)
        target_info = get_wikipedia_info(self.target_input)

        if not start_info["slug"] or not target_info["slug"]:
            yield {
                "event": "error",
                "message": "Invalid start or target page provided.",
            }
            return

        start_slug_lower = start_info["slug"].lower()
        target_slug_lower = target_info["slug"].lower()

        # Check trivial case: Start == Target
        if start_slug_lower == target_slug_lower:
            yield {
                "event": "found",
                "hops": 0,
                "path": [start_info["title"]],
                "slugs": [start_info["slug"]],
                "urls": [start_info["url"]],
                "total_visited": 1,
                "forward_visited_count": 1,
                "backward_visited_count": 0,
                "intermediate_pages": [],
                "link_context": None,
                "intermediate_steps": [],
                "found_on_page": start_info["title"],
                "message": "Start and target pages are identical! 0 hops required.",
            }
            return

        # Fetch semantic guidance for both directions in parallel
        target_backlinks: Set[str] = set()
        target_keywords: Set[str] = set()
        start_keywords: Set[str] = set()

        if self.algorithm == "heuristic":
            loop = asyncio.get_running_loop()
            t_backlinks_fut = loop.run_in_executor(None, fetch_target_backlinks, target_info["slug"], 500)
            t_cats_fut = loop.run_in_executor(None, fetch_target_categories, target_info["slug"])
            s_cats_fut = loop.run_in_executor(None, fetch_target_categories, start_info["slug"])
            target_backlinks, target_categories, start_categories = await asyncio.gather(
                t_backlinks_fut, t_cats_fut, s_cats_fut
            )
            target_keywords.update(target_categories)
            start_keywords.update(start_categories)

        if target_info.get("extract"):
            target_keywords.update(re.findall(r"\w+", target_info["extract"].lower()))
        if start_info.get("extract"):
            start_keywords.update(re.findall(r"\w+", start_info["extract"].lower()))

        target_keywords = {w for w in target_keywords if len(w) > 3}
        start_keywords = {w for w in start_keywords if len(w) > 3}

        logger.info(
            f"Bidirectional search initialized: Start '{start_info['title']}' ({len(start_keywords)} keywords) <===> "
            f"Target '{target_info['title']}' ({len(target_keywords)} keywords, {len(target_backlinks)} pre-mapped backlinks)"
        )

        yield {
            "event": "started",
            "start": start_info,
            "target": target_info,
            "algorithm": self.algorithm,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "context_words": self.context_words,
            "target_backlinks_count": len(target_backlinks),
        }

        # Traversal State Maps:
        # forward_visited: slug.lower() -> dict(title, slug, depth, path_titles, path_slugs, path_steps)
        forward_visited: Dict[str, Dict] = {}
        # backward_visited: slug.lower() -> dict(title, slug, depth, path_titles, path_slugs, path_steps)
        backward_visited: Dict[str, Dict] = {}
        # forward_outgoing: slug.lower() of an outgoing link -> dict(from_title, from_slug, step_info, path_titles, path_slugs, path_steps)
        forward_outgoing: Dict[str, Dict] = {}
        # backward_incoming: slug.lower() of an incoming link -> dict(to_title, to_slug, step_info, path_titles, path_slugs, path_steps)
        backward_incoming: Dict[str, Dict] = {}

        intermediate_pages: List[Dict] = []

        # Forward Queue: (score, depth, slug, title, path_titles, path_slugs, path_steps)
        forward_queue: List[Tuple[float, int, str, str, List[str], List[str], List[Dict]]] = [
            (0.0, 0, start_info["slug"], start_info["title"], [start_info["title"]], [start_info["slug"]], [])
        ]

        # Backward Queue: (score, depth, slug, title, path_titles, path_slugs, path_steps)
        # Note: In backward_queue, path_titles represents path from node TO Target!
        backward_queue: List[Tuple[float, int, str, str, List[str], List[str], List[Dict]]] = [
            (0.0, 0, target_info["slug"], target_info["title"], [target_info["title"]], [target_info["slug"]], [])
        ]

        visited_count = 0

        async with async_playwright() as p:
            browser = await launch_playwright_browser(p, headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            )
            page = await context.new_page()

            try:
                while (forward_queue or backward_queue) and visited_count < self.max_pages and not self.cancel_requested:
                    # Select direction for this iteration: alternate between forward and backward
                    if forward_queue and backward_queue:
                        turn_direction = "forward" if (visited_count % 2 == 0) else "backward"
                    elif forward_queue:
                        turn_direction = "forward"
                    else:
                        turn_direction = "backward"

                    # -------------------------------------------------------------
                    # TURN: FORWARD STEP (Expanding from Start side)
                    # -------------------------------------------------------------
                    if turn_direction == "forward":
                        if self.algorithm == "heuristic":
                            forward_queue.sort(key=lambda item: (-item[0], item[1]))
                        f_score, depth, current_slug, current_title, path_titles, path_slugs, path_steps = forward_queue.pop(0)

                        slug_key = current_slug.lower()
                        if slug_key in forward_visited:
                            continue

                        # Check meeting condition 1: current node already reached by backward search!
                        if slug_key in backward_visited:
                            b_node = backward_visited[slug_key]
                            final_path_titles = path_titles + b_node["path_titles"][1:]
                            final_path_slugs = path_slugs + b_node["path_slugs"][1:]
                            final_steps = path_steps + b_node["path_steps"]
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": current_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Both search frontiers met at '{current_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # Navigate to forward article
                        page_url = f"https://en.wikipedia.org/wiki/{current_slug}"
                        visited_count += 1
                        logger.info(f"Forward [{visited_count}/{self.max_pages}] (Depth {depth}): {current_title}")

                        try:
                            await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                        except Exception as nav_err:
                            logger.warning(f"Navigation error for {page_url}: {nav_err}")
                            continue

                        try:
                            real_title = await page.title()
                            clean_title = real_title.replace(" - Wikipedia", "").strip()
                        except Exception:
                            clean_title = current_title

                        lead_snippet = ""
                        try:
                            paragraphs = await page.eval_on_selector_all(
                                "#bodyContent p",
                                "elements => elements.map(e => e.innerText.trim()).filter(t => t.length > 40).slice(0, 2).join(' ')"
                            )
                            lead_snippet = paragraphs[:280] + ("..." if len(paragraphs) > 280 else "")
                        except Exception:
                            pass

                        screenshot_b64 = None
                        if self.capture_screenshots:
                            try:
                                screenshot_bytes = await page.screenshot(type="jpeg", quality=45)
                                screenshot_b64 = "data:image/jpeg;base64," + base64.b64encode(screenshot_bytes).decode("utf-8")
                            except Exception as shot_err:
                                logger.debug(f"Screenshot error: {shot_err}")

                        # Extract outgoing links and 15 words before/after
                        extracted_links: List[Dict[str, str]] = []
                        try:
                            extracted_links = await page.evaluate("""() => {
                                const body = document.querySelector('#bodyContent') || document.body;
                                const anchors = Array.from(body.querySelectorAll('a[href]'));
                                const results = [];
                                const seen = new Set();
                                const disallowedPrefixes = [
                                    'File:', 'Talk:', 'Special:', 'Wikipedia:', 'Help:',
                                    'Category:', 'Portal:', 'Template:', 'Template_talk:',
                                    'User:', 'User_talk:', 'MediaWiki:', 'Draft:', 'TimedText:', 'Module:', 'Book:'
                                ];

                                for (const a of anchors) {
                                    if (a.closest('style, script, .mw-editsection, #mw-navigation, #mw-panel, #p-lang, #footer, .vertical-navbox, .sistersitebox')) {
                                        continue;
                                    }
                                    const rawHref = a.getAttribute('href') || '';
                                    let slug = '';
                                    if (rawHref.startsWith('/wiki/')) slug = rawHref.substring(6);
                                    else if (rawHref.startsWith('https://en.wikipedia.org/wiki/')) slug = rawHref.substring(30);
                                    else continue;

                                    slug = slug.split('#')[0].split('?')[0];
                                    if (!slug || slug === 'Main_Page') continue;
                                    try { slug = decodeURIComponent(slug); } catch(e) {}
                                    if (disallowedPrefixes.some(p => slug.startsWith(p))) continue;

                                    const key = slug.toLowerCase();
                                    if (!seen.has(key)) {
                                        seen.add(key);
                                        const title = a.getAttribute('title') || a.innerText.trim() || slug.replace(/_/g, ' ');
                                        const anchorText = a.innerText.trim() || title;

                                        let wordsBefore = '';
                                        let wordsAfter = '';
                                        const block = a.closest('p, li, dd, dt, td, th') || a.parentElement;
                                        if (block) {
                                            try {
                                                const rangeBefore = document.createRange();
                                                rangeBefore.setStart(block, 0);
                                                rangeBefore.setEndBefore(a);
                                                const cloneB = rangeBefore.cloneContents();
                                                cloneB.querySelectorAll('style, script, .mw-editsection').forEach(e => e.remove());
                                                const beforeStr = cloneB.textContent.trim();
                                                const bTokens = beforeStr.split(/\\s+/).filter(Boolean);
                                                wordsBefore = bTokens.slice(-15).join(' ');

                                                const rangeAfter = document.createRange();
                                                rangeAfter.setStartAfter(a);
                                                rangeAfter.setEnd(block, block.childNodes.length);
                                                const cloneA = rangeAfter.cloneContents();
                                                cloneA.querySelectorAll('style, script, .mw-editsection').forEach(e => e.remove());
                                                const afterStr = cloneA.textContent.trim();
                                                const aTokens = afterStr.split(/\\s+/).filter(Boolean);
                                                wordsAfter = aTokens.slice(0, 15).join(' ');
                                            } catch(e) {}
                                        }

                                        results.push({
                                            slug: slug,
                                            title: title,
                                            anchor_text: anchorText,
                                            words_before: wordsBefore,
                                            words_after: wordsAfter
                                        });
                                    }
                                }
                                return results;
                            }""")
                        except Exception as link_err:
                            logger.warning(f"Error extracting links on {current_slug}: {link_err}")
                            extracted_links = []

                        forward_visited[slug_key] = {
                            "title": clean_title,
                            "slug": current_slug,
                            "depth": depth,
                            "path_titles": path_titles,
                            "path_slugs": path_slugs,
                            "path_steps": path_steps,
                        }

                        page_record = {
                            "step": visited_count,
                            "direction": "forward",
                            "title": clean_title,
                            "slug": current_slug,
                            "url": page_url,
                            "depth": depth,
                            "links_count": len(extracted_links),
                            "snippet": lead_snippet,
                            "screenshot": screenshot_b64,
                            "path_so_far": path_titles,
                        }
                        intermediate_pages.append(page_record)

                        yield {
                            "event": "visiting",
                            "direction": "forward",
                            "page": page_record,
                            "total_visited": visited_count,
                            "forward_visited_count": len(forward_visited),
                            "backward_visited_count": len(backward_visited),
                            "queue_size": len(forward_queue) + len(backward_queue),
                        }

                        # Check meeting condition on all outgoing links from this forward page
                        target_match = None
                        meeting_hit = None

                        for link in extracted_links:
                            l_slug = link["slug"].lower()
                            l_title = link["title"]

                            # Direct Target Discovery
                            if l_slug == target_slug_lower or l_title.lower() == target_info["title"].lower():
                                target_match = link
                                break

                            # Meeting with a node in backward_visited
                            if l_slug in backward_visited:
                                meeting_hit = (link, backward_visited[l_slug])
                                break

                            # Meeting with a node in backward_incoming
                            if l_slug in backward_incoming:
                                b_inc = backward_incoming[l_slug]
                                meeting_hit = (link, b_inc)
                                break

                        # 1. Direct Target Discovery
                        if target_match:
                            matched_title = target_match["title"] or target_info["title"]
                            final_path_titles = path_titles + [matched_title]
                            final_path_slugs = path_slugs + [target_match["slug"]]
                            hops = len(final_path_titles) - 1

                            final_step = {
                                "from_title": clean_title,
                                "from_slug": current_slug,
                                "from_url": page_url,
                                "to_title": matched_title,
                                "to_slug": target_match["slug"],
                                "to_url": f"https://en.wikipedia.org/wiki/{target_match['slug']}",
                                "anchor_text": target_match.get("anchor_text", matched_title),
                                "words_before": target_match.get("words_before", ""),
                                "words_after": target_match.get("words_after", ""),
                                "hop": hops,
                                "score": 10000.0,
                                "is_feeder": False,
                                "badge": "🎯 Target Discovered",
                                "badge_class": "bg-success text-white",
                                "reasons": [
                                    f"Direct live hyperlink to '{matched_title}' discovered on '{clean_title}'",
                                    "Target destination reached",
                                ],
                                "explanation": f"Goal reached! Playwright navigated to '{clean_title}' and found an active internal hyperlink pointing directly to '{matched_title}'.",
                            }
                            final_steps = path_steps + [final_step]
                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, current_slug, target_match["slug"], matched_title, self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": clean_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Found link '{matched_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # 2. Meeting Frontier Collision!
                        if meeting_hit:
                            meeting_link, b_target = meeting_hit
                            meeting_title = meeting_link["title"]
                            bridge_step = {
                                "from_title": clean_title,
                                "from_slug": current_slug,
                                "from_url": page_url,
                                "to_title": meeting_title,
                                "to_slug": meeting_link["slug"],
                                "to_url": f"https://en.wikipedia.org/wiki/{meeting_link['slug']}",
                                "anchor_text": meeting_link.get("anchor_text", meeting_title),
                                "words_before": meeting_link.get("words_before", ""),
                                "words_after": meeting_link.get("words_after", ""),
                                "hop": depth + 1,
                                "score": 9999.0,
                                "is_feeder": True,
                                "badge": "🤝 Meeting Bridge",
                                "badge_class": "bg-warning text-dark",
                                "reasons": [
                                    "Simultaneous bidirectional frontier intersection",
                                    f"Forward search from '{start_info['title']}' met reverse search from '{target_info['title']}'",
                                ],
                                "explanation": f"Meeting point reached! Playwright forward search from '{start_info['title']}' intersected with the reverse search from '{target_info['title']}' on '{meeting_title}'.",
                            }

                            final_path_titles = path_titles + [meeting_title] + b_target["path_titles"][1:]
                            final_path_slugs = path_slugs + [meeting_link["slug"]] + b_target["path_slugs"][1:]
                            final_steps = path_steps + [bridge_step] + b_target["path_steps"]
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": meeting_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Both search frontiers met at '{meeting_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # Enqueue forward children
                        if depth < self.max_depth:
                            scored_candidates = []
                            for link in extracted_links:
                                c_slug = link["slug"]
                                c_slug_key = c_slug.lower()
                                if c_slug_key in forward_visited:
                                    continue

                                c_title = link["title"]
                                link_score, is_feeder, reasons, badge, badge_class, explanation = compute_relevance_score(
                                    c_title,
                                    c_slug,
                                    target_info["title"],
                                    target_info["slug"],
                                    target_keywords,
                                    target_backlinks,
                                    depth=depth + 1,
                                    algorithm=self.algorithm,
                                )
                                step_data = {
                                    "from_title": clean_title,
                                    "from_slug": current_slug,
                                    "from_url": page_url,
                                    "to_title": c_title,
                                    "to_slug": c_slug,
                                    "to_url": f"https://en.wikipedia.org/wiki/{c_slug}",
                                    "anchor_text": link.get("anchor_text", c_title),
                                    "words_before": link.get("words_before", ""),
                                    "words_after": link.get("words_after", ""),
                                    "hop": depth + 1,
                                    "score": round(link_score, 1),
                                    "is_feeder": is_feeder,
                                    "badge": badge,
                                    "badge_class": badge_class,
                                    "reasons": reasons,
                                    "explanation": explanation,
                                }
                                forward_outgoing[c_slug_key] = {
                                    "from_slug": current_slug,
                                    "from_title": clean_title,
                                    "step_info": step_data,
                                    "path_titles": path_titles + [c_title],
                                    "path_slugs": path_slugs + [c_slug],
                                    "path_steps": path_steps + [step_data],
                                }
                                scored_candidates.append((link_score, c_slug, c_title, step_data))

                            scored_candidates.sort(key=lambda x: x[0], reverse=True)
                            branch_limit = 20 if self.algorithm == "heuristic" else 12
                            for l_score, c_slug, c_title, step_data in scored_candidates[:branch_limit]:
                                forward_queue.append((
                                    l_score,
                                    depth + 1,
                                    c_slug,
                                    c_title,
                                    path_titles + [c_title],
                                    path_slugs + [c_slug],
                                    path_steps + [step_data],
                                ))

                    # -------------------------------------------------------------
                    # TURN: BACKWARD STEP (Expanding from Target side)
                    # -------------------------------------------------------------
                    else:
                        if self.algorithm == "heuristic":
                            backward_queue.sort(key=lambda item: (-item[0], item[1]))
                        b_score, depth, current_slug, current_title, path_titles, path_slugs, path_steps = backward_queue.pop(0)

                        slug_key = current_slug.lower()
                        if slug_key in backward_visited:
                            continue

                        # Check meeting condition 1: current backward node was already visited in forward search!
                        if slug_key in forward_visited:
                            f_node = forward_visited[slug_key]
                            final_path_titles = f_node["path_titles"] + path_titles[1:]
                            final_path_slugs = f_node["path_slugs"] + path_slugs[1:]
                            final_steps = f_node["path_steps"] + path_steps
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": current_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Both search frontiers met at '{current_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # Check meeting condition 2: an already-visited forward page had an outgoing link to current_slug!
                        if slug_key in forward_outgoing:
                            f_out = forward_outgoing[slug_key]
                            bridge_step = f_out["step_info"]
                            bridge_step["badge"] = "🤝 Meeting Bridge"
                            bridge_step["badge_class"] = "bg-warning text-dark"
                            bridge_step["explanation"] = f"Frontiers met! Forward search from '{start_info['title']}' connected with reverse search from '{target_info['title']}' on '{current_title}'."

                            final_path_titles = f_out["path_titles"] + path_titles[1:]
                            final_path_slugs = f_out["path_slugs"] + path_slugs[1:]
                            final_steps = f_out["path_steps"] + path_steps
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": current_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Both search frontiers met at '{current_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # Navigate to backward article
                        page_url = f"https://en.wikipedia.org/wiki/{current_slug}"
                        visited_count += 1
                        logger.info(f"Backward [{visited_count}/{self.max_pages}] (Depth {depth}): {current_title}")

                        try:
                            await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                        except Exception as nav_err:
                            logger.warning(f"Navigation error for {page_url}: {nav_err}")
                            continue

                        try:
                            real_title = await page.title()
                            clean_title = real_title.replace(" - Wikipedia", "").strip()
                        except Exception:
                            clean_title = current_title

                        lead_snippet = ""
                        try:
                            paragraphs = await page.eval_on_selector_all(
                                "#bodyContent p",
                                "elements => elements.map(e => e.innerText.trim()).filter(t => t.length > 40).slice(0, 2).join(' ')"
                            )
                            lead_snippet = paragraphs[:280] + ("..." if len(paragraphs) > 280 else "")
                        except Exception:
                            pass

                        screenshot_b64 = None
                        if self.capture_screenshots:
                            try:
                                screenshot_bytes = await page.screenshot(type="jpeg", quality=45)
                                screenshot_b64 = "data:image/jpeg;base64," + base64.b64encode(screenshot_bytes).decode("utf-8")
                            except Exception as shot_err:
                                logger.debug(f"Screenshot error: {shot_err}")

                        # Check if this backward node is the Start page!
                        if slug_key == start_slug_lower or clean_title.lower() == start_info["title"].lower():
                            final_path_titles = path_titles
                            final_path_slugs = path_slugs
                            final_steps = path_steps
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": current_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Reverse search traced back directly to '{start_info['title']}' after inspecting {visited_count} total pages.",
                            }
                            return

                        # Fetch incoming backlinks to this node (pages that link TO this node)
                        incoming_backlinks = await get_page_backlinks(page, current_slug, limit=120)

                        backward_visited[slug_key] = {
                            "title": clean_title,
                            "slug": current_slug,
                            "depth": depth,
                            "path_titles": path_titles,
                            "path_slugs": path_slugs,
                            "path_steps": path_steps,
                        }

                        page_record = {
                            "step": visited_count,
                            "direction": "backward",
                            "title": clean_title,
                            "slug": current_slug,
                            "url": page_url,
                            "depth": depth,
                            "links_count": len(incoming_backlinks),
                            "snippet": lead_snippet,
                            "screenshot": screenshot_b64,
                            "path_so_far": path_titles,
                        }
                        intermediate_pages.append(page_record)

                        yield {
                            "event": "visiting",
                            "direction": "backward",
                            "page": page_record,
                            "total_visited": visited_count,
                            "forward_visited_count": len(forward_visited),
                            "backward_visited_count": len(backward_visited),
                            "queue_size": len(forward_queue) + len(backward_queue),
                        }

                        # Check meeting condition on incoming backlinks
                        start_hit = None
                        forward_hit = None

                        for inc in incoming_backlinks:
                            inc_slug = inc["slug"].lower()
                            inc_title = inc["title"]

                            # Direct Start hit
                            if inc_slug == start_slug_lower or inc_title.lower() == start_info["title"].lower():
                                start_hit = inc
                                break

                            # Matches a node in forward_visited
                            if inc_slug in forward_visited:
                                forward_hit = (inc, forward_visited[inc_slug])
                                break

                            # Matches a forward outgoing link
                            if inc_slug in forward_outgoing:
                                forward_hit = (inc, forward_outgoing[inc_slug])
                                break

                        # 1. Start links directly to this backward node!
                        if start_hit:
                            bridge_step = {
                                "from_title": start_info["title"],
                                "from_slug": start_info["slug"],
                                "from_url": start_info["url"],
                                "to_title": clean_title,
                                "to_slug": current_slug,
                                "to_url": page_url,
                                "anchor_text": start_hit.get("title", clean_title),
                                "words_before": "",
                                "words_after": "",
                                "hop": 1,
                                "score": 9999.0,
                                "is_feeder": True,
                                "badge": "🤝 Meeting Bridge",
                                "badge_class": "bg-warning text-dark",
                                "reasons": [
                                    "Simultaneous bidirectional frontier intersection",
                                    f"Start article '{start_info['title']}' contains direct link to reverse feeder '{clean_title}'",
                                ],
                                "explanation": f"Meeting point reached! '{start_info['title']}' directly connects into reverse feeder '{clean_title}'.",
                            }

                            final_path_titles = [start_info["title"]] + path_titles
                            final_path_slugs = [start_info["slug"]] + path_slugs
                            final_steps = [bridge_step] + path_steps
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": clean_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Both search frontiers met at '{clean_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # 2. Meeting with forward frontier!
                        if forward_hit:
                            inc_item, f_match = forward_hit
                            inc_title = inc_item["title"]
                            bridge_step = {
                                "from_title": inc_title,
                                "from_slug": inc_item["slug"],
                                "from_url": f"https://en.wikipedia.org/wiki/{inc_item['slug']}",
                                "to_title": clean_title,
                                "to_slug": current_slug,
                                "to_url": page_url,
                                "anchor_text": inc_item.get("title", clean_title),
                                "words_before": "",
                                "words_after": "",
                                "hop": depth + 1,
                                "score": 9999.0,
                                "is_feeder": True,
                                "badge": "🤝 Meeting Bridge",
                                "badge_class": "bg-warning text-dark",
                                "reasons": [
                                    "Simultaneous bidirectional frontier intersection",
                                    f"Forward frontier met backward feeder '{clean_title}' via '{inc_title}'",
                                ],
                                "explanation": f"Meeting point reached! Forward frontier on '{inc_title}' connected with reverse search feeder '{clean_title}'.",
                            }

                            final_path_titles = f_match["path_titles"] + path_titles
                            final_path_slugs = f_match["path_slugs"] + path_slugs
                            final_steps = f_match["path_steps"] + [bridge_step] + path_steps
                            hops = len(final_path_titles) - 1

                            for idx, s in enumerate(final_steps):
                                s["hop"] = idx + 1

                            ctx = await extract_target_link_context(
                                page, final_path_slugs[-2], final_path_slugs[-1], final_path_titles[-1], self.context_words
                            )

                            yield {
                                "event": "found",
                                "hops": hops,
                                "path": final_path_titles,
                                "slugs": final_path_slugs,
                                "urls": [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs],
                                "total_visited": visited_count,
                                "forward_visited_count": len(forward_visited),
                                "backward_visited_count": len(backward_visited),
                                "intermediate_pages": intermediate_pages,
                                "intermediate_steps": final_steps,
                                "found_on_page": clean_title,
                                "link_context": ctx,
                                "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Both search frontiers met at '{clean_title}' after inspecting {visited_count} total pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                            }
                            return

                        # Enqueue backward parents (pages that link into this node)
                        if depth < self.max_depth:
                            scored_parents = []
                            for inc in incoming_backlinks:
                                p_slug = inc["slug"]
                                p_slug_key = p_slug.lower()
                                if p_slug_key in backward_visited:
                                    continue

                                p_title = inc["title"]
                                # In reverse search, score incoming pages by relevance TOWARDS Start
                                link_score, is_feeder, reasons, badge, badge_class, explanation = compute_relevance_score(
                                    p_title,
                                    p_slug,
                                    start_info["title"],
                                    start_info["slug"],
                                    start_keywords,
                                    target_backlinks=set(),
                                    depth=depth + 1,
                                    algorithm=self.algorithm,
                                )

                                # Badge indicating reverse feeder
                                if "Target Match" in badge:
                                    badge = "⭐ Start Connector"
                                    badge_class = "bg-warning text-dark"
                                elif "Global Connector Hub" in badge:
                                    badge = "🌐 Global Reverse Hub"
                                else:
                                    badge = "⏪ Reverse Feeder"
                                    badge_class = "bg-info text-dark"

                                step_data = {
                                    "from_title": p_title,
                                    "from_slug": p_slug,
                                    "from_url": f"https://en.wikipedia.org/wiki/{p_slug}",
                                    "to_title": clean_title,
                                    "to_slug": current_slug,
                                    "to_url": page_url,
                                    "anchor_text": p_title,
                                    "words_before": "",
                                    "words_after": "",
                                    "hop": depth + 1,
                                    "score": round(link_score, 1),
                                    "is_feeder": True,
                                    "badge": badge,
                                    "badge_class": badge_class,
                                    "reasons": reasons + ["Reverse feeder leading towards target article"],
                                    "explanation": f"Reverse graph search: '{p_title}' links directly into '{clean_title}', building an incoming path towards '{target_info['title']}'.",
                                }

                                backward_incoming[p_slug_key] = {
                                    "parent_slug": p_slug,
                                    "parent_title": p_title,
                                    "step_info": step_data,
                                    "path_titles": [p_title] + path_titles,
                                    "path_slugs": [p_slug] + path_slugs,
                                    "path_steps": [step_data] + path_steps,
                                }
                                scored_parents.append((link_score, p_slug, p_title, step_data))

                            scored_parents.sort(key=lambda x: x[0], reverse=True)
                            branch_limit = 20 if self.algorithm == "heuristic" else 12
                            for l_score, p_slug, p_title, step_data in scored_parents[:branch_limit]:
                                backward_queue.append((
                                    l_score,
                                    depth + 1,
                                    p_slug,
                                    p_title,
                                    [p_title] + path_titles,
                                    [p_slug] + path_slugs,
                                    [step_data] + path_steps,
                                ))

                    await asyncio.sleep(0.02)

                if self.cancel_requested:
                    yield {
                        "event": "cancelled",
                        "total_visited": visited_count,
                        "forward_visited_count": len(forward_visited),
                        "backward_visited_count": len(backward_visited),
                        "intermediate_pages": intermediate_pages,
                        "message": f"Search cancelled by user after visiting {visited_count} pages ({len(forward_visited)} forward + {len(backward_visited)} backward).",
                    }
                else:
                    yield {
                        "event": "not_found",
                        "total_visited": visited_count,
                        "forward_visited_count": len(forward_visited),
                        "backward_visited_count": len(backward_visited),
                        "max_pages": self.max_pages,
                        "intermediate_pages": intermediate_pages,
                        "message": f"Reached maximum page limit ({self.max_pages} pages) without meeting. Try increasing the page limit.",
                    }

            finally:
                try:
                    await page.close()
                    await context.close()
                    await browser.close()
                except Exception as close_err:
                    logger.debug(f"Browser close cleanup: {close_err}")

