"""Test di `money.raccoglitore_funding` — exchange finto, niente rete, niente ccxt.

PERCHE' QUESTI TEST ESISTONO
============================
Il raccoglitore e' l'unico pezzo del progetto che scrive dati su disco in modo incrementale
(append-only): un suo difetto non si vede in un backtest, si vede sei mesi dopo quando i dati
mancano o sono doppi. Questi test bloccano i comportamenti che devono restare veri:
  1. idempotenza: rieseguire con gli stessi dati non duplica righe;
  2. il file resta valido quando l'exchange fallisce (append-only, niente corruzione);
  3. nel modulo non entra MAI un percorso d'ordine (guardia sul sorgente).

Implementazione: task P8 del nastro, consegnata da Agent Zero (v2.13, 2026-09-29) e integrata
da Hermes dopo review; questi test sono la versione adattata alle convenzioni del repo.

Convenzioni: niente `tempfile`/`tmp_path` (la sandbox nega `mkdtemp`) — si usa
`cartella_temporanea()` di `conftest`; niente rete per davvero (fixture `niente_rete`).
"""
from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from conftest import cartella_temporanea
from money.raccoglitore_funding import (
    _calcola_basis_pp,
    _normalizza_ts,
    raccogli_funding_basis,
    report_copertura,
    verifica_niente_ordini_sorgente,
)

MODULO = Path(__file__).resolve().parents[1] / "src" / "money" / "raccoglitore_funding.py"


@pytest.fixture(autouse=True)
def niente_rete(monkeypatch):
    """Blocca ogni socket: i test NON POSSONO usare la rete, non solo 'non la usano'."""

    def esplode(*args, **kwargs):
        raise AssertionError("Rete vietata nei test del raccoglitore: si usa l'exchange finto")

    monkeypatch.setattr(socket.socket, "connect", esplode)
    monkeypatch.setattr(socket.socket, "connect_ex", esplode)


class MockExchange:
    """Exchange finto per test - niente rete."""

    def __init__(self, dati_funding=None, dovrebbe_fallire=False, errore=None):
        self.id = "mock_test"
        self._dati = dati_funding or []
        self._dovrebbe_fallire = dovrebbe_fallire
        self._errore = errore or Exception("Errore di rete simulato")

    def fetch_funding_rate_history(self, simbolo, since=None, limit=None):
        if self._dovrebbe_fallire:
            raise self._errore
        return self._dati


class MockExchangeParziale:
    """Exchange che restituisce dati diversi per simboli diversi."""

    def __init__(self, mapping_dati):
        self.id = "mock_parziale"
        self._mapping = mapping_dati

    def fetch_funding_rate_history(self, simbolo, since=None, limit=None):
        return self._mapping.get(simbolo, [])


def test_a_raccolta_base():
    """(a) Raccolta base: N righe scritte, campi giusti."""
    output_path = str(cartella_temporanea("p8") / "funding.jsonl")

    mock_exchange = MockExchange(dati_funding=[
        {"timestamp": 1700000000000, "fundingRate": 0.0001, "markPrice": 50100, "indexPrice": 50000},
        {"timestamp": 1700003600000, "fundingRate": 0.0002, "markPrice": 50200, "indexPrice": 50050},
        {"timestamp": 1700007200000, "fundingRate": -0.0001, "markPrice": 49900, "indexPrice": 50000},
    ])

    risultato = raccogli_funding_basis(
        exchange=mock_exchange,
        simboli=["BTC/USDT:USDT"],
        data_inizio=1700000000000,
        data_fine=1700010000000,
        output_path=output_path,
    )

    assert risultato["scritti"] == 3, f"Attesi 3 scritti, got {risultato['scritti']}"
    assert risultato["duplicati"] == 0, f"Attesi 0 duplicati, got {risultato['duplicati']}"
    assert len(risultato["errori"]) == 0, f"Attesi 0 errori, got {risultato['errori']}"

    assert Path(output_path).exists(), "File output non creato"
    with open(output_path, "r") as f:
        righe = [json.loads(line) for line in f if line.strip()]
    assert len(righe) == 3, f"File ha {len(righe)} righe, attese 3"

    for r in righe:
        assert "simbolo" in r, "Manca campo 'simbolo'"
        assert "ts" in r, "Manca campo 'ts'"
        assert "funding" in r, "Manca campo 'funding'"
        assert "basis_pp" in r, "Manca campo 'basis_pp'"
        assert "fonte" in r, "Manca campo 'fonte'"
        assert r["simbolo"] == "BTC/USDT:USDT", f"Simbolo errato: {r['simbolo']}"
        assert isinstance(r["ts"], int), f"ts non int: {type(r['ts'])}"
        assert isinstance(r["funding"], float), f"funding non float: {type(r['funding'])}"
        assert isinstance(r["basis_pp"], float), f"basis_pp non float: {type(r['basis_pp'])}"
        assert r["fonte"] == "mock_test", f"Fonte errata: {r['fonte']}"


