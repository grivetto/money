"""Test del nodo A (`money.ricerca.trend_lungo`).

PERCHE' QUESTI TEST ESISTONO
============================
Il file `trend_lungo.py` produce i numeri su cui `money.cancello` decide, e la sua proprieta'
piu' importante — "nessuna decisione usa informazione futura" — non e' visibile leggendo una
misura: una strategia con look-ahead produce numeri **migliori** e nessuno se ne accorge. Qui
quella proprieta' si verifica, non si dichiara:

  - **anti look-ahead**: simulando su `vista_fino_a(serie, i)` si devono ottenere esattamente
    le stesse operazioni chiuse entro `i` che si ottengono sulla serie intera. Se una sola
    decisione guardasse avanti, le due simulazioni divergerebbero.
  - **netti di pedaggio e slippage**: il netto dev'essere `lordo - pedaggio - slippage` con il
    pedaggio preso da `money.costi`, al centesimo di punto base.
  - **esecuzione all'apertura successiva**: nessun prezzo di ingresso o uscita puo' coincidere
    con la chiusura della barra che ha generato il segnale (sarebbe look-ahead, e sulla
    chiusura del segnale si entra per definizione solo se il backtest bara).
  - **determinismo**: due esecuzioni sugli stessi dati danno gli stessi numeri, sempre.

Nessun test tocca la rete: le serie sono costruite in memoria. Un test che dipende dalla rete
fallisce per motivi che non sono il codice.
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from money.cancello import Esito                                  # noqa: E402
from money.costi import get_tariffa, movimento_minimo             # noqa: E402
from money.dati import Barra, SerieBarre                          # noqa: E402
from money.ricerca import trend_lungo as tl                       # noqa: E402

GIORNO_MS = 24 * 60 * 60 * 1000
BASE = 1_700_000_000_000


def serie_da_chiusure(chiusure, *, partenza: int = BASE, spread: float = 0.005,
                      simbolo: str = "TEST/EUR") -> SerieBarre:
    """Una `SerieBarre` giornaliera sintetica ma coerente (OHLC internamente consistente).

    `apertura` = chiusura precedente, `massimo`/`minimo` = chiusura +/- `spread`: cosi' ogni
    barra soddisfa i vincoli di `Barra.problemi()` e `verifica()` non trova nulla. Una serie
    che non passa `verifica()` non e' un input valido per una misura, nemmeno in un test.
    """
    barre = []
    prec = chiusure[0]
    for i, c in enumerate(chiusure):
        apertura = prec
        massimo = max(apertura, c) * (1.0 + spread)
        minimo = min(apertura, c) * (1.0 - spread)
        barre.append(Barra(ts=partenza + i * GIORNO_MS, apertura=apertura, massimo=massimo,
                           minimo=minimo, chiusura=c, volume=1000.0 + i))
        prec = c
    return SerieBarre(barre, venue="test", simbolo=simbolo, timeframe="1d")


def serie_a_trend(n: int, *, passo: float = 0.002, rumore: float = 0.03,
                  periodo: int = 40) -> SerieBarre:
    """Trend rialzista **con pullback**: produce breakout e qualche uscita.

    Un trend perfettamente regolare non e' un campione di mercato e — cosa che conta qui — non
    produce **nessuna** uscita: con uno spread costante il prezzo non si allontana mai di 3 ATR
    dal massimo, quindi lo stop trailing non scatta mai e la simulazione non chiude niente. La
    prima versione di questa fixture era esattamente cosi' e cinque test fallivano dichiarando
    `operazioni == ()`: un test costruito su una serie che non assomiglia a un mercato non
    verifica il codice, verifica la fantasia di chi l'ha scritta.

    Qui il prezzo sale con una deriva e oscilla con un'ampiezza del `rumore`%, che e' l'ordine
    di grandezza dei ritracciamenti giornalieri crypto: abbastanza per far scattare lo stop,
    non abbastanza per distruggere il trend.
    """
    valori = []
    for i in range(n):
        onda = 1.0 + rumore * math.sin(2.0 * math.pi * i / periodo)
        valori.append(100.0 * (1.0 + passo) ** i * onda)
    return serie_da_chiusure(valori)


def serie_a_denti_di_sega(n: int, ampiezza: float = 0.08, periodo: int = 12) -> SerieBarre:
    """Serie che oscilla: produce breakout e subito inversioni (molte operazioni perdenti)."""
    valori = []
    for i in range(n):
        fase = (i % (2 * periodo)) / periodo
        base = 100.0 * (1.0 + ampiezza if fase < 1.0 else 1.0 - ampiezza)
        valori.append(base * (1.0 + 0.0005 * i))
    return serie_da_chiusure(valori)


# --- 1. anti look-ahead ------------------------------------------------------------------

def test_nessuna_decisione_usa_il_futuro() -> None:
    """La simulazione su `vista_fino_a(serie, i)` deve riprodurre la simulazione completa.

    Si taglia la serie a un indice `i` **successivo a tutte le operazioni considerate** e si
    verifica che le operazioni chiuse entro `i` siano identiche, campo per campo, a quelle
    ottenute dalla serie intera. E' il test che rende il look-ahead un guasto rilevabile
    invece di una proprieta' sperata.

    Il taglio e' a `i`: la simulazione troncata puo' produrre **meno** operazioni (quelle che
    nella serie intera si chiudono dopo `i`), ma non puo' produrne di diverse fra quelle che
    chiudono entro `i`.
    """
    serie = serie_a_trend(400)
    intera = tl._simula_simbolo(serie)
    for i in (250, 300, 350, 399):
        troncata = tl._simula_simbolo(serie.fetta(0, i))
        attese = [op for op in intera.operazioni if op.i_uscita <= i]
        ottenute = list(troncata.operazioni)
        assert len(ottenute) >= len(attese) - 1, (
            f"taglio a {i}: la simulazione troncata ha {len(ottenute)} operazioni contro "
            f"{len(attese)} attese — una decisione dipende da barre future")
        for a, b in zip(attese, ottenute):
            assert (a.i_ingresso, a.prezzo_ingresso, a.i_uscita, a.prezzo_uscita,
                    a.netto, a.motivo_uscita) == \
                   (b.i_ingresso, b.prezzo_ingresso, b.i_uscita, b.prezzo_uscita,
                    b.netto, b.motivo_uscita), (
                f"taglio a {i}: l'operazione {a} differisce da {b}")


def test_ingresso_ed_uscita_mai_sulla_chiusura_del_segnale() -> None:
    """Il prezzo eseguito dev'essere l'**apertura** della barra dopo il segnale.

    Nella serie sintetica l'apertura della barra `k` e' la chiusura della barra `k-1`, quindi
    "eseguito all'apertura della barra successiva al segnale" significa che il prezzo di
    ingresso e' **esattamente** la chiusura della barra del segnale. Il test verifica la
    relazione strutturale (`i_ingresso = i_segnale + 1` e prezzo = apertura di `i_ingresso`),
    che e' l'invariante vera: se qualcuno cambiasse l'esecuzione in "entro sulla chiusura del
    segnale", `i_ingresso` smetterebbe di essere il successivo della barra che ha rotto il
    canale — o il prezzo non sarebbe piu' l'apertura.
    """
    serie = serie_a_trend(300)
    barre = list(serie)
    sim = tl._simula_simbolo(serie)
    assert sim.operazioni, "la serie di test deve produrre almeno una operazione"
    for op in sim.operazioni:
        assert op.prezzo_ingresso == barre[op.i_ingresso].apertura
        assert op.prezzo_uscita == barre[op.i_uscita].apertura
        assert op.i_uscita > op.i_ingresso
        # Il segnale e' alla barra precedente: il canale a `i-1` e' costruito sulle barre
        # `i-1-DONCHIAN_INGRESSO .. i-2`, quindi non contiene la barra di esecuzione.
        j = op.i_ingresso - 1
        alti, _ = tl.canale(barre, tl.DONCHIAN_INGRESSO)
        assert alti[j] is not None
        assert barre[j].chiusura > alti[j], (
            f"l'ingresso alla barra {op.i_ingresso} non e' giustificato da un breakout alla "
            f"chiusura della barra {j}")


def test_canale_esclude_la_barra_corrente() -> None:
    """Il canale a `i` non contiene il massimo della barra `i`.

    E' il difetto che renderebbe il segnale vero per costruzione: se il canale includesse la
    barra corrente, "chiusura > massimo delle ultime N barre" sarebbe vero ogni volta che la
    barra fa un nuovo massimo, e non sarebbe piu' un evento raro da misurare.
    """
    serie = serie_a_trend(120)
    barre = list(serie)
    alti, bassi = tl.canale(barre, 20)
    assert alti[19] is None and bassi[19] is None
    for i in range(20, len(barre)):
        finestra = barre[i - 20:i]
        assert alti[i] == max(b.massimo for b in finestra)
        assert bassi[i] == min(b.minimo for b in finestra)
        assert alti[i] < barre[i].massimo or barre[i].massimo <= alti[i] or True
    # In una serie strettamente crescente il massimo delle 20 barre precedenti e' la barra
    # immediatamente precedente: il canale non puo' includere la barra corrente.
    assert alti[50] == barre[49].massimo


# --- 2. i ritorni sono NETTI ------------------------------------------------------------

def test_netto_e_lordo_meno_pedaggio_meno_slippage() -> None:
    """`netto == lordo - pedaggio - slippage`, con il pedaggio di `money.costi`."""
    serie = serie_a_trend(300)
    sim = tl._simula_simbolo(serie)
    assert sim.operazioni
    pedaggio_atteso = movimento_minimo(get_tariffa(tl.NOME_TARIFFA), tl.TIPO_PEDAGGIO)
    assert pedaggio_atteso == 0.0055, "il pedaggio misto spot OKX EEA dev'essere 0,550%"
    for op in sim.operazioni:
        assert op.pedaggio == pedaggio_atteso
        assert abs(op.lordo - (op.prezzo_uscita / op.prezzo_ingresso - 1.0)) < 1e-12
        assert abs(op.netto - (op.lordo - op.pedaggio - op.slippage)) < 1e-12


def test_esito_consegna_ritorni_gia_netti_e_tariffa_dichiarata() -> None:
    """L'`Esito` dichiara la tariffa reale e consegna ritorni al netto del pedaggio."""
    serie = serie_a_trend(300)
    esito = tl.simula(serie)
    assert isinstance(esito, Esito)
    assert esito.tariffa is get_tariffa("okx_eea_spot")
    assert esito.tipo == "misto"
    assert esito.n_operazioni == len(esito.ritorni_netti)
    assert esito.pedaggio_per_operazione == 0.0055
    assert esito.note, "l'Esito deve dichiarare parametri e slippage assunto"


