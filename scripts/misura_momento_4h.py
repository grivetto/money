#!/usr/bin/env python3
"""Misura del nodo C — il momento a 4 ore, e il confronto con lo stesso segnale a 1 giorno.

COSA FA, IN ORDINE
==================
1. Carica le barre reali da OKX EEA (`eea.okx.com`) per l'universo dichiarato, su `4h` e `1d`,
   dalla cache locale (`MONEY_CACHE`) o dalla rete se la cache non copre.
2. **Addestramento**: prova TUTTE le configurazioni di `GRIGLIA_ADDESTRAMENTO` (8) sulle sole
   barre fino a `CONFINE_ADDESTRAMENTO`, e sceglie quella con l'expectancy netta piu' alta.
   La tabella completa viene stampata: il numero di tentativi e' un dato del risultato, non
   una nota a pie' di pagina.
3. **Verifica**: applica la configurazione scelta alle barre da `CONFINE_ADDESTRAMENTO` in poi,
   con la barra di confine **esclusa dall'addestramento e inclusa nella verifica** (embargo: la
   prima decisione in verifica usa `canale` barre interamente dentro la verifica).
4. Stessa cosa con la stessa configurazione sulle barre `1d`, per misurare il moltiplicatore
   delle occasioni che la tesi del nodo C afferma (~8x).
5. `cancello.giudica(esito, capitale_riferimento=1000.0, soglia_eur_anno=10.0)` su 4h e su 1d,
   piu' `confronta_tariffe` verso `okx_eea_con_perp` e `okx_eea_swap_lv1`.
6. Sensibilita' allo slippage assunto (0 / 0,02% / 0,04% / 0,10% per lato) e robustezza
   sull'universo allargato.

COSA NON FA
===========
Non ottimizza "un po' meglio" quando il verdetto non passa: se il cancello archivia, questo
script stampa l'archiviazione e i motivi, e i numeri restano quelli. Nessun parametro viene
scelto guardando la finestra di verifica.

Uso:
    set MONEY_CACHE=...\\cache_momento
    python scripts/misura_momento_4h.py
"""
from __future__ import annotations

import json
import math
import sys
import time
from pathlib import Path

# --- bootstrap del pacchetto: `src/` risalendo dalla posizione di questo file --------------
for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        break
else:  # pragma: no cover
    raise SystemExit("misura_momento_4h.py: non trovo src/money/ risalendo da "
                     f"{Path(__file__).resolve()}")

from money.cancello import confronta_tariffe, giudica, scomponi_per_regime  # noqa: E402
from money.costi import get_tariffa, movimento_minimo  # noqa: E402
from money.dati import Scarica, a_ms  # noqa: E402
from money.ricerca import momento_4h as M  # noqa: E402

# --- parametri del giudizio, scelti PRIMA di vedere i risultati ---------------------------
CAPITALE_RIFERIMENTO = 1000.0
SOGLIA_EUR_ANNO = 10.0
TIMEFRAME_PRIMARIO = "4h"
TIMEFRAME_CONFRONTO = "1d"
CARTELLA_RISULTATI = Path(__file__).resolve().parents[1] / "risultati"
TARIFFE_SCENARIO = ("okx_eea_con_perp", "okx_eea_swap_lv1")
SLIPPAGE_SENSIBILITA = (0.0, 0.0002, 0.0004, 0.0010)


def _p(x, cifre=3) -> str:
    """Percentuale con virgola decimale e segno esplicito: '+0,450%'."""
    if x is None:
        return "n/d"
    return f"{x * 100:+.{cifre}f}".replace(".", ",") + "%"


def _n(x, cifre=3) -> str:
    if x is None:
        return "n/d"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.{cifre}f}".replace(".", ",")


def _e(x) -> str:
    return "n/d" if x is None else f"{x:.2f}".replace(".", ",") + " EUR"


def _num(x, cifre=3) -> str:
    """Numero puro (t-statistic, copertura in multipli): **non** una percentuale.

    Esiste separato da `_p` perche' un t-statistic stampato come '-68,296%' invece di '-0,683'
    e' un errore di lettura, non di calcolo: e' il tipo di svista che il progetto precedente
    pagava con dashboard e validatore che non concordavano.
    """
    if x is None:
        return "n/d"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.{cifre}f}".replace(".", ",")


def _titolo(testo: str, larghezza: int = 100) -> None:
    print("\n" + "=" * larghezza)
    print(testo)
    print("=" * larghezza)