def test_b_idempotenza():
    """(b) Idempotenza: rieseguire con gli stessi dati non aggiunge righe."""
    output_path = str(cartella_temporanea("p8") / "funding.jsonl")

    mock_exchange = MockExchange(dati_funding=[
        {"timestamp": 1700000000000, "fundingRate": 0.0001, "markPrice": 50100, "indexPrice": 50000},
        {"timestamp": 1700003600000, "fundingRate": 0.0002, "markPrice": 50200, "indexPrice": 50050},
    ])

    risultato1 = raccogli_funding_basis(
        exchange=mock_exchange, simboli=["BTC/USDT:USDT"],
        data_inizio=1700000000000, data_fine=1700010000000, output_path=output_path,
    )
    risultato2 = raccogli_funding_basis(
        exchange=mock_exchange, simboli=["BTC/USDT:USDT"],
        data_inizio=1700000000000, data_fine=1700010000000, output_path=output_path,
    )

    assert risultato1["scritti"] == 2, f"Prima esecuzione: attesi 2, got {risultato1['scritti']}"
    assert risultato2["scritti"] == 0, f"Seconda esecuzione: attesi 0, got {risultato2['scritti']}"
    assert risultato2["duplicati"] == 2, f"Seconda esecuzione: attesi 2 duplicati, got {risultato2['duplicati']}"

    with open(output_path, "r") as f:
        righe = [json.loads(line) for line in f if line.strip()]
    assert len(righe) == 2, f"File ha {len(righe)} righe dopo seconda esecuzione, attese 2"


def test_c_overlap_parziale():
    """(c) Overlap parziale: intervallo sovrapposto -> nessun duplicato."""
    output_path = str(cartella_temporanea("p8") / "funding.jsonl")

    mock_exchange1 = MockExchange(dati_funding=[
        {"timestamp": 1700000000000, "fundingRate": 0.0001, "markPrice": 50100, "indexPrice": 50000},
        {"timestamp": 1700003600000, "fundingRate": 0.0002, "markPrice": 50200, "indexPrice": 50050},
        {"timestamp": 1700007200000, "fundingRate": 0.0003, "markPrice": 50300, "indexPrice": 50100},
    ])
    mock_exchange2 = MockExchange(dati_funding=[
        {"timestamp": 1700003600000, "fundingRate": 0.0002, "markPrice": 50200, "indexPrice": 50050},
        {"timestamp": 1700007200000, "fundingRate": 0.0003, "markPrice": 50300, "indexPrice": 50100},
        {"timestamp": 1700010800000, "fundingRate": 0.0004, "markPrice": 50400, "indexPrice": 50150},
        {"timestamp": 1700014400000, "fundingRate": 0.0005, "markPrice": 50500, "indexPrice": 50200},
    ])

    risultato1 = raccogli_funding_basis(
        exchange=mock_exchange1, simboli=["BTC/USDT:USDT"],
        data_inizio=1700000000000, data_fine=1700010000000, output_path=output_path,
    )
    risultato2 = raccogli_funding_basis(
        exchange=mock_exchange2, simboli=["BTC/USDT:USDT"],
        data_inizio=1700003600000, data_fine=1700020000000, output_path=output_path,
    )

    assert risultato1["scritti"] == 3, f"Prima: attesi 3, got {risultato1['scritti']}"
    assert risultato2["scritti"] == 2, f"Seconda: attesi 2 nuovi, got {risultato2['scritti']}"
    assert risultato2["duplicati"] == 2, f"Seconda: attesi 2 duplicati, got {risultato2['duplicati']}"

    with open(output_path, "r") as f:
        righe = [json.loads(line) for line in f if line.strip()]
    assert len(righe) == 5, f"File ha {len(righe)} righe, attese 5"

    ts_set = set(r["ts"] for r in righe)
    assert len(ts_set) == 5, f"Timestamp non unici: {len(ts_set)} unici su 5"


