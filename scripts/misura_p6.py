#!/usr/bin/env python3
"""Misura P6 — livello PORTAFOGLIO: cap di concorrenza e correlazione (Donchian 55/20).

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P6 di prove/REGISTRO_ESPERIMENTI.md)
=========================================================================================
- Segnale FISSO: Donchian 55/20 sui 10 majors USDT (config P1/P2). Non si tocca.
- Griglia dichiarata: {max_posizioni: 2,3,4} x {selezione: fifo, mincorr} = 6 configurazioni.
  Controllo interno: P2 "sizing no" (nessun cap) — atteso DDser 46,99% e DDport 42,84%
  (VERIFICA), 55 operazioni complessive.
- fifo: un segnale che arriva a slot pieni e' SALTATO e contato (motore portafoglio.py).
- mincorr: come fifo, ma un ingresso e' RIFIUTATO se la correlazione (Pearson) degli
  ultimi 60 rendimenti giornalieri close-to-close con una qualunque posizione aperta
  supera tau = 0,75. Solo dati fino alla barra di decisione (indice_ingresso - 1).
  Se la finestra non e' calcolabile (storia insufficiente / varianza nulla), l'ingresso
  e' CONSENTITO (il cap resta attivo) — dichiarato; i casi non calcolabili finiscono nel json.
- Ordine di valutazione di ogni segnale nel motore: PRIMA il filtro (mincorr), POI il cap.
- Metriche: primaria DD di portafoglio mark-to-market; secondarie: EUR/anno, eseguiti/
  saltati/rifiutati, esposizione aggregata massima, posizioni concorrenti massime, t-stat,
  expectancy (campione ESEGUITO), stress costi (stack fee+spread+slippage x2, come P2).
- Successo (spec): DDport <= 25% E expectancy >= 3x pedaggio, finestra VERIFICA.
- Se anche P6 fallisce, il filone trend-cash-solo si archivia per costruzione (regola P2).

NIENTE viene aggiustato per far passare il verdetto. I numeri si stampano con le cifre
che hanno, non con quelle che servirebbero.

Uso: python scripts/misura_p6.py
"""
from __future__ import annotations

import bisect
import json
import math
import sys
import time
from pathlib import Path

for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        if str(_src) not in sys.path:
            sys.path.insert(0, str(_src))
        if str(_antenato) not in sys.path:
            sys.path.insert(0, str(_antenato))
        break

from money.cancello import Esito, giudica  # noqa: E402
from money.costi import get_tariffa  # noqa: E402
from money.dati import Scarica  # noqa: E402
from money.ricerca import donchian_breakout as D  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402
from money.ricerca.portafoglio import backtest_portafoglio  # noqa: E402
from money.statistica import t_stat, t_stat_newey_west  # noqa: E402
from scripts.misura_catena_hermes import carica, prima_dopo  # noqa: E402

CONFIG = D.Config(55, 20)
ESPOSIZIONE_BASE = 0.25
CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
MAX_POSIZIONI = (2, 3, 4)
TAU = 0.75
FINESTRA_CORR = 60
#: Stress costi: lo stack fee + spread/slippage di un'operazione, applicato una seconda
#: volta (costi x2). Dichiarato: stesso scenario dell'addendum P2.
COSTO_STRESS_EXTRA = D.pedaggio() + 2.0 * D.SLIPPAGE_PER_LATO
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"

#: Riferimenti interni: controllo atteso = arm "sizing no" di P2 (misura 2026-09-30).
RIFERIMENTI = {
    "VERIFICA": (0.4699, 0.4284, 55),
    "FINESTRA PIENA": (0.7383, 0.6799, 135),
}


def _p(x, cifre=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}%".replace(".", ",")


def _n(x, cifre=3):
    if x is None:
        return "n/d"
    return f"{x:.{cifre}f}".replace(".", ",")


def _rendimenti(chiusure, i_fin, n=FINESTRA_CORR):
    """n rendimenti giornalieri close-to-close fino alla barra i_fin (inclusa).

    None se la storia non basta: il chiamante decide (qui: consente e conta).
    """
    if i_fin < n:
        return None
    return [chiusure[k] / chiusure[k - 1] - 1.0 for k in range(i_fin - n + 1, i_fin + 1)]


def _corr(a, b):
    """Pearson tra due serie di pari lunghezza; None se varianza nulla o lunghezze diverse."""
    if a is None or b is None or len(a) != len(b) or len(a) < 2:
        return None
    n = len(a)
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0.0 or vb <= 0.0:
        return None
    cov = sum((x - ma) * (y - mb) for x, y in zip(a, b))
    return cov / math.sqrt(va * vb)


