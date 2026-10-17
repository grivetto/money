"""Fixture sintetiche P25 (2 settimane) con numeri noti e valori attesi a mano.

Settimana 1 (t-14g .. t-7g): rate 0.91→0.92, USDC 999→1000  (non rilevante per il 7g)
Settimana 2 (t-7g  .. t   ): rate 0.92→0.93, USDC 1000→1002  (finestra del KPI)

Solo comparto savings (saldi_savings.USDC, equity_savings_eur): il banco sintetico
è il più semplice possibile affinché i valori attesi siano calcolabili a mano.

Attribuzione 7g attesa (metodologia watch_alerts):
  delta  = 1002*0.93 − 1000*0.92 = 931.86 − 920 = 11.86
  cambio = (0.93−0.92) × (1000+1002)/2 = 0.01 × 1001 = 10.01
  resto  = 11.86 − 10.01 = 1.85
"""
from __future__ import annotations

import datetime
import json

T_FINE = datetime.datetime(2026, 10, 18, 9, 0, tzinfo=datetime.timezone.utc).timestamp()
SETTIMANA_S = 7 * 86400
PASSI = 2016  # campioni ogni 5' in una settimana: 7*24*12

# valori noti della settimana 2 (finestra 7g)
R0, R1 = 0.92, 0.93
U0, U1 = 1000.0, 1002.0

DELTA_ATTESO = U1 * R1 - U0 * R0          # 11.86
CAMBIO_ATTESO = (R1 - R0) * (U0 + U1) / 2  # 10.01
RESTO_ATTESO = DELTA_ATTESO - CAMBIO_ATTESO  # 1.85


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(
        ts, tz=datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def riga_banco(ts: float, usdc: float, rate: float) -> dict:
    return {"timestamp": _iso(ts),
            "equity_eur": usdc * rate,
            "equity_savings_eur": usdc * rate,
            "saldi_savings": {"USDC": usdc}}


def righe_banco_2settimane(t_fine: float = T_FINE) -> list[dict]:
    """4034 righe a 5': 2 settimane di banco sintetico (interpolazione lineare)."""
    righe = []
    for w, (r0, r1, u0, u1) in enumerate(((0.91, 0.92, 999.0, 1000.0),
                                          (R0, R1, U0, U1))):
        base = t_fine - (2 - w) * SETTIMANA_S
        for i in range(PASSI + 1):
            ts = base + i * 300
            f = i / PASSI
            righe.append(riga_banco(ts, u0 + (u1 - u0) * f, r0 + (r1 - r0) * f))
    return righe


def testo_banco_2settimane(t_fine: float = T_FINE) -> str:
    return "\n".join(json.dumps(r) for r in righe_banco_2settimane(t_fine))


# ---------------------------------------------------------------------------
# Fee ledger sintetico — valori attesi a mano (rate 0.93):
#   0.50 USDC → 0.465
#   0.00 USDC → 0.000  (fee conversione a 0: inclusa)
#   0.10 EUR  → 0.100
#   0.30 USD  → 0.279
#   0.05 BTC  → esclusa (valuta non convertibile)
#   0.40 USDC → fuori finestra (13 giorni fa)
#   somma attesa = 0.844; incluse = 4; escluse_ccy = 1; fuori_periodo = 1
# ---------------------------------------------------------------------------
FEE_SOMMA_ATTESA = 0.50 * R1 + 0.0 + 0.10 + 0.30 * R1  # 0.844


def riga_fee(ts_ms: int, fee: str, ccy: str, bill: str, **over) -> dict:
    d = {"ts": ts_ms, "instId": "BTC-EUR", "ordId": "o", "clOrdId": "c",
         "side": "buy", "fillPx": "72000", "fillSz": "0.0003",
         "fee": fee, "feeCcy": ccy, "billId": bill}
    d.update(over)
    return d


def righe_fee_7g(t_fine: float = T_FINE) -> list[dict]:
    t_ms = int(t_fine * 1000)
    return [
        riga_fee(t_ms - 1000, "0.50", "USDC", "9001"),
        riga_fee(t_ms - 2000, "0", "USDC", "9002", instId="EUR-USDC"),
        riga_fee(t_ms - 3000, "0.10", "EUR", "9003", side="sell"),
        riga_fee(t_ms - 4000, "0.30", "USD", "9004", instId="BTC-USDT"),
        riga_fee(t_ms - 5000, "0.05", "BTC", "9005", instId="DOGE-USDT"),
        riga_fee(t_ms - 13 * 86400 * 1000, "0.40", "USDC", "9000"),  # fuori finestra
    ]


def testo_fee_7g(t_fine: float = T_FINE) -> str:
    return "\n".join(json.dumps(r) for r in righe_fee_7g(t_fine))
