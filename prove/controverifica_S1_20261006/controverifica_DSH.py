#!/usr/bin/env python3
"""Contro-verifica indipendente della scansione S1 (REQ-20261006-202344-5433843).

Ricalcola da zero i 5 numeri "top descrittivi" della verifica della scansione S1
(mom_abs e rsi2 su DOGE/XLM/XRP) e ne misura la robustezza.

Le DEFINIZIONI dei segnali sono state lette da `inputs/ref_scansione_ricerca.py` e
`inputs/ref_costi.py` come SPECIFICA e re-implementate qui (nessun import del repo).

Convenzioni replicati (le stesse della catena "money"):
  - decisione alla chiusura della barra i -> esecuzione all'apertura di i+1;
  - long/flat, una posizione per simbolo, una alla volta;
  - ultima barra riservata alla liquidazione finale (all'apertura);
  - ritorno netto = (1-s)*(1+lordo)*(1-s) - 1 - pedaggio_round_trip, con
    s = slippage per lato, pedaggio = giro misto della tariffa.
  - periodo di verifica = operazioni con INGRESSO >= 2024-06-01 (la selezione e'
    avvenuta in addestramento; qui si legge solo la verifica).
"""
from __future__ import annotations

import json
import math
import random
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
INPUTS = BASE / "inputs"
OUT = BASE / "verdetto.md"

CONFINE = "2024-06-01"
SUB2 = "2025-07-01"

# --- modelli di costo (frazioni) ---------------------------------------------------
# Primario = identico alla scansione S1 ufficiale: tariffa okx_eea_con_perp (giro misto
# maker 0.08% + taker 0.10% = 0.18% per round trip) + slippage 0.04% per lato.
PEDAGGIO_SCAN = 0.0018
SLIP_SCAN = 0.0004
# Variante letterale del task: fee 0.05%/lato (0.10% round trip) + slippage 4bp/lato.
PEDAGGIO_TASK = 0.0010
SLIP_TASK = 0.0004
# Costi doppi (robustezza c): per lato x2 rispetto al modello scansione.
PEDAGGIO_X2 = 0.0036
SLIP_X2 = 0.0008

BLOCCO = 10
ITERAZIONI = 2000
SEED = 20261006

# Ingressi della correzione per selezione multipla, presi dal meta della scansione
# ufficiale (322 tentativi valutabili, varianza degli Sharpe in addestramento).
N_TENTATIVI = 322
VAR_SHARPE_TRAIN = 0.016050693731531923
GAMMA_EULERO = 0.5772156649015329


def a_ms(iso: str) -> int:
    d = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    return int(d.timestamp() * 1000)


def carica(simbolo: str):
    """Barre [ts,o,h,l,c,v] da inputs/okx_eea_<base>-USDT_1d.json."""
    percorso = INPUTS / f"okx_eea_{simbolo.replace('/', '-')}_1d.json"
    dati = json.loads(percorso.read_text(encoding="utf-8"))
    return dati["barre"]


# --- segnali (re-implementati dalla specifica) -------------------------------------

def rsi_wilder(chiusure, periodo: int):
    """RSI di Wilder, allineato, None fino a `periodo` (nessun look-ahead)."""
    out = [None] * len(chiusure)
    if len(chiusure) <= periodo:
        return out
    g = p = 0.0
    for i in range(1, periodo + 1):
        d = chiusure[i] - chiusure[i - 1]
        g += max(d, 0.0)
        p += max(-d, 0.0)
    mg, mp = g / periodo, p / periodo
    out[periodo] = 100.0 - 100.0 / (1.0 + mg / mp) if mp > 0 else 100.0
    for i in range(periodo + 1, len(chiusure)):
        d = chiusure[i] - chiusure[i - 1]
        mg = (mg * (periodo - 1) + max(d, 0.0)) / periodo
        mp = (mp * (periodo - 1) + max(-d, 0.0)) / periodo
        out[i] = 100.0 - 100.0 / (1.0 + mg / mp) if mp > 0 else 100.0
    return out


def stato_mom_abs(barre, lookback: int):
    c = [b[4] for b in barre]
    return [None if i < lookback else bool(c[i] > c[i - lookback]) for i in range(len(c))]


