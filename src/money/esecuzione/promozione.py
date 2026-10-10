"""PromotionArtifact — la chiave che sblocca il capitale di validazione.

PERCHE' ESISTE
==============
L'esecutore (`money.esecuzione.esecutore`) pretende gia' un file di promozione per armare
il live (`MONEY_LIVE_ARMED=1` + `promozione_path`). Quella e' la serratura; qui c'e' la
chiave. Il capitale di validazione (~100 EUR) NON si sblocca "per provare l'infrastruttura":
si sblocca SOLO quando un'ipotesi ha superato il cancello, e la prova e' un artefatto
versionato, hashato e SCADIBILE.

GARANZIE (fail-closed, tutte verificabili)
==========================================
- l'artefatto e' immutabile: un hash copre TUTTO il contenuto (cambiare un byte lo invalida);
- ha una SCADENZA: dopo N giorni non arma piu' nulla (una promozione vecchia non vale);
- dichiara il capitale massimo autorizzato (mai "tutto quello che c'e'");
- dichiara il conteggio DSR con cui e' stato promosso (N cumulativo, non il solo ipotesi);
- un artefatto corrotto, scaduto o manomesso e' RIFIUTATO, non "quasi valido".

Nessuna funzione qui invia ordini: questo modulo scrive e LEGGE solo un file di prova.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

VERSIONE = 1
#: Durata di validita' di una promozione: oltre, si riverifica (una promozione vecchia
#: e' un'ipotesi che potrebbe non valere piu': fee cambiate, regime cambiato).
TTL_GIORNI_DEFAULT = 30


class PromozioneInvalida(RuntimeError):
    """L'artefatto non e' usabile per armare il capitale. Mai silenzioso."""


def _hash(dati: Dict[str, Any]) -> str:
    canonico = json.dumps(dati, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "promo" + hashlib.sha256(canonico.encode()).hexdigest()[:24]


@dataclass(frozen=True)
class PromotionArtifact:
    """La prova che un'ipotesi ha superato il cancello, col capitale che autorizza."""
    strategy_id: str
    nome: str
    creato: str            # ISO UTC
    scade: str             # ISO UTC
    capitale_max_eur: float
    #: conteggio dei tentativi usato per il DSR (l'ipotesi da sola, e il cumulativo reale)
    n_tentativi_ipotesi: int
    n_tentativi_cumulativi: int
    dsr: float
    verdetto: str          # PROMOSSA (unica ammessa)
    costi: Dict[str, Any] = field(default_factory=dict)
    metriche: Dict[str, Any] = field(default_factory=dict)
    commit: str = ""
    hash: str = ""

    def contenuto_hash(self) -> str:
        d = asdict(self)
        d.pop("hash", None)
        return _hash(d)

    def a_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def valida(self, *, adesso: Optional[datetime] = None) -> None:
        """Solleva `PromozioneInvalida` se l'artefatto non e' usabile. Fail-closed."""
        if self.verdetto != "PROMOSSA":
            raise PromozioneInvalida(f"verdetto {self.verdetto!r}: solo PROMOSSA sblocca capitale")
        if self.contenuto_hash() != self.hash:
            raise PromozioneInvalida("hash manomesso: il contenuto e' cambiato dopo la firma")
        if self.capitale_max_eur <= 0:
            raise PromozioneInvalida("capitale massimo non positivo: nessuna autorizzazione")
        if self.dsr < 0.95:
            raise PromozioneInvalida(f"DSR {self.dsr:.4f} < 0.95: non e' una promozione valida")
        # DSR calcolato sul conteggio CUMULATIVO (il solo conteggio dell'ipotesi mentirebbe)
        if self.n_tentativi_cumulativi < self.n_tentativi_ipotesi:
            raise PromozioneInvalida(
                "tentativi cumulativi < tentativi dell'ipotesi: contabilita' incoerente")
        ora = adesso or datetime.now(timezone.utc)
        try:
            scad = datetime.fromisoformat(self.scade)
        except ValueError:
            raise PromozioneInvalida(f"scadenza illeggibile: {self.scade!r}") from None
        if scad.tzinfo is None:
            scad = scad.replace(tzinfo=timezone.utc)
        if ora > scad:
            raise PromozioneInvalida(
                f"promozione scaduta il {self.scade}: riverificare prima di usarla")


def crea(*, strategy_id: str, nome: str, capitale_max_eur: float,
         n_tentativi_ipotesi: int, n_tentativi_cumulativi: int, dsr: float,
         costi: Optional[Dict[str, Any]] = None, metriche: Optional[Dict[str, Any]] = None,
         commit: str = "", ttl_giorni: int = TTL_GIORNI_DEFAULT) -> PromotionArtifact:
    """Costruisce e FIRMA un artefatto (solo se il verdetto e' PROMOSSA, e il DSR regge)."""
    if dsr < 0.95:
        raise PromozioneInvalida(f"rifiuto di firmare: DSR {dsr:.4f} < 0.95")
    if capitale_max_eur <= 0:
        raise PromozioneInvalida("rifiuto di firmare: capitale massimo non positivo")
    ora = datetime.now(timezone.utc)
    scad = ora + timedelta(days=int(ttl_giorni))
    grezzo = {
        "strategy_id": strategy_id, "nome": nome,
        "creato": ora.isoformat(timespec="seconds"), "scade": scad.isoformat(timespec="seconds"),
        "capitale_max_eur": float(capitale_max_eur),
        "n_tentativi_ipotesi": int(n_tentativi_ipotesi),
        "n_tentativi_cumulativi": int(n_tentativi_cumulativi),
        "dsr": float(dsr), "verdetto": "PROMOSSA",
        "costi": costi or {}, "metriche": metriche or {}, "commit": commit,
    }
    art = PromotionArtifact(**grezzo, hash=_hash(grezzo))
    art.valida()   # non si scrive un artefatto che non passerebbe la lettura
    return art


def scrivi(art: PromotionArtifact, cartella: str | Path) -> Path:
    d = Path(cartella)
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{art.creato[:10]}-{art.strategy_id}.json"
    p.write_text(json.dumps(art.a_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def leggi(path: str | Path) -> PromotionArtifact:
    """Legge e VERIFICA un artefatto. Un file corrotto/manomesso solleva, non ritorna 'quasi'."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    art = PromotionArtifact(**d)
    art.valida()
    return art
