#!/usr/bin/env python3
"""Test del generatore cruscotto (widget "andamento progetto") — nessuna rete, nessun git.

Fissano le due cose che possono mentire in silenzio:
1. la classificazione dei verdetti del Registro (il "→" piu' il verdetto esplicito);
2. il parsing difensivo dei dati fabbrica (state.json mancante/malformato -> niente crash).
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

import cruscotto  # noqa: E402


class TestClassify(unittest.TestCase):
    """Il badge di un esperimento deve riflettere il suo verdetto, non le citazioni di altri."""

    def test_verdetto_esplicito_vince(self):
        assert cruscotto.classify(
            " verdetto **'archiviato'** (7/8 criteri KO in verifica)"
        ) == "archiviata"
        assert cruscotto.classify(
            " verdetto **'insufficiente'** (23 op < 30 minime)"
        ) == "insufficiente"

    def test_citazione_di_altro_esperimento_non_avvelena(self):
        # P14 cita P10 «insufficiente» nel preambolo, ma il SUO verdetto e' archiviato.
        rest = (
            ": seguito dichiarato di P10 («insufficiente», 23 op): stesso meccanismo "
            "su universo ampio. \u2192 MISURATA 2026-10-03: verdetto **'archiviato'**"
        )
        assert cruscotto.classify(rest) == "archiviata"

    def test_verdetti_semplici(self):
        assert cruscotto.classify(" archiviata: ipotesi smentita") == "archiviata"
        assert cruscotto.classify(" **ARCHIVIATA per costruzione**") == "archiviata"
        assert cruscotto.classify(" parcheggiata: storia funding EEA") == "parcheggiata"
        assert cruscotto.classify(" **chiusa** (2026-09-30)") == "chiusa"
        assert cruscotto.classify(" integrato 2026-09-29 (9 test)") == "integrata"
        assert cruscotto.classify(" esito DESCRITTIVA SOLIDA \u2014 H1 ...") == "descrittiva"
        assert cruscotto.classify(" **insufficiente** (campione piccolo)") == "insufficiente"
        assert cruscotto.classify(" esplorativa a 4h; esito n/d.") == "esito n/d"


class TestFabbricaDataTollerante(unittest.TestCase):
    """state.json assente o malformato non deve far esplodere il cruscotto."""

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.orig = (cruscotto.FABBRICA, cruscotto.PROVE, cruscotto.BRIDGE)
        base = Path(self.tmp.name)
        (base / "fabbrica" / "log").mkdir(parents=True)
        cruscotto.FABBRICA = base / "fabbrica"
        cruscotto.PROVE = base / "prove"
        cruscotto.BRIDGE = base / "bridge"
        cruscotto.PROVE.mkdir(parents=True)
        cruscotto.BRIDGE.mkdir(parents=True)

    def tearDown(self):
        cruscotto.FABBRICA, cruscotto.PROVE, cruscotto.BRIDGE = self.orig
        self.tmp.cleanup()

    def test_state_mancante(self):
        d = cruscotto.fabbrica_data(10_000.0)
        assert d["st"] == {}
        assert d["tick_age"] is None
        assert d["jobs"] == {}
        assert d["banco_short"] == "n/d"

    def test_state_valido_estratto(self):
        st = {
            "ticks": 100, "last_ts": "2026-10-05T22:50:08Z",
            "kill_switch": False, "a0mc2": "200", "a0win": "DOWN",
            "banco": "timer=active rc=2 ultimo=X (worker 6s)",
            "hb": {"a0win": 9_000.0},
        }
        (cruscotto.FABBRICA / "state.json").write_text(json.dumps(st))
        d = cruscotto.fabbrica_data(10_000.0)
        assert d["st"]["ticks"] == 100
        assert d["banco_short"] == "timer active \u00b7 rc=2 \u00b7 worker 6s"
        assert d["a0win_age"] == 1_000.0

    def test_registro_assente_non_crasha(self):
        sections, varianti = cruscotto.parse_registro()
        assert sections == {}
        assert varianti is None


if __name__ == "__main__":
    unittest.main()
