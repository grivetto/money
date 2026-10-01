"""money.ricerca.p13_cointegrazione — pairs/basket sui major (lane P13).

PERCHE' QUESTO MODULO ESISTE
============================
Le strategie a trend del filone (P3, P5, P6) condividono lo stesso rischio: il DD nasce
dal mercato che crolla, e nessuna costruzione lo tiene sotto la soglia (P6 lo ha
dimostrato per costruzione). P13 cambia classe: coppie di major in cointegrazione,
posizione MARKET-NEUTRAL (long una gamba, short l'altra): l'esposizione netta al
mercato e' ~0 e il P&L dipende dal RIENTRO dello spread, non dalla direzione. Se
l'edge esiste, per costruzione non soffre il crollo sistemico che ha ucciso i trend.

LA SPEC (coda_catena/P13) e' PRE-REGISTRATA: questo modulo la implementa lettera per
lettera, senza ottimizzazioni. Se i numeri non arrivano, la lane si archivia: e' un
esito previsto e accettato dalla spec, non un fallimento del codice.

REGOLE CONGELATE (dalla spec — ogni variante e' una nuova voce di registro, non una
riga di codice)
-----------------------------------------------------------------------------------
- Coppie: C(10,2) = 45 tra BTC ETH SOL DOGE XRP ADA AVAX LINK LTC DOT (USDT-lungo).
- Screening su ADDESTRAMENTO [2020-10-01, 2024-06-01): EG due passi (OLS
  log(Pa) = a + b·log(Pb), ADF sui residui), |t_rho| >= 3.8 (soglia corretta per
  45 test), half-life = -ln2/ln(1+rho) in [3, 30] giorni, stabilita' beta tra le
  due sotto-finestre |dbeta|/beta <= 30%. Massimo 3 coppie per |t_rho| decrescente.
- Strategia su VERIFICA [2024-06-01, oggi], configurazione congelata:
  z(t) = (spread(t) - media_60g) / sd_60g, solo osservazioni <= t; |z|>=2 allo
  CLOSE t → esecuzione all'APERTURA t+1; z>2 short spread (short A, long B),
  z<-2 long spread. Uscita: |z|<=0.5 oppure stop |z|>=4 oppure fine serie.
  Una posizione per coppia.
- Capitale: 0.25 x equity (al momento della decisione) per coppia; NIENTE leva.
  Costi: CICLO 0.30% sul nozionale di coppia (fee perp 0.05% x 2 lati per gamba,
  due gambe, + slippage 0.05% per gamba, come nella spec).
- FUNDING: differenziale tra le gambe (short riceve su funding positivo, long
  paga) incluso dove l'archivio P8 esiste (dal 2026-06-29); dove non esiste e'
  dichiarato e NON inventato.
- Cancello: DDport <= 25% E expectancy netta per operazione (campione eseguito)
  >= 3 x pedaggio (0.90%). n < 30 → "insufficiente", mai "promossa". Segno
  dell'expectancy cambiato tra le due metà della verifica → archiviata.
- Rottura della relazione: episodio = stop |z|>=4; ROTTA se z non rientra in
  |z|<=0.5 entro 30 giorni; > 20% degli episodi → coppia esclusa a prescindere
  dal P&L.
- Anti-bias: nessun caso, nessun seme, niente I/O di rete; statistiche solo su
  osservazioni <= t; esecuzione t+1; survivorship dichiarato (major listate oggi).

DETERMINISMO: stessi input, stessi numeri.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# --- griglia CONGELATA dalla spec (unica; ogni variante = nuova voce di registro) ---
SOGLIA_T_ROHOGA: float = 3.8           # |t_rho| ADF, corretta per 45 test
HL_MIN: float = 3.0                    # half-life in giorni (min)
HL_MAX: float = 30.0                   # half-life in giorni (max)
STABILITA_BETA_MAX: float = 0.30       # |dbeta|/beta tra le due sotto-finestre
MASIMO_COPIE: int = 3                  # cap dichiarato per il capitale
Z_IN: float = 2.0                      # soglia ingresso
Z_OUT: float = 0.5                     # soglia uscita
Z_STOP: float = 4.0                    # stop
Z_MEDIA_GIORNI: int = 60               # finestra media/sd del z
ALLOCAZIONE: float = 0.25              # quota di equity per coppia
CICLO_COSTO: float = 0.0030            # 0.30% per giro completo, sul nozionale di coppia
SOGLIA_ROTTURA: float = 0.20           # > 20% episodi rotti → coppia esclusa
ROTTURA_GIORNI: int = 30               # rientro oltre 30g = rottura
DDPORT_MAX: float = 0.25               # criterio di successo
MARGINE_EXPECT: float = 3.0            # expectancy netta >= 3 x pedaggio
N_MIN: int = 30                         # sotto: "insufficiente", mai "promossa"

#: Confini di addestramento (ms epoch), dichiarati dalla spec.
ADDESTRAMENTO_INIZIO_MS = 1570915200000    # 2020-10-01T00:00Z
ADDESTRAMENTO_FINE_MS = 1717200000000      # 2024-06-01T00:00Z


# ---------- dati ------------------------------------------------------------------------

def carica_usdt_lungo(cache_dir: str, simboli: Sequence[str]) -> Dict[str, dict]:
    """Prezzi USDT-lungo dal cache di ``dati.py`` (okx_eea_{S}-USDT_1d.json).

    Ritorna ``{asset: {"ts": ms, "log_apertura", "log_chiusura"}}`` (array numpy).
    Un file assente o corto fa fallire il caricamento: meglio non misurare che
    misurare su dati rotti.
    """
    out: Dict[str, dict] = {}
    for s in simboli:
        path = f"{cache_dir}/okx_eea_{s}-USDT_1d.json"
        try:
            with open(path) as f:
                barre = json.load(f)["barre"]
        except FileNotFoundError:
            raise FileNotFoundError(
                f"P13: manca il cache {path}: i dati USDT-lungo sono prerequisito della spec")
        if len(barre) < 300:
            raise ValueError(f"P13: {s} ha solo {len(barre)} barre: insufficiente per EG")
        ts = np.array([b[0] for b in barre], dtype=np.int64)
        aperture = np.array([b[1] for b in barre], dtype=float)
        chiusure = np.array([b[4] for b in barre], dtype=float)
        if np.any(aperture <= 0) or np.any(chiusure <= 0):
            raise ValueError(f"P13: {s} ha prezzi non positivi: dati rotti")
        out[s] = {"ts": ts,
                  "log_apertura": np.log(aperture),
                  "log_chiusura": np.log(chiusure)}
    return out


def allinea(preci: Dict[str, dict], coppia: dict) -> dict:
    """Intersezione dei ts di due serie: stesso asse, nulla inventato.

    Ritorna ``{"ts", "la", "lb", "oa", "ob"}`` (log-chiusura e log-apertura,
    allineati barra a barra).
    """
    a = preci[coppia["gamba_a"]]
    b = preci[coppia["gamba_b"]]
    ts = np.intersect1d(a["ts"], b["ts"])
    ia = {int(t): i for i, t in enumerate(a["ts"])}
    ib = {int(t): i for i, t in enumerate(b["ts"])}
    idx_a = np.array([ia[int(t)] for t in ts])
    idx_b = np.array([ib[int(t)] for t in ts])
    return {"ts": ts,
            "la": a["log_chiusura"][idx_a], "lb": b["log_chiusura"][idx_b],
            "oa": a["log_apertura"][idx_a], "ob": b["log_apertura"][idx_b]}


# ---------- statistica EG (pura, deterministica) ------------------------------------------

def ols_beta(x: np.ndarray, y: np.ndarray) -> Tuple[float, float, float]:
    """OLS y = a + b·x. Ritorna (a, b, r2)."""
    n = len(x)
    X = np.column_stack([np.ones(n), x])
    theta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residui = y - X @ theta
    sse = float(residui @ residui)
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1.0 - sse / ss_tot if ss_tot > 0 else 0.0
    return float(theta[0]), float(theta[1]), r2


def adf_statistica(y: np.ndarray, ritardi: Optional[int] = None) -> Tuple[float, float]:
    """ADF (regressione Δy_t = c + ρ·y_{t-1} + Σ φ_i·Δy_{t-i}).

    Ritorna (t_rho, rho) con t_rho il test-t sul coefficiente ρ. Ritardi Schwarz
    (cap 1..25). Righe senza abbastanza storia scartate: non inventiamo dati.
    """
    n = len(y)
    p = int(math.floor(12.0 * (n / 100.0) ** 0.25)) if ritardi is None else int(ritardi)
    p = min(max(p, 1), 25)
    dy = np.diff(y)                       # n-1 elementi, dy[j] = Δy_{j+1}
    r0 = p
    yy = dy[r0:]                          # Δy_t per t = r0+1 .. n-1
    if len(yy) <= p + 1:
        raise ValueError("serie troppo corta per l'ADF con questi ritardi")
    colonne_y_t_meno_1 = y[r0:n - 1]      # y_{t-1} per t = r0+1 .. n-1
    colonne = [np.ones(len(yy)), colonne_y_t_meno_1]
    for i in range(1, p + 1):
        colonna_dv = dy[r0 - i:n - 1 - i]  # Δy_{t-i}, stesso asse
        assert len(colonna_dv) == len(yy), "indice ADF errato"
        colonne.append(colonna_dv)
    X = np.column_stack(colonne)
    theta, *_ = np.linalg.lstsq(X, yy, rcond=None)
    residui = yy - X @ theta
    dof = len(yy) - X.shape[1]
    cov = (float(residui @ residui) / dof) * np.linalg.inv(X.T @ X)
    se = math.sqrt(max(cov[1, 1], 1e-300))
    return float(theta[1] / se), float(theta[1])


def half_life_giorni(rho_adf: float) -> Optional[float]:
    """half-life = -ln2/ln(1+rho): giorni per tornare alla meta' della distanza."""
    base = 1.0 + rho_adf
    if base <= 0.0 or base >= 1.0:
        return None
    return -math.log(2.0) / math.log(base)


