#!/usr/bin/env python3
"""Misura P2 — vol targeting sulle operazioni della famiglia canale (Donchian 55/20).

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P2 di prove/REGISTRO_ESPERIMENTI.md)
=========================================================================================
- Segnale FISSO: Donchian 55/20 sui 10 majors USDT (config dell'A/B P1, gia' misurata:
  +7,99%/op netto, DD serializzato 47,0%, DD portafoglio 42,84% sul controllo). NON si tocca.
- Griglia dichiarata: vol_target {0.50, 0.60, 0.75} x {sizing si, no} = 6 configurazioni
  (n_tentativi dichiarati). L'arm "sizing no" e' il controllo interno.
- Fattore per operazione: f = min(1, vol_target / (sigma20 * sqrt(365))) via
  `money.rischio.fattore_vol_target`, sigma20 = dev std campionaria dei rendimenti
  giornalieri FINO alla barra di decisione (solo passato). Fail-closed: f = 0 sotto 2 obs.
- Ritorni: allocazione = 0.25 * f * equity per operazione; pedaggio scalato con f
  (nozionale impegnato) => netto per unita' di equity = 0.25 * f * netto_base.
- Metrica PRIMARIA: DD di portafoglio mark-to-market (motore portafoglio.py).
  Secondarie: DD serializzato, expectancy, t-stat.
- Addendum 30/09 (prima dei numeri): stress costi (stack fee+spread+slippage x2),
  coerenza per regime di volatilita', attrattivita' (exp/DD) non peggiore del controllo.
- Successo (spec): DDport <= 25% E expectancy >= 3x pedaggio. Se il DD non scende sotto il
  25%, il filone trend si archivia per costruzione.

NIENTE viene aggiustato per far passare il verdetto. I numeri si stampano con le cifre
che hanno, non con quelle che servirebbero.

Uso: python scripts/misura_p2.py
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
from money.ricerca import donchian_breakout as D  # noqa: E402
from money.ricerca import p3_trend_filtro_200g as P3  # noqa: E402
from money.ricerca.portafoglio import backtest_portafoglio  # noqa: E402
from money.rischio import fattore_vol_target  # noqa: E402
from money.statistica import t_stat, t_stat_newey_west  # noqa: E402
from scripts.misura_catena_hermes import carica, prima_dopo  # noqa: E402

CONFIG = D.Config(55, 20)
VOL_TARGETS = (0.50, 0.60, 0.75)
ESPOSIZIONE_BASE = 0.25
CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
#: Stress costi: lo stack fee + spread/slippage di un'operazione, applicato una seconda
#: volta (costi x2). Dichiarato: e' il "terzo scenario" dell'addendum.
COSTO_STRESS_EXTRA = D.pedaggio() + 2.0 * D.SLIPPAGE_PER_LATO
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"

#: Riferimento interno: controllo atteso (dai misura dell'A/B e di portafoglio del 27-29/09).
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


def _ret_fino_a(chiuse, i):
    """Rendimenti giornalieri delle ultime 20 barre fino alla chiusura di i (inclusa)."""
    inizio = max(1, i - 19)
    return [chiuse[k] / chiuse[k - 1] - 1.0 for k in range(inizio, i + 1)]


def _sigma_ann(rs):
    if len(rs) < 2:
        return None
    n = len(rs)
    media = sum(rs) / n
    var = sum((r - media) ** 2 for r in rs) / (n - 1)
    if var <= 0:
        return None
    return math.sqrt(var) * math.sqrt(365.0)


def fattori_e_vol(barre, ops, vt):
    """f e vol annualizzata per ogni operazione (solo passato; fail-closed)."""
    chiuse = [b.chiusura for b in barre]
    fattori, vol_ann = {}, {}
    for o in ops:
        i_dec = o.indice_ingresso - 1
        rs = _ret_fino_a(chiuse, i_dec) if i_dec >= 1 else []
        fattori[o.indice_ingresso] = fattore_vol_target(
            rs, vol_target_annua=vt, periodi_anno=365.0)
        vol_ann[o.indice_ingresso] = _sigma_ann(rs)
    return fattori, vol_ann


def misura_finestra(etichetta, dati, i_da, righe):
    """Un giro completo su una finestra: controllo + 3 arm di sizing + secondarie."""
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

    barre_totali = max(len(s) for s in finestra.values())
    barre_dentro = sum(o.indice_uscita - o.indice_ingresso for o in tutte)
    esp_base = min(1.0, (barre_dentro / n_ops) / barre_totali) if n_ops else 0.0
    t_inizio = min(s[0].ts for s in finestra.values())
    t_fine = max(s[-1].ts for s in finestra.values())
    giorni = (t_fine - t_inizio) / 86_400_000.0

    # fattori e vol per i tre vol target (una volta per simbolo -> riuso in secondarie)
    fattori_vt, vol_per_simbolo = {}, {}
    for vt in VOL_TARGETS:
        fattori_vt[vt] = {}
        for simbolo, ops in ops_per_simbolo.items():
            f_map, v_map = fattori_e_vol(dati[simbolo], ops, vt)
            fattori_vt[vt][simbolo] = f_map
            vol_per_simbolo[simbolo] = v_map

    mediana_vol = None
    vols = [v for v_map in vol_per_simbolo.values() for v in v_map.values() if v]
    if vols:
        vols_ordinati = sorted(vols)
        mediana_vol = vols_ordinati[len(vols_ordinati) // 2]

    arm_list = [("sizing no (controllo)", None)] + [(f"vt={vt:.2f}", vt) for vt in VOL_TARGETS]
    risultati = []
    dd_port_controllo = None
    for nome_arm, vt in arm_list:
        campioni = []  # (ts_ingresso, netto_scalato, f, vol_ann, netto_base)
        for simbolo, ops in ops_per_simbolo.items():
            fmap = (fattori_vt[vt][simbolo] if vt is not None
                    else {o.indice_ingresso: 1.0 for o in ops})
            for o in ops:
                f = fmap[o.indice_ingresso]
                netto_base = D.ritorno_netto(o.ritorno_lordo)
                campioni.append((o.ts_ingresso, f * netto_base, f,
                                 vol_per_simbolo[simbolo][o.indice_ingresso], netto_base))
        campioni.sort(key=lambda t: t[0])
        netti = [r for _, r, _, _, _ in campioni]
        f_medio = sum(f for _, _, f, _, _ in campioni) / len(campioni)
        dd_ser, _ = D.curva_equity(netti, ESPOSIZIONE_BASE)

        if vt is None:
            e_port = backtest_portafoglio(finestra, ops_per_simbolo,
                                          esposizione=ESPOSIZIONE_BASE,
                                          netto_fn=netto_fn, capitale=CAPITALE)
        else:
            hook = (lambda s, o, _f=fattori_vt[vt]:
                    ESPOSIZIONE_BASE * _f[s][o.indice_ingresso])
            e_port = backtest_portafoglio(finestra, ops_per_simbolo,
                                          esposizione=ESPOSIZIONE_BASE,
                                          netto_fn=netto_fn, capitale=CAPITALE,
                                          esposizione_per_op=hook)
        if vt is None:
            dd_port_controllo = e_port.max_drawdown

        exp = sum(netti) / len(netti)
        copertura = exp / pedaggio
        exp_stress = sum(f * (nb - COSTO_STRESS_EXTRA)
                         for _, _, f, _, nb in campioni) / len(campioni)
        t_c = t_stat(netti)
        t_nw, _se_nw = t_stat_newey_west(netti)

        esito = Esito(
            nome=f"P2 Donchian55/20 {nome_arm} [{etichetta}]",
            ritorni_netti=tuple(netti), n_operazioni=len(netti),
            esposizione_media=esp_base * f_medio,
            max_drawdown=e_port.max_drawdown, giorni_osservati=giorni,
            tariffa=get_tariffa(D.TARIFFA_ASSUNTA), tipo=D.TIPO_ORDINE,
            note=(f"P2: segnale Donchian 55/20 fisso; arm {nome_arm}; "
                  f"allocazione {ESPOSIZIONE_BASE:.2f} x f per operazione; "
                  f"pedaggio scalato con f. Metriche con DD di portafoglio mark-to-market."))
        v = giudica(esito, capitale_riferimento=CAPITALE, soglia_eur_anno=SOGLIA_EUR_ANNO)

        dd_ok = e_port.max_drawdown <= 0.25
        ped_ok = exp >= 3.0 * pedaggio
        successo = bool(dd_ok and ped_ok)
        fallimenti = [m for m, cond in (("DDport>25%", dd_ok), ("exp<3x", ped_ok))
                      if not cond]
        rid_rel = (1.0 - e_port.max_drawdown / dd_port_controllo
                   if dd_port_controllo and dd_port_controllo > 0 else None)

        # coerenza per regime (addendum b): expectancy spezzata su vol alta/bassa
        exp_alta = [r for _, r, _, v_, _ in campioni if v_ and mediana_vol and v_ >= mediana_vol]
        exp_bassa = [r for _, r, _, v_, _ in campioni if v_ and mediana_vol and v_ < mediana_vol]
        exp_regime = {
            "alta": (sum(exp_alta) / len(exp_alta)) if exp_alta else None,
            "bassa": (sum(exp_bassa) / len(exp_bassa)) if exp_bassa else None,
        }

        righe.append(
            f"  {nome_arm:>22} | f medio {_n(f_medio, 2)} | dd_ser {_p(dd_ser):>9} | "
            f"dd_port {_p(e_port.max_drawdown):>9} | exp {_p(exp):>8} | "
            f"cop {_n(copertura, 1):>5}x | t {_n(t_c, 2):>5} | t_nw {_n(t_nw, 2):>5} | "
            f"eseg/salt {e_port.operazioni_eseguite}/{e_port.operazioni_saltate} | "
            f"rid_dd {_p(rid_rel, 1) if rid_rel is not None else 'n/d':>8} | "
            f"stress {_p(exp_stress):>8} | successo {'SI' if successo else 'NO'}"
            f" | fallisce: {', '.join(fallimenti) if fallimenti else '-'}"
            f" | giudica: {v.esito}")
        risultati.append({
            "arm": nome_arm, "vol_target": vt, "f_medio": f_medio,
            "dd_serializzato": dd_ser, "dd_portafoglio": e_port.max_drawdown,
            "expectancy": exp, "copertura_pedaggio": copertura,
            "t_stat": t_c, "t_stat_newey_west": t_nw,
            "eseguite": e_port.operazioni_eseguite, "saltate": e_port.operazioni_saltate,
            "riduzione_dd_relativa": rid_rel, "expectancy_stress": exp_stress,
            "expectancy_regime_alta_vol": exp_regime["alta"],
            "expectancy_regime_bassa_vol": exp_regime["bassa"],
            "successo_dd25_exp3x": successo, "dd_ok": dd_ok, "pedaggio_ok": ped_ok,
            "giudica_esito": v.esito,
            "giudica_criteri_falliti": v.statistiche.get("criteri_falliti"),
            "eur_anno": v.statistiche.get("eur_anno"),
            "max_esposizione": e_port.max_esposizione, "max_posizioni": e_port.max_posizioni,
        })

    # controllo vs riferimento
    controllo = risultati[0]
    rif = next((v for k, v in RIFERIMENTI.items() if etichetta.startswith(k)), None)
    check = "n/d"
    if rif:
        dd_s, dd_p, n_rif = rif
        ok = (abs(controllo["dd_serializzato"] - dd_s) < 0.005
              and abs(controllo["dd_portafoglio"] - dd_p) < 0.005
              and controllo["eseguite"] + controllo["saltate"] == n_rif)
        check = "OK" if ok else "DIFF! (controllo non riproduce il riferimento)"
    righe.append(f"  [check controllo vs riferimento A/B: {check}]")
    return {"etichetta": etichetta, "n_operazioni": n_ops, "giorni": giorni,
            "pedaggio": pedaggio, "mediana_vol_annua": mediana_vol,
            "check_riferimento": check, "arm": risultati}


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    righe: list = []
    righe.append("P2 — VOL TARGETING su Donchian 55/20 (10 majors USDT) — misura e giudizio")
    righe.append("(voce pre-registrata in prove/REGISTRO_ESPERIMENTI.md prima di questi numeri;")
    righe.append(" griglia dichiarata: vol_target {0.50,0.60,0.75} x {sizing si,no} = 6)")
    righe.append(f"pedaggio assunta: {_p(D.pedaggio())} per operazione "
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
        "config": str(CONFIG), "segno": "Donchian 55/20", "simboli": list(P3.SIMBOLI),
        "inizio": P3.INIZIO_STORIA, "fine": P3.FINE_STORIA,
        "confine": P3.CONFINE_ADDESTRAMENTO, "esposizione_base": ESPOSIZIONE_BASE,
        "capitale": CAPITALE, "vol_targets": list(VOL_TARGETS), "n_tentativi": 6,
        "metrica_primaria": "DD di portafoglio mark-to-market",
        "successo": "DDport <= 25% E expectancy >= 3x pedaggio",
    }, "finestre": {}}

    for etichetta, i_da in (("VERIFICA [2024-06-01 -> 2026-09-25]", i_confine),
                            ("FINESTRA PIENA [2020-10-01 -> 2026-09-25]", 0)):
        righe.append("")
        righe.append(f"=== {etichetta} ===")
        esito_finestra = misura_finestra(etichetta, dati, i_da, righe)
        riepilogo["finestre"][etichetta] = esito_finestra

    # verdetto sintetico sulla finestra del verdetto (VERIFICA)
    verifica = next(v for k, v in riepilogo["finestre"].items() if k.startswith("VERIFICA"))
    vincenti = [a["arm"] for a in verifica["arm"][1:] if a["successo_dd25_exp3x"]]
    righe.append("")
    righe.append("=== VERDETTO P2 (finestra del verdetto: VERIFICA) ===")
    if vincenti:
        righe.append(f"  Il sizing PORTA il DD di portafoglio sotto il 25% con: "
                     f"{', '.join(vincenti)} (expectancy ancora >= 3x pedaggio).")
        righe.append("  -> il filone trend NON si archivia per costruzione: esistono "
                     "configurazioni della griglia dichiarata che soddisfano il criterio.")
    else:
        righe.append("  NESSUNA configurazione della griglia dichiarata soddisfa "
                     "DDport <= 25% E exp >= 3x pedaggio.")
        righe.append("  -> per la regola dichiarata, il filone trend si archivia per "
                     "costruzione; si progettano spec nuove sui dati.")
    migliore = min(verifica["arm"][1:], key=lambda a: a["dd_portafoglio"])
    righe.append(f"  (migliore per DD: {migliore['arm']} con dd_port "
                 f"{_p(migliore['dd_portafoglio'])}, riduzione relativa "
                 f"{_p(migliore['riduzione_dd_relativa'], 1)} vs controllo; "
                 f"riferimento esterno non vincolante: 15-35%)")
    riepilogo["verdetto_p2"] = {"vincenti_verifica": vincenti,
                                "migliore_dd": migliore["arm"],
                                "migliore_dd_port": migliore["dd_portafoglio"]}

    testo = "\n".join(righe)
    print(testo)
    (CARTELLA_PROVE / "P2_vol_target.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "P2_vol_target.json").write_text(
        json.dumps(riepilogo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print()
    print(f"artefatti: {CARTELLA_PROVE / 'P2_vol_target.txt'} "
          f"e .json | runtime {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
