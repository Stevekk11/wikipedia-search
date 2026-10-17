"""
DOM extraction and Playwright in-page utilities for Wikipedia articles.
Extracts outgoing links, surrounding sentence context, incoming backlinks,
and page previews.
"""

import base64
import logging
import urllib.parse
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import requests

if TYPE_CHECKING:
    from playwright.async_api import Page

from .config import DEFAULT_USER_AGENT, DISALLOWED_PREFIXES

logger = logging.getLogger("wikipedia_crawler.extractor")


async def extract_page_summary(page: Any, default_title: str, capture_screenshots: bool = True) -> Tuple[str, str, Optional[str]]:
    """
    Extract the clean title, lead summary snippet, and optional JPEG screenshot.
    """
    clean_title = default_title
    try:
        real_title = await page.title()
        clean_title = real_title.replace(" - Wikipedia", "").strip()
    except Exception:
        pass

    lead_snippet = ""
    try:
        paragraphs = await page.eval_on_selector_all(
            "#bodyContent p",
            """elements => elements.map(e => {
                const clone = e.cloneNode(true);
                clone.querySelectorAll('style, script, .mw-editsection').forEach(x => x.remove());
                clone.querySelectorAll('math, .mwe-math-element').forEach(m => {
                    const alt = m.getAttribute('alttext') || (m.querySelector('math') ? m.querySelector('math').getAttribute('alttext') : '');
                    if (alt) {
                        let tex = alt.trim();
                        if (tex.startsWith('{\\\\displaystyle') && tex.endsWith('}')) {
                            tex = tex.slice(14, -1).trim();
                        } else if (tex.startsWith('{\\\\textstyle') && tex.endsWith('}')) {
                            tex = tex.slice(12, -1).trim();
                        }
                        const span = document.createElement('span');
                        span.textContent = `$${tex}$`;
                        m.replaceWith(span);
                    }
                });
                return clone.innerText.trim();
            }).filter(t => t.length > 40).slice(0, 2).join(' ')""",
        )
        lead_snippet = paragraphs[:280] + ("..." if len(paragraphs) > 280 else "")
    except Exception:
        pass

    screenshot_b64: Optional[str] = None
    if capture_screenshots:
        try:
            screenshot_bytes = await page.screenshot(type="jpeg", quality=45)
            screenshot_b64 = "data:image/jpeg;base64," + base64.b64encode(screenshot_bytes).decode("utf-8")
        except Exception as shot_err:
            logger.debug(f"Screenshot error: {shot_err}")

    return clean_title, lead_snippet, screenshot_b64


