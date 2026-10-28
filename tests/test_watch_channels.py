"""Test del guardiano dei canali squadra (ops/alerts/watch_channels.py)."""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RADICE / "ops" / "alerts"))

import watch_channels as wc  # noqa: E402


def _mkcanale(tmp: Path, nome: str, req_txt: str = "", res_txt: str = "",
              age_req_s: float = 0, age_res_s: float = 0) -> Path:
    d = tmp / nome
    d.mkdir(parents=True)
    now = time.time()
    for nome_f, txt, age in (("requests.md", req_txt, age_req_s),
                             ("results.md", res_txt, age_res_s)):
        if txt is None:
            continue
        p = d / nome_f
        p.write_text(txt, encoding="utf-8")
        os.utime(p, (now - age, now - age))
    return d


def _req(rid: str, data: str) -> str:
    return "## %s | %s 12:00 UTC | PENDING\ncontenuto\n" % (rid, data)


def test_eta_canale_assente(cartella):
    assert wc.eta_canale(cartella / "nonesiste", time.time()) is None


def test_eta_canale_fresco(cartella):
    d = _mkcanale(cartella, "x")
    assert 0 <= wc.eta_canale(d, time.time()) < 10


def test_req_pendenti_nessuna(cartella):
    d = _mkcanale(cartella, "x", req_txt="", res_txt="")
    assert wc.req_pendenti(d, time.time()) == []


def test_req_pendenti_esitata_non_conta(cartella):
    d = _mkcanale(cartella, "x", req_txt=_req("REQ-X-20261028-001", "2026-10-28"),
                  res_txt="## REQ-X-20261028-001 | 13:00 UTC | DONE\n")
    assert wc.req_pendenti(d, time.time()) == []


def test_req_pendenti_vecchia_allerta(cartella):
    d = _mkcanale(cartella, "x", req_txt=_req("REQ-X-20261028-001", "2026-10-24"), res_txt="")
    pend = wc.req_pendenti(d, time.time())
    assert len(pend) == 1
    assert pend[0][0] == "REQ-X-20261028-001"
    assert pend[0][1] > wc.SOGLIA_REQ_S


def test_req_pendenti_case_insensitive(cartella):
    d = _mkcanale(cartella, "x", req_txt=_req("REQ-X-20261028-001", "2026-10-28"),
                  res_txt="## req-x-20261028-001 | 13:00 UTC | FAILED\n")
    assert wc.req_pendenti(d, time.time()) == []


def test_main_dry_tmp(cartella, monkeypatch):
    monkeypatch.setattr(wc, "BRIDGE", cartella)
    monkeypatch.setattr(wc, "LOG", cartella / "log.txt")
    _mkcanale(cartella, "nuvola")
    sys.argv = ["watch_channels", "--canali", "nuvola", "--dry"]
    rc = wc.main()
    assert rc == 0
    assert (cartella / "log.txt").is_file()