def screening_coppie(preci: Dict[str, dict],
                     da: int = ADDESTRAMENTO_INIZIO_MS,
                     fino: int = ADDESTRAMENTO_FINE_MS) -> List[dict]:
    """EG due passi su addestramento per TUTTE le coppie. Nessuna ottimizzazione.

    Ogni riga riporta i numeri grezzi e il verdetto di OGNI criterio, così il
    report non nasconde il motivo di un rifiuto.
    """
    import itertools
    risultati: List[dict] = []
    for a, b in itertools.combinations(sorted(preci), 2):
        coppia = {"gamba_a": a, "gamba_b": b}
        al = allinea(preci, coppia)
        m = (al["ts"] >= da) & (al["ts"] < fino)
        la, lb = al["la"][m], al["lb"][m]
        n = len(la)
        if n < 300:
            continue
        alfa, beta, r2 = ols_beta(lb, la)
        residui = la - (alfa + beta * lb)
        t_rho, rho = adf_statistica(residui)
        hl = half_life_giorni(rho)
        mezza = n // 2
        _, b1, _ = ols_beta(lb[:mezza], la[:mezza])
        _, b2, _ = ols_beta(lb[mezza:], la[mezza:])
        dbeta = abs(abs(b1) - abs(b2)) / max(abs(beta), 1e-12)
        risultati.append({
            "coppia": f"{a}/{b}", "gamba_a": a, "gamba_b": b,
            "n": int(n), "beta": beta, "r2": r2,
            "t_rho": t_rho, "rho": rho, "half_life_giorni": hl,
            "beta_f1": b1, "beta_f2": b2, "delta_beta_rel": dbeta,
            "pass_t": abs(t_rho) >= SOGLIA_T_ROHOGA,
            "pass_hl": (hl is not None and HL_MIN <= hl <= HL_MAX),
            "pass_stab": dbeta <= STABILITA_BETA_MAX,
        })
    for r in risultati:
        r["pass"] = r["pass_t"] and r["pass_hl"] and r["pass_stab"]
    return risultati


