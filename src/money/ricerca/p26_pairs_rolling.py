"""money.ricerca.p26_pairs_rolling — cointegrazione v2 ROLLING (lane pairs, P26).

PERCHE' QUESTO MODULO ESISTE
============================
P13 (pairs su 10 major, EG su addestramento unico) e' stata archiviata: 0 coppie
passanti, relazioni sotto-soglia, troppo lente e instabili. P26 e' l'ULTIMO giro
sulla lane, per direttiva dell'owner (18/10): combina le tre varianti ammesse dal
verdetto P13 — universo piu' largo (top 30 perp USDT), finestra z coerente, e
statistiche beta/mean-reversion su finestre ROLLING. Se anche P26 fallisce, la lane
pairs si archivia definitivamente: nessuna variante ulteriore.

LA SPEC (coda_catena/P26_cointegrazione_rolling.md) e' PRE-REGISTRATA: questo modulo
la implementa lettera per lettera, senza ottimizzazioni. Numeri brutti = esito
previsto e accettato, non un fallimento del codice.

REGOLE CONGELATE (dalla spec + addendum dati 18/10 — ogni variante e' una nuova
voce di registro, non una riga di codice)
-----------------------------------------------------------------------------------
- Universo: top 30 perp USDT OKX per notional medio sull'addestramento (lista
  congelata dall'artefatto di preflight prove/p26_preflight_20261018/
  p26_candidate_finestra_effettiva.json; survivorship dichiarato).
- Addestramento effettivo [2020-10-01, 2024-06-01); verifica [2024-06-01, ultima
  barra comune]. Coppie: C(30,2) = 435.
- Finestre ROLLING: W in {120, 180} giorni, passo 5g. In ogni finestra: EG due
  passi (OLS di log(Pa) su log(Pb); ADF sui residui) → t_rho; half-life =
  -ln2/ln(1+rho). Finestra «viva»: |t_rho| >= 3,5 E half-life in [5, 90]g.
- Eleggibilita': viva in >= 60% delle finestre VALIDE dell'addestramento E viva
  nell'ultima finestra. W* = W con quota viva piu' alta (parita': W minore).
  Cap operativo: max 3 coppie (ordine: quota viva decrescente, parita':
  lessicografico).
- Operativita' (verifica, configurazione congelata): beta = OLS dell'ultima
  finestra viva dell'addestramento; z(t) = (spread(t) - media_60g(t)) / sd_60g(t)
  su osservazioni <= t (spillover addestramento incluso, come P13); ingresso
  |z| >= 2 allo close t → esecuzione all'apertura t+1; uscita |z| <= 0,5, stop
  |z| >= 4, stop-di-relazione (ricalcolo EG della finestra [t-W*, t) non viva),
  fine serie. Una posizione per coppia.
- Capitale: 0,25 x equity per coppia, due gambe perp, NIENTE leva. Costi: ciclo
  0,30% sul nozionale di coppia (0,20% fee due gambe + 0,10% slippage); stress
  0,45% riportato sempre. Funding differenziale incluso dove l'archivio P8
  esiste (dal 2026-06-29); altrove dichiarato NON misurato.
- Cancello: DDport <= 25% E expectancy netta >= 3 x pedaggio (0,90%). n < 30 →
  «insufficiente», mai «candidata». Cambio di segno tra le due meta' → archiviata.
  Rotture: stop |z|>=4 senza rientro in |z|<=0,5 entro 30g; > 20% degli stop →
  coppia esclusa a prescindere dal P&L. Secondarie sempre riportate: t-stat, n,
  PF, criterio 8 (3 blocchi contigui), due meta', scenario stress 0,45%.
- Anti-bias: nessun caso, nessun seme, niente I/O di rete; statistiche solo su
  osservazioni <= t; esecuzione t+1; verifica UNA volta sola; nessuna soglia
  ottimizzata sui dati.

DIPENDENZE: solo stdlib + numpy (il venv canonico non ha pandas/statsmodels/scipy:
verificato su mc2 il 18/10). OLS e ADF sono gli stessi algoritmi gia' integrati e
testati in p13_cointegrazione (29 test), qui replicati con le soglie P26.

DETERMINISMO: stessi input, stessi numeri.
"""
from __future__ import annotations

import itertools
import json
import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

