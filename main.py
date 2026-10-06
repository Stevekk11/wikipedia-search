"""
FastAPI application for Wikipedia Link Hop Counter using Playwright.
Provides WebSocket streaming for real-time crawler updates,
Wikipedia autocomplete API, article assessment scoring API,
and serves the Bootstrap frontend.
"""

import asyncio
import io
import json
import logging
import os
import re
import sys
import urllib.parse
from typing import Dict, Optional

# Ensure UTF-8 stdout encoding on Windows
if sys.platform.startswith("win"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import requests
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from crawler import (
    WikipediaCrawler,
    get_wikipedia_info,
    fetch_article_assessments,
    fetch_random_article_pair,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("wikipedia_app")

app = FastAPI(
    title="Wikipedia Link Hop Counter",
    description="Finds and counts Wikipedia link hops between two pages using Playwright",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

# Ensure static directory exists
os.makedirs(STATIC_DIR, exist_ok=True)

# Mount static directory
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def get_index():
    """Serve the single page application."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse({"status": "Wikipedia Hop Counter API is running"})


@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    """Serve the favicon for standard browser icon requests."""
    favicon_path = os.path.join(STATIC_DIR, "favicon.svg")
    if os.path.exists(favicon_path):
        return FileResponse(favicon_path, media_type="image/svg+xml")
    return JSONResponse({"status": "Favicon not found"}, status_code=404)


@app.get("/api/autocomplete")
async def autocomplete(q: str = Query(..., min_length=1), lang: str = Query("en")):
    """
    Search Wikipedia articles for live autocomplete suggestions.
    Uses Wikipedia Opensearch API for the specified language.
    """
    try:
        lang_code = (lang or "en").strip().lower()
        url = f"https://{lang_code}.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(q)}&limit=8&namespace=0&format=json"
        headers = {"User-Agent": "WikipediaHopFinder/1.0 (contact@example.com)"}
        r = requests.get(url, headers=headers, timeout=4)
        if r.status_code == 200:
            data = r.json()
            # data format: [search_query, [titles], [descriptions], [urls]]
            titles = data[1] if len(data) > 1 else []
            descriptions = data[2] if len(data) > 2 else []
            urls = data[3] if len(data) > 3 else []
            results = []
            for i in range(len(titles)):
                results.append({
                    "title": titles[i],
                    "description": descriptions[i] if i < len(descriptions) else "",
                    "url": urls[i] if i < len(urls) else f"https://{lang_code}.wikipedia.org/wiki/{titles[i].replace(' ', '_')}",
                })
            return JSONResponse({"results": results})
    except Exception as e:
        logger.warning(f"Autocomplete error for '{q}' ({lang}): {e}")
    return JSONResponse({"results": []})


@app.get("/api/info")
async def get_info(title: str = Query(...), lang: str = Query("en")):
    """Fetch article canonical metadata, snippet, and thumbnail."""
    info = get_wikipedia_info(title, lang=lang)
    return JSONResponse(info)


@app.get("/api/article-assessments")
async def get_article_assessments(
    titles: str = Query(..., description="Comma or pipe-separated article titles or slugs"),
    lang: str = Query("en"),
):
    """
    Fetch Wikipedia article quality assessments, Bootstrap icons, colors, and WikiProjects.
    """
    try:
        clean_titles = [t.strip() for t in re.split(r"[,|]", titles) if t.strip()]
        data = fetch_article_assessments(clean_titles, lang=lang)
        return JSONResponse(data)
    except Exception as e:
        logger.error(f"Error fetching article assessments for '{titles}' ({lang}): {e}")
        return JSONResponse({}, status_code=500)


@app.get("/api/random")
async def get_random_articles():
    """
    Fetch two random articles from English Wikipedia using Special:Random.
    """
    try:
        start_title, target_title = await asyncio.to_thread(fetch_random_article_pair, "en")
        return JSONResponse({
            "articles": [start_title, target_title],
            "start": start_title,
            "target": target_title,
        })
    except Exception as e:
        logger.error(f"Error fetching random articles: {e}")
        return JSONResponse({"error": "Failed to fetch random articles from English Wikipedia"}, status_code=500)


@app.get("/api/presets")
async def get_presets(lang: str = Query("en")):
    """Curated list of interesting Wikipedia page pairs across languages."""
    lang_code = (lang or "en").strip().lower()

    presets_by_lang = {
        "en": [
            {
                "start": "London",
                "target": "New York City",
                "category": "Global Cities",
                "description": "Two world financial capitals and cultural centers",
            },
            {
                "start": "Python (programming language)",
                "target": "Philosophy",
                "category": "Classic Wikipedia Game",
                "description": "Explore the famous concept that all Wikipedia roads lead to Philosophy",
            },
            {
                "start": "Albert Einstein",
                "target": "Moon",
                "category": "Science & Space",
                "description": "From the father of relativity to Earth's celestial satellite",
            },
            {
                "start": "The Beatles",
                "target": "Tokyo",
                "category": "Music & Geography",
                "description": "Legendary British rock band to Japan's bustling capital",
            },
            {
                "start": "Batman",
                "target": "Renaissance",
                "category": "Culture & History",
                "description": "Gotham's superhero to the rebirth of European art and science",
            },
            {
                "start": "Coffee",
                "target": "International Space Station",
                "category": "Everyday to Cosmos",
                "description": "Morning beverage to humanity's orbital outpost",
            },
        ],
        "de": [
            {
                "start": "Berlin",
                "target": "Wien",
                "category": "Hauptstädte",
                "description": "Zwei historische europäische Hauptstädte und Kulturzentren",
            },
            {
                "start": "Albert Einstein",
                "target": "Philosophie",
                "category": "Wissenschaft & Denken",
                "description": "Vom Nobelpreisträger zur Mutter aller Wissenschaften",
            },
            {
                "start": "Kaffee",
                "target": "Mond",
                "category": "Alltag zu Kosmos",
                "description": "Vom Heißgetränk zu unserem Trabanten",
            },
            {
                "start": "Johann Wolfgang von Goethe",
                "target": "Rom",
                "category": "Literatur & Reisen",
                "description": "Von der Weimarer Klassik zur italienischen Reise",
            },
        ],
        "fr": [
            {
                "start": "Paris",
                "target": "Montréal",
                "category": "Francophonie",
                "description": "Deux grandes métropoles francophones",
            },
            {
                "start": "Tour Eiffel",
                "target": "Philosophie",
                "category": "Culture & Pensée",
                "description": "Du monument parisien emblématique à la philosophie",
            },
            {
                "start": "Marie Curie",
                "target": "Lune",
                "category": "Science & Espace",
                "description": "Pionnière de la radioactivité jusqu'à la Lune",
            },
            {
                "start": "Victor Hugo",
                "target": "Révolution française",
                "category": "Histoire & Littérature",
                "description": "De l'auteur des Misérables à l'histoire de France",
            },
        ],
        "es": [
            {
                "start": "Madrid",
                "target": "Buenos Aires",
                "category": "Grandes Ciudades",
                "description": "Dos capitales culturales del mundo hispanohablante",
            },
            {
                "start": "Miguel de Cervantes",
                "target": "Filosofía",
                "category": "Literatura & Pensamiento",
                "description": "Del creador del Quijote a la filosofía clásica",
            },
            {
                "start": "Café",
                "target": "Luna",
                "category": "Cotidiano al Cosmos",
                "description": "Desde la bebida universal hasta nuestro satélite",
            },
            {
                "start": "Amazonas",
                "target": "Inteligencia artificial",
                "category": "Naturaleza a Tecnología",
                "description": "Del río más caudaloso a las redes neuronales",
            },
        ],
        "it": [
            {
                "start": "Roma",
                "target": "Parigi",
                "category": "Capitali d'Europa",
                "description": "Dalla Città Eterna alla capitale francese",
            },
            {
                "start": "Leonardo da Vinci",
                "target": "Luna",
                "category": "Arte e Scienza",
                "description": "Dal genio del Rinascimento alla corsa allo spazio",
            },
            {
                "start": "Dante Alighieri",
                "target": "Filosofia",
                "category": "Letteratura e Pensiero",
                "description": "Dal Sommo Poeta al pensiero filosofico",
            },
        ],
        "ja": [
            {
                "start": "東京",
                "target": "京都",
                "category": "日本の都市",
                "description": "日本の首都から古都への旅",
            },
            {
                "start": "富士山",
                "target": "月",
                "category": "自然と宇宙",
                "description": "日本最高峰から地球の衛星へ",
            },
            {
                "start": "夏目漱石",
                "target": "哲学",
                "category": "文学と哲学",
                "description": "文豪から哲学の探求へ",
            },
        ],
        "ru": [
            {
                "start": "Москва",
                "target": "Санкт-Петербург",
                "category": "Города России",
                "description": "Две столицы: современная и историческая",
            },
            {
                "start": "Юрий Гагарин",
                "target": "Луна",
                "category": "Космонавтика",
                "description": "От первого человека в космосе до спутника Земли",
            },
            {
                "start": "Лев Толстой",
                "target": "Философия",
                "category": "Литература и мысль",
                "description": "От классика литературы к философским истокам",
            },
        ],
    }

    presets = presets_by_lang.get(lang_code, presets_by_lang["en"])
    return JSONResponse({"presets": presets, "lang": lang_code})


@app.post("/api/shutdown")
async def shutdown_server():
    """Gracefully shut down the FastAPI / Uvicorn server."""
    def kill_later():
        import os
        import signal
        import time
        time.sleep(0.5)
        try:
            os.kill(os.getpid(), signal.SIGTERM)
        except Exception:
            os._exit(0)

    asyncio.create_task(asyncio.to_thread(kill_later))
    return JSONResponse({
        "status": "shutting_down",
        "message": "WikiHop server is shutting down..."
    })


@app.websocket("/ws/search")
async def websocket_search(websocket: WebSocket):
    """
    WebSocket endpoint for real-time Wikipedia link hop search.
    Handles start, stop, and streams Playwright intermediate page visits.
    """
    await websocket.accept()
    current_crawler: Optional[WikipediaCrawler] = None
    crawler_task: Optional[asyncio.Task] = None

    async def run_crawler(params: dict):
        nonlocal current_crawler
        start = params.get("start", "").strip()
        target = params.get("target", "").strip()
        lang = params.get("lang", "en").strip().lower()
        algorithm = params.get("algorithm", "heuristic")
        max_pages = int(params.get("max_pages", 40))
        max_depth = int(params.get("max_depth", 5))
        capture_screenshots = bool(params.get("capture_screenshots", True))
        headless = bool(params.get("headless", True))
        context_words = int(params.get("context_words", 150))
        use_embeddings = bool(params.get("use_embeddings", True))
        adaptive_balancing = bool(params.get("adaptive_balancing", True))

        current_crawler = WikipediaCrawler(
            start_input=start,
            target_input=target,
            algorithm=algorithm,
            max_pages=max_pages,
            max_depth=max_depth,
            headless=headless,
            capture_screenshots=capture_screenshots,
            context_words=context_words,
            lang=lang,
            use_embeddings=use_embeddings,
            adaptive_balancing=adaptive_balancing,
        )

        try:
            async for event in current_crawler.search():
                await websocket.send_text(json.dumps(event))
                if event.get("event") in ("found", "not_found", "cancelled", "error"):
                    break
        except Exception as e:
            logger.error(f"Error during crawl execution: {e}", exc_info=True)
            await websocket.send_text(json.dumps({
                "event": "error",
                "message": f"Crawling error: {str(e)}"
            }))

    try:
        while True:
            text = await websocket.receive_text()
            data = json.loads(text)
            action = data.get("action")

            if action == "start":
                # Cancel existing if running
                if current_crawler:
                    current_crawler.cancel()
                if crawler_task and not crawler_task.done():
                    crawler_task.cancel()

                crawler_task = asyncio.create_task(run_crawler(data))

            elif action == "stop":
                if current_crawler:
                    current_crawler.cancel()
                if crawler_task and not crawler_task.done():
                    crawler_task.cancel()
                await websocket.send_text(json.dumps({
                    "event": "cancelled",
                    "message": "Search stopped by user."
                }))

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        if current_crawler:
            current_crawler.cancel()
        if crawler_task and not crawler_task.done():
            crawler_task.cancel()
    except Exception as e:
        logger.warning(f"WebSocket session error: {e}")
        if current_crawler:
            current_crawler.cancel()
        if crawler_task and not crawler_task.done():
            crawler_task.cancel()


if __name__ == "__main__":
    from run import get_or_create_ssl_cert
    cert_file, key_file = get_or_create_ssl_cert()
    ssl_kwargs = {}
    if cert_file and key_file and os.path.exists(cert_file) and os.path.exists(key_file):
        ssl_kwargs["ssl_certfile"] = cert_file
        ssl_kwargs["ssl_keyfile"] = key_file
    port = int(os.environ.get("PORT", 8005))
    host = os.environ.get("HOST", "0.0.0.0")
    uvicorn.run("main:app", host=host, port=port, reload=False, ws="auto", **ssl_kwargs)