def seleziona(risultati: List[dict]) -> List[dict]:
    """Migliori fino a MASIMO_COPIE tra le passanti, per |t_rho| decrescente.

    Deterministico: a parita' di |t_rho| vince l'ordine lessicografico.
    """
    ok = [r for r in risultati if r["pass"]]
    ok.sort(key=lambda r: (-abs(r["t_rho"]), r["coppia"]))
    return ok[:MASIMO_COPIE]


# ---------- z dello spread (anti-lookahead per costruzione) ------------------------------

def z_seriesi(spread: np.ndarray, finestra: int = Z_MEDIA_GIORNI) -> np.ndarray:
    """z(t) = (spread(t) - media) / sd sulla finestra [t-w+1, t] (solo <= t).

    Vettorizzata con cumsum (O(n)). Prima di ``finestra`` osservazioni non c'e'
    media_60g: z = 0, nessun segnale. sd = 0 → z = 0 (nessuna varianza, nessun
    segnale): mai un segnale inventato.
    """
    n = len(spread)
    z = np.zeros(n)
    if n < finestra:
        return z
    c1 = np.concatenate(([0.0], np.cumsum(spread)))
    c2 = np.concatenate(([0.0], np.cumsum(spread * spread)))
    w = float(finestra)
    for t in range(finestra - 1, n):
        s = c1[t + 1] - c1[t + 1 - finestra]
        s2 = c2[t + 1] - c2[t + 1 - finestra]
        media = s / w
        # varianza di campionamento (ddof=1): coerenza con np.std(ddof=1)
        var = (s2 - w * media * media) / (w - 1.0)
        sd = math.sqrt(var) if var > 0 else 0.0
        z[t] = 0.0 if sd < 1e-12 else (spread[t] - media) / sd
    return z