def test_d_report_copertura():
    """(d) Report copertura date: range richiesto vs righe presenti."""
    output_path = str(cartella_temporanea("p8") / "funding.jsonl")

    mock_exchange = MockExchangeParziale({
        "BTC/USDT:USDT": [
            {"timestamp": 1700000000000, "fundingRate": 0.0001, "markPrice": 50100, "indexPrice": 50000},
            {"timestamp": 1700003600000, "fundingRate": 0.0002, "markPrice": 50200, "indexPrice": 50050},
            {"timestamp": 1700007200000, "fundingRate": 0.0003, "markPrice": 50300, "indexPrice": 50100},
            {"timestamp": 1700010800000, "fundingRate": 0.0004, "markPrice": 50400, "indexPrice": 50150},
        ],
        "ETH/USDT:USDT": [
            {"timestamp": 1700000000000, "fundingRate": 0.0001, "markPrice": 3010, "indexPrice": 3000},
            {"timestamp": 1700003600000, "fundingRate": 0.0002, "markPrice": 3020, "indexPrice": 3005},
        ],
    })

    risultato = raccogli_funding_basis(
        exchange=mock_exchange, simboli=["BTC/USDT:USDT", "ETH/USDT:USDT"],
        data_inizio=1700000000000, data_fine=1700036000000, output_path=output_path,
    )
    assert risultato["scritti"] == 6, f"Attesi 6 scritti, got {risultato['scritti']}"

    report = report_copertura(output_path, 1700000000000, 1700036000000)

    assert report["range_richiesto"]["inizio"] == 1700000000000
    assert report["range_richiesto"]["fine"] == 1700036000000
    assert report["righe_totali"] == 6, f"Righe totali: {report['righe_totali']}"
    assert "BTC/USDT:USDT" in report["simboli"]
    assert "ETH/USDT:USDT" in report["simboli"]
    assert report["simboli"]["BTC/USDT:USDT"]["count"] == 4
    assert report["simboli"]["ETH/USDT:USDT"]["count"] == 2
    assert abs(report["copertura_pct"] - 60.0) < 0.1, f"Copertura: {report['copertura_pct']}%"


def test_e_guardia_niente_ordini():
    """(e) Guardia: scansione del sorgente -> nessuna chiamata di ordine."""
    assert verifica_niente_ordini_sorgente(str(MODULO)) is True, "Trovate chiamate di ordine nel sorgente!"


def test_f_errore_rete():
    """(f) Errore rete (exchange che solleva): il file resta valido, l'errore viene riportato."""
    output_path = str(cartella_temporanea("p8") / "funding.jsonl")

    mock_exchange = MockExchange(dovrebbe_fallire=True, errore=ConnectionError("Network unreachable"))

    risultato = raccogli_funding_basis(
        exchange=mock_exchange, simboli=["BTC/USDT:USDT"],
        data_inizio=1700000000000, data_fine=1700010000000, output_path=output_path,
    )

    assert risultato["scritti"] == 0, f"Attesi 0 scritti, got {risultato['scritti']}"
    assert len(risultato["errori"]) == 1, f"Atteso 1 errore, got {len(risultato['errori'])}"
    assert "ConnectionError" in risultato["errori"][0], f"Errore non ConnectionError: {risultato['errori']}"
    assert "Network unreachable" in risultato["errori"][0]

    if Path(output_path).exists():
        with open(output_path, "r") as f:
            contenuto = f.read().strip()
        assert contenuto == "", f"File non vuoto dopo errore: {contenuto}"


def test_extra_multi_simbolo():
    """Test extra: raccolta multi-simbolo simultanea."""
    output_path = str(cartella_temporanea("p8") / "funding.jsonl")

    mock_exchange = MockExchangeParziale({
        "BTC/USDT:USDT": [
            {"timestamp": 1700000000000, "fundingRate": 0.0001, "markPrice": 50100, "indexPrice": 50000},
        ],
        "ETH/USDT:USDT": [
            {"timestamp": 1700000000000, "fundingRate": 0.0002, "markPrice": 3010, "indexPrice": 3000},
        ],
        "SOL/USDT:USDT": [
            {"timestamp": 1700000000000, "fundingRate": 0.0003, "markPrice": 101, "indexPrice": 100},
        ],
    })

    risultato = raccogli_funding_basis(
        exchange=mock_exchange, simboli=["BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"],
        data_inizio=1700000000000, data_fine=1700010000000, output_path=output_path,
    )
    assert risultato["scritti"] == 3, f"Attesi 3, got {risultato['scritti']}"

    with open(output_path, "r") as f:
        righe = [json.loads(line) for line in f if line.strip()]
    assert len(righe) == 3
    simboli_file = set(r["simbolo"] for r in righe)
    assert simboli_file == {"BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"}


def test_extra_normalizza_ts():
    """Test helper: normalizzazione timestamp vari formati."""
    from datetime import datetime, timezone

    assert _normalizza_ts(1700000000000) == 1700000000000
    assert _normalizza_ts(1700000000000.0) == 1700000000000
    assert _normalizza_ts("2023-11-14T22:13:20+00:00") == 1700000000000
    assert _normalizza_ts("2023-11-14T22:13:20Z") == 1700000000000
    dt = datetime(2023, 11, 14, 22, 13, 20, tzinfo=timezone.utc)
    assert _normalizza_ts(dt) == 1700000000000


def test_extra_calcola_basis():
    """Test helper: calcolo basis points."""
    assert _calcola_basis_pp(100, 101) == 100.0  # 1% = 100 bp
    assert _calcola_basis_pp(100, 99) == -100.0
    assert _calcola_basis_pp(0, 100) == 0.0
    assert _calcola_basis_pp(100, 100) == 0.0