def carica(scaricatore: Scarica, simboli, timeframe: str) -> dict:
    """Carica `{simbolo: SerieBarre}` scartando i simboli con copertura insufficiente.

    La copertura si verifica sui **timestamp reali** (`copertura_barre`), non sulla presenza
    del file di cache: una serie con meta' delle barre mancanti e' peggio di una serie assente,
    perche' produce operazioni che sembrano valide e confronti fra simboli che non lo sono.
    """
    fuori: dict = {}
    for simbolo in simboli:
        try:
            serie = scaricatore.serie(simbolo, timeframe, M.INIZIO_STORIA, M.FINE_STORIA)
        except Exception as errore:                       # DatiSporchi o rete: si dichiara
            print(f"  ! {simbolo:10} {timeframe}: {type(errore).__name__} "
                  f"{str(errore)[:70]}")
            continue
        copertura = M.copertura_barre(serie)
        if copertura < M.COPERTURA_MINIMA:
            print(f"  - {simbolo:10} {timeframe}: copertura {copertura:.1%} < "
                  f"{M.COPERTURA_MINIMA:.0%}, escluso")
            continue
        problemi = serie.verifica()
        if problemi:
            print(f"  ! {simbolo:10} {timeframe}: {len(problemi)} problemi di verifica, escluso")
            continue
        fuori[simbolo] = serie
        print(f"  + {simbolo:10} {timeframe}: {len(serie):5} barre, copertura {copertura:.1%}, "
              f"da {serie.prima.ts} a {serie.ultima.ts}")
    return fuori


def prima_dopo(serie_per_simbolo: dict, istante_iso: str):
    """Primo indice la cui barra **apre** a `istante_iso` o dopo, calcolato sulla serie piu'
    lunga (la partizione dev'essere la stessa per tutti i simboli, e prendere la piu' lunga
    evita di escludere barre che esistono).

    Cosa garantisce, detto con precisione: l'addestramento usa gli indici `0..i-1` e la verifica
    `i..fine`, quindi **nessun ritorno di un'operazione di verifica entra nell'addestramento**,
    e le due finestre non condividono nessuna barra in quanto periodi.

    Cosa **non** garantisce, e va detto invece di nasconderlo: la prima decisione in verifica
    legge un canale di `canale` barre che stanno, in parte, dentro l'addestramento (indici
    `i-canale .. i-1`). Non e' leakage: sono prezzi **passati**, che in produzione sarebbero
    disponibili esattamente allo stesso modo, e il canale non contiene nessuna etichetta ne'
    nessun rendimento futuro. E' pero' vero che le prime `canale` barre di verifica non sono
    indipendenti dall'addestramento, e chi legge i numeri deve saperlo.
    """
    limite = a_ms(istante_iso)
    riferimenti = [serie for serie in serie_per_simbolo.values()]
    if not riferimenti:
        raise ValueError("nessuna serie caricata: non c'e' finestra da partizionare")
    lunga = max(riferimenti, key=len)
    for i, barra in enumerate(lunga):
        if barra.ts >= limite:
            return i
    raise ValueError(f"{istante_iso} e' oltre la fine della serie")


def righe_stato(v, esito) -> list:
    """Tutte le statistiche richieste, lette **dalle statistiche del verdetto** e non
    ricalcolate: se le ricalcolassi qui potrei stampare un numero che il verdetto non usa,
    ed e' esattamente il difetto che il progetto precedente aveva fra dashboard e validatore.
    """
    s = v.statistiche
    ic = s.get("ic_bootstrap")
    ped = esito.pedaggio_per_operazione
    exp = s.get("expectancy")
    op_anno = (esito.n_operazioni / esito.giorni_osservati * 365.0
               if esito.giorni_osservati > 0 else None)
    return [
        ("verdetto", v.esito),
        ("operazioni", esito.n_operazioni),
        ("giorni osservati", round(esito.giorni_osservati, 2)),
        ("anni osservati", round(esito.giorni_osservati / 365.0, 3)),
        ("operazioni/anno", round(op_anno, 1) if op_anno is not None else None),
        ("expectancy netta", exp),
        ("IC90 inferiore", ic[0] if ic else None),
        ("IC90 superiore", ic[1] if ic else None),
        ("t-statistic", s.get("t_stat")),
        ("profit factor", s.get("profit_factor")),
        ("hit rate", s.get("hit_rate")),
        ("perdita peggiore", s.get("perdita_peggiore")),
        ("guadagno migliore", s.get("guadagno_migliore")),
        ("max drawdown", esito.max_drawdown),
        ("pedaggio per operazione", ped),
        ("copertura pedaggio (x)", (exp / ped) if (exp is not None and ped > 0) else None),
        ("pedaggio 3x richiesto", ped * 3.0),
        ("EUR/anno", s.get("eur_anno")),
        ("criteri falliti", list(s.get("criteri_falliti", ()))),
    ]