async def extract_outgoing_links(page: Any) -> List[Dict[str, str]]:
    """
    Evaluate in-page DOM to extract all valid internal Wikipedia hyperlinks,
    along with section headers and ~15 words before & after each link.
    """
    try:
        extracted = await page.evaluate(
            """(disallowed) => {
                const body = document.querySelector('#bodyContent') || document.body;
                const anchors = Array.from(body.querySelectorAll('a[href]'));
                const results = [];
                const seen = new Set();

                for (const a of anchors) {
                    if (a.closest('style, script, .mw-editsection, #mw-navigation, #mw-panel, #p-lang, #footer, .vertical-navbox, .sistersitebox')) {
                        continue;
                    }
                    const rawHref = a.getAttribute('href') || '';
                    let slug = '';
                    if (rawHref.startsWith('/wiki/')) {
                        slug = rawHref.substring(6);
                    } else if (rawHref.includes('.wikipedia.org/wiki/')) {
                        slug = rawHref.split('.wikipedia.org/wiki/')[1] || '';
                    } else continue;

                    slug = slug.split('#')[0].split('?')[0];
                    if (!slug || slug === 'Main_Page') continue;
                    try { slug = decodeURIComponent(slug); } catch(e) {}
                    if (disallowed.some(p => slug.startsWith(p))) continue;

                    const key = slug.charAt(0).toLowerCase() + slug.slice(1);
                    if (!seen.has(key)) {
                        seen.add(key);
                        const title = a.getAttribute('title') || a.innerText.trim() || slug.replace(/_/g, ' ');
                        const anchorText = a.innerText.trim() || title;

                        let wordsBefore = '';
                        let wordsAfter = '';
                        let sectionTitle = 'Lead / Introduction';
                        
                        // Find section subtitle
                        let cur = a;
                        while (cur && cur !== body && cur !== document.documentElement) {
                            let prev = cur.previousElementSibling;
                            while (prev) {
                                const h = prev.matches('h2, h3, h4, h5, h6') ? prev : prev.querySelector('h2, h3, h4, h5, h6, .mw-headline');
                                if (h) {
                                    const cloneH = h.cloneNode(true);
                                    cloneH.querySelectorAll('.mw-editsection, style, script').forEach(e => e.remove());
                                    const hText = cloneH.textContent.trim().replace(/\\[edit\\]/gi, '').trim();
                                    if (hText) {
                                        sectionTitle = hText;
                                        break;
                                    }
                                }
                                prev = prev.previousElementSibling;
                            }
                            if (sectionTitle !== 'Lead / Introduction') break;
                            cur = cur.parentElement;
                        }

                        const block = a.closest('p, li, dd, dt, td, th') || a.parentElement;
                        if (block) {
                            try {
                                const rangeBefore = document.createRange();
                                rangeBefore.setStart(block, 0);
                                rangeBefore.setEndBefore(a);
                                const cloneB = rangeBefore.cloneContents();
                                cloneB.querySelectorAll('style, script, .mw-editsection').forEach(e => e.remove());
                                cloneB.querySelectorAll('math, .mwe-math-element').forEach(m => {
                                    const alt = m.getAttribute('alttext') || (m.querySelector('math') ? m.querySelector('math').getAttribute('alttext') : '');
                                    if (alt) {
                                        let tex = alt.trim();
                                        if (tex.startsWith('{\\\\displaystyle') && tex.endsWith('}')) tex = tex.slice(14, -1).trim();
                                        else if (tex.startsWith('{\\\\textstyle') && tex.endsWith('}')) tex = tex.slice(12, -1).trim();
                                        const span = document.createElement('span');
                                        span.textContent = ` $${tex}$ `;
                                        m.replaceWith(span);
                                    }
                                });
                                const beforeStr = cloneB.textContent.trim();
                                const bTokens = beforeStr.split(/\\s+/).filter(Boolean);
                                wordsBefore = bTokens.slice(-15).join(' ');

                                const rangeAfter = document.createRange();
                                rangeAfter.setStartAfter(a);
                                rangeAfter.setEnd(block, block.childNodes.length);
                                const cloneA = rangeAfter.cloneContents();
                                cloneA.querySelectorAll('style, script, .mw-editsection').forEach(e => e.remove());
                                cloneA.querySelectorAll('math, .mwe-math-element').forEach(m => {
                                    const alt = m.getAttribute('alttext') || (m.querySelector('math') ? m.querySelector('math').getAttribute('alttext') : '');
                                    if (alt) {
                                        let tex = alt.trim();
                                        if (tex.startsWith('{\\\\displaystyle') && tex.endsWith('}')) tex = tex.slice(14, -1).trim();
                                        else if (tex.startsWith('{\\\\textstyle') && tex.endsWith('}')) tex = tex.slice(12, -1).trim();
                                        const span = document.createElement('span');
                                        span.textContent = ` $${tex}$ `;
                                        m.replaceWith(span);
                                    }
                                });
                                const afterStr = cloneA.textContent.trim();
                                const aTokens = afterStr.split(/\\s+/).filter(Boolean);
                                wordsAfter = aTokens.slice(0, 15).join(' ');
                            } catch(e) {}
                        }

                        results.push({
                            slug: slug,
                            title: title,
                            anchor_text: anchorText,
                            section: sectionTitle,
                            words_before: wordsBefore,
                            words_after: wordsAfter
                        });
                    }
                }
                return results;
            }""",
            DISALLOWED_PREFIXES,
        )
        return extracted
    except Exception as e:
        logger.warning(f"Error extracting outgoing links: {e}")
        return []


