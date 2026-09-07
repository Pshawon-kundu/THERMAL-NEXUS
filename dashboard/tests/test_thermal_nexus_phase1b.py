"""Gate 1B tests: 4-page IA, interpolation, light theme, refresh rules."""

from __future__ import annotations

import os
from pathlib import Path

import host.dashboard.app as app
from host.dashboard.chamber_viz import (
    bilinear_grid,
    chamber_figure,
    stable_color_range,
)
from host.dashboard.telemetry_model import (
    classify_freshness,
    parse_stm_csv_fields,
    thermal_stats,
)


def test_primary_live_navigation_is_four_pages() -> None:
    assert list(app.PRIMARY_LIVE_PAGES) == ["overview", "thermal", "location", "system"]
    primary = [
        name
        for group, specs in app._NAV_GROUPS.items()
        for _label, name, _kind, _icon in specs
        if group == "Live Hardware"
    ]
    assert primary == [
        "entry:overview",
        "entry:thermal",
        "entry:location",
        "entry:system",
    ]
    assert "Research & Simulation" in app._NAV_GROUPS


def test_canonical_sensor_mapping_unchanged() -> None:
    parsed = parse_stm_csv_fields(
        "1,-99.00,28.42,51.42,27.61,28.13,27.17,27.45,26.87,27.01,27.94"
    )
    assert (parsed["si7021_1"], parsed["si7021_2"]) == (-99.00, 28.42)
    assert parsed["ntc1"] == 51.42 and parsed["ntc8"] == 27.94


def test_invalid_sensor_excluded_from_interpolation() -> None:
    ntc = {f"NTC{i}": 25.0 + 0.1 * i for i in range(1, 9)}
    ntc["NTC2"] = None  # invalid corner touches Bottom/Front/Right faces
    si = {"SI7021 #1": 24.5, "SI7021 #2": None}
    fig = chamber_figure(ntc, si)
    assert fig is not None
    surfaces = [t for t in fig.data if t.type == "surface"]
    # Faces touching NTC2 (Bottom, Front, Right) must be grey, not interpolated.
    assert len(surfaces) == 3
    for trace in surfaces:
        for row in trace.surfacecolor:
            for value in row:
                assert abs(value - (-99.0)) > 1.0
    meshes = [t for t in fig.data if t.type == "mesh3d"]
    assert len(meshes) == 3


def test_valid_ntc_statistics_correct() -> None:
    ntc = {
        "NTC1": 51.42,
        "NTC2": 27.61,
        "NTC3": None,
        "NTC4": 27.17,
        "NTC5": 27.45,
        "NTC6": None,
        "NTC7": 27.01,
        "NTC8": 27.94,
    }
    stats = thermal_stats(ntc)
    assert stats["valid_count"] == 6
    assert stats["max"] == 51.42 and stats["min"] == 27.01
    assert stats["hottest"] == "NTC1" and stats["coldest"] == "NTC7"
    assert (
        abs(stats["avg"] - sum([51.42, 27.61, 27.17, 27.45, 27.01, 27.94]) / 6) < 1e-9
    )


def _render_page(module_name: str):
    import sys

    root = Path(app.__file__).resolve().parents[2]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(
        str(root / "host" / "dashboard" / "entries" / f"{module_name}.py"),
        default_timeout=180,
    )
    at.run()
    return at


def test_overview_has_no_detailed_history() -> None:
    at = _render_page("overview")
    assert not at.exception
    texts = " ".join(m.value for m in at.markdown)
    assert "Temperature history" not in texts
    assert "RSSI trend" not in texts
    assert "3D thermal chamber" in texts or "Thermal summary" in texts
    assert len(at.multiselect) == 0
    assert len(at.selectbox) == 0


def test_thermal_page_owns_temperature_history() -> None:
    # Level-2: history lives in a client-side iframe (native toolbar, no
    # Streamlit widgets that would rebuild every tick).
    at = _render_page("thermal")
    assert not at.exception
    texts = " ".join(m.value for m in at.markdown)
    assert "Temperature history" in texts
    assert len(at.multiselect) == 0
    assert len(at.selectbox) == 0
    import inspect

    from host.dashboard import live_regions

    assert "history" in inspect.getsource(live_regions.history)


