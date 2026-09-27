"""Persistenza atomica: lo stato sopravvive al crash, il corrotto non blocca."""
import json
import os

from money.esecuzione import stato as modulo_stato
from money.esecuzione.stato import Stato, carica, salva


def test_roundtrip(tmp_path):
    p = str(tmp_path / "stato.json")
    import time
    oggi = time.strftime("%Y-%m-%d", time.gmtime())
    s = Stato(posizioni={"BTC/EUR": {"qty": 0.001, "costo_medio": 70000.0}},
              pnl_giorno=-1.5, giorno=oggi, equity_picco=100.0)
    salva(p, s)
    s2 = carica(p)
    assert s2.posizioni["BTC/EUR"]["qty"] == 0.001
    assert s2.pnl_giorno == -1.5
    assert s2.equity_picco == 100.0


def test_file_assente_stato_vuoto_con_nota(tmp_path):
    s = carica(str(tmp_path / "non_esiste.json"))
    assert s.posizioni == {} and "file assente" in s.nota


def test_file_corrotto_non_e_un_eccezione(tmp_path):
    p = tmp_path / "stato.json"
    p.write_text("{questo non e' json", encoding="utf-8")
    s = carica(str(p))
    assert s.posizioni == {} and "illegibile" in s.nota


def test_scrittura_atomica_non_lascia_tmp(tmp_path):
    p = str(tmp_path / "stato.json")
    salva(p, Stato(equity_picco=42.0))
    assert not os.path.exists(p + ".tmp")
    with open(p, encoding="utf-8") as f:
        assert json.load(f)["equity_picco"] == 42.0


def test_rollover_giorno_azzera_pnl(tmp_path):
    p = str(tmp_path / "stato.json")
    vecchio = Stato(pnl_giorno=-9.0, giorno="2020-01-01")
    salva(p, vecchio)
    s = carica(p)
    assert s.pnl_giorno == 0.0 and s.giorno != "2020-01-01"


def test_picco_si_aggiorna_solo_verso_l_alto():
    s = Stato(equity_picco=100.0)
    s.aggiorna_picco(80.0)
    assert s.equity_picco == 100.0
    s.aggiorna_picco(120.0)
    assert s.equity_picco == 120.0