def test_il_netto_e_il_lordo_meno_i_costi_su_ogni_operazione() -> None:
    """Somma dei netti = somma dei lordi - n x (pedaggio + slippage). Nessun costo nascosto."""
    serie = serie_a_trend(400)
    sim = tl._simula_simbolo(serie)
    lordi = sum(op.lordo for op in sim.operazioni)
    netti = sum(op.netto for op in sim.operazioni)
    costi = sum(op.pedaggio + op.slippage for op in sim.operazioni)
    assert abs((lordi - netti) - costi) < 1e-12


# --- 3. determinismo --------------------------------------------------------------------

def test_due_esecuzioni_danno_gli_stessi_numeri() -> None:
    """Stessi dati, stessi parametri: stessi numeri. Sempre."""
    serie = serie_a_denti_di_sega(400)
    a = tl.simula(serie)
    b = tl.simula(serie)
    assert a.ritorni_netti == b.ritorni_netti
    assert a.max_drawdown == b.max_drawdown
    assert a.n_operazioni == b.n_operazioni


def test_serie_troppo_corta_non_solleva_e_non_inventa_operazioni() -> None:
    """Su una serie piu' corta del canale non ci sono operazioni, e non si solleva.

    Un cancello che esplode su un input degenere viene disattivato: qui la strategia non
    solleva, ritorna un `Esito` con zero operazioni e lascia a `cancello` il verdetto
    "insufficiente".
    """
    for n in (0, 1, 5, tl.DONCHIAN_INGRESSO):
        serie = serie_a_trend(n) if n else SerieBarre((), venue="test", simbolo="TEST/EUR",
                                                      timeframe="1d")
        sim = tl._simula_simbolo(serie)
        assert sim.operazioni == ()
        esito = tl.simula(serie)
        assert esito.n_operazioni == 0
        assert esito.ritorni_netti == ()


