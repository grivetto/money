"""Test offline P25 — collector fee ledger (scripts/raccogli_fee_ledger.py).

Zero rete, zero chiavi: client OKX MOCK (mai un fetch reale). Dedupe su billId,
idempotenza, errori contati, paginazione, guardia statica anti-ordini.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import raccogli_fee_ledger as racc  # noqa: E402


def fill_okx(i: int, **over) -> dict:
    d = {"instType": "SPOT", "instId": "BTC-EUR", "tradeId": str(i),
         "ordId": f"o{i}", "clOrdId": f"c{i}", "billId": str(i),
         "fillPx": "72000", "fillSz": "0.0003", "side": "buy",
         "fee": "0.50", "feeCcy": "USDC", "ts": str(1700000000000 + i)}
    d.update(over)
    return d


class MockClient:
    """Client mock: una risposta per chiamata; se esaurite, lancia (errore contato)."""

    def __init__(self, risposte):
        self.risposte = list(risposte)
        self.chiamate = []

    def privateGetTradeFillsHistory(self, params):
        self.chiamate.append(dict(params))
        if not self.risposte:
            raise RuntimeError("mock: nessuna risposta disponibile")
        return self.risposte.pop(0)


# ---------------------------------------------------------------------------
# Trasformazione fill -> riga ledger (schema fisso)
# ---------------------------------------------------------------------------

def test_trasforma_fill_schema_esatto():
    riga = racc.trasforma(fill_okx(7, fee="1.23", feeCcy="USDT"))
    assert riga is not None
    assert list(riga.keys()) == ["ts", "instId", "ordId", "clOrdId", "side",
                                 "fillPx", "fillSz", "fee", "feeCcy", "billId"]
    assert riga["billId"] == "7"
    assert riga["ts"] == "1700000000007"
    assert riga["fee"] == "1.23"
    assert riga["feeCcy"] == "USDT"


def test_trasforma_senza_billid_none():
    assert racc.trasforma({"instId": "X"}) is None
    assert racc.trasforma({"billId": ""}) is None


# ---------------------------------------------------------------------------
# Dedupe su billId + idempotenza
# ---------------------------------------------------------------------------

def _scrivi_ledger(tmp_path: Path, bills: list[str]) -> Path:
    p = tmp_path / "fee_ledger.jsonl"
    p.write_text("\n".join(json.dumps({"billId": b, "fee": "0", "feeCcy": "EUR"})
                           for b in bills) + ("\n" if bills else ""),
                 encoding="utf-8")
    return p


def test_append_dedupe_su_billid(tmp_path):
    p = _scrivi_ledger(tmp_path, ["1", "2"])
    nuove = [racc.trasforma(fill_okx(i)) for i in (2, 3, 4)]
    n, d = racc.append_ledger(p, nuove)
    assert (n, d) == (2, 1)                      # 3 e 4 nuove, 2 duplicata
    bill = racc.billid_esistenti(p)
    assert bill == {"1", "2", "3", "4"}
    assert len(p.read_text().splitlines()) == 4


def test_append_idempotente_doppio_giro(tmp_path):
    p = _scrivi_ledger(tmp_path, ["1", "2"])
    nuove = [racc.trasforma(fill_okx(i)) for i in (2, 3, 4)]
    assert racc.append_ledger(p, nuove) == (2, 1)
    assert racc.append_ledger(p, nuove) == (0, 3)  # tutto già visto
    assert len(p.read_text().splitlines()) == 4


def test_append_file_mancante_tutte_nuove(tmp_path):
    p = tmp_path / "logs" / "fee_ledger.jsonl"
    nuove = [racc.trasforma(fill_okx(i)) for i in (1, 2, 3)]
    assert racc.append_ledger(p, nuove) == (3, 0)
    assert racc.billid_esistenti(p) == {"1", "2", "3"}


def test_append_duplicati_interni_al_batch(tmp_path):
    p = _scrivi_ledger(tmp_path, [])
    nuove = [racc.trasforma(fill_okx(i)) for i in (5, 5, 6)]
    n, d = racc.append_ledger(p, nuove)
    assert (n, d) == (2, 1)
    assert len(p.read_text().splitlines()) == 2


# ---------------------------------------------------------------------------
# Fetch: errori contati, paginazione, code != 0
# ---------------------------------------------------------------------------

def test_fetch_errori_contati_senza_crash(tmp_path):
    ex = MockClient([])  # lancia su ogni chiamata
    p = _scrivi_ledger(tmp_path, [])
    n, d, e = racc.raccogli(ex, 0, 9999999999999, p)
    assert (n, d) == (0, 0)
    assert e == 2  # SPOT + FUTURES, entrambe fallite
    assert p.read_text() == ""  # nessuna scrittura


def test_fetch_code_non_zero_errore(tmp_path):
    ex = MockClient([{"code": "50001", "msg": "errore api"}])
    fills, errori = racc._fetch_fills(ex, "SPOT", 0, 9999999999999)
    assert fills == []
    assert errori == 1


def test_fetch_paginazione_100_poi_30():
    ex = MockClient([
        {"code": "0", "data": [fill_okx(i) for i in range(130, 30, -1)]},  # 100 righe
        {"code": "0", "data": [fill_okx(i) for i in range(30, 0, -1)]},   # 30 righe
    ])
    fills, errori = racc._fetch_fills(ex, "SPOT", 0, 9999999999999)
    assert errori == 0
    assert len(fills) == 130
    assert len(ex.chiamate) == 2
    assert ex.chiamate[0].get("before") is None
    assert ex.chiamate[1]["before"] == "31"  # ultimo billId del primo batch
    assert ex.chiamate[0]["instType"] == "SPOT"


def test_raccogli_dry_run_non_scrive(tmp_path):
    ex = MockClient([{"code": "0", "data": [fill_okx(1), fill_okx(2)]},
                     {"code": "0", "data": []}])
    p = _scrivi_ledger(tmp_path, ["1"])
    n, d, e = racc.raccogli(ex, 0, 9999999999999, p, dry_run=True)
    assert (n, d, e) == (1, 1, 0)
    assert racc.billid_esistenti(p) == {"1"}  # il file non è stato toccato


# ---------------------------------------------------------------------------
# env e guardie statiche (zero ordini, zero chiavi in log)
# ---------------------------------------------------------------------------

def test_carica_env(tmp_path):
    p = tmp_path / ".env"
    p.write_text("OKX_API_KEY=abc\nOKX_API_SECRET=xyz\n# commento\nPASS=fake\n",
                 encoding="utf-8")
    env = racc.carica_env(p)
    assert env == {"OKX_API_KEY": "abc", "OKX_API_SECRET": "xyz", "PASS": "fake"}


def test_statico_zero_ordini_e_zero_chiavi_in_log():
    src = (ROOT / "scripts" / "raccogli_fee_ledger.py").read_text(encoding="utf-8")
    # nessun percorso di scrittura exchange
    assert "createOrder" not in src
    assert "create_order" not in src
    assert "privatePost" not in src
    # nessuna print con segreti
    righe_print = [ln for ln in src.splitlines() if "print(" in ln]
    assert not any("SECRET" in ln or "PASSPHRASE" in ln or "API_KEY" in ln
                   for ln in righe_print)
