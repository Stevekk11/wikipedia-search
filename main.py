"""
FastAPI application for Wikipedia Link Hop Counter using Playwright.
Provides WebSocket streaming for real-time crawler updates,
Wikipedia autocomplete API, and serves the Bootstrap frontend.
"""

import asyncio
import io
import json
import logging
import os
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

from crawler import WikipediaCrawler, get_wikipedia_info

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


@app.get("/api/autocomplete")
async def autocomplete(q: str = Query(..., min_length=1)):
    """
    Search Wikipedia articles for live autocomplete suggestions.
    Uses Wikipedia Opensearch API.
    """
    try:
        url = f"https://en.wikipedia.org/w/api.php?action=opensearch&search={urllib.parse.quote(q)}&limit=8&namespace=0&format=json"
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
                    "url": urls[i] if i < len(urls) else f"https://en.wikipedia.org/wiki/{titles[i].replace(' ', '_')}",
                })
            return JSONResponse({"results": results})
    except Exception as e:
        logger.warning(f"Autocomplete error for '{q}': {e}")
    return JSONResponse({"results": []})


@app.get("/api/info")
async def get_info(title: str = Query(...)):
    """Fetch article canonical metadata, snippet, and thumbnail."""
    info = get_wikipedia_info(title)
    return JSONResponse(info)


@app.get("/api/presets")
async def get_presets():
    """Curated list of interesting Wikipedia page pairs."""
    presets = [
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
    ]
    return JSONResponse({"presets": presets})


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
        algorithm = params.get("algorithm", "heuristic")
        max_pages = int(params.get("max_pages", 40))
        max_depth = int(params.get("max_depth", 5))
        capture_screenshots = bool(params.get("capture_screenshots", True))
        headless = bool(params.get("headless", True))
        context_words = int(params.get("context_words", 150))

        current_crawler = WikipediaCrawler(
            start_input=start,
            target_input=target,
            algorithm=algorithm,
            max_pages=max_pages,
            max_depth=max_depth,
            headless=headless,
            capture_screenshots=capture_screenshots,
            context_words=context_words,
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
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=False)
