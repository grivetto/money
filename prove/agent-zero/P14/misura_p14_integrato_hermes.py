#!/usr/bin/env python3
"""Misura P14 — momentum CROSS-SEZIONALE long/flat (rotazione top-k) su universo ampio — misura e giudizio.

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P14 di `prove/REGISTRO_ESPERIMENTI.md`
e spec `coda_catena/P14_momentum_universo.md`)
===========================================================================
- Dati: USDT-lungo su UNIVERSO AMPIO (coppie con copertura >=95% sulla finestra, selettore
  `money.ricerca.universo` — lo stesso criterio di P5), timeframe 1d, [2020-10-01, 2026-09-25];
  confine di addestramento 2024-06-01. Il paniere viene ALLINEATO sull'intersezione dei
  timestamp (stesse date, stesse posizioni): `momentum_cross` indicizza per posizione di barra.
- Griglia DICHIARATA (8 varianti, PRIMA dei numeri): {k: 3,5} x {L: 60,120} x {R: 7,14}.
  Tutte provate SULL'ADDESTRAMENTO [2020-10-01, 2024-06-01) e TUTTE riportate.
- Riga di riferimento NON selezionabile: la config scelta in P10 (k=2, L=120, R=14) valutata
  sullo stesso universo — solo confronto, fuori dalla selezione.
- Selezione: SOLO addestramento, miglior rapporto `expectancy_netta / dd_portafoglio`
  (candidabilita': >= 30 operazioni eseguite in addestramento; DD di portafoglio mark-to-market).
  La verifica NON entra nella scelta.
- Verifica: UNA sola configurazione su [2024-06-01, 2026-09-25); nessun ritocco.
- Costi: `money.costi` — primario `okx_eea_spot` misto + slippage 4 bp/lato (come P10),
  secondario `okx_eea_con_perp`, stress slippage x2 (8 bp/lato). Nessuna leva, cassa
  vincolante, mai short.
- Allocazione: `equity / k` per posizione (motore di portafoglio); con meno di k candidati si
  tengono i disponibili, con 0 si e' flat.
- Cancello: `money.cancello.giudica` (8 criteri) sulla finestra di verifica, nei tre scenari
  (primario, secondario, stress); confronto tariffe con `money.cancello.confronta_tariffe`.
- Metriche secondarie FISSE: DD di portafoglio mark-to-market, eseguiti/saltati (cassa),
  esposizione aggregata massima, n. simboli effettivamente presenti nell'universo.

Artefatti: `prove/P14_momentum_universo.{txt,json}`; l'outdir e' configurabile con `--outdir`.
Lo smoke ridotto gira con `--inizio/--fine/--confine` accorciati e `--outdir` NON canonico
(in quel caso la finestra non e' quella della spec e gli artefatti non vanno in `prove/`).

Uso (misura ufficiale, dal repo canonico):
    python scripts/misura_p14.py

Uso (smoke ridotto, NON ufficiale):
    python scripts/misura_p14.py --inizio 2021-06-01 --fine 2023-06-01 --confine 2022-06-01 \\
        --outdir ~/dsh-scratch/p14_smoke
"""
from __future__ import annotations

import argparse
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
        if str(_antenato) not in sys.path:          # radice repo: serve per `import scripts.*`
            sys.path.insert(0, str(_antenato))
        break

from money.cancello import Esito, confronta_tariffe, giudica  # noqa: E402
from money.costi import get_tariffa  # noqa: E402
from money.dati import DatiSporchi, Scarica, a_ms  # noqa: E402
from money.ricerca import momentum_cross as M  # noqa: E402
from money.ricerca import universo as U  # noqa: E402
from money.statistica import t_stat, t_stat_newey_west  # noqa: E402
from scripts.misura_catena_hermes import prima_dopo  # noqa: E402

CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
#: Vincolo dichiarato per candidare una variante (convenzione della catena): sotto 30
#: operazioni il cancello direbbe "insufficiente" — la variante non e' candidabile.
MIN_OP_TRAINING = 30
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"
#: Nome base degli artefatti (spec: `prove/P14_*.{txt,json}`).
BASE_ARTEFATTI = "P14_momentum_universo"

INIZIO_STORIA = "2020-10-01"
FINE_STORIA = "2026-09-25"
CONFINE_ADDESTRAMENTO = "2024-06-01"
COPERTURA_MINIMA = 0.95

#: Costi dichiarati: primario spot misto + 4 bp/lato; secondario con_perp; stress x2.
TARIFFA_PRIMARIA = "okx_eea_spot"
TARIFFA_SECONDARIA = "okx_eea_con_perp"
SLIPPAGE_BP_LATO = 0.0004
SLIPPAGE_STRESS_LATO = SLIPPAGE_BP_LATO * 2

#: Griglia P14 DICHIARATA (8 varianti, PRIMA dei numeri).
GRIGLIA_ADDESTRAMENTO: tuple[dict, ...] = tuple(
    {"k": k, "lookback": lookback, "ribilancio": ribilancio}
    for k in (3, 5)
    for lookback in (60, 120)
    for ribilancio in (7, 14)
)
#: Riferimento NON selezionabile: la config scelta in P10.
CONFIG_RIFERIMENTO: dict = {"k": 2, "lookback": 120, "ribilancio": 14}


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
                  tariffa_nome: str, capitale: float,
                  slippage_per_lato: float = SLIPPAGE_BP_LATO) -> dict:
    """Gira una config sulla finestra `[i_da, i_a]` e ritorna i numeri (nessun giudizio).

    Il DD e' quello mark-to-market del motore di portafoglio; l'expectancy e' la media dei
    ritorni netti delle operazioni REALMENTE eseguite (le saltate per cassa sono rendimento
    mancato, contato a parte). `esposizione_media` per il cancello e' la frazione dichiarata
    `1/k` per operazione, non una stima. `slippage_per_lato` entra SIA nel backtest SIA nel
    netto_fn (stessa verita' sui costi: lo scenario di stress raddoppia il valore).
    """
    finestra, offset = _finestra_con_storico(dati, i_da, i_a, config.lookback)
    tariffa = get_tariffa(tariffa_nome)
    e_port = M.backtest(finestra, config, capitale=capitale, tariffa=tariffa,
                        slippage_per_lato=slippage_per_lato,
                        i_da=offset, i_a=len(next(iter(finestra.values()))) - 1,
                        )
    netto = M.netto_fn(tariffa=tariffa, slippage_per_lato=slippage_per_lato)
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


def allena(dati: dict, i_confine: int, tariffa_nome: str, capitale: float,
           slippage_per_lato: float = SLIPPAGE_BP_LATO):
    """Griglia completa + riga di riferimento, SOLO in addestramento.

    Si riportano TUTTE le righe (riferimento + 8 varianti). La selezione sceglie per miglior
    `expectancy_netta / dd_portafoglio` con almeno `MIN_OP_TRAINING` operazioni eseguite in
    addestramento. La riga di riferimento (config P10) NON e' mai candidabile: sta fuori
    dalla lista dei candidati per costruzione. La verifica non viene nemmeno calcolata qui:
    la scelta e' funzione della sola finestra di addestramento (anti-HARKing).

    Ritorna `(scelta | None, righe_render, righe_dati, riferimento)`.
    """
    righe: list = []
    dati_righe: list[dict] = []
    rif = misura_config(dati, M.Config(**CONFIG_RIFERIMENTO), i_da=0, i_a=i_confine - 1,
                        tariffa_nome=tariffa_nome, capitale=capitale,
                        slippage_per_lato=slippage_per_lato)
    righe.append(_riga_tabella(rif) + " | RIFERIMENTO P10 (non eleggibile)")
    for parametri in GRIGLIA_ADDESTRAMENTO:
        r = misura_config(dati, M.Config(**parametri), i_da=0, i_a=i_confine - 1,
                          tariffa_nome=tariffa_nome, capitale=capitale,
                          slippage_per_lato=slippage_per_lato)
        dati_righe.append(r)
        righe.append(_riga_tabella(r))
    candidabili = [
        r for r in dati_righe
        if r["eseguite"] >= MIN_OP_TRAINING
        and r["rapporto_exp_dd"] is not None
        and not (isinstance(r["rapporto_exp_dd"], float)
                 and math.isnan(r["rapporto_exp_dd"]))
        and r["rapporto_exp_dd"] > 0
    ]
    if not candidabili:
        return None, righe, dati_righe, rif
    scelta = max(candidabili, key=lambda r: r["rapporto_exp_dd"])
    return scelta, righe, dati_righe, rif


