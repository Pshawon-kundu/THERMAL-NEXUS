"""Definitive Gate 1C DOM measurement: per-frame ready-wait, then 15 s trace."""

import sys
import time

sys.path.insert(0, ".")
from tools.gate1c_measure import INSTALL, READ  # noqa: E402

from playwright.sync_api import sync_playwright  # noqa: E402

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8501/overview"
SECONDS = int(sys.argv[2]) if len(sys.argv) > 2 else 15

with sync_playwright() as pw:
    browser = pw.chromium.launch(args=["--no-sandbox"])
    page = browser.new_page(viewport={"width": 1920, "height": 1080})
    page.goto(URL, wait_until="domcontentloaded")
    # Wait until ALL expected iframes exist and carry content.
    deadline = time.time() + 120
    ready = []
    while time.time() < deadline:
        ready = []
        for frame in page.frames[1:]:
            try:
                text = frame.locator("body").inner_text()
                ready.append(len(text.strip()) > 0)
            except Exception:
                ready.append(False)
        if len(ready) >= 5 and all(ready):
            break
        time.sleep(2)
    print("FRAMES_READY:", ready)
    for frame in page.frames:
        try:
            frame.evaluate(INSTALL)
        except Exception as exc:
            print("install-skip:", str(exc)[:80])
    time.sleep(SECONDS)
    totals = {"added": 0, "removed": 0, "bigReplace": 0,
              "plotReplace": 0, "attrPlot": 0}
    for index, frame in enumerate(page.frames):
        try:
            result = frame.evaluate(READ)
        except Exception as exc:
            print(f"frame {index}: read-skip {str(exc)[:60]}")
            continue
        print(f"frame {index}: {result}")
        if result.get("added", -1) < 0:
            continue
        for key in totals:
            totals[key] += result.get(key, 0)
    print("SECONDS:", SECONDS)
    print("TOTALS_ALL_FRAMES:", totals)
    browser.close()
print("DONE")
