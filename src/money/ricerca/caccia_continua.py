"""money.ricerca.caccia_continua — S4 «caccia continua»: ricerca incrementale di edge nuovi.

COSA E' (E COSA NON E')
=======================
Estensione a ciclo continuo del banco esplorativo (S1/S3). Ogni giro — cron, ogni 5
minuti — valuta un LOTTO di configurazioni **mai testate prima**, prese dal vicinato a
±1 passo (`PASSI_VICINI` di S3) delle configurazioni gia' viste (semi: S1+S3+S3ampio),
entro i `LIMITI` dichiarati qui sotto, PRIMA dei numeri. L'ordine e' BEST-FIRST
sull'ADDESTRAMENTO: si espande prima il vicinato dei genitori con la migliore expectancy
di addestramento; la verifica non entra MAI nell'ordinamento della ricerca.

CONTABILITA' (la parte che non si negozia)
==========================================
La correzione per selezione multipla (DSR, Bailey & Lopez de Prado) usa i tentativi
CUMULATIVI della caccia: ogni tentativo valutabile mai fatto qui (n_train >= 30) entra nel
conteggio e nella varianza, e i candidati sono RICONTROLLATI a ogni giro — se il conteggio
sale e il DSR scende sotto soglia, il candidato viene DECLASSATO (e lo si dice, mai in
silenzio). Le scansioni precedenti tengono i loro conteggi negli artefatti: la caccia ha
il PROPRIO registro cumulativo, dichiarato qui e non riusato.

Criterio candidato (identico alle scansioni): n(verifica) >= 30, exp > 0, t > 0, DSR >= 0.95.

REGOLA DI PROMOZIONE: NON promuove nulla — i sopravvissuti si pre-registrano come
esperimenti nuovi (P15+) e passano dal cancello. Stato runtime in `prove/caccia_continua/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

from ..statistica import sharpe_deflazionato
from . import scansione as S
from .scansione3 import vicini_config

VERSIONE_STATO = 1

#: Configurazioni per giro (default del runner; il lotto vero sta nello stato).
BATCH_DEFAULT = 96

#: Priorita' di ripiego per un genitore senza expectancy di addestramento valutabile.
PRIO_NULL = -1.0

#: Limiti DICHIARATI per famiglia/parametro (inclusivi). Un vicino fuori limite non entra.
#: `None` = parametro senza limiti numerici (i valori ammessi sono controllati a parte).
LIMITI: Dict[str, Dict[str, Optional[Tuple[float, float]]]] = {
    "sma_cross": {"fast": (2, 300), "slow": (3, 500)},
    "ema_cross": {"fast": (2, 300), "slow": (3, 500)},
    "macd": {"fast": (2, 80), "slow": (3, 160), "segnale": (2, 80)},
    "mom_abs": {"L": (2, 600)},
    "mom_trend": {"L": (2, 600), "sma": (10, 500)},
    "donchian": {"n_in": (2, 400), "n_out": (1, 300)},
    "reversion_z": {"n": (2, 300), "k": (0.25, 5.0)},
    "rsi2": {"periodo": (2, 12), "soglia_in": (1, 45), "soglia_out": (50, 99)},
    "turn_month": {"k": (1, 6), "pos": None},
}


def chiave(cfg: dict) -> str:
    """Etichetta stabile di una configurazione (stessa convenzione delle scansioni)."""
    return S.chiave_config(cfg)


def dentro_limiti(cfg: dict) -> bool:
    """La configurazione rispetta i limiti dichiarati? (chiavi ignote = fuori)."""
    limiti = LIMITI.get(str(cfg.get("famiglia", "")))
    if limiti is None:
        return False
    for nome, valore in cfg.items():
        if nome == "famiglia":
            continue
        bound = limiti.get(nome)
        if bound is None:
            if nome == "pos":
                if valore not in ("primi", "ultimi"):
                    return False
                continue
            return False
        minimo, massimo = bound
        try:
            if not (minimo <= float(valore) <= massimo):
                return False
        except (TypeError, ValueError):
            return False
    return True


def vicini_caccia(cfg: dict) -> List[dict]:
    """Vicini ±1 passo della configurazione, entro i limiti dichiarati, dedup per chiave."""
    visti: set = set()
    fuori: List[dict] = []
    for vicino in vicini_config(cfg):
        if not dentro_limiti(vicino):
            continue
        k = chiave(vicino)
        if k in visti:
            continue
        visti.add(k)
        fuori.append(vicino)
    return fuori


@dataclass
class Accumulo:
    """Somme sufficienti dei tentativi cumulativi: n, somma e somma dei quadrati.

    La varianza e' quella di popolazione, perche' la definizione del progetto
    (`varianza_da_tentativi`) e' quella di popolazione — qui si mantiene in forma
    incrementale, non si ricostruisce la lista.
    """

    n: int = 0
    somma: float = 0.0
    somma2: float = 0.0

    def aggiungi(self, sharpe: Optional[float]) -> None:
        if sharpe is None:
            return
        self.n += 1
        self.somma += float(sharpe)
        self.somma2 += float(sharpe) * float(sharpe)

    @property
    def varianza(self) -> float:
        if self.n < 2:
            return 0.0
        media = self.somma / self.n
        return max(self.somma2 / self.n - media * media, 0.0)

    def a_dict(self) -> dict:
        return {"n": self.n, "somma": self.somma, "somma2": self.somma2}

    @classmethod
    def da_dict(cls, d: Optional[dict]) -> "Accumulo":
        d = d or {}
        return cls(n=int(d.get("n") or 0), somma=float(d.get("somma") or 0.0),
                   somma2=float(d.get("somma2") or 0.0))


def aggiorna_accumulo(acc: Accumulo, records: Sequence[dict]) -> None:
    """Fonde nei conti cumulativi le somme per-configurazione dei record di un giro."""
    for rec in records:
        stat = rec.get("stat") or {}
        acc.n += int(stat.get("n") or 0)
        acc.somma += float(stat.get("somma") or 0.0)
        acc.somma2 += float(stat.get("somma2") or 0.0)


def semi_da_artefatti(documenti: Sequence[dict]) -> Tuple[Dict[str, dict], Dict[str, Optional[float]]]:
    """Dai documenti-artefatto delle scansioni a (semi, priorita').

    `semi`: chiave -> configurazione (famiglia + parametri). `priorita'`: chiave -> migliore
    expectancy di ADDESTRAMENTO tra i tentativi valutabili (None se nessuno). La verifica non
    viene letta: serve solo per l'ordinamento della frontiera.
    """
    semi: Dict[str, dict] = {}
    priori: Dict[str, Optional[float]] = {}
    for doc in documenti:
        trials = ((doc or {}).get("results") or {}).get("trials") or []
        for t in trials:
            k = str(t["chiave"])
            if k not in semi:
                semi[k] = {"famiglia": t["famiglia"], **(t.get("params") or {})}
            train = t.get("train") or {}
            if (train.get("n") or 0) >= S.MIN_OP and train.get("expectancy") is not None:
                e = float(train["expectancy"])
                if k not in priori or priori[k] is None or e > priori[k]:
                    priori[k] = e
    return semi, priori


def nuova_frontiera(coda: List[list], viste: set, cfg: dict, prio: Optional[float]) -> int:
    """Aggiunge alla coda i vicini ±1 passo non ancora visti; ritorna quanti ne ha aggiunti.

    Ogni voce della coda e' `[chiave, config, priorita']` (JSON-friendly).
    """
    p = PRIO_NULL if prio is None else float(prio)
    aggiunti = 0
    for vicino in vicini_caccia(cfg):
        k = chiave(vicino)
        if k in viste:
            continue
        viste.add(k)
        coda.append([k, vicino, p])
        aggiunti += 1
    return aggiunti


def estrai_batch(coda: List[list], n: int) -> List[list]:
    """Estrae (e rimuove) fino a `n` voci a priorita' piu' alta: best-first, pareggio per chiave."""
    if n <= 0:
        return []
    coda.sort(key=lambda voce: (-float(voce[2]), str(voce[0])))
    fuori = coda[:n]
    del coda[:n]
    return fuori


def record_da_trials(trials: Sequence[dict], *, min_op: int = S.MIN_OP) -> List[dict]:
    """Dai trial di un giro ai record per-configurazione (uno per chiave, ordine stabile).

    Ogni record: chiave, famiglia, parametri, le somme sufficienti dei tentativi valutabili
    (`stat`) e la selezione di addestramento (`sel`: miglior simbolo per expectancy tra i
    tentativi con n_train >= min_op; None se nessuno). La verifica entra solo dentro `sel`,
    per il ricontrollo dei candidati — mai per scegliere.
    """
    per_config: Dict[str, List[dict]] = {}
    for t in trials:
        per_config.setdefault(str(t["chiave"]), []).append(t)
    fuori: List[dict] = []
    for k in sorted(per_config):
        gruppo = per_config[k]
        acc = Accumulo()
        for t in gruppo:
            train = t.get("train") or {}
            if (train.get("n") or 0) >= min_op:
                acc.aggiungi(train.get("sharpe"))
        ammessi = [t for t in gruppo
                   if (t["train"].get("n") or 0) >= min_op
                   and t["train"].get("expectancy") is not None]
        sel = None
        if ammessi:
            scelta = max(ammessi, key=lambda t: t["train"]["expectancy"])
            campi = ("n", "expectancy", "sharpe", "t_stat")
            sel = {
                "simbolo": scelta["simbolo"],
                "train": {c: scelta["train"].get(c) for c in campi},
                "oos": {c: scelta["oos"].get(c) for c in campi},
            }
        fuori.append({
            "chiave": k,
            "famiglia": gruppo[0]["famiglia"],
            "params": gruppo[0].get("params") or {},
            "stat": acc.a_dict(),
            "sel": sel,
        })
    return fuori


def papabile(sel: Optional[dict], *, min_op: int = S.MIN_OP) -> bool:
    """Screening in verifica (identico alle scansioni): n >= soglia, exp > 0, t > 0."""
    if not sel:
        return False
    oos = sel.get("oos") or {}
    return ((oos.get("n") or 0) >= min_op
            and (oos.get("expectancy") or 0.0) > 0.0
            and (oos.get("t_stat") or 0.0) > 0.0)


def dsr_di(sel: dict, accumulo: Accumulo) -> Optional[float]:
    """DSR della selezione col conteggio cumulativo corrente; None se non calcolabile."""
    oos = sel.get("oos") or {}
    n_oos = int(oos.get("n") or 0)
    if n_oos < 2 or oos.get("sharpe") is None or accumulo.n < 2:
        return None
    return sharpe_deflazionato(float(oos["sharpe"]), n_oos, accumulo.n,
                               accumulo.varianza)["dsr"]


def valuta_candidati(papabili: Dict[str, dict], candidati: Dict[str, dict],
                     accumulo: Accumulo, *, soglia: float = S.SOGLIA_DSR) -> dict:
    """Transizioni di stato rispetto al conteggio cumulativo corrente.

    Ritorna `{"promossi": [(chiave, dsr)...], "ripromossi": [...], "declassati": [...]}`:
    - promosso: passava il DSR >= soglia e non era mai stato candidato;
    - ripromosso: era declassato e torna a passare;
    - declassato: era candidato "ok" e col conteggio salito non passa piu'.
    """
    promossi: List[tuple] = []
    ripromossi: List[tuple] = []
    declassati: List[tuple] = []
    for k in sorted(papabili):
        dsr = dsr_di(papabili[k], accumulo)
        passato = dsr is not None and dsr >= soglia
        stato = candidati.get(k)
        if passato and stato is None:
            promossi.append((k, dsr))
        elif passato and str(stato.get("stato")) != "ok":
            ripromossi.append((k, dsr))
        elif not passato and stato is not None and str(stato.get("stato")) == "ok":
            declassati.append((k, dsr))
    return {"promossi": promossi, "ripromossi": ripromossi, "declassati": declassati}


def stato_iniziale(semi: Dict[str, dict], priori: Dict[str, Optional[float]], *,
                   creazione: str, batch: int = BATCH_DEFAULT) -> dict:
    """Stato fresco: semi in `viste`, frontiera = vicini dei semi con la loro priorita'."""
    viste = set(semi)
    coda: List[list] = []
    for k in sorted(semi):
        nuova_frontiera(coda, viste, semi[k], priori.get(k))
    return {
        "versione": VERSIONE_STATO,
        "creato": creazione,
        "aggiornato": None,
        "ultimo_run": None,
        "run": 0,
        "fallimenti_consecutivi": 0,
        "esaurito": False,
        "batch": int(batch),
        "fine": None,
        "semi": len(semi),
        "accumulo": Accumulo().a_dict(),
        "coda": coda,
        "viste": sorted(viste),
        "papabili": {},
        "candidati": {},
        "ultimo_esito": None,
    }