def stampa_stato(v, esito) -> None:
    """Stampa le statistiche con la formattazione giusta per ogni grandezza.

    Tre famiglie e non una: le **percentuali** (expectancy, drawdown, pedaggio), i **numeri
    puri** (t-statistic, copertura in multipli, profitto factor) e i **conteggi/anni**. Un
    unico formattatore percentuale per tutti e' il modo in cui un t-statistic diventa '-68%'.
    """
    perc = {"expectancy netta", "IC90 inferiore", "IC90 superiore", "hit rate",
            "perdita peggiore", "guadagno migliore", "max drawdown",
            "pedaggio per operazione", "pedaggio 3x richiesto"}
    num = {"t-statistic", "profit factor", "copertura pedaggio (x)"}
    for etichetta, valore in righe_stato(v, esito):
        if isinstance(valore, (list, tuple)):
            print(f"    {etichetta:<28} {', '.join(valore) if valore else '(nessuno)'}")
        elif not isinstance(valore, (int, float)):
            print(f"    {etichetta:<28} {valore}")
        elif etichetta == "EUR/anno":
            print(f"    {etichetta:<28} {_e(valore)}")
        elif etichetta in ("operazioni", "giorni osservati"):
            print(f"    {etichetta:<28} {valore:g}".replace(".", ","))
        elif etichetta in ("anni osservati", "operazioni/anno"):
            print(f"    {etichetta:<28} {_num(valore, 2)}")
        elif etichetta in perc:
            print(f"    {etichetta:<28} {_p(valore)}")
        elif etichetta in num:
            print(f"    {etichetta:<28} {_num(valore)}")
        else:
            print(f"    {etichetta:<28} {_num(valore)}")


def esito_a_tariffa(operazioni, giorni: float, nome_tariffa: str, slip: float,
                    nome: str) -> tuple:
    """Lo stesso insieme di operazioni rivalutato a un'altra tariffa.

    Non e' un secondo backtest: e' la **stessa** sequenza di prezzi con un pedaggio diverso.
    Serve a separare le due ipotesi che un verdetto "archiviato" non distingue da solo:
    "il segnale non c'e'" contro "il segnale c'e' e il pedaggio se lo mangia".
    """
    tariffa = get_tariffa(nome_tariffa)
    esito = M.esito_da_operazioni(operazioni, giorni, nome, slippage_per_lato=slip,
                                  tariffa=tariffa, note=f"scenario tariffa {nome_tariffa}")
    return esito, giudica(esito, capitale_riferimento=CAPITALE_RIFERIMENTO,
                          soglia_eur_anno=SOGLIA_EUR_ANNO)


def blocco_verdetto(titolo: str, esito, v) -> dict:
    _titolo(titolo)
    print(f"  nome esito: {esito.nome}")
    print(f"  note      : {esito.note}")
    print(f"  tariffa   : {esito.tariffa.venue.value} | {esito.tariffa.condizione}")
    print(f"  tipo      : {esito.tipo}")
    print()
    stampa_stato(v, esito)
    print()
    print(f"  VERDETTO VERBATIM: {v.esito!r}")
    print("  MOTIVI:")
    if v.motivi:
        for motivo in v.motivi:
            print("    - " + motivo)
    else:
        print("    (nessun motivo: tutti i criteri superati)")
    return {
        "titolo": titolo,
        "nome": esito.nome,
        "note": esito.note,
        "esito": v.esito,
        "motivi": list(v.motivi),
        "statistiche": righe_stato(v, esito),
        "criteri": dict(v.statistiche.get("criteri", {})),
    }


def descrivi_blocchi(esito, n_blocchi: int = 3) -> list:
    """Scomposizione per blocchi contigui, con la lettura **netta** che decide il criterio 8."""
    sc = scomponi_per_regime(esito, n_blocchi=n_blocchi)
    righe = []
    print(f"  blocchi contigui ({len(sc.blocchi)}), valori LORDI e NETTI:")
    for i, (lorda, n_) in enumerate(zip(sc.expectancy_per_blocco, sc.n_per_blocco), start=1):
        netta = lorda - esito.pedaggio_per_operazione
        print(f"    blocco {i}: {n_:>4} operazioni, lorda {_p(lorda)}, netta {_p(netta)}")
        righe.append({"blocco": i, "n": n_, "lorda": lorda, "netta": netta})
    print(f"    {sc.motivo}")
    return righe