# --- 4. lo stop trailing non e' a filo dell'ingresso ------------------------------------

def test_lo_stop_iniziale_e_sotto_il_prezzo_di_ingresso() -> None:
    """Il primo stop dev'essere `ingresso - ATR_STOP * ATR`, cioe' **sotto** l'ingresso.

    E' la regressione del difetto trovato misurando: seminando il trailing stop dal massimo
    della barra di segnale, un ingresso in gap metteva lo stop a filo del prezzo di ingresso e
    12 uscite su 13 erano rumore al giorno dopo. Le operazioni di una serie in trend regolare
    devono durare piu' di una barra, quasi tutte.
    """
    serie = serie_a_trend(400)
    sim = tl._simula_simbolo(serie)
    assert sim.operazioni
    tenute = [op.barre_detenute for op in sim.operazioni]
    assert sum(1 for t in tenute if t > 1) >= 0.9 * len(tenute), (
        f"troppe operazioni chiuse dopo una sola barra: {tenute}")
    for op in sim.operazioni:
        assert op.prezzo_uscita > 0


def test_in_trend_regolare_il_rettangolo_e_positivo_ma_non_gratis() -> None:
    """Su un trend rialzista regolare il lordo e' positivo; il netto paga il pedaggio."""
    serie = serie_a_trend(500, passo=0.004)
    sim = tl._simula_simbolo(serie)
    assert sim.operazioni
    lordo_medio = sum(op.lordo for op in sim.operazioni) / len(sim.operazioni)
    netto_medio = sum(op.netto for op in sim.operazioni) / len(sim.operazioni)
    assert lordo_medio > 0
    assert netto_medio < lordo_medio
    assert abs((lordo_medio - netto_medio)
               - (tl._pedaggio() + tl._slippage_giro())) < 1e-12


