#!/usr/bin/env python3
"""Misura P11 — volatility breakout ATR: misura e giudizio (protocollo della catena).

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P11 di prove/REGISTRO_ESPERIMENTI.md)
=========================================================================================
- Segnale: ``money.ricerca.vol_breakout_atr`` (consegna A0-PC 30/09, review Hermes).
  Ingresso: chiusura[i]/chiusura[i-1]-1 > k*ATR%(i-1) (stretto), esecuzione all'apertura
  di i+1; uscita alla rottura del minimo delle ultime m barre (o fine serie).
- Griglia dichiarata (6 varianti): {k: 1.0, 1.5, 2.0} x {m: 10, 20}; ATR n=14 fisso.
- Selezione: SOLO addestramento [2020-10-01, 2024-06-01) con vincolo n >= 30,
  criterio = max expectancy netta (convenzione di tutti i nodi della catena).
- Verifica: UNA sola configurazione su [2024-06-01, 2026-09-25]; nessun ritocco.
- Costi: tariffa okx_eea_spot (0.55% per giro), slippage 4 bps/lato (dichiarati);
  stress = stack fee+spread+slippage applicato una seconda volta (costi x2, addendum P2).
- Primaria: DD di PORTAFOGLIO mark-to-market (motore ``portafoglio.py``): 0.25 x equity
  per operazione, cassa vincolante, niente leva, nessun cap di concorrenza (come P6).
- Successo: DDport <= 25% E expectancy (campione ESEGUITO) >= 3x pedaggio.
- Secondarie: EUR/anno, eseguiti/saltati, t-stat (Newey-West accanto), scheda economica
  E1 (``money.economia.scheda_economica``) + benchmark equal-weight della finestra.
Artefatti: ``prove/P11_vol_breakout.{txt,json}``. Se fallisce: archiviata per costruzione.

Uso: python scripts/misura_p11.py
"""
from __future__ import annotations

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
from money.economia import benchmark_equal_weight, scheda_economica  # noqa: E402
from money.ricerca import donchian_breakout as D  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402
from money.ricerca import vol_breakout_atr as V  # noqa: E402
from money.ricerca.portafoglio import backtest_portafoglio  # noqa: E402
from money.statistica import t_stat, t_stat_newey_west  # noqa: E402
from scripts.misura_catena_hermes import carica, prima_dopo  # noqa: E402

ESPOSIZIONE_BASE = 0.25
CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
ATR_N = 14
MIN_OP_TRAINING = 30
#: Griglia dichiarata, 6 varianti — PRIMA dei numeri.
GRIGLIA = tuple((k, m) for k in (1.0, 1.5, 2.0) for m in (10, 20))
COSTO_STRESS_EXTRA = D.pedaggio() + 2.0 * D.SLIPPAGE_PER_LATO
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"


def _p(x, cifre=3):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}%".replace(".", ",")


def _n(x, cifre=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x:.{cifre}f}".replace(".", ",")


def _ops_per_simbolo(dati, config, *, i_da, i_a=None):
    fuori = {}
    for simbolo, serie in sorted(dati.items()):
        ops = V.operazioni_simbolo(serie, config, i_da=i_da, i_a=i_a)
        if ops:
            fuori[simbolo] = ops
    return fuori


