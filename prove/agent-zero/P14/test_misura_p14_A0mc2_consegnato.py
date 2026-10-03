import unittest
from pathlib import Path
import sys
import math
from typing import Any

# Add the parent directory to sys.path to import misura_p14
sys.path.insert(0, str(Path(__file__).resolve().parent))

import misura_p14  # type: ignore


# ---------------------------------------------------------------------------
# Una dataclass minima di comodo per barre sintetiche.
#        ts incrementali MAI tutti uguali tra simboli diversi: serve per
#        i test di allineamento (_primo_ultimo, _finestra_con_storico).
# ---------------------------------------------------------------------------
class Bar:
    """Barra sintetica per test: solo ts serve agli helper del runner."""
    __slots__ = ("ts", "o", "h", "l", "c", "v")

    def __init__(self, ts: int, o: float = 1.0, h: float = 1.0,
                 l: float = 1.0, c: float = 1.0, v: float = 1.0):
        self.ts = ts
        self.o = o
        self.h = h
        self.l = l
        self.c = c
        self.v = v


# ---------------------------------------------------------------------------
# Funzione pura estratta dalla logica di eleggibilita` in `allena`.
# Serve per testare la condizione "n_operazioni >= soglia E rapporto positivo
# E NON e` la config di riferimento P10" senza dover mockare tutto.
# ---------------------------------------------------------------------------
def _config_eleggibile(r: dict, soglia: int, chiave_riferimento: str) -> bool:
    """Ritorna True se la riga `r` e` eleggibile per la selezione."""
    return (r["n_operazioni_campione"] >= soglia
            and r.get("rapporto_exp_dd") is not None
            and r["rapporto_exp_dd"] > 0
            and r["chiave"] != chiave_riferimento)


