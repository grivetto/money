#!/usr/bin/env python3
"""scripts/misura_griglia.py — misura il nodo B: la griglia adattiva batte il pedaggio?

COSA FA, NELL'ORDINE
====================
1. Scarica (o legge dalla cache `MONEY_CACHE`) le barre 1h reali di OKX EEA per gli 8 simboli
   in EUR dichiarati a priori, e le verifica.
2. Esegue il **walk-forward** (`esegui_walk_forward`): il moltiplicatore dell'ATR e' scelto
   sulle sole finestre di addestramento e applicato a quelle di verifica, con embargo 1 barra.
   L'`Esito` contiene **solo** le operazioni di verifica.
3. Lo fa giudicare da `money.cancello.giudica(esito, capitale_riferimento=1000.0,
   soglia_eur_anno=10.0)` e stampa il verdetto **verbatim**: `esito`, `motivi`, `statistiche`.
4. Stampa i numeri esatti: n operazioni, giorni osservati, expectancy netta, IC90, t-stat,
   profit factor, max drawdown, copertura del pedaggio (rispetto a 1x e 3x), EUR/anno,
   scomposizione per blocchi.
5. Misura la **spaziatura minima** che serve perche' la griglia non lavori in perdita: una
   sweep a spaziatura FISSA sulle stesse finestre di verifica, con interpolazione del punto
   di pareggio, confrontato con il pedaggio (0,550%) e con la sua soglia 3x (1,650%).
6. Ripete tutto in modalita' `percorso="ottimista"` per **delimitare** quanto pesa l'ipotesi
   conservativa intra-barra: conservativo = limite inferiore, ottimista = superiore.
7. Chiama `confronta_tariffe(esito, "okx_eea_spot", "okx_eea_con_perp")`.
8. Quantifica il difetto noto della flotta precedente (12-25 EUR per bot, spaziatura sotto il
   pedaggio) in EUR per ciclo: perche' i PnL erano frazioni di centesimo.

Uso:  python scripts/misura_griglia.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

# Bootstrap del pacchetto: si cerca `src/` risalendo dalla posizione di questo file, cosi' lo
# script gira da un checkout appena fatto, senza installazione e senza variabili d'ambiente.
for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break
else:  # pragma: no cover - solo se il file viene spostato fuori dal progetto
    raise SystemExit("misura_griglia.py: non trovo src/money/ risalendo da "
                     f"{Path(__file__).resolve()}")

from money.cancello import confronta_tariffe, giudica, scomponi_per_regime  # noqa: E402
from money.costi import get_tariffa, movimento_minimo, operazioni_a_pareggio  # noqa: E402
from money.ricerca.griglia_adattiva import (  # noqa: E402
    CAPITALE_RIFERIMENTO,
    INIZIO,
    FINE,
    N_LIVELLI,
    SIMBOLI_CANDIDATI,
    TIMEFRAME,
    esegui_walk_forward,
    scarica_serie,
    spaziatura_di_pareggio,
    sweep_spaziatura,
)

#: Griglia della sweep di soglia. Fitta sotto il 2% (dove sta la risposta attesa), piu' larga
#: sopra, per non spendere 200 prove dove non serve. Il numero di prove e' **dichiarato** nel
#: rapporto: e' la sweep che il cancello non puo' vedere.
SPAZIATURE_SWEEP = (
    [round(0.001 * k, 4) for k in range(1, 11)]          # 0,10% .. 1,00%
    + [round(0.002 * k, 4) for k in range(6, 16)]        # 1,20% .. 3,00%
    + [round(0.005 * k, 4) for k in range(7, 15)]        # 3,50% .. 7,00%
)

#: Divisore del capitale = la lista **dichiarata** a priori, non i simboli che hanno risposto.
#: XRP/EUR non ha candele 1h su OKX EEA: il capitale per simbolo non deve salire per questo.
N_SIMBOLI_DICHIARATI = len(SIMBOLI_CANDIDATI)


def _p(valore: float, decimali: int = 4) -> str:
    """'+0,5500%' — virgola decimale, segno sempre esplicito."""
    return f"{valore * 100:+.{decimali}f}".replace(".", ",") + "%"


def _pct(valore: float, decimali: int = 4) -> str:
    return f"{valore * 100:.{decimali}f}".replace(".", ",") + "%"


def _num(valore: float, decimali: int = 3) -> str:
    return f"{valore:.{decimali}f}".replace(".", ",")


def _json(o: object) -> str:
    return json.dumps(o, indent=2, ensure_ascii=False, default=str)


def _riga_verdetto(verdetto) -> None:
    """Il verdetto VERBATIM: `esito`, `motivi` cosi' come sono, `statistiche` in JSON."""
    print("-" * 100)
    print("VERDETTO VERBATIM — money.cancello.giudica(esito, capitale_riferimento=1000.0, "
          "soglia_eur_anno=10.0)")
    print("-" * 100)
    print(f'esito = "{verdetto.esito}"')
    print("motivi:")
    if not verdetto.motivi:
        print("  (nessuno: tutti i criteri superati)")
    for motivo in verdetto.motivi:
        print("  - " + motivo)
    print("statistiche:")
    print(_json(verdetto.statistiche))


