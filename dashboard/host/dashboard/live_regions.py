"""Level-2 live regions, part 2: thermal side, history, location, system."""

from __future__ import annotations

from host.dashboard.live import _show, API


def thermal_side(height: int = 560) -> None:
    """Right panel: metrics + compact 10-sensor matrix (fixed geometry)."""
    cells = "".join(
        f"<div class='tn-tile'><div class='tn-t-label'>{label}</div>"
        f"<div class='tn-t-value' id='tm-{key}'>-</div>"
        f"<div class='tn-t-state' id='tm-{key}-s'></div></div>"
        for label, key in
        [("NTC1", "n1"), ("NTC2", "n2"), ("NTC3", "n3"), ("NTC4", "n4"),
         ("NTC5", "n5"), ("NTC6", "n6"), ("NTC7", "n7"), ("NTC8", "n8"),
         ("SI1", "s1"), ("SI2", "s2")]
    )
    _show(
        "<div class='tn-sec'><div class='tn-sec-t'>Metrics</div>"
        "<div class='tn-grid2'>"
        "<div class='tn-metric'><div class='tn-m-label'>AVG</div>"
        "<div class='tn-m-value' id='tm-avg'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>MAX</div>"
        "<div class='tn-m-value' id='tm-max'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>MIN</div>"
        "<div class='tn-m-value' id='tm-min'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>DELTA-T</div>"
        "<div class='tn-m-value' id='tm-dt'>-</div></div></div>"
        "<div class='tn-kv'><span><span class='tn-k'>Hot:</span> "
        "<span class='tn-v' id='tm-hot'>-</span></span>"
        "<span><span class='tn-k'>Cold:</span> <span class='tn-v' id='tm-cold'>-</span></span>"
        "<span><span class='tn-k'>Valid:</span> <span class='tn-v' id='tm-valid'>-</span></span>"
        "</div></div>"
        "<div class='tn-sec'><div class='tn-sec-t'>Sensors</div>"
        f"<div class='tn-strip' style='grid-template-columns:repeat(2,minmax(0,1fr));'>{cells}</div>"
        "</div>",
        """const ORDER = ['n1','n2','n3','n4','n5','n6','n7','n8','s1','s2'];
        TN.poll('/api/telemetry/latest', 1000, (s) => {
          if (!s.hasData) return;
          const st = s.stats || {};
          TN.setText('tm-avg', TN.fmtTemp(st.avg));
          TN.setText('tm-max', TN.fmtTemp(st.max));
          TN.setText('tm-min', TN.fmtTemp(st.min));
          TN.setText('tm-dt', TN.fmtTemp(st.delta));
          TN.setText('tm-hot', st.hottest || '-');
          TN.setText('tm-cold', st.coldest || '-');
          TN.setText('tm-valid', (st.valid_count || 0) + '/8');
          const vals = { n1: s.ntc[0], n2: s.ntc[1], n3: s.ntc[2], n4: s.ntc[3],
            n5: s.ntc[4], n6: s.ntc[5], n7: s.ntc[6], n8: s.ntc[7], s1: s.si1, s2: s.si2 };
          const dec = { s1: 2, s2: 2 };
          ORDER.forEach((k) => {
            const v = vals[k], ok = TN.isValid(v);
            TN.setText('tm-' + k, ok ? v.toFixed(dec[k] || 1) + ' °C' : 'N/A');
            const el = document.getElementById('tm-' + k + '-s');
            const html = ok ? "<span class='tn-ok'>● VALID</span>"
                            : "<span class='tn-bad'>● DISCONNECTED</span>";
            if (el.innerHTML !== html) el.innerHTML = html;
          });
        });""",
        height,
    )


