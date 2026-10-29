#!/usr/bin/env python3
"""P34 review (Artù, 29/10) — riproduzione del difetto multi-riga di lettura_saldi_reali.

Uso:  python p34_review_multiriga.py [root-repo]
      root-repo = checkout del codice da provare (default: directory corrente).
      - sul codice PRE-fix il delta stampato è +253.4586036 (BUG: una sola riga letta);
      - sul codice POST-fix il delta è +0.4586036 (due righe aggregate).

Fixture reale: prove/p34_fixture_multiriga_20261029.json (stato exchange 29/10 ~15:50 UTC).
"""
import json
import sys
from pathlib import Path

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
sys.path.insert(0, str(ROOT / "src"))

from money.recon_carry import delta_qty, lettura_saldi_reali  # noqa: E402

FIXTURE = Path(__file__).with_name("p34_fixture_multiriga_20261029.json")
fx = json.loads(FIXTURE.read_text(encoding="utf-8"))
ROWS = fx["exchange_rows_dot"]
ATTESO = fx["attesi_aggregati_post_fix"]


class FakeEx:
    def fetch_balance(self):
        return {"total": {"DOT": fx["fetch_balance_total_DOT"]}}

    def fetch_positions(self, symbols=None):
        return [dict(r) for r in ROWS]

    def fetch_ticker(self, symbol):
        return {"last": 1.0}


r = lettura_saldi_reali(FakeEx(), nome="DOT", sym_perp="DOT/USD:USD-310808",
                        sym_spot="DOT/USDC", ct_val=1.0)
d = delta_qty(r.qty_spot, r.ct_perp, 1.0)
esito = "POST-FIX OK" if abs(d - ATTESO["delta_q"]) < 1e-9 else "PRE-FIX (difetto riprodotto)"
print(f"ct_perp={r.ct_perp}  uPL={r.upl_usdc}  liq={r.liq_px}  delta_q={d}  -> {esito}")
print(f"attesi: ct={ATTESO['ct_perp']} uPL={ATTESO['upl_usdc']} liq={ATTESO['liq_px']} delta_q={ATTESO['delta_q']}")
sys.exit(0 if esito == "POST-FIX OK" else 1)
