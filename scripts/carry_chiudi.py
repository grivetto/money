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
- Kill switch: NON blocca la chiusura (vedi sopra).
- Scritture SOLO con --execute: stato `data/carry_multi/stato.json`
  (coppia -> status, ts_chiudi, esiti, fee) + riga in `eventi.jsonl`
  (convenzione carry_multi). Dry-run: zero ordini, zero scritture.

Uso:
  .venv/bin/python3 scripts/carry_chiudi.py --coppia DOT              # dry-run
  .venv/bin/python3 scripts/carry_chiudi.py --coppia DOT --motivo "..." [--execute]

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
from scripts.carry_multi import COPPIE, DIR_STATO, ENV_FILE, leggi_env, ora  # noqa: E402

STATO_FILE = "stato.json"
EVENTI_FILE = "eventi.jsonl"

#: Tolleranze di confronto (dichiarate): le qty sono float di monete/contratti.
EPS_CT = 1e-6        # contratti perp
EPS_QTY = 1e-8       # unita' di spot

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


@dataclass
class Config:
    coppia: str
    motivo: str = ""
    execute: bool = False
    stato_dir: Path = DIR_STATO


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

def qty_perp(ex, c) -> float:
    """Posizione perp CON SEGNO (0 se assente)."""
    for p in ex.fetch_positions([c.sym_perp]):
        if abs(float(p.get("contracts") or 0)) > 0:
            return float(p["contracts"])
    return 0.0


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


def chiudi_perp(ex, c, cfg: Config, mgn: str, sleep_fn, out) -> Dict[str, Any]:
    """Chiude la posizione perp: LIMIT reduceOnly, lato opposto al segno,
    +1 reprice (pattern C1). qty = posizione reale RILETTA qui."""
    res = _esito_gamba()
    ct = qty_perp(ex, c)
    if abs(ct) <= EPS_CT:
        return res
    res["pre_qty"] = ct
    side = "sell" if ct > 0 else "buy"          # opposto al segno: mai invertire
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
        out(f"  invio perp FALLITO: {type(e).__name__}: {str(e)[:120]}")
        res["esito"] = "invio_fallito"
        return res
    oo, es = attesa_fill(ex, o["id"], c.sym_perp, POLL_FILL_TENTATIVI, sleep_fn)
    if es == "reprice":
        _annulla(ex, o["id"], c.sym_perp)
        ct2 = qty_perp(ex, c)                   # rilettura: mai > posizione reale
        if abs(ct2) <= EPS_CT:
            es = "closed"                       # il primo tentativo ha chiuso tutto
        else:
            side2 = "sell" if ct2 > 0 else "buy"
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
                out(f"  invio perp (reprice) FALLITO: {type(e).__name__}: {str(e)[:120]}")
                res["esito"] = "invio_fallito"
                return res
            oo, es = attesa_fill(ex, o2["id"], c.sym_perp,
                                 REPRICE_FILL_TENTATIVI, sleep_fn)
            if es != "closed":
                _annulla(ex, o2["id"], c.sym_perp)
    res.update({"esito": es,
                "filled": float(oo.get("filled") or 0) if isinstance(oo, dict) else 0.0,
                "fee": leggi_fee(oo),
                "ordine": (oo or {}).get("id", "")})
    out(f"  esito perp: {es} filled={res['filled']}")
    return res