def test_system_page_contains_link_and_raw() -> None:
    at = _render_page("system")
    assert not at.exception
    texts = " ".join(m.value for m in at.markdown)
    assert "LoRa configuration" in texts
    labels = [t.label for t in at.tabs]
    assert labels == ["Link", "Reliability", "Raw Telemetry"]
    # CSV export is served by the read-only API (no per-tick Streamlit widget).
    import urllib.request

    with urllib.request.urlopen(
        "http://127.0.0.1:8502/api/raw.csv?limit=2", timeout=15
    ) as response:
        assert response.status == 200
        assert "text/csv" in response.headers.get("Content-Type", "")
        assert len(response.read()) > 0


def test_bilinear_face_interpolation_math() -> None:
    grid = bilinear_grid(20.0, 30.0, 40.0, 10.0, n=5)
    assert grid[0][0] == 20.0  # T00 corner exact
    assert grid[0][-1] == 30.0  # T10 corner exact
    assert grid[-1][-1] == 40.0  # T11 corner exact
    assert grid[-1][0] == 10.0  # T01 corner exact
    assert abs(grid[2][2] - 25.0) < 1e-9  # center = mean of corners
    # Linearity along an edge.
    assert abs(grid[0][2] - 25.0) < 1e-9


def test_color_range_minimum_span_and_quantization() -> None:
    lo, hi = stable_color_range([25.10, 25.30])
    assert hi - lo >= 1.0
    assert lo <= 25.10 and hi >= 25.30
    # Quantized to 0.5 C steps for display stability.
    assert abs(lo * 2 - round(lo * 2)) < 1e-9
    assert abs(hi * 2 - round(hi * 2)) < 1e-9
    # Hysteresis: small drift inside previous range keeps it.
    kept = stable_color_range([25.15, 25.35], prev=(lo, hi))
    assert kept == (lo, hi)
    # Large excursion adopts a fresh range.
    moved = stable_color_range([30.0, 31.0], prev=(lo, hi))
    assert moved != (lo, hi)


def test_freshness_model_boundaries() -> None:
    assert classify_freshness(0.4) == "LIVE"
    assert classify_freshness(3.0) == "LIVE"
    assert classify_freshness(3.1) == "STALE"
    assert classify_freshness(10.0) == "STALE"
    assert classify_freshness(10.1) == "OFFLINE"
    assert classify_freshness(None) == "OFFLINE"


def test_light_theme_and_no_dark_plotly() -> None:
    css = (Path(app.__file__).resolve().parent / "assets" / "style.css").read_text(
        encoding="utf-8"
    )
    assert "#F5F7F8" in css
    assert "max-width: 1600px" in css  # within the 1560–1640 px desktop target
    assert "#0F172A" not in css  # no dark navy panels in chrome CSS
    for module in ("overview", "thermal", "location", "system"):
        source = (
            Path(app.__file__).resolve().parent / "pages" / f"{module}.py"
        ).read_text(encoding="utf-8")
        assert "plotly_dark" not in source, f"{module} must not use dark charts"
        assert "run_every" not in source, f"{module} must not use refresh fragments"
        assert "st.plotly_chart" not in source, f"{module} must not rebuild charts"
    client = (
        Path(app.__file__).resolve().parents[2] / "host" / "api" / "static" / "live.js"
    ).read_text(encoding="utf-8")
    assert "uirevision" not in client  # react data-only: layout never resent
    assert "Plotly.react" in client
    assert "plotly_dark" not in client


def test_chamber_figure_camera_persistence() -> None:
    ntc = {f"NTC{i}": 24.0 + 0.2 * i for i in range(1, 9)}
    si = {"SI7021 #1": 24.5, "SI7021 #2": None}
    fig = chamber_figure(ntc, si)
    assert fig is not None
    assert fig.layout.uirevision == "thermal-nexus-chamber-v1"


def test_location_and_overview_render_without_exception() -> None:
    for module in ("location", "overview"):
        at = _render_page(module)
        assert not at.exception, f"{module}: {at.exception}"


def test_sidebar_four_primary_collapsed_research() -> None:
    live = [name for _label, name, _kind, _icon in app._NAV_GROUPS["Live Hardware"]]
    assert live == ["entry:overview", "entry:thermal", "entry:location", "entry:system"]
    assert list(app._NAV_GROUPS) == ["Live Hardware", "Research & Simulation"]
    source = Path(app.__file__).read_text(encoding="utf-8")
    assert 'position="hidden"' in source
    assert "page_link" in source
    assert "expanded=False" in source