# ---------- motore (un solo: cash, MTM giornaliero, esecuzione t+1) -----------------------

@dataclass(frozen=True)
class Operazione:
    """Un giro completo di una coppia: ingresso e uscita all'APERTURA di una barra."""

    coppia: str
    lato: str                       # "long_spread" (long A, short B) | "short_spread"
    ts_ingresso: int                # apertura della barra di esecuzione ingresso
    ts_uscita: int                  # apertura (o chiusura finale) dell'esecuzione uscita
    z_ingresso: float
    z_uscita: float
    motivo_uscita: str              # "rientro" | "stop" | "fine_serie"
    nozionale: float                # capitale allocato alla coppia (equity x 0.25)
    pnp_lordo: float                # P&L lordo in valuta (due gambe, hedge pari)
    pnp_netto: float                # lordo - CICLO_COSTO x nozionale
    rotture: bool = False           # stop con mancato rientro in |z|<=0.5 entro 30g


def simula_portafoglio(scelte: Sequence[dict],
                       allineate: Dict[str, dict],
                       giorni: np.ndarray,
                       capitale: float = 1000.0,
                       funding_per_giorno: Optional[Dict[str, Dict[int, float]]] = None
                       ) -> dict:
    """Il conto reale: fino a 3 coppie in parallelo, cassa vincolata, MTM alla chiusura.

    Ordine di ogni barra k (coerente con ``ricerca.portafoglio``):
      1. esecuzione all'APERTURA k di quanto deciso allo close k-1 (prima uscite,
         poi ingressi: la cassa liberata e' disponibile);
      2. mark-to-market alla CHIUSURA k (curva equity);
      3. funding differenziale della giornata (solo dove l'archivio lo fornisce);
      4. decisioni allo close k (z[t], solo osservazioni <= k) per la barra k+1.
    Alla fine della serie le posizioni aperte chiudono all'ultima chiusura
    (motivo "fine_serie"). Deterministico.
    """
    per_coppia: Dict[str, dict] = {}
    for r in scelte:
        d = allineate[r["coppia"]]
        per_coppia[r["coppia"]] = {
            "d": d, "beta": r["beta"],
            "z": z_seriesi(d["la"] - r["beta"] * d["lb"]),
            "map": {int(t): i for i, t in enumerate(d["ts"])},
        }

    cassa = capitale
    aperte: Dict[str, dict] = {}
    programma: Dict[str, Tuple[str, float]] = {}   # coppia -> ("exit", z) | ("entry", z)
    curva: List[Tuple[int, float]] = []
    ops: List[Operazione] = []
    picco = capitale
    max_dd = 0.0
    saltate = 0
    funding_tot = 0.0
    stops: List[Tuple[str, int]] = []              # (coppia, indice barra stop)
    equity_close_prev = capitale                   # equity al close della barra precedente

    def valore_aperte(ts_int: int) -> float:
        tot = 0.0
        for c, st in aperte.items():
            d = per_coppia[c]
            i = d["map"].get(ts_int)
            beta = d["beta"]
            sp = (d["d"]["la"][i] - beta * d["d"]["lb"][i]) if i is not None else st["sp_ing"]
            tot += st["nozionale"] + st["segno"] * st["nozionale"] / 2.0 * (sp - st["sp_ing"])
        return tot

    def chiudi(c: str, ts_int: int, motivo: str, z_dec: float, i_exec: int,
               prezzo_uscita: float) -> None:
        nonlocal cassa
        st = aperte.pop(c)
        sp_out = prezzo_uscita
        lordo = st["segno"] * st["nozionale"] / 2.0 * (sp_out - st["sp_ing"])
        netto = lordo - CICLO_COSTO * st["nozionale"]
        cassa += st["nozionale"] + netto
        ops.append(Operazione(
            coppia=c, lato=st["lato"],
            ts_ingresso=st["ts_ing"], ts_uscita=ts_int,
            z_ingresso=st["z_ing"], z_uscita=z_dec, motivo_uscita=motivo,
            nozionale=st["nozionale"], pnp_lordo=lordo, pnp_netto=netto))
        if motivo == "stop":
            stops.append((c, i_exec))

    for k, ts in enumerate(giorni):
        ts_int = int(ts)
        # 1) esecuzioni all'APERTURA di k (decisone allo close k-1, in programma).
        #    Ordine: PRIMA le uscite (liberano cassa), poi gli ingressi — la cassa
        #    liberata e' disponibile per i segnali di oggi (coerente con portafoglio).
        for c, (azione, z_dec) in programma.items():
            if azione != "exit" or c not in aperte or c not in per_coppia:
                continue
            d = per_coppia[c]["d"]
            i = per_coppia[c]["map"].get(ts_int)
            if i is None:
                continue
            # esecuzione all'apertura di k: prezzo = OA[k]
            sp_out = d["oa"][i] - per_coppia[c]["beta"] * d["ob"][i]
            chiudi(c, ts_int, "stop" if abs(z_dec) >= Z_STOP else "rientro",
                   z_dec, i, sp_out)
        for c, (azione, z_dec) in programma.items():
            if azione != "entry" or c in aperte or c not in per_coppia:
                continue
            d = per_coppia[c]["d"]
            i = per_coppia[c]["map"].get(ts_int)
            if i is None:
                continue
            if abs(z_dec) < Z_IN:      # guard: il segnale deve valere alla decisione
                continue
            equity_dec = equity_close_prev  # equity al close della barra della decisione
            nozionale = ALLOCAZIONE * equity_dec
            if nozionale <= 0 or cassa < nozionale:
                saltate += 1
                continue
            cassa -= nozionale
            lato = "long_spread" if z_dec < 0 else "short_spread"
            seg = 1.0 if lato == "long_spread" else -1.0
            sp_ing = d["oa"][i] - per_coppia[c]["beta"] * d["ob"][i]
            aperte[c] = {"lato": lato, "segno": seg, "nozionale": nozionale,
                         "ts_ing": ts_int, "z_ing": z_dec, "sp_ing": sp_ing}
        programma = {}
        # 2) mark-to-market alla chiusura di k
        equity = cassa + valore_aperte(ts_int)
        curva.append((ts_int, equity))
        if equity > picco:
            picco = equity
        if picco > 0:
            max_dd = max(max_dd, 1.0 - equity / picco)
        # 3) funding differenziale della giornata
        if funding_per_giorno:
            for c, st in aperte.items():
                r = next(x for x in scelte if x["coppia"] == c)
                fa = funding_per_giorno.get(r["gamba_a"], {}).get(ts_int)
                fb = funding_per_giorno.get(r["gamba_b"], {}).get(ts_int)
                if fa is not None and fb is not None:
                    diff = (fb - fa) if st["lato"] == "long_spread" else (fa - fb)
                    cassa += st["nozionale"] / 2.0 * diff
                    funding_tot += st["nozionale"] / 2.0 * diff
        # 4) decisioni allo close di k, per la barra k+1
        if k + 1 < len(giorni):
            for c in per_coppia:
                i = per_coppia[c]["map"].get(ts_int)
                if i is None:
                    continue
                z_t = per_coppia[c]["z"][i]
                if c in aperte:
                    if abs(z_t) <= Z_OUT:
                        programma[c] = ("exit", z_t)
                    elif abs(z_t) >= Z_STOP:
                        programma[c] = ("exit", z_t)
                elif abs(z_t) >= Z_IN:
                    programma[c] = ("entry", z_t)
        equity_close_prev = equity   # equity al close di k, per i sizing di k+1

    # fine serie: chiudi le residue all'ultima CHIUSURA (prezzo = LA[ultimo])
    ultimo = int(giorni[-1])
    for c in list(aperte):
        d = per_coppia[c]
        i = d["map"].get(ultimo)
        z_dec = d["z"][i] if i is not None else 0.0
        i_exec = i if i is not None else len(d["d"]["ts"]) - 1
        sp_ult = d["d"]["la"][i_exec] - d["beta"] * d["d"]["lb"][i_exec]
        chiudi(c, ultimo, "fine_serie", z_dec, i_exec, sp_ult)
    # capitale finale = cassa (dopo le chiusure finali, valutate alla stessa chiusura)
    finale = cassa
    if curva:
        curva = curva[:-1] + [(ultimo, finale)]
        if finale > picco:
            picco = finale

    # ---- diagnosi ROTTURE: stop senza rientro in |z|<=0.5 entro ROTTURA_GIORNI ----
    stop_map: Dict[Tuple[str, int], bool] = {}
    for c, i_stop in stops:
        z = per_coppia[c]["z"]
        fine = min(i_stop + ROTTURA_GIORNI, len(z))
        non_rientrato = all(abs(z[u]) > Z_OUT for u in range(i_stop + 1, fine))
        stop_map[(c, int(per_coppia[c]["d"]["ts"][i_stop]))] = non_rientrato
    ops_out: List[Operazione] = [
        Operazione(**{**o.__dict__,
                      "rotture": stop_map.get((o.coppia, o.ts_uscita), False)})
        if o.motivo_uscita == "stop" else o
        for o in ops]

    return {
        "curva": tuple(curva),
        "ops": ops_out,
        "n": len(ops_out),
        "saltate": saltate,
        "ddport": max_dd,
        "capitale_finale": finale,
        "funding_totale": funding_tot,
    }


