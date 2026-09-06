"""Gate 1C camera/map stability: rotate, wait through polls, compare state.

Prerequisites, in order:
  1. Telemetry API:  python -m host.api.server --port 8502
  2. Dashboard:      streamlit run host/dashboard/app.py --server.port 8501

The chamber iframe only plots once /api/telemetry/latest reports hasData,
so this gate preflights the API before touching the browser. Exit codes:
0 = pass, 1 = camera did not persist, 2 = setup/chamber failure.
"""

import json
import sys
import time
import urllib.request

from playwright.sync_api import Frame, Page, sync_playwright

TELEMETRY_URL = "http://127.0.0.1:8502/api/telemetry/latest"
DASHBOARD_URL = "http://127.0.0.1:8501/"

FIND_CHAMBER = """() => {
    for (const d of document.querySelectorAll('.js-plotly-plot')) {
        if (d._fullLayout && d._fullLayout.scene && d._fullLayout.scene.camera) {
            return true;
        }
    }
    return false;
}"""

PROBE_STATE = """() => ({
    ch: !!document.getElementById('ch'),
    wait: (() => {
        const w = document.getElementById('ch-wait');
        return w ? w.style.display !== 'none' : null;
    })(),
    plots: document.querySelectorAll('.js-plotly-plot').length,
})"""

GET_EYE = """() => {
    for (const d of document.querySelectorAll('.js-plotly-plot')) {
        if (d._fullLayout && d._fullLayout.scene && d._fullLayout.scene.camera) {
            return d._fullLayout.scene.camera.eye;
        }
    }
    return null;
}"""

SET_EYE = """(eye) => {
    for (const d of document.querySelectorAll('.js-plotly-plot')) {
        if (d._fullLayout && d._fullLayout.scene && d._fullLayout.scene.camera) {
            Plotly.relayout(d, {'scene.camera.eye': eye});
            return true;
        }
    }
    return false;
}"""


def preflight() -> None:
    try:
        with urllib.request.urlopen(TELEMETRY_URL, timeout=5) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except Exception as exc:
        print(f"CAMERA_TEST: telemetry API unreachable ({exc})")
        sys.exit(2)
    if not payload.get("hasData"):
        print("CAMERA_TEST: telemetry API has no data; chamber cannot render")
        sys.exit(2)


def find_chamber(
    page: Page,
    timeout_s: float = 90.0,
    stall_s: float = 20.0,
    max_renavigations: int = 3,
) -> tuple[Frame | None, dict]:
    """Poll frames for the chamber plot; re-navigate if the session stalls."""
    deadline = time.time() + timeout_s
    renav = 0
    saw_ch = 0
    saw_iframes = False
    last_state = {}
    errors = []
    stall_since = time.time()
    while time.time() < deadline:
        # Pump the CDP event loop: a bare sleep() never round-trips the
        # connection, so page.frames tracking can go stale at 0 forever and
        # the stall re-navigation then discards a session that was about to
        # render. The DOM query is also the authoritative iframe ground truth.
        try:
            dom_iframes = page.evaluate("document.querySelectorAll('iframe').length")
        except Exception as exc:
            errors.append("main eval: " + str(exc)[:120])
            dom_iframes = 0
        frames = page.frames[1:]
        if frames or dom_iframes:
            saw_iframes = True
            stall_since = time.time()
        for frame in frames:
            try:
                state = frame.evaluate(PROBE_STATE)
                if state["ch"]:
                    saw_ch += 1
                    last_state = state
                if frame.evaluate(FIND_CHAMBER):
                    return frame, {
                        "saw_ch": saw_ch,
                        "saw_iframes": saw_iframes,
                        "last_state": last_state,
                        "errors": errors,
                    }
            except Exception as exc:
                errors.append(str(exc)[:120])
        if (
            not frames
            and dom_iframes == 0
            and time.time() - stall_since > stall_s
            and renav < max_renavigations
        ):
            renav += 1
            stall_since = time.time()
            try:
                page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            except Exception as exc:
                errors.append("renav: " + str(exc)[:100])
        time.sleep(3)
    return None, {
        "saw_ch": saw_ch,
        "saw_iframes": saw_iframes,
        "last_state": last_state,
        "errors": errors,
    }


def main() -> int:
    preflight()
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1080})
            page.goto(DASHBOARD_URL, wait_until="domcontentloaded")
            chamber, diag = find_chamber(page)
            if chamber is None:
                print("CAMERA_TEST: chamber never rendered")
                print("iframes ever seen:", diag["saw_iframes"])
                print("frames with #ch (cumulative polls):", diag["saw_ch"])
                print("last #ch state:", diag["last_state"])
                if diag["errors"]:
                    print("sample errors:", diag["errors"][:3])
                return 2
            print("chamber found")
            eye_before = chamber.evaluate(GET_EYE)
            print("eye before:", eye_before)
            if not chamber.evaluate(SET_EYE, {"x": -1.8, "y": 0.6, "z": 0.9}):
                print("CAMERA_TEST: camera relayout failed")
                return 2
            time.sleep(2)
            eye_set = chamber.evaluate(GET_EYE)
            print("eye set:", eye_set)
            time.sleep(10)  # ~8 poll/react cycles at 1.2 s
            eye_after = chamber.evaluate(GET_EYE)
            print("eye after:", eye_after)
            if not isinstance(eye_set, dict) or not isinstance(eye_after, dict):
                print("CAMERA_PERSISTED: False")
                return 1
            same = (
                abs(eye_after["x"] - eye_set["x"]) < 1e-9
                and abs(eye_after["y"] - eye_set["y"]) < 1e-9
                and abs(eye_after["z"] - eye_set["z"]) < 1e-9
            )
            print("CAMERA_PERSISTED:", same)
            return 0 if same else 1
        finally:
            browser.close()


if __name__ == "__main__":
    sys.exit(main())
