"""Test del redirect 301 denaro.grivetto.eu/ -> web.grivetto.eu.

Il modulo ops/dashboard/serve_dashboard.py non e' un package importabile:
viene caricato con importlib.util.spec_from_file_location (pattern usato
altrove nei test del repo). Il server viene avviato su una porta effimera
e interrogato con Host header esplicito.
"""
from __future__ import annotations

import http.client
import importlib.util
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "ops" / "dashboard" / "serve_dashboard.py"

_spec = importlib.util.spec_from_file_location("serve_dashboard_under_test", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _make_server(tmp_path: Path) -> tuple[ThreadingHTTPServer, int]:
    (tmp_path / "landing.html").write_text("<html>landing</html>", encoding="utf-8")
    (tmp_path / "dashboard.html").write_text("<html>dashboard</html>", encoding="utf-8")
    (tmp_path / "agenti.html").write_text("<html>agenti</html>", encoding="utf-8")
    (tmp_path / "squadra.html").write_text("<html>squadra</html>", encoding="utf-8")
    (tmp_path / "agenti.json").write_text("{}", encoding="utf-8")
    (tmp_path / "scommessa.json").write_text("{}", encoding="utf-8")
    (tmp_path / "dsh.json").write_text("{}", encoding="utf-8")
    (tmp_path / "infra.json").write_text("{}", encoding="utf-8")

    _mod.DashboardHandler.html_dir = tmp_path
    _mod.DashboardHandler.html_file = "dashboard.html"
    _mod.DashboardHandler.landing_file = "landing.html"
    _mod.DashboardHandler.agg = None

    server = ThreadingHTTPServer(("127.0.0.1", 0), _mod.DashboardHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, port


def _request(port: int, method: str, path: str, host: str) -> tuple[int, dict[str, str]]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", host)
        conn.endheaders()
        resp = conn.getresponse()
        headers = {k.lower(): v for k, v in resp.getheaders()}
        resp.read()
        return resp.status, headers
    finally:
        conn.close()


def test_denaro_root_redirects_to_web(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, headers = _request(port, "GET", "/", "denaro.grivetto.eu")
        assert status == 301
        assert headers["location"] == "https://web.grivetto.eu/"

        status, headers = _request(port, "GET", "/index.html", "denaro.grivetto.eu")
        assert status == 301
        assert headers["location"] == "https://web.grivetto.eu/"

        status, _ = _request(port, "HEAD", "/", "denaro.grivetto.eu")
        assert status == 301
    finally:
        server.shutdown()
        server.server_close()


def test_denaro_operative_routes_not_redirected(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, _ = _request(port, "GET", "/dashboard", "denaro.grivetto.eu")
        assert status == 200

        status, _ = _request(port, "GET", "/agenti", "denaro.grivetto.eu")
        assert status == 200

        status, _ = _request(port, "GET", "/squadra", "denaro.grivetto.eu")
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()


def test_local_host_not_redirected(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, _ = _request(port, "GET", "/", "127.0.0.1")
        assert status == 200
    finally:
        server.shutdown()
        server.server_close()
