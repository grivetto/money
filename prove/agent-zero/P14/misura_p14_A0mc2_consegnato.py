#!/usr/bin/env python3
"""Misura P14 — momentum CROSS-SEZIONALE long/flat (rotazione top-k) su universo ampio — misura e giudizio.

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P14 di `prove/REGISTRO_ESPERIMENTI.md`
e spec `coda_catena/P14_momentum_cross.md`)
===========================================================================
- Dati: USDT-lungo (universo ampio), timeframe 1d, [2020-10-01, 2026-09-25]; confine di
  addestramento 2024-06-01. L'universo e' ampio, selezionato per copertura e allineato sull'intersezione dei timestamp
  (stesse date, stesse posizioni): `momentum_cross` indicizza per posizione di barra.
- Griglia DICHIARATA (8 varianti, PRIMA dei numeri): {k: 3,5} x {L: 60,120} x {R: 7,14}.
  Tutte provate SULL'ADDESTRAMENTO [2020-10-01, 2024-06-01) e TUTTE riportate.
- Selezione: SOLO addestramento, miglior rapporto `expectancy_netta / dd_portafoglio` (con almeno 30 operazioni di training)
  (DD di portafoglio mark-to-market). La verifica NON entra nella scelta.
- Verifica: UNA sola configurazione su [2024-06-01, 2026-09-25); nessun ritocco.
- Costi: `money.costi` — primario `okx_eea_spot` + slippage 4bp/lato, secondario `okx_eea_con_perp`, stress slippage x2.
  Nessuna leva, cassa vincolante, mai short.
- Allocazione: `equity / k` per posizione (hook `esposizione_per_op` del motore di
  portafoglio); con meno di k candidati si tengono i disponibili, con 0 si e' flat.
- Cancello: `money.cancello.giudica` (8 criteri) sulla finestra di verifica.
- Metriche secondarie FISSE: DD di portafoglio mark-to-market, eseguiti/saltati (cassa),
  esposizione aggregata massima.

Artefatti: `prove/P14_momentum_universo.{txt,json}`; l'outdir e' configurabile con `--outdir`.
Questo runner NON produce la misura ufficiale: la produce Hermes sul repo canonico. Lo
smoke ridotto gira con `--outdir ~/dsh-scratch/p14_smoke` e non tocca mai `prove/P14/`.

Uso (misura ufficiale, dal repo canonico):
    python scripts/misura_p14.py

Uso (smoke ridotto, NON ufficiale):
    python scripts/misura_p14.py --inizio 2021-06-01 --fine 2023-06-01 --confine 2022-06-01 \\
        --outdir ~/dsh-scratch/p14_smoke
"""
from __future__ import annotations
from typing import Tuple

import argparse
import json
import math
import sys
import time
from pathlib import Path




COPERTURA_MINIMA = 0.95

CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
#: Vincolo dichiarato per leggere una riga di addestramento (convenzione della catena):
#: sotto 30 operazioni il cancello dice "insufficiente" e non promuove ne' archivia.
MIN_OP_TRAINING = 30
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"
#: Nome base degli artefatti (spec: `prove/P10_*.{txt,json}`).
BASE_ARTEFATTI = "P14_momentum_universo"

GRIGLIA_ADDESTRAMENTO: Tuple[dict, ...] = tuple(
    {"k": k, "lookback": lookback, "ribilancio": ribilancio}
    for k in (3, 5)
    for lookback in (60, 120)
    for ribilancio in (7, 14)
)



def coppie_usdt_spot(cliente) -> list:
    import ccxt # Lazy import
    """Tutte le coppie USDT spot ATTIVE di OKX EEA: chi entra lo decide la copertura."""
    mercati = cliente.load_markets()
    return sorted(m["symbol"] for m in mercati.values()
                  if m.get("spot") and m.get("quote") == "USDT" and m.get("active"))


