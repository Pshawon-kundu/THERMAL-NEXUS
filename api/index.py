from __future__ import annotations

from http import HTTPStatus
from http.server import BaseHTTPRequestHandler


HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Thermal Nexus</title>
  <style>
    :root {
      color-scheme: light;
      font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f7f9fb;
      color: #172033;
      --accent: #0f766e;
      --accent-dark: #0f5f59;
      --border: #d8e0ea;
      --muted: #41506a;
    }
    * {
      box-sizing: border-box;
    }
    body {
      margin: 0;
      min-height: 100vh;
      background:
        linear-gradient(180deg, rgba(15, 118, 110, 0.08), transparent 280px),
        #f7f9fb;
    }
    header {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto;
      padding: 24px 0 18px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 12px;
      min-width: 0;
    }
    .mark {
      width: 38px;
      height: 38px;
      border-radius: 8px;
      background: #17324d;
      color: #ffffff;
      display: grid;
      place-items: center;
      font-weight: 800;
      letter-spacing: 0;
    }
    h1 {
      margin: 0;
      font-size: clamp(1.35rem, 3vw, 2rem);
      line-height: 1.1;
      letter-spacing: 0;
    }
    .subtitle {
      margin: 4px 0 0;
      color: var(--muted);
      font-size: 0.95rem;
    }
    .actions {
      display: flex;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
      justify-content: flex-end;
    }
    a.button {
      appearance: none;
      border: 1px solid var(--accent);
      border-radius: 7px;
      background: var(--accent);
      color: #ffffff;
      text-decoration: none;
      padding: 10px 14px;
      font-size: 0.95rem;
      font-weight: 700;
      line-height: 1;
    }
    a.button:hover {
      background: var(--accent-dark);
      border-color: var(--accent-dark);
    }
    a.secondary {
      background: #ffffff;
      color: #17324d;
      border-color: var(--border);
    }
    a.secondary:hover {
      background: #eef3f8;
      border-color: #bac8d8;
    }
    main {
      width: min(1180px, calc(100% - 32px));
      margin: 0 auto 28px;
    }
    .panel {
      background: #ffffff;
      border: 1px solid var(--border);
      border-radius: 8px;
      box-shadow: 0 18px 45px rgba(23, 32, 51, 0.08);
      overflow: hidden;
    }
    .status-bar {
      border-bottom: 1px solid var(--border);
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 14px;
      color: #24324a;
      font-size: 0.94rem;
      flex-wrap: wrap;
    }
    .status-left {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      padding: 6px 10px;
      border-radius: 7px;
      background: #e9f7ef;
      color: #17613a;
      font-size: 0.9rem;
      font-weight: 650;
      white-space: nowrap;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: #21a466;
    }
    .local-url {
      color: var(--muted);
      overflow-wrap: anywhere;
    }
    iframe {
      display: block;
      width: 100%;
      height: min(78vh, 900px);
      min-height: 560px;
      border: 0;
      background: #ffffff;
    }
    .fallback {
      padding: clamp(24px, 5vw, 40px);
      display: none;
    }
    .fallback.active {
      display: block;
    }
    .fallback h2 {
      margin: 0 0 10px;
      font-size: clamp(1.5rem, 4vw, 2.4rem);
      line-height: 1.1;
      letter-spacing: 0;
    }
    .fallback p {
      margin: 0 0 18px;
      max-width: 68ch;
      color: var(--muted);
      font-size: 1rem;
      line-height: 1.65;
    }
    code {
      color: #22304a;
      background: #eef3f8;
      border-radius: 5px;
      padding: 2px 5px;
    }
    @media (max-width: 760px) {
      header {
        align-items: flex-start;
        flex-direction: column;
      }
      .actions {
        justify-content: flex-start;
      }
      iframe {
        min-height: 620px;
        height: 80vh;
      }
    }
  </style>
</head>
<body>
  <header>
    <div class="brand">
      <div class="mark">TN</div>
      <div>
        <h1>Thermal Nexus</h1>
        <p class="subtitle">Cold-chain monitoring dashboard launcher</p>
      </div>
    </div>
    <nav class="actions" aria-label="Dashboard links">
      <a class="button" href="http://localhost:8501" target="_blank" rel="noreferrer">Open local dashboard</a>
      <a class="button secondary" href="http://localhost:8501">Use this tab</a>
    </nav>
  </header>
  <main>
    <section class="panel" aria-label="Thermal Nexus local dashboard">
      <div class="status-bar">
        <div class="status-left">
          <span class="status"><span class="dot"></span>Vercel is live</span>
          <span class="local-url">Local dashboard target: <code>http://localhost:8501</code></span>
        </div>
        <span id="frame-status">Loading local dashboard...</span>
      </div>
      <iframe
        id="dashboard-frame"
        title="Thermal Nexus local Streamlit dashboard"
        src="http://localhost:8501"
        loading="eager"
      ></iframe>
      <div class="fallback" id="fallback">
        <h2>Start the local dashboard to use this page.</h2>
        <p>
          This deployed Vercel page is a public launcher. The interactive
          Streamlit dashboard, MQTT ingestion service, and SQLite database run
          on your computer at <code>http://localhost:8501</code>.
        </p>
        <p>
          Start the stack locally, then use the button above or refresh this
          page. In this repository the command is
          <code>powershell -NoProfile -ExecutionPolicy Bypass -File .\\tools\\run_dashboard.ps1</code>.
        </p>
      </div>
    </section>
  </main>
  <script>
    const frame = document.getElementById("dashboard-frame");
    const fallback = document.getElementById("fallback");
    const statusText = document.getElementById("frame-status");

    let loaded = false;
    frame.addEventListener("load", () => {
      loaded = true;
      statusText.textContent = "Local dashboard loaded";
    });

    window.setTimeout(() => {
      if (!loaded) {
        fallback.classList.add("active");
        statusText.textContent = "Waiting for localhost";
      }
    }, 4500);
  </script>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header(
            "Content-Security-Policy",
            "frame-src http://localhost:8501 http://127.0.0.1:8501; "
            "default-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "script-src 'self' 'unsafe-inline'",
        )
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