# --- griglia CONGELATA dalla spec -----------------------------------------------------
SOGLIA_T_RHO: float = 3.5           # |t_rho| ADF per finestra
HL_MIN: float = 5.0                 # half-life in giorni (min)
HL_MAX: float = 90.0                # half-life in giorni (max)
W_GRIGLIA: Tuple[int, ...] = (120, 180)   # finestre rolling (giorni)
PASSO_FINESTRE_GIORNI: int = 5      # passo della griglia rolling
QUOTA_VIVA_MIN: float = 0.60        # >= 60% delle finestre valide
MAX_COPPIE: int = 3                 # cap operativo dichiarato
Z_IN: float = 2.0                   # soglia ingresso
Z_OUT: float = 0.5                  # soglia uscita (rientro)
Z_STOP: float = 4.0                 # stop
Z_MEDIA_GIORNI: int = 60            # finestra media/sd del z
ALLOCAZIONE: float = 0.25           # quota di equity per coppia
CICLO_COSTO: float = 0.0030         # 0.30% per giro completo, sul nozionale di coppia
COSTO_STRESS: float = 0.0045        # scenario tariffa stress 0.45%
SOGLIA_ROTTURA: float = 0.20        # > 20% degli stop rotti -> coppia esclusa
ROTTURA_GIORNI: int = 30            # rientro oltre 30g = rottura
DDPORT_MAX: float = 0.25            # criterio di successo
MARGINE_EXPECT: float = 3.0         # expectancy netta >= 3 x pedaggio
N_MIN: int = 30                     # sotto: "insufficiente", mai "candidata"
VALID_MIN_OBS: int = 100            # finestra con meno osservazioni = INVALIDA (dato, non segnale)
N_BLOCCHI_CRITERIO8: int = 3        # partizione temporale del criterio 8 (secondaria)

GIORNO_MS: int = 86_400_000
# 2020-10-01T00:00Z = 18536 giorni dall'epoch * 86400000 ms (finestra effettiva,
# addendum dati 18/10: 59/90 coppie hanno prima barra 2020-10-01).
ADDESTRAMENTO_INIZIO_MS = 1_601_510_400_000
# 2024-06-01T00:00Z (confine addestramento/verifica, invariato dalla spec).
ADDESTRAMENTO_FINE_MS = 1_717_200_000_000
VERIFICA_INIZIO_MS = ADDESTRAMENTO_FINE_MS


# ---------- dati ----------------------------------------------------------------------

def carica_usdt_lungo(cache_dir: str, simboli: Sequence[str]) -> Dict[str, dict]:
    """Prezzi USDT-lungo dal cache di ``dati.py`` (okx_eea_{S}-USDT_1d.json).

    Ritorna ``{asset: {"ts": ms, "log_apertura", "log_chiusura"}}`` (array numpy).
    Un file assente o corto fa fallire il caricamento: meglio non misurare che
    misurare su dati rotti (convenzione P13).
    """
    out: Dict[str, dict] = {}
    for s in simboli:
        path = f"{cache_dir}/okx_eea_{s}-USDT_1d.json"
        try:
            with open(path) as f:
                barre = json.load(f)["barre"]
        except FileNotFoundError:
            raise FileNotFoundError(
                f"P26: manca il cache {path}: i dati USDT-lungo sono prerequisito della spec")
        if len(barre) < 300:
            raise ValueError(f"P26: {s} ha solo {len(barre)} barre: insufficiente per EG")
        ts = np.array([b[0] for b in barre], dtype=np.int64)
        aperture = np.array([b[1] for b in barre], dtype=float)
        chiusure = np.array([b[4] for b in barre], dtype=float)
        if np.any(aperture <= 0) or np.any(chiusure <= 0):
            raise ValueError(f"P26: {s} ha prezzi non positivi: dati rotti")
        out[s] = {"ts": ts,
                  "log_apertura": np.log(aperture),
                  "log_chiusura": np.log(chiusure)}
    return out


def allinea(preci: Dict[str, dict], gamba_a: str, gamba_b: str) -> dict:
    """Intersezione dei ts di due serie: stesso asse, nulla inventato (P13).

    Ritorna ``{"ts", "la", "lb", "oa", "ob"}`` (log-chiusura e log-apertura,
    allineati barra a barra).
    """
    a = preci[gamba_a]
    b = preci[gamba_b]
    ts = np.intersect1d(a["ts"], b["ts"])
    ia = {int(t): i for i, t in enumerate(a["ts"])}
    ib = {int(t): i for i, t in enumerate(b["ts"])}
    idx_a = np.array([ia[int(t)] for t in ts])
    idx_b = np.array([ib[int(t)] for t in ts])
    return {"ts": ts,
            "la": a["log_chiusura"][idx_a], "lb": b["log_chiusura"][idx_b],
            "oa": a["log_apertura"][idx_a], "ob": b["log_apertura"][idx_b]}


# ---------- statistica EG (pura, deterministica; stessa di P13) -------------------------

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
    (Algoritmo identico a p13_cointegrazione, verificato dai suoi 29 test.)
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
        if len(colonna_dv) != len(yy):
            raise RuntimeError("invariante violata: indice ADF errato")
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