def verifica(dati: dict, config: M.Config, *, i_da: int, i_a: int,
             tariffa_nome: str, capitale: float, etichetta: str,
             slippage_per_lato: float = SLIPPAGE_BP_LATO) -> dict:
    """UNA verifica: misura + giudizio a 8 criteri sulla finestra (nessun ritocco)."""
    r = misura_config(dati, config, i_da=i_da, i_a=i_a,
                      tariffa_nome=tariffa_nome, capitale=capitale,
                      slippage_per_lato=slippage_per_lato)
    netti = tuple(r["netti_eseguiti"])
    esito = Esito(
        nome=f"P14 momentum cross-universo {config} [{etichetta}]",
        ritorni_netti=netti, n_operazioni=len(netti),
        esposizione_media=1.0 / config.k, max_drawdown=r["dd_portafoglio"],
        giorni_osservati=r["giorni"], tariffa=get_tariffa(tariffa_nome), tipo=M.TIPO_ORDINE,
        note=(f"P14: rotazione top-{config.k}, momentum {config.lookback}g, ribilancio "
              f"{config.ribilancio}g; allocazione equity/{config.k}; DD portafoglio MTM; "
              f"costi {tariffa_nome} misto + {_p(slippage_per_lato, 2)}/lato."),
    )
    v = giudica(esito, capitale_riferimento=capitale, soglia_eur_anno=SOGLIA_EUR_ANNO)
    return {"misura": r, "esito": esito, "verdetto": v}


def _blocchi_verifica(ris: dict, righe: list, etichetta: str) -> None:
    r = ris["misura"]
    v = ris["verdetto"]
    righe.append(f"  [{etichetta}] configurazione CONGELATA: {r['descrizione']}")
    righe.append(f"  [{etichetta}] operazioni: campione {r['n_operazioni_campione']} | eseguite "
                 f"{r['eseguite']} | saltate {r['saltate']} (cassa)")
    righe.append(f"  [{etichetta}] expectancy netta {_p(r['expectancy_netta'], 4)} | DD portafoglio "
                 f"MTM {_p(r['dd_portafoglio'], 3)} | esposizione max "
                 f"{_p(r['max_esposizione'], 1)} | max posizioni {r['max_posizioni']}")
    righe.append(f"  [{etichetta}] t-stat {_n(r['t_stat'], 2)} | t-stat Newey-West "
                 f"{_n(r['t_stat_newey_west'], 2)} | capitale finale "
                 f"{_n(r['capitale_finale'], 2)} EUR | giorni {_n(r['giorni'], 1)}")
    criteri = v.statistiche.get("criteri", {})
    if criteri:
        righe.append("  CRITERI (8): " + " | ".join(
            f"{nome}={'ok' if ok else 'KO'}" for nome, ok in criteri.items()))
    else:
        righe.append("  CRITERI (8): non valutati — il verdetto si e' fermato prima "
                     "(serie vuota, degenere o numerosita' < 30)")
    righe.append(f"  VERDETTO ({etichetta}): {v.esito}")
    for motivo in v.motivi:
        righe.append(f"    - {motivo}")