async def get_page_backlinks(page: Any, slug: str, limit: int = 500, lang: str = "en") -> List[Dict[str, str]]:
    """
    Fetch incoming backlinks to a Wikipedia article.
    First tries Wikipedia Action API; falls back to Playwright Special:WhatLinksHere.
    """
    lang = (lang or "en").strip().lower()
    clean_slug = slug.strip().replace(" ", "_")
    encoded = urllib.parse.quote(clean_slug.replace("_", " "))
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    api_url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=backlinks"
        f"&bltitle={encoded}&bllimit={limit}&blnamespace=0&blfilterredir=nonredirects&format=json"
    )

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
        logger.debug(f"Action API backlinks failed for {clean_slug} ({lang}): {e}")

    # Fallback to Playwright Special:WhatLinksHere
    try:
        what_url = f"https://{lang}.wikipedia.org/wiki/Special:WhatLinksHere/{clean_slug}?limit={limit}&namespace=0"
        await page.goto(what_url, wait_until="domcontentloaded", timeout=12000)
        items = await page.evaluate(
            """(disallowed) => {
                const list = document.querySelector('#mw-whatlinkshere-list');
                if (!list) return [];
                const results = [];
                const seen = new Set();
                const lis = Array.from(list.querySelectorAll('li > bdi > a'));
                for (const a of lis) {
                    const rawHref = a.getAttribute('href') || '';
                    let s = '';
                    if (rawHref.startsWith('/wiki/')) {
                        s = rawHref.substring(6);
                    } else if (rawHref.includes('.wikipedia.org/wiki/')) {
                        s = rawHref.split('.wikipedia.org/wiki/')[1] || '';
                    } else continue;
                    s = s.split('#')[0].split('?')[0];
                    if (!s || s === 'Main_Page') continue;
                    try { s = decodeURIComponent(s); } catch(e) {}
                    if (disallowed.some(p => s.startsWith(p))) continue;
                    const k = s.toLowerCase();
                    if (!seen.has(k)) {
                        seen.add(k);
                        const title = a.getAttribute('title') || a.innerText.trim() || s.replace(/_/g, ' ');
                        results.push({ slug: s, title: title });
                    }
                }
                return results;
            }""",
            DISALLOWED_PREFIXES,
        )
        return items
    except Exception as e:
        logger.warning(f"Playwright WhatLinksHere failed for {clean_slug} ({lang}): {e}")
        return []