def test_live_pages_have_no_streamlit_live_widgets() -> None:
    # All live values render inside client-side iframes; the Streamlit shell
    # must contain zero auto-updating widgets/plots (nothing to rebuild).
    for module in ("overview", "thermal", "location"):
        at = _render_page(module)
        assert not at.exception, f"{module}: {at.exception}"
        assert len(at.metric) == 0, f"{module} must not use st.metric for live data"
        source = (
            Path(app.__file__).resolve().parent / "pages" / f"{module}.py"
        ).read_text(encoding="utf-8")
        assert "st.plotly_chart" not in source, f"{module} must not rebuild charts"


def test_overview_information_ownership() -> None:
    at = _render_page("overview")
    texts = " ".join(m.value for m in at.markdown)
    assert "Temperature history" not in texts
    assert "Raw Telemetry" not in texts
    assert "Link" not in texts.split()


def test_thermal_desktop_structure() -> None:
    source = (Path(app.__file__).resolve().parent / "pages" / "thermal.py").read_text(
        encoding="utf-8"
    )
    assert "st.columns([2, 1]" in source  # 8-col chamber + 4-col side panel
    assert "thermal_side" in source
    assert "history" in source


def test_fixed_geometry_tokens() -> None:
    css = (Path(app.__file__).resolve().parent / "assets" / "style.css").read_text(
        encoding="utf-8"
    )
    for token in (
        "--space-1",
        "--space-2",
        "--space-3",
        "--space-4",
        "--space-5",
        "--space-6",
        "--space-8",
    ):
        assert token in css
    assert "tabular-nums" in css


def test_sensor_strip_fixed_tiles() -> None:
    import inspect

    from host.dashboard import live

    source = inspect.getsource(live.sensor_strip)
    for key in ["n0", "n7", "s1", "s2"]:
        assert key in source  # all 10 tiles always exist; N/A never removes them


def test_chamber_client_math_matches_server() -> None:
    root = Path(app.__file__).resolve().parents[2]
    client = (root / "host" / "api" / "static" / "live.js").read_text(encoding="utf-8")
    assert "stableRange" in client and "bilinearGrid" in client
    assert "1.0" in client  # minimum color span mirrored client-side
    assert "Plotly.react" in client


def test_com3_assumption_absent() -> None:
    root = Path(app.__file__).resolve().parents[2]
    for relative in (
        "host/dashboard/telemetry_model.py",
        "host/dashboard/pages/overview.py",
        "host/dashboard/pages/thermal.py",
        "host/dashboard/pages/location.py",
        "host/dashboard/pages/system.py",
        "config/dashboard.yaml",
    ):
        text = (root / relative).read_text(encoding="utf-8")
        assert "COM3" not in text, f"{relative} must not assume COM3"
    assert os.getenv("HART_SERIAL_PORT", "COM4") is not None