def eg_finestra(la_win: np.ndarray, lb_win: np.ndarray) -> dict:
    """EG due passi su una finestra: ritorna {t_rho, rho, half_life_giorni, beta,
    alfa, r2, viva} (viva = |t_rho| >= soglia E half-life in [5, 90]g)."""
    alfa, beta, r2 = ols_beta(lb_win, la_win)
    residui = la_win - (alfa + beta * lb_win)
    t_rho, rho = adf_statistica(residui)
    hl = half_life_giorni(rho)
    viva = abs(t_rho) >= SOGLIA_T_RHO and (hl is not None and HL_MIN <= hl <= HL_MAX)
    return {"t_rho": t_rho, "rho": rho, "half_life_giorni": hl,
            "beta": beta, "alfa": alfa, "r2": r2, "viva": bool(viva)}


# ---------- screening rolling -----------------------------------------------------------

def finestre_rolling(al: dict, W: int, da: int, fino: int,
                     passo: int = PASSO_FINESTRE_GIORNI) -> List[dict]:
    """Finestre [fine - W·g, fine) su griglia calendariale: fine = da+W, +passo·g, ...

    ``al`` = coppia allineata ({"ts", "la", "lb"}). Ogni voce riporta i numeri
    grezzi e il verdetto di OGNI criterio; le finestre con meno di VALID_MIN_OBS
    osservazioni sono INVALIDE (dato insufficiente, non segnale) e non contano
    nella quota.
    """
    ts = al["ts"]
    la = al["la"]
    lb = al["lb"]
    W_ms = W * GIORNO_MS
    passo_ms = passo * GIORNO_MS
    # griglia ancorata alla FINE: l'ultima finestra termina esattamente a ``fino``
    # (la beta congelata copre tutti i giorni di addestramento, nessuna coda).
    k_max = (fino - (da + W_ms)) // passo_ms
    if k_max < 0:
        return []
    fine_list = [fino - k * passo_ms for k in range(k_max, -1, -1)]
    out: List[dict] = []
    for fine in fine_list:
        inizio = fine - W_ms
        m = (ts >= inizio) & (ts < fine)
        n = int(m.sum())
        if n >= VALID_MIN_OBS:
            try:
                eg = eg_finestra(la[m], lb[m])
            except (ValueError, np.linalg.LinAlgError) as e:
                # finestra degenerata (residui singolari): dato, non segnale —
                # esclusa dalla quota, mai silenziosa
                out.append({"fine_ts": int(fine), "n": n, "valida": False,
                            "errore": f"{type(e).__name__}: {e}",
                            "t_rho": None, "rho": None, "half_life_giorni": None,
                            "beta": None, "alfa": None, "r2": None, "viva": False})
            else:
                out.append({"fine_ts": int(fine), "n": n, "valida": True,
                            **eg})
        else:
            out.append({"fine_ts": int(fine), "n": n, "valida": False,
                        "t_rho": None, "rho": None, "half_life_giorni": None,
                        "beta": None, "alfa": None, "r2": None, "viva": False})
    return out


def screening_rolling(preci: Dict[str, dict], simboli: Sequence[str],
                      da: int = ADDESTRAMENTO_INIZIO_MS,
                      fino: int = ADDESTRAMENTO_FINE_MS) -> List[dict]:
    """EG rolling su addestramento per TUTTE le coppie x W in {120, 180}.

    Ogni riga: quota di finestre valide «vive», ultima finestra, e i numeri
    grezzi dell'ultima finestra (beta congelata per la verifica). Nessuna
    ottimizzazione, nessuna soglia scelta sui dati.
    """
    risultati: List[dict] = []
    for a, b in itertools.combinations(sorted(simboli), 2):
        al = allinea(preci, a, b)
        for W in W_GRIGLIA:
            finestre = finestre_rolling(al, W, da, fino)
            valide = [f for f in finestre if f["valida"]]
            n_vive = sum(1 for f in valide if f["viva"])
            quota = (n_vive / len(valide)) if valide else 0.0
            ultima = finestre[-1] if finestre else {"valida": False, "viva": False}
            ultima_viva = bool(ultima["valida"] and ultima["viva"])
            pass_ = quota >= QUOTA_VIVA_MIN and ultima_viva
            risultati.append({
                "coppia": f"{a}/{b}", "gamba_a": a, "gamba_b": b, "W": W,
                "n_finestre": len(finestre), "n_valide": len(valide),
                "n_vive": n_vive, "quota_viva": quota,
                "ultima_viva": ultima_viva,
                "beta_ultima": ultima.get("beta"), "alfa_ultima": ultima.get("alfa"),
                "t_rho_ultima": ultima.get("t_rho"),
                "half_life_ultima": ultima.get("half_life_giorni"),
                "pass": bool(pass_),
            })
    return risultati