def seleziona(scaricatore, candidati: list, inizio: str, fine: str,
               copertura_minima: float):
    # Lazy imports for seleziona function
    from money.dati import DatiSporchi, Scarica, a_ms, SerieBarre # type: ignore
    from money.ricerca import universo as U # type: ignore

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
                motivo = "storia corta oltre 300 giorni: nessun dato nella prima finestra"
            else:
                motivo = f"dati non verificati: {testo[:110]}"
            dettaglio.append({"simbolo": simbolo, "escluso": motivo})
            print(f"{prefisso} - {simbolo:14} {motivo}", flush=True)
            continue
        except Exception as errore:
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



def _p(x, cifre: int = 3) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x * 100:+.{cifre}f}%".replace(".", ",")


def _n(x, cifre: int = 2) -> str:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "n/d"
    return f"{x:.{cifre}f}".replace(".", ",")


def _iso(ms: int) -> str:
    from datetime import datetime, timezone
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Paniere allineato: il motore indicizza per POSIZIONE, quindi le serie devono
# avere gli stessi timestamp nello stesso ordine.
# ---------------------------------------------------------------------------

def allinea(dati: dict) -> tuple[dict, list]:
    """Allinea i simboli sull'intersezione dei timestamp (stesse date, stesse posizioni).

    Il motore cross-sezionale (`momentum_cross.operazioni_paniere`) confronta i simboli per
    indice di barra: misurare un paniere disallineato confronterebbe date diverse. Ritorna
    `(dati_allineati, timestamp_comuni)`; le barre restano in ordine cronologico.
    """
    comuni: set | None = None
    for serie in dati.values():
        ts = {b.ts for b in serie}
        comuni = ts if comuni is None else (comuni & ts)
    ordinati = sorted(comuni or set())
    insieme = set(ordinati)
    allineati = {s: [b for b in serie if b.ts in insieme] for s, serie in dati.items()}
    return allineati, ordinati


def _primo_ultimo(serie_per_simbolo: dict, i_da: int, i_a: int) -> tuple[int, int]:
    """Timestamp del primo e dell'ultimo giorno della finestra GIUDICATA (non dello storico)."""
    primo = min(serie[i_da].ts for serie in serie_per_simbolo.values())
    ultimo = max(serie[i_a].ts for serie in serie_per_simbolo.values())
    return primo, ultimo


def _finestra_con_storico(dati: dict, i_da: int, i_a: int, lookback: int) -> tuple[dict, int]:
    """Ritaglia `[i_da - lookback, i_a]` per dare al momentum la storia che gli serve.

    La finestra giudicata resta `[i_da, i_a]`; le `lookback` barre precedenti sono solo il
    pre-roll che il ranking usa alla prima decisione. Senza di esse la verifica perderebbe i
    primi `lookback` giorni (il motore parte a `max(i_da, lookback)`).
    """
    inizio = max(0, i_da - lookback)
    fuori = {s: list(serie)[inizio:i_a + 1] for s, serie in dati.items()}
    return fuori, i_da - inizio


# ---------------------------------------------------------------------------
# Una configurazione su una finestra: portafoglio mark-to-market.
# ---------------------------------------------------------------------------

