"""money.ricerca.funding_scan — S2: scansione dell'edge di funding carry (X-Perp OKX EEA).

SPEC: docs/24_S2_ricerca_funding_scan.md (dichiarata PRIMA dei numeri).

COSA FA
=======
Quantifica, per ogni X-Perp OKX EEA presente nell'archivio, l'edge di carry
da funding: a favore di quale lato (short o long), con quale regolarita' e con
quale rendimento NETTO dopo fee di entrata+uscita e slippage — sulla rotazione
dichiarata dalla spec (1 ciclo di apertura/chiusura al mese).

CONVENZIONI
===========
- Calendario VERO: i giorni derivano dagli ts reali (UTC). Nessuna assunzione
  su eventi/giorno: il "funding giornaliero" e' la SOMMA degli eventi del
  giorno, e la media giornaliera e' la media di quelle somme.
- Segno (convenzione OKX, come legacy/hedge_bot.py e p13_cointegrazione.py):
  funding positivo -> i LONG pagano gli SHORT. Cassa dello short = +funding,
  cassa del long = -funding.
- Costi: `money.costi` (la tariffa vera del conto, X-Perps attivi) + slippage
  per lato dichiarato. Un ciclo = giro misto + 2 x slippage.
- Annualizzazione: media giornaliera x 365 (lato favorevole).
- Persistenza: autocorrelazione campionaria lag-1 del funding a livello di
  evento (`money.statistica.autocorrelazione`).

SCELTE (interpretazioni conservative della spec, dichiarate)
============================================================
SCELTA: il "netto annualizzato" di testa e' quello del LATO FAVOREVOLE
(short se la media giornaliera e' positiva, long altrimenti): la spec chiede
"a favore dello short (o del long)". Entrambi i lati sono comunque riportati
per ogni simbolo, e il lato e' dichiarato in output.
SCELTA: l'anomalia del canary si legge su OGNI SINGOLO GIORNO
(max |funding giornaliero| > 0,5%), non sulla media: un giorno storto (una
cifra sbagliata, un tick di collaudo) e' un segnale di errore dati anche se
la media resta piccola. Piu' conservativo, mai meno.
SCELTA: il criterio "n >= 60 giorni" conta i giorni con ALMENO UN'osservazione,
non lo span di calendario: 60 giorni di copertura sparsa non sono storia.
SCELTA: valori di funding non finiti (NaN/inf) contano come righe malformate,
non come zeri: uno zero inventato falserebbe la media.
SCELTA: dedup su ts con "vince l'ultima riga letta" (archivio append-only,
come il raccoglitore P8/funding_regime): la ri-collezione e' idempotente.

L'output e' DESCRITTIVO: nessuna promozione. I candidati si pre-registrano
come esperimenti (spec propria) e passano da `money.cancello`.
"""
from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence, Tuple

from ..costi import Tariffa, get_tariffa
from ..statistica import autocorrelazione

# --- assunzioni dichiarate (le stesse del resto del rig) --------------------------

#: Tariffa vera del conto (X-Perps attivi dal 2026-10-01, acctLv 2).
TARIFFA_ASSUNTA: str = "okx_eea_con_perp"
#: Slippage per lato: mediana spread misurata 2026-09-25 (come gli altri nodi).
SLIPPAGE_PER_LATO: float = 0.0004

GIORNI_ALL_ANNO: int = 365
#: Criterio di lettura della spec: 1 ciclo di apertura/chiusura al mese.
CICLI_ALL_ANNO: int = 12

#: Soglia di anomalia del canary: |funding giornaliero| > 0,5%.
SOGLIA_ANOMALIA: float = 0.005
#: Criterio di lettura: storia di almeno 60 giorni.
MIN_GIORNI: int = 60

_MS_GIORNO: int = 86_400_000


@dataclass(frozen=True)
class SerieFunding:
    """Una serie di funding: ts ms (ordinati) e valori (frazione per periodo)."""

    simbolo: str
    ts: Tuple[int, ...]
    funding: Tuple[float, ...]


