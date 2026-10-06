# WikiHop 🌐 &bull; Wikipedia Link Hop Counter

An interactive web application built with **Playwright**, **FastAPI**, and **Bootstrap 5** that navigates live Wikipedia articles, tracks degrees of separation, and calculates the exact number of link hops required to travel from a starting Wikipedia page to a target page (e.g., from *London* to *New York City*).

---

## ✨ Features

- **Connecting Link Context (150 Words Before & After)**: Extracts and presents the surrounding ~150 words before and ~150 words after the connecting link in the source article with full link highlighting, word counts, and one-click copy.
- **Intermediate Links Used & Algorithmic Rationale**: Comprehensive step-by-step breakdown of every link traversed in the final connecting path and *why* it was chosen by the algorithm:
  - **15-Word Surrounding Context**: Shows ~15 words before and ~15 words after each intermediate link on its source page with highlighted anchor text.
  - Quantitative score breakdown (e.g. `+5,000 pts Direct Feeder`, `+120 pts Keyword Overlap`, `+45 pts Global Connector Hub`, `+10,000 pts Target Discovered`)
  - Categorical decision badges (`⭐ Direct Feeder`, `🌐 Global Connector Hub`, `🎯 Target Discovered`, `BFS Level`)
  - Natural-language explanations detailing the decision-making behind each branch expansion
  - Factor tags indicating category overlaps, token intersections, and structural graph centrality
- **Dedicated Settings Panel**: Customize the surrounding context length (slider from 25 to 350+ words), switch search algorithms, configure max page and hop depth limits, and toggle live screenshots.
- **Automated Playwright Traversal**: Uses Microsoft Playwright (Chromium/Edge) to load actual Wikipedia pages, execute in-page DOM parsing, extract all internal links, and detect connections.
- **Degrees of Separation (Hop Counter)**: Counts intermediate hops taken to find the target page.
- **Full Intermediate Pages Log**: Displays every single intermediate page visited by Playwright, complete with:
  - Step index and current hop depth
  - Article title and link to the live Wikipedia page
  - Count of outgoing links discovered
  - Summary snippet of the article
  - Live page thumbnail preview
- **Live Visual Monitor**: Captures real-time Playwright browser screenshots and displays what the browser is navigating at that very second.
- **Visual Hop Chain**: Renders a clear node-link path from Start ➔ Intermediate Hops ➔ Target once found.
- **Search Strategies**:
  - **Simultaneous Bidirectional Meet-in-the-Middle Search**: Concurrently searches forward from the **Start** article and backward from the **Target** article (via incoming backlinks and Special:WhatLinksHere). The search frontiers alternately expand in Playwright until their outgoing or incoming links intersect. Searching from both sides simultaneously dramatically cuts search complexity from $O(b^d)$ to $O(b^{d/2})$, finding connections in obscure pairings (such as *Orlando &rarr; Oral sex*) with exceptional speed.
  - **Dynamic Frontier Direction Tracking**: Live UI badges display whether Playwright is currently expanding `⏩ Forward from Start` or `⏪ Backward from Target`, with split KPI counters (`X forward • Y backward`).
  - **Meeting Bridge Stitched Path**: When the two search frontiers collide, the forward path and reverse path are stitched together seamlessly with a dedicated `🤝 Meeting Bridge` intermediate step highlighting the exact connecting link.
  - **Semantic Category & Hub Weighting**: Integrates target categories and boosts high-centrality global bridges (countries, foundational disciplines) while penalizing dead-end local streets and school districts.
  - **Breadth-First Search (BFS)**: Systematically checks pages level by level to discover the shortest path.
- **Wikipedia Autocomplete**: Real-time article suggestions as you type in the start or target fields.
- **Quick Presets**: One-click exploration of popular Wikipedia pairings (e.g., *London &rarr; New York City*, *Python &rarr; Philosophy*, *Albert Einstein &rarr; Moon*).
- **Responsive Bootstrap 5 UI**: Clean, modern interface with dark/light mode toggle, progress indicators, settings modal, and interactive modals.
- **Graceful Server Shutdown**: Built-in red Shutdown button with confirmation modal and full-screen state overlay that cleanly terminates the server and background browser instances.

---

## 🛠️ Architecture

```
┌────────────────────────────────┐       WebSocket        ┌────────────────────────────────┐
│   Bootstrap 5 Frontend         │ <════════════════════> │    FastAPI ASGI Server         │
│   (index.html, style.css, app) │                        │    (main.py)                   │
└────────────────────────────────┘                        └───────────────┬────────────────┘
                                                                          │
                                                                          ▼
                                                          ┌────────────────────────────────┐
                                                          │   Playwright Crawler Engine    │
                                                          │   (crawler/ - Chromium/Edge)   │
                                                          └───────────────┬────────────────┘
                                                                          │
                                                                          ▼
                                                          ┌────────────────────────────────┐
                                                          │    Live Wikipedia Articles     │
                                                          │    (https://en.wikipedia.org)  │
                                                          └────────────────────────────────┘
```

---

## 🚀 Quick Start

### 1. Requirements

- Python 3.10+
- Microsoft Edge or Google Chrome (or default Chromium)

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the Application

```bash
python run.py
```

Or run via Uvicorn:

```bash
uvicorn main:app --host 127.0.0.1 --port 8000
```

Open your browser at **[http://localhost:8000](http://localhost:8000)**.

---

## 🧪 Testing

To test the crawler directly from the command line:

```bash
python -c "import asyncio; from crawler import WikipediaCrawler; asyncio.run(WikipediaCrawler('London', 'New York City', max_pages=10).search())"
```

---

## 📂 Project Structure

```
wikipedia-search/
├── crawler/             # Modular Playwright crawling engine
│   ├── __init__.py      # Package exports and platform UTF-8 setup
│   ├── api.py           # Wikipedia REST / Action API utilities
│   ├── browser.py       # Playwright browser lifecycle & channel fallbacks
│   ├── config.py        # Hubs, dead-end patterns, disallowed namespaces
│   ├── engine.py        # Bidirectional search engine (WikipediaCrawler)
│   ├── extractor.py     # In-page DOM extraction and context scraping
│   └── scorer.py        # Heuristic scoring & decision rationale engine
├── main.py              # FastAPI server, WebSocket handler, and autocomplete endpoints
├── run.py               # Application launcher
├── requirements.txt     # Python package requirements
├── .gitignore           # Git ignore rules
├── static/
│   ├── index.html       # Bootstrap 5 responsive UI
│   ├── style.css        # Custom CSS, node hop chains & animations
│   └── app.js           # WebSocket client, autocomplete, live dashboard logic
└── README.md            # Documentation
```

---

## 📄 License

MIT