async def extract_target_link_context(
    page: Any,
    source_slug: str,
    target_slug: str,
    target_title: str,
    words_count: int = 150,
    source_title: Optional[str] = None,
    lang: str = "en",
) -> Dict:
    """
    Extract up to words_count before and after the target link on source_slug,
    along with section header.
    """
    lang = (lang or "en").strip().lower()
    clean_source_title = source_title or source_slug.replace("_", " ")
    try:
        cur_url = page.url or ""
        if f"/wiki/{source_slug}".lower() not in urllib.parse.unquote(cur_url).lower():
            await page.goto(f"https://{lang}.wikipedia.org/wiki/{source_slug}", wait_until="domcontentloaded", timeout=12000)

        extracted_context = await page.evaluate(
            """args => {
                const rawTargetSlug = args.targetSlug || '';
                const normWikiSlug = s => s ? (s.charAt(0).toLowerCase() + s.slice(1)).replace(/ /g, '_') : '';
                const targetWikiSlug = normWikiSlug(rawTargetSlug);
                const targetSlug = rawTargetSlug.toLowerCase();
                const cleanSlug = targetSlug.replace(/_/g, ' ');
                const targetTitleLower = (args.targetTitle || '').toLowerCase().trim();
                const wordsBeforeCount = args.wordsBeforeCount;
                const wordsAfterCount = args.wordsAfterCount;
                const body = document.querySelector('#bodyContent') || document.body;

                function decodeHrefSlug(rawHref) {
                    let s = '';
                    if (rawHref.startsWith('/wiki/')) {
                        s = rawHref.substring(6);
                    } else if (rawHref.includes('.wikipedia.org/wiki/')) {
                        s = rawHref.split('.wikipedia.org/wiki/')[1] || '';
                    } else {
                        return '';
                    }
                    s = s.split('#')[0].split('?')[0];
                    try { s = decodeURIComponent(s); } catch(e) {}
                    return s;
                }

                const anchors = Array.from(body.querySelectorAll('a[href]'));

                // Priority 1: Exact Wikipedia canonical slug match in main article prose (excluding navboxes)
                let targetAnchor = anchors.find(a => {
                    if (a.closest('.navbox, .vertical-navbox')) return false;
                    const s = normWikiSlug(decodeHrefSlug(a.getAttribute('href') || ''));
                    return s && s === targetWikiSlug;
                });

                // Priority 2: Case-insensitive exact decoded slug match in main article prose
                if (!targetAnchor) {
                    targetAnchor = anchors.find(a => {
                        if (a.closest('.navbox, .vertical-navbox')) return false;
                        const s = decodeHrefSlug(a.getAttribute('href') || '').toLowerCase();
                        return s === targetSlug || s.replace(/_/g, ' ') === cleanSlug;
                    });
                }

                // Priority 3: Exact decoded slug match anywhere on the page (including navboxes/tables)
                if (!targetAnchor) {
                    targetAnchor = anchors.find(a => {
                        const rawS = decodeHrefSlug(a.getAttribute('href') || '');
                        const s = rawS.toLowerCase();
                        return normWikiSlug(rawS) === targetWikiSlug || s === targetSlug || s.replace(/_/g, ' ') === cleanSlug;
                    });
                }

                // Priority 4: Exact title attribute or anchor text match (for redirects)
                if (!targetAnchor) {
                    targetAnchor = anchors.find(a => {
                        const text = (a.innerText || '').toLowerCase().trim();
                        const title = (a.getAttribute('title') || '').toLowerCase().trim();
                        return (
                            text === cleanSlug ||
                            title === cleanSlug ||
                            (targetTitleLower && (text === targetTitleLower || title === targetTitleLower))
                        );
                    });
                }

                if (!targetAnchor) return null;

                let sectionTitle = 'Lead / Introduction';
                let cur = targetAnchor;
                while (cur && cur !== body && cur !== document.documentElement) {
                    let prev = cur.previousElementSibling;
                    while (prev) {
                        const h = prev.matches('h2, h3, h4, h5, h6') ? prev : prev.querySelector('h2, h3, h4, h5, h6, .mw-headline');
                        if (h) {
                            const cloneH = h.cloneNode(true);
                            cloneH.querySelectorAll('.mw-editsection, style, script').forEach(e => e.remove());
                            const hText = cloneH.textContent.trim().replace(/\\[edit\\]/gi, '').trim();
                            if (hText) {
                                sectionTitle = hText;
                                break;
                            }
                        }
                        prev = prev.previousElementSibling;
                    }
                    if (sectionTitle !== 'Lead / Introduction') break;
                    cur = cur.parentElement;
                }

                const walkerBefore = document.createTreeWalker(body, NodeFilter.SHOW_TEXT, null, false);
                walkerBefore.currentNode = targetAnchor;
                const wordsBefore = [];
                let prevNode;
                const seenMathBefore = new Set();
                while (wordsBefore.length < wordsBeforeCount && (prevNode = walkerBefore.previousNode())) {
                    const parent = prevNode.parentElement;
                    if (!parent || parent.closest('script, style, #mw-navigation, #footer')) continue;
                    const mathEl = parent.closest('math, .mwe-math-element');
                    if (mathEl) {
                        if (!seenMathBefore.has(mathEl)) {
                            seenMathBefore.add(mathEl);
                            const alt = mathEl.getAttribute('alttext') || (mathEl.querySelector('math') ? mathEl.querySelector('math').getAttribute('alttext') : '');
                            if (alt) {
                                let tex = alt.trim();
                                if (tex.startsWith('{\\\\displaystyle') && tex.endsWith('}')) tex = tex.slice(14, -1).trim();
                                else if (tex.startsWith('{\\\\textstyle') && tex.endsWith('}')) tex = tex.slice(12, -1).trim();
                                wordsBefore.unshift(`$${tex}$`);
                            }
                        }
                        continue;
                    }
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
                const seenMathAfter = new Set();
                while (wordsAfter.length < wordsAfterCount && (nextNode = walkerAfter.nextNode())) {
                    if (targetAnchor.contains(nextNode)) continue;
                    const parent = nextNode.parentElement;
                    if (!parent || parent.closest('script, style, #mw-navigation, #footer')) continue;
                    const mathEl = parent.closest('math, .mwe-math-element');
                    if (mathEl) {
                        if (!seenMathAfter.has(mathEl)) {
                            seenMathAfter.add(mathEl);
                            const alt = mathEl.getAttribute('alttext') || (mathEl.querySelector('math') ? mathEl.querySelector('math').getAttribute('alttext') : '');
                            if (alt) {
                                let tex = alt.trim();
                                if (tex.startsWith('{\\\\displaystyle') && tex.endsWith('}')) tex = tex.slice(14, -1).trim();
                                else if (tex.startsWith('{\\\\textstyle') && tex.endsWith('}')) tex = tex.slice(12, -1).trim();
                                wordsAfter.push(`$${tex}$`);
                            }
                        }
                        continue;
                    }
                    const txt = nextNode.textContent.trim();
                    if (!txt) continue;
                    const tokens = txt.split(/\\s+/).filter(Boolean);
                    for (let i = 0; i < tokens.length && wordsAfter.length < wordsAfterCount; i++) {
                        wordsAfter.push(tokens[i]);
                    }
                }

                return {
                    anchorText: targetAnchor.innerText.trim() || targetAnchor.getAttribute('title') || '',
                    section: sectionTitle,
                    wordsBefore: wordsBefore.join(' '),
                    wordsAfter: wordsAfter.join(' '),
                    beforeCount: wordsBefore.length,
                    afterCount: wordsAfter.length
                };
            }""",
            {
                "targetSlug": target_slug,
                "targetTitle": target_title,
                "wordsBeforeCount": words_count,
                "wordsAfterCount": words_count,
            },
        )
        if extracted_context:
            return {
                "source_title": clean_source_title,
                "source_slug": source_slug,
                "source_url": f"https://{lang}.wikipedia.org/wiki/{source_slug}",
                "target_title": target_title,
                "target_slug": target_slug,
                "target_url": f"https://{lang}.wikipedia.org/wiki/{target_slug}",
                "section": extracted_context.get("section", "Lead / Introduction"),
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
        "source_title": clean_source_title,
        "source_slug": source_slug,
        "source_url": f"https://{lang}.wikipedia.org/wiki/{source_slug}",
        "target_title": target_title,
        "target_slug": target_slug,
        "target_url": f"https://{lang}.wikipedia.org/wiki/{target_slug}",
        "section": "Lead / Introduction",
        "words_before": "",
        "anchor_text": target_title,
        "words_after": "",
        "before_count": 0,
        "after_count": 0,
        "requested_words": words_count,
    }