def eleggibilita(risultati: List[dict]) -> List[dict]:
    """Seleziona fino a MAX_COPPIE coppie eleggibili, W* per quota viva decrescente.

    Per coppia vale il (coppia, W) con quota piu' alta (parita': W minore) — la
    scelta di W e' fatta SOLO su addestramento ed e' congelata per la verifica.
    Ordinamento finale: quota viva decrescente, parita' lessicografica sulla coppia.
    Deterministico. Le voci ritornate sono gia' normalizzate per il motore:
    ``beta`` = OLS dell'ultima finestra viva (congelata), ``W`` = finestra scelta.
    """
    best: Dict[str, dict] = {}
    for r in risultati:
        if not r["pass"]:
            continue
        c = r["coppia"]
        cur = best.get(c)
        if cur is None or r["quota_viva"] > cur["quota_viva"] or (
                r["quota_viva"] == cur["quota_viva"] and r["W"] < cur["W"]):
            best[c] = r
    ok = sorted(best.values(), key=lambda r: (-r["quota_viva"], r["coppia"]))
    scelte: List[dict] = []
    for r in ok[:MAX_COPPIE]:
        scelte.append({
            "coppia": r["coppia"], "gamba_a": r["gamba_a"], "gamba_b": r["gamba_b"],
            "W": r["W"], "quota_viva": r["quota_viva"],
            "n_vive": r["n_vive"], "n_valide": r["n_valide"],
            "ultima_viva": r["ultima_viva"],
            "beta": r["beta_ultima"], "alfa": r["alfa_ultima"],
            "t_rho": r["t_rho_ultima"], "half_life_giorni": r["half_life_ultima"],
        })
    return scelte


# ---------- z dello spread (anti-lookahead per costruzione; stessa di P13) --------------

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
        var = (s2 - w * media * media) / (w - 1.0)
        sd = math.sqrt(var) if var > 0 else 0.0
        z[t] = 0.0 if sd < 1e-12 else (spread[t] - media) / sd
    return z


# ---------- ricalcolo della relazione (stop-di-relazione) -------------------------------

def serie_relazione(al: dict, W: int) -> np.ndarray:
    """Ricalcolo rolling GIORNALIERO della relazione: per ogni indice i, EG sulla
    finestra [ts_i - W·g, ts_i] (osservazioni <= i, spillover addestramento incluso)
    → «viva». Ritorna array bool allineato ad ``al["ts"]``; False dove manca storia.

    E' il «ricalcolo» dello stop-di-relazione: una posizione aperta chiude quando
    la finestra corrente non e' piu' viva (|t_rho| >= 3,5 E half-life in [5, 90]g).
    """
    ts = al["ts"]
    la = al["la"]
    lb = al["lb"]
    W_ms = W * GIORNO_MS
    n = len(ts)
    out = np.zeros(n, dtype=bool)
    for i in range(n):
        fine = ts[i]
        m = (ts > fine - W_ms) & (ts <= fine)
        if int(m.sum()) < VALID_MIN_OBS:
            continue
        try:
            out[i] = bool(eg_finestra(la[m], lb[m])["viva"])
        except (ValueError, np.linalg.LinAlgError):
            out[i] = False   # finestra degenerata: relazione non "viva"
    return out


# ---------- motore (un solo: cash, MTM giornaliero, esecuzione t+1; derivato da P13) ----

@dataclass(frozen=True)
class Operazione:
    """Un giro completo di una coppia: ingresso e uscita all'APERTURA di una barra."""

    coppia: str
    lato: str                       # "long_spread" (long A, short B) | "short_spread"
    ts_ingresso: int                # apertura della barra di esecuzione ingresso
    ts_uscita: int                  # apertura (o chiusura finale) dell'esecuzione uscita
    z_ingresso: float
    z_uscita: float
    motivo_uscita: str              # "rientro" | "stop" | "relazione" | "fine_serie"
    nozionale: float                # capitale allocato alla coppia (equity x 0.25)
    pnp_lordo: float                # P&L lordo in valuta (due gambe, hedge pari)
    pnp_netto: float                # lordo - costo ciclo x nozionale
    rotture: bool = False           # stop con mancato rientro in |z|<=0.5 entro 30g


