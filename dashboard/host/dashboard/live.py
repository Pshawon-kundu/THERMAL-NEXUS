"""Level-2 live regions: self-contained iframe apps with client-side polling.

Each region is a static HTML document rendered ONCE by Streamlit via
``components.html``. Inside, JavaScript polls the read-only telemetry API
(127.0.0.1:8502) and updates the DOM in place (``textContent``/``classList``)
or calls ``Plotly.react`` with data-only traces. Streamlit NEVER reruns for
telemetry, so there is no card replacement, no chart remount, no camera
reset and no flash. Fixed iframe heights keep page geometry constant.
"""

from __future__ import annotations

import streamlit.components.v1 as components

API = "http://127.0.0.1:8502"

_CSS = """
:root{--sp1:4px;--sp2:8px;--sp3:12px;--sp4:16px;--sp5:20px;--sp6:24px;}
*{box-sizing:border-box;}
html,body{margin:0;padding:0;background:#FFFFFF;color:#13202B;
font-family:"Source Sans Pro",-apple-system,"Segoe UI",Roboto,sans-serif;font-size:13px;}
.tn-chip{display:inline-flex;align-items:center;gap:6px;border:1px solid #DDE4E8;
border-radius:999px;font-size:12.5px;font-weight:650;padding:3px 11px;white-space:nowrap;}
.tn-dot{border-radius:50%;display:inline-block;height:8px;width:8px;}
.tn-live{background:#E9F7EF;border-color:#BFE6CC;color:#157A3D;}
.tn-stale{background:#FFF7E5;border-color:#F0DDA8;color:#92690E;}
.tn-off{background:#FDECEC;border-color:#F3C2C2;color:#B33737;}
.tn-neutral{background:#F1F4F5;color:#42505C;}
.tn-grid2{display:grid;grid-template-columns:1fr 1fr;gap:8px;}
.tn-metric{border:1px solid #DDE4E8;border-radius:8px;padding:8px 10px;min-width:0;}
.tn-m-label{color:#637381;font-size:11px;font-weight:700;letter-spacing:.04em;}
.tn-m-value{font-size:21px;font-weight:750;font-variant-numeric:tabular-nums;
line-height:1.25;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}
.tn-kv{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:13px;margin-top:8px;}
.tn-k{color:#637381;}.tn-v{font-weight:650;font-variant-numeric:tabular-nums;}
.tn-sec{border:1px solid #DDE4E8;border-radius:10px;padding:10px 12px;margin-bottom:10px;}
.tn-sec-t{color:#637381;font-size:11px;font-weight:700;letter-spacing:.05em;margin-bottom:6px;}
.tn-strip{display:grid;grid-template-columns:repeat(10,minmax(0,1fr));gap:6px;}
.tn-tile{border:1px solid #DDE4E8;border-radius:8px;padding:5px 7px;min-width:0;overflow:hidden;}
.tn-t-label{color:#637381;font-size:11px;font-weight:700;line-height:1.2;}
.tn-t-value{font-size:15px;font-weight:750;font-variant-numeric:tabular-nums;white-space:nowrap;line-height:1.2;}
.tn-t-state{font-size:10px;font-weight:700;white-space:nowrap;line-height:1.2;min-height:12px;}
.tn-ok{color:#157A3D;}.tn-bad{color:#B33737;}
.tn-wait{color:#637381;font-size:13px;padding:8px 2px;}
.tn-row{display:flex;gap:8px;align-items:center;}
table.tn-table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums;}
table.tn-table th{color:#637381;text-align:left;font-weight:700;padding:5px 8px;
border-bottom:1px solid #DDE4E8;position:sticky;top:0;background:#FFFFFF;}
table.tn-table td{padding:4px 8px;border-bottom:1px solid #EDF1F3;white-space:nowrap;}
.tn-scroll{overflow-y:auto;}
.tn-hist-bar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:6px;font-size:12.5px;}
.tn-hist-bar label{display:inline-flex;gap:4px;align-items:center;color:#42505C;}
.tn-hist-bar select{border:1px solid #DDE4E8;border-radius:6px;padding:3px 6px;}
a.tn-btn{display:inline-block;background:#0E7C7B;color:#fff;border-radius:8px;
padding:6px 14px;text-decoration:none;font-weight:650;font-size:13px;margin-top:8px;}
"""


def _doc(body: str, script: str, *, plotly: bool = False) -> str:
    plotly_tag = (f'<script src="{API}/static/plotly.min.js"></script>'
                  if plotly else "")
    return (
        "<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<style>{_CSS}</style>{plotly_tag}"
        f"<script src='{API}/static/live.js'></script>"
        "</head><body>"
        f"{body}<script>{script}</script>"
        "</body></html>"
    )


def _show(body: str, script: str, height: int, *, plotly: bool = False) -> None:
    components.html(_doc(body, script, plotly=plotly), height=height)


# ---------------------------------------------------------------------------
# Regions
# ---------------------------------------------------------------------------

