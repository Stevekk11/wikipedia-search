"""
Wikipedia REST and Action API utilities.
Handles title normalization, summary/thumbnail metadata lookup,
target category extraction, incoming backlinks querying,
and Wikipedia quality assessment scores & WikiProjects retrieval.
"""

import logging
import re
import urllib.parse
from typing import Dict, List, Optional, Set

import requests

from .config import DEFAULT_REST_USER_AGENT, DEFAULT_USER_AGENT

logger = logging.getLogger("wikipedia_crawler.api")

# Quality assessment grades and hierarchy ranking
ASSESSMENT_RANKS: Dict[str, int] = {
    "FA": 10,
    "FL": 9,
    "GA": 8,
    "A": 7,
    "B": 6,
    "C": 5,
    "START": 4,
    "STUB": 3,
    "LIST": 2,
}

CLASS_META: Dict[str, Dict[str, str]] = {
    "FA": {
        "name": "Featured Article",
        "icon": "bi-star-fill",
        "color": "#2563eb",
        "badge_class": "badge-fa",
    },
    "FL": {
        "name": "Featured List",
        "icon": "bi-award-fill",
        "color": "#0284c7",
        "badge_class": "badge-fl",
    },
    "GA": {
        "name": "Good Article",
        "icon": "bi-patch-check-fill",
        "color": "#16a34a",
        "badge_class": "badge-ga",
    },
    "A": {
        "name": "A-Class",
        "icon": "bi-check-circle-fill",
        "color": "#0891b2",
        "badge_class": "badge-a",
    },
    "B": {
        "name": "B-Class",
        "icon": "bi-file-earmark-check-fill",
        "color": "#65a30d",
        "badge_class": "badge-b",
    },
    "C": {
        "name": "C-Class",
        "icon": "bi-file-earmark-text-fill",
        "color": "#ca8a04",
        "badge_class": "badge-c",
    },
    "START": {
        "name": "Start-Class",
        "icon": "bi-play-circle-fill",
        "color": "#ea580c",
        "badge_class": "badge-start",
    },
    "STUB": {
        "name": "Stub-Class",
        "icon": "bi-file-earmark-minus-fill",
        "color": "#dc2626",
        "badge_class": "badge-stub",
    },
    "LIST": {
        "name": "List-Class",
        "icon": "bi-list-ul",
        "color": "#7c3aed",
        "badge_class": "badge-list",
    },
    "UNASSESSED": {
        "name": "Unassessed",
        "icon": "bi-question-circle-fill",
        "color": "#6b7280",
        "badge_class": "badge-unassessed",
    },
}


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


def get_wikipedia_info(title_or_slug: str, lang: str = "en") -> Dict[str, str]:
    """
    Query the Wikipedia REST / Action API to resolve redirects,
    get canonical title, slug, summary snippet, and thumbnail.
    """
    lang = (lang or "en").strip().lower()
    clean = normalize_slug_or_title(title_or_slug)
    encoded = urllib.parse.quote(clean)

    headers = {"User-Agent": DEFAULT_REST_USER_AGENT}

    # 1. Try REST API summary
    rest_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{encoded}"
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
                "url": f"https://{lang}.wikipedia.org/wiki/{canonical_slug}",
                "description": description,
                "extract": extract[:250] + ("..." if len(extract) > 250 else ""),
                "thumbnail": thumbnail,
            }
    except Exception as e:
        logger.warning(f"Failed to query summary API for {clean} ({lang}): {e}")

    # 2. Fallback to Action API query
    api_url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&titles={encoded}"
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
                        "url": f"https://{lang}.wikipedia.org/wiki/{s}",
                        "description": "",
                        "extract": "",
                        "thumbnail": "",
                    }
    except Exception as e:
        logger.warning(f"Failed to query action API for {clean} ({lang}): {e}")

    title = clean.replace("_", " ")
    return {
        "title": title,
        "slug": clean,
        "url": f"https://{lang}.wikipedia.org/wiki/{clean}",
        "description": "",
        "extract": "",
        "thumbnail": "",
    }


