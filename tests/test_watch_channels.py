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


def test_chiave_alert_stabile_sul_drift():
    """La chiave di dedup non deve cambiare quando il testo 'drifta' (numeri che si muovono)."""
    a1 = "CANALI: canale 'dsh' muto da 10.4 giorni (ultima attivita' 250.8h fa)"
    a2 = "CANALI: canale 'dsh' muto da 10.5 giorni (ultima attivita' 251.8h fa)"
    assert wc._chiave_alert(a1) == wc._chiave_alert(a2) == "muto:dsh"
    r1 = "CANALI: REQ-20260928-222647-941241 PENDING da 741.8h senza esito in results.md"
    r2 = "CANALI: REQ-20260928-222647-941241 PENDING da 742.8h senza esito in results.md"
    assert wc._chiave_alert(r1) == wc._chiave_alert(r2) == "req:REQ-20260928-222647-941241"


def test_dedup_tra_giri_con_testo_driftato(cartella, monkeypatch):
    """Il secondo giro (testo driftato di un'ora) NON deve rinviare nulla: chiave stabile."""
    inviati: list[str] = []
    monkeypatch.setattr(wc, "BRIDGE", cartella)
    monkeypatch.setattr(wc, "LOG", cartella / "log.txt")
    monkeypatch.setattr(wc, "_notifica_tg", lambda t: inviati.append(t) or True)
    d = _mkcanale(cartella, "dsh", req_txt=_req("REQ-D-20261020-001", "2026-10-20"),
                  age_req_s=8 * 86400, age_res_s=8 * 86400)
    sys.argv = ["watch_channels", "--canali", "dsh"]
    wc.main()
    assert len(inviati) == 1  # UN messaggio consolidato (muto + REQ vecchia)
    assert "muto" in inviati[0] and "REQ-D-20261020-001" in inviati[0]
    now = time.time()
    for nome_f in ("requests.md", "results.md"):
        p = d / nome_f
        os.utime(p, (now - 8 * 86400 - 3600, now - 8 * 86400 - 3600))
    wc.main()  # testo driftato di un'ora: chiave uguale -> niente secondo invio
    assert len(inviati) == 1


def test_main_dry_tmp(cartella, monkeypatch):
    monkeypatch.setattr(wc, "BRIDGE", cartella)
    monkeypatch.setattr(wc, "LOG", cartella / "log.txt")
    _mkcanale(cartella, "nuvola")
    sys.argv = ["watch_channels", "--canali", "nuvola", "--dry"]
    rc = wc.main()
    assert rc == 0
    assert (cartella / "log.txt").is_file()