async def enrich_final_steps_context(page: Any, final_steps: List[Dict], lang: str = "en"):
    """
    Post-crawl resolution: For any step in the winning path where in-page
    context is missing (such as reverse backlink feeders), navigate to the source page
    and extract the real section subtitle, in-page anchor text, and 15 words before/after.
    Since this runs only once for the winning path (1-3 steps), it has zero impact on search speed.
    """
    lang = (lang or "en").strip().lower()
    for step in final_steps:
        if not step.get("words_before") and not step.get("words_after"):
            from_slug = step.get("from_slug")
            from_title = step.get("from_title")
            to_slug = step.get("to_slug")
            to_title = step.get("to_title")
            if from_slug and to_slug:
                try:
                    c = await extract_target_link_context(
                        page, from_slug, to_slug, to_title or to_slug, words_count=15, source_title=from_title, lang=lang
                    )
                    if c:
                        if c.get("words_before") or c.get("words_after"):
                            step["words_before"] = c.get("words_before", "")
                            step["words_after"] = c.get("words_after", "")
                        if c.get("anchor_text"):
                            step["anchor_text"] = c.get("anchor_text")
                        sec = c.get("section")
                        if sec and sec != "Lead / Introduction":
                            step["section"] = sec
                        elif not step.get("section") or step.get("section") == "Backlinks / Incoming":
                            step["section"] = sec or "Lead / Introduction"
                except Exception as e:
                    logger.debug(f"Could not enrich intermediate step context for {from_slug}: {e}")