def _numeri(esito, verdetto) -> None:
    s = verdetto.statistiche
    ic = s.get("ic_bootstrap")
    ped = esito.pedaggio_per_operazione
    exp = s.get("expectancy")
    print("-" * 100)
    print("NUMERI ESATTI (tutti dall'Esito giudicato; ritorni = frazioni del nozionale di livello)")
    print("-" * 100)
    print(f"  n operazioni ................ {esito.n_operazioni}")
    print(f"  giorni osservati ............ {_num(esito.giorni_osservati, 2)}")
    print(f"  operazioni/giorno ........... {_num(esito.n_operazioni / esito.giorni_osservati, 3) if esito.giorni_osservati else 'n/d'}")
    print(f"  expectancy netta ............ {_p(exp, 4) if exp is not None else 'n/d'}")
    print(f"  IC90 bootstrap .............. "
          f"[{_p(ic[0], 4)}, {_p(ic[1], 4)}]" if ic else "  IC90 bootstrap .............. n/d")
    print(f"  t-statistic ................. "
          f"{_num(s['t_stat'], 3) if s.get('t_stat') is not None else 'n/d'}")
    pf = s.get("profit_factor")
    print(f"  profit factor ............... {_num(pf, 3) if pf is not None else 'n/d'}")
    print(f"  max drawdown ................ {_pct(esito.max_drawdown, 4)}")
    print(f"  esposizione media ........... {_pct(esito.esposizione_media, 4)} del capitale")
    print(f"  pedaggio per operazione ..... {_p(esito.pedaggio_per_operazione, 4)} "
          f"(tariffa {esito.tariffa.venue.value}, tipo {esito.tipo})")
    if exp is not None and ped > 0:
        print(f"  copertura del pedaggio ...... {_num(exp / ped, 3)}x  (1x = pareggio, "
              f"3x = soglia del criterio 6)")
        print(f"  mancano a 3x pedaggio ....... {_p(3 * ped - exp, 4)} per operazione "
              f"({_p(3 * ped, 4)} richiesti)")
    if s.get("eur_anno") is not None:
        print(f"  EUR/anno attesi ............. {_num(s['eur_anno'], 4)} EUR "
              f"(estrapolazione, capitale 1000 EUR, soglia 10 EUR)")
        g = s.get("guadagno_annuo", {})
        if g.get("disponibile"):
            print(f"  capitale per operazione ..... {_num(g['capitale_per_operazione'], 3)} EUR")
            print(f"  operazioni/anno proiettate .. {_num(g['operazioni_per_anno'], 1)}")
    print(f"  criteri del cancello ........ {s.get('criteri')}")
    print(f"  criteri falliti ............. {s.get('criteri_falliti')}")


