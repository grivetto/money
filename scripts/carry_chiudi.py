#!/usr/bin/env python3
"""carry_chiudi.py — chiusura delta-neutral di UNA coppia carry multi (P28).

PERCHE' ESISTE
==============
Il carry multi (`scripts/carry_multi.py` + `scripts/carry_apri.py`) sa APRIRE le
coppie ma non ha una via di CHIUSURA: la modalita' `close` esiste solo in C1
(`scripts/canary_carry.py`, hardcoded su DOGE). Questo modulo chiude il gap:
chiude UNA coppia qualsiasi di `COPPIE` (DOT, DOGE, LINK, ADA, LTC, AVAX) con la
stessa meccanica VALIDATA di C1, riusa il percorso di invio unico
(`money.esecuzione.invio.invia_gamba`) e la stessa convenzione di stato/eventi
di `carry_multi` (`data/carry_multi/`).

DIFFERENZE DICHIARATE rispetto a C1
===================================
1. Coppia parametrica (--coppia), non hardcoded.
2. Nessun gate di apertura e nessun check del kill switch: la chiusura e'
   RIDUZIONE DI RISCHIO (spec P28, come C1: il kill switch ordina di chiudere,
   non di restare scoperti).
3. Quantita' da chiudere = posizioni REALI lette dall'exchange e RILETTE prima
   di ogni ordine; i numeri dello stato non vengono mai usati per la taglia.
4. Riconciliazione finale con POLL ESTESO (lezione REQ-008: l'aggiornamento di
   posizione/saldi puo' avere latenza). Timeout -> FAIL_CHIUSURA con nota
   esplicita, nessuna azione correttiva automatica oltre il reprice previsto.

P34 (REQ-MERL-20261026-020):
  - verdetto di CHIUSURA ECONOMICA (P34-F2): con --netto-stimato (dalla
    riconciliazione su saldi reali) il piano stampa ok/soglia
    (fee_uscita+basis+margine, tariffe di money.costi + spread del book);
    --solo-economica rifiuta l'esecuzione sotto soglia (exit 2, zero ordini).
    Le chiusure di emergenza/kill switch restano INCONDIZIONATE.

MECCANICA (dichiarata)
======================
- Ordini LIMIT con reprice (pattern C1, coerente con la regola di progetto
  "mai market"): perp buy reduceOnly @ ask*1.002 (reprice ask*1.004) o
  sell reduceOnly @ bid*0.998 (reprice bid*0.996); spot sell @ bid*0.998
  (reprice bid*0.996).
- Sequenza PERP -> SPOT: se la perp non si chiude, lo spot NON viene venduto
  (mai una posizione nuda); se lo spot non si chiude dopo la perp: retry con
  reprice e poi errore esplicito (spot residuo = long, da sistemare a mano).
- Casi limite: perp assente + spot presente -> chiude solo lo spot (fallback
  C1); spot assente + perp presente -> chiude solo la perp con nota.
- Entrambe le gambe gia' a zero -> «gia' chiusa», no-op, exit 0 (idempotente).
- Guardie: qty = posizione reale riletta (mai > reale, mai segno invertito:
  reduceOnly e' il cap lato exchange); minimi di mercato controllati; coppia
  non nota -> rifiuto (exit 2).
- --qty (MD1-005): qty SPOT esplicita da vendere. Sovrascrive la qty_spot
  dello stato per la gamba spot (guardie F3/F5, vendita e riconciliazione
  incluse): serve quando il saldo reale non coincide con la coppia (es. DOT
  post-scaling: saldo 337,459 vs stato 77,922). Con --qty la vendita e'
  PARZIALE se il saldo eccede la qty richiesta (il residuo resta long).
  Senza --qty il rifiuto F5 resta (mai vendere saldi estranei di default).
- Kill switch: NON blocca la chiusura (vedi sopra).
- Scritture SOLO con --execute: stato `data/carry_multi/stato.json`
  (coppia -> status, ts_chiudi, esiti, fee) + riga in `eventi.jsonl`
  (convenzione carry_multi). Dry-run: zero ordini, zero scritture.

Uso:
  .venv/bin/python3 scripts/carry_chiudi.py --coppia DOT              # dry-run
  .venv/bin/python3 scripts/carry_chiudi.py --coppia DOT --motivo "..." [--execute]
  .venv/bin/python3 scripts/carry_chiudi.py --coppia DOT --qty 337.46  # dry-run, qty spot esplicita

Exit code: 0 = ok / gia' chiusa / dry-run; 1 = errore o FAIL_CHIUSURA;
2 = rifiuto (guardie, coppia ignota, --execute senza chiavi).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import ccxt

#: Stessi percorsi del carry multi (MARCODG1). Sui nodi senza /home/marco i
#: percorsi non esistono: lo script si rifiuta (mai dati inventati).
ROOT = Path("/home/marco/money")
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from money.esecuzione.invio import Gamba, invia_gamba  # noqa: E402
from money.chiusura_carry import (  # noqa: E402  (P34-F2)
    chiusura_economica, stima_costi_uscita)
from scripts.carry_multi import COPPIE, DIR_STATO, ENV_FILE, leggi_env, ora  # noqa: E402

STATO_FILE = "stato.json"
EVENTI_FILE = "eventi.jsonl"

#: Tolleranze di confronto (dichiarate): le qty sono float di monete/contratti.
EPS_CT = 1e-6        # contratti perp
EPS_QTY = 1e-8       # unita' di spot

#: F5 (P31): tolleranza relativa tra il saldo spot reale e la qty della coppia
#: (stato qty_spot). Entro la tolleranza si vende il saldo reale; oltre, e'
#: saldo estraneo alla coppia -> rifiuto (serve --qty esplicito).
TOLL_QTY_REL = 0.001   # 0,1%

#: Attesa fill ordine: C1 usa 60s con passo 1.5s -> 40 tentativi (iniezione
#: sleep_fn per i test: il budget e' in tentativi, non a muro).
POLL_FILL_TENTATIVI = 40
POLL_FILL_PASSO = 1.5
REPRICE_FILL_TENTATIVI = 30   # 45s come C1

#: Riconciliazione finale: poll esteso (lezione REQ-008, stesso budget di
#: earn_move: 60 x 2s = ~120s). Al timeout FAIL_CHIUSURA, zero azioni
#: correttive automatiche.
RECONCILIA_POLL_N = 60
RECONCILIA_INTERVAL_S = 2.0

#: Modalita' di margine della perp alla chiusura: quella usata in apertura
#: (carry_apri usa "isolated"); se lo stato porta `mgn_mode` si usa quello.
MGN_DEFAULT = "isolated"

#: Fee per la STIMA del piano — dai valori verificati di src/money/costi.py
#: (MAI da memoria): spot = okx_eea_con_perp, verificata 2026-10-06 sul conto
#: main (maker 0,080% / taker 0,100%); perp = okx_eea_swap_lv1, verificata
#: 2026-09-25 + fill del canary C1 (maker 0,020% / taker 0,050%).
FEE_SPOT = {"maker": 0.0008, "taker": 0.0010}
FEE_PERP = {"maker": 0.0002, "taker": 0.0005}

#: Reprice pattern C1: primo tentativo +0,2% (buy) / -0,2% (sell); reprice
#: +0,4% / -0,4%.
PRIMO_BUY = 1.002
REPRICE_BUY = 1.004
PRIMO_SELL = 0.998
REPRICE_SELL = 0.996


class CLIError(Exception):
    """Rifiuto di configurazione/guardia (exit 2)."""


class PosizioneIncoerente(Exception):
    """F1 (P31): info['pos'] e 'side' della posizione perp si contraddicono.
    Fermarsi senza ordini (exit 1): il lato non si deduce mai da una fonte
    ambigua."""


@dataclass
class Config:
    coppia: str
    motivo: str = ""
    execute: bool = False
    stato_dir: Path = DIR_STATO
    #: P34-F2: verdetto della chiusura economica. netto_stimato arriva dalla
    #: riconciliazione su saldi REALI (mai da uno stato); solo_economica
    #: rifiuta l'esecuzione sotto soglia (fee_uscita+basis+margine).
    netto_stimato: Optional[float] = None
    solo_economica: bool = False
    margine: float = 0.0
    #: MD1-005: qty SPOT esplicita (sovrascrive qty_spot dello stato per la
    #: gamba spot). None = comportamento storico (rifiuto F5 su saldi
    #: estranei alla coppia).
    qty_esplicita: Optional[float] = None


# ---------------------------------------------------------------------------
# Stato / eventi (convenzione carry_multi, ma con dir parametrico per i test)
# ---------------------------------------------------------------------------

def leggi_stato(dir_stato: Path) -> dict:
    """Legge stato.json; assente/corrotto -> {'coppie': {}} (come carry_multi)."""
    try:
        return json.loads((dir_stato / STATO_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"coppie": {}}


def scrivi_stato(dir_stato: Path, s: dict) -> None:
    dir_stato.mkdir(parents=True, exist_ok=True)
    s["aggiornato"] = ora()
    (dir_stato / STATO_FILE).write_text(json.dumps(s, indent=1))


def evento(dir_stato: Path, tipo: str, **kw) -> None:
    """Append-only su eventi.jsonl (stesso formato di carry_multi). SOLO in --execute."""
    dir_stato.mkdir(parents=True, exist_ok=True)
    riga = {"ts": ora(), "evento": tipo, **kw}
    with (dir_stato / EVENTI_FILE).open("a", encoding="utf-8") as f:
        f.write(json.dumps(riga) + "\n")


def cid_stabile(prefisso: str, intento: str) -> str:
    """clOrdId deterministico per intento (pattern carry_apri/C1): un retry
    riusa lo stesso id, l'exchange deduplica. MAI id legati all'orologio."""
    h = hashlib.sha1(f"{prefisso}|{intento}".encode()).hexdigest()[:20]
    return f"{prefisso}{h}"[:32]


def build_client(env_path: Path) -> Any:
    """Client OKX EEA (stessa configurazione di carry_multi.client)."""
    e = leggi_env(env_path)
    return ccxt.okx({"apiKey": e["OKX_API_KEY"], "secret": e["OKX_API_SECRET"],
                     "password": e["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                     "enableRateLimit": True, "options": {"defaultType": "spot"}})


# ---------------------------------------------------------------------------
# Letture dall'exchange (posizioni REALI: mai i numeri dello stato)
# ---------------------------------------------------------------------------

def lato_taglia_perp(p: dict) -> Tuple[float, float, str]:
    """F1 (P31): UNICO punto che decide lato e taglia della gamba perp, usato
    sia dal piano (stampa_piano) sia dall'invio (chiudi_perp).

    Forma REALE di ccxt: `contracts` e' POSITIVO (taglia), la direzione sta in
    `side` (short -> chiusura buy, long -> sell). Forma legacy (mock/test di
    P28): `contracts` firmato senza `side`.

    Ritorna (ct_firmato, qty_abs, side_di_chiusura)."""
    ct = float(p.get("contracts") or 0)
    qty = abs(ct)
    if qty <= EPS_CT:
        return 0.0, 0.0, ""
    side = (p.get("side") or "").lower()
    if side == "short":
        return -qty, qty, "buy"
    if side == "long":
        return qty, qty, "sell"
    return ct, qty, "sell" if ct > 0 else "buy"


def _coerenza_info_pos(p: dict, ct: float) -> None:
    """F1 (P31): info['pos'] e' SOLO un controllo di coerenza (mai fonte
    primaria). Se il segno contraddice `side` -> PosizioneIncoerente."""
    info = p.get("info")
    if not isinstance(info, dict):
        return
    raw = info.get("pos")
    if raw is None:
        return
    try:
        pos_info = float(str(raw).strip().replace(",", "."))
    except (TypeError, ValueError):
        return
    if abs(ct) > EPS_CT and abs(pos_info) > EPS_CT and (pos_info > 0) != (ct > 0):
        raise PosizioneIncoerente(
            f"posizione perp incoerente: contracts={p.get('contracts')} "
            f"side={p.get('side')} info.pos={raw}")


def leggi_perp_reale(ex, c, controlla: bool = True) -> Tuple[float, str]:
    """(ct con segno, side di chiusura) dalla posizione reale. Unico punto
    usato da piano e invio; qty_perp ne e' il wrapper di sola lettura.

    MD1-005: lettura MULTI-RIGA (lezione P34 di money_recon_carry): la stessa
    instId puo' avere piu' righe (mgnMode isolated + cross) e i contratti si
    SOMMANO con segno (DOT reale: -84 cross + -253 isolated = -337). La
    lettura a riga singola del P28 chiudeva solo UNA riga: pericoloso.
    Righe di segno misto -> PosizioneIncoerente (mai sommare al buio)."""
    tot = 0.0
    segni: set = set()
    for p in ex.fetch_positions([c.sym_perp]):
        ct, qty, side = lato_taglia_perp(p)
        if qty <= EPS_CT:
            continue
        if controlla:
            _coerenza_info_pos(p, ct)
        tot += ct
        segni.add("short" if ct < 0 else "long")
    if len(segni) > 1:
        raise PosizioneIncoerente(
            f"righe perp di segno misto su {c.sym_perp} ({sorted(segni)}): "
            "nessuna somma, verifica manuale.")
    if abs(tot) > EPS_CT:
        return tot, ("sell" if tot > 0 else "buy")
    return 0.0, ""


def righe_perp(ex, c) -> list:
    """Righe di posizione non vuote per l'instId (controlli multi-riga)."""
    out = []
    for p in ex.fetch_positions([c.sym_perp]):
        _ct, qty, _side = lato_taglia_perp(p)
        if qty > EPS_CT:
            out.append(p)
    return out