async def walk_final_path_interactively(
    page: Any,
    final_path_titles: List[str],
    final_path_slugs: List[str],
    final_steps: List[Dict],
    lang: str = "en",
    cancel_check: Optional[Any] = None,
) -> Any:
    """
    Interactive Walkthrough Replay:
    Opens/uses the visible Playwright browser to walk the actual discovered path
    from Start to Target step-by-step. On each page, injects a visual HUD banner,
    locates the exact outgoing link to the next hop (expanding collapsed templates
    or synthesizing a prominent link banner if hidden), smoothly scrolls it into view,
    highlights it with a glowing pulse animation, and clicks it to navigate to the next hop.
    Yields real-time progress events for the WebSocket client.
    """
    import asyncio

    lang = (lang or "en").strip().lower()
    total_hops = max(0, len(final_path_slugs) - 1)
    if total_hops == 0:
        return

    start_slug = final_path_slugs[0]
    start_title = final_path_titles[0] if final_path_titles else start_slug.replace("_", " ")
    start_url = f"https://{lang}.wikipedia.org/wiki/{start_slug}"

    yield {
        "event": "interactive_walk_step",
        "hop": 0,
        "total_hops": total_hops,
        "status": "starting",
        "from_title": start_title,
        "to_title": final_path_titles[1] if len(final_path_titles) > 1 else "",
        "message": f"Interactive Walkthrough: Opening starting article '{start_title}'...",
    }

    try:
        await page.bring_to_front()
    except Exception:
        pass

    try:
        await page.goto(start_url, wait_until="domcontentloaded", timeout=20000)
    except Exception as e:
        logger.warning(f"Interactive walk failed to load start page {start_url}: {e}")

    for hop_idx in range(total_hops):
        if cancel_check and cancel_check():
            return

        from_slug = final_path_slugs[hop_idx]
        from_title = final_path_titles[hop_idx] if hop_idx < len(final_path_titles) else from_slug.replace("_", " ")
        to_slug = final_path_slugs[hop_idx + 1]
        to_title = (
            final_path_titles[hop_idx + 1]
            if (hop_idx + 1) < len(final_path_titles)
            else to_slug.replace("_", " ")
        )
        step_meta = final_steps[hop_idx] if hop_idx < len(final_steps) else {}
        anchor_hint = step_meta.get("anchor_text") or to_title
        hop_num = hop_idx + 1

        # Ensure we are on the expected source page before searching for the link
        cur_url = page.url or ""
        if f"/wiki/{from_slug}".lower() not in urllib.parse.unquote(cur_url).lower():
            try:
                await page.goto(
                    f"https://{lang}.wikipedia.org/wiki/{from_slug}",
                    wait_until="domcontentloaded",
                    timeout=18000,
                )
            except Exception as e:
                logger.debug(f"Interactive walk navigation fallback for {from_slug}: {e}")

        yield {
            "event": "interactive_walk_step",
            "hop": hop_num,
            "total_hops": total_hops,
            "status": "scrolling",
            "from_title": from_title,
            "to_title": to_title,
            "message": f"Hop {hop_num}/{total_hops}: Scrolling to '{to_title}' on '{from_title}'...",
        }

        # Inject HUD banner, find target anchor, uncollapse any hidden containers, scroll & highlight
        found_info = await page.evaluate(
            """(args) => {
                const { toSlug, toTitle, anchorHint, fromTitle, hopNum, totalHops, lang } = args;
                const normWikiSlug = s => s ? (s.charAt(0).toLowerCase() + s.slice(1)).replace(/ /g, '_') : '';
                const targetWikiSlug = normWikiSlug(toSlug || '');
                const targetSlugLower = (toSlug || '').toLowerCase();
                const targetTitleLower = (toTitle || '').toLowerCase().trim();
                const cleanSlugLower = targetSlugLower.replace(/_/g, ' ');
                const hintLower = (anchorHint || '').toLowerCase().trim();

                // 1. Inject CSS for HUD & glowing link highlight
                if (!document.getElementById('wikihop-interactive-style')) {
                    const style = document.createElement('style');
                    style.id = 'wikihop-interactive-style';
                    style.textContent = `
                        @keyframes wikihop-pulse {
                            0% { transform: scale(1); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0.85), 0 0 18px 6px rgba(239, 68, 68, 0.75); }
                            50% { transform: scale(1.09); box-shadow: 0 0 0 14px rgba(234, 179, 8, 0), 0 0 28px 12px rgba(239, 68, 68, 0.95); }
                            100% { transform: scale(1); box-shadow: 0 0 0 0 rgba(234, 179, 8, 0), 0 0 18px 6px rgba(239, 68, 68, 0.75); }
                        }
                        .wikihop-target-highlight {
                            display: inline-block !important;
                            background: linear-gradient(135deg, #facc15 0%, #f97316 100%) !important;
                            color: #0f172a !important;
                            font-weight: 800 !important;
                            padding: 4px 10px !important;
                            margin: 0 3px !important;
                            border-radius: 8px !important;
                            border: 3px solid #ef4444 !important;
                            text-decoration: none !important;
                            position: relative !important;
                            z-index: 99998 !important;
                            animation: wikihop-pulse 0.9s infinite ease-in-out !important;
                            transition: all 0.25s ease !important;
                        }
                        .wikihop-target-clicked {
                            background: linear-gradient(135deg, #22c55e 0%, #16a34a 100%) !important;
                            color: #ffffff !important;
                            border-color: #15803d !important;
                            transform: scale(1.14) !important;
                        }
                        #wikihop-hud-banner {
                            position: fixed;
                            top: 16px;
                            right: 16px;
                            z-index: 99999;
                            background: rgba(15, 23, 42, 0.94);
                            color: #f8fafc;
                            border: 2px solid #38bdf8;
                            border-radius: 14px;
                            padding: 14px 20px;
                            font-family: system-ui, -apple-system, sans-serif;
                            box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45);
                            max-width: 430px;
                            backdrop-filter: blur(8px);
                        }
                    `;
                    document.head.appendChild(style);
                }

                // 2. Inject or update floating HUD banner
                let hud = document.getElementById('wikihop-hud-banner');
                if (!hud) {
                    hud = document.createElement('div');
                    hud.id = 'wikihop-hud-banner';
                    document.body.appendChild(hud);
                }
                hud.innerHTML = `
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #38bdf8; font-weight: 700; margin-bottom: 4px;">
                        🌐 WikiHop Interactive Final Path &bull; Hop ${hopNum} of ${totalHops}
                    </div>
                    <div style="font-size: 15px; font-weight: 700; margin-bottom: 6px; line-height: 1.35;">
                        ${fromTitle} <span style="color: #facc15; margin: 0 4px;">&rarr;</span> <span style="color: #4ade80;">${toTitle}</span>
                    </div>
                    <div id="wikihop-hud-status" style="font-size: 12.5px; color: #cbd5e1;">
                        🔍 Locating &amp; scrolling to connecting link...
                    </div>
                `;

                // 3. Locate the link in #bodyContent or document.body
                const body = document.querySelector('#bodyContent') || document.body;
                const anchors = Array.from(body.querySelectorAll('a[href]'));

                function decodeSlug(rawHref) {
                    let s = '';
                    if (rawHref.startsWith('/wiki/')) s = rawHref.substring(6);
                    else if (rawHref.includes('.wikipedia.org/wiki/')) s = rawHref.split('.wikipedia.org/wiki/')[1] || '';
                    else return '';
                    s = s.split('#')[0].split('?')[0];
                    try { s = decodeURIComponent(s); } catch(e) {}
                    return s;
                }

                // Priority 1: Exact Wikipedia canonical slug match in main prose (not navbox)
                let targetEl = anchors.find(a => {
                    if (a.closest('.navbox, .vertical-navbox')) return false;
                    const s = normWikiSlug(decodeSlug(a.getAttribute('href') || ''));
                    return s && s === targetWikiSlug;
                });

                // Priority 2: Case-insensitive exact slug match in main prose (not navbox)
                if (!targetEl) {
                    targetEl = anchors.find(a => {
                        if (a.closest('.navbox, .vertical-navbox')) return false;
                        const s = decodeSlug(a.getAttribute('href') || '').toLowerCase();
                        return s === targetSlugLower || s.replace(/_/g, ' ') === cleanSlugLower;
                    });
                }

                // Priority 3: Exact slug match anywhere (including navboxes/tables)
                if (!targetEl) {
                    targetEl = anchors.find(a => {
                        const rawS = decodeSlug(a.getAttribute('href') || '');
                        const s = rawS.toLowerCase();
                        return normWikiSlug(rawS) === targetWikiSlug || s === targetSlugLower || s.replace(/_/g, ' ') === cleanSlugLower;
                    });
                }

                // Priority 4: Match by title attribute or anchor text (for redirects)
                if (!targetEl) {
                    targetEl = anchors.find(a => {
                        const t = (a.getAttribute('title') || '').toLowerCase().trim();
                        const txt = (a.innerText || '').toLowerCase().trim();
                        return t === targetTitleLower || t === cleanSlugLower || txt === targetTitleLower || (hintLower && txt === hintLower);
                    });
                }

                // If inside a collapsed container (e.g. mw-collapsed navbox), expand it so it is visible
                if (targetEl) {
                    let cur = targetEl.parentElement;
                    while (cur && cur !== document.body) {
                        if (cur.classList && cur.classList.contains('mw-collapsed')) {
                            cur.classList.remove('mw-collapsed');
                        }
                        const st = window.getComputedStyle(cur);
                        if (st.display === 'none' || st.visibility === 'hidden') {
                            cur.style.setProperty('display', 'block', 'important');
                            cur.style.setProperty('visibility', 'visible', 'important');
                        }
                        cur = cur.parentElement;
                    }
                } else {
                    // Fallback: synthesize a visible bridge link banner at top of article if hidden in collapsed template
                    const fallbackBox = document.createElement('div');
                    fallbackBox.style.cssText = 'margin: 18px 0; padding: 14px 18px; background: #fef9c3; border: 2px dashed #eab308; border-radius: 10px; color: #1e293b; font-family: sans-serif;';
                    fallbackBox.innerHTML = `<span style="font-weight:600; margin-right: 8px;">WikiHop Direct Link Target:</span>`;
                    const synthA = document.createElement('a');
                    synthA.href = `/wiki/${encodeURIComponent(toSlug)}`;
                    synthA.textContent = toTitle;
                    fallbackBox.appendChild(synthA);
                    body.prepend(fallbackBox);
                    targetEl = synthA;
                }

                // Tag the element so we can click it reliably
                document.querySelectorAll('[data-wikihop-active]').forEach(el => {
                    el.removeAttribute('data-wikihop-active');
                    el.classList.remove('wikihop-target-highlight', 'wikihop-target-clicked');
                });
                targetEl.setAttribute('data-wikihop-active', 'true');
                targetEl.classList.add('wikihop-target-highlight');

                // Rewrite href to canonical target slug so redirects land cleanly on the next hop
                targetEl.setAttribute('href', `/wiki/${toSlug}`);
                targetEl.removeAttribute('target');

                targetEl.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'nearest' });

                const statusEl = document.getElementById('wikihop-hud-status');
                if (statusEl) {
                    statusEl.innerHTML = `✨ Highlighted link <strong>"${(targetEl.innerText || toTitle).trim()}"</strong> &mdash; clicking next...`;
                }

                return {
                    found: true,
                    anchorText: (targetEl.innerText || toTitle).trim(),
                };
            }""",
            {
                "toSlug": to_slug,
                "toTitle": to_title,
                "anchorHint": anchor_hint,
                "fromTitle": from_title,
                "hopNum": hop_num,
                "totalHops": total_hops,
                "lang": lang,
            },
        )

        # Wait so user can clearly watch the smooth scroll and glowing highlight pulse
        await asyncio.sleep(1.8)
        if cancel_check and cancel_check():
            return

        yield {
            "event": "interactive_walk_step",
            "hop": hop_num,
            "total_hops": total_hops,
            "status": "clicking",
            "from_title": from_title,
            "to_title": to_title,
            "anchor_text": (found_info or {}).get("anchorText", to_title),
            "message": f"Hop {hop_num}/{total_hops}: Clicking link '{(found_info or {}).get('anchorText', to_title)}' → '{to_title}'...",
        }

        # Visually mark as clicked before triggering navigation
        try:
            await page.evaluate(
                """() => {
                    const el = document.querySelector('[data-wikihop-active="true"]');
                    if (el) el.classList.add('wikihop-target-clicked');
                    const statusEl = document.getElementById('wikihop-hud-status');
                    if (statusEl) statusEl.innerHTML = '🖱️ Clicking link &amp; navigating...';
                }"""
            )
        except Exception:
            pass

        await asyncio.sleep(0.35)

        # Click the highlighted link and wait for navigation to the next article
        navigated = False
        try:
            locator = page.locator('[data-wikihop-active="true"]').first
            async with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
                await locator.click(timeout=5000, force=True)
            navigated = True
        except Exception as click_err:
            logger.debug(f"Interactive click navigation fallback on hop {hop_num}: {click_err}")

        if not navigated:
            try:
                await page.goto(
                    f"https://{lang}.wikipedia.org/wiki/{to_slug}",
                    wait_until="domcontentloaded",
                    timeout=18000,
                )
            except Exception as nav_err:
                logger.warning(f"Interactive walk fallback goto failed for {to_slug}: {nav_err}")

        await asyncio.sleep(0.4)

    # Final destination reached banner on Target page
    final_title = final_path_titles[-1] if final_path_titles else final_path_slugs[-1].replace("_", " ")
    try:
        await page.evaluate(
            """(args) => {
                const { finalTitle, totalHops } = args;
                let hud = document.getElementById('wikihop-hud-banner');
                if (!hud) {
                    hud = document.createElement('div');
                    hud.id = 'wikihop-hud-banner';
                    hud.style.cssText = 'position: fixed; top: 16px; right: 16px; z-index: 99999; background: rgba(15, 23, 42, 0.95); color: #f8fafc; border: 2px solid #22c55e; border-radius: 14px; padding: 14px 20px; font-family: system-ui, -apple-system, sans-serif; box-shadow: 0 12px 32px rgba(0, 0, 0, 0.45); max-width: 430px;';
                    document.body.appendChild(hud);
                } else {
                    hud.style.borderColor = '#22c55e';
                }
                hud.innerHTML = `
                    <div style="font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: #4ade80; font-weight: 700; margin-bottom: 4px;">
                        🎯 Target Destination Reached!
                    </div>
                    <div style="font-size: 16px; font-weight: 800; margin-bottom: 4px; color: #ffffff;">
                        ${finalTitle}
                    </div>
                    <div style="font-size: 12.5px; color: #cbd5e1;">
                        Completed ${totalHops} hop${totalHops === 1 ? '' : 's'} along the final path.
                    </div>
                `;
            }""",
            {"finalTitle": final_title, "totalHops": total_hops},
        )
    except Exception:
        pass

    yield {
        "event": "interactive_walk_step",
        "hop": total_hops,
        "total_hops": total_hops,
        "status": "completed",
        "from_title": final_path_titles[0] if final_path_titles else "",
        "to_title": final_title,
        "message": f"Interactive Walkthrough complete! Reached '{final_title}' in {total_hops} hop{'s' if total_hops != 1 else ''}.",
    }

    # Pause briefly on the final target article so the user can see the destination
    await asyncio.sleep(2.5)

