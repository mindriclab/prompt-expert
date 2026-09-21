"""Auslieferung der Wurzel-URL.

Sobald ``frontend/dist`` existiert, wird das gebaute Frontend ausgeliefert.
Bis dahin steht dort eine Statusseite, die den Live-Zustand des Backends zeigt -
statt eines 404, das wie ein Absturz aussieht.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles

from app.core.paths import frontend_dist

STATUS_PAGE = """<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prompt Expert</title>
<style>
  :root { color-scheme: dark; }
  body {
    margin: 0; min-height: 100vh; display: grid; place-items: center;
    background: #0e1013; color: #e6e8ec;
    font: 15px/1.6 "Segoe UI", system-ui, sans-serif;
  }
  main { width: min(680px, 92vw); padding: 40px 0; }
  h1 { font-size: 22px; font-weight: 600; margin: 0 0 4px; letter-spacing: -0.01em; }
  .sub { color: #8b93a1; margin: 0 0 28px; font-size: 14px; }
  .card { background: #16191f; border: 1px solid #242932;
          border-radius: 10px; padding: 20px 22px; }
  .row { display: flex; justify-content: space-between;
         gap: 20px; padding: 7px 0; font-size: 14px; }
  .row + .row { border-top: 1px solid #1e222a; }
  .k { color: #8b93a1; }
  .v { color: #e6e8ec; font-family: "Cascadia Mono", Consolas, monospace; font-size: 13px;
       text-align: right; word-break: break-all; }
  .dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 7px; }
  .on { background: #3ecf8e; } .off { background: #e5484d; } .wait { background: #8b93a1; }
  .note { margin-top: 22px; color: #8b93a1; font-size: 13px; }
  .copyright { margin-top: 26px; color: #6b7280; font-size: 12px; }
  a { color: #7aa2f7; text-decoration: none; }
  a:hover { text-decoration: underline; }
  .links { margin-top: 20px; display: flex; gap: 18px; font-size: 14px; }
</style>
</head>
<body>
<main>
  <h1>Prompt Expert</h1>
  <p class="sub">Backend läuft. Die Oberfläche ist noch nicht gebaut &mdash;
     einmal <code>scriptsuild_frontend.ps1</code> ausführen.</p>

  <div class="card" id="card">
    <div class="row"><span class="k">Status</span>
      <span class="v"><span class="dot wait" id="dot"></span>
        <span id="status">wird geprüft</span></span></div>
    <div class="row"><span class="k">Version</span><span class="v" id="version">-</span></div>
    <div class="row"><span class="k">Zielprofile</span><span class="v" id="profiles">-</span></div>
    <div class="row"><span class="k">Provider</span><span class="v" id="provider">-</span></div>
    <div class="row"><span class="k">Modell</span><span class="v" id="model">-</span></div>
    <div class="row"><span class="k">Datenverzeichnis</span>
      <span class="v" id="datadir">-</span></div>
  </div>

  <div class="links">
    <a href="/docs">API-Doku</a>
    <a href="/api/health">/api/health</a>
    <a href="/api/profiles">/api/profiles</a>
  </div>

  <p class="copyright">© by mindric lab</p>

  <p class="note">Verbindung zum Modellserver prüfen:
    <code>POST /api/provider/test</code> mit <code>{"probe": true}</code> &mdash;
    am einfachsten über die API-Doku.</p>
</main>
<script>
fetch("/api/health").then(r => r.json()).then(h => {
  document.getElementById("dot").className = "dot on";
  document.getElementById("status").textContent = "bereit";
  document.getElementById("version").textContent = h.version;
  document.getElementById("profiles").textContent =
    h.profiles + (h.profiles_invalid ? " (" + h.profiles_invalid + " ungültig)" : "");
  document.getElementById("provider").textContent = h.provider_kind + " @ " + h.provider_base_url;
  document.getElementById("model").textContent = h.text_model;
  document.getElementById("datadir").textContent = h.data_dir;
}).catch(() => {
  document.getElementById("dot").className = "dot off";
  document.getElementById("status").textContent = "Backend antwortet nicht";
});
</script>
</body>
</html>
"""


def mount_web(app: FastAPI) -> bool:
    """Hängt Wurzel-Route bzw. gebautes Frontend ein. True = Frontend gefunden."""

    @app.get("/favicon.ico", include_in_schema=False)
    async def _favicon() -> Response:
        return Response(status_code=204)

    dist = frontend_dist()
    if (dist / "index.html").is_file():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")
        return True

    @app.get("/", include_in_schema=False)
    async def _status_page() -> HTMLResponse:
        return HTMLResponse(STATUS_PAGE)

    return False