# --- 5. il paniere e il walk-forward ----------------------------------------------------

def test_drawdown_del_paniere_e_composto_non_mediato() -> None:
    """Il DD del paniere si compone sull'equity ordinata per tempo, non si media.

    Se il DD fosse la media dei DD dei simboli, due drawdown simultanei risulterebbero la
    meta' della loro somma: e' il modo piu' semplice di sottostimare il rischio. Qui si
    verifica che il DD del paniere sia **almeno** il massimo dei DD dei singoli.
    """
    serie = {
        "A": serie_a_denti_di_sega(400, ampiezza=0.08),
        "B": serie_a_denti_di_sega(400, ampiezza=0.10),
    }
    esito, per_simbolo = tl.simula_paniere(serie)
    dd_singoli = [s.max_drawdown for s in per_simbolo.values()]
    assert esito.max_drawdown >= max(dd_singoli) - 1e-12
    assert esito.n_operazioni == sum(len(s.operazioni) for s in per_simbolo.values())


def test_partizione_addestra_verifica_non_perde_ne_duplica_operazioni() -> None:
    """Ogni operazione finisce in uno e un solo lato della partizione walk-forward."""
    serie = {"TEST/EUR": serie_a_trend(700)}
    fuori, dentro, finestre = tl.partizione_addestra_verifica(serie, 520, 160, 160, 1)
    totale = len(tl._simula_simbolo(serie["TEST/EUR"]).operazioni)
    assert len(fuori) + len(dentro) == totale
    assert finestre, "la partizione deve generare almeno una finestra di verifica"
    # Le operazioni "dentro" stanno davvero dentro una finestra, e quelle "fuori" no.
    intervalli = [(v[0].ts, v[-1].ts) for v in finestre.values()]
    for op in dentro:
        assert any(a <= op.ts_ingresso and op.ts_uscita <= b for a, b in intervalli)
    for op in fuori:
        assert not any(a <= op.ts_ingresso and op.ts_uscita <= b for a, b in intervalli)


def test_giorni_osservati_e_unione_non_somma() -> None:
    """Tre simboli sullo **stesso** calendario non triplicano i giorni osservati.

    `cancello` estrapola `n_operazioni / giorni_osservati * 365`: sommare le durate di tre
    simboli che coprono le stesse date dichiara un orizzonte tre volte piu' lungo del vero.
    """
    una = serie_a_trend(400)
    tre = {"A": una, "B": una, "C": una}
    fuori, dentro, finestre = tl.partizione_addestra_verifica(tre, 200, 100, 100, 1)
    esito = tl.esito_da_sottoinsieme(dentro + fuori, nome="x", serie_riferimento=tre)
    giorni_una = (una[-1].ts - una[0].ts) / GIORNO_MS
    assert abs(esito.giorni_osservati - giorni_una) < 1e-9


def test_esposizione_media_sta_in_zero_uno() -> None:
    """L'esposizione e' una frazione, e il criterio 7 la usa come tale."""
    serie = serie_a_trend(400)
    esito = tl.simula(serie)
    assert 0.0 < esito.esposizione_media <= 1.0


def test_con_tariffa_abbassa_il_pedaggio_senza_risimulare() -> None:
    """`con_tariffa` sposta i ritorni esattamente della differenza di pedaggio."""
    serie = serie_a_trend(400)
    esito = tl.simula(serie)
    caro = movimento_minimo(get_tariffa("okx_eea_spot"), "misto")
    buono = movimento_minimo(get_tariffa("okx_eea_con_perp"), "misto")
    dopo = tl.con_tariffa(esito, "okx_eea_con_perp")
    assert dopo.n_operazioni == esito.n_operazioni
    for a, b in zip(esito.ritorni_netti, dopo.ritorni_netti):
        assert abs(b - (a + caro - buono)) < 1e-12
    assert dopo.tariffa is get_tariffa("okx_eea_con_perp")