def _blocchi(esito) -> None:
    print("-" * 100)
    print("SCOMPOSIZIONE PER BLOCCHI CONTIGUI (criterio 8) — valori LORDI, decisione al netto")
    print("-" * 100)
    for n_blocchi in (3, 4):
        sc = scomponi_per_regime(esito, n_blocchi=n_blocchi)
        print(f"  {n_blocchi} blocchi:")
        for i, (e_, n_) in enumerate(zip(sc.expectancy_per_blocco, sc.n_per_blocco), start=1):
            print(f"    blocco {i}/{len(sc.blocchi)}: {n_:>5} operazioni, expectancy lorda "
                  f"{_p(e_, 4)}")
        print(f"    -> {sc.motivo}")
    print("  Nota: i blocchi sono contigui e uniformi, non confini di regime noti. Cambiando il")
    print("  numero di blocchi l'esito del criterio puo' cambiare: e' dichiarato nel modulo.")


def _composizione(raccolta, ris_per_finestra) -> None:
    print("-" * 100)
    print("COMPOSIZIONE DELLE OPERAZIONI DI VERIFICA (cicli chiusi vs liquidazioni)")
    print("-" * 100)
    n = raccolta.esito.n_operazioni
    print(f"  cicli completati (acquisto+vendita a limite) .. {raccolta.n_cicli}"
          f"  ({_pct(raccolta.n_cicli / n, 2) if n else 'n/d'})")
    print(f"  liquidazioni (banda rotta o fine finestra) .... {raccolta.n_liquidazioni}"
          f"  ({_pct(raccolta.n_liquidazioni / n, 2) if n else 'n/d'})")
    print(f"  riancoraggi della griglia .................... {raccolta.n_riancoraggi}")
    print(f"  frazione di operazioni con spaziatura > pedaggio "
          f"{_pct(raccolta.frazione_sopra_pedaggio, 3) if raccolta.frazione_sopra_pedaggio is not None else 'n/d'}")
    print(f"  moltipli scelti sull'addestramento ........... {sorted(set(raccolta.multipli_scelti))}")
    print("  spaziatura media di verifica per simbolo:")
    for simbolo, media in raccolta.spaziature_medie.items():
        print(f"    {simbolo:<10} {_pct(media, 4) if media == media else 'n/d'}")
    print(f"  finestre di verifica ......................... {len(raccolta.dettagli_finestre)}")
    for d in raccolta.dettagli_finestre:
        exp = d["expectancy_verifica"]
        print(f"    {d['simbolo']:<10} m={d['multiplo_scelto']:<5} "
              f"n={d['n_operazioni_verifica']:>4} "
              f"exp={'n/d' if exp is None else _p(exp, 4):>9} "
              f"spaz={('n/d' if d['spaziatura_media_verifica'] is None else _pct(d['spaziatura_media_verifica'], 4)):>9}")


def _sweep(serie, pedaggio: float, percorso: str) -> list:
    print("-" * 100)
    print(f"SPAZIATURA MINIMA NECESSARIA — sweep a spaziatura FISSA, percorso {percorso}")
    print(f"({len(SPAZIATURE_SWEEP)} prove dichiarate: e' una misura di soglia, NON una "
          f"strategia promossa)")
    print("-" * 100)
    t0 = time.time()
    sweep = sweep_spaziatura(serie, spaziature=SPAZIATURE_SWEEP, percorso=percorso,
                             n_simboli_capitale=N_SIMBOLI_DICHIARATI)
    print(f"  sweep calcolata in {_num(time.time() - t0, 1)} s")
    print(f"  {'spaziatura':>11} {'/pedaggio':>10} {'n op':>7} {'cicli':>7} {'liq':>7} "
          f"{'expectancy':>12} {'copertura':>10} {'simboli+':>9}")
    for p in sweep:
        exp = p["expectancy_netta"]
        print(f"  {_pct(p['spaziatura'], 3):>11} "
              f"{_num(p['spaziatura_su_pedaggio'], 2) + 'x':>10} "
              f"{p['n_operazioni']:>7} {p['n_cicli']:>7} {p['n_liquidazioni']:>7} "
              f"{('n/d' if exp is None else _p(exp, 4)):>12} "
              f"{('n/d' if p['copertura_pedaggio'] is None else _num(p['copertura_pedaggio'], 3) + 'x'):>10} "
              f"{p['positivi_per_simbolo']:>9}")
    pareggio = spaziatura_di_pareggio(sweep, 0.0)
    soglia_3x = spaziatura_di_pareggio(sweep, 3.0 * pedaggio)
    print(f"  pedaggio (1x) ............................... {_p(pedaggio, 4)}")
    print(f"  soglia criterio 6 (3x pedaggio) ............. {_p(3 * pedaggio, 4)}")
    print(f"  SPAZIATURA DI PAREGGIO (expectancy = 0) ..... "
          f"{_p(pareggio, 4) if pareggio else 'non raggiunta nella sweep'}"
          + (f"  = {_num(pareggio / pedaggio, 2)}x il pedaggio" if pareggio else ""))
    print(f"  SPAZIATURA per 3x pedaggio .................. "
          f"{_p(soglia_3x, 4) if soglia_3x else 'non raggiunta nella sweep'}"
          + (f"  = {_num(soglia_3x / pedaggio, 2)}x il pedaggio" if soglia_3x else ""))
    return sweep