def history(height: int = 430) -> None:
    """Full-width temperature history with native toolbar (no Streamlit widgets)."""
    boxes = "".join(
        f"<label><input type='checkbox' data-s='{key}'"
        f"{' checked' if key.startswith('ntc') else ''}> {label}</label>"
        for label, key in
        [("NTC1", "ntc1"), ("NTC2", "ntc2"), ("NTC3", "ntc3"), ("NTC4", "ntc4"),
         ("NTC5", "ntc5"), ("NTC6", "ntc6"), ("NTC7", "ntc7"), ("NTC8", "ntc8"),
         ("SI1", "si1"), ("SI2", "si2")]
    )
    _show(
        "<div class='tn-hist-bar'><span style='color:#637381;font-weight:700;'>Sensors</span>"
        f"{boxes}"
        "<span style='color:#637381;font-weight:700;'>Range</span>"
        "<select id='h-range'><option value='300'>Recent</option>"
        "<option value='300'>5 min</option><option value='900'>15 min</option>"
        "<option value='2000'>Session</option></select></div>"
        "<div id='hdiv' style='width:100%;height:360px;'></div>",
        """const PAL = ['#0E7C7B','#7A4EAB','#C26A1B','#2E7D32','#C0392B',
          '#93702A','#1F618D','#A63FA0','#0A9396','#D14D8A'];
        const NAMES = { ntc1: 'NTC1', ntc2: 'NTC2', ntc3: 'NTC3', ntc4: 'NTC4',
          ntc5: 'NTC5', ntc6: 'NTC6', ntc7: 'NTC7', ntc8: 'NTC8', si1: 'SI7021 #1', si2: 'SI7021 #2' };
        let init = false, timer = null;
        const LAYOUT = { template: 'plotly_white', height: 360,
          margin: { l: 48, r: 16, t: 12, b: 40 }, yaxis: { title: 'Temperature (°C)' },
          paper_bgcolor: '#FFFFFF', plot_bgcolor: '#FFFFFF',
          legend: { orientation: 'h', y: 1.06, x: 0 } };
        function selected() {
          return Array.from(document.querySelectorAll('[data-s]:checked')).map((c) => c.dataset.s);
        }
        async function tick() {
          const limit = document.getElementById('h-range').value;
          let d; try { d = await TN.get('/api/telemetry/history?limit=' + limit); }
          catch (e) { return; }
          const sel = selected();
          const traces = sel.map((k, i) => ({
            type: 'scatter', mode: 'lines', name: NAMES[k],
            x: d.t.map((t) => new Date(t * 1000)), y: d[k], connectgaps: false,
            line: { color: PAL[i % PAL.length], width: 1.8 } }));
          const div = document.getElementById('hdiv');
          if (!init) { Plotly.newPlot(div, traces, LAYOUT,
            { responsive: true, displaylogo: false }); init = true; }
          else { Plotly.react(div, traces, div.layout); }
        }
        function restart() { if (timer) clearInterval(timer); tick(); timer = setInterval(tick, 3000); }
        document.querySelectorAll('[data-s]').forEach((c) => c.addEventListener('change', tick));
        document.getElementById('h-range').addEventListener('change', tick);
        restart();""",
        height,
        plotly=True,
    )


def location_kpi(height: int = 84) -> None:
    """Compact GPS summary row (fixed geometry)."""
    _show(
        "<div class='tn-row' style='gap:8px;'>"
        "<span class='tn-chip tn-off' id='g-fix'>NO FIX</span>"
        "<span class='tn-chip tn-neutral' id='g-sats'>- SATS</span>"
        "<span class='tn-chip tn-neutral' id='g-ll'>- , -</span>"
        "<span class='tn-chip tn-neutral' id='g-age'>Updated -</span>"
        "</div>",
        """TN.poll('/api/telemetry/latest', 2000, (s) => {
          const el = document.getElementById('g-fix');
          if (!s.hasData || !s.gpsValid) {
            el.className = 'tn-chip tn-off'; TN.setText('g-fix', 'NO FIX');
            TN.setText('g-ll', '- , -');
          } else {
            el.className = 'tn-chip tn-live'; TN.setText('g-fix', 'FIX');
            const plot = !(Math.abs(s.latitude) < 1e-9 && Math.abs(s.longitude) < 1e-9);
            TN.setText('g-ll', plot ? s.latitude.toFixed(6) + ', ' + s.longitude.toFixed(6) : '- , -');
          }
          TN.setText('g-sats', (s.hasData && s.satellites !== null ? s.satellites : '-') + ' SATS');
          TN.setText('g-age', 'Updated ' + (!s.hasData ? '-' : s.ageSeconds.toFixed(0) + ' s'));
        });""",
        height,
    )


def gps_map(height: int = 540) -> None:
    """OSM map; viewport never touched after init (zoom survives updates)."""
    _show(
        "<div id='mapdiv' style='width:100%;height:100%;'></div>"
        "<div class='tn-wait' id='map-wait'>NO GPS FIX — searching for satellites…</div>",
        """let init = false;
        TN.poll('/api/gps/trail?limit=150', 2000, (d) => {
          const pts = d.points || [];
          if (!pts.length) return;
          document.getElementById('map-wait').style.display = 'none';
          const cur = d.current;
          const trail = { type: 'scattermapbox', mode: 'lines',
            lat: pts.map((p) => p.lat), lon: pts.map((p) => p.lon),
            line: { color: '#0E7C7B', width: 3 }, hoverinfo: 'skip', name: 'Trail' };
          const mark = { type: 'scattermapbox', mode: 'markers',
            lat: [cur.lat], lon: [cur.lon],
            marker: { size: 18, color: '#1FA34A', allowoverlap: true },
            hovertemplate: '<b>Current</b><br>' + cur.lat.toFixed(6) + ', ' +
              cur.lon.toFixed(6) + '<br>Sats: ' + cur.sats + ' · seq ' + cur.seq + '<extra></extra>',
            name: 'Current' };
          const div = document.getElementById('mapdiv');
          if (!init) {
            Plotly.newPlot(div, [trail, mark],
              { mapbox: { style: 'open-street-map',
                  center: { lat: cur.lat, lon: cur.lon }, zoom: 16 },
                height: __H__, margin: { l: 0, r: 0, t: 8, b: 0 },
                paper_bgcolor: '#FFFFFF',
                legend: { font: { color: '#42505C' }, orientation: 'h', y: -0.02 } },
              { responsive: true, displaylogo: false });
            init = true;
          } else { Plotly.react(div, [trail, mark], div.layout); }
        });""".replace("__H__", str(height)),
        height,
        plotly=True,
    )


