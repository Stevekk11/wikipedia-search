"""
Article statistics and analytics module for Wikipedia pages.
Fetches page stats from Wikimedia XTools API with fallback to MediaWiki API.
Provides metrics such as word count, file size, edit count (revisions),
distinct editors, page watchers, page views, reference counts, and creation dates.
"""

import concurrent.futures
import logging
import re
import threading
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("wikipedia_stats")

# Cache to prevent redundant network calls: (lang, title_or_slug) -> (timestamp, data)
_STATS_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
_CACHE_LOCK = threading.Lock()
_CACHE_TTL_SECONDS = 3600  # 1 hour cache

USER_AGENT = "WikiHopStats/1.0 (https://github.com/wikihop; contact@example.com)"


def _normalize_title(raw_title: str) -> str:
    """Normalize Wikipedia title for API requests."""
    t = raw_title.strip().replace(" ", "_")
    # Strip leading URL if provided
    if "wikipedia.org/wiki/" in t:
        t = t.split("wikipedia.org/wiki/")[-1].split("?")[0].split("#")[0]
    return urllib.parse.unquote(t)


def _format_bytes(num_bytes: int) -> str:
    """Format bytes into human-readable file size."""
    if num_bytes <= 0:
        return "0 B"
    if num_bytes < 1024:
        return f"{num_bytes} B"
    elif num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    else:
        return f"{num_bytes / (1024 * 1024):.2f} MB"


def _format_number(n: int) -> str:
    """Format integer with thousands separator."""
    return f"{n:,}" if n else "0"


