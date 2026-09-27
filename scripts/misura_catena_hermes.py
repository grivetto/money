#!/usr/bin/env python3
"""Catena parallela Hermes — nodi H (RSI mean reversion) e I (Donchian breakout), giornaliero.

PROTOCOLLO (identico ai nodi A-F, perche' il confronto fra nodi deve avere senso):
1. barre 1d reali da OKX EEA per l'universo primario (10 coppie EUR, dal 2023-12-01);
2. griglia dichiarata provata TUTTA in addestramento [2023-12-01, 2025-09-01), scelta per
   expectancy netta;
3. verifica su [2025-09-01, 2026-09-25), mai usata per scegliere;
4. `cancello.giudica` su capitale 1000 EUR, soglia 10 EUR/anno;
5. confronta_tariffe verso okx_eea_con_perp e okx_eea_swap_lv1 (le stesse operazioni,
   pedaggio diverso: separa "nessun edge" da "edge mangiato dal pedaggio");
6. verdetti e numeri in `prove/` (txt leggibile + json macchina).

Cosa NON fa: non ritocca la griglia dopo aver visto la verifica. Se archivia, archivia.
Uso: `python scripts/misura_catena_hermes.py` (scarica i dati la prima volta, poi cache).
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
        break

from money.cancello import confronta_tariffe, giudica  # noqa: E402
from money.costi import get_tariffa  # noqa: E402
from money.dati import Scarica, a_ms  # noqa: E402
from money.ricerca import donchian_breakout as D  # noqa: E402
from money.ricerca import rsi_mean_reversion as R  # noqa: E402

CAPITALE_RIFERIMENTO = 1000.0
SOGLIA_EUR_ANNO = 10.0
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"
TARIFFE_SCENARIO = ("okx_eea_con_perp", "okx_eea_swap_lv1")


def _p(x, cifre=3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}".replace(".", ",") + "%"


def _n(x, cifre=2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x:.{cifre}f}".replace(".", ",")


def _iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()


def carica(scaricatore: Scarica, simboli, timeframe: str, inizio: str, fine: str,
           copertura_minima: float) -> dict:
    fuori: dict = {}
    for simbolo in simboli:
        try:
            serie = scaricatore.serie(simbolo, timeframe, inizio, fine)
        except Exception as errore:
            print(f"  ! {simbolo:10}: {type(errore).__name__} {str(errore)[:70]}")
            continue
        copertura = R.copertura_barre(serie)
        if copertura < copertura_minima:
            print(f"  - {simbolo:10}: copertura {copertura:.1%} < {copertura_minima:.0%}, escluso")
            continue
        problemi = serie.verifica()
        if problemi:
            print(f"  ! {simbolo:10}: {len(problemi)} problemi di verifica, escluso")
            continue
        fuori[simbolo] = serie
        print(f"  + {simbolo:10}: {len(serie):5} barre, copertura {copertura:.1%}")
    return fuori


def prima_dopo(serie_per_simbolo: dict, istante_iso: str) -> int:
    limite = a_ms(istante_iso)
    lunga = max(serie_per_simbolo.values(), key=len)
    for i, barra in enumerate(lunga):
        if barra.ts >= limite:
            return i
    raise ValueError(f"{istante_iso} oltre la fine della serie")


def riassunto(v, esito) -> dict:
    s = v.statistiche
    ped = esito.pedaggio_per_operazione
    exp = s.get("expectancy")
    return {
        "verdetto": v.esito, "motivi": list(v.motivi),
        "operazioni": esito.n_operazioni,
        "giorni": round(esito.giorni_osservati, 1),
        "expectancy_netta": exp, "ic90": list(s.get("ic_bootstrap") or ()),
        "t_stat": s.get("t_stat"), "profit_factor": s.get("profit_factor"),
        "max_drawdown": esito.max_drawdown, "pedaggio": ped,
        "copertura_3x": (exp / ped) if (exp is not None and ped > 0) else None,
        "eur_anno": s.get("eur_anno"),
        "criteri_falliti": list(s.get("criteri_falliti", ())),
    }


def giudica_nodo(nome: str, modulo, dati: dict, i_confine: int, righe_log: list) -> dict:
    tariffa = get_tariffa(modulo.TARIFFA_ASSUNTA)

    righe_log.append(f"\n=== NODO {nome} — griglia completa in addestramento "
                     f"({len(modulo.GRIGLIA_ADDESTRAMENTO)} configurazioni) ===")
    config, tabella = modulo.scegli_config(dati, i_da=0, i_a=i_confine - 1,
                                           nome=f"addestramento {nome}", tariffa=tariffa)
    for riga in tabella:
        righe_log.append(f"  {str(riga['config']):<46} n={riga['n']:>4}  "
                         f"expectancy netta {_p(riga['expectancy_netta'], 4)}")
    righe_log.append(f"  SCELTA: {config}")

    esito_v = modulo.simula(dati, config, nome=f"{nome} [{config}] verifica",
                            tariffa=tariffa, i_da=i_confine)
    v = giudica(esito_v, capitale_riferimento=CAPITALE_RIFERIMENTO,
                soglia_eur_anno=SOGLIA_EUR_ANNO)
    rias = riassunto(v, esito_v)
    righe_log.append(f"\n  VERIFICA [confine -> {modulo.FINE_STORIA}]:")
    righe_log.append(f"    operazioni {rias['operazioni']} in {rias['giorni']} giorni | "
                     f"expectancy netta {_p(rias['expectancy_netta'], 4)} | "
                     f"pedaggio {_p(rias['pedaggio'], 3)} (copertura "
                     f"{_n(rias['copertura_3x'])}x, servono 3x)")
    righe_log.append(f"    IC90 {[_p(x, 4) for x in rias['ic90']]} | "
                     f"t {_n(rias['t_stat'])} | PF {_n(rias['profit_factor'])} | "
                     f"maxDD {_p(rias['max_drawdown'], 1)} | EUR/anno {_n(rias['eur_anno'])}")
    righe_log.append(f"    VERDETTO: {v.esito}")
    for m in v.motivi:
        righe_log.append(f"      - {m}")

    scenari: dict = {}
    for nome_tariffa in TARIFFE_SCENARIO:
        ct = confronta_tariffe(esito_v, modulo.TARIFFA_ASSUNTA, nome_tariffa,
                               capitale_riferimento=CAPITALE_RIFERIMENTO,
                               soglia_eur_anno=SOGLIA_EUR_ANNO)
        scenari[nome_tariffa] = {
            "verdetto": ct.verdetto_b.esito,
            "expectancy_netta": ct.verdetto_b.statistiche.get("expectancy"),
            "eur_anno": ct.verdetto_b.statistiche.get("eur_anno"),
        }
        righe_log.append(f"    scenario {nome_tariffa}: verdetto {ct.verdetto_b.esito}, "
                         f"expectancy {_p(ct.verdetto_b.statistiche.get('expectancy'), 4)}, "
                         f"EUR/anno {_n(ct.verdetto_b.statistiche.get('eur_anno'))}")

    return {
        "nodo": nome, "config_scelta": str(config),
        "griglia_n": len(modulo.GRIGLIA_ADDESTRAMENTO),
        "griglia": [{"config": str(r["config"]), "n": r["n"],
                     "expectancy_netta": r["expectancy_netta"]} for r in tabella],
        "verifica": rias, "scenari_tariffa": scenari,
    }


def main() -> int:
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    scaricatore = Scarica()
    print(f"cache dati: {scaricatore.cartella_cache}")
    print(f"universo: {len(R.SIMBOLI)} coppie EUR, 1d, "
          f"{R.INIZIO_STORIA} -> {R.FINE_STORIA}, confine {R.CONFINE_ADDESTRAMENTO}")

    dati = carica(scaricatore, R.SIMBOLI, "1d", R.INIZIO_STORIA, R.FINE_STORIA,
                  R.COPERTURA_MINIMA)
    if not dati:
        print("DATI INSUFFICIENTI: non si misura niente.")
        return 1
    i_confine = prima_dopo(dati, R.CONFINE_ADDESTRAMENTO)
    confine_reale = _iso(max(dati.values(), key=len)[i_confine].ts)
    print(f"confine effettivo: indice {i_confine} @ {confine_reale}")

    risultati: dict = {}
    for nome, modulo in (("H_rsi_mean_reversion", R), ("I_donchian_breakout", D)):
        righe_log: list = []
        esito_nodo = giudica_nodo(nome, modulo, dati, i_confine, righe_log)
        esito_nodo["meta"] = {
            "periodo": [modulo.INIZIO_STORIA, modulo.FINE_STORIA],
            "confine": modulo.CONFINE_ADDESTRAMENTO,
            "confine_reale_iso": confine_reale,
            "universo": sorted(dati.keys()),
            "tariffa": modulo.TARIFFA_ASSUNTA, "tipo": modulo.TIPO_ORDINE,
            "slippage_per_lato": modulo.SLIPPAGE_PER_LATO,
            "esposizione": modulo.ESPOSIZIONE,
            "capitale_riferimento": CAPITALE_RIFERIMENTO,
            "soglia_eur_anno": SOGLIA_EUR_ANNO,
        }
        risultati[nome] = esito_nodo
        testo = "\n".join(righe_log)
        print(testo)
        (CARTELLA_PROVE / f"{nome}.txt").write_text(testo + "\n", encoding="utf-8")
        (CARTELLA_PROVE / f"{nome}.json").write_text(
            json.dumps(esito_nodo, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8")

    print("\n=== QUADRO CATENA ===")
    for nome, r in risultati.items():
        v = r["verifica"]
        print(f"  {nome:<24} {v['verdetto']:<16} n={v['operazioni']:>4}  "
              f"exp {_p(v['expectancy_netta'], 4)}  copertura {_n(v['copertura_3x'])}x")
    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