def allena(dati, i_confine, righe):
    """Griglia completa SOLO in addestramento; sceglie per max expectancy netta (n>=30)."""
    tabella = []
    righe.append(f"  (configurazioni provate: {len(GRIGLIA)}; vincolo n >= {MIN_OP_TRAINING})")
    for k, m in GRIGLIA:
        config = V.Config(k=k, m=m, atr_n=ATR_N)
        ops = _ops_per_simbolo(dati, config, i_da=0, i_a=i_confine - 1)
        tutte = [o for lst in ops.values() for o in lst]
        netti = [D.ritorno_netto(o.ritorno_lordo) for o in tutte]
        lordi = [o.ritorno_lordo for o in tutte]
        exp = sum(netti) / len(netti) if netti else None
        lordo_m = sum(lordi) / len(lordi) if lordi else None
        tabella.append({"k": k, "m": m, "n": len(tutte), "expectancy_netta": exp,
                        "lordo_medio": lordo_m})
        righe.append(f"  k={_n(k, 1)} m={m:>2} | n={len(tutte):>4} | "
                     f"lordo medio {_p(lordo_m, 4)} | exp netta {_p(exp, 4)}")
    ammissibili = [t for t in tabella if t["n"] >= MIN_OP_TRAINING
                   and t["expectancy_netta"] is not None]
    if not ammissibili:
        return None, tabella
    scelta = max(ammissibili, key=lambda t: t["expectancy_netta"])
    return scelta, tabella