def carica_funding(path: str) -> Dict[str, Dict[int, float]]:
    """Archivio P8 (funding_xperp.jsonl) → {asset: {ts_ms: funding}}.

    Dedup su (asset, ts) tenendo la PRIMA riga (deterministico). Il simbolo del
    perp "BTC/USD:USD-310404" → asset "BTC".
    """
    out: Dict[str, Dict[int, float]] = {}
    try:
        with open(path) as f:
            for linea in f:
                r = json.loads(linea)
                asset = r["simbolo"].split("/")[0]
                out.setdefault(asset, {})
                out[asset].setdefault(int(r["ts"]), float(r["funding"]))
    except FileNotFoundError:
        return {}
    return out


# ---------- verifica e verdetto ------------------------------------------------------------

def valuta_verifica(scelte: Sequence[dict],
                    allineate: Dict[str, dict],
                    giorni: np.ndarray,
                    capitale: float = 1000.0,
                    funding_per_giorno: Optional[Dict[str, Dict[int, float]]] = None
                    ) -> dict:
    """Esegue il cancello: DDport, expectancy, t-stat, PF, metà, rotture, esito."""
    res = simula_portafoglio(scelte, allineate, giorni, capitale, funding_per_giorno)
    ops: List[Operazione] = res["ops"]
    n = res["n"]

    # per coppia: expectancy, rotture, half-life di verifica
    per_coppia: Dict[str, dict] = {}
    for r in scelte:
        c = r["coppia"]
        mio = [o for o in ops if o.coppia == c]
        expi = [o.pnp_netto / o.nozionale for o in mio]
        stops_c = [o for o in mio if o.motivo_uscita == "stop"]
        rotture_c = [o for o in stops_c if o.rotture]
        d = allineate[c]
        m_ver = (d["ts"] >= int(giorni[0])) & (d["ts"] < int(giorni[-1]) + 86400000)
        spread_ver = (d["la"] - r["beta"] * d["lb"])[m_ver]
        t_rho_v, rho_v = (None, None)
        hl_v = None
        if len(spread_ver) >= 120:
            try:
                t_rho_v, rho_v = adf_statistica(spread_ver)
                hl_v = half_life_giorni(rho_v)
            except ValueError:
                pass
        per_coppia[c] = {
            "n": len(mio),
            "expectancy_netta": float(np.mean(expi)) if expi else 0.0,
            "stop": len(stops_c),
            "rotture": len(rotture_c),
            "quota_rotture": (len(rotture_c) / len(stops_c)) if stops_c else 0.0,
            "esclusa": bool(stops_c) and (len(rotture_c) / len(stops_c)) > SOGLIA_ROTTURA,
            "half_life_verifica": hl_v,
            "t_rho_verifica": t_rho_v,
        }

    # metriche aggregate
    expi = [o.pnp_netto / o.nozionale for o in ops]
    pnl = [o.pnp_netto for o in ops]
    exp_media = float(np.mean(expi)) if expi else 0.0
    t_stat = 0.0
    if len(expi) > 2:
        sd = float(np.std(expi, ddof=1))
        t_stat = exp_media / (sd / math.sqrt(len(expi))) if sd > 0 else 0.0
    pos = sum(p for p in pnl if p > 0)
    neg = -sum(p for p in pnl if p < 0)
    pf = (pos / neg) if neg > 0 else (float("inf") if pos > 0 else 0.0)

    # le due metà della verifica (per data delle operazioni)
    meze = {"prima": {"n": 0, "exp": 0.0}, "seconda": {"n": 0, "exp": 0.0}}
    if n:
        ts_sorted = sorted(o.ts_uscita for o in ops)
        mid = (ts_sorted[0] + ts_sorted[-1]) // 2
        prima = [o for o in ops if o.ts_uscita < mid]
        seconda = [o for o in ops if o.ts_uscita >= mid]
        meze["prima"]["n"] = len(prima)
        meze["seconda"]["n"] = len(seconda)
        meze["prima"]["exp"] = (float(np.mean([o.pnp_netto / o.nozionale for o in prima]))
                                if prima else 0.0)
        meze["seconda"]["exp"] = (float(np.mean([o.pnp_netto / o.nozionale for o in seconda]))
                                  if seconda else 0.0)
    cambio_segno = (meze["prima"]["n"] > 0 and meze["seconda"]["n"] > 0
                    and (meze["prima"]["exp"] <= 0) != (meze["seconda"]["exp"] <= 0))

    escluse = [c for c, s in per_coppia.items() if s["esclusa"]]
    pedaggio = CICLO_COSTO * MARGINE_EXPECT

    dd_ok = res["ddport"] <= DDPORT_MAX
    exp_ok = exp_media >= pedaggio
    n_ok = n >= N_MIN
    tutte_escluse = bool(scelte) and all(s["esclusa"] for s in per_coppia.values())
    # Priorita' (spec): cambio-segno o tutte-escluse → ARCHIVIATA a prescindere;
    # poi promossa solo se tutti i criteri; altrimenti INSUFFICIENTE (n<30 incluso).
    if cambio_segno or tutte_escluse:
        esito = "archiviata"
    elif dd_ok and exp_ok and n_ok:
        esito = "promossa"
    else:
        esito = "insufficiente"
    motivi: List[str] = []
    if not dd_ok:
        motivi.append(f"DDport {res['ddport']:.1%} > {DDPORT_MAX:.0%}")
    if not exp_ok:
        motivi.append(f"expectancy {exp_media:.3%} < {pedaggio:.2%} (3x pedaggio)")
    if not n_ok:
        motivi.append(f"n={n} < {N_MIN}: insufficiente")
    if cambio_segno:
        motivi.append("cambio di segno dell'expectancy tra le due metà")
    if escluse:
        motivi.append("coppie escluse per rotture: " + ", ".join(escluse))
    if esito == "archiviata" and not motivi:
        motivi.append("coppie tutte escluse o cambio di segno tra le metà")

    return {
        "capitale": capitale,
        "capitale_finale": res["capitale_finale"],
        "rendimento": res["capitale_finale"] / capitale - 1.0,
        "ddport": res["ddport"],
        "n": n,
        "saltate": res["saltate"],
        "expectancy_netta": exp_media,
        "t_stat": t_stat,
        "profit_factor": pf,
        "meze": meze,
        "cambio_segno_meze": cambio_segno,
        "funding_totale": res["funding_totale"],
        "pedaggio_soglia": pedaggio,
        "per_coppia": per_coppia,
        "esclusa_per_rotture": escluse,
        "criteri": {"dd_ok": dd_ok, "exp_ok": exp_ok, "n_ok": n_ok},
        "esito": esito,
        "motivi": motivi,
        "n_operazioni": n,
    }