def fetch_target_backlinks(target_slug: str, limit: int = 500, lang: str = "en") -> Set[str]:
    """
    Fetch articles that link directly to the target article (What Links Here).
    Any page linking to these backlinks is guaranteed to be 1 hop away from target!
    """
    lang = (lang or "en").strip().lower()
    backlinks: Set[str] = set()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=linkshere"
        f"&titles={urllib.parse.quote(target_slug)}&lhlimit={limit}&lhnamespace=0&format=json"
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
        logger.warning(f"Failed to fetch target backlinks for {target_slug} ({lang}): {e}")
    return backlinks


def fetch_target_categories(target_slug: str, lang: str = "en") -> Set[str]:
    """
    Fetch Wikipedia categories of the target article to enrich semantic keywords.
    """
    lang = (lang or "en").strip().lower()
    cat_words: Set[str] = set()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=categories"
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
        logger.warning(f"Failed to fetch categories for {target_slug} ({lang}): {e}")
    return cat_words


def parse_page_assessment(title: str, raw_assessments: Optional[Dict]) -> Dict:
    """
    Parse the raw MediaWiki pageassessments dictionary for an article.
    Extracts the highest quality assessment grade, Bootstrap icon,
    color, and all WikiProjects it belongs to.
    """
    projects = []
    classes = []

    for proj_name, data in (raw_assessments or {}).items():
        raw_cls = data.get("class", "").strip().upper()
        if raw_cls:
            classes.append(raw_cls)
        if proj_name != "Project-independent assessment":
            projects.append({
                "name": proj_name,
                "importance": data.get("importance", "").strip(),
                "class": data.get("class", "").strip(),
            })

    best_cls = "UNASSESSED"
    best_rank = -1
    for c in classes:
        rank = ASSESSMENT_RANKS.get(c, 0)
        if rank > best_rank:
            best_rank = rank
            best_cls = c

    # Sort projects by Wikipedia importance hierarchy
    imp_order = {"TOP": 4, "HIGH": 3, "MID": 2, "LOW": 1, "": 0}
    projects.sort(key=lambda p: imp_order.get(p["importance"].upper(), 0), reverse=True)

    meta = CLASS_META.get(best_cls, CLASS_META["UNASSESSED"])
    primary_proj = projects[0] if projects else None

    # Proper display title
    display_class = best_cls if best_cls != "UNASSESSED" else "Unassessed"

    return {
        "title": title,
        "class": display_class,
        "class_name": meta["name"],
        "icon": meta["icon"],
        "color": meta["color"],
        "badge_class": meta["badge_class"],
        "has_wikiproject": len(projects) > 0,
        "primary_project": primary_proj,
        "all_projects": [p["name"] for p in projects],
        "projects": projects,
    }


def fetch_article_assessments(titles_or_slugs: List[str], lang: str = "en") -> Dict[str, Dict]:
    """
    Batch query Wikipedia Action API for article quality assessments and WikiProjects.
    Returns a dictionary mapping titles/slugs to assessment info.
    """
    if not titles_or_slugs:
        return {}

    lang = (lang or "en").strip().lower()
    clean_titles = []
    seen = set()
    for t in titles_or_slugs:
        c = normalize_slug_or_title(t).replace("_", " ")
        if c and c.lower() not in seen:
            seen.add(c.lower())
            clean_titles.append(c)

    if not clean_titles:
        return {}

    headers = {"User-Agent": DEFAULT_REST_USER_AGENT}
    encoded = "|".join(urllib.parse.quote(t) for t in clean_titles)
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=pageassessments"
        f"&palimit=500&redirects=1&format=json&titles={encoded}"
    )

    results: Dict[str, Dict] = {}
    try:
        resp = requests.get(url, headers=headers, timeout=6)
        if resp.status_code != 200:
            logger.warning(f"Wikipedia assessments API returned status {resp.status_code}")
            for req in clean_titles:
                fallback = parse_page_assessment(req, {})
                results[req] = fallback
                results[req.replace(" ", "_")] = fallback
            return results
        r = resp.json()
        query = r.get("query", {})
        pages = query.get("pages", {})

        alias_map = {}
        for norm in query.get("normalized", []):
            alias_map[norm.get("from", "")] = norm.get("to", "")
        for red in query.get("redirects", []):
            alias_map[red.get("from", "")] = red.get("to", "")

        for pid, pdata in pages.items():
            t = pdata.get("title", "")
            raw_assess = pdata.get("pageassessments", {}) if pid != "-1" else {}
            parsed = parse_page_assessment(t, raw_assess)
            results[t] = parsed
            results[t.replace(" ", "_")] = parsed
            results[t.lower()] = parsed
            results[t.lower().replace(" ", "_")] = parsed

        for req in clean_titles:
            canon = alias_map.get(req, req)
            if canon in results:
                results[req] = results[canon]
                results[req.replace(" ", "_")] = results[canon]
            elif req not in results:
                fallback = parse_page_assessment(req, {})
                results[req] = fallback
                results[req.replace(" ", "_")] = fallback

    except Exception as e:
        logger.warning(f"Failed to fetch article assessments for {clean_titles} ({lang}): {e}")
        for req in clean_titles:
            fallback = parse_page_assessment(req, {})
            results[req] = fallback
            results[req.replace(" ", "_")] = fallback

    return results