def simula_portafoglio(scelte: Sequence[dict],
                       allineate: Dict[str, dict],
                       giorni: np.ndarray,
                       capitale: float = 1000.0,
                       funding_per_giorno: Optional[Dict[str, Dict[int, float]]] = None,
                       costo: float = CICLO_COSTO,
                       relazione: Optional[Dict[str, np.ndarray]] = None
                       ) -> dict:
    """Il conto reale: fino a 3 coppie in parallelo, cassa vincolata, MTM alla chiusura.

    Ordine di ogni barra k (coerente con ``ricerca.portafoglio`` e P13):
      1. esecuzione all'APERTURA k di quanto deciso allo close k-1 (prima uscite,
         poi ingressi: la cassa liberata e' disponibile);
      2. mark-to-market alla CHIUSURA k (curva equity);
      3. funding differenziale della giornata (solo dove l'archivio lo fornisce);
      4. decisioni allo close k (z[t], solo osservazioni <= k) per la barra k+1.
    Decisioni di uscita (priorita' della spec): rientro |z| <= 0,5 · stop
    |z| >= 4 · stop-di-relazione (``relazione[c][i]`` False) · fine serie.
    Alla fine della serie le posizioni aperte chiudono all'ultima chiusura
    (motivo "fine_serie"). Deterministico.
    """
    per_coppia: Dict[str, dict] = {}
    for r in scelte:
        d = allineate[r["coppia"]]
        per_coppia[r["coppia"]] = {
            "d": d, "beta": r["beta"],
            "z": z_seriesi(d["la"] - r["beta"] * d["lb"]),
            "rel": (relazione[r["coppia"]] if relazione else None),
            "map": {int(t): i for i, t in enumerate(d["ts"])},
        }

    cassa = capitale
    aperte: Dict[str, dict] = {}
    programma: Dict[str, Tuple[str, float, str]] = {}
    curva: List[Tuple[int, float]] = []
    ops: List[Operazione] = []
    picco = capitale
    max_dd = 0.0
    saltate = 0
    funding_tot = 0.0
    stops: List[Tuple[str, int]] = []              # (coppia, indice barra stop)
    equity_close_prev = capitale                   # equity al close della barra precedente

    # MTM delle posizioni aperte: nozionale + segno x nozionale/2 x Δspread
    def valore_aperte(ts_int: int) -> float:
        tot = 0.0
        for c, st in aperte.items():
            d = per_coppia[c]["d"]
            i = per_coppia[c]["map"].get(ts_int)
            if i is not None:
                sp = d["la"][i] - per_coppia[c]["beta"] * d["lb"][i]
            else:
                sp = st["sp_ing"]
            tot += st["nozionale"] + st["segno"] * st["nozionale"] / 2.0 * (sp - st["sp_ing"])
        return tot

    def chiudi(c: str, ts_int: int, motivo: str, z_dec: float, i_exec: int,
               prezzo_uscita: float) -> None:
        nonlocal cassa
        st = aperte.pop(c)
        sp_out = prezzo_uscita
        lordo = st["segno"] * st["nozionale"] / 2.0 * (sp_out - st["sp_ing"])
        netto = lordo - costo * st["nozionale"]
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
        # 1) esecuzioni all'APERTURA di k (decisione allo close k-1, in programma).
        for c, (azione, z_dec, motivo) in list(programma.items()):
            if azione != "exit" or c not in aperte or c not in per_coppia:
                continue
            d = per_coppia[c]["d"]
            i = per_coppia[c]["map"].get(ts_int)
            if i is None:
                continue
            sp_out = d["oa"][i] - per_coppia[c]["beta"] * d["ob"][i]
            chiudi(c, ts_int, motivo, z_dec, i, sp_out)
        for c, (azione, z_dec, _motivo) in list(programma.items()):
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
                rel = per_coppia[c]["rel"]
                if c in aperte:
                    if abs(z_t) <= Z_OUT:
                        programma[c] = ("exit", z_t, "rientro")
                    elif abs(z_t) >= Z_STOP:
                        programma[c] = ("exit", z_t, "stop")
                    elif rel is not None and not bool(rel[i]):
                        programma[c] = ("exit", z_t, "relazione")
                elif abs(z_t) >= Z_IN:
                    programma[c] = ("entry", z_t, "")
        equity_close_prev = equity   # equity al close di k, per i sizing di k+1

    # fine serie: chiudi le residue all'ultima CHIUSURA (prezzo = LA[ultimo])
    ultimo = int(giorni[-1])
    for c in list(aperte):
        d = per_coppia[c]["d"]
        i = per_coppia[c]["map"].get(ultimo)
        z_dec = per_coppia[c]["z"][i] if i is not None else 0.0
        i_exec = i if i is not None else len(d["ts"]) - 1
        sp_ult = d["la"][i_exec] - per_coppia[c]["beta"] * d["lb"][i_exec]
        chiudi(c, ultimo, "fine_serie", z_dec, i_exec, sp_ult)
    # capitale finale = cassa (dopo le chiusure finali, valutate alla stessa chiusura)
    finale = cassa
    if curva:
        curva = curva[:-1] + [(ultimo, finale)]
        if finale > picco:
            picco = finale

    # ---- diagnosi ROTTURE: stop senza rientro in |z|<=0.5 entro ROTTURA_GIORNI ----
    return {
        "curva": tuple(curva),
        "ops": ops,
        "n": len(ops),
        "saltate": saltate,
        "ddport": max_dd,
        "capitale_finale": finale,
        "funding_totale": funding_tot,
        "stops": stops,
        "per_coppia": per_coppia,
    }


