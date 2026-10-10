"""
Wikipedia REST and Action API utilities.
Handles title normalization, summary/thumbnail metadata lookup,
target category extraction, incoming backlinks querying,
and Wikipedia quality assessment scores & WikiProjects retrieval.
"""

import logging
import re
import urllib.parse
from typing import Any, Dict, List, Optional, Set

import requests

from .config import (
    DEFAULT_REST_USER_AGENT,
    DEFAULT_USER_AGENT,
    DISALLOWED_PREFIXES,
    HIGH_CENTRALITY_HUBS,
)

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


def fetch_target_backlinks_detailed(target_slug: str, limit: int = 500, lang: str = "en") -> List[Dict[str, str]]:
    """
    Fetch articles that link directly to the target article.
    Uses Wikipedia Action API list=backlinks with blnamespace=0 and blfilterredir=nonredirects.
    """
    lang = (lang or "en").strip().lower()
    clean_slug = target_slug.strip().replace(" ", "_")
    encoded = urllib.parse.quote(clean_slug.replace("_", " "))
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=backlinks"
        f"&bltitle={encoded}&bllimit={min(limit, 500)}&blnamespace=0&blfilterredir=nonredirects&format=json"
    )
    backlinks: List[Dict[str, str]] = []
    try:
        r = requests.get(url, headers=headers, timeout=5).json()
        bl_list = r.get("query", {}).get("backlinks", [])
        for b in bl_list:
            t = b.get("title", "")
            if t and not any(t.startswith(p) for p in DISALLOWED_PREFIXES):
                backlinks.append({"title": t, "slug": t.replace(" ", "_")})
    except Exception as e:
        logger.warning(f"Failed to fetch detailed backlinks for {target_slug} ({lang}): {e}")
    return backlinks


def fetch_target_backlinks(target_slug: str, limit: int = 500, lang: str = "en") -> Set[str]:
    """
    Fetch articles that link directly to the target article (What Links Here).
    Any page linking to these backlinks is guaranteed to be 1 hop away from target!
    """
    detailed = fetch_target_backlinks_detailed(target_slug, limit=limit, lang=lang)
    backlinks: Set[str] = set()
    for item in detailed:
        t = item["title"]
        s = item["slug"]
        backlinks.add(t.lower())
        backlinks.add(s.lower())
    return backlinks


def fetch_target_category_titles(target_slug: str, lang: str = "en") -> List[str]:
    """
    Fetch the list of topical Category: titles for a Wikipedia article,
    ignoring maintenance, tracking, and metadata categories.
    """
    lang = (lang or "en").strip().lower()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    url = (
<<<<<<< HEAD
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=linkshere"
        f"&titles={urllib.parse.quote(target_slug)}&lhlimit={limit}&lhnamespace=0&format=json"
=======
        f"https://{lang}.wikipedia.org/w/api.php?action=query&prop=categories"
        f"&titles={urllib.parse.quote(target_slug)}&cllimit=50&format=json"
>>>>>>> 2a65300 (Implement Improvement 2: Category Bridge Seeding for niche targets)
    )
    categories: List[str] = []
    ignored = [
        "articles", "all ", "use ", "pages", "cs1", "commons",
        "short", "statements", "webarchive", "wikidata", "coordinates",
        "gadget", "hidden", "disambiguation", "redirects", "infobox"
    ]
    try:
        r = requests.get(url, headers=headers, timeout=4).json()
        pages = r.get("query", {}).get("pages", {})
        for pid, p in pages.items():
            for cat in p.get("categories", []):
                c_title = cat.get("title", "")
                if not any(ign in c_title.lower() for ign in ignored):
                    categories.append(c_title)
    except Exception as e:
        logger.warning(f"Failed to fetch category titles for {target_slug} ({lang}): {e}")
    return categories


def fetch_target_categories(target_slug: str, lang: str = "en") -> Set[str]:
    """
    Fetch Wikipedia categories of the target article to enrich semantic keywords.
    """
    cat_titles = fetch_target_category_titles(target_slug, lang=lang)
    cat_words: Set[str] = set()
    for c_title in cat_titles:
        clean = c_title.replace("Category:", "")
        words = re.findall(r"\w+", clean.lower())
        cat_words.update(w for w in words if len(w) > 3)
    return cat_words


