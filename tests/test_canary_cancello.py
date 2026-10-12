"""Test del cancello del canary (fake exchange, nessuna rete, nessun ordine).

Fissa le due invarianti del cablaggio 2026-10-12:
- senza ATR calcolabile il canary NON invia (niente stop inventato);
- un ordine oltre i limiti di rischio non parte (SystemExit, non un default).
"""
import sys
import tempfile
import types
import unittest
from pathlib import Path

# `scripts/` (dove vive canary_carry.py) — stesso pattern di test_canary_carry.
_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

_ccxt_vero = sys.modules.get("ccxt")
sys.modules["ccxt"] = types.ModuleType("ccxt")
try:
    import canary_carry  # noqa: E402
finally:
    if _ccxt_vero is not None:
        sys.modules["ccxt"] = _ccxt_vero
    else:
        sys.modules.pop("ccxt", None)


class FakeEx:
    """Exchange minimo: solo `fetch_ohlcv`, con dati fissi o assenti."""

    def __init__(self, ohlcv=None):
        self._ohlcv = ohlcv

    def fetch_ohlcv(self, symbol, timeframe="1D", limit=20):
        if self._ohlcv is None:
            raise RuntimeError("nessun dato")
        return self._ohlcv


def _barre(n=20, hi=0.105, lo=0.095, close=0.10):
    """Barre con True Range costante = hi - lo."""
    base = 1700000000000
    return [[base + i * 86400000, close, hi, lo, close, 1.0] for i in range(n)]


class TestAtr(unittest.TestCase):

    def test_atr_barre_valide(self):
        a = canary_carry.atr_ultimo(FakeEx(_barre()), "DOGE/USDC")
        self.assertAlmostEqual(a, 0.01, places=6)

    def test_atr_senza_dati_none(self):
        self.assertIsNone(canary_carry.atr_ultimo(FakeEx(None), "DOGE/USDC"))

    def test_atr_barre_insufficienti_none(self):
        self.assertIsNone(canary_carry.atr_ultimo(FakeEx(_barre(3)), "DOGE/USDC"))


class TestCancello(unittest.TestCase):

    def setUp(self):
        self._eq = canary_carry.equity_totale
        canary_carry.equity_totale = lambda *a, **k: 1000.0
        self._ev = canary_carry.EVENTS
        canary_carry.EVENTS = Path(tempfile.mkdtemp()) / "ev.jsonl"

    def tearDown(self):
        canary_carry.equity_totale = self._eq
        canary_carry.EVENTS = self._ev

    def test_cancello_ok(self):
        d = canary_carry.cancello(FakeEx(_barre()), "DOGE/USDC", "buy", 50.0, 0.10)
        self.assertTrue(d.ok)

    def test_cancello_senza_atr_aborta(self):
        with self.assertRaises(SystemExit):
            canary_carry.cancello(FakeEx(None), "DOGE/USDC", "buy", 50.0, 0.10)

    def test_cancello_rifiuta_oltre_rischio(self):
        with self.assertRaises(SystemExit):
            canary_carry.cancello(FakeEx(_barre()), "DOGE/USDC", "buy", 100000.0, 0.10)


if __name__ == "__main__":
    unittest.main()