def chips(height: int = 46) -> None:
    """Compact LIVE/COM4/seq/age chips (reception lives on System page)."""
    _show(
        "<div class='tn-row' style='gap:8px;padding:2px;'>"
        "<span class='tn-chip tn-off' id='c-fresh'><span class='tn-dot' id='c-dot' "
        "style='background:#D64545;'></span><span id='c-fresh-t'>OFFLINE</span></span>"
        "<span class='tn-chip tn-neutral' id='c-port'>COM4</span>"
        "<span class='tn-chip tn-neutral' id='c-seq'>Seq -</span>"
        "<span class='tn-chip tn-neutral' id='c-age'>Updated -</span>"
        "</div>",
        """TN.poll('/api/telemetry/latest', 1000, (s) => {
          const f = s.hasData ? s.freshness : 'OFFLINE';
          TN.setText('c-fresh-t', f);
          document.getElementById('c-fresh').className =
            'tn-chip ' + (f === 'LIVE' ? 'tn-live' : f === 'STALE' ? 'tn-stale' : 'tn-off');
          document.getElementById('c-dot').style.background =
            f === 'LIVE' ? '#1FA34A' : f === 'STALE' ? '#D9A21B' : '#D64545';
          TN.setText('c-seq', 'Seq ' + (s.hasData ? s.seq : '-'));
          TN.setText('c-age', 'Updated ' + (!s.hasData || s.ageSeconds === null ? '-' :
            (s.ageSeconds < 60 ? s.ageSeconds.toFixed(1) + ' s' : (s.ageSeconds / 60).toFixed(1) + ' min')));
        });""",
        height,
    )


def data_bar(height: int = 60) -> None:
    """Slim full-width data-quality bar (ownership: reception stats live here)."""
    _show(
        "<div class='tn-kv' style='margin:0;'>"
        "<span><span class='tn-k'>Unique:</span> <span class='tn-v' id='d-u'>-</span></span>"
        "<span><span class='tn-k'>Duplicates:</span> <span class='tn-v' id='d-d'>-</span></span>"
        "<span><span class='tn-k'>Missing:</span> <span class='tn-v' id='d-m'>-</span></span>"
        "<span><span class='tn-k'>Malformed:</span> <span class='tn-v' id='d-mm'>-</span></span>"
        "<span><span class='tn-k'>Reception:</span> <span class='tn-v' id='d-r'>-</span></span>"
        "</div>",
        """TN.poll('/api/telemetry/latest', 2000, (s) => {
          if (!s.hasData) return;
          TN.setText('d-u', String(s.uniqueRx));
          TN.setText('d-d', String(s.duplicates));
          TN.setText('d-m', String(s.estimatedMissing));
          TN.setText('d-mm', String(s.malformed));
          TN.setText('d-r', s.receptionRate === null ? '-' : s.receptionRate.toFixed(1) + ' %');
        });""",
        height,
    )


def sensor_strip(height: int = 92) -> None:
    """10 compact sensor tiles in one row (fixed geometry, N/A-safe)."""
    tiles = "".join(
        f"<div class='tn-tile'><div class='tn-t-label'>{label}</div>"
        f"<div class='tn-t-value' id='tile-{key}'>-</div>"
        f"<div class='tn-t-state' id='tile-{key}-s'></div></div>"
        for label, key in
        [("N1", "n0"), ("N2", "n1"), ("N3", "n2"), ("N4", "n3"), ("N5", "n4"),
         ("N6", "n5"), ("N7", "n6"), ("N8", "n7"), ("SI1", "s1"), ("SI2", "s2")]
    )
    _show(
        f"<div class='tn-strip'>{tiles}</div>",
        """const KEYS = ['n0','n1','n2','n3','n4','n5','n6','n7','s1','s2'];
        TN.poll('/api/telemetry/latest', 1000, (s) => {
          const vals = s.hasData ? s.ntc.concat([s.si1, s.si2]) : KEYS.map(() => null);
          const dec = (k) => (k[0] === 's' ? 2 : 1);
          KEYS.forEach((k, i) => {
            const v = vals[i], ok = TN.isValid(v);
            TN.setText('tile-' + k, ok ? v.toFixed(dec(k)) + ' °C' : 'N/A');
            const st = document.getElementById('tile-' + k + '-s');
            const html = ok ? "<span class='tn-ok'>● VALID</span>"
                            : "<span class='tn-bad'>● DISCONNECTED</span>";
            if (st.innerHTML !== html) st.innerHTML = html;
          });
        });""",
        height,
    )


def chamber(height: int = 540) -> None:
    """Interpolated-gradient 3D chamber (camera preserved across updates)."""
    _show(
        "<div id='ch' style='width:100%;height:100%;'></div>"
        "<div class='tn-wait' id='ch-wait'>WAITING FOR TELEMETRY</div>",
        """let range = null, init = false;
        TN.poll('/api/telemetry/latest', 1200, (s) => {
          if (!s.hasData) return;
          document.getElementById('ch-wait').style.display = 'none';
          const ntc = {}; s.ntc.forEach((v, i) => ntc['NTC' + (i + 1)] = v);
          const si = { SI1: s.si1, SI2: s.si2 };
          range = TN.stableRange(s.ntc.filter(TN.isValid), range);
          const traces = TN.chamberTraces(ntc, si, range);
          const div = document.getElementById('ch');
          if (!init) {
            Plotly.newPlot(div, traces, TN.chamberLayout(__H__),
              { responsive: true, displaylogo: false,
                modeBarButtonsToRemove: ['lasso2d', 'select2d'] });
            init = true;
          } else { Plotly.react(div, traces, div.layout); }
        });""".replace("__H__", str(height)),
        height,
        plotly=True,
    )