def fetch_category_members(cat_title: str, limit: int = 50, lang: str = "en") -> List[Dict[str, str]]:
    """
    Fetch mainspace article members belonging to a Wikipedia Category.
    """
    lang = (lang or "en").strip().lower()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    clean_cat = cat_title.strip()
    if not clean_cat.startswith("Category:"):
        clean_cat = f"Category:{clean_cat}"
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query&list=categorymembers"
        f"&cmtitle={urllib.parse.quote(clean_cat)}&cmlimit={min(limit, 100)}&cmnamespace=0&format=json"
    )
    members: List[Dict[str, str]] = []
    try:
        r = requests.get(url, headers=headers, timeout=4).json()
        for item in r.get("query", {}).get("categorymembers", []):
            t = item.get("title", "")
            if t and not any(t.startswith(p) for p in DISALLOWED_PREFIXES):
                members.append({"title": t, "slug": t.replace(" ", "_")})
    except Exception as e:
        logger.debug(f"Failed to fetch members for {cat_title} ({lang}): {e}")
    return members


def fetch_niche_target_bridges(
    target_slug: str,
    target_title: str,
    direct_backlinks: List[Dict[str, str]],
    lang: str = "en",
) -> Dict[str, Any]:
    """
    Category Bridge Seeding for niche / low-connectivity targets (< 25 backlinks).
    Analyzes topical categories, identifies core category topic pages, and queries
    incoming backlinks of the target's direct backlinks to establish verified 2-hop
    feeder chains.
    """
    lang = (lang or "en").strip().lower()
    headers = {"User-Agent": DEFAULT_USER_AGENT}
    cat_titles = fetch_target_category_titles(target_slug, lang=lang)

    # 1. Derive candidate topic pages from category titles (e.g. 'Villages in Gloucestershire' -> 'Gloucestershire')
    category_topics: Set[str] = set()
    for cat in cat_titles:
        c_clean = cat.replace("Category:", "").strip()
        category_topics.add(c_clean)
        for sep in [" in ", " of ", " from ", " by "]:
            if sep in c_clean:
                parent_topic = c_clean.split(sep)[-1].strip()
                if len(parent_topic) > 2:
                    category_topics.add(parent_topic)

    # 2. Collect category members (from first 2 topical categories)
    cat_members: List[Dict[str, str]] = []
    for cat in cat_titles[:2]:
        cat_members.extend(fetch_category_members(cat, limit=30, lang=lang))

    cat_member_slugs = {m["slug"].lower(): m for m in cat_members}
    direct_slugs = {b["slug"].lower() for b in direct_backlinks}

    # 3. Identify direct backlinks that are category members or match category topics
    boosted_direct = []
    for b in direct_backlinks:
        b_slug_l = b["slug"].lower()
        is_cat_match = b_slug_l in cat_member_slugs or any(t.lower() in b["title"].lower() for t in category_topics)
        boosted_direct.append({
            **b,
            "is_category_bridge": is_cat_match,
        })

    # 4. Discover 2-hop feeder bridgeheads (parents of direct backlinks)
    two_hop_bridges: Dict[str, Dict[str, Any]] = {}
    for b in direct_backlinks[:8]:
        b_slug = b["slug"]
        url_p = (
            f"https://{lang}.wikipedia.org/w/api.php?action=query&list=backlinks"
            f"&bltitle={urllib.parse.quote(b_slug)}&bllimit=40&blnamespace=0&blfilterredir=nonredirects&format=json"
        )
        try:
            rp = requests.get(url_p, headers=headers, timeout=3).json()
            for item in rp.get("query", {}).get("backlinks", []):
                pt = item.get("title", "")
                ps = pt.replace(" ", "_")
                ps_lower = ps.lower()
                if (
                    ps_lower not in direct_slugs
                    and ps_lower != target_slug.lower()
                    and not any(pt.startswith(pfx) for pfx in DISALLOWED_PREFIXES)
                ):
                    if ps_lower not in two_hop_bridges:
                        is_hub = ps_lower in HIGH_CENTRALITY_HUBS
                        is_cat_rel = ps_lower in cat_member_slugs or any(t.lower() in pt.lower() for t in category_topics)
                        two_hop_bridges[ps_lower] = {
                            "parent_slug": ps,
                            "parent_title": pt,
                            "bridge_slug": b["slug"],
                            "bridge_title": b["title"],
                            "is_hub": is_hub,
                            "is_category_related": is_cat_rel,
                        }
        except Exception:
            pass

    return {
        "category_titles": cat_titles,
        "category_topics": list(category_topics),
        "boosted_direct": boosted_direct,
        "two_hop_bridges": two_hop_bridges,
    }


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