def misura_finestra(etichetta, dati, i_da, config, righe):
    """Un giro sul portafoglio con la configurazione SCELTA (nessun ritocco)."""
    finestra = {s: list(serie)[i_da:] for s, serie in dati.items()}
    ops_per_simbolo = _ops_per_simbolo(dati, config, i_da=i_da)
    tutte = [o for lst in ops_per_simbolo.values() for o in lst]
    pedaggio = D.pedaggio()

    barre_totali = max(len(s) for s in finestra.values())
    t_inizio = min(s[0].ts for s in finestra.values())
    t_fine = max(s[-1].ts for s in finestra.values())
    giorni = (t_fine - t_inizio) / 86_400_000.0

    e_port = backtest_portafoglio(finestra, ops_per_simbolo,
                                  esposizione=ESPOSIZIONE_BASE,
                                  netto_fn=D.ritorno_netto, capitale=CAPITALE)

    lordi_ese = [o.ritorno_lordo for _, o in e_port.esecuzioni]
    netti_ese = [D.ritorno_netto(o.ritorno_lordo) for _, o in e_port.esecuzioni]
    n_ese = len(netti_ese)

    dd_ser = exp = copertura = exp_stress = t_c = t_nw = None
    esp_base = 0.0
    if n_ese:
        dd_ser, _ = D.curva_equity(netti_ese, ESPOSIZIONE_BASE)
        exp = sum(netti_ese) / n_ese
        copertura = exp / pedaggio
        exp_stress = sum(nb - COSTO_STRESS_EXTRA for nb in netti_ese) / n_ese
        t_c = t_stat(netti_ese)
        t_nw, _se = t_stat_newey_west(netti_ese)
        barre_ese = sum(o.indice_uscita - o.indice_ingresso for _, o in e_port.esecuzioni)
        esp_base = min(1.0, (barre_ese / n_ese) / barre_totali)

    eur_anno = None
    giudica_esito = "n/d (nessuna esecuzione)"
    criteri_falliti = None
    if n_ese:
        esito = Esito(
            nome=f"P11 vol-breakout k={config.k} m={config.m} [{etichetta}]",
            ritorni_netti=tuple(netti_ese), n_operazioni=n_ese,
            esposizione_media=esp_base, max_drawdown=e_port.max_drawdown,
            giorni_osservati=giorni, tariffa=get_tariffa(D.TARIFFA_ASSUNTA),
            tipo=D.TIPO_ORDINE,
            note=(f"P11: segnale vol-breakout ATR (k={config.k}, m={config.m}); "
                  "DD di portafoglio mark-to-market; nessun cap di concorrenza."))
        v = giudica(esito, capitale_riferimento=CAPITALE, soglia_eur_anno=SOGLIA_EUR_ANNO)
        eur_anno = v.statistiche.get("eur_anno")
        giudica_esito = v.esito
        criteri_falliti = v.statistiche.get("criteri_falliti")

    scheda = None
    if n_ese:
        scheda = scheda_economica(lordi_ese, netti_ese, pedaggio,
                                  costo_stress_extra=COSTO_STRESS_EXTRA)

    bench = None
    try:
        chiusure = {s: [b.chiusura for b in serie] for s, serie in finestra.items()}
        i_fin = min(len(c) for c in chiusure.values()) - 1
        bench = benchmark_equal_weight(chiusure, 0, i_fin)
    except Exception:
        bench = None

    dd_ok = e_port.max_drawdown <= 0.25
    ped_ok = exp is not None and exp >= 3.0 * pedaggio
    successo = bool(dd_ok and ped_ok)
    fallimenti = [m for m, cond in (("DDport>25%", dd_ok), ("exp<3x", ped_ok)) if not cond]

    righe.append(
        f"  [{etichetta}] n_ops(campione) {len(tutte)} | eseguite {e_port.operazioni_eseguite}"
        f" | saltate {e_port.operazioni_saltate} | rifiutate {e_port.operazioni_rifiutate}")
    righe.append(
        f"    dd_ser {_p(dd_ser)} | dd_port {_p(e_port.max_drawdown)}"
        f" | exp {_p(exp, 4)} | cop {_n(copertura, 1)}x | t {_n(t_c, 2)}"
        f" | t_nw {_n(t_nw, 2)} | stress {_p(exp_stress, 4)}")
    righe.append(
        f"    max_esp {_p(e_port.max_esposizione, 1)} | max_pos {e_port.max_posizioni}"
        f" | eur/anno {_n(eur_anno, 1)} | giudica {giudica_esito}"
        f"{' | fallisce: ' + ', '.join(map(str, criteri_falliti)) if criteri_falliti else ''}")
    if scheda:
        righe.append(
            f"    E1 scheda: cost_to_edge {_n(scheda['cost_to_edge'], 2)}"
            f" | cte_stress {_n(scheda['cost_to_edge_stress'], 2)}"
            f" | netto/stress medi {_p(scheda['netto_medio'], 3)}/{_p(scheda['netto_stress_medio'], 3)}")
    righe.append(f"    benchmark equal-weight finestra: {_p(bench)} | "
                 f"successo {'SI' if successo else 'NO'}"
                 f"{' | fallisce: ' + ', '.join(fallimenti) if fallimenti else ''}")

    return {
        "etichetta": etichetta, "config": {"k": config.k, "m": config.m, "atr_n": config.atr_n},
        "n_operazioni_campione": len(tutte),
        "eseguite": e_port.operazioni_eseguite, "saltate": e_port.operazioni_saltate,
        "rifiutate": e_port.operazioni_rifiutate,
        "dd_serializzato": dd_ser, "dd_portafoglio": e_port.max_drawdown,
        "expectancy": exp, "copertura_pedaggio": copertura,
        "expectancy_stress": exp_stress, "t_stat": t_c, "t_stat_newey_west": t_nw,
        "max_esposizione": e_port.max_esposizione, "max_posizioni": e_port.max_posizioni,
        "eur_anno": eur_anno, "giudica_esito": giudica_esito,
        "giudica_criteri_falliti": criteri_falliti,
        "scheda_e1": scheda, "benchmark_equal_weight": bench,
        "successo_dd25_exp3x": successo, "dd_ok": dd_ok, "pedaggio_ok": ped_ok,
        "fallimenti": fallimenti, "giorni": giorni,
    }


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    righe: list = []
    righe.append("P11 — VOLATILITY BREAKOUT ATR — misura e giudizio (portafoglio)")
    righe.append("(voce pre-registrata in prove/REGISTRO_ESPERIMENTI.md prima di questi numeri;")
    righe.append(" griglia dichiarata: {k: 1.0, 1.5, 2.0} x {m: 10, 20} = 6 varianti)")
    righe.append(f"pedaggio assunto: {_p(D.pedaggio())} per operazione "
                 f"({D.TARIFFA_ASSUNTA}, {D.TIPO_ORDINE}); "
                 f"slippage {_p(2 * D.SLIPPAGE_PER_LATO)} per giro")
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
        "segnale": "vol-breakout ATR (ingresso stretto su k*ATR%, uscita canale m)",
        "simboli": list(P3.SIMBOLI), "inizio": P3.INIZIO_STORIA, "fine": P3.FINE_STORIA,
        "confine": P3.CONFINE_ADDESTRAMENTO, "esposizione_base": ESPOSIZIONE_BASE,
        "capitale": CAPITALE, "griglia": [{"k": k, "m": m} for k, m in GRIGLIA],
        "n_varianti": len(GRIGLIA), "min_op_training": MIN_OP_TRAINING,
        "metrica_primaria": "DD di portafoglio mark-to-market",
        "successo": "DDport <= 25% E expectancy (eseguito) >= 3x pedaggio",
    }, "addestramento": None, "finestre": {}}

    righe.append("")
    righe.append(f"=== ADDESTRAMENTO [{P3.INIZIO_STORIA} -> {P3.CONFINE_ADDESTRAMENTO}) ===")
    scelta, tabella = allena(dati, i_confine, righe)
    riepilogo["addestramento"] = {"tabella": tabella, "scelta": scelta}

    if scelta is None:
        righe.append("  NESSUNA configurazione ammissibile (n >= 30) in addestramento:")
        righe.append("  misura non procedibile su verifica; si riporta e si ferma qui.")
        testo = "\n".join(righe)
        print(testo)
        (CARTELLA_PROVE / "P11_vol_breakout.txt").write_text(testo + "\n", encoding="utf-8")
        (CARTELLA_PROVE / "P11_vol_breakout.json").write_text(
            json.dumps(riepilogo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        return 0

    righe.append(f"  SCELTA (solo addestramento): k={_n(scelta['k'], 1)} m={scelta['m']} "
                 f"(n={scelta['n']}, exp netta {_p(scelta['expectancy_netta'], 4)})")
    config = V.Config(k=scelta["k"], m=scelta["m"], atr_n=ATR_N)

    for etichetta, i_da in ((f"VERIFICA [{P3.CONFINE_ADDESTRAMENTO} -> {P3.FINE_STORIA}]", i_confine),
                            (f"FINESTRA PIENA [{P3.INIZIO_STORIA} -> {P3.FINE_STORIA}]", 0)):
        righe.append("")
        righe.append(f"=== {etichetta} ===")
        esito_finestra = misura_finestra(etichetta, dati, i_da, config, righe)
        riepilogo["finestre"][etichetta] = esito_finestra

    verifica = next(v for k, v in riepilogo["finestre"].items() if k.startswith("VERIFICA"))
    righe.append("")
    righe.append("=== VERDETTO P11 (finestra del verdetto: VERIFICA) ===")
    if verifica["successo_dd25_exp3x"]:
        righe.append("  La configurazione scelta soddisfa DDport <= 25% E exp >= 3x pedaggio")
        righe.append("  -> la famiglia vol-breakout NON si archivia: merita l'analisi successiva.")
    else:
        righe.append("  La configurazione scelta NON soddisfa il criterio:")
        righe.append(f"  fallisce: {', '.join(verifica['fallimenti'])}")
        righe.append("  -> per la regola dichiarata, la famiglia si archivia per costruzione;")
        righe.append("  si prosegue con P12 o il filone funding (quando i dati maturano).")
    riepilogo["verdetto_p11"] = {
        "config": {"k": scelta["k"], "m": scelta["m"]},
        "successo": verifica["successo_dd25_exp3x"], "fallimenti": verifica["fallimenti"],
        "dd_port": verifica["dd_portafoglio"], "expectancy": verifica["expectancy"],
        "copertura_pedaggio": verifica["copertura_pedaggio"],
    }

    testo = "\n".join(righe)
    print(testo)
    (CARTELLA_PROVE / "P11_vol_breakout.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "P11_vol_breakout.json").write_text(
        json.dumps(riepilogo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"artefatti: {CARTELLA_PROVE / 'P11_vol_breakout.txt'} e .json "
          f"| runtime {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
