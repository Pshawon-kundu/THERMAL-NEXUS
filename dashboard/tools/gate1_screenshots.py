"""Gate 1B screenshot capture: Playwright + real waits, one shot per page."""

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parents[1] / "evidence" / "gate1b"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = ["overview", "thermal", "location", "system"]
MARKERS = {
    "overview": "Thermal summary",
    "thermal": "Temperature history",
    "location": "GPS history",
    "system": "LoRa configuration",
}

width = int(sys.argv[1]) if len(sys.argv) > 1 else 1920
height = int(sys.argv[2]) if len(sys.argv) > 2 else 1080
tag = sys.argv[3] if len(sys.argv) > 3 else f"{width}x{height}"

with sync_playwright() as pw:
    browser = pw.chromium.launch(args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": width, "height": height})
    for name in PAGES:
        page.goto(f"http://localhost:8501/{name}", wait_until="domcontentloaded")
        try:
            page.get_by_text(MARKERS[name], exact=False).first.wait_for(timeout=90000)
        except Exception as exc:
            print(f"{name}: marker wait failed: {str(exc)[:120]}")
        page.wait_for_timeout(5000)
        dest = OUT / f"{name}_{tag}.png"
        page.screenshot(path=str(dest), full_page=False)
        print(f"saved {dest} ({dest.stat().st_size} bytes)")
    browser.close()
print("DONE")