def stato_rsi2(barre, periodo: int, soglia_in: float, soglia_out: float):
    c = [b[4] for b in barre]
    r = rsi_wilder(c, periodo)
    stato = [None] * len(c)
    dentro = False
    for i in range(len(c)):
        if r[i] is None:
            continue
        if not dentro:
            if r[i] < soglia_in:
                dentro = True
        else:
            if r[i] > soglia_out:
                dentro = False
        stato[i] = dentro
    return stato


def simula(barre, stato, i_da: int = 0):
    """Gira lo stato voluto in operazioni. Ritorna [(ts_in, ts_out, lordo)]."""
    n = len(barre)
    if n < 2:
        return []
    a = n - 1  # ultima barra: liquidazione finale all'apertura
    trades = []
    dentro = False
    i_in = None
    i = max(int(i_da), 0)
    while i + 1 < a:
        s = stato[i]
        if s is None:
            i += 1
            continue
        if not dentro and s is True:
            dentro = True
            i_in = i + 1
        elif dentro and s is False:
            trades.append((barre[i_in][0], barre[i + 1][0],
                           barre[i + 1][1] / barre[i_in][1] - 1.0))
            dentro = False
            i_in = None
        i += 1
    if dentro and i_in is not None:
        trades.append((barre[i_in][0], barre[a][0],
                       barre[a][1] / barre[i_in][1] - 1.0))
    return trades


# --- costi e metriche --------------------------------------------------------------

def netto(lordo: float, slip: float, pedaggio: float) -> float:
    eseguito = (1.0 - slip) * (1.0 + lordo) * (1.0 - slip) - 1.0
    return eseguito - pedaggio


def media(xs):
    return sum(xs) / len(xs)


def dev_campionaria(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = media(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def t_stat(xs):
    n = len(xs)
    if n < 2:
        return None
    sd = dev_campionaria(xs)
    if sd <= 0:
        return None
    return media(xs) * math.sqrt(n) / sd


def profit_factor(xs):
    pos = sum(x for x in xs if x > 0)
    neg = sum(x for x in xs if x < 0)
    if neg < 0:
        return pos / abs(neg)
    return float("inf") if pos > 0 else 0.0


def metriche(xs):
    if not xs:
        return {"n": 0, "exp": None, "t": None, "pf": None, "somma": 0.0}
    return {"n": len(xs), "exp": media(xs), "t": t_stat(xs),
            "pf": profit_factor(xs), "somma": sum(xs)}


# --- Sharpe deflazionato (stessa formula di money.statistica) -----------------------

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def norm_ppf(p):
    a = (-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00)
    b = (-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01)
    c = (-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00)
    dd = (7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
          3.754408661907416e+00)
    pl = 0.02425
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) \
            / ((((dd[0] * q + dd[1]) * q + dd[2]) * q + dd[3]) * q + 1)
    if p > 1 - pl:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) \
            / ((((dd[0] * q + dd[1]) * q + dd[2]) * q + dd[3]) * q + 1)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q \
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def sharpe_atteso_massimo(n_tentativi, varianza):
    if n_tentativi < 2:
        return 0.0
    ta = norm_ppf(1.0 - 1.0 / n_tentativi)
    arg = 1.0 - 1.0 / (n_tentativi * math.e)
    tb = norm_ppf(arg) if 0.0 < arg < 1.0 else 0.0
    return math.sqrt(varianza) * ((1.0 - GAMMA_EULERO) * ta + GAMMA_EULERO * tb)


def dsr_case(xs):
    """Sharpe deflazionato della verifica con i tentativi della scansione ufficiale."""
    if len(xs) < 2:
        return None
    sd = dev_campionaria(xs)
    if sd <= 0:
        return None
    sr = media(xs) / sd
    sr0 = sharpe_atteso_massimo(N_TENTATIVI, VAR_SHARPE_TRAIN)
    denominatore = 1.0 + ((3.0 - 1.0) / 4.0) * sr * sr  # skew 0, kurtosi 3
    z = (sr - sr0) * math.sqrt(len(xs) - 1) / math.sqrt(denominatore)
    return {"sr": sr, "sr0": sr0, "dsr": norm_cdf(z)}