def fetch_random_article_title(lang: str = "en") -> str:
    """
    Fetch a single random article title using Special:Random from the specified Wikipedia edition
    (defaults to English Wikipedia).
    Uses HEAD request to follow or inspect the 302/Location redirect, with GET fallback.
    """
    lang = (lang or "en").strip().lower()
    headers = {"User-Agent": DEFAULT_REST_USER_AGENT}

    # Preferred: MediaWiki API (language-independent; main namespace only).
    # Special:Random is localized on many editions (e.g. "Spécial:Aléatoire"), so
    # redirect parsing is unreliable there.
    try:
        r = requests.get(
            f"https://{lang}.wikipedia.org/w/api.php",
            params={
                "action": "query", "list": "random", "rnnamespace": 0,
                "rnlimit": 1, "format": "json",
            },
            headers=headers, timeout=5,
        )
        items = r.json().get("query", {}).get("random", [])
        if items and items[0].get("title"):
            return items[0]["title"]
    except Exception as e:
        logger.debug(f"Random API query for {lang} failed: {e}")

    url = f"https://{lang}.wikipedia.org/wiki/Special:Random"

    try:
        r = requests.head(url, headers=headers, allow_redirects=False, timeout=5)
        loc = r.headers.get("Location", "")
        if loc and "/wiki/" in loc:
            slug = loc.split("/wiki/")[-1].split("?")[0].split("#")[0]
            title = urllib.parse.unquote(slug).replace("_", " ")
            if title and title != "Special:Random":
                return title
    except Exception as e:
        logger.debug(f"HEAD request to {url} failed: {e}")

    # Fallback to GET with redirects followed
    try:
        r = requests.get(url, headers=headers, allow_redirects=True, timeout=5)
        parsed = urllib.parse.urlsplit(r.url)
        slug = parsed.path.split("/wiki/")[-1] if "/wiki/" in parsed.path else parsed.path.strip("/")
        slug = slug.split("?")[0].split("#")[0]
        title = urllib.parse.unquote(slug).replace("_", " ")
        if title and title != "Special:Random":
            return title
    except Exception as e:
        logger.warning(f"Failed to fetch random article from {url}: {e}")

    return ""


def fetch_random_article_pair(lang: str = "en") -> tuple[str, str]:
    """
    Fetch two distinct random article titles using Special:Random from the given Wikipedia edition.
    Special:Random exists on every edition, so this works for all languages. English-only
    placeholder fallbacks are used only for ``en``; other editions raise if nothing could be fetched.
    """
    lang = (lang or "en").strip().lower()
    titles: List[str] = []
    seen: Set[str] = set()

    for _ in range(6):
        title = fetch_random_article_title(lang=lang)
        if title and title.lower() not in seen:
            seen.add(title.lower())
            titles.append(title)
            if len(titles) == 2:
                break

    if len(titles) == 2:
        return titles[0], titles[1]
    if lang != "en":
        raise RuntimeError(f"Could not fetch two random articles from {lang}.wikipedia.org")
    if len(titles) == 1:
        fallback = "Philosophy" if titles[0].lower() != "philosophy" else "Science"
        return titles[0], fallback
    return "London", "New York City"