@dataclass(frozen=True)
class StatisticheFunding:
    """Le metriche della spec, per un simbolo. Tutte in frazioni."""

    simbolo: str
    n: int                              # n osservazioni (eventi di funding)
    primo_ts: int
    ultimo_ts: int
    giorni_storia: int                  # giorni di calendario primo->ultimo (inclusi)
    n_giorni: int                       # giorni con almeno un'osservazione
    media_giornaliera: float            # media delle somme giornaliere (frazione/giorno)
    mediana_giornaliera: float
    frazione_giorni_positivi_short: float   # short riceve quando funding > 0
    frazione_giorni_positivi_long: float    # long riceve quando funding < 0
    autocorr: Optional[float]           # persistenza: lag-1 del funding a evento
    max_giornaliero_assoluto: float     # max |funding giornaliero| (canary)
    giorno_max_ts: int                  # giorno (ms, mezzanotte UTC) del max
    anomalia: bool                      # max |funding giornaliero| > soglia canary
    annuo_lordo: float                  # media_giornaliera x 365 (lato short)
    costo_ciclo: float                  # giro misto + 2 x slippage
    cicli_all_anno: int
    netto_annualizzato_short: float
    netto_annualizzato_long: float
    lato_favorevole: str                # "short" | "long"
    netto_annualizzato: float           # del lato favorevole (il metrico di testa)
    payback_giorni: Optional[float]     # giorni di funding per coprire UN ciclo


# --- caricamento ------------------------------------------------------------------