def qty_perp(ex, c) -> float:
    """Posizione perp CON SEGNO (0 se assente). Sola lettura (riconciliazione):
    taglia e lato dal punto unico lato_taglia_perp, senza check di coerenza."""
    ct, _ = leggi_perp_reale(ex, c, controlla=False)
    return ct


def saldo_spot(ex, c) -> Tuple[float, float]:
    """(free, total) della valuta spot della coppia."""
    b = ex.fetch_balance()
    free = float((b.get("free") or {}).get(c.nome, 0) or 0)
    total = float((b.get("total") or {}).get(c.nome, 0) or 0)
    return free, total


def qty_spot(ex, c) -> float:
    """Quantita' spot vendibile: free se disponibile, altrimenti total."""
    free, total = saldo_spot(ex, c)
    return free if free > EPS_QTY else total


def saldo_funding(ex, c) -> float:
    """F3 (P31): totale della valuta nei comparti funding e Simple Earn (se il
    client li espone): la gamba spot puo' essere li', non nel trading.
    0.0 se il comparto non e' esposto o la lettura fallisce."""
    tot = 0.0
    for tipo in ("funding", "earn"):
        try:
            b = ex.fetch_balance({"type": tipo})
            tot += float((b.get("total") or {}).get(c.nome, 0) or 0)
        except Exception:  # noqa: BLE001
            continue
    return tot


