"""money.ricerca.funding_regime — P12: persistenza, netto e regola di regime del funding X-Perp.

Decision-support per il carry (P4/C1). NON e' una strategia a se': misura il FLUSSO di funding
dell'archivio P8 (10 X-Perp OKX EEA), la sua persistenza, il netto a tariffe X-Perp reali e la
regola di regime "media3>0 / uscita primo negativo" contro always-on. Solo stdlib.

Griglia dichiarata in `coda_catena/P12_funding_regime.md` (pre-registrata prima dei numeri):
- ingresso media3>0, uscita primo negativo (UNICA variante);
- orizzonti {7,14,30,60,90} riportati tutti; costi {0,40% primario, 0,62% stress};
- bootstrap a blocchi (21 eventi), 2000 ripetizioni, seme fisso SEME_BOOTSTRAP.

Anti-look-ahead: ogni decisione a t usa SOLO eventi <= t-1 (testato in tests/ricerca/).
"""
from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

SEME_BOOTSTRAP = 20261001
BLOCCO_BOOTSTRAP = 21          # eventi (7 giorni di funding a 8h)
RIPETIZIONI_BOOTSTRAP = 2000
ORIZZONTI_GIORNI = (7, 14, 30, 60, 90)
COSTI = (0.0040, 0.0062)       # C: 0,40% tariffe X-Perp (primario) e 0,62% stress (pre-X-Perp)
EVENTI_AL_GIORNO = 3           # funding ogni 8h -> 3 eventi/giorno
SOGLIA_PAYBACK_GIORNI = 45     # criterio H2


@dataclass(frozen=True)
class SerieSimbolo:
    simbolo: str
    ts: Tuple[int, ...]
    funding: Tuple[float, ...]


def carica_serie(path: str) -> Tuple[Dict[str, SerieSimbolo], int]:
    """Carica l'archivio P8. Ritorna (serie ordinate per ts per simbolo, n. righe malformate).

    Dedup su ts (append-only idempotente: a parita' di ts vince l'ultima riga letta).
    """
    per: Dict[str, Dict[int, float]] = {}
    malformate = 0
    with open(path, "r", encoding="utf-8") as f:
        for riga in f:
            riga = riga.strip()
            if not riga:
                continue
            try:
                r = json.loads(riga)
                sim = str(r["simbolo"]).strip().upper()
                ts = int(r["ts"])
                valore = float(r["funding"])
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                malformate += 1
                continue
            per.setdefault(sim, {})[ts] = valore
    serie: Dict[str, SerieSimbolo] = {}
    for sim, mappa in per.items():
        ts_ordinati = tuple(sorted(mappa.keys()))
        serie[sim] = SerieSimbolo(sim, ts_ordinati, tuple(mappa[t] for t in ts_ordinati))
    return serie, malformate


def _media(xs: Sequence[float]) -> Optional[float]:
    if not xs:
        return None
    return sum(xs) / len(xs)