def gps_table(height: int = 220) -> None:
    """Compact recent-fixes table (fixed 12 rows, in-place cells)."""
    rows = "".join(
        f"<tr>{''.join(f'<td id=\"gt-{r}-{c}\">-</td>' for c in range(5))}</tr>"
        for r in range(12)
    )
    _show(
        "<div class='tn-scroll' style='max-height:100%%;'><table class='tn-table'>"
        "<tr><th>Time</th><th>Seq</th><th>Lat</th><th>Lon</th><th>Sats</th></tr>"
        f"{rows}</table></div>",
        """TN.poll('/api/gps/trail?limit=12', 5000, (d) => {
          const pts = (d.points || []).slice(-12).reverse();
          for (let r = 0; r < 12; r++) {
            const p = pts[r];
            const vals = p ? [new Date(p.t * 1000).toLocaleTimeString(), String(p.seq),
              p.lat.toFixed(6), p.lon.toFixed(6), String(p.sats)] : ['-','-','-','-','-'];
            vals.forEach((v, c) => TN.setText('gt-' + r + '-' + c, v));
          }
        });""",
        height,
    )


def link_metrics(height: int = 170) -> None:
    """Static RF config line + live RSSI/SNR/quality/age (HTML only)."""
    _show(
        "<div class='tn-kv' style='margin:0 0 8px;'>"
        "<span><span class='tn-k'>433 MHz</span></span>"
        "<span><span class='tn-k'>SF7</span></span>"
        "<span><span class='tn-k'>BW125</span></span>"
        "<span><span class='tn-k'>CR4/5</span></span>"
        "<span><span class='tn-k'>CRC ON</span></span></div>"
        "<div class='tn-grid2' style='grid-template-columns:repeat(4,minmax(0,1fr));'>"
        "<div class='tn-metric'><div class='tn-m-label'>RSSI</div>"
        "<div class='tn-m-value' id='l-rssi'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>SNR</div>"
        "<div class='tn-m-value' id='l-snr'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>QUALITY</div>"
        "<div class='tn-m-value' id='l-q'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>PACKET AGE</div>"
        "<div class='tn-m-value' id='l-age'>-</div></div></div>",
        """TN.poll('/api/telemetry/latest', 1000, (s) => {
          if (!s.hasData) return;
          TN.setText('l-rssi', s.rssi === null ? '-' : s.rssi.toFixed(0) + ' dBm');
          TN.setText('l-snr', s.snr === null ? '-' : s.snr.toFixed(1) + ' dB');
          TN.setText('l-q', s.quality === null ? '-' : s.quality + ' %');
          TN.setText('l-age', s.ageSeconds.toFixed(0) + ' s');
        });""",
        height,
    )


def link_trends(height: int = 300) -> None:
    """RSSI/SNR/quality subplots (react data-only)."""
    _show(
        "<div id='tdiv' style='width:100%;height:100%;'></div>",
        """let init = false;
        const L = (title) => ({ title, showgrid: true, gridcolor: '#E7ECEF' });
        const LAYOUT = { template: 'plotly_white', height: __H__,
          margin: { l: 48, r: 14, t: 16, b: 30 }, paper_bgcolor: '#FFFFFF',
          plot_bgcolor: '#FFFFFF', showlegend: false,
          grid: { rows: 1, columns: 3, pattern: 'independent' },
          yaxis: L('RSSI (dBm)'), yaxis2: L('SNR (dB)'), yaxis3: L('Quality (%)') };
        TN.poll('/api/link/recent?limit=300', 3000, (d) => {
          const pts = d.points || [];
          const x = pts.map((p) => new Date(p.t * 1000));
          const traces = [
            { type: 'scatter', mode: 'lines+markers', x, y: pts.map((p) => p.rssi),
              marker: { size: 4 }, line: { color: '#7A4EAB', width: 1.8 }, xaxis: 'x', yaxis: 'y' },
            { type: 'scatter', mode: 'lines+markers', x, y: pts.map((p) => p.snr),
              marker: { size: 4 }, line: { color: '#C26A1B', width: 1.8 }, xaxis: 'x2', yaxis: 'y2' },
            { type: 'scatter', mode: 'lines+markers', x, y: pts.map((p) => p.q),
              marker: { size: 4 }, line: { color: '#0E7C7B', width: 1.8 }, xaxis: 'x3', yaxis: 'y3' },
          ];
          const div = document.getElementById('tdiv');
          if (!init) { Plotly.newPlot(div, traces, LAYOUT,
            { responsive: true, displaylogo: false }); init = true; }
          else { Plotly.react(div, traces, div.layout); }
        });""".replace("__H__", str(height - 20)),
        height,
        plotly=True,
    )