def carica_serie(percorso: str) -> Tuple[Dict[str, SerieFunding], int, int]:
    """Carica l'archivio JSONL. Ritorna (serie per simbolo, righe malformate,
    righe non vuote lette).

    Dedup su ts (append-only idempotente: a parita' di ts vince l'ultima riga
    letta). Serie ordinate per ts. Valori non finiti = riga malformata.
    """
    per: Dict[str, Dict[int, float]] = {}
    malformate = 0
    lette = 0
    with open(percorso, "r", encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            lette += 1
            try:
                r = json.loads(riga)
                sim = str(r["simbolo"]).strip().upper()
                ts = int(r["ts"])
                valore = float(r["funding"])
                if not math.isfinite(valore) or ts < 0:
                    raise ValueError("valore non finito o ts negativo")
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                malformate += 1
                continue
            per.setdefault(sim, {})[ts] = valore
    serie: Dict[str, SerieFunding] = {}
    for sim, mappa in per.items():
        ts_ordinati = tuple(sorted(mappa.keys()))
        serie[sim] = SerieFunding(sim, ts_ordinati, tuple(mappa[t] for t in ts_ordinati))
    return serie, malformate, lette


def aggrega_giornaliera(s: SerieFunding) -> Tuple[Tuple[int, float], ...]:
    """(giorno_ms, funding giornaliero): una riga per giorno UTC, dagli ts reali.

    Il giorno e' ricavato per interi (ts // ms_giorno): nessuna assunzione su
    quanti eventi cadono in un giorno.
    """
    per: Dict[int, float] = {}
    for ts, valore in zip(s.ts, s.funding):
        giorno = (ts // _MS_GIORNO) * _MS_GIORNO
        per[giorno] = per.get(giorno, 0.0) + valore
    return tuple(sorted(per.items()))


# --- metriche ---------------------------------------------------------------------

def _autocorr(valori: Sequence[float]) -> Optional[float]:
    """Autocorrelazione lag-1 (money.statistica); None se non definita."""
    if len(valori) < 2:
        return None
    return autocorrelazione(list(valori), 1)


def statistiche(s: SerieFunding, *, tariffa: Optional[Tariffa] = None,
                slippage_per_lato: float = SLIPPAGE_PER_LATO,
                cicli_all_anno: int = CICLI_ALL_ANNO) -> Optional[StatisticheFunding]:
    """Le metriche della spec per un simbolo. Serie vuota -> None (non eccezione).

    Il funding giornaliero e' la somma degli eventi del giorno UTC; lo short
    riceve +funding, il long -funding (convenzione OKX). Il netto annualizzato
    sottrae `cicli_all_anno` cicli completi (giro misto + 2 x slippage).
    """
    if not s.ts:
        return None
    tar = tariffa if tariffa is not None else get_tariffa(TARIFFA_ASSUNTA)
    giorni = aggrega_giornaliera(s)
    valori = [d for _, d in giorni]
    n_giorni = len(giorni)
    media_g = sum(valori) / n_giorni
    primo_g, ultimo_g = giorni[0][0], giorni[-1][0]
    max_assoluto, giorno_max = max(((abs(d), g) for g, d in giorni))
    costo_ciclo = tar.giro_misto + 2.0 * slippage_per_lato
    annuo_lordo = media_g * GIORNI_ALL_ANNO
    netto_short = annuo_lordo - cicli_all_anno * costo_ciclo
    netto_long = -annuo_lordo - cicli_all_anno * costo_ciclo
    lato = "short" if media_g > 0.0 else "long"
    payback = (costo_ciclo / abs(media_g)) if media_g != 0.0 else None
    return StatisticheFunding(
        simbolo=s.simbolo,
        n=len(s.ts),
        primo_ts=s.ts[0],
        ultimo_ts=s.ts[-1],
        giorni_storia=(ultimo_g - primo_g) // _MS_GIORNO + 1,
        n_giorni=n_giorni,
        media_giornaliera=media_g,
        mediana_giornaliera=statistics.median(valori),
        frazione_giorni_positivi_short=sum(1 for d in valori if d > 0.0) / n_giorni,
        frazione_giorni_positivi_long=sum(1 for d in valori if d < 0.0) / n_giorni,
        autocorr=_autocorr(s.funding),
        max_giornaliero_assoluto=max_assoluto,
        giorno_max_ts=giorno_max,
        anomalia=max_assoluto > SOGLIA_ANOMALIA,
        annuo_lordo=annuo_lordo,
        costo_ciclo=costo_ciclo,
        cicli_all_anno=cicli_all_anno,
        netto_annualizzato_short=netto_short,
        netto_annualizzato_long=netto_long,
        lato_favorevole=lato,
        netto_annualizzato=netto_short if lato == "short" else netto_long,
        payback_giorni=payback,
    )


def criteri_di_lettura(st: StatisticheFunding) -> Dict[str, bool]:
    """I criteri della spec (NON promozione): persistenza > 0, n_giorni >= 60,
    netto > 0 dopo costi. `candidato` = tutti e tre + nessuna anomalia
    (un simbolo "da verificare" non puo' essere candidato: il suo numero
    potrebbe essere un errore di dati, non un edge)."""
    persistenza = st.autocorr is not None and st.autocorr > 0.0
    storia = st.n_giorni >= MIN_GIORNI
    netto = st.netto_annualizzato > 0.0
    return {
        "persistenza_positiva": persistenza,
        "storia_60g": storia,
        "netto_positivo": netto,
        "senza_anomalie": not st.anomalia,
        "candidato": persistenza and storia and netto and not st.anomalia,
    }


# --- scansione --------------------------------------------------------------------

def scansione(percorso: str, *, tariffa: Optional[Tariffa] = None,
              slippage_per_lato: float = SLIPPAGE_PER_LATO,
              cicli_all_anno: int = CICLI_ALL_ANNO) -> dict:
    """Scansione completa: carica l'archivio, misura, classifica.

    Il file di input e' un parametro (la funzione e' pura: nessuna rete, nessun
    stato globale). Ritorna un dict serializzabile: meta, per_simbolo (con
    criteri), classifica (per netto annualizzato del lato favorevole),
    candidati e da_verificare.
    """
    tar = tariffa if tariffa is not None else get_tariffa(TARIFFA_ASSUNTA)
    serie, malformate, lette = carica_serie(percorso)
    per_simbolo: Dict[str, dict] = {}
    per_regola: Dict[str, dict] = {}
    for nome in sorted(serie):
        st = statistiche(serie[nome], tariffa=tar, slippage_per_lato=slippage_per_lato,
                         cicli_all_anno=cicli_all_anno)
        if st is None:
            continue
        record = asdict(st)
        record["criteri"] = criteri_di_lettura(st)
        per_simbolo[nome] = record
        # SCELTA (conservativa): i simboli "da verificare" (anomalia del
        # canary) restano FUORI dalla classifica: un possibile errore di
        # dati non e' un edge, e il suo numero di testa sarebbe gonfiato
        # dal giorno storto. Vanno letti nella sezione dedicata.
        if not st.anomalia:
            per_regola[nome] = record
    classifica = sorted(per_regola.values(),
                        key=lambda r: (-r["netto_annualizzato"], r["simbolo"]))
    costo_ciclo = tar.giro_misto + 2.0 * slippage_per_lato
    return {
        "meta": {
            "percorso": percorso,
            "righe": lette,
            "malformate": malformate,
            "n_simboli": len(per_simbolo),
            "n_esclusi_anomalia": len(per_simbolo) - len(per_regola),
            "tariffa": f"{tar.venue.value} ({tar.condizione})",
            "giro_misto": tar.giro_misto,
            "slippage_per_lato": slippage_per_lato,
            "costo_ciclo": costo_ciclo,
            "cicli_all_anno": cicli_all_anno,
            "giorni_all_anno": GIORNI_ALL_ANNO,
            "soglia_anomalia": SOGLIA_ANOMALIA,
            "min_giorni": MIN_GIORNI,
        },
        "per_simbolo": per_simbolo,
        "classifica": classifica,
        "candidati": [r["simbolo"] for r in classifica if r["criteri"]["candidato"]],
        "da_verificare": [
            {
                "simbolo": r["simbolo"],
                "giorno": _iso(r["giorno_max_ts"]),
                "funding_giornaliero": r["max_giornaliero_assoluto"],
            }
            for r in per_simbolo.values() if r["anomalia"]
        ],
    }


# --- report -----------------------------------------------------------------------

def _iso(giorno_ms: int) -> str:
    return datetime.fromtimestamp(giorno_ms / 1000, tz=timezone.utc).date().isoformat()


def _fmt_pct(x: Optional[float], cifre: int = 2) -> str:
    return "n/d" if x is None else ("%+.*f%%" % (cifre, 100.0 * x))


def report_testo(risultato: dict) -> str:
    """Report testuale deterministico (ASCII, leggibile in prove/)."""
    meta = risultato["meta"]
    righe: List[str] = []
    righe.append("S2 — FUNDING SCAN X-PERP OKX EEA (scansione descrittiva — NON promozione)")
    righe.append("=" * 78)
    righe.append("Dati: %s | righe lette: %d | malformate: %d | simboli: %d" % (
        meta["percorso"], meta["righe"], meta["malformate"], meta["n_simboli"]))
    righe.append("Costi: %s | giro misto %.3f%% | slippage %.3f%%/lato | ciclo %.3f%% x %d/anno (1 apertura/chiusura al mese)" % (
        meta["tariffa"], 100.0 * meta["giro_misto"], 100.0 * meta["slippage_per_lato"],
        100.0 * meta["costo_ciclo"], meta["cicli_all_anno"]))
    righe.append("")
    righe.append("%-24s %5s %5s %9s %9s %10s %5s %8s %7s %7s %s" % (
        "simbolo", "n", "giorni", "media/g", "annuo lordo", "annuo NETTO",
        "lato", "%g+short", "autocorr", "payback", "criteri"))
    for r in risultato["classifica"]:
        c = r["criteri"]
        lettere = ("P" if c["persistenza_positiva"] else "-") \
            + ("S" if c["storia_60g"] else "-") \
            + ("N" if c["netto_positivo"] else "-")
        flag = lettere + ("!" if r["anomalia"] else "")
        payback = ("%.0fg" % r["payback_giorni"]) if r["payback_giorni"] is not None else "n/d"
        autocorr = ("%+.3f" % r["autocorr"]) if r["autocorr"] is not None else "n/d"
        righe.append("%-24s %5d %5d %+8.4f%% %+8.2f%% %+9.2f%% %5s %7.1f%% %7s %7s %s" % (
            r["simbolo"], r["n"], r["n_giorni"],
            100.0 * r["media_giornaliera"], 100.0 * r["annuo_lordo"],
            100.0 * r["netto_annualizzato"], r["lato_favorevole"],
            100.0 * r["frazione_giorni_positivi_short"], autocorr, payback, flag))
    righe.append("")
    righe.append("Criteri (NON promozione): persistenza > 0 [P] | n_giorni >= %d [S] | netto > 0 dopo costi [N]; ! = anomalia" % meta["min_giorni"])
    n_cand = len(risultato["candidati"])
    righe.append("CANDIDATI (%d/%d): %s" % (
        n_cand, meta["n_simboli"],
        ", ".join(risultato["candidati"]) if n_cand else "nessuno"))
    if meta["n_esclusi_anomalia"]:
        righe.append("La classifica esclude %d simbolo/i 'da verificare' "
                     "(un possibile errore di dati non e' un edge)." % meta["n_esclusi_anomalia"])
    if risultato["da_verificare"]:
        righe.append("DA VERIFICARE (|funding giornaliero| > %.2f%% — possibile errore dati, non edge):" % (
            100.0 * meta["soglia_anomalia"]))
        for dv in risultato["da_verificare"]:
            righe.append("  %-24s giorno %s: funding giornaliero %s" % (
                dv["simbolo"], dv["giorno"], _fmt_pct(dv["funding_giornaliero"], 3)))
    else:
        righe.append("DA VERIFICARE: nessun simbolo oltre la soglia del canary (%.2f%% giornaliero)" % (
            100.0 * meta["soglia_anomalia"]))
    righe.append("")
    righe.append("L'output e' DESCRITTIVO: i candidati si pre-registrano come esperimenti (spec propria) e passano da money.cancello.")
    righe.append("Nessuna promozione automatica. La classifica mescola lati diversi: controllare il campo 'lato' prima di confrontare.")
    return "\n".join(righe) + "\n"


def report_json(risultato: dict) -> str:
    """Versione JSON serializzabile (per prove/funding_scan_<data>.json)."""
    return json.dumps(risultato, indent=1, sort_keys=True)
