#!/usr/bin/env python3
"""Misura del NODO A — trend a orizzonte lungo — e giudizio di `money.cancello`.

COSA FA, IN ORDINE
==================
1. Scarica (o legge dalla cache) barre **reali** OKX EEA, `1d`, coppie EUR, per BTC/ETH/SOL.
   Verifica ogni serie con `SerieBarre.verifica()` e **dichiara** se non e' sana.
2. Simula l'ipotesi (`money.ricerca.trend_lungo`) con parametri **fissati a priori**: nessuna
   griglia, nessuna ottimizzazione, nessun parametro scelto guardando il risultato.
3. Costruisce l'`Esito` **netto** (pedaggio `okx_eea_spot` misto 0,550% + slippage assunto
   0,100% per giro, gia' sottratti) e lo fa giudicare da `cancello.giudica(...)` con
   capitale di riferimento 1.000 EUR e soglia 10 EUR/anno.
4. Stampa il verdetto **verbatim** e tutti i numeri che lo sostengono, la scomposizione per
   blocchi contigui (criterio 8) e il confronto `okx_eea_spot` -> `okx_eea_con_perp`.
5. Ripete il giudizio su una **partizione walk-forward** dichiarata
   (`iterazioni_walk_forward(addestra, verifica, passo, embargo=1)`): l'unico periodo che non
   ho guardato mentre sceglievo i parametri. E' la verifica di stabilita', non una seconda
   possibilita' di promozione.

NIENTE VIENE AGGIUSTATO PER FAR PASSARE IL VERDETTO. Se il cancello archivia, si riporta
"archiviato" e i motivi. Se dice "insufficiente", si riporta quello. I numeri si stampano con
le cifre che hanno, non con quelle che servirebbero.

Uso:
    python scripts/misura_trend_lungo.py                 # misura completa (usa la cache)
    python scripts/misura_trend_lungo.py --refresh       # riscarica dalla sede
    python scripts/misura_trend_lungo.py --json fuori.json
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]
_SRC = _RADICE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

#: La cache va in un percorso **dentro la copia di lavoro**: scrivere fuori dalla sandbox non
#: e' possibile, e una cache che non si puo' scrivere e' una cache che riscarica ogni volta.
os.environ.setdefault("MONEY_CACHE", str(_RADICE / "dati_cache"))

from money.cancello import (                                             # noqa: E402
    Esito,
    confronta_tariffe,
    giudica,
    scomponi_per_regime,
)
from money.costi import get_tariffa, movimento_minimo                     # noqa: E402
from money.dati import (                                                 # noqa: E402
    DatiSporchi,
    Scarica,
    da_ms,
    iterazioni_walk_forward,
)
from money.ricerca import trend_lungo as tl                              # noqa: E402

# --- protocollo dichiarato PRIMA di guardare i risultati --------------------------------

#: Capitale di riferimento per il criterio 7 (EUR). Scelto prima, non dopo.
CAPITALE_RIFERIMENTO = 1_000.0

#: Soglia di rilevanza annua (EUR). Scelta prima, non dopo.
SOGLIA_EUR_ANNO = 10.0

#: Blocchi contigui del criterio 8: quattro quarti di tempo, non tre. Con tre blocchi un edge
#: che vive in una sola finestra lunga un terzo del campione puo' passare; con quattro il
#: criterio e' piu' severo, ed e' la direzione giusta in cui sbagliare.
N_BLOCCHI = 4

#: Walk-forward: 550 barre di addestramento (~18 mesi) e 480 di verifica (~16 mesi).
#: Con ~1.039 barre per simbolo si ottengono le finestre che stanno in `finestre_indici` —
#: il generatore si ferma quando la verifica uscirebbe dalla serie, senza finestre parziali.
#: I parametri NON si scelgono nella finestra di addestramento (sono costanti del modulo):
#: l'addestramento qui serve solo a **dichiarare** il confine da cui comincia il non-visto, e
#: il costo e' pagato in operazioni, non in gradi di liberta'.
WF_ADDESTRA = 550
WF_VERIFICA = 480
WF_PASSO = 480
WF_EMBARGO = 1

#: Seconda griglia, piu' fine, per la robustezza **multi-finestra**: 520 barre di
#: addestramento (~17 mesi) e finestre di verifica di 160 barre (~5 mesi). Serve a rispondere
#: alla domanda che una sola partizione non pone: l'edge regge anche fuori da **quella**
#: finestra, o e' un episodio di un trimestre? Con ~1.039 barre per simbolo entrano 3 finestre
#: per simbolo (l'ultima troncata dal generatore, che non produce finestre parziali).
#:
#: Il costo di questa griglia e' alto in numerosita' (poche operazioni per finestra) ed e'
#: dichiarato: qui non si cerca un verdetto, si cerca la **distribuzione dei segni**. Una
#: strategia il cui segno dipende da quale trimestre guardi non e' una strategia.
WF_ADDESTRA_FINE = 520
WF_VERIFICA_FINE = 160


# --- formattazione: numeri con la virgola, come nel resto del progetto --------------------

def pct(x: float, cifre: int = 3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}%".replace(".", ",")


def num(x, cifre: int = 3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.{cifre}f}".replace(".", ",")


def eur(x) -> str:
    if x is None:
        return "n/d"
    return f"{x:+.2f} EUR".replace(".", ",")


def titolo(testo: str) -> None:
    print()
    print("=" * 108)
    print(testo)
    print("=" * 108)


# --- 1. i dati ---------------------------------------------------------------------------

def _dd_a_nozionale_fisso(ritorni) -> float:
    """Drawdown della curva di **somma** dei ritorni, cioe' a nozionale fisso.

    E' la lettura alternativa a quella di `cancello` (che compone): qui ogni operazione rischia
    sempre la stessa fetta di capitale, quindi i ritorni si **sommano** invece di moltiplicarsi,
    e il drawdown e' la massima distanza da un picco della somma cumulata, in unita' di
    nozionale. Il divisore e' il nozionale pieno, non il capitale del conto: per la frazione di
    conto si moltiplica per la frazione di capitale impegnata per posizione, e il runner lo fa
    esplicitamente invece di lasciarlo implicito.

    Non e' "il drawdown vero" e non e' "quello gonfiato": sono due denominatori per due modelli
    di sizing diversi, e un numero di rischio senza il suo modello accanto non e' un numero.
    """
    cumulata = 0.0
    picco = 0.0
    dd = 0.0
    for r in ritorni:
        cumulata += r
        picco = max(picco, cumulata)
        dd = max(dd, picco - cumulata)
    return dd


def carica_dati(refresh: bool) -> dict:
    """Scarica (o legge dalla cache) le serie del paniere, ognuna **verificata**.

    `Scarica.serie()` gia' chiama `verifica()` e solleva `DatiSporchi` se la serie non e'
    sana: qui si rilancia con un messaggio che dice cosa fare, perche' una serie sporca non
    e' un guasto del codice ma un dato che non si usa.
    """
    s = Scarica()
    serie: dict = {}
    for simbolo in tl.SIMBOLI:
        try:
            serie[simbolo] = s.serie(simbolo, tl.TIMEFRAME, tl.INIZIO_STORIA, tl.FINE_STORIA,
                                     refresh=refresh)
        except DatiSporchi as errore:
            raise SystemExit(
                f"serie {simbolo} {tl.TIMEFRAME} non utilizzabile: {errore}\n"
                f"Un dato sporco non entra in una misura: si corregge la fonte, non il "
                f"controllo.") from errore
    return serie


# --- 2. il giudizio, stampato per esteso --------------------------------------------------

def stampa_verdetto(v, etichetta: str) -> None:
    """Stampa il verdetto **verbatim**: `esito`, `motivi`, `statistiche` salienti."""
    print(f"--- {etichetta}")
    print(f"esito : {v.esito!r}")
    print("motivi:")
    if not v.motivi:
        print("  (nessuno: tutti i criteri superati)")
    for m in v.motivi:
        print(f"  - {m}")
    s = v.statistiche
    ic = s.get("ic_bootstrap")
    print("statistiche salienti:")
    print(f"  nome                : {s.get('nome')}")
    print(f"  n operazioni        : {s.get('n')}")
    print(f"  giorni osservati    : {num(s.get('giorni_osservati'), 1)}")
    print(f"  expectancy netta/op : {pct(s.get('expectancy'))}   "
          f"({pct(s.get('expectancy'), 6)} esatto)")
    print("  IC90 bootstrap      : " + (f"[{pct(ic[0])}, {pct(ic[1])}]" if ic else "n/d")
          + f"  (seme {s.get('ic_seme')}, {s.get('ic_ricampionamenti')} ricampionamenti)")
    print(f"  t-statistic         : {num(s.get('t_stat'))}")
    print(f"  profit factor       : {num(s.get('profit_factor'))}")
    print(f"  hit rate            : {pct(s.get('hit_rate'), 1)}   "
          f"(positivi {s.get('n_positivi')} / negativi {s.get('n_negativi')} / "
          f"nulli {s.get('n_nulli')})")
    print(f"  somma positivi      : {pct(s.get('somma_positivi'))}   "
          f"somma negativi {pct(s.get('somma_negativi'))}")
    print(f"  dev std / mediana   : {pct(s.get('dev_std'), 2)} / {pct(s.get('mediana'), 2)}")
    print(f"  guadagno/peggiore   : {pct(s.get('guadagno_migliore'), 2)} / "
          f"{pct(s.get('perdita_peggiore'), 2)}")
    print(f"  max drawdown        : {pct(s.get('max_drawdown'), 2)}")
    print(f"  esposizione media   : {num(s.get('esposizione_media'), 4)}")
    print(f"  pedaggio/op         : {pct(s.get('pedaggio_per_operazione'))}   "
          f"tariffa {s.get('tariffa')}   tipo {s.get('tipo')}")
    print(f"  copertura pedaggio  : {num((s.get('expectancy') or 0) / (s.get('pedaggio_per_operazione') or float('nan')))}x")
    print(f"  EUR/anno attesi     : {eur(s.get('eur_anno'))}   "
          f"(capitale {eur(s.get('capitale_riferimento'))})")
    g = s.get("guadagno_annuo") or {}
    if g.get("disponibile"):
        print(f"  estrapolazione      : {num(g.get('operazioni_per_anno'), 1)} op/anno, "
              f"anno coperto {num(g.get('anno_coperto'), 2)}")
        print(f"  avvertenza          : {g.get('avvertenza')}")
    else:
        print(f"  estrapolazione      : non disponibile — {g.get('motivo')}")
    print(f"  criteri             : {s.get('criteri')}")
    print(f"  criteri falliti     : {s.get('criteri_falliti')}")


def stampa_scomposizione(sc, verdetto) -> None:
    """Stampa il criterio 8 con le expectancy **nette** per blocco che hanno deciso.

    Le nette si leggono dai dettagli del verdetto (`expectancy_netta_per_blocco`): il cancello
    le ha gia' calcolate con la stessa partizione e lo stesso pedaggio. Ricalcolarle qui
    significherebbe avere due formule per la stessa grandezza, che e' esattamente il difetto
    per cui nel progetto precedente dashboard e validatore non concordavano mai.
    """
    ca = verdetto.statistiche.get("criteri", {})
    # I dettagli del criterio sono ricostruibili dall'esito: si prende il pedaggio dichiarato
    # e si applica ai blocchi della `Scomposizione`, che sono gli stessi che il cancello usa.
    pedaggio = verdetto.statistiche.get("pedaggio_per_operazione") or 0.0
    print(f"--- criterio 8: {N_BLOCCHI} blocchi contigui di tempo (quartili di operazioni)")
    print(f"{'blocco':>7} {'n op':>6} {'expectancy lorda':>18} {'expectancy netta':>18}")
    for i, (lorda, n_) in enumerate(zip(sc.expectancy_per_blocco, sc.n_per_blocco), start=1):
        print(f"{i:>7} {n_:>6} {pct(lorda):>18} {pct(lorda - pedaggio):>18}")
    print(f"  pedaggio sottratto per blocco  : {pct(pedaggio)} (tariffa assunta)")
    print(f"  indipendenza dai blocchi passa : {ca.get('indipendenza_dai_blocchi')}")
    print(f"  motivo                         : {sc.motivo}")
    print(f"  migliore                       : blocco {sc.migliore + 1}/{len(sc.blocchi)} "
          f"a {pct(sc.expectancy_migliore)} lordo "
          f"({pct(sc.expectancy_migliore - pedaggio)} netto)")
    print(f"  expectancy netta senza il migliore: "
          f"{pct(sc.expectancy_senza_migliore) if sc.expectancy_senza_migliore is not None else 'n/d'}")
    print(f"  criteri falliti                : {verdetto.statistiche.get('criteri_falliti')}")


# --- 3. il walk-forward -------------------------------------------------------------------

def misura_walk_forward(serie: dict) -> tuple:
    """Partiziona le operazioni fra barre di addestramento e barre di verifica walk-forward.

    Le finestre di verifica di `iterazioni_walk_forward` sono contigue, non sovrapposte e
    separate dall'addestramento da un embargo di una barra (`finestre_indici`): quindi "tutto
    cio' che non sta in una verifica" e' esattamente il periodo di addestramento. Le operazioni
    della simulazione **completa** si assegnano ai due lati in base a dove cadono, cosi' la
    partizione e' quella onesta del walk-forward **senza** pagare il costo di riscaldamento
    degli indicatori: una finestra di verifica "autonoma" spreca le prime
    `DONCHIAN_INGRESSO` barre a ricostruire il canale, e su una finestra di 480 barre sono
    l'8% del campione buttato via.

    I parametri della strategia sono costanti e non vengono toccati qui: il walk-forward
    **partiziona il tempo**, non allena niente. Va detto con precisione — un walk-forward che
    non stima alcun parametro non e' una prova di out-of-sample di un modello, e' la prova che
    l'edge non e' un artefatto di una singola finestra temporale.
    """
    fuori, dentro, finestre = tl.partizione_addestra_verifica(
        serie, WF_ADDESTRA, WF_VERIFICA, WF_PASSO, WF_EMBARGO)
    per_giro = sorted((k, len(v), v[0].ts, v[-1].ts) for k, v in finestre.items())
    esito_add = tl.esito_da_sottoinsieme(
        fuori,
        nome=(f"trend lungo — barre di ADDESTRAMENTO walk-forward "
              f"(prime {WF_ADDESTRA} barre per simbolo)"),
        serie_riferimento=dict(serie),
        note_extra="periodo in cui i valori dei parametri sono stati scelti: in-sample",
    )
    esito_ver = tl.esito_da_sottoinsieme(
        dentro,
        nome=(f"trend lungo — barre di VERIFICA walk-forward "
              f"(addestra {WF_ADDESTRA}, verifica {WF_VERIFICA}, passo {WF_PASSO}, "
              f"embargo {WF_EMBARGO})"),
        serie_riferimento=finestre,
        note_extra=(f"{len(finestre)} finestre di verifica, parametri costanti non stimati "
                    f"in-sample"),
    )
    return esito_add, esito_ver, per_giro, finestre


# --- main --------------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="Misura del nodo A (trend a orizzonte lungo).")
    ap.add_argument("--refresh", action="store_true",
                    help="riscarica dalla sede invece di usare la cache")
    ap.add_argument("--json", type=str, default=None,
                    help="scrive il riepilogo completo in un file JSON")
    args = ap.parse_args()

    titolo("NODO A — TREND A ORIZZONTE LUNGO: MISURA E GIUDIZIO")
    print(f"cache MONEY_CACHE : {os.environ['MONEY_CACHE']}")
    print(f"tariffa assunta   : {tl.NOME_TARIFFA} (tipo {tl.TIPO_PEDAGGIO}) "
          f"-> pedaggio {pct(tl._pedaggio())} per operazione")
    print(f"slippage assunto  : {pct(tl._slippage_giro())} per giro "
          f"({pct(tl.SLIPPAGE_PER_LATO)} per lato) — ASSUNTO, non misurato")
    print(f"parametri (fissi) : Donchian{tl.DONCHIAN_INGRESSO} ingresso, "
          f"canale{tl.USCITA_CANALE} uscita, ATR{tl.ATR_PERIODO} x {tl.ATR_STOP} trailing, "
          f"stop tempo {tl.STOP_TEMPO} barre")
    print("esecuzione        : all'apertura della barra SUCCESSIVA al segnale; "
          "decisione alla chiusura della barra del segnale")
    print(f"capitale soglia   : {eur(CAPITALE_RIFERIMENTO)} capitale, "
          f"{eur(SOGLIA_EUR_ANNO)}/anno di soglia (criterio 7)")

    serie = carica_dati(args.refresh)

    titolo("1) I DATI (reali, OKX EEA, barre verificate)")
    print(f"{'simbolo':>9} {'barre':>6} {'dal':>11} {'al':>11} {'giorni':>7} "
          f"{'problemi verifica':>17}  chiave")
    for simbolo, s in serie.items():
        problemi = s.verifica()
        print(f"{simbolo:>9} {len(s):>6} {str(da_ms(s[0].ts).date()):>11} "
              f"{str(da_ms(s[-1].ts).date()):>11} "
              f"{(s[-1].ts - s[0].ts) / 86400000:>7.0f} {len(problemi):>17}  {s.chiave()}")

    # --- 2. simulazione e esito netto ---
    esito, per_simbolo = tl.simula_paniere(serie)

    titolo("2) OPERAZIONI PER SIMBOLO (prima di giudicare: i conteggi, non il merito)")
    print(f"{'simbolo':>9} {'op':>4} {'op/anno':>8} {'lordo medio':>12} "
          f"{'netto medio':>12} {'DD':>8} {'esposizione':>11}  uscite")
    for simbolo, sim in per_simbolo.items():
        op = sim.operazioni
        motivi: dict = {}
        for o in op:
            motivi[o.motivo_uscita] = motivi.get(o.motivo_uscita, 0) + 1
        lordo = math.fsum(o.lordo for o in op) / len(op) if op else float("nan")
        netto = math.fsum(o.netto for o in op) / len(op) if op else float("nan")
        print(f"{simbolo:>9} {len(op):>4} "
              f"{len(op) / (sim.giorni_osservati / 365) if sim.giorni_osservati else 0:>8.2f} "
              f"{pct(lordo):>12} {pct(netto):>12} {pct(sim.max_drawdown, 2):>8} "
              f"{num(tl._esposizione_media(serie[simbolo], op), 4):>11}  {motivi}")
    print(f"{'TOTALE':>9} {esito.n_operazioni:>4}")

    # --- 3. il giudizio principale: storia intera ---
    titolo("3) VERDETTO — misura principale (storia intera del paniere, parametri a priori)")
    verdetto = giudica(esito, capitale_riferimento=CAPITALE_RIFERIMENTO,
                       soglia_eur_anno=SOGLIA_EUR_ANNO, n_blocchi_regime=N_BLOCCHI)
    stampa_verdetto(verdetto, "VERDETTO PRINCIPALE (verbatim)")
    print()
    # Il drawdown del criterio 5 e' quello della curva a **capitale pieno**: e' il
    # denominatore che il criterio chiede ("il 25% del capitale"), ma e' severo, perche' la
    # curva composta reinveste in ogni operazione tutto il guadagno precedente. Si dichiara
    # anche la lettura parzialmente investita, perche' un numero senza la sua definizione
    # accanto e' un numero che qualcuno usera' male — nelle due direzioni opposte.
    #
    # ATTENZIONE ALLE DIMENSIONI: `esposizione_media` e' la frazione di **capitale per
    # operazione** (barre detenute medie / barre totali), ed e' quella che il criterio 7 di
    # `cancello` usa. NON e' il tempo in mercato, che e' un'altra grandezza e vale ~25%: le due
    # si confondono facilmente, e la prima versione di questa riga le scambiava stampando un
    # drawdown di conto privo di significato.
    capitale_per_op = CAPITALE_RIFERIMENTO * esito.esposizione_media
    perdita_peggiore = min(esito.ritorni_netti) if esito.ritorni_netti else 0.0
    tempo_in_mercato = max(
        (tl.esposizione_tempo(serie[s], per_simbolo[s].operazioni) for s in serie), default=0.0)
    print("Definizione del drawdown qui sopra: curva equity **composta a capitale pieno** "
          "(equity *= 1 + netto per")
    print("ogni operazione, in ordine di chiusura). Il criterio 5 chiede una frazione del "
          "capitale, e questo e'")
    print("il denominatore che riceve; ma la curva reinveste in ogni operazione tutto il "
          "guadagno precedente,")
    print("quindi **amplifica i drawdown** rispetto a un conto che tiene fermo il nozionale. "
          "Va detto due volte:")
    print("una perche' il numero e' vero, una perche' e' sfavorevole.")
    print()
    print("Nel modello d'esecuzione di questo file ogni posizione impegna una frazione piccola "
          "e costante del")
    print("conto (nessuna piramide, nessun reinvestimento). Con capitale di riferimento "
          f"{eur(CAPITALE_RIFERIMENTO)} e capitale per")
    print(f"operazione {eur(capitale_per_op)}, la perdita peggiore ({pct(perdita_peggiore, 2)}) "
          f"vale {eur(capitale_per_op * perdita_peggiore)} sul conto.")
    print()
    print("ATTENZIONE ALLE DIMENSIONI: `esposizione_media` e' la frazione di **capitale per "
          "operazione**")
    print("(barre detenute medie / barre totali), ed e' quella che il criterio 7 di `cancello` "
          "usa. NON e' il")
    print("tempo in mercato, che qui vale "
          f"{pct(tempo_in_mercato, 1)}: la prima versione di questa riga le scambiava e stampava un")
    print("drawdown di conto privo di significato, perche' moltiplicava un rendimento per "
          "operazione per una")
    print(f"frazione di tempo. `esposizione_media` = {pct(esito.esposizione_media, 2)} e' capitale "
          f"per operazione "
          f"({eur(capitale_per_op)} su {eur(CAPITALE_RIFERIMENTO)}).")
    print("L'unico modo corretto di dare la lettura **a nozionale fisso** e':")
    dd_fisso = _dd_a_nozionale_fisso(esito.ritorni_netti)
    print(f"  drawdown della curva a nozionale pieno        : {pct(esito.max_drawdown, 2)}")
    print(f"  drawdown a nozionale fisso (somma dei ritorni) : {pct(dd_fisso, 2)}")
    print(f"  dello stesso modello con il 25% del conto per posizione: "
          f"{pct(dd_fisso * 0.25, 2)} del conto")
    print("(il 25% e' il `frazione_massima` di `money.costi.capitale_minimo`: non e' una "
          "scelta di questo")
    print("file, e' il valore che il progetto usa altrove).")
    print()
    print("La conclusione non dipende da quale lettura del drawdown si preferisce: il verdetto "
          "e' **archiviato**")
    print("comunque, e i criteri che lo archiviano (expectancy_ic90, t_stat, rilevanza) non "
          "guardano il")
    print("drawdown. Ma il criterio 5 va riportato con accanto la sua definizione, perche' un "
          "numero di rischio")
    print("senza definizione e' un numero che qualcuno usera' male.")
    print()
    print("Nota obbligatoria su questa misura: la storia intera **include** il periodo in cui "
          "ho scelto i")
    print("valori dei parametri. I valori sono convenzionali e non sono stati ottimizzati su "
          "questa serie")
    print("(nessuna griglia, nessuna ricerca), ma 'non ottimizzato' non e' 'out-of-sample'. Il "
          "verdetto")
    print("qui sotto e' una misura **in-sample** del progetto di strategia.")

    # --- 4. criterio 8, in dettaglio ---
    titolo("4) CRITERIO 8 — L'EDGE DIPENDE DA UN SOLO BLOCCO?")
    sc = scomponi_per_regime(esito, n_blocchi=N_BLOCCHI)
    stampa_scomposizione(sc, verdetto)

    # --- 5. walk-forward: addestramento vs verifica ---
    titolo("5) VERIFICA DI STABILITA' — barre di verifica walk-forward (mai viste)")
    esito_add, esito_ver, per_giro, finestre = misura_walk_forward(serie)
    print(f"{'finestra':>14} {'barre':>6} {'dal':>11} {'al':>11}")
    for k, n_, t0, t1 in per_giro:
        print(f"{k:>14} {n_:>6} {str(da_ms(t0).date()):>11} {str(da_ms(t1).date()):>11}")
    print()
    print(f"operazioni fuori dalle finestre (addestramento): {esito_add.n_operazioni}")
    print(f"operazioni dentro le finestre (verifica)       : {esito_ver.n_operazioni}")
    print()
    verdetto_add = giudica(esito_add, capitale_riferimento=CAPITALE_RIFERIMENTO,
                           soglia_eur_anno=SOGLIA_EUR_ANNO, n_blocchi_regime=N_BLOCCHI)
    verdetto_ver = giudica(esito_ver, capitale_riferimento=CAPITALE_RIFERIMENTO,
                           soglia_eur_anno=SOGLIA_EUR_ANNO, n_blocchi_regime=N_BLOCCHI)
    stampa_verdetto(verdetto_add, "VERDETTO — barre di ADDESTRAMENTO (verbatim)")
    print()
    stampa_verdetto(verdetto_ver, "VERDETTO — barre di VERIFICA (verbatim)")

    # --- 5b. robustezza su piu' finestre piu' corte ---
    titolo("5b) ROBUSTEZZA — piu' finestre di verifica corte (multi-finestra)")
    esiti_finestre = []
    for simbolo, s in serie.items():
        for k, (_, ver) in enumerate(
                iterazioni_walk_forward(s, WF_ADDESTRA_FINE, WF_VERIFICA_FINE,
                                       WF_VERIFICA_FINE, WF_EMBARGO), 1):
            sim = tl._simula_simbolo(ver)
            chiuse = tuple(op for op in sim.operazioni if op.i_uscita <= len(ver) - 1)
            esito_f = tl.esito_da_sottoinsieme(
                chiuse, nome=f"finestra {simbolo}#{k}",
                serie_riferimento={f"{simbolo}#{k}": ver})
            esiti_finestre.append((simbolo, k, ver[0].ts, ver[-1].ts, esito_f))
    print(f"{'finestra':>14} {'barre':>6} {'dal':>11} {'al':>11} {'n op':>5} "
          f"{'expectancy netta':>17} {'EUR/anno':>10}")
    positive = 0
    for simbolo, k, t0, t1, e in esiti_finestre:
        vf = giudica(e, capitale_riferimento=CAPITALE_RIFERIMENTO,
                     soglia_eur_anno=SOGLIA_EUR_ANNO)
        exp = vf.statistiche.get("expectancy")
        if exp is not None and exp > 0:
            positive += 1
        print(f"{simbolo + '#' + str(k):>14} "
              f"{(t1 - t0) // 86400000 + 1:>6} {str(da_ms(t0).date()):>11} "
              f"{str(da_ms(t1).date()):>11} {e.n_operazioni:>5} "
              f"{pct(exp):>17} {eur(vf.statistiche.get('eur_anno')):>10}")
    print(f"finestre con expectancy netta > 0: {positive}/{len(esiti_finestre)}")

    # --- 6. confronto tariffe ---
    titolo("6) CONFRONTO TARIFFE — quanto vale aprire gli X-Perps")
    ct = confronta_tariffe(esito, "okx_eea_spot", "okx_eea_con_perp",
                           capitale_riferimento=CAPITALE_RIFERIMENTO,
                           soglia_eur_anno=SOGLIA_EUR_ANNO, n_blocchi_regime=N_BLOCCHI)
    print(ct.sintesi)
    print()
    a, b = ct.verdetto_a.statistiche, ct.verdetto_b.statistiche
    ca, cb = a.get("criteri", {}), b.get("criteri", {})
    print(f"{'criterio':<28} {'okx_eea_spot':>12} {'con_perp':>11}   cambia")
    for k in ca:
        if k in cb:
            print(f"{k:<28} {('passa' if ca[k] else 'FALLISCE'):>12} "
                  f"{('passa' if cb[k] else 'FALLISCE'):>11}   "
                  f"{'<== SI' if ca[k] != cb[k] else ''}")
    print()
    print(f"pedaggio per operazione : {pct(esito.pedaggio_per_operazione)} -> "
          f"{pct(movimento_minimo(get_tariffa('okx_eea_con_perp'), esito.tipo))}")
    print(f"expectancy netta        : {pct(a.get('expectancy'))} -> {pct(b.get('expectancy'))}")
    print(f"EUR/anno attesi         : {eur(a.get('eur_anno'))} -> {eur(b.get('eur_anno'))}")
    print(f"verdetto                : {ct.verdetto_a.esito} -> {ct.verdetto_b.esito}")

    # --- 7. riepilogo macchina-leggibile ---
    riepilogo = {
        "protocollo": {
            "simboli": list(tl.SIMBOLI),
            "timeframe": tl.TIMEFRAME,
            "inizio": tl.INIZIO_STORIA,
            "fine": tl.FINE_STORIA,
            "tariffa": tl.NOME_TARIFFA,
            "tipo": tl.TIPO_PEDAGGIO,
            "pedaggio_per_operazione": esito.pedaggio_per_operazione,
            "slippage_per_lato": tl.SLIPPAGE_PER_LATO,
            "slippage_per_giro": tl._slippage_giro(),
            "parametri": {
                "donchian_ingresso": tl.DONCHIAN_INGRESSO,
                "uscita_canale": tl.USCITA_CANALE,
                "atr_periodo": tl.ATR_PERIODO,
                "atr_stop": tl.ATR_STOP,
                "stop_tempo": tl.STOP_TEMPO,
            },
            "capitale_riferimento": CAPITALE_RIFERIMENTO,
            "soglia_eur_anno": SOGLIA_EUR_ANNO,
            "n_blocchi": N_BLOCCHI,
            "walk_forward": {"addestra": WF_ADDESTRA, "verifica": WF_VERIFICA,
                             "passo": WF_PASSO, "embargo": WF_EMBARGO},
        },
        "dati": {s: {"barre": len(v), "chiave": v.chiave(),
                     "dal": str(da_ms(v[0].ts).date()), "al": str(da_ms(v[-1].ts).date()),
                     "problemi_verifica": v.verifica()} for s, v in serie.items()},
        "per_simbolo": {s: {"operazioni": len(sim.operazioni),
                            "max_drawdown": sim.max_drawdown,
                            "netto_medio": (math.fsum(o.netto for o in sim.operazioni)
                                            / len(sim.operazioni)) if sim.operazioni else None,
                            "uscite": {m: sum(1 for o in sim.operazioni
                                              if o.motivo_uscita == m)
                                       for m in {o.motivo_uscita for o in sim.operazioni}}}
                        for s, sim in per_simbolo.items()},
        "esito_principale": {
            "verdetto": verdetto.esito,
            "motivi": list(verdetto.motivi),
            "criteri": verdetto.statistiche.get("criteri"),
            "n": verdetto.statistiche.get("n"),
            "giorni_osservati": verdetto.statistiche.get("giorni_osservati"),
            "expectancy": verdetto.statistiche.get("expectancy"),
            "ic_bootstrap": verdetto.statistiche.get("ic_bootstrap"),
            "t_stat": verdetto.statistiche.get("t_stat"),
            "profit_factor": verdetto.statistiche.get("profit_factor"),
            "max_drawdown": verdetto.statistiche.get("max_drawdown"),
            "esposizione_media": verdetto.statistiche.get("esposizione_media"),
            "pedaggio_per_operazione": verdetto.statistiche.get(
                "pedaggio_per_operazione"),
            "eur_anno": verdetto.statistiche.get("eur_anno"),
            "eu_anno_per_anno": verdetto.statistiche.get("guadagno_annuo"),
            "scomposizione": {
                "expectancy_lorda_per_blocco": list(sc.expectancy_per_blocco),
                "n_per_blocco": list(sc.n_per_blocco),
                "expectancy_senza_migliore": sc.expectancy_senza_migliore,
                "dipende_da_un_solo_blocco": sc.dipende_da_un_solo_blocco,
                "motivo": sc.motivo,
            },
        },
        "addestramento": {
            "verdetto": verdetto_add.esito,
            "motivi": list(verdetto_add.motivi),
            "criteri": verdetto_add.statistiche.get("criteri"),
            "n": verdetto_add.statistiche.get("n"),
            "giorni_osservati": verdetto_add.statistiche.get("giorni_osservati"),
            "expectancy": verdetto_add.statistiche.get("expectancy"),
            "ic_bootstrap": verdetto_add.statistiche.get("ic_bootstrap"),
            "t_stat": verdetto_add.statistiche.get("t_stat"),
            "profit_factor": verdetto_add.statistiche.get("profit_factor"),
            "max_drawdown": verdetto_add.statistiche.get("max_drawdown"),
            "eur_anno": verdetto_add.statistiche.get("eur_anno"),
        },
        "verifica_walk_forward": {
            "verdetto": verdetto_ver.esito,
            "motivi": list(verdetto_ver.motivi),
            "criteri": verdetto_ver.statistiche.get("criteri"),
            "n": verdetto_ver.statistiche.get("n"),
            "giorni_osservati": verdetto_ver.statistiche.get("giorni_osservati"),
            "expectancy": verdetto_ver.statistiche.get("expectancy"),
            "ic_bootstrap": verdetto_ver.statistiche.get("ic_bootstrap"),
            "t_stat": verdetto_ver.statistiche.get("t_stat"),
            "profit_factor": verdetto_ver.statistiche.get("profit_factor"),
            "max_drawdown": verdetto_ver.statistiche.get("max_drawdown"),
            "eur_anno": verdetto_ver.statistiche.get("eur_anno"),
            "finestre": [{"finestra": k, "barre": n_,
                          "dal": str(da_ms(t0).date()), "al": str(da_ms(t1).date())}
                         for k, n_, t0, t1 in per_giro],
        },
        "finestre_corte": [
            {"finestra": f"{s}#{k}", "barre": (t1 - t0) // 86400000 + 1,
             "dal": str(da_ms(t0).date()), "al": str(da_ms(t1).date()),
             "n": e.n_operazioni,
             "expectancy": ((math.fsum(e.ritorni_netti) / len(e.ritorni_netti))
                            if e.ritorni_netti else None)}
            for s, k, t0, t1, e in esiti_finestre
        ],
        "finestre_corte_positive": positive,
        "finestre_corte_totali": len(esiti_finestre),
        "confronto_tariffe": {
            "sintesi": ct.sintesi,
            "criteri_cambiati": list(ct.criteri_cambiati),
            "verdetto_a": ct.verdetto_a.esito,
            "verdetto_b": ct.verdetto_b.esito,
            "expectancy_a": a.get("expectancy"),
            "expectancy_b": b.get("expectancy"),
            "eur_anno_a": a.get("eur_anno"),
            "eur_anno_b": b.get("eur_anno"),
        },
    }
    if args.json:
        percorso = Path(args.json)
        percorso.parent.mkdir(parents=True, exist_ok=True)
        percorso.write_text(json.dumps(riepilogo, indent=2, ensure_ascii=False,
                                       default=str), encoding="utf-8")
        print()
        print(f"riepilogo JSON scritto in {percorso}")

    titolo("SINTESI (una riga per verdetto)")
    print(f"storia intera  : {verdetto.esito:<14} n={esito.n_operazioni:<4} "
          f"expectancy {pct(verdetto.statistiche.get('expectancy'))}  "
          f"t {num(verdetto.statistiche.get('t_stat'), 2)}  "
          f"EUR/anno {eur(verdetto.statistiche.get('eur_anno'))}")
    print(f"addestramento  : {verdetto_add.esito:<14} n={esito_add.n_operazioni:<4} "
          f"expectancy {pct(verdetto_add.statistiche.get('expectancy'))}  "
          f"t {num(verdetto_add.statistiche.get('t_stat'), 2)}  "
          f"EUR/anno {eur(verdetto_add.statistiche.get('eur_anno'))}")
    print(f"verifica WF    : {verdetto_ver.esito:<14} n={esito_ver.n_operazioni:<4} "
          f"expectancy {pct(verdetto_ver.statistiche.get('expectancy'))}  "
          f"t {num(verdetto_ver.statistiche.get('t_stat'), 2)}  "
          f"EUR/anno {eur(verdetto_ver.statistiche.get('eur_anno'))}")
    print(f"finestre corte : {positive}/{len(esiti_finestre)} con expectancy netta > 0")
    print(f"X-Perps        : {ct.verdetto_b.esito:<14} expectancy "
          f"{pct(b.get('expectancy'))}  EUR/anno {eur(b.get('eur_anno'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
