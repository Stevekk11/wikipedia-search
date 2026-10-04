"""
Wikipedia Link Hop Crawler using Playwright.
Navigates Wikipedia pages to find the shortest or heuristic link path
between two articles, reports intermediate visited pages in real-time,
and extracts 150 words of context before and after the connecting links.

Features Bidirectional Backlinks-Guided Search (Meet-in-the-Middle),
Target Category Semantic Weighting, and High-Centrality Hub Prioritization.
"""

import asyncio
import base64
import html
import logging
import re
import urllib.parse
from typing import AsyncGenerator, Dict, List, Optional, Set, Tuple
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
) -> Tuple[float, bool]:
    """
    Advanced heuristic score for a candidate link:
    - Target Backlinks Hit (guaranteed 1 hop to target): +5000 points!
    - Exact/Substring match: +1000 / +150 points
    - Token overlap: +120 points per token
    - Category & context overlap: +15 points per keyword
    - High-Centrality global connector hubs: +45 points
    - Narrow dead-end penalties (local roads, specific schools): -30 to -50 points
    - Slight depth penalty to prefer shorter branches
    Returns: (score, is_backlink_hit)
    """
    link_lower = link_title.lower()
    slug_lower = link_slug.lower()
    target_lower = target_title.lower()
    target_s_lower = target_slug.lower()

    # 1. Direct Target Match
    if target_lower == link_lower or target_s_lower == slug_lower:
        return 10000.0, False

    # 2. Backlink Hit: Candidate links DIRECTLY to target!
    is_backlink_hit = (slug_lower in target_backlinks or link_lower in target_backlinks)
    if is_backlink_hit:
        return 5000.0 - (depth * 10.0), True

    score = 0.0

    # 3. Substring match
    if target_lower in link_lower or target_s_lower in slug_lower:
        score += 150.0
    elif link_lower in target_lower or slug_lower in target_s_lower:
        score += 90.0

    # 4. Token overlap with target title and slug
    target_tokens = set(re.findall(r"\w+", target_lower + " " + target_s_lower.replace("_", " ")))
    link_tokens = set(re.findall(r"\w+", link_lower + " " + slug_lower.replace("_", " ")))
    overlap = target_tokens.intersection(link_tokens)
    score += len(overlap) * 120.0

    # 5. Overlap with target categories & summary keywords
    keyword_overlap = target_keywords.intersection(link_tokens)
    score += len(keyword_overlap) * 16.0

    # 6. High-Centrality Hubs
    if slug_lower in HIGH_CENTRALITY_HUBS or any(slug_lower == h for h in HIGH_CENTRALITY_HUBS):
        score += 45.0

    # 7. Penalize dead-end narrow topics (highways, elementary schools, etc.)
    for pattern in DEAD_END_PATTERNS:
        if pattern in link_lower or pattern in slug_lower:
            score -= 40.0
            break

    if any(slug_lower.startswith(p) for p in ["list_of", "timeline_of"]):
        score -= 25.0

    # 8. Slight depth penalty so shallower discoveries are preferred
    score -= depth * 5.0

    return score, False


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


