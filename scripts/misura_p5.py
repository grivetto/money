#!/usr/bin/env python3
"""P5 — Donchian puro su universo ESTESO (robustezza del t-stat).

Perche' esiste (nato dalla misura, non dalla speranza): sull'universo da 10 simboli il
Donchian puro (config 55/20) passa 6/8 criteri e cade solo su t=1,620 (vs 1,650) e DD 47%.
Il t e' funzione di n: con piu' simboli indipendenti la stima si stringe intorno alla media
vera SE l'edge e' reale. Questo e' un test di ROBUSTEZZA dichiarato prima del risultato:
l'universo lo decide la copertura (vedi `money.ricerca.universo`), non noi.

Uso:
    python scripts/misura_p5.py --solo-universo   # fase 1: congela l'universo
    python scripts/misura_p5.py                   # fase 1 + 2 (misura completa)

Fase 2: regola e protocollo IDENTICI al nodo I (nessun parametro nuovo): griglia 6 config
dichiarata, scelta in addestramento con n >= 30, verifica OOS col cancello, scenari tariffa.
"""
from __future__ import annotations

import argparse
import json
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

from money.dati import DatiSporchi, Scarica, a_ms  # noqa: E402
from money.ricerca import donchian_breakout as D  # noqa: E402
from money.ricerca import universo as U  # noqa: E402
from scripts.misura_catena_hermes import (  # noqa: E402
    CAPITALE_RIFERIMENTO, SOGLIA_EUR_ANNO, _iso, giudica_nodo, prima_dopo)

INIZIO_STORIA = "2020-10-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2024-06-01"
COPERTURA_MINIMA = 0.95
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"


def coppie_usdt_spot(cliente) -> list:
    """Tutte le coppie USDT spot ATTIVE di OKX EEA: chi entra lo decide la copertura."""
    mercati = cliente.load_markets()
    return sorted(m["symbol"] for m in mercati.values()
                  if m.get("spot") and m.get("quote") == "USDT" and m.get("active"))


def seleziona(scaricatore: Scarica, candidati: list, inizio: str, fine: str,
              copertura_minima: float):
    """Scarica e filtra: torna (dati, dettaglio). Un motivo scritto per ogni esclusa."""
    inizio_ms, fine_ms = a_ms(inizio), a_ms(fine)
    dati: dict = {}
    dettaglio: list = []
    for posizione, simbolo in enumerate(candidati, 1):
        prefisso = f"  [{posizione:>3}/{len(candidati)}]"
        try:
            serie = scaricatore.serie(simbolo, "1d", inizio, fine)
        except DatiSporchi as errore:
            testo = str(errore)
            if "serie vuota" in testo:
                # Prima pagina di paginazione vuota = nessun dato nei primi 300 giorni della
                # finestra (ccxt chiede [since, since+300d]): la coppia e' fuori per
                # costruzione (tolleranza 7 giorni), con un motivo vero al posto di un
                # errore di scarica.
                motivo = "storia corta oltre 300 giorni: nessun dato nella prima finestra"
            else:
                motivo = f"dati non verificati: {testo[:110]}"
            dettaglio.append({"simbolo": simbolo, "escluso": motivo})
            print(f"{prefisso} - {simbolo:14} {motivo}", flush=True)
            continue
        except Exception as errore:  # rete, simbolo sparito: esclusa, loggata
            motivo = f"{type(errore).__name__}: {str(errore)[:90]}"
            dettaglio.append({"simbolo": simbolo, "escluso": motivo})
            print(f"{prefisso} - {simbolo:14} {motivo}", flush=True)
            continue
        motivo = U.motivo_esclusione(serie, inizio_ms=inizio_ms, fine_ms=fine_ms,
                                     copertura_minima=copertura_minima)
        if motivo:
            dettaglio.append({"simbolo": simbolo, "escluso": motivo})
            print(f"{prefisso} - {simbolo:14} {motivo}", flush=True)
            continue
        copertura = U.copertura_finestra(serie, inizio_ms, fine_ms)
        dati[simbolo] = serie
        dettaglio.append({"simbolo": simbolo, "barre": len(serie),
                          "copertura": round(copertura, 4)})
        print(f"{prefisso} + {simbolo:14} {len(serie)} barre, copertura {copertura:.2%}",
              flush=True)
    return dati, dettaglio


