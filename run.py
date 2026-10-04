"""
Startup script for WikiHop - Wikipedia Link Hop Counter.
Runs the FastAPI web server on http://localhost:8000.
"""

import sys
import webbrowser
import uvicorn

def main():
    port = 8000
    host = "127.0.0.1"
    url = f"http://{host}:{port}"
    print("=" * 60)
    print("  WikiHop - Wikipedia Link Hop Counter (Playwright)")
    print(f"  Starting web server at {url}")
    print("=" * 60)

    # Launch browser automatically
    try:
        webbrowser.open(url)
    except Exception:
        pass

    uvicorn.run("main:app", host=host, port=port, reload=False)

if __name__ == "__main__":
    main()
