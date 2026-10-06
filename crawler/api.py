"""
Wikipedia REST and Action API utilities.
Handles title normalization, summary/thumbnail metadata lookup,
target category extraction, and incoming backlinks querying.
"""

import logging
import re
import urllib.parse
from typing import Dict, Set

import requests

from .config import DEFAULT_REST_USER_AGENT, DEFAULT_USER_AGENT

logger = logging.getLogger("wikipedia_crawler.api")


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

    headers = {"User-Agent": DEFAULT_REST_USER_AGENT}

    # 1. Try REST API summary
    rest_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"
    try:
        r = requests.get(rest_url, headers=headers, timeout=5)
        if r.status_code == 200:
            data = r.json()
            canonical_title = data.get("title", clean.replace("_", " "))
            canonical_slug = urllib.parse.unquote(
                data.get("titles", {}).get("canonical", canonical_title.replace(" ", "_"))
            )
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

    # 2. Fallback to Action API query
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
    backlinks: Set[str] = set()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = (
        f"https://en.wikipedia.org/w/api.php?action=query&prop=linkshere"
        f"&titles={urllib.parse.quote(target_slug)}&lhlimit=500&lhnamespace=0&format=json"
    )
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
    cat_words: Set[str] = set()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = (
        f"https://en.wikipedia.org/w/api.php?action=query&prop=categories"
        f"&titles={urllib.parse.quote(target_slug)}&cllimit=50&format=json"
    )
    try:
        r = requests.get(url, headers=headers, timeout=4).json()
        pages = r.get("query", {}).get("pages", {})
        for pid, p in pages.items():
            for cat in p.get("categories", []):
                c_title = cat.get("title", "").replace("Category:", "")
                if any(
                    ign in c_title.lower()
                    for ign in [
                        "articles", "all", "use", "pages", "cs1", "commons",
                        "short", "statements", "webarchive"
                    ]
                ):
                    continue
                words = re.findall(r"\w+", c_title.lower())
                cat_words.update(w for w in words if len(w) > 3)
    except Exception as e:
        logger.warning(f"Failed to fetch categories for {target_slug}: {e}")
    return cat_words