def report_testo(risultato: Optional[dict], screening: List[dict], scelte: List[dict],
                 periodo_addestramento: str, periodo_verifica: str) -> str:
    righe: List[str] = []
    w = righe.append
    w("P13 — COINTEGRAZIONE: PAIRS/BASKET SUI MAJOR")
    w("=" * 62)
    w(f"Addestramento: {periodo_addestramento} | Verifica: {periodo_verifica} (una volta sola)")
    w("")
    w("SCREENER (%d coppie, soglia |t_rho|>=%.1f, half-life [%.0f,%.0f]g, |dbeta|/beta<=%.0f%%)"
      % (len(screening), SOGLIA_T_ROHOGA, HL_MIN, HL_MAX, STABILITA_BETA_MAX * 100))
    w("-" * 62)
    for r in sorted(screening, key=lambda x: -abs(x["t_rho"]))[:10]:
        mark = "PASS" if r["pass"] else "    "
        w("  [%s] %-12s t_rho=%+7.2f  hl=%5.1fg  beta=%6.3f  dbeta=%5.1f%%"
          % (mark, r["coppia"], r["t_rho"], r["half_life_giorni"] or float("nan"),
             r["beta"], r["delta_beta_rel"] * 100))
    w("  ... (%d coppie totali, mostrate le top 10 per |t_rho|)" % len(screening))
    w("")
    if not scelte:
        w("VERDETTO: NESSUNA COPIA PASSA LO SCREENER → lane archiviata (kill rapido).")
        w("E' un esito previsto e accettato dalla spec, non un fallimento.")
        w("")
        w("ESITO: ARCHIVIATA (screening vuoto)")
        return "\n".join(righe)

    w("COPIE SELEZIONATE (configurazione CONGELATA per la verifica):")
    for r in scelte:
        w("  %-12s beta=%.3f  t_rho_addestr=%+.2f  hl_addestr=%.1fg"
          % (r["coppia"], r["beta"], r["t_rho"], r["half_life_giorni"] or float("nan")))
    w("")
    if risultato is None:
        raise ValueError("report_testo: coppie scelte ma risultato None")
    v = risultato
    w("VERIFICA OOS — capitale %.0f EUR, allocazione %.0f%%/coppia, ciclo %.2f%%"
      % (v["capitale"], ALLOCAZIONE * 100, CICLO_COSTO * 100))
    w("-" * 62)
    w("  capitale finale: %.2f EUR (rend %.2f%%)  funding diff: %+.2f EUR"
      % (v["capitale_finale"], v["rendimento"] * 100, v["funding_totale"]))
    w("  DDport: %.2f%%  (soglia %.0f%%)  %s"
      % (v["ddport"] * 100, DDPORT_MAX * 100,
         "OK" if v["criteri"]["dd_ok"] else "KO"))
    w("  operazioni: %d  (saltate per cassa: %d)  %s"
      % (v["n"], v["saltate"], "OK" if v["criteri"]["n_ok"] else
         "< %d: INSUFFICIENTE" % N_MIN))
    w("  expectancy netta/op: %.3f%%  (soglia %.2f%% = 3x pedaggio)  %s"
      % (v["expectancy_netta"] * 100, v["pedaggio_soglia"] * 100,
         "OK" if v["criteri"]["exp_ok"] else "KO"))
    w("  t-stat: %+.2f  |  profit factor: %s"
      % (v["t_stat"], ("inf" if v["profit_factor"] == float("inf")
                      else "%.2f" % v["profit_factor"])))
    m = v["meze"]
    w("  metà verifica: prima n=%d exp=%+.3f%% | seconda n=%d exp=%+.3f%%  %s"
      % (m["prima"]["n"], m["prima"]["exp"] * 100, m["seconda"]["n"],
         m["seconda"]["exp"] * 100,
         "CAMBIO DI SEGNO → archiviata" if v["cambio_segno_meze"] else "segno stabile"))
    w("")
    w("  PER COPIA (half-life di verifica vs addestramento):")
    for r in scelte:
        s = v["per_coppia"][r["coppia"]]
        hl_ad = r["half_life_giorni"] or float("nan")
        w("    %-12s n=%2d  exp=%+.3f%%  stop=%d  rotture=%d (%.0f%%)  hl_verif=%s  %s"
          % (r["coppia"], s["n"], s["expectancy_netta"] * 100, s["stop"],
             s["rotture"], s["quota_rotture"] * 100,
             ("%.1fg" % s["half_life_verifica"]) if s["half_life_verifica"] else "n/d",
             "ESCLUSA (rotture)" if s["esclusa"] else ""))
    w("")
    w("ESITO: %s" % v["esito"].upper())
    if v["motivi"]:
        for motivo in v["motivi"]:
            w("  - %s" % motivo)
    w("")
    w("Nota sopravvivenza: universo = major listate oggi (dichiarato; i delisting")
    w("non sono rappresentati). Nota funding: misurato solo dove l'archivio P8")
    w("esiste (dal 2026-06-29); il resto del periodo e' a funding zero per costruzione")
    w("dei dati, non per misura.")
    return "\n".join(righe)


def report_json(risultato: Optional[dict], screening: List[dict],
                scelte: List[dict]) -> str:
    payload = {
        "griglia_congelata": {
            "soglia_t_rho": SOGLIA_T_ROHOGA, "half_life": [HL_MIN, HL_MAX],
            "stabilita_beta_max": STABILITA_BETA_MAX, "max_coppie": MASIMO_COPIE,
            "z_ingresso": Z_IN, "z_uscita": Z_OUT, "z_stop": Z_STOP,
            "z_media_giorni": Z_MEDIA_GIORNI, "allocazione": ALLOCAZIONE,
            "ciclo_costo": CICLO_COSTO, "soglia_rotture": SOGLIA_ROTTURA,
            "rotture_giorni": ROTTURA_GIORNI, "ddport_max": DDPORT_MAX,
            "margine_expect": MARGINE_EXPECT, "n_min": N_MIN,
        },
        "screening_top": sorted(screening, key=lambda x: -abs(x["t_rho"]))[:10],
        "scelte": scelte,
        "verifica": risultato,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=float)
