"""Test del check funding di `canary_carry` (funzione pura, nessuna rete).

Retrofit 2026-10-06: il check precedente normalizzava il funding cumulato sul nozionale
A UN ISTANTE (0,1%), soglia superata per costruzione dal cumulato di pochi giorni su taglia
minima — l'ANOMALIA scattava a ogni riga di log. Ora si normalizza sui GIORNI di apertura
(tasso giornaliero implicito) con soglia 0,5%/giorno.
"""
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

# `scripts/` (dove vive canary_carry.py) — stesso pattern di test_canary_review.
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# canary_carry importa ccxt al livello di modulo; qui serve solo `anomalia_funding`.
# Si importa con uno stub e si ripristina `sys.modules` com'era: senza il ripristino
# `test_dati::test_importare_e_creare_non_importa_ccxt` ("ccxt" deve restare assente).
_ccxt_vero = sys.modules.get("ccxt")
sys.modules["ccxt"] = types.ModuleType("ccxt")
try:
    import canary_carry  # noqa: E402
finally:
    if _ccxt_vero is not None:
        sys.modules["ccxt"] = _ccxt_vero
    else:
        sys.modules.pop("ccxt", None)


class TestAnomaliaFunding(unittest.TestCase):

    def setUp(self):
        self.now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
        self.ts_open = "2026-09-30T22:43:25+00:00"   # apertura reale del canary C1

    def test_funding_tipico_del_canary_nessuna_anomalia(self):
        """Il cumulato reale (+0,016 USDC su ~10,5 USDC in ~5,6 giorni) e' plausibile."""
        r = canary_carry.anomalia_funding(0.0159769, 11, 10.0, 0.09583, self.ts_open,
                                          now=self.now)
        self.assertIsNone(r)

    def test_funding_assurdo_e_anomalia(self):
        """Un cumulato di 10 USDC su ~10,5 di nozionale in 5 giorni NON e' un carry."""
        r = canary_carry.anomalia_funding(10.0, 11, 10.0, 0.09583, self.ts_open,
                                          now=self.now)
        self.assertIsNotNone(r)
        self.assertIn("funding cum", r)
        self.assertIn("/g", r)

    def test_ts_open_mancante_il_check_tace(self):
        """Senza data di apertura non si inventano giorni: il check tace."""
        self.assertIsNone(canary_carry.anomalia_funding(0.016, 11, 10.0, 0.09583, None,
                                                        now=self.now))
        self.assertIsNone(canary_carry.anomalia_funding(0.016, 11, 10.0, 0.09583, "boh",
                                                        now=self.now))

    def test_soglia_giornaliera(self):
        """Appena sotto la soglia: nessuna anomalia. Appena sopra: anomalia."""
        giorni = 5.0
        ts_open = (self.now - timedelta(days=giorni)).isoformat()
        nozionale = 11 * 10.0 * 0.1
        sotto = canary_carry.SOGLIA_FUNDING_GIORNO * nozionale * giorni * 0.99
        sopra = canary_carry.SOGLIA_FUNDING_GIORNO * nozionale * giorni * 1.01
        self.assertIsNone(canary_carry.anomalia_funding(sotto, 11, 10.0, 0.1, ts_open,
                                                        now=self.now))
        self.assertIsNotNone(canary_carry.anomalia_funding(sopra, 11, 10.0, 0.1, ts_open,
                                                           now=self.now))

    def test_funding_negativo_usa_il_valore_assoluto(self):
        """Anche un funding molto negativo (dati rotti) va segnalato."""
        r = canary_carry.anomalia_funding(-5.0, 11, 10.0, 0.09583, self.ts_open,
                                          now=self.now)
        self.assertIsNotNone(r)


if __name__ == "__main__":
    unittest.main()