def _flotta_precedente() -> None:
    print("-" * 100)
    print("IL DIFETTO DELLA FLOTTA PRECEDENTE, IN EUR PER CICLO (12-25 EUR per bot)")
    print("-" * 100)
    tariffa = get_tariffa("okx_eea_spot")
    ped = movimento_minimo(tariffa, "misto")
    print(f"  pedaggio okx_eea_spot misto .................. {_p(ped, 4)} per ciclo")
    for nozionale in (12.0, 20.0, 25.0):
        costo = nozionale * ped
        print(f"  nozionale {_num(nozionale, 0):>4} EUR -> costo di un ciclo "
              f"{_num(costo, 4)} EUR")
        for spaz in (0.0020, 0.0035, 0.0050):
            lordo = nozionale * spaz
            print(f"      spaziatura {_pct(spaz, 2)} -> lordo {_num(lordo, 4)} EUR, "
                  f"netto {_num(lordo - costo, 4)} EUR")
    print(f"  spaziatura di pareggio con questa tariffa .... {_p(ped, 4)}")
    print(f"  ciclo da 5,35% lordo (il breakout del demo) .. "
          f"{_num(operazioni_a_pareggio(0.0535, tariffa, 'misto'), 2)} operazioni sostenibili "
          f"prima di lavorare in perdita")
    print("  -> con una spaziatura sotto il pedaggio OGNI ciclo chiude in perdita per")
    print("     costruzione: i PnL di frazioni di centesimo non erano sfortuna, erano")
    print("     aritmetica. Il capitale frammentato non e' la causa prima.")