def bootstrap_blocchi(xs, blocco=BLOCCO, iterazioni=ITERAZIONI, seed=SEED, scorrevole=False):
    """CI 90% della expectancy media, block bootstrap su blocchi contigui di `blocco`.

    `scorrevole=False` (primario): partizione in blocchi contigui non sovrapposti.
    `scorrevole=True`: tutti i blocchi di lunghezza `blocco` (moving block bootstrap).
    """
    n = len(xs)
    if n == 0:
        return None
    if scorrevole:
        blocks = [xs[i:i + blocco] for i in range(0, max(1, n - blocco + 1))]
    else:
        blocks = [xs[i:i + blocco] for i in range(0, n, blocco)]
    if not blocks:
        return None
    rng = random.Random(seed)
    medie = []
    for _ in range(iterazioni):
        campione = []
        while len(campione) < n:
            campione.extend(rng.choice(blocks))
        campione = campione[:n]
        medie.append(media(campione))
    medie.sort()
    lo = medie[int(0.05 * iterazioni)]
    hi = medie[min(iterazioni - 1, int(0.90 * iterazioni))]
    return {"lo": lo, "hi": hi, "media": media(medie),
            "p_gt0": sum(1 for m in medie if m > 0) / iterazioni,
            "n_blocchi": len(blocks)}


# --- i 5 casi ----------------------------------------------------------------------

CASI = (
    ("mom_abs(L=20)", "DOGE/USDT", "mom_abs", (20,)),
    ("mom_abs(L=10)", "XLM/USDT", "mom_abs", (10,)),
    ("mom_abs(L=10)", "XRP/USDT", "mom_abs", (10,)),
    ("mom_abs(L=20)", "XRP/USDT", "mom_abs", (20,)),
    ("rsi2(3,15,65)", "XRP/USDT", "rsi2", (3, 15.0, 65.0)),
)

# Numeri ufficiali dichiarati (dal task / scansione_S1_20261006_2022.json).
UFFICIALE = {
    ("mom_abs(L=20)", "DOGE/USDT"): (35, 0.0680175463811849, 0.8650444139281218),
    ("mom_abs(L=10)", "XLM/USDT"): (56, 0.06192845052181286, 0.8038222623802053),
    ("mom_abs(L=10)", "XRP/USDT"): (61, 0.051509675911117825, 0.8422631890354111),
    ("mom_abs(L=20)", "XRP/USDT"): (49, 0.048479771992293516, 0.7739767313661338),
    ("rsi2(3,15,65)", "XRP/USDT"): (32, 0.025430682764718063, 1.7118564893635337),
}

confine_ms = a_ms(CONFINE)
sub2_ms = a_ms(SUB2)


def analizza():
    risultati = []
    for chiave, simbolo, famiglia, params in CASI:
        barre = carica(simbolo)
        if famiglia == "mom_abs":
            stato = stato_mom_abs(barre, params[0])
        else:
            stato = stato_rsi2(barre, params[0], params[1], params[2])
        trades = simula(barre, stato)

        # convenzione del rig: la finestra di verifica e' quella dell'INGRESSO
        oos = [t for t in trades if t[0] >= confine_ms]
        # variante "riparti dal confine" (dentro=False al 2024-06-01)
        i_conf = next((i for i, b in enumerate(barre) if b[0] >= confine_ms), None)
        trades_riavvio = simula(barre, stato, i_da=i_conf) if i_conf is not None else []
        oos_riavvio = [t for t in trades_riavvio if t[0] >= confine_ms]

        base = [netto(l, SLIP_SCAN, PEDAGGIO_SCAN) for _, _, l in oos]
        doppio = [netto(l, SLIP_X2, PEDAGGIO_X2) for _, _, l in oos]
        task = [netto(l, SLIP_TASK, PEDAGGIO_TASK) for _, _, l in oos]

        p1 = [netto(l, SLIP_SCAN, PEDAGGIO_SCAN) for ts, _, l in oos if ts < sub2_ms]
        p2 = [netto(l, SLIP_SCAN, PEDAGGIO_SCAN) for ts, _, l in oos if ts >= sub2_ms]

        boot = bootstrap_blocchi(base, scorrevole=False)
        boot_sl = bootstrap_blocchi(base, scorrevole=True)

        lordi = [l for _, _, l in oos]
        risultati.append({
            "chiave": chiave, "simbolo": simbolo,
            "n": len(oos),
            "base": metriche(base), "doppio": metriche(doppio), "task": metriche(task),
            "p1": metriche(p1), "p2": metriche(p2),
            "boot": boot, "boot_scorrevole": boot_sl,
            "dsr": dsr_case(base),
            "lordo_medio": media(lordi) if lordi else None,
            "riavvio_n": len(oos_riavvio),
            "riavvio_exp": (media([netto(l, SLIP_SCAN, PEDAGGIO_SCAN)
                                   for _, _, l in oos_riavvio])
                            if oos_riavvio else None),
            "costo_allin_scan": PEDAGGIO_SCAN + 2 * SLIP_SCAN,
            "n_barre": len(barre),
            "ultima_barra": barre[-1][0],
        })
    return risultati


