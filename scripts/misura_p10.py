#!/usr/bin/env python3
"""Misura P10 — momentum CROSS-SEZIONALE long/flat (rotazione top-k) — misura e giudizio.

PROTOCOLLO (pre-registrato PRIMA di ogni numero; voce P10 di `prove/REGISTRO_ESPERIMENTI.md`
e spec `coda_catena/P10_momentum_cross.md`)
===========================================================================
- Dati: USDT-lungo (10 major), timeframe 1d, [2020-10-01, 2026-09-25]; confine di
  addestramento 2024-06-01. Il paniere viene ALLINEATO sull'intersezione dei timestamp
  (stesse date, stesse posizioni): `momentum_cross` indicizza per posizione di barra.
- Griglia DICHIARATA (8 varianti, PRIMA dei numeri): {k: 2,3} x {L: 60,120} x {R: 7,14}.
  Tutte provate SULL'ADDESTRAMENTO [2020-10-01, 2024-06-01) e TUTTE riportate.
- Selezione: SOLO addestramento, miglior rapporto `expectancy_netta / dd_portafoglio`
  (DD di portafoglio mark-to-market). La verifica NON entra nella scelta.
- Verifica: UNA sola configurazione su [2024-06-01, 2026-09-25); nessun ritocco.
- Costi: `money.costi` — `okx_eea_spot` misto + 4 bp di slippage per lato (una sola
  verita' sui costi, la stessa dei nodi Donchian/P2/P3). Scenario secondario
  `okx_eea_con_perp` via `confronta_tariffe`. Nessuna leva, cassa vincolante, mai short.
- Allocazione: `equity / k` per posizione (hook `esposizione_per_op` del motore di
  portafoglio); con meno di k candidati si tengono i disponibili, con 0 si e' flat.
- Cancello: `money.cancello.giudica` (8 criteri) sulla finestra di verifica.
- Metriche secondarie FISSE: DD di portafoglio mark-to-market, eseguiti/saltati (cassa),
  esposizione aggregata massima.

Artefatti: `prove/P10_momentum_cross.{txt,json}`; l'outdir e' configurabile con `--outdir`.
Questo runner NON produce la misura ufficiale: la produce Hermes sul repo canonico. Lo
smoke ridotto gira con `--outdir ~/dsh-scratch/...` e non tocca mai `prove/`.

Uso (misura ufficiale, dal repo canonico):
    python scripts/misura_p10.py

Uso (smoke ridotto, NON ufficiale):
    python scripts/misura_p10.py --simboli BTC/USDT,ETH/USDT,SOL/USDT,DOGE/USDT \\
        --inizio 2021-06-01 --fine 2023-06-01 --confine 2022-06-01 \\
        --outdir ~/dsh-scratch/p10_smoke
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
from money.dati import Scarica  # noqa: E402
from money.ricerca import momentum_cross as M  # noqa: E402
from money.statistica import t_stat, t_stat_newey_west  # noqa: E402
from scripts.misura_catena_hermes import carica, prima_dopo  # noqa: E402

CAPITALE = 1000.0
SOGLIA_EUR_ANNO = 10.0
#: Vincolo dichiarato per leggere una riga di addestramento (convenzione della catena):
#: sotto 30 operazioni il cancello dice "insufficiente" e non promuove ne' archivia.
MIN_OP_TRAINING = 30
CARTELLA_PROVE = Path(__file__).resolve().parents[1] / "prove"
#: Nome base degli artefatti (spec: `prove/P10_*.{txt,json}`).
BASE_ARTEFATTI = "P10_momentum_cross"


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
    """Griglia completa SOLO in addestramento; sceglie per miglior `expectancy_netta / dd_port`.

    Si riportano TUTTE le 8 righe. La verifica non viene nemmeno calcolata qui: la scelta e'
    funzione della sola finestra di addestramento, per costruzione anti-HARKing.
    """
    tabella: list = []
    for parametri in M.GRIGLIA_ADDESTRAMENTO:
        config = M.Config(**parametri)
        r = misura_config(dati, config, i_da=0, i_a=i_confine - 1,
                          tariffa_nome=tariffa_nome, capitale=capitale)
        tabella.append(r)
    valide = [r for r in tabella
              if r["rapporto_exp_dd"] is not None
              and not (isinstance(r["rapporto_exp_dd"], float)
                       and math.isnan(r["rapporto_exp_dd"]))]
    if not valide:
        return None, tabella
    scelta = max(valide, key=lambda r: r["rapporto_exp_dd"])
    return scelta, tabella


def verifica(dati: dict, config: M.Config, *, i_da: int, i_a: int,
             tariffa_nome: str, capitale: float, etichetta: str) -> dict:
    """UNA verifica: giudizio a 8 criteri sulla finestra + scenario tariffe secondario."""
    r = misura_config(dati, config, i_da=i_da, i_a=i_a,
                      tariffa_nome=tariffa_nome, capitale=capitale)
    netti = tuple(r["netti_eseguiti"])
    esito = Esito(
        nome=f"P10 momentum cross {config} [{etichetta}]",
        ritorni_netti=netti, n_operazioni=len(netti),
        esposizione_media=1.0 / config.k, max_drawdown=r["dd_portafoglio"],
        giorni_osservati=r["giorni"], tariffa=get_tariffa(tariffa_nome), tipo=M.TIPO_ORDINE,
        note=(f"P10: rotazione top-{config.k}, momentum {config.lookback}g, ribilancio "
              f"{config.ribilancio}g; allocazione equity/{config.k}; DD portafoglio MTM; "
              f"costi {tariffa_nome} misto + {_p(M.SLIPPAGE_PER_LATO, 2)}/lato."),
    )
    v = giudica(esito, capitale_riferimento=capitale, soglia_eur_anno=SOGLIA_EUR_ANNO)
    ct = confronta_tariffe(esito, tariffa_nome, M.TARIFFA_SECONDARIA,
                           capitale_riferimento=capitale, soglia_eur_anno=SOGLIA_EUR_ANNO)
    return {"misura": r, "esito": esito, "verdetto": v, "confronto_tariffe": ct}


def _blocchi_verifica(ris: dict, righe: list) -> None:
    r = ris["misura"]
    v = ris["verdetto"]
    ct = ris["confronto_tariffe"]
    righe.append(f"  configurazione CONGELATA: {r['descrizione']}")
    righe.append(f"  operazioni: campione {r['n_operazioni_campione']} | eseguite "
                 f"{r['eseguite']} | saltate {r['saltate']} (cassa)")
    righe.append(f"  expectancy netta {_p(r['expectancy_netta'], 4)} | DD portafoglio MTM "
                 f"{_p(r['dd_portafoglio'], 3)} | esposizione max "
                 f"{_p(r['max_esposizione'], 1)} | max posizioni {r['max_posizioni']}")
    righe.append(f"  t-stat {_n(r['t_stat'], 2)} | t-stat Newey-West "
                 f"{_n(r['t_stat_newey_west'], 2)} | capitale finale "
                 f"{_n(r['capitale_finale'], 2)} EUR | giorni {_n(r['giorni'], 1)}")
    criteri = v.statistiche.get("criteri", {})
    if criteri:
        righe.append("  CRITERI (8): " + " | ".join(
            f"{nome}={'ok' if ok else 'KO'}" for nome, ok in criteri.items()))
    else:
        righe.append("  CRITERI (8): non valutati — il verdetto si e' fermato prima "
                     "(serie vuota, degenere o numerosita' < 30)")
    righe.append(f"  VERDETTO: {v.esito}")
    for motivo in v.motivi:
        righe.append(f"    - {motivo}")
    righe.append(f"  scenario tariffe: {ct.sintesi}")
    righe.append(f"    {M.TARIFFA_SECONDARIA}: verdetto {ct.verdetto_b.esito}, "
                 f"expectancy {_p(ct.verdetto_b.statistiche.get('expectancy'), 4)}, "
                 f"EUR/anno {_n(ct.verdetto_b.statistiche.get('eur_anno'), 1)}")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Misura P10 — momentum cross-section long/flat")
    parser.add_argument("--outdir", default=None,
                        help="cartella artefatti (default: <repo>/prove)")
    parser.add_argument("--simboli", default=None,
                        help="simboli separati da virgola (default: universo P10)")
    parser.add_argument("--inizio", default=M.INIZIO_STORIA)
    parser.add_argument("--fine", default=M.FINE_STORIA)
    parser.add_argument("--confine", default=M.CONFINE_ADDESTRAMENTO)
    parser.add_argument("--cache", default=None, help="cartella cache dati (default: repo/data/cache)")
    parser.add_argument("--timeframe", default="1d")
    args = parser.parse_args(argv)

    outdir = Path(args.outdir).expanduser() if args.outdir else CARTELLA_PROVE
    outdir.mkdir(parents=True, exist_ok=True)
    simboli = tuple(s.strip() for s in args.simboli.split(",")) if args.simboli else M.SIMBOLI
    tariffa_nome = M.TARIFFA_ASSUNTA

    t0 = time.time()
    righe: list = []
    righe.append("P10 — MOMENTUM CROSS-SECTIONAL long/flat (rotazione top-k) — misura e giudizio")
    righe.append("(voce pre-registrata; griglia {k:2,3} x {L:60,120} x {R:7,14} = 8 varianti)")
    righe.append(f"universo: {len(simboli)} simboli | periodo {args.inizio} -> {args.fine} | "
                 f"confine addestramento {args.confine}")
    righe.append(f"costi: {tariffa_nome} misto + {_p(M.SLIPPAGE_PER_LATO, 2)}/lato "
                 f"(secondario {M.TARIFFA_SECONDARIA}); capitale {_n(CAPITALE, 0)} EUR; "
                 f"allocazione equity/k; mai leva, mai short")
    if args.outdir:
        righe.append("(ESECUZIONE RIDOTTA/NON UFFICIALE: outdir e universo non canonici)")

    scaricatore = Scarica(args.cache)
    righe.append(f"cache dati: {scaricatore.cartella_cache}")
    dati = carica(scaricatore, simboli, args.timeframe, args.inizio, args.fine, M.COPERTURA_MINIMA)
    if len(dati) < 2:
        righe.append("DATI INSUFFICIENTI: servono almeno 2 simboli allineabili.")
        _scrivi(outdir, righe, {"errore": "dati insufficienti", "simboli": list(dati)})
        return 1
    dati, ts = allinea(dati)
    n_barre = len(ts)
    i_confine = prima_dopo(dati, args.confine)
    righe.append(f"allineamento: {len(dati)} simboli x {n_barre} barre comuni "
                 f"({_iso(ts[0])} -> {_iso(ts[-1])}); confine reale indice {i_confine} "
                 f"@ {_iso(ts[i_confine])}")

    riepilogo: dict = {"protocollo": {
        "universo": list(dati.keys()), "inizio": args.inizio, "fine": args.fine,
        "confine": args.confine, "tariffa_primaria": tariffa_nome,
        "tariffa_secondaria": M.TARIFFA_SECONDARIA, "tipo_ordine": M.TIPO_ORDINE,
        "slippage_per_lato": M.SLIPPAGE_PER_LATO, "capitale": CAPITALE,
        "soglia_eur_anno": SOGLIA_EUR_ANNO, "griglia": [dict(p) for p in M.GRIGLIA_ADDESTRAMENTO],
        "n_varianti": len(M.GRIGLIA_ADDESTRAMENTO),
        "selezione": "max expectancy_netta / dd_portafoglio SOLO in addestramento",
        "verifica": "UNA sola, [%s, %s]" % (args.confine, args.fine),
        "criteri_cancello": 8, "metriche_secondarie": [
            "DD portafoglio mark-to-market", "eseguiti/saltati", "esposizione aggregata massima"],
    }, "addestramento": None, "verifica": None}

    righe.append("")
    righe.append(f"=== ADDESTRAMENTO [{args.inizio} -> {args.confine}) — tutte le {len(M.GRIGLIA_ADDESTRAMENTO)} varianti ===")
    scelta, tabella = allena(dati, i_confine, tariffa_nome, CAPITALE)
    for r in tabella:
        righe.append(_riga_tabella(r))
    riepilogo["addestramento"] = {
        "tabella": [{k: v for k, v in r.items() if k != "netti_eseguiti"} for r in tabella],
        "scelta": ({k: v for k, v in scelta.items() if k != "netti_eseguiti"}
                   if scelta else None),
    }
    if scelta is None:
        righe.append("  NESSUNA variante con rapporto exp/dd definito: misura non procedibile.")
        _scrivi(outdir, righe, riepilogo)
        return 0
    righe.append(f"  SCELTA (solo addestramento, max exp/dd): {scelta['descrizione']} "
                 f"(exp netta {_p(scelta['expectancy_netta'], 4)}, dd_port "
                 f"{_p(scelta['dd_portafoglio'], 3)}, n {scelta['eseguite']})")
    if scelta["eseguite"] < MIN_OP_TRAINING:
        righe.append(f"  ATTENZIONE: la scelta ha {scelta['eseguite']} operazioni < "
                     f"{MIN_OP_TRAINING}: il cancello dira' 'insufficiente', non un verdetto.")
    config = M.Config(**scelta["config"])

    righe.append("")
    righe.append(f"=== VERIFICA (UNA sola) [{args.confine} -> {args.fine}] ===")
    ris = verifica(dati, config, i_da=i_confine, i_a=n_barre - 1, tariffa_nome=tariffa_nome,
                   capitale=CAPITALE, etichetta=f"{args.confine} -> {args.fine}")
    _blocchi_verifica(ris, righe)
    v = ris["verdetto"]
    ct = ris["confronto_tariffe"]
    riepilogo["verifica"] = {
        "misura": {k: vv for k, vv in ris["misura"].items() if k != "netti_eseguiti"},
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
        "scenario_secondario": {
            "tariffa": M.TARIFFA_SECONDARIA, "verdetto": ct.verdetto_b.esito,
            "criteri_cambiati": list(ct.criteri_cambiati), "sintesi": ct.sintesi,
            "expectancy": ct.verdetto_b.statistiche.get("expectancy"),
            "eur_anno": ct.verdetto_b.statistiche.get("eur_anno"),
        },
    }

    righe.append("")
    righe.append("=== VERDETTO P10 (finestra di verifica) ===")
    if bool(v):
        righe.append("  PROMOSSO: la configurazione scelta supera gli 8 criteri sulla verifica.")
    elif v.esito == "insufficiente":
        righe.append("  INSUFFICIENTE: campione sotto la soglia minima — misura NON conclusiva.")
        righe.append("  -> non promuove e non archivia (regola dichiarata): un eventuale seguito "
                     "con piu' campioni e' un esperimento NUOVO, non un ritocco di questo.")
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