def fetch_mediawiki_fallback(title: str, lang: str = "en", timeout: int = 5) -> Dict[str, Any]:
    """
    Fallback method using MediaWiki Action API when XTools is unreachable.
    Fetches article length (bytes), watchers, pageviews, and revision info.
    """
    slug = urllib.parse.quote(title)
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?"
        f"action=query&prop=info|pageviews|extracts&inprop=watchers&titles={slug}"
        f"&explaintext=1&exintro=1&format=json"
    )
    headers = {"User-Agent": USER_AGENT}

    try:
        r = requests.get(url, headers=headers, timeout=timeout)
        if r.status_code == 200:
            data = r.json()
            pages = data.get("query", {}).get("pages", {})
            for pid, pdata in pages.items():
                if pid == "-1":
                    continue
                length = pdata.get("length", 0)
                watchers = pdata.get("watchers", 0)
                pv_dict = pdata.get("pageviews", {})
                total_views = sum(v for v in pv_dict.values() if isinstance(v, (int, float)))

                # Rough estimate of word count from extract if available, else length // 6
                extract = pdata.get("extract", "")
                word_est = len(extract.split()) if extract else max(length // 6, 0)

                return {
                    "words": word_est,
                    "bytes": length,
                    "file_size_formatted": _format_bytes(length),
                    "file_size_kb": round(length / 1024, 1) if length else 0.0,
                    "revisions": 0,
                    "editors": 0,
                    "watchers": watchers,
                    "pageviews": total_views,
                    "references": 0,
                    "created_at": "",
                    "modified_at": pdata.get("touched", ""),
                    "assessment": "",
                    "source": "mediawiki_fallback",
                }
    except Exception as e:
        logger.warning(f"MediaWiki fallback failed for '{title}' ({lang}): {e}")

    return {
        "words": 0,
        "bytes": 0,
        "file_size_formatted": "0 B",
        "file_size_kb": 0.0,
        "revisions": 0,
        "editors": 0,
        "watchers": 0,
        "pageviews": 0,
        "references": 0,
        "created_at": "",
        "modified_at": "",
        "assessment": "",
        "source": "fallback_empty",
    }


def fetch_page_stats(title: str, lang: str = "en", timeout: int = 6) -> Dict[str, Any]:
    """
    Fetch comprehensive article statistics for a single Wikipedia article.
    Combines XTools Article Info (edits, editors, watchers, views, created)
    and XTools Prose Info (word count, prose byte size, references, sections).
    """
    clean_title = _normalize_title(title)
    lang_code = (lang or "en").strip().lower()
    if not re.fullmatch(r"[a-z0-9-]{2,12}", lang_code):
        lang_code = "en"

    cache_key = (lang_code, clean_title.lower())
    now = time.time()

    with _CACHE_LOCK:
        if cache_key in _STATS_CACHE:
            ts, cached_data = _STATS_CACHE[cache_key]
            if now - ts < _CACHE_TTL_SECONDS:
                return cached_data

    slug = urllib.parse.quote(clean_title)
    headers = {"User-Agent": USER_AGENT}

    info_url = f"https://xtools.wmflabs.org/api/page/articleinfo/{lang_code}.wikipedia.org/{slug}"
    prose_url = f"https://xtools.wmflabs.org/api/page/prose/{lang_code}.wikipedia.org/{slug}"

    info_data: Dict[str, Any] = {}
    prose_data: Dict[str, Any] = {}

    def get_json(url: str) -> Optional[Dict[str, Any]]:
        try:
            res = requests.get(url, headers=headers, timeout=timeout)
            if res.status_code == 200:
                return res.json()
            logger.debug(f"XTools HTTP {res.status_code} for {url}")
        except Exception as ex:
            logger.debug(f"XTools request error for {url}: {ex}")
        return None

    # Fetch both endpoints concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_info = executor.submit(get_json, info_url)
        f_prose = executor.submit(get_json, prose_url)
        info_data = f_info.result() or {}
        prose_data = f_prose.result() or {}

    # If both XTools calls returned empty/error, fallback to MediaWiki Action API
    if not info_data and not prose_data:
        logger.info(f"XTools unavailable for '{clean_title}', falling back to MediaWiki API")
        fallback = fetch_mediawiki_fallback(clean_title, lang=lang_code, timeout=timeout)
        stats = {
            "title": clean_title.replace("_", " "),
            "slug": clean_title,
            "lang": lang_code,
            **fallback,
        }
    else:
        # Extract Word Count
        words = prose_data.get("words")
        if words is None:
            # Fallback estimation if prose failed but articleinfo succeeded
            raw_chars = prose_data.get("characters", 0)
            words = raw_chars // 5 if raw_chars else 0

        # Extract File / Prose Size in bytes
        num_bytes = prose_data.get("bytes", 0)
        if not num_bytes:
            # Fallback to total wikitext bytes if prose bytes is missing
            num_bytes = info_data.get("bytes", 0)

        # Extract revisions (number of edits)
        revisions = info_data.get("revisions", 0)
        editors = info_data.get("editors", 0)
        watchers = info_data.get("watchers", 0)
        pageviews = info_data.get("pageviews", 0)
        references = prose_data.get("references", 0)
        sections = prose_data.get("sections", 0)
        created_at = str(info_data.get("created_at") or "")
        modified_at = str(info_data.get("modified_at") or "")
        assessment = str(info_data.get("assessment") or "")

        stats = {
            "title": clean_title.replace("_", " "),
            "slug": clean_title,
            "lang": lang_code,
            "words": int(words or 0),
            "bytes": int(num_bytes or 0),
            "file_size_formatted": _format_bytes(int(num_bytes or 0)),
            "file_size_kb": round(int(num_bytes or 0) / 1024, 1),
            "revisions": int(revisions or 0),
            "editors": int(editors or 0),
            "watchers": int(watchers or 0),
            "pageviews": int(pageviews or 0),
            "references": int(references or 0),
            "sections": int(sections or 0),
            "created_at": created_at,
            "modified_at": modified_at,
            "assessment": assessment,
            "source": "xtools",
        }

    # Store in memory cache
    with _CACHE_LOCK:
        _STATS_CACHE[cache_key] = (now, stats)

    return stats


def fetch_multiple_page_stats(
    titles: List[str], lang: str = "en", max_workers: int = 6
) -> Dict[str, Dict[str, Any]]:
    """
    Concurrently fetch article statistics for a list of Wikipedia articles.
    Returns a dict mapping clean title -> article statistics dictionary.
    """
    clean_titles = [_normalize_title(t) for t in titles if t and t.strip()]
    unique_titles = list(dict.fromkeys(clean_titles))  # Deduplicate preserving order

    if not unique_titles:
        return {}

    results: Dict[str, Dict[str, Any]] = {}

    def _worker(t: str) -> Tuple[str, Dict[str, Any]]:
        return t, fetch_page_stats(t, lang=lang)

    workers = min(max_workers, len(unique_titles), 10)
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        future_map = {pool.submit(_worker, t): t for t in unique_titles}
        for future in concurrent.futures.as_completed(future_map):
            try:
                t, stat = future.result()
                results[t] = stat
                # Also index by human title without underscore
                human_title = t.replace("_", " ")
                if human_title not in results:
                    results[human_title] = stat
            except Exception as e:
                orig_t = future_map[future]
                logger.error(f"Error fetching stats for '{orig_t}': {e}")
                fallback = fetch_mediawiki_fallback(orig_t, lang=lang)
                results[orig_t] = {
                    "title": orig_t.replace("_", " "),
                    "slug": orig_t,
                    "lang": lang,
                    **fallback,
                }

    return results


def summarize_crawl_stats(stats_list: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Generate summary KPIs and aggregated metrics from a list of page statistics.
    Useful for highlighting standout pages (e.g. most edited, largest file size, highest word count).
    """
    if not stats_list:
        return {
            "total_pages": 0,
            "avg_words": 0,
            "avg_file_size_kb": 0.0,
            "total_edits": 0,
            "max_words_page": None,
            "max_file_size_page": None,
            "max_edits_page": None,
            "most_viewed_page": None,
        }

    total_words = sum(s.get("words", 0) for s in stats_list)
    total_bytes = sum(s.get("bytes", 0) for s in stats_list)
    total_edits = sum(s.get("revisions", 0) for s in stats_list)

    max_words_item = max(stats_list, key=lambda s: s.get("words", 0), default={})
    max_size_item = max(stats_list, key=lambda s: s.get("bytes", 0), default={})
    max_edits_item = max(stats_list, key=lambda s: s.get("revisions", 0), default={})
    most_viewed_item = max(stats_list, key=lambda s: s.get("pageviews", 0), default={})

    count = len(stats_list)

    return {
        "total_pages": count,
        "avg_words": round(total_words / count) if count else 0,
        "avg_file_size_kb": round((total_bytes / count) / 1024, 1) if count else 0.0,
        "total_edits": total_edits,
        "max_words_page": {
            "title": max_words_item.get("title", ""),
            "words": max_words_item.get("words", 0),
        }
        if max_words_item.get("words", 0) > 0
        else None,
        "max_file_size_page": {
            "title": max_size_item.get("title", ""),
            "size_formatted": max_size_item.get("file_size_formatted", "0 B"),
            "size_kb": max_size_item.get("file_size_kb", 0.0),
        }
        if max_size_item.get("bytes", 0) > 0
        else None,
        "max_edits_page": {
            "title": max_edits_item.get("title", ""),
            "edits": max_edits_item.get("revisions", 0),
        }
        if max_edits_item.get("revisions", 0) > 0
        else None,
        "most_viewed_page": {
            "title": most_viewed_item.get("title", ""),
            "views": most_viewed_item.get("pageviews", 0),
        }
        if most_viewed_item.get("pageviews", 0) > 0
        else None,
    }
