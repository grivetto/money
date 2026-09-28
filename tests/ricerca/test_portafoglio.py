"""Test del motore di portafoglio — il fix della falla strutturale (2026-09-29).

La curva serializzata (`equity *= (1 + r * esposizione)` per trade, uno alla volta) non
e' un conto: e' una sequenza. Questi test bloccano per costruzione le proprieta' che il
conto vero ha e la sequenza no: posizioni concorrenti, mark-to-market, vincolo di cassa.
"""
import pytest

from money.dati import Barra
from money.ricerca.portafoglio import backtest_portafoglio

T0 = 1_700_000_000_000
PASSO = 86_400_000


def barre(piazze, ts0=T0):
    """piazze: lista di tuple (apertura, chiusura)."""
    return [Barra(ts0 + i * PASSO, a, max(a, c), min(a, c), c, 1000.0)
            for i, (a, c) in enumerate(piazze)]


class Op:
    """Operazione minimale: gli stessi campi che usa il motore."""

    def __init__(self, ts_ingresso, ts_uscita, prezzo_ingresso, prezzo_uscita):
        self.ts_ingresso = ts_ingresso
        self.ts_uscita = ts_uscita
        self.prezzo_ingresso = prezzo_ingresso
        self.prezzo_uscita = prezzo_uscita


def identico(lordo):
    return lordo


def test_due_trade_non_sovrapposti_uguali_al_serializzato():
    # Due trade sequenziali, entrambi +10%: il portafoglio deve comporre come il
    # modello serializzato (1 + 0.25*0.10)^2 — nessuna differenza quando non c'e'
    # concorrenza e nessun dip intra-trade.
    x = barre([(100, 100), (100, 100), (100, 100), (110, 110), (110, 110),
               (100, 100), (100, 100), (110, 110), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 3 * PASSO, 100.0, 110.0),
                 Op(T0 + 5 * PASSO, T0 + 7 * PASSO, 100.0, 110.0)]}
    esito = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    atteso = 1000.0 * (1 + 0.25 * 0.10) ** 2
    assert esito.capitale_finale == pytest.approx(atteso, rel=1e-9)
    assert esito.max_drawdown == pytest.approx(0.0, abs=1e-12)
    assert esito.operazioni_eseguite == 2
    assert esito.operazioni_saltate == 0


def test_mtm_vede_il_drawdown_dentro_il_trade():
    # Il trade chiude in guadagno (+10%), ma la curva ha visto il dip a 80: il
    # modello serializzato questo non lo vede, il conto vero si'.
    x = barre([(100, 100), (100, 100), (100, 80), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 3 * PASSO, 100.0, 110.0)]}
    esito = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    assert esito.capitale_finale == pytest.approx(1025.0, rel=1e-9)
    assert esito.max_drawdown == pytest.approx(0.05, rel=1e-9)


def test_esposizione_aggregata_riportata():
    # 4 simboli entrano lo stesso giorno al 25%: esposizione aggregata = 100%.
    simboli = ["A", "B", "C", "D"]
    serie = {s: barre([(100, 100)] * 6) for s in simboli}
    ops = {s: [Op(T0 + 1 * PASSO, T0 + 5 * PASSO, 100.0, 100.0)] for s in simboli}
    esito = backtest_portafoglio(serie, ops, esposizione=0.25, netto_fn=identico)
    assert esito.max_esposizione == pytest.approx(1.0, rel=1e-9)
    assert esito.max_posizioni == 4
    assert esito.operazioni_eseguite == 4


def test_cassa_esaurita_salta_e_conta():
    # 5 segnali lo stesso giorno al 25%: solo 4 trovano cassa, il quinto e' saltato
    # e CONTATO — un segnale perso non deve mai sparire in silenzio.
    simboli = ["A", "B", "C", "D", "E"]
    serie = {s: barre([(100, 100)] * 6) for s in simboli}
    ops = {s: [Op(T0 + 1 * PASSO, T0 + 5 * PASSO, 100.0, 100.0)] for s in simboli}
    esito = backtest_portafoglio(serie, ops, esposizione=0.25, netto_fn=identico)
    assert esito.operazioni_eseguite == 4
    assert esito.operazioni_saltate == 1
    assert esito.max_posizioni == 4


def test_tetto_posizioni_concorrenti():
    simboli = ["A", "B", "C"]
    serie = {s: barre([(100, 100)] * 6) for s in simboli}
    ops = {s: [Op(T0 + 1 * PASSO, T0 + 5 * PASSO, 100.0, 100.0)] for s in simboli}
    esito = backtest_portafoglio(serie, ops, esposizione=0.25, netto_fn=identico,
                                 max_posizioni=2)
    assert esito.max_posizioni == 2
    assert esito.operazioni_saltate == 1


def test_costi_applicati_alla_chiusura():
    x = barre([(100, 100), (100, 100), (110, 110), (110, 110)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 2 * PASSO, 100.0, 110.0)]}
    senza = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    con = backtest_portafoglio({"X": x}, ops, esposizione=0.25,
                               netto_fn=lambda r: r - 0.01)
    assert con.capitale_finale < senza.capitale_finale
    assert con.capitale_finale == pytest.approx(1000.0 + 250.0 * (0.10 - 0.01), rel=1e-9)


def test_determinismo():
    x = barre([(100, 100), (100, 105), (105, 110), (110, 108), (108, 112)])
    ops = {"X": [Op(T0 + 1 * PASSO, T0 + 4 * PASSO, 100.0, 108.0)]}
    a = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    b = backtest_portafoglio({"X": x}, ops, esposizione=0.25, netto_fn=identico)
    assert a == b


def test_serie_vuota_non_esplode():
    esito = backtest_portafoglio({}, {}, esposizione=0.25, netto_fn=identico)
    assert esito.capitale_finale == 1000.0
    assert esito.operazioni_eseguite == 0
    assert esito.curva == ()