def filtro_mincorr(chiuse, ts_list, dati, non_calcolabili):
    """Filtro d'ingresso della variante mincorr (spec P6), con soli dati passati.

    `(simbolo, op, ts, posizioni) -> bool`: False = rifiutato (correlazione > tau con
    almeno una posizione aperta). Finestra non calcolabile -> True (e si conta).
    """

    def _ultimo_al_o_prima(simbolo_altro, ts):
        lista = ts_list[simbolo_altro]
        i = bisect.bisect_right(lista, ts) - 1
        return i if i >= 0 else None

    def filtro(simbolo, op, ts, posizioni):
        i_dec = op.indice_ingresso - 1
        if i_dec < 0 or not posizioni:
            return True
        rs_cand = _rendimenti(chiuse[simbolo], i_dec)
        if rs_cand is None:
            non_calcolabili["n"] += 1
            return True
        ts_dec = dati[simbolo][i_dec].ts
        for altro in posizioni:
            j = _ultimo_al_o_prima(altro, ts_dec)
            rs_alt = _rendimenti(chiuse[altro], j) if j is not None else None
            if rs_alt is None:
                continue
            c = _corr(rs_cand, rs_alt)
            if c is not None and c > TAU:
                return False
        return True

    return filtro


def misura_finestra(etichetta, dati, i_da, righe):
    """Un giro completo su una finestra: controllo + 6 arm dichiarate + secondarie."""
    finestra = {s: list(serie)[i_da:] for s, serie in dati.items()}
    ops_per_simbolo = {}
    for simbolo, serie in sorted(dati.items()):
        ops = D.operazioni_simbolo(serie, CONFIG, i_da=i_da)
        if ops:
            ops_per_simbolo[simbolo] = ops
    tutte = [o for ops in ops_per_simbolo.values() for o in ops]
    n_ops = len(tutte)
    pedaggio = D.pedaggio()
    netto_fn = lambda lordo: D.ritorno_netto(lordo)  # noqa: E731

    ts_list = {s: [b.ts for b in serie] for s, serie in dati.items()}
    chiuse = {s: [b.chiusura for b in serie] for s, serie in dati.items()}

    barre_totali = max(len(s) for s in finestra.values())
    t_inizio = min(s[0].ts for s in finestra.values())
    t_fine = max(s[-1].ts for s in finestra.values())
    giorni = (t_fine - t_inizio) / 86_400_000.0

    # --- controllo interno: nessun cap, nessun filtro (= P2 "sizing no") ----------------
    e_controllo = backtest_portafoglio(finestra, ops_per_simbolo,
                                       esposizione=ESPOSIZIONE_BASE,
                                       netto_fn=netto_fn, capitale=CAPITALE)
    netti_tutte = [D.ritorno_netto(o.ritorno_lordo)
                   for o in sorted(tutte, key=lambda o: o.ts_ingresso)]
    dd_ser_controllo, _ = D.curva_equity(netti_tutte, ESPOSIZIONE_BASE)
    dd_port_controllo = e_controllo.max_drawdown

    rif = next((v for k, v in RIFERIMENTI.items() if etichetta.startswith(k)), None)
    check = "n/d"
    if rif:
        dd_s, dd_p, n_rif = rif
        ok = (abs(dd_ser_controllo - dd_s) < 0.005
              and abs(dd_port_controllo - dd_p) < 0.005
              and e_controllo.operazioni_eseguite + e_controllo.operazioni_saltate == n_rif)
        check = "OK" if ok else "DIFF! (controllo non riproduce il riferimento P2)"
    righe.append(f"  [controllo (sizing no) {etichetta[:9]}: dd_ser {_p(dd_ser_controllo)}, "
                 f"dd_port {_p(dd_port_controllo)}, esegui+salt {e_controllo.operazioni_eseguite}"
                 f"+{e_controllo.operazioni_saltate} | check vs P2: {check}]")

    risultati = []
    for mp in MAX_POSIZIONI:
        for selezione in ("fifo", "mincorr"):
            non_calc = {"n": 0}
            filtro = (filtro_mincorr(chiuse, ts_list, dati, non_calc)
                      if selezione == "mincorr" else None)
            e_port = backtest_portafoglio(
                finestra, ops_per_simbolo, esposizione=ESPOSIZIONE_BASE,
                netto_fn=netto_fn, capitale=CAPITALE,
                max_posizioni=mp, filtro_ingresso=filtro)

            netti_ese = [D.ritorno_netto(o.ritorno_lordo) for _, o in e_port.esecuzioni]
            n_ese = len(netti_ese)
            if n_ese:
                dd_ser_arm, _ = D.curva_equity(netti_ese, ESPOSIZIONE_BASE)
                exp = sum(netti_ese) / n_ese
                copertura = exp / pedaggio
                exp_stress = sum(nb - COSTO_STRESS_EXTRA for nb in netti_ese) / n_ese
                t_c = t_stat(netti_ese)
                t_nw, _se = t_stat_newey_west(netti_ese)
                barre_ese = sum(o.indice_uscita - o.indice_ingresso
                                for _, o in e_port.esecuzioni)
                esp_base = min(1.0, (barre_ese / n_ese) / barre_totali)
            else:
                dd_ser_arm = exp = copertura = exp_stress = t_c = t_nw = None
                esp_base = 0.0

            eur_anno = None
            giudica_esito = "n/d (nessuna esecuzione)"
            criteri_falliti = None
            if n_ese:
                esito = Esito(
                    nome=f"P6 Donchian55/20 mp={mp} {selezione} [{etichetta}]",
                    ritorni_netti=tuple(netti_ese), n_operazioni=n_ese,
                    esposizione_media=esp_base, max_drawdown=e_port.max_drawdown,
                    giorni_osservati=giorni, tariffa=get_tariffa(D.TARIFFA_ASSUNTA),
                    tipo=D.TIPO_ORDINE,
                    note=(f"P6: segnale Donchian 55/20 fisso; cap {mp}, selezione {selezione}"
                          + (f"; tau {TAU} su {FINESTRA_CORR} rendimenti"
                             if selezione == "mincorr" else "")
                          + "; DD di portafoglio mark-to-market."))
                v = giudica(esito, capitale_riferimento=CAPITALE,
                            soglia_eur_anno=SOGLIA_EUR_ANNO)
                eur_anno = v.statistiche.get("eur_anno")
                giudica_esito = v.esito
                criteri_falliti = v.statistiche.get("criteri_falliti")

            dd_ok = e_port.max_drawdown <= 0.25
            ped_ok = exp is not None and exp >= 3.0 * pedaggio
            successo = bool(dd_ok and ped_ok)
            fallimenti = [m for m, cond in (("DDport>25%", dd_ok), ("exp<3x", ped_ok))
                          if not cond]
            rid_rel = (1.0 - e_port.max_drawdown / dd_port_controllo
                       if dd_port_controllo > 0 else None)
            nome_arm = f"mp={mp} {selezione}"

            righe.append(
                f"  {nome_arm:>12} | dd_ser {_p(dd_ser_arm):>9} | dd_port {_p(e_port.max_drawdown):>9} "
                f"| exp {_p(exp):>8} | cop {_n(copertura, 1):>5}x | t {_n(t_c, 2):>5} "
                f"| t_nw {_n(t_nw, 2):>5} | eseg/salt/rif "
                f"{e_port.operazioni_eseguite}/{e_port.operazioni_saltate}/{e_port.operazioni_rifiutate}"
                f" | rid_dd {_p(rid_rel, 1) if rid_rel is not None else 'n/d':>8}"
                f" | stress {_p(exp_stress):>8} | max_esp {_p(e_port.max_esposizione, 1)}"
                f" | eur/anno {_n(eur_anno, 1)} | successo {'SI' if successo else 'NO'}"
                f"{' | fallisce: ' + ', '.join(fallimenti) if fallimenti else ''}")

            risultati.append({
                "arm": nome_arm, "max_posizioni": mp, "selezione": selezione,
                "dd_serializzato": dd_ser_arm, "dd_portafoglio": e_port.max_drawdown,
                "expectancy": exp, "copertura_pedaggio": copertura,
                "t_stat": t_c, "t_stat_newey_west": t_nw,
                "eseguite": e_port.operazioni_eseguite, "saltate": e_port.operazioni_saltate,
                "rifiutate": e_port.operazioni_rifiutate,
                "casi_non_calcolabili_filtro": non_calc["n"],
                "riduzione_dd_relativa": rid_rel, "expectancy_stress": exp_stress,
                "posizioni_concorrenti_massime": e_port.max_posizioni,
                "max_esposizione": e_port.max_esposizione,
                "eur_anno": eur_anno, "successo_dd25_exp3x": successo,
                "dd_ok": dd_ok, "pedaggio_ok": ped_ok,
                "giudica_esito": giudica_esito,
                "giudica_criteri_falliti": criteri_falliti,
            })

    return {"etichetta": etichetta, "n_operazioni_totali": n_ops, "giorni": giorni,
            "pedaggio": pedaggio, "check_riferimento": check,
            "controllo": {"dd_serializzato": dd_ser_controllo,
                          "dd_portafoglio": dd_port_controllo,
                          "eseguite": e_controllo.operazioni_eseguite,
                          "saltate": e_controllo.operazioni_saltate},
            "arm": risultati}


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    righe: list = []
    righe.append("P6 — LIVELLO PORTAFOGLIO: cap di concorrenza e correlazione — misura e giudizio")
    righe.append("(voce pre-registrata in prove/REGISTRO_ESPERIMENTI.md prima di questi numeri;")
    righe.append(" griglia dichiarata: {max_posizioni: 2,3,4} x {fifo, mincorr} = 6 varianti)")
    righe.append(f"pedaggio assunta: {_p(D.pedaggio())} per operazione "
                 f"({D.TARIFFA_ASSUNTA}, {D.TIPO_ORDINE}); "
                 f"slippage {_p(2 * D.SLIPPAGE_PER_LATO)} per giro; tau={_n(TAU, 2)} "
                 f"su {FINESTRA_CORR} rendimenti")
    righe.append(f"stress costi: stack fee+spread+slippage applicato due volte "
                 f"({_p(COSTO_STRESS_EXTRA)} extra per operazione)")

    scaricatore = Scarica()
    dati = carica(scaricatore, P3.SIMBOLI, "1d", P3.INIZIO_STORIA, P3.FINE_STORIA,
                  P3.COPERTURA_MINIMA)
    if not dati:
        print("DATI INSUFFICIENTI: non si misura niente.")
        return 1
    i_confine = prima_dopo(dati, P3.CONFINE_ADDESTRAMENTO)

    riepilogo = {"protocollo": {
        "config": str(CONFIG), "segno": "Donchian 55/20", "simboli": list(P3.SIMBOLI),
        "inizio": P3.INIZIO_STORIA, "fine": P3.FINE_STORIA,
        "confine": P3.CONFINE_ADDESTRAMENTO, "esposizione_base": ESPOSIZIONE_BASE,
        "capitale": CAPITALE, "max_posizioni": list(MAX_POSIZIONI),
        "selezioni": ["fifo", "mincorr"], "tau": TAU, "finestra_correlazione": FINESTRA_CORR,
        "n_varianti": 6, "metrica_primaria": "DD di portafoglio mark-to-market",
        "successo": "DDport <= 25% E expectancy (eseguito) >= 3x pedaggio",
    }, "finestre": {}}

    for etichetta, i_da in (("VERIFICA [2024-06-01 -> 2026-09-25]", i_confine),
                            ("FINESTRA PIENA [2020-10-01 -> 2026-09-25]", 0)):
        righe.append("")
        righe.append(f"=== {etichetta} ===")
        esito_finestra = misura_finestra(etichetta, dati, i_da, righe)
        riepilogo["finestre"][etichetta] = esito_finestra

    # verdetto sintetico sulla finestra del verdetto (VERIFICA)
    verifica = next(v for k, v in riepilogo["finestre"].items() if k.startswith("VERIFICA"))
    vincenti = [a["arm"] for a in verifica["arm"] if a["successo_dd25_exp3x"]]
    migliore = min(verifica["arm"], key=lambda a: a["dd_portafoglio"])
    righe.append("")
    righe.append("=== VERDETTO P6 (finestra del verdetto: VERIFICA) ===")
    if vincenti:
        righe.append(f"  Le configurazioni della griglia dichiarata che portano il DD di "
                     f"portafoglio sotto il 25% (con expectancy ancora >= 3x pedaggio): "
                     f"{', '.join(vincenti)}.")
        righe.append("  -> il filone trend NON si archivia per costruzione: esistono "
                     "configurazioni dichiarate che soddisfano il criterio.")
    else:
        righe.append("  NESSUNA configurazione della griglia dichiarata soddisfa "
                     "DDport <= 25% E exp >= 3x pedaggio.")
        righe.append("  -> per la regola dichiarata (P2), il filone trend si archivia per "
                     "costruzione; si prosegue con le famiglie nuove.")
    righe.append(f"  (migliore per DD: {migliore['arm']} con dd_port "
                 f"{_p(migliore['dd_portafoglio'])}; controllo P2: "
                 f"{_p(verifica['controllo']['dd_portafoglio'])}; "
                 f"riferimento esterno non vincolante: 15-35%)")
    riepilogo["verdetto_p6"] = {"vincenti_verifica": vincenti,
                                "migliore_dd": migliore["arm"],
                                "migliore_dd_port": migliore["dd_portafoglio"],
                                "controllo_dd_port": verifica["controllo"]["dd_portafoglio"]}

    testo = "\n".join(righe)
    print(testo)
    (CARTELLA_PROVE / "P6_portafoglio.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "P6_portafoglio.json").write_text(
        json.dumps(riepilogo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"artefatti: {CARTELLA_PROVE / 'P6_portafoglio.txt'} "
          f"e .json | runtime {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
