/* THERMAL NEXUS live client library (served by the read-only telemetry API).
 * In-place updates only: textContent / classList / Plotly.react.
 * Never rebuilds containers, never touches layout/camera after init.
 */
(function () {
  "use strict";
  const API = "http://127.0.0.1:8502";

  const NTC_POS = {
    NTC1: [0, 0, 0], NTC2: [100, 0, 0], NTC3: [100, 100, 0], NTC4: [0, 100, 0],
    NTC5: [0, 0, 100], NTC6: [100, 0, 100], NTC7: [100, 100, 100], NTC8: [0, 100, 100],
  };
  const SI_POS = { SI1: [50, 50, 100], SI2: [50, 50, 0] };
  const CORNER_NAMES = {
    NTC1: "Bottom/Front/Left", NTC2: "Bottom/Front/Right",
    NTC3: "Bottom/Back/Right", NTC4: "Bottom/Back/Left",
    NTC5: "Top/Front/Left", NTC6: "Top/Front/Right",
    NTC7: "Top/Back/Right", NTC8: "Top/Back/Left",
  };
  const FACES = [
    ["Bottom", ["NTC1", "NTC2", "NTC3", "NTC4"]],
    ["Top", ["NTC5", "NTC6", "NTC7", "NTC8"]],
    ["Front", ["NTC1", "NTC2", "NTC6", "NTC5"]],
    ["Back", ["NTC3", "NTC4", "NTC8", "NTC7"]],
    ["Left", ["NTC1", "NTC4", "NTC8", "NTC5"]],
    ["Right", ["NTC2", "NTC3", "NTC7", "NTC6"]],
  ];
  const SHORT = { NTC1: "N1", NTC2: "N2", NTC3: "N3", NTC4: "N4",
                  NTC5: "N5", NTC6: "N6", NTC7: "N7", NTC8: "N8" };
  const GRID_N = 10;
  const THERMAL_COLORSCALE = [
    [0.00, "#313695"],   // deep blue — coldest
    [0.15, "#4575B4"],   // blue
    [0.30, "#74ADD1"],   // light blue
    [0.42, "#ABD9E9"],   // cyan / light cyan
    [0.55, "#FFFFBF"],   // yellow
    [0.70, "#FDAE61"],   // orange
    [0.82, "#F46D43"],   // orange-red
    [0.92, "#D73027"],   // red
    [1.00, "#A50026"],   // deep red — hottest
  ];

  function isValid(v) {
    return typeof v === "number" && isFinite(v) && Math.abs(v - -99.0) > 0.05;
  }

  async function get(path) {
    const res = await fetch(API + path, { cache: "no-store" });
    if (!res.ok) throw new Error("API " + res.status);
    return res.json();
  }

  function poll(path, ms, fn) {
    let stopped = false;
    async function tick() {
      if (stopped) return;
      try { fn(await get(path)); } catch (e) { /* keep polling */ }
    }
    tick();
    const id = setInterval(tick, ms);
    return () => { stopped = true; clearInterval(id); };
  }

  function fmtTemp(v, decimals) {
    if (!isValid(v)) return "N/A";
    return v.toFixed(decimals === undefined ? 1 : decimals) + " °C";
  }

  function setText(id, text) {
    const el = document.getElementById(id);
    if (el && el.textContent !== text) el.textContent = text;
  }

  function bilinearGrid(t00, t10, t11, t01, n) {
    n = n || GRID_N;
    const grid = [];
    for (let j = 0; j < n; j++) {
      const v = j / (n - 1), row = [];
      for (let i = 0; i < n; i++) {
        const u = i / (n - 1);
        row.push((1 - u) * (1 - v) * t00 + u * (1 - v) * t10 +
                 u * v * t11 + (1 - u) * v * t01);
      }
      grid.push(row);
    }
    return grid;
  }

  function posGrid(corners, n) {
    n = n || GRID_N;
    const pts = corners.map((c) => NTC_POS[c]);
    const xs = [], ys = [], zs = [];
    for (let j = 0; j < n; j++) {
      const v = j / (n - 1), xr = [], yr = [], zr = [];
      for (let i = 0; i < n; i++) {
        const u = i / (n - 1);
        const w = [(1 - u) * (1 - v), u * (1 - v), u * v, (1 - u) * v];
        xr.push(w[0] * pts[0][0] + w[1] * pts[1][0] + w[2] * pts[2][0] + w[3] * pts[3][0]);
        yr.push(w[0] * pts[0][1] + w[1] * pts[1][1] + w[2] * pts[2][1] + w[3] * pts[3][1]);
        zr.push(w[0] * pts[0][2] + w[1] * pts[1][2] + w[2] * pts[2][2] + w[3] * pts[3][2]);
      }
      xs.push(xr); ys.push(yr); zs.push(zr);
    }
    return [xs, ys, zs];
  }

  function stableRange(vals, prev) {
    if (!vals.length) return [0, 1];
    let lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    if (hi - lo < 1.0) { const mid = (hi + lo) / 2; lo = mid - 0.5; hi = mid + 0.5; }
    lo = Math.floor(lo * 2) / 2; hi = Math.ceil(hi * 2) / 2;
    if (prev && lo >= prev[0] - 0.25 && hi <= prev[1] + 0.25) return prev;
    return [lo, hi];
  }

  /* Build chamber traces (data only). Layout is set once at init and never
   * touched again, so user camera/map state always survives updates. */
  function chamberTraces(ntc, si, range) {
    const cmin = range[0], cmax = range[1];
    const traces = [];
    let firstSurface = true;
    FACES.forEach(([faceName, corners]) => {
      const temps = corners.map((c) => ntc[c]);
      const [xs, ys, zs] = posGrid(corners);
      if (temps.some((t) => !isValid(t))) {
        traces.push({
          type: "mesh3d",
          x: [xs[0][0], xs[0][GRID_N - 1], xs[GRID_N - 1][GRID_N - 1], xs[GRID_N - 1][0]],
          y: [ys[0][0], ys[0][GRID_N - 1], ys[GRID_N - 1][GRID_N - 1], ys[GRID_N - 1][0]],
          z: [zs[0][0], zs[0][GRID_N - 1], zs[GRID_N - 1][GRID_N - 1], zs[GRID_N - 1][0]],
          i: [0, 0], j: [1, 2], k: [2, 3],
          color: "#9AA5B1", opacity: 0.35, flatshading: true,
          hovertemplate: faceName + " face<br>INVALID corner — no interpolation<extra></extra>",
          showlegend: false,
        });
        return;
      }
      const tg = bilinearGrid(temps[0], temps[1], temps[2], temps[3]);
      traces.push({
        type: "surface", x: xs, y: ys, z: zs, surfacecolor: tg,
        colorscale: THERMAL_COLORSCALE, cmin, cmax, showscale: firstSurface,
        colorbar: firstSurface ? { title: "°C", thickness: 14, len: 0.65 } : undefined,
        hovertemplate: "%{hovertext}<extra></extra>",
        hovertext: tg.map((row, j) => row.map((t, i) =>
          faceName + " face<br>" + t.toFixed(1) + " °C<br>Interpolated")),
        lighting: { ambient: 0.9, diffuse: 0.4, specular: 0.1 },
        contours: { x: { highlight: false }, y: { highlight: false }, z: { highlight: false } },
        showlegend: false,
      });
      firstSurface = false;
    });

    const edgePairs = [["NTC1","NTC2"],["NTC2","NTC3"],["NTC3","NTC4"],["NTC4","NTC1"],
      ["NTC5","NTC6"],["NTC6","NTC7"],["NTC7","NTC8"],["NTC8","NTC5"],
      ["NTC1","NTC5"],["NTC2","NTC6"],["NTC3","NTC7"],["NTC4","NTC8"]];
    edgePairs.forEach(([a, b]) => {
      traces.push({ type: "scatter3d", mode: "lines",
        x: [NTC_POS[a][0], NTC_POS[b][0]], y: [NTC_POS[a][1], NTC_POS[b][1]],
        z: [NTC_POS[a][2], NTC_POS[b][2]],
        line: { color: "rgba(230,237,242,0.55)", width: 2 },
        showlegend: false, hoverinfo: "skip" });
    });

    const validLabels = Object.keys(ntc).filter((l) => isValid(ntc[l]));
    if (validLabels.length) {
      traces.push({ type: "scatter3d", mode: "markers+text",
        x: validLabels.map((l) => NTC_POS[l][0]),
        y: validLabels.map((l) => NTC_POS[l][1]),
        z: validLabels.map((l) => NTC_POS[l][2]),
        marker: { size: 6, color: validLabels.map((l) => ntc[l]),
          colorscale: THERMAL_COLORSCALE, cmin, cmax, showscale: false,
          line: { color: "white", width: 1.5 } },
        text: validLabels.map((l) => SHORT[l]), textposition: "top center",
        textfont: { size: 10, color: "#E8EEF3" },
        hovertemplate: validLabels.map((l) =>
          "<b>" + l + "</b><br>" + ntc[l].toFixed(1) + " °C<br>Corner: " +
          CORNER_NAMES[l] + "<br>VALID<extra></extra>"),
        name: "NTC corners" });
    }
    const invalidLabels = Object.keys(ntc).filter((l) => !isValid(ntc[l]));
    if (invalidLabels.length) {
      traces.push({ type: "scatter3d", mode: "markers+text",
        x: invalidLabels.map((l) => NTC_POS[l][0]),
        y: invalidLabels.map((l) => NTC_POS[l][1]),
        z: invalidLabels.map((l) => NTC_POS[l][2]),
        marker: { size: 6, color: "#8A97A3", symbol: "x",
          line: { color: "white", width: 1.5 } },
        text: invalidLabels.map((l) => SHORT[l]), textposition: "top center",
        textfont: { size: 10, color: "#C7D0D9" },
        hovertemplate: invalidLabels.map((l) =>
          "<b>" + l + "</b><br>N/A<br>Corner: " + CORNER_NAMES[l] + "<br>INVALID<extra></extra>"),
        name: "NTC invalid" });
    }
    const siLabels = Object.keys(si);
    traces.push({ type: "scatter3d", mode: "markers+text",
      x: siLabels.map((l) => SI_POS[l][0]),
      y: siLabels.map((l) => SI_POS[l][1]),
      z: siLabels.map((l) => SI_POS[l][2]),
      marker: { size: 9, symbol: "diamond",
        color: "#18B8A6",
        line: { color: "#0E7C7B", width: 2 } },
      text: siLabels.map((l) => (l === "SI1" ? "S1" : "S2")),
      textposition: "top center", textfont: { size: 10, color: "#0E7C7B" },
      hovertemplate: siLabels.map((l) =>
        "<b>SI7021 #" + (l === "SI1" ? "1" : "2") + "</b><br>" +
        (isValid(si[l]) ? si[l].toFixed(2) + " °C" : "N/A") +
        "<br>Reference probe (not interpolated)<br>" +
        (isValid(si[l]) ? "CONNECTED" : "DISCONNECTED") + "<extra></extra>"),
      name: "SI7021 probes" });
    return traces;
  }

  function chamberLayout(height) {
    const axis = (title) => ({ title, range: [-8, 108], showticklabels: false,
      backgroundcolor: "#33404E", gridcolor: "#45576A", zerolinecolor: "#45576A" });
    return {
      scene: { xaxis: axis("X (mm)"), yaxis: axis("Y (mm)"), zaxis: axis("Z (mm)"),
        aspectmode: "cube", bgcolor: "#33404E",
        camera: { eye: { x: 1.45, y: 1.45, z: 1.1 } } },
      height: height || 540, margin: { l: 0, r: 0, t: 8, b: 0 },
      paper_bgcolor: "rgba(0,0,0,0)",
      legend: { font: { color: "#42505C" }, orientation: "h", y: -0.02 },
      template: "plotly_white",
    };
  }

  window.TN = { API, get, poll, isValid, fmtTemp, setText, bilinearGrid,
                stableRange, chamberTraces, chamberLayout, NTC_POS, SI_POS,
                THERMAL_COLORSCALE, BUILD_ID: "thermal-color-v3" };
})();