def _pearson(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    n = len(xs)
    if n < 3 or n != len(ys):
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = math.sqrt(sum((x - mx) ** 2 for x in xs))
    dy = math.sqrt(sum((y - my) ** 2 for y in ys))
    if dx == 0.0 or dy == 0.0:
        return None
    return num / (dx * dy)


def _ranghi(xs: Sequence[float]) -> List[float]:
    """Ranghi con media sui pareggi (per Spearman)."""
    ordinati = sorted(range(len(xs)), key=lambda i: xs[i])
    ranghi = [0.0] * len(xs)
    i = 0
    while i < len(ordinati):
        j = i
        while j + 1 < len(ordinati) and xs[ordinati[j + 1]] == xs[ordinati[i]]:
            j += 1
        rango = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranghi[ordinati[k]] = rango
        i = j + 1
    return ranghi


def _spearman(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    return _pearson(_ranghi(xs), _ranghi(ys))


def autocorr1(valori: Sequence[float]) -> Optional[float]:
    """Autocorrelazione lag-1 (Pearson su coppie consecutive)."""
    if len(valori) < 4:
        return None
    return _pearson(valori[:-1], valori[1:])


def streak_negativa_massima(valori: Sequence[float]) -> int:
    """Lunghezza massima di una serie consecutiva di eventi negativi (< 0)."""
    massimo = corrente = 0
    for v in valori:
        if v < 0:
            corrente += 1
            massimo = max(massimo, corrente)
        else:
            corrente = 0
    return massimo


def p_media3_positiva(valori: Sequence[float]) -> Optional[float]:
    """P(next > 0 | media dei 3 eventi precedenti > 0). Solo passato nella condizione."""
    n = len(valori)
    if n < 4:
        return None
    casi = 0
    positivi = 0
    for t in range(3, n):
        m3 = (valori[t - 1] + valori[t - 2] + valori[t - 3]) / 3.0
        if m3 > 0:
            casi += 1
            if valori[t] > 0:
                positivi += 1
    if casi == 0:
        return None
    return positivi / casi


def p_corrente_positiva(valori: Sequence[float]) -> Optional[float]:
    """P(next > 0 | corrente > 0)."""
    if len(valori) < 2:
        return None
    casi = positivi = 0
    for t in range(1, len(valori)):
        if valori[t - 1] > 0:
            casi += 1
            if valori[t] > 0:
                positivi += 1
    if casi == 0:
        return None
    return positivi / casi


@dataclass(frozen=True)
class Statistiche:
    simbolo: str
    n: int
    primo_ts: int
    ultimo_ts: int
    mu: float                       # media per evento (frazione)
    mu_giornaliera: float
    annualizzato: float
    base_rate: float                # P(next > 0) = frazione positivi
    p_corrente: Optional[float]
    p_media3: Optional[float]
    autocorr: Optional[float]
    streak_neg_max: int
    payback_giorni: Optional[float]  # C(0,40%) / mu_giornaliera
    mu_ic90: Optional[Tuple[float, float]]
    p1b_ic90: Optional[Tuple[float, float]]


def statistiche(s: SerieSimbolo) -> Optional[Statistiche]:
    v = s.funding
    n = len(v)
    if n == 0:
        return None
    mu = sum(v) / n
    mu_g = mu * EVENTI_AL_GIORNO
    base_rate = sum(1 for x in v if x > 0) / n
    payback = (COSTI[0] / mu_g) if mu_g > 0 else None
    return Statistiche(
        simbolo=s.simbolo,
        n=n,
        primo_ts=s.ts[0],
        ultimo_ts=s.ts[-1],
        mu=mu,
        mu_giornaliera=mu_g,
        annualizzato=mu_g * 365.0,
        base_rate=base_rate,
        p_corrente=p_corrente_positiva(v),
        p_media3=p_media3_positiva(v),
        autocorr=autocorr1(v),
        streak_neg_max=streak_negativa_massima(v),
        payback_giorni=payback,
        mu_ic90=bootstrap_ic90(v, _media_di_lista),
        p1b_ic90=bootstrap_ic90(v, p_media3_positiva),
    )


def _media_di_lista(xs: Sequence[float]) -> Optional[float]:
    return _media(list(xs))


def bootstrap_ic90(
    valori: Sequence[float],
    fn: Any,
    seme: int = SEME_BOOTSTRAP,
    blocco: int = BLOCCO_BOOTSTRAP,
    ripetizioni: int = RIPETIZIONI_BOOTSTRAP,
) -> Optional[Tuple[float, float]]:
    """IC90 (p5, p95) di fn via block bootstrap (blocchi contigui di lunghezza fissa).

    Deterministico a parita' di seme. None se la serie e' troppo corta o fn non definita.
    """
    n = len(valori)
    if n < blocco + 1:
        return None
    rng = random.Random(seme)
    n_blocchi = math.ceil(n / blocco)
    stime: List[float] = []
    for _ in range(ripetizioni):
        campione: List[float] = []
        for _ in range(n_blocchi):
            start = rng.randrange(0, n - blocco + 1)
            campione.extend(valori[start:start + blocco])
        valore = fn(campione[:n])
        if valore is not None:
            stime.append(valore)
    if len(stime) < 20:
        return None
    stime.sort()
    lo = stime[int(0.05 * len(stime))]
    hi = stime[min(len(stime) - 1, int(0.95 * len(stime)))]
    return lo, hi


def netto(mu_giornaliera: float, orizzonte_giorni: int, costo: float) -> float:
    """Netto a orizzonte (frazione): mu_giornaliera * H - costo di ciclo."""
    return mu_giornaliera * orizzonte_giorni - costo


@dataclass(frozen=True)
class EsitoFlusso:
    flusso: float                  # somma funding catturato (frazione)
    eventi_catturati: int
    giorni_in_posizione: float
    dd_flusso: float               # max drawdown della cumulata (>= 0, frazione)
    episodi: int                   # numero di ingressi
    negativi_catturati: float      # somma dei funding negativi catturati


def flusso_always_on(s: SerieSimbolo) -> EsitoFlusso:
    v = s.funding
    flusso = 0.0
    cum = peak = dd = 0.0
    negativi = 0.0
    for x in v:
        flusso += x
        if x < 0:
            negativi += x
        cum += x
        peak = max(peak, cum)
        dd = max(dd, peak - cum)
    return EsitoFlusso(flusso, len(v), len(v) / EVENTI_AL_GIORNO, dd, 0, negativi)


def flusso_regola(s: SerieSimbolo) -> EsitoFlusso:
    """RULE dichiarata: ingresso a t se non in posizione e media3(t-1) > 0;
    uscita PRIMA di t se in posizione e funding(t-1) < 0 ("primo negativo").

    Ogni decisione usa SOLO eventi <= t-1 (anti-look-ahead, testato).
    """
    v = s.funding
    n = len(v)
    in_pos = False
    flusso = cum = peak = dd = negativi = 0.0
    episodi = eventi = 0
    for t in range(n):
        if in_pos and v[t - 1] < 0:
            in_pos = False
        if not in_pos and t >= 3:
            m3 = (v[t - 1] + v[t - 2] + v[t - 3]) / 3.0
            if m3 > 0:
                in_pos = True
                episodi += 1
        if in_pos:
            x = v[t]
            flusso += x
            eventi += 1
            if x < 0:
                negativi += x
            cum += x
            peak = max(peak, cum)
            dd = max(dd, peak - cum)
    return EsitoFlusso(flusso, eventi, eventi / EVENTI_AL_GIORNO, dd, episodi, negativi)


def stabilita(serie: Dict[str, SerieSimbolo]) -> Dict[str, Any]:
    """Stabilita' tra le due meta' del CALENDARIO (taglio fisso a meta' dell'arco globale).

    Ritorna rho di Spearman tra i mu delle due meta' (sui simboli con >= 30 eventi per meta'),
    il conteggio delle inversioni di segno e i dettagli per simbolo.
    """
    tutti_ts = [t for s in serie.values() for t in s.ts]
    if not tutti_ts:
        return {"rho": None, "inversioni": 0, "per_simbolo": {}, "nota": "archivio vuoto"}
    taglio = (min(tutti_ts) + max(tutti_ts)) // 2
    dettagli: Dict[str, Dict[str, Any]] = {}
    mu1: List[float] = []
    mu2: List[float] = []
    nomi: List[str] = []
    for nome, s in sorted(serie.items()):
        h1 = [v for t, v in zip(s.ts, s.funding) if t <= taglio]
        h2 = [v for t, v in zip(s.ts, s.funding) if t > taglio]
        m1 = _media(h1) if len(h1) >= 30 else None
        m2 = _media(h2) if len(h2) >= 30 else None
        dettagli[nome] = {"mu_h1": m1, "mu_h2": m2, "n_h1": len(h1), "n_h2": len(h2)}
        if m1 is not None and m2 is not None:
            mu1.append(m1)
            mu2.append(m2)
            nomi.append(nome)
    rho = _spearman(mu1, mu2) if len(mu1) >= 3 else None
    inversioni = sum(1 for a, b in zip(mu1, mu2) if (a > 0) != (b > 0))
    return {
        "rho": rho,
        "inversioni": inversioni,
        "n_simboli": len(mu1),
        "taglio_ts": taglio,
        "per_simbolo": dettagli,
    }


def valuta(serie: Dict[str, SerieSimbolo]) -> Dict[str, Any]:
    """Applica i criteri dichiarati (H1, H2, H3, RULE) e produce l'esito.

    Esiti ammessi (spec P12): {descrittiva solida, insufficiente, archiviata-al-netto}.
    """
    stats: Dict[str, Statistiche] = {}
    for nome, s in sorted(serie.items()):
        st = statistiche(s)
        if st is not None:
            stats[nome] = st
    n_simboli = len(stats)

    # H1: p1b vs base rate (pooled, pesato per eventi) + autocorr mediana.
    tot_casi = tot_pos = 0
    autocorrs: List[float] = []
    for st, s in ((st, serie[st.simbolo]) for st in stats.values()):
        v = s.funding
        for t in range(3, len(v)):
            m3 = (v[t - 1] + v[t - 2] + v[t - 3]) / 3.0
            if m3 > 0:
                tot_casi += 1
                if v[t] > 0:
                    tot_pos += 1
        if st.autocorr is not None:
            autocorrs.append(st.autocorr)
    p1b_pooled = (tot_pos / tot_casi) if tot_casi else None
    base_rate_pooled = (
        sum(1 for st in stats.values() for v in serie[st.simbolo].funding if v > 0)
        / sum(st.n for st in stats.values())
        if stats else None
    )
    autocorr_med = sorted(autocorrs)[len(autocorrs) // 2] if autocorrs else None
    # Informativo (non gating): simboli con estremo inferiore IC90 di p1b sopra il base rate.
    p1b_ci_ok = sum(
        1 for st in stats.values()
        if st.p1b_ic90 is not None and st.p1b_ic90[0] > st.base_rate
    )

    # H2: netto a 30g (C primario) > 0 e payback <= 45g.
    h2_ok_count = sum(
        1
        for st in stats.values()
        if netto(st.mu_giornaliera, 30, COSTI[0]) > 0
        and st.payback_giorni is not None
        and st.payback_giorni <= SOGLIA_PAYBACK_GIORNI
    )

    # H3: rho >= 0.5 e inversioni <= 2.
    stab = stabilita(serie)
    h3_ok = (
        stab.get("rho") is not None
        and stab["rho"] >= 0.5
        and stab.get("inversioni", 99) <= 2
    )

    # RULE vs always-on (pesato per flusso).
    flusso_ao = flusso_rule = dd_ao = dd_rule = 0.0
    per_flusso: Dict[str, Dict[str, float]] = {}
    for nome, s in sorted(serie.items()):
        ao = flusso_always_on(s)
        ru = flusso_regola(s)
        flusso_ao += ao.flusso
        flusso_rule += ru.flusso
        dd_ao += ao.dd_flusso
        dd_rule += ru.dd_flusso
        per_flusso[nome] = {
            "ao": ao.flusso,
            "rule": ru.flusso,
            "quota": (ru.flusso / ao.flusso) if ao.flusso != 0 else None,
            "dd_ao": ao.dd_flusso,
            "dd_rule": ru.dd_flusso,
            "episodi": ru.episodi,
        }
    quota_ru = flusso_rule / flusso_ao if flusso_ao != 0 else None
    dd_riduzione = (1.0 - dd_rule / dd_ao) if dd_ao > 0 else None
    rule_vince = (
        quota_ru is not None
        and quota_ru >= 0.85
        and dd_riduzione is not None
        and dd_riduzione >= 0.50
    )

    # Esito dichiarato (spec P12).
    if n_simboli == 0 or sum(st.n for st in stats.values()) < 30 * max(1, n_simboli):
        esito = "insufficiente"
    elif h2_ok_count < 6:
        esito = "archiviata-al-netto"
    else:
        esito = "descrittiva solida"

    return {
        "n_simboli": n_simboli,
        "h1": {
            "p1b_pooled": p1b_pooled,
            "base_rate_pooled": base_rate_pooled,
            "autocorr_mediana": autocorr_med,
            "simboli_p1b_ic90_oltre_base": p1b_ci_ok,
            "su": len(stats),
            "ok": (
                p1b_pooled is not None
                and base_rate_pooled is not None
                and p1b_pooled > base_rate_pooled
                and (autocorr_med or 0) > 0
            ),
        },
        "h2": {"ok_count": h2_ok_count, "su": n_simboli, "ok": h2_ok_count >= 6},
        "h3": {"rho": stab.get("rho"), "inversioni": stab.get("inversioni"), "ok": h3_ok},
        "rule": {
            "quota_vs_always_on": quota_ru,
            "dd_riduzione_relativa": dd_riduzione,
            "vince": rule_vince,
        },
        "esito": esito,
        "statistiche": stats,
        "stabilita": stab,
        "flusso_per_simbolo": per_flusso,
    }


def report_testo(risultato: Dict[str, Any], malformate: int) -> str:
    """Report testuale deterministico (ASCII, leggibile in prove/)."""
    stats: Dict[str, Statistiche] = risultato["statistiche"]
    righe: List[str] = []
    righe.append("P12 — FUNDING: REGIME E TIMING (decision-support, NON promozione)")
    righe.append("=" * 78)
    righe.append(
        "Dati: archivio P8 X-Perp OKX EEA | righe malformate: %d | campione: UN regime (~95g)"
        % malformate
    )
    righe.append("")
    righe.append(
        "%-22s %5s %9s %7s %7s %7s %8s %6s" %
        ("simbolo", "n", "ann.%", "%pos", "p1b", "ac1", "streakNeg", "payback")
    )
    for nome in sorted(stats):
        st = stats[nome]
        righe.append(
            "%-22s %5d %+8.2f%% %6.1f%% %7s %7s %8d %6s" % (
                nome,
                st.n,
                100.0 * st.annualizzato,
                100.0 * st.base_rate,
                ("%.3f" % st.p_media3) if st.p_media3 is not None else "n/d",
                ("%+.3f" % st.autocorr) if st.autocorr is not None else "n/d",
                st.streak_neg_max,
                ("%.0fg" % st.payback_giorni) if st.payback_giorni is not None else "n/d",
            )
        )
    righe.append("")
    for C in COSTI:
        etichetta = "XPerp 0,40%" if C == COSTI[0] else "stress 0,62%"
        positivi = sum(1 for n in stats if netto(stats[n].mu_giornaliera, 30, C) > 0)
        righe.append(
            "Netto@30g (C=%s): %d/%d simboli positivi" % (etichetta, positivi, len(stats))
        )
    righe.append("")
    h1, h2, h3 = risultato["h1"], risultato["h2"], risultato["h3"]
    righe.append("H1 persistenza : p1b pooled %s vs base %s | autocorr mediana %s | p1b_IC90_low>base: %s/%s -> %s" % (
        _fmt_pct(h1["p1b_pooled"]), _fmt_pct(h1["base_rate_pooled"]),
        _fmt_num(h1["autocorr_mediana"]),
        h1.get("simboli_p1b_ic90_oltre_base"), h1.get("su"),
        "OK" if h1["ok"] else "NO"))
    righe.append("H2 netto costi : %d/%d simboli net@30g>0 e payback<=45g -> %s" % (
        h2["ok_count"], h2["su"], "OK" if h2["ok"] else "NO"))
    righe.append("H3 stabilita'  : rho=%s inversioni=%s -> %s" % (
        _fmt_num(h3["rho"]), h3.get("inversioni"), "OK" if h3["ok"] else "NO"))
    r = risultato["rule"]
    righe.append("RULE vs AO     : quota %s | riduzione DD %s -> %s" % (
        _fmt_pct(r["quota_vs_always_on"]), _fmt_pct(r["dd_riduzione_relativa"]),
        "VINCE LA REGOLA" if r["vince"] else "sempre-on"))
    righe.append("")
    righe.append("ESITO: %s" % risultato["esito"].upper())
    righe.append("(nessuna promozione possibile con un solo regime — spec P12)")
    return "\n".join(righe) + "\n"


def _fmt_pct(x: Optional[float]) -> str:
    return "n/d" if x is None else "%.1f%%" % (100.0 * x)


def _fmt_num(x: Optional[float]) -> str:
    return "n/d" if x is None else "%.3f" % x


def report_json(risultato: Dict[str, Any], malformate: int) -> str:
    """Versione JSON serializzabile (per prove/P12_funding_regime.json)."""

    def _conv(o: Any) -> Any:
        if isinstance(o, Statistiche):
            return o.__dict__
        if isinstance(o, EsitoFlusso):
            return o.__dict__
        if isinstance(o, tuple):
            return list(o)
        return str(o)

    out = {"malformate": malformate}
    for k, v in risultato.items():
        if k == "statistiche":
            out[k] = {n: st.__dict__ for n, st in sorted(v.items())}
        else:
            out[k] = v
    return json.dumps(out, indent=1, default=_conv, sort_keys=True)