def main() -> int:
    t0 = time.time()
    CARTELLA_RISULTATI.mkdir(parents=True, exist_ok=True)
    scaricatore = Scarica()

    _titolo("MISURA DEL NODO C — momento a 4 ore (breakout di canale, long-only, EUR)")
    print("  dati          : OKX EEA (eea.okx.com), coppie EUR, point-in-time, barra in corso "
          "scartata da money.dati")
    print(f"  periodo       : {M.INIZIO_STORIA} -> {M.FINE_STORIA}")
    print(f"  addestramento : {M.INIZIO_STORIA} -> {M.CONFINE_ADDESTRAMENTO} (escluso)")
    print(f"  verifica      : {M.CONFINE_ADDESTRAMENTO} -> {M.FINE_STORIA} (embargo strutturale)")
    print(f"  griglia       : {len(M.GRIGLIA_ADDESTRAMENTO)} configurazioni, dichiarate a priori: "
          f"{[str(M.Config(**c)) for c in M.GRIGLIA_ADDESTRAMENTO]}")
    print(f"  tariffa       : {M.TARIFFA_ASSUNTA} ({M.TIPO_ORDINE}) = "
          f"{_p(M.pedaggio(), 4)} per giro; 3x = {_p(M.pedaggio() * 3, 4)}")
    print(f"  slippage      : {_p(M.SLIPPAGE_PER_LATO, 4)} per lato, assunto (spread misurati "
          f"2026-09-25: 0,003% BTC -> 0,49% APT, mediana ~0,04%)")
    print(f"  esposizione   : {_p(M.ESPOSIZIONE, 0)} del capitale per operazione")
    print(f"  capitale      : {_e(CAPITALE_RIFERIMENTO)}, soglia {_e(SOGLIA_EUR_ANNO)}/anno")
    print(f"  cache dati    : {scaricatore.cartella_cache}")

    _titolo("1) CARICAMENTO DATI")
    dati: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        print(f"\n  universo primario, {timeframe}:")
        dati[timeframe] = carica(scaricatore, M.SIMBOLI, timeframe)

    if not dati[TIMEFRAME_PRIMARIO] or not dati[TIMEFRAME_CONFRONTO]:
        print("\n  DATI INSUFFICIENTI: non si misura niente.")
        return 1

    # Il confine e' lo stesso per tutti: si calcola sulla serie piu' lunga del timeframe 4h e
    # si usa lo stesso istante ISO per il giornaliero. Cosi' i due timeframe vedono la stessa
    # finestra di calendario e il confronto fra i due e' un confronto, non due esperimenti.
    i_confine = prima_dopo(dati[TIMEFRAME_PRIMARIO], M.CONFINE_ADDESTRAMENTO)
    inizio_comune = max(serie.intervallo()[0] for serie in dati[TIMEFRAME_PRIMARIO].values())
    riferimento = max(dati[TIMEFRAME_PRIMARIO].values(), key=len)[i_confine].ts
    confine_iso = _iso(riferimento)
    print(f"\n  confine effettivo (stessa barra per tutti): indice {i_confine} @ {confine_iso}")
    print(f"  controllo partizione: addestramento = indici 0..{i_confine - 1}, verifica = "
          f"indici {i_confine}..fine (nessuna barra condivisa)")
    print(f"  prima barra del paniere: {_iso(inizio_comune)}")

    # --- 2. addestramento su entrambi i timeframe -----------------------------------------
    _titolo("2) ADDESTRAMENTO — scelta dei parametri (solo barre fino al confine)")
    scelte: dict = {}
    tabelle: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        print(f"\n  --- {timeframe}: griglia completa, expectancy netta in addestramento ---")
        config, tabella = M.scegli_config(
            dati[timeframe], i_da=0, i_a=i_confine - 1,
            nome=f"addestramento {timeframe}", tariffa=get_tariffa(M.TARIFFA_ASSUNTA))
        for riga in tabella:
            print(f"    {str(riga['config']):<48} n={riga['n']:>5}  "
                  f"expectancy netta {_p(riga['expectancy_netta'], 4)}")
        scelte[timeframe] = config
        tabelle[timeframe] = [
            {"config": str(riga["config"]), "n": riga["n"],
             "expectancy_netta": riga["expectancy_netta"]} for riga in tabella]
        print(f"    SCELTA {timeframe}: {config}")

    # --- 3. verifica ----------------------------------------------------------------------
    _titolo("3) VERIFICA — la configurazione scelta, applicata alla finestra mai usata")
    esiti: dict = {}
    verdetti: dict = {}
    operazioni_verifica: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        config = scelte[timeframe]
        finestra = dati[timeframe]
        i_da = prima_dopo(finestra, confine_iso)
        esito = M.simula(
            finestra, config,
            nome=f"momento {timeframe} breakout [{config}] verifica "
                 f"{confine_iso[:10]}->{M.FINE_STORIA}",
            tariffa=get_tariffa(M.TARIFFA_ASSUNTA), i_da=i_da)
        v = giudica(esito, capitale_riferimento=CAPITALE_RIFERIMENTO,
                    soglia_eur_anno=SOGLIA_EUR_ANNO)
        esiti[timeframe] = esito
        verdetti[timeframe] = v
        operazioni_verifica[timeframe] = _operazioni_da_esito(esito, finestra, config, i_da)
        blocco_verdetto(f"3.{timeframe}) VERDETTO {timeframe.upper()} — verifica "
                        f"(tariffa {M.TARIFFA_ASSUNTA})", esito, v)
        print()
        print(f"  SCOMPOSIZIONE PER BLOCCHI ({timeframe}):")
        descrivi_blocchi(esito, 3)

    # --- 4. confronto 4h vs 1d ------------------------------------------------------------
    _titolo("4) CONFRONTO 4h vs 1d — la tesi del nodo C e' relativa al giornaliero")
    print(f"  {'metrica':<34} {'4h':>16} {'1d':>16} {'rapporto 4h/1d':>16}")
    e4, e1 = esiti[TIMEFRAME_PRIMARIO], esiti[TIMEFRAME_CONFRONTO]
    op4 = e4.n_operazioni / e4.giorni_osservati * 365.0 if e4.giorni_osservati else 0.0
    op1 = e1.n_operazioni / e1.giorni_osservati * 365.0 if e1.giorni_osservati else 0.0
    exp4 = _media(e4.ritorni_netti)
    exp1 = _media(e1.ritorni_netti)
    righe_confronto = [
        ("operazioni in verifica", f"{e4.n_operazioni}", f"{e1.n_operazioni}", None),
        ("giorni osservati", f"{e4.giorni_osservati:.0f}", f"{e1.giorni_osservati:.0f}", None),
        ("operazioni/anno", _n(op4, 1), _n(op1, 1), _n(op4 / op1, 2) if op1 else "n/d"),
        ("expectancy LORDA/operazione", _p(M.expectancy_lorda(operazioni_verifica[TIMEFRAME_PRIMARIO]), 4),
         _p(M.expectancy_lorda(operazioni_verifica[TIMEFRAME_CONFRONTO]), 4), None),
        ("expectancy NETTA/operazione", _p(exp4, 4), _p(exp1, 4), None),
        ("pedaggio per operazione", _p(e4.pedaggio_per_operazione, 4),
         _p(e1.pedaggio_per_operazione, 4), None),
        ("t-statistic", _num(verdetti[TIMEFRAME_PRIMARIO].statistiche.get("t_stat"), 3),
         _num(verdetti[TIMEFRAME_CONFRONTO].statistiche.get("t_stat"), 3), None),
        ("verdetto del cancello", verdetti[TIMEFRAME_PRIMARIO].esito,
         verdetti[TIMEFRAME_CONFRONTO].esito, None),
    ]
    for etichetta, a, b, r in righe_confronto:
        print(f"  {etichetta:<34} {a:>16} {b:>16} {r if r else '':>16}")
    print()
    print(f"  La tesi del nodo C afferma ~8x occasioni a 4h rispetto al giornaliero: misurato "
          f"{_n(op4 / op1, 2) if op1 else 'n/d'}x.")
    print(f"  Edge netto a 4h  : {_p(exp4, 4)} per operazione contro un pedaggio di "
          f"{_p(e4.pedaggio_per_operazione, 4)} -> copertura "
          f"{_n(exp4 / e4.pedaggio_per_operazione, 3)}x (servono 3x)")
    print(f"  Edge netto a 1d  : {_p(exp1, 4)} per operazione contro un pedaggio di "
          f"{_p(e1.pedaggio_per_operazione, 4)} -> copertura "
          f"{_n(exp1 / e1.pedaggio_per_operazione, 3)}x (servono 3x)")

    # --- 5. confronta_tariffe e scenari ---------------------------------------------------
    _titolo("5) CONFRONTA_TARIFFE — quanto vale abbassare il pedaggio (stesse operazioni)")
    confronti: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        esito = esiti[timeframe]
        for nome_tariffa in TARIFFE_SCENARIO:
            ct = confronta_tariffe(esito, "okx_eea_spot", nome_tariffa,
                                   capitale_riferimento=CAPITALE_RIFERIMENTO,
                                   soglia_eur_anno=SOGLIA_EUR_ANNO)
            print(f"\n  [{timeframe}] {ct.sintesi}")
            print(f"        pedaggio per operazione: {_p(esito.pedaggio_per_operazione, 4)} -> "
                  f"{_p(movimento_minimo(get_tariffa(nome_tariffa), esito.tipo), 4)}  "
                  f"(fattore {_n(M.pedaggio() / movimento_minimo(get_tariffa(nome_tariffa), esito.tipo), 2)}x)")
            print(f"        expectancy netta: {_p(ct.verdetto_a.statistiche['expectancy'], 4)} -> "
                  f"{_p(ct.verdetto_b.statistiche['expectancy'], 4)}")
            print(f"        EUR/anno: {_e(ct.verdetto_a.statistiche.get('eur_anno'))} -> "
                  f"{_e(ct.verdetto_b.statistiche.get('eur_anno'))}")
            print(f"        verdetto: {ct.verdetto_a.esito} -> {ct.verdetto_b.esito}")
            confronti[f"{timeframe}|{nome_tariffa}"] = {
                "sintesi": ct.sintesi,
                "criteri_cambiati": list(ct.criteri_cambiati),
                "verdetto_a": ct.verdetto_a.esito,
                "verdetto_b": ct.verdetto_b.esito,
                "pedaggio_a": esito.pedaggio_per_operazione,
                "pedaggio_b": movimento_minimo(get_tariffa(nome_tariffa), esito.tipo),
                "expectancy_a": ct.verdetto_a.statistiche["expectancy"],
                "expectancy_b": ct.verdetto_b.statistiche["expectancy"],
                "eur_anno_a": ct.verdetto_a.statistiche.get("eur_anno"),
                "eur_anno_b": ct.verdetto_b.statistiche.get("eur_anno"),
            }

    _titolo("5b) SCENARI DI TARIFFA — il verdetto a ogni pedaggio, stesse operazioni")
    scenari: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        operazioni = operazioni_verifica[timeframe]
        giorni = esiti[timeframe].giorni_osservati
        print(f"\n  --- {timeframe} ---")
        print(f"  {'tariffa':<22} {'pedaggio':>10} {'3x':>10} {'exp. netta':>12} "
              f"{'copertura':>10} {'EUR/anno':>12} {'verdetto':>16}")
        righe = {}
        for nome_tariffa in ("okx_eea_spot",) + TARIFFE_SCENARIO:
            tariffa = get_tariffa(nome_tariffa)
            ped = movimento_minimo(tariffa, M.TIPO_ORDINE)
            esito, v = esito_a_tariffa(
                operazioni, giorni, nome_tariffa, M.SLIPPAGE_PER_LATO,
                f"momento {timeframe} [{scelte[timeframe]}] @ {nome_tariffa}")
            exp = v.statistiche.get("expectancy")
            print(f"  {nome_tariffa:<22} {_p(ped, 3):>10} {_p(ped * 3, 3):>10} {_p(exp, 4):>12} "
                  f"{_n(exp / ped, 3):>10} {_e(v.statistiche.get('eur_anno')):>12} "
                  f"{v.esito:>16}")
            righe[nome_tariffa] = {
                "pedaggio": ped, "soglia_3x": ped * 3.0, "expectancy_netta": exp,
                "copertura": exp / ped if ped > 0 else None,
                "eur_anno": v.statistiche.get("eur_anno"), "verdetto": v.esito,
                "criteri_falliti": list(v.statistiche.get("criteri_falliti", ())),
                "t_stat": v.statistiche.get("t_stat"),
                "ic90": list(v.statistiche.get("ic_bootstrap") or (float("nan"),) * 2),
            }
        scenari[timeframe] = righe
    print("\n  Nota: qui cambia SOLO la tariffa. La sequenza di prezzi, le operazioni, i giorni")
    print("  osservati e l'esposizione sono identici: e' la stessa strategia con un pedaggio")
    print("  diverso, non un secondo backtest.")

    # --- 6. sensibilita' slippage ---------------------------------------------------------
    _titolo("6) SENSIBILITA' ALLO SLIPPAGE ASSUNTO (verifica, tariffa spot)")
    slip_tabella: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        operazioni = operazioni_verifica[timeframe]
        giorni = esiti[timeframe].giorni_osservati
        print(f"\n  --- {timeframe} ---")
        print(f"  {'slippage/lato':>14} {'exp. netta':>12} {'t-stat':>9} {'EUR/anno':>12} "
              f"{'verdetto':>16}")
        righe = {}
        for slip in SLIPPAGE_SENSIBILITA:
            esito, v = esito_a_tariffa(operazioni, giorni, M.TARIFFA_ASSUNTA, slip,
                                       f"momento {timeframe} slip {slip:.4%}")
            print(f"  {_p(slip, 4):>14} {_p(v.statistiche.get('expectancy'), 4):>12} "
                  f"{_n(v.statistiche.get('t_stat'), 2):>9} "
                  f"{_e(v.statistiche.get('eur_anno')):>12} {v.esito:>16}")
            righe[f"{slip:.4f}"] = {
                "slippage_per_lato": slip,
                "expectancy_netta": v.statistiche.get("expectancy"),
                "t_stat": v.statistiche.get("t_stat"),
                "eur_anno": v.statistiche.get("eur_anno"),
                "verdetto": v.esito,
            }
        slip_tabella[timeframe] = righe

    # --- 7. universo allargato ------------------------------------------------------------
    _titolo("7) ROBUSTEZZA — universo allargato (18 coppie EUR, storia parziale per 8)")
    allargato: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        print(f"\n  universo allargato, {timeframe}:")
        dati_all = carica(scaricatore, M.SIMBOLI_ALLARGATO, timeframe)
        config = scelte[timeframe]
        e_all = M.simula(dati_all, config, nome=f"allargato {timeframe} [{config}]",
                         tariffa=get_tariffa(M.TARIFFA_ASSUNTA))
        v_all = giudica(e_all, capitale_riferimento=CAPITALE_RIFERIMENTO,
                        soglia_eur_anno=SOGLIA_EUR_ANNO)
        op_all = _operazioni_da_esito(e_all, dati_all, config, 0)
        print("    PERIODO INTERO (addestramento + verifica: qui la partizione non e' "
              "riportabile, perche' 8 dei 18 simboli partono nel 2024-03 e la loro "
              "'addestramento' sarebbe piu' corto di quello degli altri)")
        print(f"      {e_all.n_operazioni} operazioni in {e_all.giorni_osservati:.0f} giorni, "
              f"expectancy LORDA {_p(M.expectancy_lorda(op_all), 4)}, expectancy netta "
              f"{_p(v_all.statistiche.get('expectancy'), 4)}, verdetto {v_all.esito}")
        print(f"      criteri falliti: "
              f"{', '.join(v_all.statistiche.get('criteri_falliti', ())) or '(nessuno)'}")
        # La stessa robustezza **sulla sola finestra di verifica**, che e' il confronto onesto
        # con la misura primaria: stesse date, paniere piu' largo.
        i_da_all = prima_dopo(dati_all, confine_iso)
        e_all_v = M.simula(dati_all, config, nome=f"allargato {timeframe} verifica [{config}]",
                           tariffa=get_tariffa(M.TARIFFA_ASSUNTA), i_da=i_da_all)
        v_all_v = giudica(e_all_v, capitale_riferimento=CAPITALE_RIFERIMENTO,
                          soglia_eur_anno=SOGLIA_EUR_ANNO)
        op_all_v = _operazioni_da_esito(e_all_v, dati_all, config, i_da_all)
        print(f"    SOLO VERIFICA {confine_iso[:10]}->{M.FINE_STORIA} (stesse date della "
              f"misura primaria, paniere piu' largo)")
        print(f"      {e_all_v.n_operazioni} operazioni in {e_all_v.giorni_osservati:.0f} giorni, "
              f"expectancy LORDA {_p(M.expectancy_lorda(op_all_v), 4)}, expectancy netta "
              f"{_p(v_all_v.statistiche.get('expectancy'), 4)}, verdetto {v_all_v.esito}")
        print(f"      criteri falliti: "
              f"{', '.join(v_all_v.statistiche.get('criteri_falliti', ())) or '(nessuno)'}")
        allargato[timeframe] = {
            "periodo_intero": {
                "n_operazioni": e_all.n_operazioni,
                "giorni": e_all.giorni_osservati,
                "expectancy_lorda": M.expectancy_lorda(op_all),
                "expectancy_netta": v_all.statistiche.get("expectancy"),
                "verdetto": v_all.esito,
                "eur_anno": v_all.statistiche.get("eur_anno"),
            },
            "solo_verifica": {
                "n_operazioni": e_all_v.n_operazioni,
                "giorni": e_all_v.giorni_osservati,
                "expectancy_lorda": M.expectancy_lorda(op_all_v),
                "expectancy_netta": v_all_v.statistiche.get("expectancy"),
                "verdetto": v_all_v.esito,
                "eur_anno": v_all_v.statistiche.get("eur_anno"),
                "criteri_falliti": list(v_all_v.statistiche.get("criteri_falliti", ())),
            },
        }

    # --- 8. globale (tutto il periodo) come contesto --------------------------------------
    _titolo("8) CONTESTO — stessa configurazione su TUTTO il periodo (non e' la misura)")
    globale: dict = {}
    for timeframe in (TIMEFRAME_PRIMARIO, TIMEFRAME_CONFRONTO):
        config = scelte[timeframe]
        e_full = M.simula(dati[timeframe], config, nome=f"momento {timeframe} [{config}] "
                          f"periodo intero {M.INIZIO_STORIA}->{M.FINE_STORIA}",
                          tariffa=get_tariffa(M.TARIFFA_ASSUNTA))
        v_full = giudica(e_full, capitale_riferimento=CAPITALE_RIFERIMENTO,
                         soglia_eur_anno=SOGLIA_EUR_ANNO)
        print(f"\n  [{timeframe}] {e_full.n_operazioni} operazioni in "
              f"{e_full.giorni_osservati:.0f} giorni, expectancy LORDA "
              f"{_p(M.expectancy_lorda(_operazioni_da_esito(e_full, dati[timeframe], config, 0)), 4)}, "
              f"expectancy netta {_p(v_full.statistiche.get('expectancy'), 4)}, verdetto "
              f"{v_full.esito}")
        print(f"        motivi: {'; '.join(v_full.motivi[:3]) if v_full.motivi else '(nessuno)'}")
        globale[timeframe] = {
            "n_operazioni": e_full.n_operazioni,
            "giorni": e_full.giorni_osservati,
            "expectancy_netta": v_full.statistiche.get("expectancy"),
            "verdetto": v_full.esito,
            "motivi": list(v_full.motivi),
        }

    # --- 9. salvataggio -------------------------------------------------------------------
    risultato = {
        "meta": {
            "periodo": [M.INIZIO_STORIA, M.FINE_STORIA],
            "confine_addestramento": M.CONFINE_ADDESTRAMENTO,
            "confine_effettivo_iso": confine_iso,
            "universo_primario": list(M.SIMBOLI),
            "griglia": [str(M.Config(**c)) for c in M.GRIGLIA_ADDESTRAMENTO],
            "tariffa_assunta": M.TARIFFA_ASSUNTA,
            "tipo": M.TIPO_ORDINE,
            "pedaggio_per_operazione": M.pedaggio(),
            "slippage_per_lato": M.SLIPPAGE_PER_LATO,
            "esposizione": M.ESPOSIZIONE,
            "capitale_riferimento": CAPITALE_RIFERIMENTO,
            "soglia_eur_anno": SOGLIA_EUR_ANNO,
        },
        "scelte": {tf: str(scelte[tf]) for tf in scelte},
        "griglia_addestramento": tabelle,
        "verdetti_verifica": {tf: {"esito": verdetti[tf].esito, "motivi": list(verdetti[tf].motivi),
                                   "statistiche": righe_stato(verdetti[tf], esiti[tf])}
                              for tf in verdetti},
        "confronto_4h_1d": {
            "operazioni_anno_4h": op4, "operazioni_anno_1d": op1,
            "rapporto_occasioni": (op4 / op1) if op1 else None,
            "expectancy_netta_4h": exp4, "expectancy_netta_1d": exp1,
            "expectancy_lorda_4h": M.expectancy_lorda(operazioni_verifica[TIMEFRAME_PRIMARIO]),
            "expectancy_lorda_1d": M.expectancy_lorda(operazioni_verifica[TIMEFRAME_CONFRONTO]),
        },
        "confronta_tariffe": confronti,
        "scenari_tariffa": scenari,
        "slippage": slip_tabella,
        "universo_allargato": allargato,
        "periodo_intero": globale,
    }
    percorso = CARTELLA_RISULTATI / "momento_4h.json"
    percorso.write_text(json.dumps(risultato, indent=2, ensure_ascii=False, default=str),
                        encoding="utf-8")
    print(f"\n  risultato salvato in: {percorso}")
    print(f"  tempo totale: {time.time() - t0:.1f}s")
    return 0


