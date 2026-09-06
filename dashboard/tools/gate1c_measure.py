"""Phase A/C flicker measurement: MutationObserver in TOP doc + all iframes."""

import sys
import time

from playwright.sync_api import sync_playwright

INSTALL = """() => {
  window.__tnMut = {added: 0, removed: 0, bigReplace: 0, plotReplace: 0, attrPlot: 0};
  const isPlot = (n) => n.nodeType === 1 && (
    (n.classList && n.classList.contains('js-plotly-plot')) ||
    (n.querySelector && n.querySelector('.js-plotly-plot')));
  new MutationObserver((records) => {
    for (const r of records) {
      if (r.type === 'attributes') {
        if (r.target.closest && r.target.closest('.js-plotly-plot')) window.__tnMut.attrPlot++;
        continue;
      }
      for (const n of r.addedNodes) {
        window.__tnMut.added++;
        const size = n.nodeType === 1 && n.querySelectorAll ? n.querySelectorAll('*').length : 0;
        if (size > 30) window.__tnMut.bigReplace++;
        if (isPlot(n)) window.__tnMut.plotReplace++;
      }
      for (const n of r.removedNodes) window.__tnMut.removed++;
    }
  }).observe(document.body || document.documentElement,
    {childList: true, subtree: true, attributes: true,
     attributeFilter: ['style', 'class', 'd', 'points']});
  return 'installed';
}"""

READ = """() => window.__tnMut || {added: -1}"""


def measure(url: str, seconds: int) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 1920, "height": 1080})
        page.goto(url, wait_until="domcontentloaded")
        deadline = time.time() + 90
        while time.time() < deadline:
            try:
                texts = [f.locator("body").inner_text() for f in page.frames[1:3]]
                if any("Seq" in t for t in texts):
                    break
            except Exception:
                pass
            time.sleep(2)
        print("LIVE_CONTENT_STREAMING")
        for frame in page.frames:
            try:
                print("install:", frame.evaluate(INSTALL)[:20])
            except Exception as exc:
                print("install-skip:", str(exc)[:80])
        time.sleep(seconds)
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
        print("SECONDS:", seconds)
        print("TOTALS_ALL_FRAMES:", totals)
        browser.close()
    print("DONE")


if __name__ == "__main__":
    measure(sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8501/overview",
            int(sys.argv[2]) if len(sys.argv) > 2 else 15)
