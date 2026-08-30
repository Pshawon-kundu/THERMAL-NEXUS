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
    }
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 32px;
    }
    main {
      width: min(760px, 100%);
      background: #ffffff;
      border: 1px solid #d8e0ea;
      border-radius: 8px;
      padding: clamp(28px, 5vw, 48px);
      box-shadow: 0 18px 55px rgba(23, 32, 51, 0.08);
    }
    h1 {
      margin: 0 0 12px;
      font-size: clamp(2rem, 5vw, 3.25rem);
      line-height: 1.05;
      letter-spacing: 0;
    }
    p {
      margin: 0 0 18px;
      max-width: 66ch;
      color: #41506a;
      font-size: 1rem;
      line-height: 1.65;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 8px;
      margin-bottom: 24px;
      padding: 6px 10px;
      border-radius: 999px;
      background: #e9f7ef;
      color: #17613a;
      font-size: 0.9rem;
      font-weight: 650;
    }
    .dot {
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: #21a466;
    }
    code {
      color: #22304a;
      background: #eef3f8;
      border-radius: 5px;
      padding: 2px 5px;
    }
  </style>
</head>
<body>
  <main>
    <div class="status"><span class="dot"></span>Vercel deployment is live</div>
    <h1>Thermal Nexus</h1>
    <p>
      Predictive cold-chain temperature monitoring prototype with simulation,
      ML artifacts, MQTT ingestion, and an offline Streamlit dashboard.
    </p>
    <p>
      This Vercel entrypoint verifies the repository deploys successfully on
      Vercel. Run the interactive dashboard locally with
      <code>streamlit run host/dashboard/app.py</code>.
    </p>
  </main>
</body>
</html>
"""


class handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = HTML.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