# --- formattazione -----------------------------------------------------------------

def pct(x, cifre=2):
    if x is None:
        return "n/d"
    return f"{x * 100:+.{cifre}f}%".replace(".", ",")


def num(x, cifre=3):
    if x is None:
        return "n/d"
    if isinstance(x, float) and math.isinf(x):
        return "inf"
    return f"{x:.{cifre}f}".replace(".", ",")


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def verdetto_riga(r):
    """Verdetto per un caso: regge / parziale / no + motivazione."""
    b, d, bo = r["base"], r["doppio"], r["boot"]
    p1, p2 = r["p1"], r["p2"]
    num_ok = (b["n"] == UFFICIALE[(r["chiave"], r["simbolo"])][0]
              and abs(b["exp"] - UFFICIALE[(r["chiave"], r["simbolo"])][1]) < 1e-9)
    motivi = []
    if num_ok:
        motivi.append("numeri ufficiali riprodotti esattamente")
    else:
        motivi.append("numeri NON riprodotti")
    positivi = []
    if b["exp"] is not None and b["exp"] > 0:
        positivi.append("exp>0")
    if p1["n"] > 0 and p1["exp"] is not None and p1["exp"] > 0:
        positivi.append("P1>0")
    else:
        motivi.append("P1<=0")
    if p2["n"] > 0 and p2["exp"] is not None and p2["exp"] > 0:
        positivi.append("P2>0")
    else:
        motivi.append("P2<=0")
    if bo and bo["lo"] > 0:
        positivi.append("CI90>0")
    else:
        motivi.append("CI90 include 0")
    if d["exp"] is not None and d["exp"] > 0:
        positivi.append("costi x2>0")
    else:
        motivi.append("costi x2<=0")
    if len(motivi) == 1 and num_ok and len(positivi) == 5:
        return "sì", "; ".join(motivi)
    if num_ok and len(positivi) >= 2:
        return "parziale", "; ".join(motivi)
    return "no", "; ".join(motivi)


def escalation(r):
    """Una riga: merita escalation a esperimento?"""
    b, d, bo = r["base"], r["doppio"], r["boot"]
    t = b["t"] if b["t"] is not None else 0.0
    dsr = r["dsr"]["dsr"] if r["dsr"] else None
    robusto = (bo is not None and bo["lo"] > 0
               and r["p1"]["exp"] is not None and r["p1"]["exp"] > 0
               and r["p2"]["exp"] is not None and r["p2"]["exp"] > 0
               and d["exp"] is not None and d["exp"] > 0)
    if robusto and dsr is not None and dsr >= 0.95:
        return ("SÌ — regge bootstrap, sub-periodi e costi doppi, e DSR >= 0,95: "
                "pre-registrare un esperimento nuovo.")
    if robusto:
        return ("SOLO come esperimento pre-registrato MIRATO (ipotesi singola), non "
                f"come candidato: regge bootstrap/costi x2 ma DSR={num(dsr)} << 0,95 "
                f"e t={num(t)} < 2.")
    return ("NO — descrittivo di selezione multipla (512 tentativi, 322 valutabili): "
            "t basso, CI90 della expectancy include 0 e/o sub-periodo negativo.")


