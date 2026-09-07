"""3D thermal-chamber figure with true face-interpolated gradient.

The 8 corner NTCs define the thermal field. Every cube face with four valid
corner temperatures is rendered as a ``go.Surface`` over a bilinear
interpolation grid (10x10), sharing one ``cmin``/``cmax``/cold-blue→hot-red
scale for the whole chamber. Faces touching an invalid (-99) corner render
neutral grey — never interpolated fake data. SI7021 probes are independent
teleal diamonds and never influence interpolation.

The colorscale is an *explicit* array of [fraction, hex] stops rather than a
named Plotly colorscale, so Python and browser-side Plotly.js render the
identical gradient without any name-resolution ambiguity.

Display values are smoothed only in the colour *range* (hysteresis);
stored telemetry is never altered.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

import logging as _logging
import os as _os
import time as _time

from host.dashboard.telemetry_model import (
    NTC_POSITIONS_MM,
    SI_POSITIONS_MM,
    clean_temperature,
)

_RENDER_LOGGER = _logging.getLogger("thermal-nexus.render")

THERMAL_COLORSCALE: list[list] = [
    [0.00, "#313695"],   # deep blue — coldest
    [0.15, "#4575B4"],   # blue
    [0.30, "#74ADD1"],   # light blue
    [0.42, "#ABD9E9"],   # cyan / light cyan
    [0.55, "#FFFFBF"],   # yellow
    [0.70, "#FDAE61"],   # orange
    [0.82, "#F46D43"],   # orange-red
    [0.92, "#D73027"],   # red
    [1.00, "#A50026"],   # deep red — hottest
]
GRID_N = 10
MIN_SPAN_C = 1.0
_RANGE_STEP = 0.5
_HYSTERESIS_C = 0.25
UIREVISION_CHAMBER = "thermal-nexus-chamber-v1"

# Corner names for hover detail (x: Left/Right, y: Front/Back, z: Bottom/Top).
CORNER_NAMES: dict[str, str] = {
    "NTC1": "Bottom/Front/Left",
    "NTC2": "Bottom/Front/Right",
    "NTC3": "Bottom/Back/Right",
    "NTC4": "Bottom/Back/Left",
    "NTC5": "Top/Front/Left",
    "NTC6": "Top/Front/Right",
    "NTC7": "Top/Back/Right",
    "NTC8": "Top/Back/Left",
}

# Faces as [c00, c10, c11, c01] for bilinear T(u,v).
FACES: list[tuple[str, list[str]]] = [
    ("Bottom", ["NTC1", "NTC2", "NTC3", "NTC4"]),
    ("Top", ["NTC5", "NTC6", "NTC7", "NTC8"]),
    ("Front", ["NTC1", "NTC2", "NTC6", "NTC5"]),
    ("Back", ["NTC3", "NTC4", "NTC8", "NTC7"]),
    ("Left", ["NTC1", "NTC4", "NTC8", "NTC5"]),
    ("Right", ["NTC2", "NTC3", "NTC7", "NTC6"]),
]

_SHORT = {f"NTC{i}": f"N{i}" for i in range(1, 9)}


# ---------------------------------------------------------------------------
# Pure math helpers (unit-tested)
# ---------------------------------------------------------------------------

def bilinear_grid(
    t00: float, t10: float, t11: float, t01: float, n: int = GRID_N,
) -> list[list[float]]:
    """Bilinear interpolation grid over one face.

    T(u,v) = (1-u)(1-v)T00 + u(1-v)T10 + uvT11 + (1-u)vT01.
    """
    grid: list[list[float]] = []
    for j in range(n):
        v = j / (n - 1)
        row: list[float] = []
        for i in range(n):
            u = i / (n - 1)
            row.append(
                (1 - u) * (1 - v) * t00
                + u * (1 - v) * t10
                + u * v * t11
                + (1 - u) * v * t01
            )
        grid.append(row)
    return grid


def _expand_and_quantize(lo: float, hi: float) -> tuple[float, float]:
    """Enforce minimum span and quantize to 0.5 C steps (display stability)."""
    if hi - lo < MIN_SPAN_C:
        mid = (hi + lo) / 2.0
        lo, hi = mid - MIN_SPAN_C / 2.0, mid + MIN_SPAN_C / 2.0
    import math as _math

    return (_math.floor(lo / _RANGE_STEP) * _RANGE_STEP,
            _math.ceil(hi / _RANGE_STEP) * _RANGE_STEP)


def stable_color_range(
    temps: list[float], prev: tuple[float, float] | None = None
) -> tuple[float, float]:
    """Shared (cmin, cmax) over VALID temps with display-only hysteresis.

    Small fluctuations must not recolour the chamber every second: when the
    fresh range sits inside the previous range (plus a small margin), the
    previous range is kept.
    """
    if not temps:
        return (0.0, 1.0)
    fresh = _expand_and_quantize(min(temps), max(temps))
    if prev is None:
        return fresh
    plo, phi = prev
    if fresh[0] >= plo - _HYSTERESIS_C and fresh[1] <= phi + _HYSTERESIS_C:
        return (plo, phi)
    return fresh


def face_position_grid(
    corners: list[str], n: int = GRID_N
) -> tuple[list[list[float]], list[list[float]], list[list[float]]]:
    """Bilinear 3D position grid for a face's four corner labels."""
    pts = [NTC_POSITIONS_MM[label] for label in corners]
    xs, ys, zs = [], [], []
    for j in range(n):
        v = j / (n - 1)
        xr, yr, zr = [], [], []
        for i in range(n):
            u = i / (n - 1)
            w = [(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v]
            xr.append(sum(w[k] * pts[k][0] for k in range(4)))
            yr.append(sum(w[k] * pts[k][1] for k in range(4)))
            zr.append(sum(w[k] * pts[k][2] for k in range(4)))
        xs.append(xr)
        ys.append(yr)
        zs.append(zr)
    return xs, ys, zs


# ---------------------------------------------------------------------------
# Figure
# ---------------------------------------------------------------------------

def chamber_figure(
    ntc: dict[str, float | None],
    si: dict[str, float | None],
    *,
    height: int = 480,
    color_range: tuple[float, float] | None = None,
    uirevision: str = UIREVISION_CHAMBER,
) -> go.Figure | None:
    """Build the interpolated-gradient chamber figure (None if all invalid)."""
    if _os.getenv("TN_RENDER_TRACE") == "1":
        _RENDER_LOGGER.info("[RENDER] chamber_figure build t=%.3f", _time.time())
    valid = {label: temp for label, temp in ntc.items() if temp is not None}
    valid_si = {label: temp for label, temp in si.items() if temp is not None}
    if not valid and not valid_si:
        return None

    scale_vals = list(valid.values()) or list(valid_si.values())
    cmin, cmax = (
        color_range if color_range is not None
        else stable_color_range([float(v) for v in scale_vals])
    )

    fig = go.Figure()
    first_surface = True

    for face_name, corners in FACES:
        temps = [ntc.get(label) for label in corners]
        xs, ys, zs = face_position_grid(corners)
        if any(temp is None for temp in temps):
            # Invalid corner: neutral translucent grey, markers retained.
            flat_x = [row[0] for row in xs]
            _ = flat_x
            fig.add_trace(go.Mesh3d(
                x=[xs[0][0], xs[0][-1], xs[-1][-1], xs[-1][0]],
                y=[ys[0][0], ys[0][-1], ys[-1][-1], ys[-1][0]],
                z=[zs[0][0], zs[0][-1], zs[-1][-1], zs[-1][0]],
                i=[0, 0], j=[1, 2], k=[2, 3],
                color="#9AA5B1", opacity=0.35, flatshading=True,
                hovertemplate=f"{face_name} face<br>INVALID corner — no interpolation<extra></extra>",
                name=f"{face_name} (invalid)", showlegend=False,
            ))
            continue
        t = [float(v) for v in temps]  # type: ignore[misc]
        tgrid = bilinear_grid(t[0], t[1], t[2], t[3])
        hover = [
            [f"{face_name} face<br>{tgrid[j][i]:.1f} &deg;C<br>Interpolated"
             for i in range(GRID_N)]
            for j in range(GRID_N)
        ]
        fig.add_trace(go.Surface(
            x=xs, y=ys, z=zs, surfacecolor=tgrid,
            colorscale=THERMAL_COLORSCALE, cmin=cmin, cmax=cmax,
            showscale=first_surface,
            colorbar={"title": "°C", "thickness": 14, "len": 0.65} if first_surface else None,
            hovertemplate="%{hovertext}<extra></extra>",
            hovertext=hover,
            lighting={"ambient": 0.9, "diffuse": 0.4, "specular": 0.1},
            contours={"x": {"highlight": False}, "y": {"highlight": False}, "z": {"highlight": False}},
            name=face_name, showlegend=False,
        ))
        first_surface = False

    # Chamber edges for geometric readability.
    edge_pairs = [
        ("NTC1", "NTC2"), ("NTC2", "NTC3"), ("NTC3", "NTC4"), ("NTC4", "NTC1"),
        ("NTC5", "NTC6"), ("NTC6", "NTC7"), ("NTC7", "NTC8"), ("NTC8", "NTC5"),
        ("NTC1", "NTC5"), ("NTC2", "NTC6"), ("NTC3", "NTC7"), ("NTC4", "NTC8"),
    ]
    for a, b in edge_pairs:
        pa, pb = NTC_POSITIONS_MM[a], NTC_POSITIONS_MM[b]
        fig.add_trace(go.Scatter3d(
            x=[pa[0], pb[0]], y=[pa[1], pb[1]], z=[pa[2], pb[2]],
            mode="lines", line={"color": "rgba(230,237,242,0.7)", "width": 3},
            showlegend=False, hoverinfo="skip",
        ))

    # Valid NTC corner markers (circles, full detail on hover).
    if valid:
        labels = list(valid)
        fig.add_trace(go.Scatter3d(
            x=[NTC_POSITIONS_MM[label][0] for label in labels],
            y=[NTC_POSITIONS_MM[label][1] for label in labels],
            z=[NTC_POSITIONS_MM[label][2] for label in labels],
            mode="markers+text",
            marker={
                "size": 6,
                "color": [valid[label] for label in labels],
                "colorscale": THERMAL_COLORSCALE, "cmin": cmin, "cmax": cmax,
                "showscale": False,
                "line": {"color": "white", "width": 1.5},
            },
            text=[_SHORT[label] for label in labels],
            textposition="top center",
            textfont={"size": 10, "color": "#E8EEF3"},
            hovertemplate=[
                f"<b>{label}</b><br>{valid[label]:.1f} &deg;C<br>"
                f"Corner: {CORNER_NAMES[label]}<br>VALID<extra></extra>"
                for label in labels
            ],
            name="NTC corners",
        ))

    # Invalid NTC markers (grey x).
    invalid = [label for label, temp in ntc.items() if temp is None]
    if invalid:
        fig.add_trace(go.Scatter3d(
            x=[NTC_POSITIONS_MM[label][0] for label in invalid],
            y=[NTC_POSITIONS_MM[label][1] for label in invalid],
            z=[NTC_POSITIONS_MM[label][2] for label in invalid],
            mode="markers+text",
            marker={"size": 6, "color": "#8A97A3", "symbol": "x",
                    "line": {"color": "white", "width": 1.5}},
            text=[_SHORT[label] for label in invalid],
            textposition="top center",
            textfont={"size": 10, "color": "#C7D0D9"},
            hovertemplate=[
                f"<b>{label}</b><br>N/A<br>Corner: {CORNER_NAMES[label]}"
                f"<br>INVALID<extra></extra>" for label in invalid
            ],
            name="NTC invalid",
        ))

    # SI7021 reference probes (diamonds, excluded from interpolation).
    si_items = list(si.items())
    if si_items:
        fig.add_trace(go.Scatter3d(
            x=[SI_POSITIONS_MM[label][0] for label, _ in si_items],
            y=[SI_POSITIONS_MM[label][1] for label, _ in si_items],
            z=[SI_POSITIONS_MM[label][2] for label, _ in si_items],
            mode="markers+text",
            marker={
                "size": 9, "symbol": "diamond",
                "color": "#18B8A6",
                "line": {"color": "#0E7C7B", "width": 2},
            },
            text=["S1" if label == "SI7021 #1" else "S2" for label, _ in si_items],
            textposition="top center",
            textfont={"size": 10, "color": "#0E7C7B"},
            hovertemplate=[
                f"<b>{label}</b><br>"
                f"{(f'{temp:.2f} &deg;C' if temp is not None else 'N/A')}<br>"
                f"Reference probe (not interpolated)<br>"
                f"{'CONNECTED' if temp is not None else 'DISCONNECTED'}<extra></extra>"
                for label, temp in si_items
            ],
            name="SI7021 probes",
        ))

    fig.update_layout(
        scene={
            "xaxis": {"title": "X (mm)", "range": [-8, 108], "showticklabels": False,
                      "backgroundcolor": "#232F3B", "gridcolor": "#35424F",
                      "zerolinecolor": "#35424F"},
            "yaxis": {"title": "Y (mm)", "range": [-8, 108], "showticklabels": False,
                      "backgroundcolor": "#232F3B", "gridcolor": "#35424F",
                      "zerolinecolor": "#35424F"},
            "zaxis": {"title": "Z (mm)", "range": [-8, 108], "showticklabels": False,
                      "backgroundcolor": "#232F3B", "gridcolor": "#35424F",
                      "zerolinecolor": "#35424F"},
            "aspectmode": "cube",
            "bgcolor": "#232F3B",
            "camera": {"eye": {"x": 1.45, "y": 1.45, "z": 1.1}},
        },
        height=height,
        margin={"l": 0, "r": 0, "t": 8, "b": 0},
        paper_bgcolor="rgba(0,0,0,0)",
        legend={"font": {"color": "#42505C"}, "orientation": "h", "y": -0.02},
        uirevision=uirevision,
        template="plotly_white",
    )
    return fig


def ntc_for_row(row: dict[str, Any]) -> tuple[dict[str, float | None], dict[str, float | None]]:
    """Split a telemetry_readings row into (ntc, si) dicts with validity."""
    ntc = {f"NTC{i}": clean_temperature(row.get(f"ntc{i}_temp")) for i in range(1, 9)}
    si = {
        "SI7021 #1": clean_temperature(row.get("digital_top_temp")),
        "SI7021 #2": clean_temperature(row.get("digital_bottom_temp")),
    }
    return ntc, si