def main() -> None:
    print("=" * 100)
    print("NODO B — GRIGLIA ADATTIVA: la spaziatura minima supera il pedaggio?")
    print("=" * 100)
    print(f"  dati        : OKX EEA (eea.okx.com), coppie EUR, timeframe {TIMEFRAME}, "
          f"{INIZIO} -> {FINE}")
    print(f"  simboli     : {', '.join(SIMBOLI_CANDIDATI)}")
    print(f"  livelli     : {N_LIVELLI} per lato; nozionale di livello "
          f"{_num(CAPITALE_RIFERIMENTO / N_SIMBOLI_DICHIARATI / N_LIVELLI, 2)} EUR "
          f"({_num(CAPITALE_RIFERIMENTO, 0)} EUR / {N_SIMBOLI_DICHIARATI} simboli dichiarati / "
          f"{N_LIVELLI} livelli)")
    print()

    t0 = time.time()
    serie = scarica_serie(SIMBOLI_CANDIDATI, timeframe=TIMEFRAME, inizio=INIZIO, fine=FINE)
    print("  barre scaricate/verificate: "
          + ", ".join(f"{k}={len(v)}" for k, v in serie.items())
          + f"  ({_num(time.time() - t0, 1)} s)")
    persi = [s for s in SIMBOLI_CANDIDATI if s not in serie]
    if persi:
        print(f"  SIMBOLI DICHIARATI SENZA DATI, SALTATI (non sostituiti): {persi}")
        print("  -> il divisore del capitale resta quello dichiarato: il capitale per simbolo")
        print("     non sale per un dato mancante. Misure su "
              f"{len(serie)} simboli su {N_SIMBOLI_DICHIARATI} dichiarati.")

    tariffa = get_tariffa("okx_eea_spot")
    pedaggio = movimento_minimo(tariffa, "misto")
    print(f"  pedaggio assunto: okx_eea_spot misto = {_p(pedaggio, 4)} per giro "
          f"(maker 0,20% + taker 0,35%)")
    print()

    # --- 1. la strategia vera: walk-forward, percorso conservativo ------------------------
    print("=" * 100)
    print("A) PERCORSO CONSERVATIVO (il verdetto si da' su questo)")
    print("=" * 100)
    t0 = time.time()
    rac_cons = esegui_walk_forward(serie, percorso="conservativo",
                                   n_simboli_capitale=N_SIMBOLI_DICHIARATI)
    print(f"  calcolato in {_num(time.time() - t0, 1)} s")
    print()
    print("  NOTE DELL'ESITO (verbatim dal campo `note`):")
    print("  " + rac_cons.esito.note)
    print()
    verdetto_cons = giudica(rac_cons.esito, capitale_riferimento=1000.0, soglia_eur_anno=10.0)
    _riga_verdetto(verdetto_cons)
    _numeri(rac_cons.esito, verdetto_cons)
    _blocchi(rac_cons.esito)
    _composizione(rac_cons, None)

    # --- 2. la misura del nodo B ----------------------------------------------------------
    sweep_cons = _sweep(serie, pedaggio, "conservativo")

    # --- 3. il limite superiore dichiarato ------------------------------------------------
    print("=" * 100)
    print("B) PERCORSO OTTIMISTA (limite SUPERIORE dichiarato: il ciclo puo' chiudersi nella")
    print("   barra in cui si apre). Serve a delimitare quanto pesa l'ipotesi conservativa.")
    print("=" * 100)
    t0 = time.time()
    rac_ott = esegui_walk_forward(serie, percorso="ottimista",
                                  n_simboli_capitale=N_SIMBOLI_DICHIARATI)
    print(f"  calcolato in {_num(time.time() - t0, 1)} s")
    verdetto_ott = giudica(rac_ott.esito, capitale_riferimento=1000.0, soglia_eur_anno=10.0)
    print(f'  esito = "{verdetto_ott.esito}"  (conservativo: "{verdetto_cons.esito}")')
    print("  motivi:")
    for motivo in verdetto_ott.motivi:
        print("    - " + motivo)
    sn, so = verdetto_cons.statistiche, verdetto_ott.statistiche
    print(f"  n operazioni    : conservativo {rac_cons.esito.n_operazioni}  "
          f"ottimista {rac_ott.esito.n_operazioni}")
    print(f"  expectancy netta: conservativo "
          f"{_p(sn['expectancy'], 4) if sn.get('expectancy') is not None else 'n/d'}  "
          f"ottimista {_p(so['expectancy'], 4) if so.get('expectancy') is not None else 'n/d'}")
    print(f"  max drawdown    : conservativo {_pct(rac_cons.esito.max_drawdown, 4)}  "
          f"ottimista {_pct(rac_ott.esito.max_drawdown, 4)}")
    print(f"  copertura       : conservativo "
          f"{_num(sn['expectancy'] / pedaggio, 3) if sn.get('expectancy') is not None else 'n/d'}x  "
          f"ottimista "
          f"{_num(so['expectancy'] / pedaggio, 3) if so.get('expectancy') is not None else 'n/d'}x")
    sweep_ott = _sweep(serie, pedaggio, "ottimista")

    # --- 4. il confronto fra tariffe ------------------------------------------------------
    print("=" * 100)
    print("C) CONFRONTO FRA TARIFFE — la stessa griglia (conservativa) con un pedaggio diverso")
    print("=" * 100)
    try:
        confronto = confronta_tariffe(rac_cons.esito, "okx_eea_spot", "okx_eea_con_perp")
        print("  " + confronto.sintesi)
        print(f"  verdetto A ({confronto.tariffa_a}): {confronto.verdetto_a.esito}")
        print(f"  verdetto B ({confronto.tariffa_b}): {confronto.verdetto_b.esito}")
        print(f"  criteri cambiati: {confronto.criteri_cambiati}")
        for etichetta, v in (("A", confronto.verdetto_a), ("B", confronto.verdetto_b)):
            s = v.statistiche
            print(f"    {etichetta}: expectancy "
                  f"{_p(s['expectancy'], 4) if s.get('expectancy') is not None else 'n/d'}, "
                  f"EUR/anno "
                  f"{_num(s['eur_anno'], 4) if s.get('eur_anno') is not None else 'n/d'}, "
                  f"criteri falliti {s.get('criteri_falliti')}")
        print(f"  pedaggio per giro: okx_eea_spot {_p(pedaggio, 4)} -> okx_eea_con_perp "
              f"{_p(movimento_minimo(get_tariffa('okx_eea_con_perp'), 'misto'), 4)}")
    except Exception as errore:  # pragma: no cover - diagnostica
        print(f"  confronta_tariffe non disponibile: {type(errore).__name__}: {errore}")

    # --- 5. il difetto della flotta precedente --------------------------------------------
    _flotta_precedente()

    # --- 6. sintesi ------------------------------------------------------------------------
    print("=" * 100)
    print("SINTESI DEL NODO B")
    print("=" * 100)
    pareggio = spaziatura_di_pareggio(sweep_cons, 0.0)
    pareggio_ott = spaziatura_di_pareggio(sweep_ott, 0.0)
    soglia_3x = spaziatura_di_pareggio(sweep_cons, 3.0 * pedaggio)
    print(f"  pedaggio di un giro (okx_eea_spot, misto) ....... {_p(pedaggio, 4)}")
    medie = [m for m in rac_cons.spaziature_medie.values() if m == m]
    print(f"  spaziatura media della griglia adattiva ......... "
          f"{_pct(math.fsum(medie) / len(medie), 4) if medie else 'n/d'} "
          f"(media delle medie per simbolo)")
    print(f"  operazioni con spaziatura > pedaggio ............ "
          f"{_pct(rac_cons.frazione_sopra_pedaggio, 3) if rac_cons.frazione_sopra_pedaggio is not None else 'n/d'}")
    print(f"  spaziatura di pareggio, percorso CONSERVATIVO ... "
          f"{_p(pareggio, 4) if pareggio else 'non raggiunta'}"
          + (f" = {_num(pareggio / pedaggio, 2)}x il pedaggio" if pareggio else ""))
    print(f"  spaziatura di pareggio, percorso OTTIMISTA ...... "
          f"{_p(pareggio_ott, 4) if pareggio_ott else 'non raggiunta'}"
          + (f" = {_num(pareggio_ott / pedaggio, 2)}x il pedaggio" if pareggio_ott else ""))
    print(f"  spaziatura per coprire 3x il pedaggio ........... "
          f"{_p(soglia_3x, 4) if soglia_3x else 'non raggiunta'}"
          + (f" = {_num(soglia_3x / pedaggio, 2)}x il pedaggio" if soglia_3x else ""))
    print("  la tesi 'basta superare il pedaggio' e' VERA come condizione necessaria e FALSA")
    print("  come condizione sufficiente: il pareggio sta sopra il pedaggio perche' ogni")
    print("  rottura della banda liquida l'inventario a mercato. La differenza fra le due")
    print("  soglie e' il costo del trend, che una spaziatura uguale al pedaggio non copre.")
    print()
    print("  ARTEFATTO JSON (per rifare i conti):")
    print(_json({
        "verdetto_conservativo": {"esito": verdetto_cons.esito, "motivi": list(verdetto_cons.motivi)},
        "verdetto_ottimista": {"esito": verdetto_ott.esito, "motivi": list(verdetto_ott.motivi)},
        "pedaggio_misto": pedaggio,
        "n_operazioni_conservativo": rac_cons.esito.n_operazioni,
        "n_operazioni_ottimista": rac_ott.esito.n_operazioni,
        "giorni_osservati": rac_cons.esito.giorni_osservati,
        "spaziatura_pareggio_conservativo": pareggio,
        "spaziatura_pareggio_ottimista": pareggio_ott,
        "spaziatura_per_3x_pedaggio": soglia_3x,
        "sweep_conservativo": sweep_cons,
        "sweep_ottimista": sweep_ott,
        "spaziature_medie_per_simbolo": rac_cons.spaziature_medie,
        "frazione_sopra_pedaggio": rac_cons.frazione_sopra_pedaggio,
    }))


if __name__ == "__main__":
    main()
