"""Test del guard Cloudflare Access sulle route /api/console.

Senza header Cf-Access-Jwt-Assertion la console non deve essere raggiungibile:
/api/console/chat puo' mandare messaggi ai 4 Hermes e non deve essere pubblico.
"""
from __future__ import annotations

import http.client
import importlib.util
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO / "ops" / "dashboard" / "serve_dashboard.py"

_spec = importlib.util.spec_from_file_location("serve_dashboard_console_guard", MODULE_PATH)
assert _spec is not None and _spec.loader is not None
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def _make_server(tmp_path: Path) -> tuple[ThreadingHTTPServer, int]:
    keys = tmp_path / "console-keys.json"
    keys.write_text("{}", encoding="utf-8")
    setattr(_mod, "CONSOLE_KEYS_FILE", str(keys))
    _mod.DashboardHandler.html_dir = tmp_path
    _mod.DashboardHandler.html_file = "dashboard.html"
    _mod.DashboardHandler.landing_file = "landing.html"
    _mod.DashboardHandler.agg = None
    server = ThreadingHTTPServer(("127.0.0.1", 0), _mod.DashboardHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def _request(port: int, method: str, path: str, headers: dict[str, str] | None = None) -> tuple[int, dict[str, str], bytes]:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.putrequest(method, path, skip_host=True)
        conn.putheader("Host", "denaro.grivetto.eu")
        for k, v in (headers or {}).items():
            conn.putheader(k, v)
        conn.endheaders()
        resp = conn.getresponse()
        body = resp.read()
        hdrs = {k.lower(): v for k, v in resp.getheaders()}
        return resp.status, hdrs, body
    finally:
        conn.close()


def test_console_agents_requires_access_header(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, _, body = _request(port, "GET", "/api/console/agents")
        assert status == 403
        assert b"Cloudflare Access" in body
    finally:
        server.shutdown()
        server.server_close()


def test_console_agents_with_access_header(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, _, body = _request(
            port, "GET", "/api/console/agents",
            {"Cf-Access-Jwt-Assertion": "dummy"},
        )
        assert status == 200
        data = json.loads(body)
        assert data["agents"] == []
    finally:
        server.shutdown()
        server.server_close()


def test_console_chat_requires_access_header(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, _, body = _request(port, "POST", "/api/console/chat")
        assert status == 403
        assert b"Cloudflare Access" in body
    finally:
        server.shutdown()
        server.server_close()


def test_console_result_requires_access_header(tmp_path: Path) -> None:
    server, port = _make_server(tmp_path)
    try:
        status, _, _ = _request(port, "GET", "/api/console/result?id=x")
        assert status == 403
    finally:
        server.shutdown()
        server.server_close()