def overview_side(height: int = 560) -> None:
    """Right-column stack: thermal metrics, sensor health, location, radio."""
    _show(
        "<div class='tn-sec'><div class='tn-sec-t'>Thermal</div>"
        "<div class='tn-grid2'>"
        "<div class='tn-metric'><div class='tn-m-label'>AVG</div>"
        "<div class='tn-m-value' id='o-avg'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>MAX</div>"
        "<div class='tn-m-value' id='o-max'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>MIN</div>"
        "<div class='tn-m-value' id='o-min'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>DELTA-T</div>"
        "<div class='tn-m-value' id='o-dt'>-</div></div></div>"
        "<div class='tn-kv'><span><span class='tn-k'>Hot:</span> "
        "<span class='tn-v' id='o-hot'>-</span></span>"
        "<span><span class='tn-k'>Cold:</span> <span class='tn-v' id='o-cold'>-</span></span>"
        "<span><span class='tn-k'>Valid:</span> <span class='tn-v' id='o-valid'>-</span></span>"
        "</div></div>"
        "<div class='tn-sec'><div class='tn-sec-t'>Sensor health</div>"
        "<div class='tn-kv'><span><span class='tn-k'>NTC:</span> "
        "<span class='tn-v' id='o-ntc'>-</span></span>"
        "<span><span class='tn-k'>SI1:</span> <span class='tn-v' id='o-si1'>-</span></span>"
        "<span><span class='tn-k'>SI2:</span> <span class='tn-v' id='o-si2'>-</span></span>"
        "</div></div>"
        "<div class='tn-sec'><div class='tn-sec-t'>Location</div>"
        "<div class='tn-kv'><span><span class='tn-k'>GPS:</span> "
        "<span class='tn-v' id='o-fix'>-</span></span>"
        "<span><span class='tn-k'>Sats:</span> <span class='tn-v' id='o-sats'>-</span></span>"
        "<span><span class='tn-k'>Lat/Lon:</span> <span class='tn-v' id='o-ll'>-</span></span>"
        "</div></div>"
        "<div class='tn-sec'><div class='tn-sec-t'>Radio</div>"
        "<div class='tn-kv'><span><span class='tn-k'>RSSI:</span> "
        "<span class='tn-v' id='o-rssi'>-</span></span>"
        "<span><span class='tn-k'>SNR:</span> <span class='tn-v' id='o-snr'>-</span></span>"
        "<span><span class='tn-k'>Quality:</span> <span class='tn-v' id='o-q'>-</span></span>"
        "</div></div>",
        """TN.poll('/api/telemetry/latest', 1000, (s) => {
          if (!s.hasData) return;
          const st = s.stats || {};
          TN.setText('o-avg', TN.fmtTemp(st.avg));
          TN.setText('o-max', TN.fmtTemp(st.max));
          TN.setText('o-min', TN.fmtTemp(st.min));
          TN.setText('o-dt', TN.fmtTemp(st.delta));
          TN.setText('o-hot', (st.hottest || '-') + (TN.isValid(st.max) ? ' ' + st.max.toFixed(1) : ''));
          TN.setText('o-cold', (st.coldest || '-') + (TN.isValid(st.min) ? ' ' + st.min.toFixed(1) : ''));
          TN.setText('o-valid', (st.valid_count || 0) + '/8');
          const ok = s.ntc.filter(TN.isValid).length;
          TN.setText('o-ntc', ok + '/8');
          TN.setText('o-si1', TN.isValid(s.si1) ? s.si1.toFixed(2) + ' ●' : 'DISCONNECTED');
          TN.setText('o-si2', TN.isValid(s.si2) ? s.si2.toFixed(2) + ' ●' : 'DISCONNECTED');
          const plot = s.gpsValid && !(Math.abs(s.latitude) < 1e-9 && Math.abs(s.longitude) < 1e-9);
          TN.setText('o-fix', s.gpsValid ? 'FIX' : 'NO FIX');
          TN.setText('o-sats', s.satellites === null || s.satellites === undefined ? '-' : String(s.satellites));
          TN.setText('o-ll', plot ? s.latitude.toFixed(5) + ', ' + s.longitude.toFixed(5) : '-');
          TN.setText('o-rssi', (s.rssi === null ? '-' : s.rssi.toFixed(0) + ' dBm'));
          TN.setText('o-snr', (s.snr === null ? '-' : s.snr.toFixed(1) + ' dB'));
          TN.setText('o-q', (s.quality === null ? '-' : s.quality + ' %'));
        });""",
        height,
    )