def reliability(height: int = 120) -> None:
    """Receiver counters (receiver duplicates are legitimate RX data)."""
    _show(
        "<div class='tn-grid2' style='grid-template-columns:repeat(6,minmax(0,1fr));'>"
        "<div class='tn-metric'><div class='tn-m-label'>SEQ</div>"
        "<div class='tn-m-value' id='r-seq'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>UNIQUE</div>"
        "<div class='tn-m-value' id='r-u'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>DUPLICATES</div>"
        "<div class='tn-m-value' id='r-d'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>MISSING</div>"
        "<div class='tn-m-value' id='r-m'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>MALFORMED</div>"
        "<div class='tn-m-value' id='r-mm'>-</div></div>"
        "<div class='tn-metric'><div class='tn-m-label'>RECEPTION</div>"
        "<div class='tn-m-value' id='r-r'>-</div></div></div>",
        """TN.poll('/api/telemetry/latest', 2000, (s) => {
          if (!s.hasData) return;
          TN.setText('r-seq', String(s.seq));
          TN.setText('r-u', String(s.uniqueRx));
          TN.setText('r-d', String(s.duplicates));
          TN.setText('r-m', String(s.estimatedMissing));
          TN.setText('r-mm', String(s.malformed));
          TN.setText('r-r', s.receptionRate === null ? '-' : s.receptionRate.toFixed(1) + ' %');
        });""",
        height,
    )


def raw_table(height: int = 480) -> None:
    """Latest canonical rows, fixed 20 rows updated in place + CSV link."""
    cols = ["Time", "Seq", "SI1", "SI2", "NTC1", "NTC8", "RSSI", "Q"]
    rows = "".join(
        f"<tr>{''.join(f'<td id=\"rw-{r}-{c}\">-</td>' for c in range(len(cols)))}</tr>"
        for r in range(20)
    )
    _show(
        "<div class='tn-scroll' style='max-height:420px;'><table class='tn-table'><tr>"
        + "".join(f"<th>{c}</th>" for c in cols) + "</tr>" + rows + "</table></div>"
        + f"<a class='tn-btn' href='{API}/api/raw.csv?limit=200'>Download telemetry CSV</a>",
        """TN.poll('/api/raw?limit=20', 5000, (d) => {
          const rows = d.rows || [];
          for (let r = 0; r < 20; r++) {
            const row = rows[r];
            const vals = row ? [new Date(row.received_at * 1000).toLocaleTimeString(),
              String(row.seq),
              TN.isValid(row.digital_top_temp) ? row.digital_top_temp.toFixed(2) : 'N/A',
              TN.isValid(row.digital_bottom_temp) ? row.digital_bottom_temp.toFixed(2) : 'N/A',
              TN.isValid(row.ntc1_temp) ? row.ntc1_temp.toFixed(1) : 'N/A',
              TN.isValid(row.ntc8_temp) ? row.ntc8_temp.toFixed(1) : 'N/A',
              row.rssi_dbm === null ? '-' : row.rssi_dbm.toFixed(0),
              row.signal_quality === null ? '-' : String(row.signal_quality)]
              : ['-','-','-','-','-','-','-','-'];
            vals.forEach((v, c) => TN.setText('rw-' + r + '-' + c, v));
          }
        });""",
        height,
    )


def events_list(height: int = 190) -> None:
    """Recent receiver events (in-place list)."""
    items = "".join(f"<div class='tn-kv' id='ev-{i}'></div>" for i in range(8))
    _show(
        f"<div class='tn-sec-t'>Receiver events</div>{items}",
        """TN.poll('/api/events?limit=8', 5000, (d) => {
          const evs = d.events || [];
          for (let i = 0; i < 8; i++) {
            const el = document.getElementById('ev-' + i);
            const html = evs[i]
              ? '<span><span class=\"tn-k\">' + new Date(evs[i].received_at * 1000).toLocaleTimeString() +
                '</span> <span class=\"tn-v\">' + evs[i].event_type + '</span></span>'
              : '<span class=\"tn-k\">—</span>';
            if (el.innerHTML !== html) el.innerHTML = html;
          }
        });""",
        height,
    )
