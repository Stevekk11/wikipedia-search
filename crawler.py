"""
Wikipedia Link Hop Crawler using Playwright.
Navigates Wikipedia pages to find the shortest or heuristic link path
between two articles, reports intermediate visited pages in real-time,
and extracts 150 words of context before and after the connecting links.
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
        "User-Agent": "WikipediaHopFinder/1.0 (https://github.com/example/wikipedia-search; contact@example.com)"
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


def compute_relevance_score(
    link_title: str, link_slug: str, target_title: str, target_slug: str, target_keywords: Set[str]
) -> float:
    """
    Score a candidate link based on relevance to the target page.
    """
    score = 0.0
    link_lower = link_title.lower()
    slug_lower = link_slug.lower()
    target_lower = target_title.lower()
    target_s_lower = target_slug.lower()

    if target_lower == link_lower or target_s_lower == slug_lower:
        return 1000.0
    
    if target_lower in link_lower or target_s_lower in slug_lower:
        score += 150.0
    elif link_lower in target_lower or slug_lower in target_s_lower:
        score += 90.0

    target_tokens = set(re.findall(r"\w+", target_lower))
    link_tokens = set(re.findall(r"\w+", link_lower + " " + slug_lower.replace("_", " ")))
    overlap = target_tokens.intersection(link_tokens)
    score += len(overlap) * 40.0

    keyword_overlap = target_keywords.intersection(link_tokens)
    score += len(keyword_overlap) * 12.0

    hubs = {
        "united_states", "united_kingdom", "europe", "north_america", "asia", 
        "world", "earth", "country", "city", "history", "geography", "government",
        "economy", "culture", "science", "technology", "transport", "international",
        "london", "new_york_city"
    }
    if slug_lower in hubs or any(slug_lower == h for h in hubs):
        score += 15.0

    return score


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
    Orchestrates the Wikipedia hop counting traversal using Playwright.
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

        yield {
            "event": "started",
            "start": start_info,
            "target": target_info,
            "algorithm": self.algorithm,
            "max_pages": self.max_pages,
            "max_depth": self.max_depth,
            "context_words": self.context_words,
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

        # Prepare target keywords for heuristic
        target_keywords: Set[str] = set()
        if target_info.get("extract"):
            target_keywords.update(re.findall(r"\w+", target_info["extract"].lower()))
        if target_info.get("description"):
            target_keywords.update(re.findall(r"\w+", target_info["description"].lower()))
        target_keywords = {w for w in target_keywords if len(w) > 3}

        # Traversal bookkeeping
        visited_slugs: Set[str] = set()
        intermediate_pages: List[Dict] = []
        
        # Queue item: (score, depth, current_slug, current_title, path_titles, path_slugs)
        queue: List[Tuple[float, int, str, str, List[str], List[str]]] = [
            (0.0, 0, start_info["slug"], start_info["title"], [start_info["title"]], [start_info["slug"]])
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
                        score, depth, current_slug, current_title, path_titles, path_slugs = queue.pop(0)
                    else:
                        score, depth, current_slug, current_title, path_titles, path_slugs = queue.pop(0)

                    slug_key = current_slug.lower()
                    if slug_key in visited_slugs:
                        continue
                    visited_slugs.add(slug_key)
                    visited_count += 1

                    page_url = f"https://en.wikipedia.org/wiki/{current_slug}"
                    logger.info(f"Visiting [{visited_count}/{self.max_pages}] (Hop {depth}): {current_title}")

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
                                    
                                    // Locate the anchor tag
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
                            link_score = compute_relevance_score(
                                c_title, c_slug, target_info["title"], target_info["slug"], target_keywords
                            )
                            scored_candidates.append((link_score, c_slug, c_title))

                        scored_candidates.sort(key=lambda x: x[0], reverse=True)

                        branch_limit = 25 if self.algorithm == "heuristic" else 15
                        for l_score, c_slug, c_title in scored_candidates[:branch_limit]:
                            queue.append((
                                l_score,
                                depth + 1,
                                c_slug,
                                c_title,
                                path_titles + [c_title],
                                path_slugs + [c_slug],
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