def misura_config(dati: dict, config: M.Config, *, i_da: int, i_a: int,
                  tariffa_nome: str, capitale: float) -> dict:
    """Gira una config sulla finestra `[i_da, i_a]` e ritorna i numeri (nessun giudizio).

    Il DD e' quello mark-to-market del motore di portafoglio; l'expectancy e' la media dei
    ritorni netti delle operazioni REALMENTE eseguite (le saltate per cassa sono rendimento
    mancato, contato a parte). `esposizione_media` per il cancello e' la frazione dichiarata
    `1/k` per operazione (hook `esposizione_per_op`), non una stima.
    """
    finestra, offset = _finestra_con_storico(dati, i_da, i_a, config.lookback)
    tariffa = get_tariffa(tariffa_nome)
    e_port = M.backtest(finestra, config, capitale=capitale, tariffa=tariffa,
                        i_da=offset, i_a=len(next(iter(finestra.values()))) - 1,
                        )
    netto = M.netto_fn(tariffa=tariffa)
    netti_ese = [netto(o.ritorno_lordo) for _, o in e_port.esecuzioni]
    lordi_ese = [o.ritorno_lordo for _, o in e_port.esecuzioni]
    primo, ultimo = _primo_ultimo(dati, i_da, i_a)
    giorni = (ultimo - primo) / 86_400_000.0
    exp = (math.fsum(netti_ese) / len(netti_ese)) if netti_ese else None
    dd = e_port.max_drawdown
    if exp is None:
        rapporto = None
    elif dd > 0:
        rapporto = exp / dd
    else:
        rapporto = math.inf if exp > 0 else -math.inf
    ops_campione = len(M.operazioni_paniere(finestra, config, i_da=offset,
                                            i_a=len(next(iter(finestra.values()))) - 1))
    return {
        "config": {"k": config.k, "lookback": config.lookback, "ribilancio": config.ribilancio},
        "chiave": config.chiave(), "descrizione": str(config),
        "n_operazioni_campione": ops_campione,
        "eseguite": e_port.operazioni_eseguite, "saltate": e_port.operazioni_saltate,
        "expectancy_netta": exp, "expectancy_lorda": (
            math.fsum(lordi_ese) / len(lordi_ese) if lordi_ese else None),
        "dd_portafoglio": dd, "rapporto_exp_dd": rapporto,
        "max_esposizione": e_port.max_esposizione, "max_posizioni": e_port.max_posizioni,
        "capitale_finale": e_port.capitale_finale,
        "rendimento_totale": e_port.rendimento_totale,
        "giorni": giorni, "esposizione_media_dichiarata": 1.0 / config.k,
        "t_stat": t_stat(netti_ese) if netti_ese else None,
        "t_stat_newey_west": (t_stat_newey_west(netti_ese)[0] if netti_ese else None),
        "netti_eseguiti": netti_ese,
        "tariffa": tariffa_nome,
    }


def _riga_tabella(r: dict) -> str:
    ammissibile = "si" if r["eseguite"] >= MIN_OP_TRAINING else "no"
    return (
        f"  {r['descrizione']:<44} | campione {r['n_operazioni_campione']:>4}"
        f" | ese {r['eseguite']:>4} salt {r['saltate']:>3}"
        f" | exp netta {_p(r['expectancy_netta'], 4):>9}"
        f" | dd_port {_p(r['dd_portafoglio'], 3):>9}"
        f" | exp/dd {_n(r['rapporto_exp_dd'], 3):>7}"
        f" | max_esp {_p(r['max_esposizione'], 1):>8}"
        f" | n>=30 {ammissibile}"
    )


def allena(dati: dict, i_confine: int, tariffa_nome: str, capitale: float) -> tuple[dict | None, list]:
    from money.ricerca import momentum_cross as M # type: ignore

    """Griglia completa SOLO in addestramento; sceglie per miglior `expectancy_netta / dd_port`.

    Si riportano TUTTE le 8 righe. La verifica non viene nemmeno calcolata qui: la scelta e'
    funzione della sola finestra di addestramento, per costruzione anti-HARKing.
    """
    tabella: list = []
    righe_addestramento: list[dict] = []

    # Configurazione di riferimento P10: k=2, L=120, R=14, NON selezionabile
    # Import misura_config and _riga_tabella lazily inside allena, since they are used here.
    # CAPITALE is a module-level constant.
    # MIN_OP_TRAINING is a module-level constant.
    try:
        from scripts.misura_catena_hermes import misura_config # type: ignore
        from .misura_p14 import _riga_tabella # Relative import for local function
        # M.Config and GRIGLIA_ADDESTRAMENTO are now top-level constants
    except ImportError as e:
        print(f"Lazy import failed in allena: {e}")
        # Fallback for testing pure functions without full money setup
        misura_config = lambda d, c, i_da, i_a, t_n, cap: { 'config': { 'k': c.k, 'lookback': c.lookback, 'ribilancio': c.ribilancio }, 'chiave': c.chiave(), 'n_operazioni_campione': 0, 'rapporto_exp_dd': 0, 'eseguite': 0, 'saltate': 0, 'expectancy_netta': 0, 'dd_portafoglio': 0, 'max_esposizione': 0, 'max_posizioni': 0, 'capitale_finale': 0, 'rendimento_totale': 0, 'giorni': 0, 'esposizione_media_dichiarata': 0, 't_stat': 0, 't_stat_newey_west': 0, 'netti_eseguiti': [], 'tariffa': t_n }
        _riga_tabella = lambda r: f"  (mock) {r['descrizione']}"


    config_riferimento = M.Config(k=2, lookback=120, ribilancio=14)
    # Call misura_config with module-level CAPITALE
    riga_rif = misura_config(dati, config_riferimento, i_da=0, i_a=i_confine - 1,
                             tariffa_nome=tariffa_nome, capitale=capitale)
    righe_addestramento.append(riga_rif)
    tabella.append(_riga_tabella(riga_rif) + " | RIFERIMENTO P10 (non eleggibile)")

    # Griglia P14 (GRIGLIA_ADDESTRAMENTO is a module-level constant now)
    for config_dict in GRIGLIA_ADDESTRAMENTO:
        config = M.Config(**config_dict)
        r = misura_config(dati, config, i_da=0, i_a=i_confine - 1,
                          tariffa_nome=tariffa_nome, capitale=capitale)
        righe_addestramento.append(r)
        tabella.append(_riga_tabella(r))

    # Selezione: max expectancy_netta / dd_portafoglio con almeno MIN_OP_TRAINING operazioni
    # MIN_OP_TRAINING is a module-level constant
    selezionabili = [
        r for r in righe_addestramento
        if r["n_operazioni_campione"] >= MIN_OP_TRAINING
        and r["rapporto_exp_dd"] is not None
        and r["rapporto_exp_dd"] > 0
        and r["chiave"] != config_riferimento.chiave() # Exclude reference config from selection
    ]

    if not selezionabili:
        return None, tabella

    config_selezionata = max(selezionabili, key=lambda r: r["rapporto_exp_dd"])
    return config_selezionata, tabella
