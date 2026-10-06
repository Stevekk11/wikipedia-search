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
            "elements => elements.map(e => e.innerText.trim()).filter(t => t.length > 40).slice(0, 2).join(' ')",
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
                    if (rawHref.startsWith('/wiki/')) slug = rawHref.substring(6);
                    else if (rawHref.startsWith('https://en.wikipedia.org/wiki/')) slug = rawHref.substring(30);
                    else continue;

                    slug = slug.split('#')[0].split('?')[0];
                    if (!slug || slug === 'Main_Page') continue;
                    try { slug = decodeURIComponent(slug); } catch(e) {}
                    if (disallowed.some(p => slug.startsWith(p))) continue;

                    const key = slug.toLowerCase();
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


async def get_page_backlinks(page: Any, slug: str, limit: int = 150) -> List[Dict[str, str]]:
    """
    Fetch incoming backlinks to a Wikipedia article.
    First tries Wikipedia Action API; falls back to Playwright Special:WhatLinksHere.
    """
    clean_slug = slug.strip().replace(" ", "_")
    encoded = urllib.parse.quote(clean_slug.replace("_", " "))
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    api_url = (
        f"https://en.wikipedia.org/w/api.php?action=query&list=backlinks"
        f"&bltitle={encoded}&bllimit={limit}&blnamespace=0&format=json"
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
        logger.debug(f"Action API backlinks failed for {clean_slug}: {e}")

    # Fallback to Playwright Special:WhatLinksHere
    try:
        what_url = f"https://en.wikipedia.org/wiki/Special:WhatLinksHere/{clean_slug}?limit={limit}&namespace=0"
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
                    if (rawHref.startsWith('/wiki/')) s = rawHref.substring(6);
                    else if (rawHref.startsWith('https://en.wikipedia.org/wiki/')) s = rawHref.substring(30);
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
        logger.warning(f"Playwright WhatLinksHere failed for {clean_slug}: {e}")
        return []


async def extract_target_link_context(
    page: Any,
    source_slug: str,
    target_slug: str,
    target_title: str,
    words_count: int = 150,
) -> Dict:
    """
    Extract up to words_count before and after the target link on source_slug,
    along with section header.
    """
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

                // Find section subtitle
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
                    section: sectionTitle,
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
            },
        )
        if extracted_context:
            return {
                "source_slug": source_slug,
                "source_url": f"https://en.wikipedia.org/wiki/{source_slug}",
                "target_title": target_title,
                "target_slug": target_slug,
                "target_url": f"https://en.wikipedia.org/wiki/{target_slug}",
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
        "source_slug": source_slug,
        "source_url": f"https://en.wikipedia.org/wiki/{source_slug}",
        "target_title": target_title,
        "target_slug": target_slug,
        "target_url": f"https://en.wikipedia.org/wiki/{target_slug}",
        "section": "Lead / Introduction",
        "words_before": "",
        "anchor_text": target_title,
        "words_after": "",
        "before_count": 0,
        "after_count": 0,
        "requested_words": words_count,
    }


async def enrich_final_steps_context(page: Any, final_steps: List[Dict]):
    """
    Post-crawl resolution: For any step in the winning path where in-page
    context is missing (such as reverse backlink feeders), navigate to the source page
    and extract the real section subtitle, in-page anchor text, and 15 words before/after.
    Since this runs only once for the winning path (1-3 steps), it has zero impact on search speed.
    """
    for step in final_steps:
        if not step.get("words_before") and not step.get("words_after"):
            from_slug = step.get("from_slug")
            to_slug = step.get("to_slug")
            to_title = step.get("to_title")
            if from_slug and to_slug:
                try:
                    c = await extract_target_link_context(page, from_slug, to_slug, to_title or to_slug, words_count=15)
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