def classifica_rotture(per_coppia: Dict[str, dict], stops: List[Tuple[str, int]],
                       ops: List[Operazione]) -> List[Operazione]:
    """Rotture: uno stop con z che NON rientra in |z| <= 0.5 entro ROTTURA_GIORNI.

    Ritorna le operazioni con il campo ``rotture`` compilato (solo gli stop).
    Funzione pura (nessun I/O), testabile su serie esatte.
    """
    stop_map: Dict[Tuple[str, int], bool] = {}
    for c, i_stop in stops:
        z = per_coppia[c]["z"]
        fine = min(i_stop + ROTTURA_GIORNI, len(z))
        non_rientrato = all(abs(z[u]) > Z_OUT for u in range(i_stop + 1, fine))
        stop_map[(c, int(per_coppia[c]["d"]["ts"][i_stop]))] = non_rientrato
    return [
        Operazione(**{**o.__dict__, "rotture": stop_map.get((o.coppia, o.ts_uscita), False)})
        if o.motivo_uscita == "stop" else o
        for o in ops
    ]


def carica_funding(path: str) -> Dict[str, Dict[int, float]]:
    """Archivio P8 (funding_xperp.jsonl) → {asset: {ts_ms: funding}} (come P13).

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


# ---------- verifica e verdetto ---------------------------------------------------------

def criterio8_serie(ritorni_netti: Sequence[float],
                    n_blocchi: int = N_BLOCCHI_CRITERIO8) -> Optional[dict]:
    """Criterio 8 (secondario, sempre riportato): partizione in blocchi CONTIGUI
    per tempo, rimozione del blocco migliore, expectancy del resto.

    ``dipende_da_un_solo_blocco`` = True se senza il blocco migliore l'expectancy
    netta media dei restanti e' <= 0 (semantica di money.cancello). Ritorna None
    se la serie e' vuota (criterio non applicabile).
    """
    n = len(ritorni_netti)
    if n == 0:
        return None
    k = min(max(n_blocchi, 1), n)
    base, resto = divmod(n, k)
    blocchi: List[List[float]] = []
    acc = 0
    for i in range(k):
        fine = acc + base + (1 if i < resto else 0)
        blocchi.append(list(ritorni_netti[acc:fine]))
        acc = fine
    exp_per_blocco = [math.fsum(b) / len(b) for b in blocchi]
    migliore = max(range(len(blocchi)), key=lambda i: exp_per_blocco[i])
    restanti = [r for i, b in enumerate(blocchi) if i != migliore for r in b]
    senza = (math.fsum(restanti) / len(restanti)) if restanti else None
    return {
        "n_blocchi": k,
        "expectancy_per_blocco": exp_per_blocco,
        "n_per_blocco": [len(b) for b in blocchi],
        "blocco_migliore": migliore,
        "expectancy_senza_migliore": senza,
        "dipende_da_un_solo_blocco": bool(senza is not None and senza <= 0.0),
    }


def valuta_verifica(scelte: Sequence[dict],
                    allineate: Dict[str, dict],
                    giorni: np.ndarray,
                    capitale: float = 1000.0,
                    funding_per_giorno: Optional[Dict[str, Dict[int, float]]] = None,
                    relazione: Optional[Dict[str, np.ndarray]] = None
                    ) -> dict:
    """Esegue il cancello: DDport, expectancy, t-stat, PF, meta', criterio 8,
    rotture, scenario stress 0,45%. Esiti ammessi: {candidata_su_evidenza,
    insufficiente, archiviata} (nessun altro)."""
    res = simula_portafoglio(scelte, allineate, giorni, capitale,
                             funding_per_giorno, CICLO_COSTO, relazione)
    ops: List[Operazione] = classifica_rotture(
        res["per_coppia"], res["stops"], res["ops"])
    n = res["n"]

    # per coppia: expectancy, rotture, uscite per relazione, half-life di verifica
    per_coppia: Dict[str, dict] = {}
    for r in scelte:
        c = r["coppia"]
        mio = [o for o in ops if o.coppia == c]
        expi = [o.pnp_netto / o.nozionale for o in mio]
        stops_c = [o for o in mio if o.motivo_uscita == "stop"]
        rotture_c = [o for o in stops_c if o.rotture]
        rel_c = [o for o in mio if o.motivo_uscita == "relazione"]
        d = allineate[c]
        m_ver = (d["ts"] >= int(giorni[0])) & (d["ts"] < int(giorni[-1]) + GIORNO_MS)
        spread_ver = (d["la"] - r["beta"] * d["lb"])[m_ver]
        t_rho_v, rho_v = (None, None)
        hl_v = None
        if len(spread_ver) >= 120:
            try:
                t_rho_v, rho_v = adf_statistica(spread_ver)
                hl_v = half_life_giorni(rho_v)
            except (ValueError, np.linalg.LinAlgError):
                pass
        per_coppia[c] = {
            "n": len(mio),
            "expectancy_netta": float(np.mean(expi)) if expi else 0.0,
            "stop": len(stops_c),
            "rotture": len(rotture_c),
            "quota_rotture": (len(rotture_c) / len(stops_c)) if stops_c else 0.0,
            "esclusa": bool(stops_c) and (len(rotture_c) / len(stops_c)) > SOGLIA_ROTTURA,
            "uscite_relazione": len(rel_c),
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

    # le due meta' della verifica (per data delle operazioni)
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

    # criterio 8 (secondario, riportato; semantica di money.cancello)
    c8 = criterio8_serie(expi)

    # scenario stress 0,45%: stessi segnali, costo ciclo diverso
    res_stress = simula_portafoglio(scelte, allineate, giorni, capitale,
                                    funding_per_giorno, COSTO_STRESS, relazione)
    ops_stress = classifica_rotture(res_stress["per_coppia"], res_stress["stops"],
                                    res_stress["ops"])
    expi_stress = [o.pnp_netto / o.nozionale for o in ops_stress]
    stress = {
        "costo": COSTO_STRESS,
        "n": len(ops_stress),
        "expectancy_netta": float(np.mean(expi_stress)) if expi_stress else 0.0,
        "ddport": res_stress["ddport"],
        "capitale_finale": res_stress["capitale_finale"],
        "rendimento": res_stress["capitale_finale"] / capitale - 1.0,
        "funding_totale": res_stress["funding_totale"],
    }

    escluse = [c for c, s in per_coppia.items() if s["esclusa"]]
    pedaggio = CICLO_COSTO * MARGINE_EXPECT

    dd_ok = res["ddport"] <= DDPORT_MAX
    exp_ok = exp_media >= pedaggio
    n_ok = n >= N_MIN
    tutte_escluse = bool(scelte) and all(s["esclusa"] for s in per_coppia.values())
    if cambio_segno or tutte_escluse:
        esito = "archiviata"
    elif dd_ok and exp_ok and n_ok:
        esito = "candidata_su_evidenza"
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
        motivi.append("cambio di segno dell'expectancy tra le due meta'")
    if escluse:
        motivi.append("coppie escluse per rotture: " + ", ".join(escluse))
    if esito == "archiviata" and not motivi:
        motivi.append("coppie tutte escluse o cambio di segno tra le meta'")

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
        "criterio8": c8,
        "funding_totale": res["funding_totale"],
        "pedaggio_soglia": pedaggio,
        "per_coppia": per_coppia,
        "esclusa_per_rotture": escluse,
        "criteri": {"dd_ok": dd_ok, "exp_ok": exp_ok, "n_ok": n_ok},
        "esito": esito,
        "motivi": motivi,
        "stress": stress,
        "ops": ops,
    }


# ---------- report ----------------------------------------------------------------------

def report_testo(risultato: Optional[dict], screening: List[dict], scelte: List[dict],
                 universo: Sequence[str], periodo_addestramento: str,
                 periodo_verifica: str) -> str:
    righe: List[str] = []
    w = righe.append
    w("P26 — COINTEGRAZIONE V2: UNIVERSO ESTESO + STATISTICA ROLLING (lane pairs)")
    w("=" * 72)
    w(f"Addestramento: {periodo_addestramento} | Verifica: {periodo_verifica} (una volta sola)")
    w(f"Universo: top {len(universo)} perp USDT (notional medio addestramento;")
    w("  lista congelata da prove/p26_preflight_20261018/p26_candidate_finestra_effettiva.json)")
    w("  " + ", ".join(universo))
    w("")
    n_coppie = len({r["coppia"] for r in screening})
    w(f"SCREENER ROLLING ({n_coppie} coppie x W in {W_GRIGLIA}, passo {PASSO_FINESTRE_GIORNI}g;")
    w(f"  viva = |t_rho|>= {SOGLIA_T_RHO} E half-life [{HL_MIN:.0f},{HL_MAX:.0f}]g;")
    w(f"  eleggibile = viva >= {QUOTA_VIVA_MIN:.0%} delle finestre valide E ultima viva)")
    w("-" * 72)
    for r in sorted(screening, key=lambda x: -x["quota_viva"])[:12]:
        mark = "PASS" if r["pass"] else "    "
        hl = ("%.1fg" % r["half_life_ultima"]) if r["half_life_ultima"] else "n/d"
        t = ("%+7.2f" % r["t_rho_ultima"]) if r["t_rho_ultima"] is not None else "    n/d"
        w("  [%s] %-10s W=%3d  vive %3d/%3d (%5.1f%%)  ult:%s  t=%s  hl=%s"
          % (mark, r["coppia"], r["W"], r["n_vive"], r["n_valide"],
             r["quota_viva"] * 100, "viva" if r["ultima_viva"] else "no  ", t, hl))
    w("  ... (%d righe coppia x W totali)" % len(screening))
    w("")
    if not scelte:
        w("VERDETTO: NESSUNA COPPIA ELEGGIBILE IN ADDESTRAMENTO.")
        w("Esito previsto e accettato dalla spec: lane pairs ARCHIVIATA DEFINITIVAMENTE")
        w("(nessuna variante ulteriore senza un fatto nuovo esterno).")
        w("")
        w("ESITO: ARCHIVIATA_DEFINITIVA (screening vuoto)")
        return "\n".join(righe)

    w("COPPIE SELEZIONATE (configurazione CONGELATA per la verifica):")
    for r in scelte:
        w("  %-10s W=%3d quota=%5.1f%%  beta=%.3f  t_rho_ult=%+.2f  hl_ult=%s"
          % (r["coppia"], r["W"], r["quota_viva"] * 100, r["beta"],
             r["t_rho"] or float("nan"),
             ("%.1fg" % r["half_life_giorni"]) if r["half_life_giorni"] else "n/d"))
    w("")
    if risultato is None:
        raise ValueError("report_testo: coppie scelte ma risultato None")
    v = risultato
    w("VERIFICA OOS — capitale %.0f EUR, allocazione %.0f%%/coppia, ciclo %.2f%%"
      % (v["capitale"], ALLOCAZIONE * 100, CICLO_COSTO * 100))
    w("-" * 72)
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
    c8 = v["criterio8"]
    if c8:
        w("  criterio 8 (%d blocchi contigui): exp per blocco %s  senza migliore: %s  %s"
          % (c8["n_blocchi"],
             ", ".join("%+.3f%%" % (e * 100) for e in c8["expectancy_per_blocco"]),
             ("%+.3f%%" % (c8["expectancy_senza_migliore"] * 100))
             if c8["expectancy_senza_migliore"] is not None else "n/d",
             "DIPENDE DA UN SOLO BLOCCO" if c8["dipende_da_un_solo_blocco"]
             else "edge distribuito"))
    m = v["meze"]
    w("  meta' verifica: prima n=%d exp=%+.3f%% | seconda n=%d exp=%+.3f%%  %s"
      % (m["prima"]["n"], m["prima"]["exp"] * 100, m["seconda"]["n"],
         m["seconda"]["exp"] * 100,
         "CAMBIO DI SEGNO -> archiviata" if v["cambio_segno_meze"] else "segno stabile"))
    s = v["stress"]
    w("  SCENARIO STRESS %.2f%%: exp=%+.3f%%  DDport=%.2f%%  finale=%.2f EUR"
      % (s["costo"] * 100, s["expectancy_netta"] * 100, s["ddport"] * 100,
         s["capitale_finale"]))
    w("")
    w("  PER COPPIA:")
    for r in scelte:
        s = v["per_coppia"][r["coppia"]]
        w("    %-10s n=%2d  exp=%+.3f%%  stop=%d  rotture=%d (%.0f%%)  usc_rel=%d  hl_verif=%s  %s"
          % (r["coppia"], s["n"], s["expectancy_netta"] * 100, s["stop"],
             s["rotture"], s["quota_rotture"] * 100, s["uscite_relazione"],
             ("%.1fg" % s["half_life_verifica"]) if s["half_life_verifica"] else "n/d",
             "ESCLUSA (rotture)" if s["esclusa"] else ""))
    w("")
    w("ESITO: %s" % v["esito"].upper())
    if v["motivi"]:
        for motivo in v["motivi"]:
            w("  - %s" % motivo)
    w("")
    w("Note: survivorship dichiarato (universo = perp listati oggi); funding misurato")
    w("solo dove l'archivio P8 esiste (dal 2026-06-29), altrove a funding zero per")
    w("costruzione dei dati; lo stop-di-relazione puo' scattare solo quando il")
    w("ricalcolo rolling ha abbastanza storia (>= %d osservazioni nella finestra)."
      % VALID_MIN_OBS)
    return "\n".join(righe)


def report_json(risultato: Optional[dict], screening: List[dict],
                scelte: List[dict], universo: Sequence[str]) -> str:
    payload = {
        "griglia_congelata": {
            "soglia_t_rho": SOGLIA_T_RHO, "half_life": [HL_MIN, HL_MAX],
            "W_griglia": list(W_GRIGLIA), "passo_finestre_giorni": PASSO_FINESTRE_GIORNI,
            "quota_viva_min": QUOTA_VIVA_MIN, "max_coppie": MAX_COPPIE,
            "z_ingresso": Z_IN, "z_uscita": Z_OUT, "z_stop": Z_STOP,
            "z_media_giorni": Z_MEDIA_GIORNI, "allocazione": ALLOCAZIONE,
            "ciclo_costo": CICLO_COSTO, "costo_stress": COSTO_STRESS,
            "soglia_rotture": SOGLIA_ROTTURA, "rotture_giorni": ROTTURA_GIORNI,
            "ddport_max": DDPORT_MAX, "margine_expect": MARGINE_EXPECT,
            "n_min": N_MIN, "valid_min_obs": VALID_MIN_OBS,
            "n_blocchi_criterio8": N_BLOCCHI_CRITERIO8,
            "addestramento_inizio_ms": ADDESTRAMENTO_INIZIO_MS,
            "addestramento_fine_ms": ADDESTRAMENTO_FINE_MS,
        },
        "universo": sorted(universo),
        "screening": screening,
        "scelte": scelte,
        "verifica": risultato,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, default=float)