class WikipediaCrawler:
    """
    Orchestrates the Wikipedia hop counting traversal using Playwright
    with bidirectional target backlinks guidance and semantic scoring.
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
        self.max_pages = max(5, min(max_pages, 100))
        self.max_depth = max(1, min(max_depth, 6))
        self.headless = headless
        self.capture_screenshots = capture_screenshots
        self.context_words = max(20, min(context_words, 500))
        self.cancel_requested = False

    def cancel(self):
        """Signal the crawler to cancel traversal."""
        self.cancel_requested = True

    async def search(self) -> AsyncGenerator[Dict, None]:
        """Executes the search and yields JSON-serializable event dicts."""
        start_info = get_wikipedia_info(self.start_input)
        target_info = get_wikipedia_info(self.target_input)

        if not start_info["slug"] or not target_info["slug"]:
            yield {
                "event": "error",
                "message": "Invalid start or target page provided.",
            }
            return

        # Fetch Target Backlinks (Meet-in-the-Middle Guidance) and Categories in parallel
        target_backlinks: Set[str] = set()
        target_keywords: Set[str] = set()

        if self.algorithm == "heuristic":
            # Run backlinks and categories in background threads
            loop = asyncio.get_running_loop()
            backlinks_future = loop.run_in_executor(None, fetch_target_backlinks, target_info["slug"], 1000)
            categories_future = loop.run_in_executor(None, fetch_target_categories, target_info["slug"])
            target_backlinks, target_categories = await asyncio.gather(backlinks_future, categories_future)
            target_keywords.update(target_categories)

        if target_info.get("extract"):
            target_keywords.update(re.findall(r"\w+", target_info["extract"].lower()))
        if target_info.get("description"):
            target_keywords.update(re.findall(r"\w+", target_info["description"].lower()))
        target_keywords = {w for w in target_keywords if len(w) > 3}

        logger.info(f"Target '{target_info['title']}' loaded with {len(target_backlinks)} backlinks and {len(target_keywords)} context keywords")

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

        # Check trivial case: Start == Target
        if start_info["slug"].lower() == target_info["slug"].lower():
            yield {
                "event": "found",
                "hops": 0,
                "path": [start_info["title"]],
                "slugs": [start_info["slug"]],
                "urls": [start_info["url"]],
                "total_visited": 1,
                "intermediate_pages": [],
                "link_context": None,
                "message": "Start and target pages are identical! 0 hops required.",
            }
            return

        # Traversal bookkeeping
        visited_slugs: Set[str] = set()
        intermediate_pages: List[Dict] = []
        
        # Queue item: (score, depth, current_slug, current_title, path_titles, path_slugs, is_backlink_hit)
        queue: List[Tuple[float, int, str, str, List[str], List[str], bool]] = [
            (0.0, 0, start_info["slug"], start_info["title"], [start_info["title"]], [start_info["slug"]], False)
        ]

        target_slug_lower = target_info["slug"].lower()
        target_title_lower = target_info["title"].lower()

        async with async_playwright() as p:
            browser = await launch_playwright_browser(p, headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            )
            page = await context.new_page()

            visited_count = 0

            try:
                while queue and visited_count < self.max_pages and not self.cancel_requested:
                    if self.algorithm == "heuristic":
                        queue.sort(key=lambda item: (-item[0], item[1]))
                        score, depth, current_slug, current_title, path_titles, path_slugs, was_backlink_hit = queue.pop(0)
                    else:
                        score, depth, current_slug, current_title, path_titles, path_slugs, was_backlink_hit = queue.pop(0)

                    slug_key = current_slug.lower()
                    if slug_key in visited_slugs:
                        continue
                    visited_slugs.add(slug_key)
                    visited_count += 1

                    page_url = f"https://en.wikipedia.org/wiki/{current_slug}"
                    logger.info(f"Visiting [{visited_count}/{self.max_pages}] (Hop {depth}): {current_title} {'⭐[Direct Feeder]' if was_backlink_hit else ''}")

                    # Navigate via Playwright
                    try:
                        await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                    except Exception as nav_err:
                        logger.warning(f"Navigation error for {page_url}: {nav_err}")
                        continue

                    # Extract page title
                    try:
                        real_title = await page.title()
                        clean_title = real_title.replace(" - Wikipedia", "").strip()
                    except Exception:
                        clean_title = current_title

                    # Extract lead snippet
                    lead_snippet = ""
                    try:
                        paragraphs = await page.eval_on_selector_all(
                            "#bodyContent p",
                            "elements => elements.map(e => e.innerText.trim()).filter(t => t.length > 40).slice(0, 2).join(' ')"
                        )
                        lead_snippet = paragraphs[:280] + ("..." if len(paragraphs) > 280 else "")
                    except Exception:
                        pass

                    # Capture screenshot thumbnail
                    screenshot_b64 = None
                    if self.capture_screenshots:
                        try:
                            screenshot_bytes = await page.screenshot(type="jpeg", quality=45)
                            screenshot_b64 = "data:image/jpeg;base64," + base64.b64encode(screenshot_bytes).decode("utf-8")
                        except Exception as shot_err:
                            logger.debug(f"Screenshot error: {shot_err}")

                    # Extract valid internal links inside main article body
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
                                if (a.closest('#mw-navigation, #mw-panel, #p-lang, #footer, .vertical-navbox, .sistersitebox')) {
                                    continue;
                                }
                                const rawHref = a.getAttribute('href') || '';
                                let slug = '';
                                if (rawHref.startsWith('/wiki/')) {
                                    slug = rawHref.substring(6);
                                } else if (rawHref.startsWith('https://en.wikipedia.org/wiki/')) {
                                    slug = rawHref.substring(30);
                                } else {
                                    continue;
                                }

                                slug = slug.split('#')[0].split('?')[0];
                                if (!slug || slug === 'Main_Page') continue;
                                
                                try {
                                    slug = decodeURIComponent(slug);
                                } catch(e) {}

                                if (disallowedPrefixes.some(p => slug.startsWith(p))) continue;

                                const key = slug.toLowerCase();
                                if (!seen.has(key)) {
                                    seen.add(key);
                                    const title = a.getAttribute('title') || a.innerText.trim() || slug.replace(/_/g, ' ');
                                    results.push({ slug, title });
                                }
                            }
                            return results;
                        }""")
                    except Exception as link_err:
                        logger.warning(f"Error extracting links on {current_slug}: {link_err}")
                        extracted_links = []

                    page_record = {
                        "step": visited_count,
                        "title": clean_title,
                        "slug": current_slug,
                        "url": page_url,
                        "depth": depth,
                        "links_count": len(extracted_links),
                        "snippet": lead_snippet,
                        "screenshot": screenshot_b64,
                        "path_so_far": path_titles,
                        "is_feeder": was_backlink_hit,
                    }
                    intermediate_pages.append(page_record)

                    # Emit visiting event
                    yield {
                        "event": "visiting",
                        "page": page_record,
                        "total_visited": visited_count,
                        "queue_size": len(queue),
                    }

                    # CHECK TARGET MATCH: Is target among the links on this page?
                    target_match = None
                    for link in extracted_links:
                        l_slug = link["slug"].lower()
                        l_title = link["title"].lower()
                        if (
                            l_slug == target_slug_lower
                            or l_title == target_title_lower
                            or l_slug == target_title_lower.replace(" ", "_")
                        ):
                            target_match = link
                            break

                    if target_match:
                        matched_title = target_match["title"] or target_info["title"]
                        final_path_titles = path_titles + [matched_title]
                        final_path_slugs = path_slugs + [target_match["slug"]]
                        final_urls = [f"https://en.wikipedia.org/wiki/{s}" for s in final_path_slugs]
                        hops = len(final_path_titles) - 1

                        # EXTRACT CONTEXT (150 words before and 150 words after the target link)
                        extracted_context = None
                        try:
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

                                    // Bidirectional TreeWalker starting at targetAnchor
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
                                    "targetSlug": target_match["slug"],
                                    "wordsBeforeCount": self.context_words,
                                    "wordsAfterCount": self.context_words,
                                }
                            )
                        except Exception as ctx_err:
                            logger.warning(f"Error extracting link context: {ctx_err}")

                        link_context = {
                            "source_title": clean_title,
                            "source_slug": current_slug,
                            "source_url": page_url,
                            "target_title": matched_title,
                            "target_slug": target_match["slug"],
                            "target_url": f"https://en.wikipedia.org/wiki/{target_match['slug']}",
                            "words_before": extracted_context.get("wordsBefore", "") if extracted_context else "",
                            "anchor_text": extracted_context.get("anchorText", matched_title) if extracted_context else matched_title,
                            "words_after": extracted_context.get("wordsAfter", "") if extracted_context else "",
                            "before_count": extracted_context.get("beforeCount", 0) if extracted_context else 0,
                            "after_count": extracted_context.get("afterCount", 0) if extracted_context else 0,
                            "requested_words": self.context_words,
                        }

                        yield {
                            "event": "found",
                            "hops": hops,
                            "path": final_path_titles,
                            "slugs": final_path_slugs,
                            "urls": final_urls,
                            "total_visited": visited_count,
                            "intermediate_pages": intermediate_pages,
                            "found_on_page": clean_title,
                            "link_context": link_context,
                            "message": f"Target reached in {hops} hop{'s' if hops != 1 else ''}! Found link '{matched_title}' after inspecting {visited_count} intermediate pages.",
                        }
                        return

                    # Enqueue candidate children
                    if depth < self.max_depth:
                        scored_candidates = []
                        for link in extracted_links:
                            c_slug = link["slug"]
                            if c_slug.lower() in visited_slugs:
                                continue
                            c_title = link["title"]
                            link_score, is_feeder = compute_relevance_score(
                                c_title,
                                c_slug,
                                target_info["title"],
                                target_info["slug"],
                                target_keywords,
                                target_backlinks,
                                depth=depth + 1,
                            )
                            scored_candidates.append((link_score, c_slug, c_title, is_feeder))

                        # Sort children by relevance
                        scored_candidates.sort(key=lambda x: x[0], reverse=True)

                        # Enqueue top candidates
                        branch_limit = 25 if self.algorithm == "heuristic" else 15
                        for l_score, c_slug, c_title, is_feeder in scored_candidates[:branch_limit]:
                            queue.append((
                                l_score,
                                depth + 1,
                                c_slug,
                                c_title,
                                path_titles + [c_title],
                                path_slugs + [c_slug],
                                is_feeder,
                            ))

                    await asyncio.sleep(0.02)

                if self.cancel_requested:
                    yield {
                        "event": "cancelled",
                        "total_visited": visited_count,
                        "intermediate_pages": intermediate_pages,
                        "message": f"Search cancelled by user after visiting {visited_count} pages.",
                    }
                else:
                    yield {
                        "event": "not_found",
                        "total_visited": visited_count,
                        "max_pages": self.max_pages,
                        "intermediate_pages": intermediate_pages,
                        "message": f"Reached maximum page limit ({self.max_pages} pages) without finding a direct link to target. Try increasing the page limit.",
                    }

            finally:
                try:
                    await page.close()
                    await context.close()
                    await browser.close()
                except Exception as close_err:
                    logger.debug(f"Browser close cleanup: {close_err}")