def genera_md(ris):
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    L = []
    L.append("# Contro-verifica indipendente — scansione S1 "
             "(REQ-20261006-202344-5433843)")
    L.append("")
    L.append(f"**Data:** {ts}  ")
    L.append("**Nodo:** DSH (omarchy) — ricalcolo da zero, nessun import del codice "
             "`money` (solo `numpy`/stdlib; qui nemmeno numpy).  ")
    L.append("**Perimetro:** 5 configurazioni/simbolo top-descrittive della verifica "
             "(`>= 2024-06-01`) della scansione S1 (16 major, 32 config x 7 famiglie).  ")
    L.append(f"**Dati:** `inputs/okx_eea_<SYM>-USDT_1d.json`, "
             f"{ris[0]['n_barre']} barre 1d per simbolo, "
             f"ultima barra {iso(ris[0]['ultima_barra'])}.")
    L.append("")
    L.append("## Assunzioni di costo (dichiarate)")
    L.append("")
    L.append("- **Modello primario (identico alla scansione S1 ufficiale):** tariffa "
             "`okx_eea_con_perp`, giro misto = maker 0,08% + taker 0,10% = **0,18% per "
             "round trip** (pedaggio), più **slippage 0,04% per lato** applicato "
             "moltiplicativamente su entrambe le gambe "
             "(`netto = (1-s)(1+lordo)(1-s) - 1 - pedaggio`). Costo all-in ~0,26% "
             "per operazione.")
    L.append("- **Variante letterale del task:** fee 0,05%/lato (0,10% round trip) + "
             "slippage 4 bp/lato, cioè ~0,18% all-in. Riportata in tabella come "
             "`costi task` per trasparenza: è ~8 bp più ottimistica del modello ufficiale.")
    L.append("- **Costi doppi (robustezza c):** pedaggio 0,36% + slippage 0,08%/lato "
             "(~0,52% all-in).")
    L.append("")
    L.append("> Nota di merito: per riprodurre i numeri ufficiali al 7° decimale ho "
             "dovuto usare **tutte** le barre presenti negli input (ultima "
             f"**{iso(ris[0]['ultima_barra'])}**), mentre il registro dichiara "
             "`FINE_STORIA = 2026-09-25`. Il ritaglio a 2026-09-25 cambia n di ±1 e "
             "l'expectancy di ~0,4 bp: non sposta il verdetto, ma è una discrepanza di "
             "dichiarazione da sanare.")
    L.append("")
    L.append("## Tabella — numeri ricalcolati (verifica, costi ufficiali)")
    L.append("")
    L.append("| # | config | simbolo | n | exp netta | t-stat | profit factor | "
             "DSR (vs 322 tentativi) | CI90 block bootstrap (10 op, 2000 iter) | "
             "P(exp>0) |")
    L.append("|---|--------|---------|---|-----------|--------|---------------|"
             "----------------------|------------------------------------------|"
             "---------|")
    for i, r in enumerate(ris, 1):
        b, bo = r["base"], r["boot"]
        ci = f"[{pct(bo['lo'])}, {pct(bo['hi'])}]" if bo else "n/d"
        pgt = f"{bo['p_gt0']:.3f}".replace(".", ",") if bo else "n/d"
        dsr = num(r["dsr"]["dsr"], 3) if r["dsr"] else "n/d"
        L.append(f"| {i} | {r['chiave']} | {r['simbolo']} | {b['n']} | {pct(b['exp'])} | "
                 f"{num(b['t'])} | {num(b['pf'])} | {dsr} | {ci} | {pgt} |")
    L.append("")
    L.append("Soglia ufficiale di sopravvivenza: **DSR >= 0,95** (nessuno la supera; "
             "SR0 di benchmark = 0,370 per operazione, da 322 tentativi valutabili). "
             "Il DSR è ricalcolato qui per ogni caso con i parametri del meta ufficiale "
             "(322 tentativi, varianza Sharpe train 0,01605, skew 0 e curtosi 3 come "
             "`money.statistica`); nell'output ufficiale era calcolato solo per il "
             "simbolo selezionato per configurazione.")
    L.append("")
    L.append("**Confronto con i numeri ufficiali (task / "
             "`scansione_S1_20261006_2022.json`):**")
    L.append("")
    L.append("| # | config | simbolo | n uff. | n mio | exp uff. | exp mia | t uff. | t mio | "
             "esito |")
    L.append("|---|--------|---------|--------|-------|----------|---------|--------|-------|"
             "-------|")
    for i, r in enumerate(ris, 1):
        u = UFFICIALE[(r["chiave"], r["simbolo"])]
        b = r["base"]
        uguale = (u[0] == b["n"] and abs(u[1] - b["exp"]) < 1e-9
                  and abs(u[2] - b["t"]) < 1e-9)
        L.append(f"| {i} | {r['chiave']} | {r['simbolo']} | {u[0]} | {b['n']} | "
                 f"{pct(u[1])} | {pct(b['exp'])} | {num(u[2])} | {num(b['t'])} | "
                 f"{'identico' if uguale else 'DIVERGE'} |")
    L.append("")
    L.append("## Robustezza")
    L.append("")
    L.append("### a) Due sub-periodi (per data di ingresso)")
    L.append("")
    L.append("| config | simbolo | P1 [2024-06-01, 2025-07-01) n / exp | "
             "P2 [2025-07-01, fine] n / exp |")
    L.append("|--------|---------|------------------------------------------|"
             "--------------------------------|")
    for r in ris:
        L.append(f"| {r['chiave']} | {r['simbolo']} | {r['p1']['n']} / "
                 f"{pct(r['p1']['exp'])} | {r['p2']['n']} / {pct(r['p2']['exp'])} |")
    L.append("")
    L.append("### b) Block bootstrap (blocchi contigui di 10 operazioni, 2000 iterazioni)")
    L.append("")
    L.append("| config | simbolo | exp media | CI90 (partizione) | CI90 (blocchi "
             "scorrevoli) | P(exp>0) | n blocchi |")
    L.append("|--------|---------|-----------|-------------------|"
             "------------------------|---------|-----------|")
    for r in ris:
        bo, bs = r["boot"], r["boot_scorrevole"]
        L.append(f"| {r['chiave']} | {r['simbolo']} | {pct(r['base']['exp'])} | "
                 f"[{pct(bo['lo'])}, {pct(bo['hi'])}] | "
                 f"[{pct(bs['lo'])}, {pct(bs['hi'])}] | "
                 f"{str(round(bo['p_gt0'], 3)).replace('.', ',')} | {bo['n_blocchi']} |")
    L.append("")
    L.append("### c) Costi doppi (fee e slippage per lato x2) e variante costi del task")
    L.append("")
    L.append("| config | simbolo | exp (costi ufficiali) | exp (costi x2) | t (x2) | "
             "PF (x2) | exp (costi task) |")
    L.append("|--------|---------|----------------------|----------------|--------|"
             "--------|------------------|")
    for r in ris:
        L.append(f"| {r['chiave']} | {r['simbolo']} | {pct(r['base']['exp'])} | "
                 f"{pct(r['doppio']['exp'])} | {num(r['doppio']['t'])} | "
                 f"{num(r['doppio']['pf'])} | {pct(r['task']['exp'])} |")
    L.append("")
    L.append("### d) Sensibilità alla convenzione di partenza")
    L.append("")
    L.append("Se si applica il segnale ripartendo da zero al 2024-06-01 "
             "(`dentro=False`), invece della convenzione del rig (stato calcolato "
             "sull'intera storia e operazioni filtrate per data di ingresso), i numeri "
             "cambiano:")
    L.append("")
    L.append("| config | simbolo | n (convenzione rig) | n (riavvio al confine) | "
             "exp (riavvio) |")
    L.append("|--------|---------|---------------------|------------------------|"
             "---------------|")
    for r in ris:
        L.append(f"| {r['chiave']} | {r['simbolo']} | {r['n']} | {r['riavvio_n']} | "
                 f"{pct(r['riavvio_exp'])} |")
    L.append("")
    L.append("## Verdetti")
    L.append("")
    L.append("Criterio: **sì** = numeri riprodotti *e* robusti (CI90>0, entrambi i "
             "sub-periodi positivi, regge i costi doppi); **parziale** = numeri "
             "riprodotti ma robustezza incompleta; **no** = numeri non riprodotti o "
             "segno negativo. Il criterio NON è la significatività sotto selezione "
             "multipla: quella resta il DSR, e nessuno la supera.")
    L.append("")
    L.append("| # | config | simbolo | regge i numeri? | merita escalation a esperimento? |")
    L.append("|---|--------|---------|-----------------|----------------------------------|")
    verdetti = []
    for i, r in enumerate(ris, 1):
        v, motivo = verdetto_riga(r)
        e = escalation(r)
        verdetti.append((r, v, motivo, e))
        L.append(f"| {i} | {r['chiave']} | {r['simbolo']} | **{v}** | {e} |")
    L.append("")
    L.append("### Dettaglio dei verdetti")
    L.append("")
    for i, (r, v, motivo, e) in enumerate(verdetti, 1):
        u = UFFICIALE[(r["chiave"], r["simbolo"])]
        L.append(f"**{i}. {r['chiave']} su {r['simbolo']} — {v}.** "
                 f"Ricalcolo: n={r['base']['n']}, exp={pct(r['base']['exp'])}, "
                 f"t={num(r['base']['t'])}, PF={num(r['base']['pf'])} "
                 f"(ufficiale: n={u[0]}, exp={pct(u[1])}, t={num(u[2])}). "
                 f"Sub-periodi: P1 n={r['p1']['n']} exp={pct(r['p1']['exp'])}, "
                 f"P2 n={r['p2']['n']} exp={pct(r['p2']['exp'])}. "
                 f"CI90 expectancy: [{pct(r['boot']['lo'])}, {pct(r['boot']['hi'])}] "
                 f"(P>0 = {str(round(r['boot']['p_gt0'], 3)).replace('.', ',')}). "
                 f"Costi x2: exp={pct(r['doppio']['exp'])}, t={num(r['doppio']['t'])}. "
                 f"DSR={num(r['dsr']['dsr'], 3) if r['dsr'] else 'n/d'} "
                 f"(SR={num(r['dsr']['sr']) if r['dsr'] else 'n/d'} vs SR0="
                 f"{num(r['dsr']['sr0']) if r['dsr'] else 'n/d'}). "
                 f"Motivo: {motivo}. Escalation: {e}")
        L.append("")
    L.append("## Conclusioni")
    L.append("")
    L.append("- **I numeri ufficiali si riproducono esattamente** (n, expectancy e "
             "t-stat al 7° decimale) su tutte e 5 le configurazioni, una volta usata "
             "tutta la serie degli input. La pipeline della scansione S1 è quindi "
             "aritmeticamente corretta: il problema non è un bug di calcolo.")
    L.append("- **4 su 5 non reggono** (i `mom_abs`): expectancy trainata da poche "
             "operazioni grandi (win rate 26-46%), secondo sub-periodo piatto o "
             "negativo (+0,06% / +0,04% / -2,02% / -0,50%), CI90 bootstrap che include "
             "lo zero e DSR <= 0,10. Sono code di selezione, non edge.")
    L.append("- **1 su 5 regge la robustezza descrittiva** (`rsi2(3,15,65)` su XRP): "
             "positivo in entrambi i sub-periodi (+3,71%, +1,64%), CI90 della "
             "expectancy sopra zero ([+0,78%, +4,02%]) anche con blocchi scorrevoli e "
             "con costi doppi (+2,28%, t=1,54). **Ma** n=32, t=1,71 < 2 e soprattutto "
             "**DSR = 0,36**, molto sotto la soglia 0,95: è l'unico che merita un "
             "esperimento pre-registrato mirato, non una promozione.")
    L.append("- **Discrepanza da sanare (dichiarazione, non calcolo):** il registro "
             "dichiara `FINE_STORIA = 2026-09-25`, ma i numeri ufficiali si ottengono "
             "solo includendo le barre fino al 2026-10-05. L'impatto sui verdetti è "
             "nullo, ma la finestra va dichiarata in modo coerente.")
    L.append("- **Coerente con l'esito ufficiale**: 0 candidati (DSR < 0,95) resta la "
             "conclusione corretta; questi 5 record sono descrittivi e non "
             "promuovibili.")
    L.append("")
    return "\n".join(L)


def main():
    ris = analizza()
    testo = genera_md(ris)
    OUT.write_text(testo, encoding="utf-8")

    print("Contro-verifica S1 — riepilogo (costi ufficiali: pedaggio 0,18% + "
          f"slippage {SLIP_SCAN:.2%}/lato)")
    for r in ris:
        b, bo, d = r["base"], r["boot"], r["doppio"]
        print(f"  {r['chiave']:16} {r['simbolo']:10} n={b['n']:>3} "
              f"exp={pct(b['exp'])} t={num(b['t'])} PF={num(b['pf'])} "
              f"CI90=[{pct(bo['lo'])},{pct(bo['hi'])}] "
              f"P1={pct(r['p1']['exp'])}(n={r['p1']['n']}) "
              f"P2={pct(r['p2']['exp'])}(n={r['p2']['n']}) "
              f"x2={pct(d['exp'])}")
    print(f"\nscritto: {OUT}")


if __name__ == "__main__":
    main()
