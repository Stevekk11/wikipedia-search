"""
Wikipedia link hop crawler engine using Playwright.
Orchestrates simultaneous bidirectional meet-in-the-middle search,
coordinates forward and reverse queues, checks frontier intersections,
and yields real-time streaming events.
"""

import asyncio
import logging
import re
from typing import TYPE_CHECKING, Any, AsyncGenerator, Dict, List, Optional, Set, Tuple

if TYPE_CHECKING:
    from playwright.async_api import Page

from .api import (
    fetch_article_assessments,
    fetch_target_backlinks,
    fetch_target_categories,
    get_wikipedia_info,
)
from .browser import launch_playwright_browser
from .extractor import (
    enrich_final_steps_context,
    extract_outgoing_links,
    extract_page_summary,
    extract_target_link_context,
    get_page_backlinks,
)
from .scorer import compute_relevance_score
from .semantic import prime_embeddings, warm_up

logger = logging.getLogger("wikipedia_crawler.engine")


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
        lang: str = "en",
    ):
        self.start_input = start_input
        self.target_input = target_input
        self.algorithm = algorithm.lower()
        self.max_pages = max(5, min(max_pages, 1000))
        self.max_depth = max(1, min(max_depth, 50))
        self.headless = headless
        self.capture_screenshots = capture_screenshots
        self.context_words = max(20, min(context_words, 500))
        self.lang = (lang or "en").strip().lower()
        self.cancel_requested = False

    def cancel(self):
        """Signal the crawler to cancel traversal."""
        self.cancel_requested = True

    async def _build_found_payload(
        self,
        page: Any,
        final_path_titles: List[str],
        final_path_slugs: List[str],
        final_steps: List[Dict],
        visited_count: int,
        forward_visited: Dict,
        backward_visited: Dict,
        intermediate_pages: List[Dict],
        found_on_page: str,
        message: str,
    ) -> Dict:
        """Helper to format the winning path, enrich context, and build the 'found' event."""
        hops = len(final_path_titles) - 1

        for idx, s in enumerate(final_steps):
            s["hop"] = idx + 1

        await enrich_final_steps_context(page, final_steps, lang=self.lang)

        source_slug = final_path_slugs[-2] if len(final_path_slugs) >= 2 else final_path_slugs[0]
        source_title = final_path_titles[-2] if len(final_path_titles) >= 2 else final_path_titles[0]
        target_slug = final_path_slugs[-1]
        target_title = final_path_titles[-1]

        ctx = await extract_target_link_context(
            page, source_slug, target_slug, target_title, self.context_words, source_title=source_title, lang=self.lang
        )

        assessments = fetch_article_assessments(final_path_titles, lang=self.lang)

        return {
            "event": "found",
            "hops": hops,
            "path": final_path_titles,
            "slugs": final_path_slugs,
            "urls": [f"https://{self.lang}.wikipedia.org/wiki/{s}" for s in final_path_slugs],
            "assessments": assessments,
            "total_visited": visited_count,
            "forward_visited_count": len(forward_visited),
            "backward_visited_count": len(backward_visited),
            "intermediate_pages": intermediate_pages,
            "intermediate_steps": final_steps,
            "found_on_page": found_on_page,
            "link_context": ctx,
            "message": message,
        }

    async def search(self) -> AsyncGenerator[Dict, None]:
        """Executes simultaneous bidirectional search and yields JSON-serializable events."""
        from playwright.async_api import async_playwright

        start_info = get_wikipedia_info(self.start_input, lang=self.lang)
        target_info = get_wikipedia_info(self.target_input, lang=self.lang)

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
            assessments = fetch_article_assessments([start_info["title"]], lang=self.lang)
            yield {
                "event": "found",
                "hops": 0,
                "path": [start_info["title"]],
                "slugs": [start_info["slug"]],
                "urls": [start_info["url"]],
                "assessments": assessments,
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
            t_backlinks_fut = loop.run_in_executor(None, fetch_target_backlinks, target_info["slug"], 500, self.lang)
            t_cats_fut = loop.run_in_executor(None, fetch_target_categories, target_info["slug"], self.lang)
            s_cats_fut = loop.run_in_executor(None, fetch_target_categories, start_info["slug"], self.lang)
            target_backlinks, target_categories, start_categories = await asyncio.gather(
                t_backlinks_fut, t_cats_fut, s_cats_fut
            )
            target_keywords.update(target_categories)
            start_keywords.update(start_categories)

        if target_info.get("extract"):
            target_keywords.update(re.findall(r"\w+", target_info["extract"].lower()))
        if start_info.get("extract"):
            start_keywords.update(re.findall(r"\w+", start_info["extract"].lower()))

        # Unfiltered context (categories + lead text + title) used to exempt dead-end
        # patterns that are actually relevant to the endpoint (e.g. "championship" for a skier)
        target_context: Set[str] = set(re.findall(r"\w+", " ".join(target_keywords).lower())) | set(
            re.findall(r"\w+", target_info["title"].lower())
        )
        start_context: Set[str] = set(re.findall(r"\w+", " ".join(start_keywords).lower())) | set(
            re.findall(r"\w+", start_info["title"].lower())
        )
        target_summary: str = target_info.get("extract") or target_info["title"]
        start_summary: str = start_info.get("extract") or start_info["title"]

        target_keywords = {w for w in target_keywords if len(w) > 3}
        start_keywords = {w for w in start_keywords if len(w) > 3}

        logger.info(
            f"Bidirectional search initialized: Start '{start_info['title']}' ({len(start_keywords)} keywords) <===> "
            f"Target '{target_info['title']}' ({len(target_keywords)} keywords, {len(target_backlinks)} pre-mapped backlinks)"
        )

        if self.algorithm == "heuristic":
            # Load the embedding model once, off the event loop (no-op if unavailable/disabled)
            await asyncio.get_running_loop().run_in_executor(None, warm_up)

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
        forward_visited: Dict[str, Dict] = {}
        backward_visited: Dict[str, Dict] = {}
        forward_outgoing: Dict[str, Dict] = {}
        backward_incoming: Dict[str, Dict] = {}

        intermediate_pages: List[Dict] = []

        # Forward Queue: (score, depth, slug, title, path_titles, path_slugs, path_steps)
        forward_queue: List[Tuple[float, int, str, str, List[str], List[str], List[Dict]]] = [
            (0.0, 0, start_info["slug"], start_info["title"], [start_info["title"]], [start_info["slug"]], [])
        ]

        # Backward Queue: (score, depth, slug, title, path_titles, path_slugs, path_steps)
        backward_queue: List[Tuple[float, int, str, str, List[str], List[str], List[Dict]]] = [
            (0.0, 0, target_info["slug"], target_info["title"], [target_info["title"]], [target_info["slug"]], [])
        ]

        visited_count = 0

        async with async_playwright() as p:
            browser = await launch_playwright_browser(p, headless=self.headless)
            context = await browser.new_context(
                viewport={"width": 1280, "height": 720},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
                ignore_https_errors=True,
            )
            page = await context.new_page()

            try:
                while (forward_queue or backward_queue) and visited_count < self.max_pages and not self.cancel_requested:
                    # Cardinality balancing: always expand the frontier with the smaller queue,
                    # so a small/starved side (e.g. obscure target with few incoming links)
                    # is exhausted immediately instead of waiting for alternating turns.
                    if forward_queue and backward_queue:
                        if len(forward_queue) < len(backward_queue):
                            turn_direction = "forward"
                        elif len(backward_queue) < len(forward_queue):
                            turn_direction = "backward"
                        else:
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

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Both search frontiers met at '{current_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                current_title, msg
                            )
                            return

                        # Navigate to forward article
                        page_url = f"https://{self.lang}.wikipedia.org/wiki/{current_slug}"
                        visited_count += 1
                        logger.info(f"Forward [{visited_count}/{self.max_pages}] (Depth {depth}): {current_title}")

                        try:
                            await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                        except Exception as nav_err:
                            logger.warning(f"Navigation error for {page_url}: {nav_err}")
                            continue

                        clean_title, lead_snippet, screenshot_b64 = await extract_page_summary(
                            page, current_title, capture_screenshots=self.capture_screenshots
                        )
                        extracted_links = await extract_outgoing_links(page)

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
                            "links_type": "outgoing",
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

                            if l_slug == target_slug_lower or l_title.lower() == target_info["title"].lower():
                                target_match = link
                                break

                            if l_slug in backward_visited:
                                meeting_hit = (link, backward_visited[l_slug])
                                break

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
                                "to_url": f"https://{self.lang}.wikipedia.org/wiki/{target_match['slug']}",
                                "section": target_match.get("section", "Lead / Introduction"),
                                "anchor_text": target_match.get("anchor_text", matched_title),
                                "words_before": target_match.get("words_before", ""),
                                "words_after": target_match.get("words_after", ""),
                                "hop": hops,
                                "score": 10000.0,
                                "is_feeder": False,
                                "badge": "🎯 Target Discovered",
                                "badge_class": "bg-success text-white",
                                "badges": [{"text": "🎯 Target Discovered", "class": "bg-success text-white"}],
                                "reasons": [
                                    f"Direct live hyperlink to '{matched_title}' discovered on '{clean_title}'",
                                    "Target destination reached",
                                ],
                                "explanation": f"Goal reached! Playwright navigated to '{clean_title}' and found an active internal hyperlink pointing directly to '{matched_title}'.",
                            }
                            final_steps = path_steps + [final_step]

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Found link '{matched_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                clean_title, msg
                            )
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
                                "to_url": f"https://{self.lang}.wikipedia.org/wiki/{meeting_link['slug']}",
                                "section": meeting_link.get("section", "Lead / Introduction"),
                                "anchor_text": meeting_link.get("anchor_text", meeting_title),
                                "words_before": meeting_link.get("words_before", ""),
                                "words_after": meeting_link.get("words_after", ""),
                                "hop": depth + 1,
                                "score": 9999.0,
                                "is_feeder": True,
                                "badge": "🤝 Meeting Bridge",
                                "badge_class": "bg-warning text-dark",
                                "badges": [
                                    {"text": "🤝 Meeting Bridge", "class": "bg-warning text-dark"},
                                    {"text": "Frontier Intersection", "class": "bg-primary-subtle text-primary border border-primary-subtle"},
                                ],
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

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Both search frontiers met at '{meeting_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                meeting_title, msg
                            )
                            return

                        # Enqueue forward children
                        if depth < self.max_depth:
                            if self.algorithm == "heuristic":
                                await asyncio.get_running_loop().run_in_executor(
                                    None, prime_embeddings, [l["title"] for l in extracted_links]
                                )
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
                                    target_context=target_context,
                                    target_summary=target_summary,
                                )
                                badges_list = [{"text": badge, "class": badge_class}]
                                step_data = {
                                    "from_title": clean_title,
                                    "from_slug": current_slug,
                                    "from_url": page_url,
                                    "to_title": c_title,
                                    "to_slug": c_slug,
                                    "to_url": f"https://{self.lang}.wikipedia.org/wiki/{c_slug}",
                                    "section": link.get("section", "Lead / Introduction"),
                                    "anchor_text": link.get("anchor_text", c_title),
                                    "words_before": link.get("words_before", ""),
                                    "words_after": link.get("words_after", ""),
                                    "hop": depth + 1,
                                    "score": round(link_score, 1),
                                    "is_feeder": is_feeder,
                                    "badge": badge,
                                    "badge_class": badge_class,
                                    "badges": badges_list,
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

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Both search frontiers met at '{current_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                current_title, msg
                            )
                            return

                        # Check meeting condition 2: an already-visited forward page had an outgoing link to current_slug!
                        if slug_key in forward_outgoing:
                            f_out = forward_outgoing[slug_key]
                            bridge_step = f_out["step_info"]
                            bridge_step["badge"] = "🤝 Meeting Bridge"
                            bridge_step["badge_class"] = "bg-warning text-dark"
                            bridge_step_badges = bridge_step.get("badges", [])
                            if not any("Meeting Bridge" in b.get("text", "") for b in bridge_step_badges):
                                bridge_step["badges"] = [{"text": "🤝 Meeting Bridge", "class": "bg-warning text-dark"}] + bridge_step_badges
                            bridge_step["explanation"] = f"Frontiers met! Forward search from '{start_info['title']}' connected with reverse search from '{target_info['title']}' on '{current_title}'."

                            final_path_titles = f_out["path_titles"] + path_titles[1:]
                            final_path_slugs = f_out["path_slugs"] + path_slugs[1:]
                            final_steps = f_out["path_steps"] + path_steps
                            hops = len(final_path_titles) - 1

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Both search frontiers met at '{current_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                current_title, msg
                            )
                            return

                        # Navigate to backward article
                        page_url = f"https://{self.lang}.wikipedia.org/wiki/{current_slug}"
                        visited_count += 1
                        logger.info(f"Backward [{visited_count}/{self.max_pages}] (Depth {depth}): {current_title}")

                        try:
                            await page.goto(page_url, wait_until="domcontentloaded", timeout=15000)
                        except Exception as nav_err:
                            logger.warning(f"Navigation error for {page_url}: {nav_err}")
                            continue

                        clean_title, lead_snippet, screenshot_b64 = await extract_page_summary(
                            page, current_title, capture_screenshots=self.capture_screenshots
                        )

                        # Check if this backward node is the Start page!
                        if slug_key == start_slug_lower or clean_title.lower() == start_info["title"].lower():
                            final_path_titles = path_titles
                            final_path_slugs = path_slugs
                            final_steps = path_steps
                            hops = len(final_path_titles) - 1

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Reverse search traced back directly to '{start_info['title']}' after inspecting {visited_count} total pages."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                current_title, msg
                            )
                            return

                        # Fetch incoming backlinks to this node (pages that link TO this node)
                        incoming_backlinks = await get_page_backlinks(page, current_slug, limit=120, lang=self.lang)

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
                            "links_type": "incoming_backlinks",
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

                            if inc_slug == start_slug_lower or inc_title.lower() == start_info["title"].lower():
                                start_hit = inc
                                break

                            if inc_slug in forward_visited:
                                forward_hit = (inc, forward_visited[inc_slug])
                                break

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
                                "section": start_hit.get("section", "Backlinks / Incoming"),
                                "anchor_text": clean_title,
                                "words_before": "",
                                "words_after": "",
                                "hop": 1,
                                "score": 9999.0,
                                "is_feeder": True,
                                "badge": "🤝 Meeting Bridge",
                                "badge_class": "bg-warning text-dark",
                                "badges": [
                                    {"text": "🤝 Meeting Bridge", "class": "bg-warning text-dark"},
                                    {"text": "⭐ Start Connector", "class": "bg-success text-white"},
                                ],
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

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Both search frontiers met at '{clean_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                clean_title, msg
                            )
                            return

                        # 2. Meeting with forward frontier!
                        if forward_hit:
                            inc_item, f_match = forward_hit
                            inc_title = inc_item["title"]
                            bridge_step = {
                                "from_title": inc_title,
                                "from_slug": inc_item["slug"],
                                "from_url": f"https://{self.lang}.wikipedia.org/wiki/{inc_item['slug']}",
                                "to_title": clean_title,
                                "to_slug": current_slug,
                                "to_url": page_url,
                                "section": inc_item.get("section", "Backlinks / Incoming"),
                                "anchor_text": clean_title,
                                "words_before": "",
                                "words_after": "",
                                "hop": depth + 1,
                                "score": 9999.0,
                                "is_feeder": True,
                                "badge": "🤝 Meeting Bridge",
                                "badge_class": "bg-warning text-dark",
                                "badges": [
                                    {"text": "🤝 Meeting Bridge", "class": "bg-warning text-dark"},
                                    {"text": "Frontier Intersection", "class": "bg-primary-subtle text-primary border border-primary-subtle"},
                                ],
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

                            msg = (
                                f"Target reached in {hops} hop{'s' if hops != 1 else ''}! "
                                f"Both search frontiers met at '{clean_title}' after inspecting {visited_count} total pages "
                                f"({len(forward_visited)} forward + {len(backward_visited)} backward)."
                            )
                            yield await self._build_found_payload(
                                page, final_path_titles, final_path_slugs, final_steps,
                                visited_count, forward_visited, backward_visited, intermediate_pages,
                                clean_title, msg
                            )
                            return

                        # Enqueue backward parents (pages that link into this node)
                        if depth < self.max_depth:
                            if self.algorithm == "heuristic":
                                await asyncio.get_running_loop().run_in_executor(
                                    None, prime_embeddings, [i["title"] for i in incoming_backlinks]
                                )
                            scored_parents = []
                            for inc in incoming_backlinks:
                                p_slug = inc["slug"]
                                p_slug_key = p_slug.lower()
                                if p_slug_key in backward_visited:
                                    continue

                                p_title = inc["title"]
                                link_score, is_feeder, reasons, badge, badge_class, explanation = compute_relevance_score(
                                    p_title,
                                    p_slug,
                                    start_info["title"],
                                    start_info["slug"],
                                    start_keywords,
                                    target_backlinks=set(),
                                    depth=depth + 1,
                                    algorithm=self.algorithm,
                                    target_context=start_context,
                                    target_summary=start_summary,
                                )

                                badges_list = [
                                    {"text": "⏪ Reverse Feeder", "class": "bg-info text-dark"}
                                ]
                                if "Target Match" in badge or "Start" in badge:
                                    badges_list.append({"text": "⭐ Start Connector", "class": "bg-warning text-dark"})
                                    primary_badge = "⭐ Start Connector"
                                    primary_badge_class = "bg-warning text-dark"
                                elif "Global Connector Hub" in badge:
                                    badges_list.append({"text": "🌐 Global Connector Hub", "class": "bg-primary text-white"})
                                    primary_badge = "🌐 Global Reverse Hub"
                                    primary_badge_class = "bg-primary text-white"
                                elif badge and badge != "Candidate Neighbor":
                                    badges_list.append({"text": badge, "class": badge_class})
                                    primary_badge = badge
                                    primary_badge_class = badge_class
                                else:
                                    primary_badge = "⏪ Reverse Feeder"
                                    primary_badge_class = "bg-info text-dark"

                                step_data = {
                                    "from_title": p_title,
                                    "from_slug": p_slug,
                                    "from_url": f"https://{self.lang}.wikipedia.org/wiki/{p_slug}",
                                    "to_title": clean_title,
                                    "to_slug": current_slug,
                                    "to_url": page_url,
                                    "section": inc.get("section", "Backlinks / Incoming"),
                                    "anchor_text": clean_title,
                                    "words_before": "",
                                    "words_after": "",
                                    "hop": depth + 1,
                                    "score": round(link_score, 1),
                                    "is_feeder": True,
                                    "badge": primary_badge,
                                    "badge_class": primary_badge_class,
                                    "badges": badges_list,
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