def chiudi_spot(ex, c, cfg: Config, sleep_fn, out) -> Dict[str, Any]:
    """Vende lo spot detenuto: LIMIT +1 reprice (pattern C1). Solo SELL: la
    gamba spot del carry e' long; mai un buy (mai invertire il segno)."""
    res = _esito_gamba()
    q = qty_spot(ex, c)
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
        out(f"  invio spot FALLITO: {type(e).__name__}: {str(e)[:120]}")
        res["esito"] = "invio_fallito"
        return res
    oo, es = attesa_fill(ex, o["id"], c.sym_spot, POLL_FILL_TENTATIVI, sleep_fn)
    if es == "reprice":
        _annulla(ex, o["id"], c.sym_spot)
        q2 = qty_spot(ex, c)                    # rilettura: mai > posizione reale
        if q2 <= EPS_QTY:
            es = "closed"
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
                out(f"  invio spot (reprice) FALLITO: {type(e).__name__}: {str(e)[:120]}")
                res["esito"] = "invio_fallito"
                return res
            oo, es = attesa_fill(ex, o2["id"], c.sym_spot,
                                 REPRICE_FILL_TENTATIVI, sleep_fn)
            if es != "closed":
                _annulla(ex, o2["id"], c.sym_spot)
    res.update({"esito": es,
                "filled": float(oo.get("filled") or 0) if isinstance(oo, dict) else 0.0,
                "fee": leggi_fee(oo),
                "ordine": (oo or {}).get("id", "")})
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
                 mgn: str, out) -> None:
    out(f"=== CHIUDI {cfg.coppia} {'[EXECUTE]' if cfg.execute else '[DRY-RUN]'} ===")
    if cfg.motivo:
        out(f"motivo: {cfg.motivo}")
    out(f"posizioni reali (exchange): perp {ct:g} ct ({ct * c.ct_val:g} {c.nome})"
        f" | spot {q_spot:g} {c.nome}")
    if abs(ct) > EPS_CT:
        side = "sell" if ct > 0 else "buy"
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
    ct, q_spot = leggi_posizioni_reali(ex, c)
    t_p = ex.fetch_ticker(c.sym_perp)
    t_s = ex.fetch_ticker(c.sym_spot)
    mkt_p = ex.market(c.sym_perp)
    mkt_s = ex.market(c.sym_spot)
    min_p = float((mkt_p.get("limits") or {}).get("amount", {}).get("min") or 0)
    min_s = float((mkt_s.get("limits") or {}).get("amount", {}).get("min") or 0)
    mgn = voce.get("mgn_mode") or MGN_DEFAULT

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
    free, total = saldo_spot(ex, c)
    if total > EPS_QTY and free <= EPS_QTY:
        out(f"ATTENZIONE: spot {total:g} presente ma free=0 (vincolato?): "
            "il sell potrebbe fallire — verifica ordini aperti.")

    stampa_piano(c, cfg, ct, q_spot, t_p, t_s, mgn, out)
    if not cfg.execute:
        out("DRY-RUN: 0 ordini inviati, 0 scritture (stato/eventi intatti).")
        return 0

    # -- ESECUZIONE (SOLO --execute) --
    evento(cfg.stato_dir, "chiusura_iniziata", coppia=cfg.coppia,
           motivo=cfg.motivo, ct_perp=ct, qty_spot=q_spot)
    esiti: Dict[str, str] = {"perp": "assente", "spot": "assente"}

    # 1) perp (reduceOnly). Se non si chiude: lo spot NON si tocca.
    r_p = chiudi_perp(ex, c, cfg, mgn, sleep_fn, out)
    esiti["perp"] = r_p["esito"]
    evento(cfg.stato_dir, "chiusura_perp", coppia=cfg.coppia,
           esito=r_p["esito"], filled=r_p["filled"], ordine=r_p["ordine"])
    if r_p["esito"] == "assente":
        out("  gamba perp assente: si prosegue con lo spot (fallback C1).")
    elif r_p["esito"] != "closed":
        esiti["spot"] = "non_tentato"
        nota = (f"gamba perp non chiusa ({r_p['esito']}): la gamba spot NON "
                "viene venduta (nessuna posizione nuda); verifica manuale.")
        registra_esito(cfg, esiti, "chiusura_fallita", nota=nota)
        evento(cfg.stato_dir, "chiusura_fallita", coppia=cfg.coppia,
               nota=nota, esiti=esiti)
        out(f"FALLIMENTO CHIUSURA: {nota}")
        return 1

    # 2) spot (solo dopo perp chiusa o assente)
    r_s = chiudi_spot(ex, c, cfg, sleep_fn, out)
    esiti["spot"] = r_s["esito"]
    evento(cfg.stato_dir, "chiusura_spot", coppia=cfg.coppia,
           esito=r_s["esito"], filled=r_s["filled"], ordine=r_s["ordine"])
    if r_s["esito"] == "assente":
        out("  gamba spot assente: chiusa solo la perp (nota).")
    elif r_s["esito"] != "closed":
        residuo = r_s["pre_qty"] - r_s["filled"]
        nota = (f"gamba spot non chiusa ({r_s['esito']}): perp gia' chiusa, "
                f"spot residuo {residuo:.8g} {c.nome} LONG — da sistemare a mano.")
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
        registra_esito(cfg, esiti, "closed", fee=fee)
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
    cfg = Config(coppia=nome, motivo=(args.motivo or "").strip(),
                 execute=args.execute)
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