def leggi_posizioni_reali(ex, c) -> Tuple[float, float]:
    """(ct_perp con segno, qty_spot) letti dall'exchange."""
    return qty_perp(ex, c), qty_spot(ex, c)


def leggi_fee(oo: Optional[dict]) -> Optional[float]:
    """Fee dal fill (ccxt: order['fee']['cost']). None se assente: mai inventata."""
    if isinstance(oo, dict) and isinstance(oo.get("fee"), dict):
        try:
            return float(oo["fee"].get("cost") or 0)
        except (TypeError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------
# Attesa fill (budget in tentativi, sleep iniettato per i test)
# ---------------------------------------------------------------------------

def attesa_fill(ex, oid: str, sym: str, tentativi: int,
                sleep_fn=time.sleep) -> Tuple[Optional[dict], str]:
    """Poll fino a closed. Ritorna (ordine, esito) con esito in
    {closed, partial, reprice}: closed = chiuso, partial = annullato/fill
    parziale, reprice = timeout (si puo' cancellare e ritentare)."""
    for _ in range(tentativi):
        sleep_fn(POLL_FILL_PASSO)
        try:
            oo = ex.fetch_order(oid, sym)
        except Exception:
            continue
        st = oo.get("status")
        if st == "closed":
            return oo, "closed"
        if st == "canceled":
            return oo, "partial"
    try:
        return ex.fetch_order(oid, sym), "reprice"
    except Exception:
        return None, "reprice"


def _prezzo_limit(sym: str, px: float, side: str, primo: bool) -> float:
    if side == "buy":
        return round(px * (PRIMO_BUY if primo else REPRICE_BUY), 8)
    return round(px * (PRIMO_SELL if primo else REPRICE_SELL), 8)


def _esito_gamba() -> Dict[str, Any]:
    return {"esito": "assente", "filled": 0.0, "fee": None, "ordine": "",
            "pre_qty": 0.0}


def _annulla(ex, oid: str, sym: str) -> None:
    try:
        ex.cancel_order(oid, sym)
    except Exception:
        pass


def _cerca_ordine_vivo(ex, cid: str, sym: str) -> Optional[dict]:
    """F2 (P31): cerca un ordine per clOrdId dopo un'eccezione di invio.
    Ritorna l'ordine se ESISTE (vivo o riempito), None solo se provato
    assente. Un'eccezione su create_order NON prova "non inviato"."""
    try:
        oo = ex.fetch_order(cid, sym)
        if isinstance(oo, dict) and (oo.get("status") or "") in ("open", "closed"):
            return oo
    except Exception:  # noqa: BLE001
        pass
    try:
        for oo in ex.fetch_open_orders(sym):
            info = oo.get("info")
            cid_o = None
            if isinstance(info, dict):
                cid_o = info.get("clOrdId") or info.get("clientOrderId")
            if cid_o is None:
                cid_o = oo.get("clientOrderId")
            if cid_o == cid:
                return oo
    except Exception:  # noqa: BLE001
        pass
    return None


def chiudi_perp(ex, c, cfg: Config, mgn: str, voce: dict, sleep_fn, out) -> Dict[str, Any]:
    """Chiude la posizione perp: LIMIT reduceOnly, lato opposto al segno,
    +1 reprice (pattern C1). qty = posizione reale RILETTA qui; lato e taglia
    dal punto unico leggi_perp_reale (F1). Eccezione su create_order NON
    equivale a "non inviato" (F2). "Assente" mai con una sola lettura (F4).
    Fill cumulato primo+secondo ordine (F6)."""
    res = _esito_gamba()
    try:
        ct, side = leggi_perp_reale(ex, c)
    except PosizioneIncoerente as e:
        out(f"  STOP: {e}")
        res["esito"] = "incerto"
        return res
    if len(righe_perp(ex, c)) > 1:
        out("  STOP: posizione perp multi-riga: chiusura per-bucket non "
            "implementata — nessun ordine (verifica manuale).")
        res["esito"] = "incerto"
        return res
    if abs(ct) <= EPS_CT:
        # F4: seconda lettura concordante ~1s dopo; arbitro finale lo stato
        sleep_fn(1.0)
        try:
            ct2, _side2 = leggi_perp_reale(ex, c)
        except PosizioneIncoerente as e:
            out(f"  STOP: {e}")
            res["esito"] = "incerto"
            return res
        ct_stato = float(voce.get("ct_perp") or 0)
        if abs(ct2) > EPS_CT:
            out(f"  letture perp discordanti (0 poi {ct2:g} ct): nessun ordine, "
                "verifica manuale.")
            res["esito"] = "incerto"
            return res
        if abs(ct_stato) > EPS_CT:
            out(f"  perp assente in 2 letture ma stato ct_perp={ct_stato:g}: "
                "nessun ordine, verifica manuale.")
            res["esito"] = "incerto"
            return res
        return res
    res["pre_qty"] = ct
    qty = abs(ct)
    t = ex.fetch_ticker(c.sym_perp)
    px = ex.price_to_precision(c.sym_perp,
                               _prezzo_limit(c.sym_perp, float(t["ask"] if side == "buy" else t["bid"]),
                                             side, primo=True))
    cid = cid_stabile(f"{cfg.coppia.lower()}x",
                      f"close_perp|{c.sym_perp}|{qty}|{ora()[:10]}")
    try:
        o = invia_gamba(ex, Gamba(c.sym_perp, side, qty, float(px), cid,
                                  td_mode=mgn, reduce_only=True))
    except Exception as e:  # noqa: BLE001
        # F2: un'eccezione non prova "non inviato": cercare per clOrdId; se
        # l'ordine esiste, annullarlo, rileggere e fermarsi con "incerto".
        trovato = _cerca_ordine_vivo(ex, cid, c.sym_perp)
        if trovato is not None:
            _annulla(ex, trovato.get("id") or cid, c.sym_perp)
            try:
                ct_ri, _ = qty_perp(ex, c)
                ri = f"posizione residua {ct_ri:g} ct"
            except Exception:  # noqa: BLE001
                ri = "posizione residua ILLEGGIBILE"
            out(f"  invio perp INCERTO ({type(e).__name__}): ordine {cid} "
                f"trovato vivo e annullato; {ri} — VERIFICA MANUALE, nessuna "
                "altra gamba.")
            res.update({"esito": "incerto", "ordine": trovato.get("id", ""),
                        "cl_ord_id": cid})
            return res
        out(f"  invio perp FALLITO: {type(e).__name__}: {str(e)[:120]}")
        res["esito"] = "invio_fallito"
        return res
    filled_tot = 0.0
    fees = []
    oo, es = attesa_fill(ex, o["id"], c.sym_perp, POLL_FILL_TENTATIVI, sleep_fn)
    if es == "reprice":
        _annulla(ex, o["id"], c.sym_perp)
        # F6: il fill DEFINITIVO del primo ordine conta (riletto post-cancel)
        try:
            oo1 = ex.fetch_order(o["id"], c.sym_perp)
        except Exception:  # noqa: BLE001
            oo1 = None
        if isinstance(oo1, dict):
            filled_tot += float(oo1.get("filled") or 0)
            f1 = leggi_fee(oo1)
            if f1 is not None:
                fees.append(f1)
        try:
            ct2, side2 = leggi_perp_reale(ex, c)   # rilettura: mai > posizione reale
        except PosizioneIncoerente as e:
            out(f"  STOP: {e}")
            res.update({"esito": "incerto", "filled": filled_tot,
                        "fee": somma_fee(fees), "ordine": o["id"],
                        "cl_ord_id": cid})
            return res
        if abs(ct2) <= EPS_CT:
            es = "closed"                       # il primo tentativo ha chiuso tutto
            oo = oo1 if isinstance(oo1, dict) else oo
        else:
            qty2 = abs(ct2)
            t2 = ex.fetch_ticker(c.sym_perp)
            px2 = ex.price_to_precision(
                c.sym_perp,
                _prezzo_limit(c.sym_perp, float(t2["ask"] if side2 == "buy" else t2["bid"]),
                              side2, primo=False))
            cid2 = cid_stabile(f"{cfg.coppia.lower()}x",
                               f"close_perp|{c.sym_perp}|{qty}|{ora()[:10]}|reprice")
            try:
                o2 = invia_gamba(ex, Gamba(c.sym_perp, side2, qty2, float(px2), cid2,
                                           td_mode=mgn, reduce_only=True))
            except Exception as e:  # noqa: BLE001
                trovato = _cerca_ordine_vivo(ex, cid2, c.sym_perp)
                if trovato is not None:
                    _annulla(ex, trovato.get("id") or cid2, c.sym_perp)
                    out(f"  invio perp (reprice) INCERTO ({type(e).__name__}): "
                        f"ordine {cid2} trovato vivo e annullato — VERIFICA "
                        "MANUALE.")
                    res.update({"esito": "incerto", "filled": filled_tot,
                                "fee": somma_fee(fees),
                                "ordine": trovato.get("id", ""),
                                "cl_ord_id": cid2})
                    return res
                out(f"  invio perp (reprice) FALLITO: {type(e).__name__}: {str(e)[:120]}")
                res.update({"esito": "invio_fallito", "filled": filled_tot,
                            "fee": somma_fee(fees), "ordine": o["id"],
                            "cl_ord_id": cid2})
                return res
            oo, es = attesa_fill(ex, o2["id"], c.sym_perp,
                                 REPRICE_FILL_TENTATIVI, sleep_fn)
            if es != "closed":
                _annulla(ex, o2["id"], c.sym_perp)
    if isinstance(oo, dict):
        filled_tot += float(oo.get("filled") or 0)
        f2 = leggi_fee(oo)
        if f2 is not None:
            fees.append(f2)
    res.update({"esito": es,
                "filled": filled_tot,
                "fee": somma_fee(fees),
                "ordine": (oo or {}).get("id", ""),
                "cl_ord_id": cid})
    out(f"  esito perp: {es} filled={res['filled']}")
    return res


def chiudi_spot(ex, c, cfg: Config, voce: dict, sleep_fn, out) -> Dict[str, Any]:
    """Vende lo spot detenuto: LIMIT +1 reprice (pattern C1). Solo SELL: la
    gamba spot del carry e' long; mai un buy (mai invertire il segno).
    F5: la qty venduta e' al piu' la qty della coppia (stato qty_spot).
    F2/F6: come chiudi_perp (ordine vivo su eccezione, fill cumulato)."""
    res = _esito_gamba()
    qty_attesa = float(voce.get("qty_spot") or 0)
    if cfg.qty_esplicita is not None:
        qty_attesa = cfg.qty_esplicita
    q = qty_spot(ex, c)
    if qty_attesa > EPS_QTY:
        q = min(q, qty_attesa * (1 + TOLL_QTY_REL))
    if q <= EPS_QTY:
        return res
    res["pre_qty"] = q
    t = ex.fetch_ticker(c.sym_spot)
    px = ex.price_to_precision(c.sym_spot, _prezzo_limit(c.sym_spot, float(t["bid"]),
                                                         "sell", primo=True))
    cid = cid_stabile(f"{cfg.coppia.lower()}y",
                      f"close_spot|{c.sym_spot}|{q}|{ora()[:10]}")
    try:
        o = invia_gamba(ex, Gamba(c.sym_spot, "sell", q, float(px), cid))
    except Exception as e:  # noqa: BLE001
        trovato = _cerca_ordine_vivo(ex, cid, c.sym_spot)
        if trovato is not None:
            _annulla(ex, trovato.get("id") or cid, c.sym_spot)
            out(f"  invio spot INCERTO ({type(e).__name__}): ordine {cid} "
                "trovato vivo e annullato — VERIFICA MANUALE.")
            res.update({"esito": "incerto", "ordine": trovato.get("id", ""),
                        "cl_ord_id": cid})
            return res
        out(f"  invio spot FALLITO: {type(e).__name__}: {str(e)[:120]}")
        res["esito"] = "invio_fallito"
        return res
    filled_tot = 0.0
    fees = []
    oo, es = attesa_fill(ex, o["id"], c.sym_spot, POLL_FILL_TENTATIVI, sleep_fn)
    if es == "reprice":
        _annulla(ex, o["id"], c.sym_spot)
        # F6: il fill DEFINITIVO del primo ordine conta (riletto post-cancel)
        try:
            oo1 = ex.fetch_order(o["id"], c.sym_spot)
        except Exception:  # noqa: BLE001
            oo1 = None
        if isinstance(oo1, dict):
            filled_tot += float(oo1.get("filled") or 0)
            f1 = leggi_fee(oo1)
            if f1 is not None:
                fees.append(f1)
        q2 = qty_spot(ex, c)                    # rilettura: mai > posizione reale
        if qty_attesa > EPS_QTY:
            q2 = min(q2, qty_attesa * (1 + TOLL_QTY_REL))
        if q2 <= EPS_QTY:
            es = "closed"
            oo = oo1 if isinstance(oo1, dict) else oo
        else:
            t2 = ex.fetch_ticker(c.sym_spot)
            px2 = ex.price_to_precision(c.sym_spot,
                                        _prezzo_limit(c.sym_spot, float(t2["bid"]),
                                                      "sell", primo=False))
            cid2 = cid_stabile(f"{cfg.coppia.lower()}y",
                               f"close_spot|{c.sym_spot}|{q}|{ora()[:10]}|reprice")
            try:
                o2 = invia_gamba(ex, Gamba(c.sym_spot, "sell", q2, float(px2), cid2))
            except Exception as e:  # noqa: BLE001
                trovato = _cerca_ordine_vivo(ex, cid2, c.sym_spot)
                if trovato is not None:
                    _annulla(ex, trovato.get("id") or cid2, c.sym_spot)
                    out(f"  invio spot (reprice) INCERTO ({type(e).__name__}): "
                        f"ordine {cid2} trovato vivo e annullato — VERIFICA "
                        "MANUALE.")
                    res.update({"esito": "incerto", "filled": filled_tot,
                                "fee": somma_fee(fees),
                                "ordine": trovato.get("id", ""),
                                "cl_ord_id": cid2})
                    return res
                out(f"  invio spot (reprice) FALLITO: {type(e).__name__}: {str(e)[:120]}")
                res.update({"esito": "invio_fallito", "filled": filled_tot,
                            "fee": somma_fee(fees), "ordine": o["id"],
                            "cl_ord_id": cid2})
                return res
            oo, es = attesa_fill(ex, o2["id"], c.sym_spot,
                                 REPRICE_FILL_TENTATIVI, sleep_fn)
            if es != "closed":
                _annulla(ex, o2["id"], c.sym_spot)
    if isinstance(oo, dict):
        filled_tot += float(oo.get("filled") or 0)
        f2 = leggi_fee(oo)
        if f2 is not None:
            fees.append(f2)
    res.update({"esito": es,
                "filled": filled_tot,
                "fee": somma_fee(fees),
                "ordine": (oo or {}).get("id", ""),
                "cl_ord_id": cid})
    out(f"  esito spot: {es} filled={res['filled']}")
    return res


# ---------------------------------------------------------------------------
# Piano + riconciliazione
# ---------------------------------------------------------------------------

def stima_fee(c, ct: float, q_spot: float, px_p: float, px_s: float) -> Dict[str, float]:
    """Stima fee del ciclo di chiusura (maker/taker), mai numeri inventati:
    tassi dai valori verificati di costi.py (costanti in testa al modulo)."""
    noz_p = abs(ct) * c.ct_val * px_p
    noz_s = q_spot * px_s
    return {"taker": noz_p * FEE_PERP["taker"] + noz_s * FEE_SPOT["taker"],
            "maker": noz_p * FEE_PERP["maker"] + noz_s * FEE_SPOT["maker"]}


def stampa_piano(c, cfg: Config, ct: float, q_spot: float, t_p: dict, t_s: dict,
                 mgn: str, side_perp: str, out) -> None:
    out(f"=== CHIUDI {cfg.coppia} {'[EXECUTE]' if cfg.execute else '[DRY-RUN]'} ===")
    if cfg.motivo:
        out(f"motivo: {cfg.motivo}")
    out(f"posizioni reali (exchange): perp {ct:g} ct ({ct * c.ct_val:g} {c.nome})"
        f" | spot {q_spot:g} {c.nome}")
    if abs(ct) > EPS_CT:
        side = side_perp or ("sell" if ct > 0 else "buy")   # punto unico F1
        lim = _prezzo_limit(c.sym_perp, float(t_p["ask"] if side == "buy" else t_p["bid"]),
                            side, primo=True)
        noz = abs(ct) * c.ct_val * float(t_p["last"])
        out(f"gamba 1/2 perp: {side} {abs(ct):g} ct reduceOnly ({mgn})"
            f" @ limit ~{lim:.8g} (bid {t_p['bid']} / ask {t_p['ask']})"
            f" | nozionale ~{noz:.2f} USDC")
    else:
        out("gamba 1/2 perp: assente — nessun ordine perp")
    if q_spot > EPS_QTY:
        lim = _prezzo_limit(c.sym_spot, float(t_s["bid"]), "sell", primo=True)
        noz = q_spot * float(t_s["last"])
        out(f"gamba 2/2 spot: sell {q_spot:g} {c.nome}"
            f" @ limit ~{lim:.8g} (bid {t_s['bid']} / ask {t_s['ask']})"
            f" | nozionale ~{noz:.2f} USDC")
    else:
        out("gamba 2/2 spot: assente — nessun ordine spot")
    fee = stima_fee(c, ct, q_spot, float(t_p["last"]), float(t_s["last"]))
    out(f"stima fee: taker {fee['taker']:.4f} / maker {fee['maker']:.4f} USDC "
        f"(tassi verificati di costi.py, vedi LEGGIMI)")


def riconcilia(ex, c, qty_attesa_spot: float, sleep_fn) -> Tuple[bool, float, float, int]:
    """Poll esteso: perp == 0 E spot == qty attesa (lezione REQ-008)."""
    ct, q = 0.0, 0.0
    for n in range(1, RECONCILIA_POLL_N + 1):
        ct, q = leggi_posizioni_reali(ex, c)
        if abs(ct) <= EPS_CT and abs(q - qty_attesa_spot) <= EPS_QTY:
            return True, ct, q, n
        if n < RECONCILIA_POLL_N:
            sleep_fn(RECONCILIA_INTERVAL_S)
    ct, q = leggi_posizioni_reali(ex, c)
    return False, ct, q, RECONCILIA_POLL_N


def somma_fee(fees) -> Optional[float]:
    note = [f for f in fees if f is not None]
    return float(sum(note)) if note else None


def registra_esito(cfg: Config, esiti: Dict[str, str], status: str,
                   nota: Optional[str] = None, fee: Optional[float] = None) -> None:
    """Aggiorna stato.json della coppia (mantiene i campi dell'apertura)."""
    s = leggi_stato(cfg.stato_dir)
    vecchia = (s.get("coppie") or {}).get(cfg.coppia) or {}
    nuova = dict(vecchia)
    nuova.update({"status": status, "ts_chiudi": ora(), "esiti": esiti})
    if cfg.motivo:
        nuova["motivo_chiudi"] = cfg.motivo
    if nota is not None:
        nuova["nota_chiudi"] = nota
    nuova["fee"] = fee
    s.setdefault("coppie", {})[cfg.coppia] = nuova
    scrivi_stato(cfg.stato_dir, s)


# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------

def esegui(ex, cfg: Config, sleep_fn=time.sleep, out=print) -> int:
    """Core della chiusura. Exit: 0 ok / 1 errore o FAIL_CHIUSURA / 2 rifiuto."""
    c = COPPIE[cfg.coppia]          # il chiamante ha gia' validato la coppia
    ex.load_markets()

    # -- pre-check: stato (avvisi, MAI bloccanti: governano le posizioni reali) --
    s = leggi_stato(cfg.stato_dir)
    voce = (s.get("coppie") or {}).get(cfg.coppia)
    if not voce:
        out(f"ATTENZIONE: {cfg.coppia} assente in {STATO_FILE} — si procede "
            "sulle posizioni REALI.")
    elif voce.get("status") == "closed":
        out(f"ATTENZIONE: {cfg.coppia} risulta gia' 'closed' nello stato — si "
            "procede comunque sulle posizioni REALI (uno stato stantio non "
            "deve mai bloccare una riduzione di rischio).")
    voce = voce or {}

    # -- posizioni REALI + prezzi indicativi + minimi --
    qty_attesa = float(voce.get("qty_spot") or 0)      # F3/F5: qty della coppia
    if cfg.qty_esplicita is not None:
        out(f"NOTA --qty: qty spot esplicita {cfg.qty_esplicita:g} "
            f"(stato qty_spot={qty_attesa:g}) — gamba spot decisa su questa.")
        qty_attesa = cfg.qty_esplicita
    toll_qty = max(EPS_QTY, qty_attesa * TOLL_QTY_REL)
    try:
        ct, side_perp = leggi_perp_reale(ex, c)        # punto unico F1
    except PosizioneIncoerente as e:
        out(f"RIFIUTO: {e} — nessun ordine inviato.")
        return 1
    q_spot = qty_spot(ex, c)
    free_t, total_t = saldo_spot(ex, c)
    total_f = saldo_funding(ex, c)
    totale_reale = total_t + total_f
    t_p = ex.fetch_ticker(c.sym_perp)
    t_s = ex.fetch_ticker(c.sym_spot)
    mkt_p = ex.market(c.sym_perp)
    mkt_s = ex.market(c.sym_spot)
    min_p = float((mkt_p.get("limits") or {}).get("amount", {}).get("min") or 0)
    min_s = float((mkt_s.get("limits") or {}).get("amount", {}).get("min") or 0)
    mgn = voce.get("mgn_mode") or MGN_DEFAULT

    # -- F3: la gamba spot si decide con stato + trading + funding/earn --
    if qty_attesa > EPS_QTY:
        if totale_reale <= EPS_QTY:
            out(f"RIFIUTO: {cfg.coppia} qty_spot={qty_attesa:g} nello stato ma "
                "spot reale 0 in trading+funding/earn — verifica manuale, "
                "nessun ordine.")
            return 2
        if total_t <= EPS_QTY:
            out(f"RIFIUTO: spot della coppia ({qty_attesa:g}) non nel trading "
                f"ma in funding/earn ({totale_reale:g}) — serve earn_move "
                "redeem prima della chiusura, nessun ordine.")
            return 2
    # -- F5: la qty spot venduta e' quella della coppia, non l'intero saldo;
    # --qty esplicito (MD1-005) autorizza la vendita PARZIALE della sola
    # qty richiesta (il residuo resta long). --
    if qty_attesa > EPS_QTY and total_t > qty_attesa + toll_qty:
        if cfg.qty_esplicita is None:
            out(f"RIFIUTO: saldo spot {total_t:g} supera la qty della coppia "
                f"{qty_attesa:g} di {total_t - qty_attesa:g} — serve --qty "
                "esplicito, nessun ordine.")
            return 2
        out(f"NOTA --qty: saldo spot {total_t:g} > qty richiesta "
            f"{qty_attesa:g}: vendita PARZIALE della sola qty richiesta "
            f"(residuo {total_t - qty_attesa:g} resta long).")

    # -- idempotenza: entrambe le gambe gia' a zero --
    if abs(ct) <= EPS_CT and q_spot <= EPS_QTY:
        out(f"=== {cfg.coppia}: gia' chiusa (perp 0, spot 0). Nessuna azione. ===")
        return 0

    # -- guardie: minimi di mercato --
    if 0 < abs(ct) < min_p:
        out(f"RIFIUTO: posizione perp {ct:g} ct sotto il minimo di mercato "
            f"{min_p:g} — chiusura manuale necessaria.")
        return 2
    if 0 < q_spot < min_s:
        out(f"RIFIUTO: spot {q_spot:g} {c.nome} sotto il minimo di mercato "
            f"{min_s:g} — chiusura manuale necessaria.")
        return 2
    if total_t > EPS_QTY and free_t <= EPS_QTY:
        out(f"ATTENZIONE: spot {total_t:g} presente ma free=0 (vincolato?): "
            "il sell potrebbe fallire — verifica ordini aperti.")

    righe = righe_perp(ex, c)
    if len(righe) > 1:
        dett = "; ".join(
            f"{lato_taglia_perp(p)[0]:g} ct "
            f"(mgnMode={((p.get('info') or {}).get('mgnMode') or '?')})"
            for p in righe)
        out(f"posizione perp MULTI-RIGA ({len(righe)}): {dett} — "
            f"somma {ct:g} ct")
        if cfg.execute:
            out("RIFIUTO: chiusura per-bucket non implementata in "
                "carry_chiudi (una riga per mgnMode) — nessun ordine, "
                "verifica manuale o REQ dedicata.")
            return 2

    stampa_piano(c, cfg, ct, q_spot, t_p, t_s, mgn, side_perp, out)

    # -- P34-F2: verdetto della chiusura ECONOMICA. Il netto stimato NON si
    # calcola qui (la fonte e' la riconciliazione su saldi reali, P34-F3):
    # chi chiude per convenienza lo passa con --netto-stimato. Le chiusure di
    # emergenza/kill switch NON passano di qui (restano incondizionate). --
    if cfg.netto_stimato is not None:
        try:
            costi = stima_costi_uscita(
                noz_spot=q_spot * float(t_s["last"]),
                noz_perp=abs(ct) * c.ct_val * float(t_p["last"]),
                bid_spot=float(t_s["bid"]), ask_spot=float(t_s["ask"]),
                bid_perp=float(t_p["bid"]), ask_perp=float(t_p["ask"]))
        except ValueError as e:  # noqa: BLE001
            out(f"RIFIUTO: stima costi di uscita impossibile: {e}")
            return 2
        dec = chiusura_economica(cfg.netto_stimato, costi.fee_uscita,
                                 costi.basis_uscita, margine=cfg.margine)
        out(f"chiusura economica: ok={dec.ok} | netto stimato "
            f"{dec.netto_stimato:.4f} vs soglia {dec.soglia:.4f} USDC "
            f"(fee {costi.fee_uscita:.4f} + basis {costi.basis_uscita:.4f} "
            f"+ margine {cfg.margine:.4f})")
        out(f"  fonte costi: {costi.fonte}")
        if not dec.ok:
            out("  motivo: " + "; ".join(dec.motivi))
            if cfg.solo_economica:
                out("RIFIUTO (--solo-economica): nessun ordine inviato.")
                return 2
        elif cfg.solo_economica:
            out("  (--solo-economica: criterio soddisfatto, si procede)")
    elif cfg.solo_economica:
        out("RIFIUTO: --solo-economica richiede --netto-stimato "
            "(fail-closed). Nessun ordine inviato.")
        return 2

    if not cfg.execute:
        out("DRY-RUN: 0 ordini inviati, 0 scritture (stato/eventi intatti).")
        return 0

    # -- ESECUZIONE (SOLO --execute) --
    evento(cfg.stato_dir, "chiusura_iniziata", coppia=cfg.coppia,
           motivo=cfg.motivo, ct_perp=ct, qty_spot=q_spot)
    esiti: Dict[str, str] = {"perp": "assente", "spot": "assente"}

    # 1) perp (reduceOnly). Se non si chiude: lo spot NON si tocca.
    r_p = chiudi_perp(ex, c, cfg, mgn, voce, sleep_fn, out)
    esiti["perp"] = r_p["esito"]
    evento(cfg.stato_dir, "chiusura_perp", coppia=cfg.coppia,
           esito=r_p["esito"], filled=r_p["filled"], ordine=r_p["ordine"],
           cl_ord_id=r_p.get("cl_ord_id", ""))
    if r_p["esito"] == "assente":
        out("  gamba perp assente: si prosegue con lo spot (fallback C1).")
    elif r_p["esito"] != "closed":
        esiti["spot"] = "non_tentato"
        if r_p["esito"] == "incerto":
            nota = (f"gamba perp INCERTA (ordine {r_p.get('ordine') or '?'} "
                    f"clOrdId {r_p.get('cl_ord_id') or '?'}): trovata viva e "
                    "annullata dopo errore di invio; la gamba spot NON viene "
                    "venduta — verifica manuale.")
        else:
            nota = (f"gamba perp non chiusa ({r_p['esito']}): la gamba spot "
                    "NON viene venduta (nessuna posizione nuda); verifica "
                    "manuale.")
        registra_esito(cfg, esiti, "chiusura_fallita", nota=nota)
        evento(cfg.stato_dir, "chiusura_fallita", coppia=cfg.coppia,
               nota=nota, esiti=esiti)
        out(f"FALLIMENTO CHIUSURA: {nota}")
        return 1

    # 2) spot (solo dopo perp chiusa o assente)
    r_s = chiudi_spot(ex, c, cfg, voce, sleep_fn, out)
    esiti["spot"] = r_s["esito"]
    evento(cfg.stato_dir, "chiusura_spot", coppia=cfg.coppia,
           esito=r_s["esito"], filled=r_s["filled"], ordine=r_s["ordine"],
           cl_ord_id=r_s.get("cl_ord_id", ""))
    nota_spot = None
    if r_s["esito"] == "assente":
        if qty_attesa > EPS_QTY:
            # F3: lo stato dice che la gamba doveva esserci ma il trading e'
            # vuoto: MAI scrivere closed (la qty puo' essere in funding/earn)
            nota = (f"gamba spot assente ma qty attesa {qty_attesa:g} "
                    "> tolleranza: possibile funding/earn — verifica manuale.")
            registra_esito(cfg, esiti, "chiusura_fallita", nota=nota)
            evento(cfg.stato_dir, "chiusura_fallita", coppia=cfg.coppia,
                   nota=nota, esiti=esiti)
            out(f"FALLIMENTO CHIUSURA: {nota}")
            return 1
        nota_spot = f"gamba spot assente (qty attesa {qty_attesa:g})"
        out(f"  gamba spot assente: chiusa solo la perp (nota: {nota_spot}).")
    elif r_s["esito"] != "closed":
        if r_s["esito"] == "incerto":
            nota = (f"gamba spot INCERTA (ordine {r_s.get('ordine') or '?'} "
                    f"clOrdId {r_s.get('cl_ord_id') or '?'}): trovata viva e "
                    "annullata dopo errore di invio — verifica manuale.")
        else:
            residuo = r_s["pre_qty"] - r_s["filled"]
            nota = (f"gamba spot non chiusa ({r_s['esito']}): perp gia' "
                    f"chiusa, spot residuo {residuo:.8g} {c.nome} LONG — da "
                    "sistemare a mano.")
        registra_esito(cfg, esiti, "chiusura_fallita", nota=nota)
        evento(cfg.stato_dir, "chiusura_fallita", coppia=cfg.coppia,
               nota=nota, esiti=esiti)
        out(f"FALLIMENTO CHIUSURA: {nota}")
        return 1

    # 3) riconciliazione con poll esteso (lezione REQ-008)
    attesa_spot = r_s["pre_qty"] - r_s["filled"]
    ok, ct2, q2, letture = riconcilia(ex, c, attesa_spot, sleep_fn)
    fee = somma_fee([r_p["fee"], r_s["fee"]])
    if ok:
        registra_esito(cfg, esiti, "closed", nota=nota_spot, fee=fee)
        evento(cfg.stato_dir, "chiusura_completa", coppia=cfg.coppia,
               esiti=esiti, fee=fee, perp_residuo=ct2, spot_residuo=q2,
               letture_riconciliazione=letture)
        out(f"RICONCILIAZIONE OK: perp {ct2:g} ct, spot {q2:g} "
            f"(convergenza alla lettura {letture}). {cfg.coppia} CHIUSA.")
        return 0
    nota = (f"riconciliazione non convergente dopo ~"
            f"{RECONCILIA_POLL_N * RECONCILIA_INTERVAL_S:.0f}s "
            f"({RECONCILIA_POLL_N}x{RECONCILIA_INTERVAL_S:.0f}s): perp residuo "
            f"{ct2:g}, spot residuo {q2:g} (atteso {attesa_spot:g}) — possibile "
            "latenza di aggiornamento (lezione REQ-008): verifica manuale, "
            "nessuna azione correttiva automatica.")
    registra_esito(cfg, esiti, "chiusura_fallita", nota=nota, fee=fee)
    evento(cfg.stato_dir, "chiusura_fallita", coppia=cfg.coppia,
           nota=nota, esiti=esiti, perp_residuo=ct2, spot_residuo=q2)
    out(f"FAIL_CHIUSURA: {nota}")
    return 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="carry_chiudi.py",
        description="P28 — chiusura delta-neutral di UNA coppia carry multi "
                    "(OKX EEA): perp reduceOnly + spot sell. Dry-run di "
                    "default; --execute esegue (SOLO dopo preflight).",
    )
    p.add_argument("--coppia", required=True, help="coppia carry (es. DOT)")
    p.add_argument("--motivo", default="", help="motivo della chiusura "
                                                "(registrato negli eventi)")
    p.add_argument("--netto-stimato", type=float, default=None,
                   help="P34-F2: netto stimato in USDC dalla riconciliazione "
                        "su saldi reali (attiva il verdetto di chiusura "
                        "economica nel piano)")
    p.add_argument("--solo-economica", action="store_true",
                   help="P34-F2: esegue SOLO se il criterio economico e' "
                        "soddisfatto (netto >= fee_uscita+basis+margine); "
                        "sotto soglia rifiuta (exit 2, zero ordini)")
    p.add_argument("--margine", type=float, default=0.0,
                   help="P34-F2: margine USDC oltre fee+basis (default 0)")
    p.add_argument("--qty", type=float, default=None,
                   help="MD1-005: qty SPOT esplicita da vendere (sovrascrive "
                        "qty_spot dello stato per la gamba spot; il saldo "
                        "oltre la qty resta long)")
    p.add_argument("--env-file", default=None,
                   help="env-file con le chiavi OKX (default: quello del "
                        "carry multi su MARCODG1)")
    p.add_argument("--execute", action="store_true",
                   help="ESEGUE la chiusura. Default = dry-run.")
    return p


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    nome = args.coppia.strip().upper()
    if nome not in COPPIE:
        print(f"RIFIUTO: coppia ignota {nome!r}. Disponibili: {sorted(COPPIE)}",
              file=sys.stderr)
        return 2
    if args.qty is not None and args.qty <= 0:
        print(f"RIFIUTO: --qty deve essere > 0 (ricevuto {args.qty:g}).",
              file=sys.stderr)
        return 2
    cfg = Config(coppia=nome, motivo=(args.motivo or "").strip(),
                 execute=args.execute, qty_esplicita=args.qty)
    env_path = Path(args.env_file) if args.env_file else ENV_FILE
    if not env_path.exists():
        if args.execute:
            print(f"RIFIUTO: --execute richiede le chiavi: env-file mancante "
                  f"({env_path}).", file=sys.stderr)
            return 2
        print(f"env-file mancante ({env_path}): impossibile leggere le "
              "posizioni reali. Specificare --env-file.", file=sys.stderr)
        return 1
    try:
        ex = build_client(env_path)
    except Exception as e:  # noqa: BLE001
        print(f"ERRORE costruzione client (nessun segreto mostrato): "
              f"{type(e).__name__}", file=sys.stderr)
        return 1
    return esegui(ex, cfg)


if __name__ == "__main__":
    raise SystemExit(main())