def _riepilogo_verifica(ris: dict) -> dict:
    """Blocco JSON per una verifica (stile P10, senza i netti per-operazione)."""
    v = ris["verdetto"]
    return {
        "misura": _pulito({k: vv for k, vv in ris["misura"].items() if k != "netti_eseguiti"}),
        "verdetto": v.esito, "motivi": list(v.motivi),
        "criteri": dict(v.statistiche.get("criteri", {})),
        "criteri_falliti": list(v.statistiche.get("criteri_falliti", ())),
        "statistiche_cancello": {
            "expectancy": v.statistiche.get("expectancy"),
            "ic90": list(v.statistiche.get("ic_bootstrap") or ()),
            "t_stat": v.statistiche.get("t_stat"),
            "profit_factor": v.statistiche.get("profit_factor"),
            "max_drawdown": v.statistiche.get("max_drawdown"),
            "esposizione_media": v.statistiche.get("esposizione_media"),
            "eur_anno": v.statistiche.get("eur_anno"),
            "pedaggio_per_operazione": v.statistiche.get("pedaggio_per_operazione"),
        },
    }


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Misura P14 — momentum cross-section long/flat su universo ampio")
    parser.add_argument("--outdir", default=None,
                        help="cartella artefatti (default: <repo>/prove)")
    parser.add_argument("--inizio", default=INIZIO_STORIA)
    parser.add_argument("--fine", default=FINE_STORIA)
    parser.add_argument("--confine", default=CONFINE_ADDESTRAMENTO)
    parser.add_argument("--cache", default=None,
                        help="cartella cache dati (default: repo/data/cache)")
    args = parser.parse_args(argv)

    outdir = Path(args.outdir).expanduser() if args.outdir else CARTELLA_PROVE
    outdir.mkdir(parents=True, exist_ok=True)
    tariffa_nome = TARIFFA_PRIMARIA

    t0 = time.time()
    righe: list = []
    righe.append("P14 — MOMENTUM CROSS-SECTIONAL long/flat su UNIVERSO AMPIO — misura e giudizio")
    righe.append("(voce pre-registrata; griglia {k:3,5} x {L:60,120} x {R:7,14} = 8 varianti; "
                 "riferimento P10 k=2 L=120 R=14 NON selezionabile)")
    righe.append(f"periodo {args.inizio} -> {args.fine} | confine addestramento {args.confine}")
    righe.append(f"costi: {tariffa_nome} misto + {_p(SLIPPAGE_BP_LATO, 2)}/lato "
                 f"(secondario {TARIFFA_SECONDARIA}; stress slippage x2 = "
                 f"{_p(SLIPPAGE_STRESS_LATO, 2)}/lato); capitale {_n(CAPITALE, 0)} EUR; "
                 f"allocazione equity/k; mai leva, mai short")
    if args.outdir:
        righe.append("(ESECUZIONE RIDOTTA/NON UFFICIALE: outdir non canonico)")

    scaricatore = Scarica(args.cache)
    righe.append(f"cache dati: {scaricatore.cartella_cache}")
    candidati = coppie_usdt_spot(scaricatore.cliente())
    righe.append(f"candidati: {len(candidati)} coppie USDT spot attive su OKX EEA")
    print(righe[-2], flush=True)
    print(righe[-1], flush=True)
    dati, dettaglio = seleziona(scaricatore, candidati, args.inizio, args.fine,
                                COPERTURA_MINIMA)
    if len(dati) < 2:
        righe.append(f"UNIVERSO INSUFFICIENTE: {len(dati)} coppie con copertura "
                     f">= {COPERTURA_MINIMA:.0%} nella finestra.")
        _scrivi(outdir, righe, {"errore": "universo insufficiente", "n_universo": len(dati),
                                "dettaglio": dettaglio})
        return 1
    dati, ts = allinea(dati)
    n_barre = len(ts)
    i_confine = prima_dopo(dati, args.confine)
    righe.append(f"universo: {len(dati)} simboli x {n_barre} barre comuni "
                 f"({_iso(ts[0])} -> {_iso(ts[-1])}); confine reale indice {i_confine} "
                 f"@ {_iso(ts[i_confine])}")

    riepilogo: dict = {"protocollo": {
        "universo": sorted(dati.keys()), "n_universo": len(dati),
        "inizio": args.inizio, "fine": args.fine, "confine": args.confine,
        "tariffa_primaria": tariffa_nome, "tariffa_secondaria": TARIFFA_SECONDARIA,
        "slippage_per_lato": SLIPPAGE_BP_LATO,
        "slippage_stress_per_lato": SLIPPAGE_STRESS_LATO,
        "tipo_ordine": M.TIPO_ORDINE, "capitale": CAPITALE,
        "soglia_eur_anno": SOGLIA_EUR_ANNO, "copertura_minima": COPERTURA_MINIMA,
        "griglia": [dict(p) for p in GRIGLIA_ADDESTRAMENTO],
        "n_varianti": len(GRIGLIA_ADDESTRAMENTO),
        "riferimento": dict(CONFIG_RIFERIMENTO),
        "selezione": ("max expectancy_netta / dd_portafoglio SOLO in addestramento "
                      f"(n >= {MIN_OP_TRAINING} operazioni eseguite)"),
        "verifica": "UNA sola, [%s, %s]" % (args.confine, args.fine),
        "criteri_cancello": 8,
        "metriche_secondarie": [
            "DD portafoglio mark-to-market", "eseguiti/saltati (cassa)",
            "esposizione aggregata massima", "n simboli universo"],
        "dettaglio_universo": dettaglio,
    }, "addestramento": None, "verifica_primaria": None, "verifica_secondaria": None,
        "verifica_stress": None, "confronto_secondario": None}

    righe.append("")
    righe.append(f"=== ADDESTRAMENTO [{args.inizio} -> {args.confine}) — griglia P14 (8) "
                 f"+ riferimento non eleggibile ===")
    scelta, righe_tab, dati_tab, rif = allena(dati, i_confine, tariffa_nome, CAPITALE,
                                              slippage_per_lato=SLIPPAGE_BP_LATO)
    righe.extend(righe_tab)
    riepilogo["addestramento"] = {
        "tabella": [_pulito({k: v for k, v in r.items() if k != "netti_eseguiti"})
                    for r in dati_tab],
        "riferimento": _pulito({k: v for k, v in rif.items() if k != "netti_eseguiti"}),
        "scelta": (_pulito({k: v for k, v in scelta.items() if k != "netti_eseguiti"})
                   if scelta else None),
    }
    if scelta is None:
        righe.append(f"  NESSUNA variante candidabile ({MIN_OP_TRAINING}+ operazioni, "
                     "exp/dd > 0): misura non procedibile.")
        _scrivi(outdir, righe, riepilogo)
        return 0
    righe.append(f"  SCELTA (solo addestramento, max exp/dd): {scelta['descrizione']} "
                 f"(exp netta {_p(scelta['expectancy_netta'], 4)}, dd_port "
                 f"{_p(scelta['dd_portafoglio'], 3)}, n {scelta['eseguite']})")
    config = M.Config(**scelta["config"])

    righe.append("")
    righe.append(f"=== VERIFICA (UNA sola) [{args.confine} -> {args.fine}] ===")
    v1 = verifica(dati, config, i_da=i_confine, i_a=n_barre - 1, tariffa_nome=tariffa_nome,
                  capitale=CAPITALE, etichetta="primario spot+4bp",
                  slippage_per_lato=SLIPPAGE_BP_LATO)
    _blocchi_verifica(v1, righe, "primario")
    ct_sec = confronta_tariffe(v1["esito"], tariffa_nome, TARIFFA_SECONDARIA,
                               capitale_riferimento=CAPITALE,
                               soglia_eur_anno=SOGLIA_EUR_ANNO)
    righe.append(f"  confronto tariffe {tariffa_nome} / {TARIFFA_SECONDARIA}: "
                 f"{ct_sec.sintesi}")
    riepilogo["confronto_secondario"] = {
        "sintesi": ct_sec.sintesi, "verdetto_b": ct_sec.verdetto_b.esito,
        "criteri_cambiati": list(ct_sec.criteri_cambiati),
        "expectancy_b": ct_sec.verdetto_b.statistiche.get("expectancy"),
        "eur_anno_b": ct_sec.verdetto_b.statistiche.get("eur_anno"),
    }

    righe.append("")
    righe.append("=== SCENARIO SECONDARIO (okx_eea_con_perp) ===")
    v2 = verifica(dati, config, i_da=i_confine, i_a=n_barre - 1,
                  tariffa_nome=TARIFFA_SECONDARIA, capitale=CAPITALE,
                  etichetta="secondario con_perp", slippage_per_lato=SLIPPAGE_BP_LATO)
    _blocchi_verifica(v2, righe, "secondario")

    righe.append("")
    righe.append("=== STRESS (slippage x2) ===")
    v3 = verifica(dati, config, i_da=i_confine, i_a=n_barre - 1, tariffa_nome=tariffa_nome,
                  capitale=CAPITALE, etichetta="stress slippage x2",
                  slippage_per_lato=SLIPPAGE_STRESS_LATO)
    _blocchi_verifica(v3, righe, "stress")
    righe.append(f"  confronto stress (slippage x2): expectancy "
                 f"{_p(v1['misura']['expectancy_netta'], 4)} -> "
                 f"{_p(v3['misura']['expectancy_netta'], 4)}; verdetto "
                 f"{v1['verdetto'].esito} -> {v3['verdetto'].esito}")

    v = v1["verdetto"]
    riepilogo["verifica_primaria"] = _riepilogo_verifica(v1)
    riepilogo["verifica_secondaria"] = _riepilogo_verifica(v2)
    riepilogo["verifica_stress"] = _riepilogo_verifica(v3)

    righe.append("")
    righe.append("=== VERDETTO P14 (finestra di verifica, scenario primario) ===")
    if bool(v):
        righe.append("  PROMOSSO: la configurazione scelta supera gli 8 criteri sulla verifica.")
        if not bool(v3["verdetto"]):
            righe.append("  ATTENZIONE stress: non regge lo scenario slippage x2 "
                         "(criterio di robustezza dichiarato prima).")
    elif v.esito == "insufficiente":
        righe.append("  INSUFFICIENTE: campione sotto la soglia minima — misura NON conclusiva.")
        righe.append("  -> non promuove e non archivia (regola dichiarata): un eventuale "
                     "seguito con piu' campioni e' un esperimento NUOVO, non un ritocco "
                     "di questo.")
    else:
        righe.append(f"  {v.esito.upper()}: la configurazione scelta NON supera il cancello "
                     f"sulla verifica (criteri falliti: "
                     f"{', '.join(v.statistiche.get('criteri_falliti', ())) or 'n/d'}).")
        righe.append("  -> si archivia per costruzione, niente 'quasi'.")

    _scrivi(outdir, righe, riepilogo)
    print()
    print(f"artefatti: {outdir / (BASE_ARTEFATTI + '.txt')} e .json | "
          f"runtime {time.time() - t0:.1f}s")
    return 0


def _pulito(obj):
    """Rende JSON-serializzabile un albero di numeri: `inf`/`nan` -> `None` (JSON valido)."""
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, dict):
        return {k: _pulito(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_pulito(v) for v in obj]
    return obj


def _scrivi(outdir: Path, righe: list, riepilogo: dict) -> None:
    testo = "\n".join(righe)
    print(testo)
    (outdir / f"{BASE_ARTEFATTI}.txt").write_text(testo + "\n", encoding="utf-8")
    (outdir / f"{BASE_ARTEFATTI}.json").write_text(
        json.dumps(_pulito(riepilogo), indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