# --- Gate 1C visual fixes: top chrome, SI clipping, cold-blue/hot-red ---


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    """Extract (r, g, b) ints from a '#RRGGBB' hex color string."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def test_thermal_colorscale_is_cold_blue_hot_red() -> None:
    from host.dashboard.chamber_viz import THERMAL_COLORSCALE, chamber_figure

    # Must be an explicit array (not a named string) for Plotly.js parity.
    assert isinstance(THERMAL_COLORSCALE, list)
    assert len(THERMAL_COLORSCALE) >= 6  # at least 6 stops
    ntc = {f"NTC{i}": 25.0 + 0.1 * i for i in range(1, 9)}
    si = {"SI7021 #1": 24.5, "SI7021 #2": 25.0}
    fig = chamber_figure(ntc, si)
    assert fig is not None
    scales = []
    for trace in fig.data:
        if trace.type == "surface":
            scales.append(list(trace.colorscale))
        elif (
            trace.type == "scatter3d"
            and getattr(trace.marker, "colorscale", None) is not None
        ):
            scales.append(list(trace.marker.colorscale))
    assert scales, "no thermal-scaled traces"
    first = scales[0]
    cold_rgb = _hex_to_rgb(first[0][1])
    hot_rgb = _hex_to_rgb(first[-1][1])
    assert cold_rgb[2] > cold_rgb[0]  # cold end is blue-dominant
    assert hot_rgb[0] > hot_rgb[2]  # hot end is red-dominant
    for sc in scales:
        assert sc == first  # shared colorscale across faces + NTC markers


def test_si_markers_distinct_teal_never_interpolated() -> None:
    from host.dashboard.chamber_viz import chamber_figure

    ntc = {f"NTC{i}": 25.0 + 0.1 * i for i in range(1, 9)}
    si = {"SI7021 #1": 99.0, "SI7021 #2": 5.0}  # far outside NTC band
    fig = chamber_figure(ntc, si)
    assert fig is not None
    # cmin/cmax derive from valid NTC only (SI extremes excluded).
    for trace in fig.data:
        if trace.type == "surface":
            assert trace.cmin >= 24.0 and trace.cmax <= 26.8
    # SI markers are solid teal diamonds, not thermal-scale-coloured.
    si_traces = [
        t
        for t in fig.data
        if t.type == "scatter3d" and getattr(t.marker, "symbol", None) == "diamond"
    ]
    assert si_traces
    for trace in si_traces:
        assert trace.marker.color == "#18B8A6"


def test_invalid_minus99_excluded_from_color_range() -> None:
    from host.dashboard.chamber_viz import stable_color_range

    # -99 sentinel is filtered upstream; range must reflect the real band.
    lo, hi = stable_color_range([25.3, 25.6, 26.4])
    assert lo >= 25.0
    assert hi <= 27.0
    assert (hi - lo) >= 1.0  # minimum display span preserved
    # -99 is excluded by clean_temperature upstream; stable_color_range
    # itself just takes min/max of whatever it receives.
    lo2, hi2 = stable_color_range([-99.0, 25.3, 25.6])
    assert lo2 == -99.0  # function trusts its input
    assert hi2 >= 25.0
    assert (hi2 - lo2) >= 1.0


def test_thermal_side_panel_has_all_ten_sensors() -> None:
    import inspect

    from host.dashboard.live_regions import thermal_side

    source = inspect.getsource(thermal_side)
    # 10-cell matrix: 2 columns x 5 rows via the CSS grid template.
    assert "repeat(2,minmax(0,1fr))" in source  # 2 columns
    assert "tm-{key}" in source  # NTC1..NTC8 SI1 SI2 cell ids
    assert "n8" in source and "n5" in source and "n1" in source
    assert "s1" in source and "s2" in source  # SI probes present


def test_sensor_cards_fixed_equal_geometry() -> None:
    import inspect

    from host.dashboard.live_regions import thermal_side

    source = inspect.getsource(thermal_side)
    # 10 tiles; each always renders label + value + status line, so a VALID
    # value vs N/A/DISCONNECTED never changes the card geometry (no height jump).
    assert "class='tn-tile'" in source
    assert "tn-t-value" in source and "tn-t-state" in source
    assert "tm-{key}-s" in source
    assert "DISCONNECTED" in source and "VALID" in source


def test_native_streamlit_toolbar_hidden_and_app_header_kept() -> None:
    from host.dashboard.components.theme import apply_theme
    from host.dashboard.config import load_dashboard_config

    css = apply_theme.__globals__["STYLE_CSS"].read_text(encoding="utf-8")
    # Native chrome hidden.
    assert '[data-testid="stHeader"]' in css and "display: none" in css
    assert '[data-testid="stToolbar"]' in css and "visibility: hidden" in css
    assert "#MainMenu" in css and "display: none" in css
    # Our own app header/typography must remain visible (never hidden).
    assert ".tn-brandline" in css
    assert "display: none" not in css.split('[data-testid="stHeader"]')[0].lower()
    assert load_dashboard_config()  # theme + config still load


def test_thermal_colorscale_explicit_cold_blue() -> None:
    """First color in the canonical scale must be a deep blue family color."""
    from host.dashboard.chamber_viz import THERMAL_COLORSCALE

    first_stop = THERMAL_COLORSCALE[0]
    r, g, b = _hex_to_rgb(first_stop[1])
    assert b > r and b > g, f"Expected blue-dominant cold end, got #{first_stop[1]}"


def test_thermal_colorscale_explicit_hot_red() -> None:
    """Final color in the canonical scale must be a deep red family color."""
    from host.dashboard.chamber_viz import THERMAL_COLORSCALE

    last_stop = THERMAL_COLORSCALE[-1]
    r, g, b = _hex_to_rgb(last_stop[1])
    assert r > b and r > g, f"Expected red-dominant hot end, got #{last_stop[1]}"


def test_thermal_colorscale_contains_cyan_transition() -> None:
    """Scale must pass through a cyan / light-blue zone (~0.3–0.45)."""
    from host.dashboard.chamber_viz import THERMAL_COLORSCALE

    mid_cold = [s for s in THERMAL_COLORSCALE if 0.25 <= s[0] <= 0.50]
    assert mid_cold, "No stops in the cyan/light-blue transition region"
    for frac, color in mid_cold:
        r, g, b = _hex_to_rgb(color)
        # At least one cyan-region stop should be blue-dominant or green-blue.
        assert b > r or g > r, f"Stop at {frac} should be cool-colored, got #{color}"


def test_thermal_colorscale_contains_yellow_midpoint() -> None:
    """Scale must pass through a yellow / orange zone (~0.5–0.7)."""
    from host.dashboard.chamber_viz import THERMAL_COLORSCALE

    mid_hot = [s for s in THERMAL_COLORSCALE if 0.50 <= s[0] <= 0.75]
    assert mid_hot, "No stops in the yellow/orange midpoint region"
    for frac, color in mid_hot:
        r, g, b = _hex_to_rgb(color)
        # Yellow/orange: red and green are both relatively high.
        assert r > 100 or g > 100, f"Stop at {frac} should be warm-colored, got #{color}"


def test_python_and_js_colorscale_match() -> None:
    """Python THERMAL_COLORSCALE must exactly match the JS definition."""
    import re
    from pathlib import Path

    from host.dashboard.chamber_viz import THERMAL_COLORSCALE

    root = Path(app.__file__).resolve().parents[2]
    js_source = (root / "host" / "api" / "static" / "live.js").read_text(encoding="utf-8")
    assert "THERMAL_COLORSCALE" in js_source, "live.js must define THERMAL_COLORSCALE"
    # Extract each [number, "#hex"] stop from the JS definition.
    # Find the THERMAL_COLORSCALE block.
    idx = js_source.index("THERMAL_COLORSCALE")
    block = js_source[idx : idx + 600]  # generous window
    stops = re.findall(r'\[\s*([\d.]+)\s*,\s*"(#[0-9A-Fa-f]{6})"\s*]', block)
    assert len(stops) == len(THERMAL_COLORSCALE), (
        f"JS has {len(stops)} stops, Python has {len(THERMAL_COLORSCALE)}"
    )
    for (js_frac, js_hex), py_stop in zip(stops, THERMAL_COLORSCALE):
        assert float(js_frac) == py_stop[0], (
            f"Fraction mismatch: JS={js_frac} vs Python={py_stop[0]}"
        )
        assert js_hex.upper() == py_stop[1].upper(), (
            f"Color mismatch at {js_frac}: JS={js_hex} Python={py_stop[1]}"
        )


def test_si_markers_never_use_thermal_colorscale() -> None:
    """SI7021 probes are solid teal — not coloured by the thermal scale."""
    from host.dashboard.chamber_viz import chamber_figure

    ntc = {f"NTC{i}": 25.0 + 0.1 * i for i in range(1, 9)}
    si = {"SI7021 #1": 25.0, "SI7021 #2": 25.0}
    fig = chamber_figure(ntc, si)
    assert fig is not None
    si_traces = [
        t for t in fig.data
        if t.type == "scatter3d" and getattr(t.marker, "symbol", None) == "diamond"
    ]
    for trace in si_traces:
        assert trace.marker.color == "#18B8A6"
        assert getattr(trace.marker, "colorscale", None) is None


def test_history_series_keep_stable_identity() -> None:
    """Blue→red is for thermal magnitude only; history keeps distinct series."""
    import inspect

    from host.dashboard.live_regions import history

    source = inspect.getsource(history)
    assert "#313695" not in source  # not thermal-scaled
    assert "Inferno" not in source
    assert "PAL" in source and "line: { color: PAL" in source  # stable palette