def congela_universo(dati: dict, dettaglio: list, n_candidati: int) -> dict:
    freeze = {
        "finestra": [INIZIO_STORIA, FINE_STORIA],
        "copertura_minima": COPERTURA_MINIMA,
        "tolleranza_prima_barra_giorni": U.TOLLERANZA_MS // 86_400_000,
        "n_candidati": n_candidati,
        "n_inclusi": len(dati),
        "inclusi": sorted(dati),
        "dettaglio": dettaglio,
        "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    percorso = CARTELLA_PROVE / "P5_universo.json"
    percorso.write_text(json.dumps(freeze, indent=1, ensure_ascii=False), encoding="utf-8")
    return freeze


def main(argv=None) -> int:
    analizzatore = argparse.ArgumentParser(description="P5 — Donchian su universo esteso.")
    analizzatore.add_argument("--solo-universo", action="store_true",
                              help="ferma dopo il congelamento dell'universo")
    argomenti = analizzatore.parse_args(argv)
    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)

    scaricatore = Scarica()
    print(f"cache dati : {scaricatore.cartella_cache}")
    print(f"finestra   : {INIZIO_STORIA} -> {FINE_STORIA} (confine {CONFINE_ADDESTRAMENTO})")
    candidati = coppie_usdt_spot(scaricatore.cliente())
    print(f"candidati  : {len(candidati)} coppie USDT spot attive su OKX EEA")
    print(flush=True)

    dati, dettaglio = seleziona(scaricatore, candidati, INIZIO_STORIA, FINE_STORIA,
                                COPERTURA_MINIMA)
    freeze = congela_universo(dati, dettaglio, len(candidati))
    print(f"\nUNIVERSO CONGELATO: {freeze['n_inclusi']}/{freeze['n_candidati']} coppie "
          f"→ prove/P5_universo.json", flush=True)
    if not dati:
        print("universo vuoto: non si misura niente.")
        return 1
    if argomenti.solo_universo:
        print(f"(fermato dopo la fase 1 — {time.time() - t0:.0f}s)")
        return 0

    # --- Fase 2: misura (protocollo identico al nodo I) ----------------------
    i_confine = prima_dopo(dati, CONFINE_ADDESTRAMENTO)
    confine_reale = _iso(max(dati.values(), key=len)[i_confine].ts)
    righe_log: list = [
        f"P5 — Donchian puro su universo ESTESO ({len(dati)} coppie, {INIZIO_STORIA} -> "
        f"{FINE_STORIA}; confine {CONFINE_ADDESTRAMENTO} @ {confine_reale})",
        f"universo: {', '.join(sorted(dati))}",
        "(dettaglio selezioni: prove/P5_universo.json; criteri: money.ricerca.universo)",
    ]
    print(flush=True)
    nodo = giudica_nodo("P5_donchian_esteso", D, dati, i_confine, righe_log)
    nodo["meta"] = {
        "periodo": [INIZIO_STORIA, FINE_STORIA],
        "confine": CONFINE_ADDESTRAMENTO,
        "confine_reale_iso": confine_reale,
        "universo": sorted(dati),
        "n_universo": len(dati),
        "tariffa": D.TARIFFA_ASSUNTA, "tipo": D.TIPO_ORDINE,
        "slippage_per_lato": D.SLIPPAGE_PER_LATO,
        "esposizione": D.ESPOSIZIONE,
        "capitale_riferimento": CAPITALE_RIFERIMENTO,
        "soglia_eur_anno": SOGLIA_EUR_ANNO,
        "selezione": "copertura >= 95% finestra + prima barra entro 7 giorni "
                     "(vedi prove/P5_universo.json)",
    }
    testo = "\n".join(righe_log)
    print(testo)
    (CARTELLA_PROVE / "P5_donchian_esteso.txt").write_text(testo + "\n", encoding="utf-8")
    (CARTELLA_PROVE / "P5_donchian_esteso.json").write_text(
        json.dumps(nodo, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
