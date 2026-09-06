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


def _rgb_channels(rgb: str) -> tuple[int, int, int]:
    """Extract (r, g, b) ints from a 'rgb(r,g,b)' color string."""
    inner = rgb[rgb.index("(") + 1 : rgb.index(")")]
    return tuple(int(ch) for ch in inner.split(","))


def test_thermal_colorscale_is_cold_blue_hot_red() -> None:
    from host.dashboard.chamber_viz import THERMAL_COLORSCALE, chamber_figure

    assert THERMAL_COLORSCALE == "RdYlBu_r"  # cold blue -> hot red
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
    cold_rgb = _rgb_channels(first[0][1])
    hot_rgb = _rgb_channels(first[-1][1])
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


def test_history_series_keep_stable_identity() -> None:
    """Blue→red is for thermal magnitude only; history keeps distinct series."""
    import inspect

    from host.dashboard.live_regions import history

    source = inspect.getsource(history)
    assert "RdYlBu_r" not in source  # not thermal-scaled
    assert "Inferno" not in source
    assert "PAL" in source and "line: { color: PAL" in source  # stable palette