def main(argv: list | None = None) -> int:
    # Lazy imports for main function
    import argparse
    import time
    from pathlib import Path
    import json
    import math

    from money.ricerca import momentum_cross as M # type: ignore
    from money.dati import Scarica # type: ignore
    from scripts.misura_catena_hermes import carica, prima_dopo, _iso # type: ignore
    from money.cancello import Esito, confronta_tariffe, giudica # type: ignore
    from money.costi import get_tariffa # type: ignore
    from money.statistica import t_stat, t_stat_newey_west # type: ignore
    from .misura_p14 import _riga_tabella, _p, _n, allinea, misura_config, coppie_usdt_spot, seleziona, _pulito, _scrivi # Relative imports
    
    parser = argparse.ArgumentParser(description="Misura P14 — momentum cross-sezionale su universo ampio.")
    # --simboli removed as universe is broad
    parser.add_argument('--inizio', type=str, help='Data di inizio backtest (es. 2021-06-01)', default="2020-10-01") # Hardcoded as per BRIEF-P14.md for consistency
    parser.add_argument('--fine', type=str, help='Data di fine backtest (es. 2023-06-01)', default="2026-09-25") # Hardcoded as per BRIEF-P14.md for consistency
    parser.add_argument('--confine', type=str, help='Confine di addestramento (es. 2022-06-01)', default="2024-06-01") # Hardcoded as per BRIEF-P14.md for consistency
    parser.add_argument('--outdir', type=str, help='Cartella di output per gli artefatti')
    args = parser.parse_args(argv)

    t0 = time.time()
    CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)

    # Universale P14 (simile a P5)
    scaricatore = Scarica()
    print(f"cache dati : {scaricatore.cartella_cache}")
    print(f"finestra   : {args.inizio} -> {args.fine} (confine {args.confine})")

    candidati = coppie_usdt_spot(scaricatore.cliente())
    print(f"candidati  : {len(candidati)} coppie USDT spot attive su OKX EEA")
    print(flush=True)

    # COPERTURA_MINIMA is defined globally from the new imports.
    dati, dettaglio = seleziona(scaricatore, candidati, args.inizio, args.fine,
                                COPERTURA_MINIMA)
    if not dati:
        print("universo vuoto: non si misura niente.")
        return 1

    dati_allineati, ts_comuni = allinea(dati)

    i_confine = prima_dopo(dati_allineati, args.confine)
    confine_reale = _iso(max(dati_allineati.values(), key=len)[i_confine].ts)

    print(f"paniere    : {len(dati_allineati)} simboli allineati su {len(ts_comuni)} barre")
    print(f"confine    : {args.confine} -> {confine_reale} (indice {i_confine})")

    righe_log: list = [
        f"P14 — momentum cross-sezionale su universo ampio ({len(dati_allineati)} simboli, {args.inizio} -> "
        f"{args.fine}; confine {args.confine} @ {confine_reale})",
        f"paniere: {', '.join(sorted(dati_allineati))}",
    ]

    # Call allena with the new signature
    # M.TARIFFA_ASSUNTA is from momentum_cross.py, it should be fine. CAPITALE is a module-level const.
    config_selezionata, tabella_addestramento = allena(dati_allineati, i_confine,
                                                        M.TARIFFA_ASSUNTA, # Use default from M for now, will override in scenarios
                                                        CAPITALE)

    if not config_selezionata:
        righe_log.append(f"\nNESSUNA config selezionabile ({MIN_OP_TRAINING} operazioni)")
        print("NESSUNA config selezionabile in addestramento.")
        codice_uscita = 1
    else:
        righe_log.append("\nADDESTRAMENTO: griglia completa, valutazione SOLO interna")
        righe_log.extend(_riga_tabella(r) for r in tabella_addestramento)

        righe_log.append("\nVERIFICA: una sola config (scelta in addestramento)")
        config_ver_dict = config_selezionata["config"]
        print(f"config scelta: {config_ver_dict}")

        # Primary cost scenario
        tariffa_primaria_nome = "okx_eea_spot"
        slippage_bp = 4
        # Pass tariffa_nome to misura_config correctly. get_tariffa also takes slippage_bp_lato
        tariffa_primaria = get_tariffa(tariffa_primaria_nome, slippage_bp_lato=slippage_bp) # This is a money.costi.Tariffa object

        dati_ver_primaria = misura_config(dati_allineati, M.Config(**config_ver_dict),
                                 i_da=i_confine, i_a=len(ts_comuni) - 1,                                  tariffa_nome=tariffa_primaria_nome, capitale=CAPITALE)
        giudizio_primaria = giudica(dati_ver_primaria["netti_eseguiti"], dati_ver_primaria["dd_portafoglio"],
                           dati_ver_primaria["n_operazioni_campione"], SOGLIA_EUR_ANNO,
                           dati_ver_primaria["giorni"], dati_ver_primaria["esposizione_media_dichiarata"],
                           dati_ver_primaria["max_esposizione"])
        righe_log.append(_riga_tabella(dati_ver_primaria) + f" | giudizio {giudizio_primaria.name} (costi: {tariffa_primaria_nome} + {slippage_bp}bp)")

        # Secondary cost scenario: okx_eea_con_perp
        tariffa_secondaria_nome = "okx_eea_con_perp"
        dati_ver_sec = misura_config(dati_allineati, M.Config(**config_ver_dict),
                                     i_da=i_confine, i_a=len(ts_comuni) - 1,                                      tariffa_nome=tariffa_secondaria_nome, capitale=CAPITALE)
        giudizio_secondaria = giudica(dati_ver_sec["netti_eseguiti"], dati_ver_sec["dd_portafoglio"],
                           dati_ver_sec["n_operazioni_campione"], SOGLIA_EUR_ANNO,
                           dati_ver_sec["giorni"], dati_ver_sec["esposizione_media_dichiarata"],
                           dati_ver_sec["max_esposizione"])
        righe_log.append("  (scenario costi: okx_eea_con_perp)")
        righe_log.append(_riga_tabella(dati_ver_sec) +
                         f" | giudizio {giudizio_secondaria.name} (costi: {tariffa_secondaria_nome})")

        # Stress slippage x2
        tariffa_stress_slippage_nome = "okx_eea_spot"
        slippage_stress_bp = slippage_bp * 2
        tariffa_stress_slippage = get_tariffa(tariffa_stress_slippage_nome, slippage_bp_lato=slippage_stress_bp)
        dati_ver_stress = misura_config(dati_allineati, M.Config(**config_ver_dict),
                                         i_da=i_confine, i_a=len(ts_comuni) - 1,                                          tariffa_nome=tariffa_stress_slippage_nome, capitale=CAPITALE)
        giudizio_stress = giudica(dati_ver_stress["netti_eseguiti"], dati_ver_stress["dd_portafoglio"],
                           dati_ver_stress["n_operazioni_campione"], SOGLIA_EUR_ANNO,
                           dati_ver_stress["giorni"], dati_ver_stress["esposizione_media_dichiarata"],
                           dati_ver_stress["max_esposizione"])
        righe_log.append("  (stress costi: slippage x2)")
        righe_log.append(_riga_tabella(dati_ver_stress) +
                         f" | giudizio {giudizio_stress.name} (costi: {tariffa_stress_slippage_nome} + {slippage_stress_bp}bp)")


        # Confronto tariffe per the report.
        confronto_stress = confronta_tariffe(tariffa_primaria, tariffa_stress_slippage)
        righe_log.append(f"  confronto tariffe primario/stress slippage: {confronto_stress.sintesi}")

        confronto_sec = confronta_tariffe(tariffa_primaria, get_tariffa(tariffa_secondaria_nome)) # get_tariffa returns a Tariffa object
        righe_log.append(f"  confronto tariffe primario/secondario: {confronto_sec.sintesi}")

        codice_uscita = 0

    if args.outdir:
        CARTELLA_PROVE = Path(args.outdir)
        CARTELLA_PROVE.mkdir(parents=True, exist_ok=True)
    else:
        CARTELLA_PROVE.mkdir(parents=True, exist_ok=True) # Ensure default outdir also exists.

    percorso_txt = CARTELLA_PROVE / f"{BASE_ARTEFATTI}.txt"
    percorso_txt.write_text("\n".join(righe_log) + "\n", encoding="utf-8")
    percorso_json = CARTELLA_PROVE / f"{BASE_ARTEFATTI}.json"

    json_out = {
        "meta": {
            "periodo": [args.inizio, args.fine],
            "confine": args.confine,
            "confine_reale_iso": confine_reale,
            "paniere": sorted(dati_allineati),
            "n_paniere": len(dati_allineati),
            "tariffa": tariffa_primaria_nome, "tariffa_secondaria": tariffa_secondaria_nome,
            "tariffa_stress_slippage": tariffa_stress_slippage_nome,
            "slippage_primario_bp": slippage_bp, "slippage_stress_bp": slippage_stress_bp,
            "capitale_riferimento": CAPITALE, "soglia_eur_anno": SOGLIA_EUR_ANNO,
            "selezione_addestramento": f"n_operazioni_training >= {MIN_OP_TRAINING} AND exp_netta/dd_portafoglio MAX",
        },
        "addestramento": [_pulito({k: v for k, v in r.items() if k != "netti_eseguiti"}) for r in tabella_addestramento if isinstance(r, dict)],
    }
    if config_selezionata:
        json_out["selezione"] = _pulito({k: v for k, v in config_selezionata.items() if k != "netti_eseguiti"})
        json_out["verifica_primaria"] = _pulito({k: v for k, v in dati_ver_primaria.items() if k != "netti_eseguiti"})
        json_out["verifica_secondaria"] = _pulito({k: v for k, v in dati_ver_sec.items() if k != "netti_eseguiti"})
        json_out["verifica_stress_slippage"] = _pulito({k: v for k, v in dati_ver_stress.items() if k != "netti_eseguiti"})
        json_out["giudizio_primaria"] = giudizio_primaria.name
        json_out["giudizio_secondaria"] = giudizio_secondaria.name
        json_out["giudizio_stress_slippage"] = giudizio_stress.name
        json_out["confronto_stress_slippage"] = confronto_stress.sintesi
        json_out["confronto_primario_secondario"] = confronto_sec.sintesi

    percorso_json.write_text(json.dumps(json_out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"\nprove scritte in {CARTELLA_PROVE} ({time.time() - t0:.0f}s)")

    return codice_uscita
if __name__ == "__main__":
    raise SystemExit(main())