def _media(valori) -> float:
    return math.fsum(valori) / len(valori) if valori else float("nan")


def _iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def _operazioni_da_esito(esito, serie_per_simbolo: dict, config, i_da: int) -> list:
    """Rifa' le operazioni **con i loro ritorni lordi** per la stessa finestra dell'esito.

    Serve a valutare scenari di tariffa e slippage sulle stesse operazioni: l'`Esito` conserva
    solo i ritorni netti, e ricostruire il lordo sommando indietro il pedaggio sarebbe corretto
    ma fragile (basterebbe un secondo costo non dichiarato per sbagliare in silenzio). Qui il
    lordo viene dal motore, che e' l'unico che lo conosce per davvero.
    """
    operazioni: list = []
    for simbolo, serie in sorted(serie_per_simbolo.items()):
        if len(serie) < config.canale + config.orizzonte + 2:
            continue
        trovate = M.operazioni_simbolo(serie, config, i_da=i_da, i_a=len(serie) - 1)
        operazioni.extend(
            M.Operazione(simbolo, o.indice_ingresso, o.indice_uscita, o.ts_ingresso, o.ts_uscita,
                         o.prezzo_ingresso, o.prezzo_uscita, o.ritorno_lordo, o.motivo)
            for o in trovate)
    return operazioni


if __name__ == "__main__":
    raise SystemExit(main())