class TestMisuraP14PureFunctions(unittest.TestCase):

    # -----------------------------------------------------------------------
    # GRIGLIA
    # -----------------------------------------------------------------------
    def test_griglia_8_varianti(self):
        """GRIGLIA_ADDESTRAMENTO ha esattamente 8 varianti {k:3,5} x {L:60,120} x {R:7,14}."""
        g = misura_p14.GRIGLIA_ADDESTRAMENTO
        self.assertEqual(len(g), 8)
        # Verifica ogni combinazione
        for config in g:
            self.assertIn(config["k"], (3, 5))
            self.assertIn(config["lookback"], (60, 120))
            self.assertIn(config["ribilancio"], (7, 14))
        # Verifica che ci siano tutte e 8
        combinazioni_attese = {
            (3, 60, 7), (3, 60, 14),
            (3, 120, 7), (3, 120, 14),
            (5, 60, 7), (5, 60, 14),
            (5, 120, 7), (5, 120, 14),
        }
        combinazioni_ottenute = {(c["k"], c["lookback"], c["ribilancio"]) for c in g}
        self.assertEqual(combinazioni_ottenute, combinazioni_attese)

    # -----------------------------------------------------------------------
    # FORMATTATORI
    # -----------------------------------------------------------------------
    def test_p(self):
        self.assertEqual(misura_p14._p(0.01), "+1,000%")
        self.assertEqual(misura_p14._p(0.12345), "+12,345%")
        self.assertEqual(misura_p14._p(None), "n/d")
        self.assertEqual(misura_p14._p(float("nan")), "n/d")
        # Valori negativi
        self.assertEqual(misura_p14._p(-0.05), "-5,000%")
        self.assertEqual(misura_p14._p(0.0), "+0,000%")
        # cifre custom
        self.assertEqual(misura_p14._p(0.12345, cifre=6), "+12,345000%")

    def test_n(self):
        self.assertEqual(misura_p14._n(123.456), "123,46")
        self.assertEqual(misura_p14._n(10), "10,00")
        self.assertEqual(misura_p14._n(None), "n/d")
        self.assertEqual(misura_p14._n(float("nan")), "n/d")
        self.assertEqual(misura_p14._n(0.5, cifre=4), "0,5000")

    def test_iso(self):
        # Test con un timestamp noto: 2020-01-01 00:00:00 UTC = 1577836800000 ms
        # L'implementazione usa fromtimestamp, dobbiamo solo controllare il formato
        risultato = misura_p14._iso(1577836800000)
        # Il risultato deve essere una stringa ISO YYYY-MM-DD
        self.assertRegex(risultato, r"^\d{4}-\d{2}-\d{2}$")
        # Controllo contenuto
        self.assertEqual(risultato, "2020-01-01")

    # -----------------------------------------------------------------------
    # RIGA TABELLA
    # -----------------------------------------------------------------------
    def test_riga_tabella(self):
        """Costruzione riga artefatto su una riga nota."""
        mock_r = {
            "descrizione": "k=3_L=60_R=7",
            "eseguite": 45,
            "n_operazioni_campione": 50,
            "saltate": 5,
            "expectancy_netta": 0.005,
            "dd_portafoglio": 0.1,
            "rapporto_exp_dd": 0.05,
            "max_esposizione": 0.2,
        }
        riga = misura_p14._riga_tabella(mock_r)
        self.assertIsInstance(riga, str)
        self.assertIn("k=3_L=60_R=7", riga)
        self.assertIn("ese   45", riga.replace("\n", " "))
        self.assertIn("n>=30 si", riga)

        # Con eseguite < 30
        mock_r["eseguite"] = 25
        mock_r["n_operazioni_campione"] = 25
        riga_poca = misura_p14._riga_tabella(mock_r)
        self.assertIn("n>=30 no", riga_poca)

    # -----------------------------------------------------------------------
    # ELEGGIBILITA` (estratta da allena)
    # -----------------------------------------------------------------------
    def test_config_eleggibile(self):
        """Verifica la logica di eleggibilita` per la selezione."""
        chiave_riferimento = "k=2_L=120_R=14"
        soglia = 30

        # Caso ok
        ok = {
            "chiave": "k=3_L=60_R=7",
            "n_operazioni_campione": 35,
            "rapporto_exp_dd": 0.1,
        }
        self.assertTrue(_config_eleggibile(ok, soglia, chiave_riferimento))

        # Troppo poche operazioni
        poche_op = {**ok, "n_operazioni_campione": 25}
        self.assertFalse(_config_eleggibile(poche_op, soglia, chiave_riferimento))

        # Rapporto negativo
        rapporto_neg = {**ok, "rapporto_exp_dd": -0.1}
        self.assertFalse(_config_eleggibile(rapporto_neg, soglia, chiave_riferimento))

        # Rapporto None
        rapporto_null = {**ok, "rapporto_exp_dd": None}
        self.assertFalse(_config_eleggibile(rapporto_null, soglia, chiave_riferimento))

        # Config di riferimento P10 (non eleggibile)
        rif = {
            "chiave": chiave_riferimento,
            "n_operazioni_campione": 40,
            "rapporto_exp_dd": 0.08,
        }
        self.assertFalse(_config_eleggibile(rif, soglia, chiave_riferimento))

    # -----------------------------------------------------------------------
    # ALLINEAMENTO (usa la nostra Bar, non SerieBarre)
    # -----------------------------------------------------------------------
    def test_allinea_ts_comuni(self):
        """Allinea seleziona solo i timestamp comuni."""
        # Simboli con ts parzialmente sovrapposti
        dati = {
            "S1": [Bar(ts=100), Bar(ts=200), Bar(ts=300)],
            "S2": [Bar(ts=200), Bar(ts=300), Bar(ts=400)],
        }
        allineati, comuni = misura_p14.allinea(dati)
        self.assertIn("S1", allineati)
        self.assertIn("S2", allineati)
        self.assertEqual(comuni, [200, 300])  # solo questi sono comuni
        self.assertEqual(len(allineati["S1"]), 2)
        self.assertEqual(len(allineati["S2"]), 2)

    def test_allinea_tutti_stessi_ts(self):
        """Se tutti hanno gli stessi ts, tutto viene preservato."""
        dati = {
            "A": [Bar(ts=100), Bar(ts=200)],
            "B": [Bar(ts=100), Bar(ts=200)],
        }
        allineati, comuni = misura_p14.allinea(dati)
        self.assertEqual(comuni, [100, 200])
        self.assertEqual(len(allineati["A"]), 2)
        self.assertEqual(len(allineati["B"]), 2)

    def test_allinea_nessun_ts_comune(self):
        """Nessun ts comune -> lista vuota, dizionario con liste vuote."""
        dati = {
            "X": [Bar(ts=100)],
            "Y": [Bar(ts=200)],
        }
        allineati, comuni = misura_p14.allinea(dati)
        self.assertEqual(comuni, [])
        self.assertEqual(len(allineati["X"]), 0)
        self.assertEqual(len(allineati["Y"]), 0)

    def test_allinea_simbolo_singolo(self):
        """Un solo simbolo: tutti i suoi ts sono "comuni"."""
        dati = {"SOLO": [Bar(ts=10), Bar(ts=20), Bar(ts=30)]}
        allineati, comuni = misura_p14.allinea(dati)
        self.assertEqual(comuni, [10, 20, 30])
        self.assertEqual(len(allineati["SOLO"]), 3)

    def test_primo_ultimo(self):
        """_primo_ultimo su indice di barra."""
        dati_test = {
            "A": [Bar(ts=100), Bar(ts=200), Bar(ts=300)],
            "B": [Bar(ts=150), Bar(ts=250), Bar(ts=350)],
        }
        primo, ultimo = misura_p14._primo_ultimo(dati_test, 0, 2)
        self.assertEqual(primo, 100)
        self.assertEqual(ultimo, 350)

    def test_finestra_con_storico(self):
        """Taglia finestra con lookback correttamente."""
        # 10 barre con ts crescenti
        dati = {
            "A": [Bar(ts=i * 100) for i in range(10)],
            "B": [Bar(ts=i * 100) for i in range(10)],
        }
        # i_da=5, i_a=9, lookback=3 : finestra attesa [2, 9], offset = 5 - 2 = 3
        finestra, offset = misura_p14._finestra_con_storico(dati, 5, 9, 3)
        self.assertEqual(offset, 3)
        self.assertEqual(len(finestra["A"]), 8)  # indici 2..9
        self.assertEqual(finestra["A"][0].ts, 200)  # primo = indice 2

    def test_finestra_zero_lookback(self):
        """Lookback = 0: la finestra inizia da i_da."""
        dati = {"A": [Bar(ts=i * 100) for i in range(10)]}
        finestra, offset = misura_p14._finestra_con_storico(dati, 3, 7, 0)
        self.assertEqual(offset, 0)
        self.assertEqual(len(finestra["A"]), 5)  # indici 3..7
        self.assertEqual(finestra["A"][0].ts, 300)


if __name__ == "__main__":
    unittest.main()
