#!/usr/bin/env python3
"""tabellone.py — il libro contabile onesto del progetto Denaro.

Risponde a UNA domanda, con numeri e non con sensazioni: **stiamo guadagnando?**

    versato  = depositi - prelievi (netto, in EUR)
    equity   = valore attuale dei conti (aggregator, equity_source=balances)
    netto    = equity - versato            <-- LA risposta
    fee      = commissioni cumulate pagate all'exchange (da OKX bills)
    reale    = PnL realizzato (trade chiusi), al netto delle fee

In piu' (REQ-MERL-20261026-021):

    rendita netta = (funding carry + Earn stimato - fee del periodo) / giorni
        in EUR/giorno, rapportata all'equity (EUR/giorno per EUR impegnato).
        Fonti: recon.jsonl del carry (delta funding/fee tra ultima riga e
        riga ~N giorni prima) + saldo/tasso Simple Earn reali (OKX private,
        sola lettura). Numero + data di calcolo; n/d se una fonte manca.
    benchmark passivo = tasso Earn corrente letto dall'API OKX pubblica
        a ogni run (se il conto rende meno di cosi', il passivo batte l'attivo).

Fonti (tutte in SOLA LETTURA):
  - equity: aggregator  (default http://[::1]:8912/api/infra.json, campo total_equity)
  - bills / depositi / prelievi / Earn: OKX EEA main (chiave IP-bound -> gira su MARCODG1/nuvola)
  - funding/fee del carry: recon.jsonl (default /home/marco/hermes-scratch/carry_recon/recon.jsonl)

Uso:
    tabellone.py [--env /home/marco/denaro/secrets/main_okx.env]
                 [--equity-url http://[::1]:8912/api/infra.json]
                 [--recon-file /home/marco/hermes-scratch/carry_recon/recon.jsonl]
                 [--giorni 7]        # finestra della rendita
                 [--versato N]       # se noto, forza il versato e segnala lo scarto
                 [--json]

Nessun ordine, nessun movimento, nessun valore di chiave stampato.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

try:
    import ccxt
except ImportError:  # pragma: no cover
    raise SystemExit("serve ccxt nel venv (es. /home/marco/denaro/venv/bin/python)")

OKX_PUB = "https://eea.okx.com"
#: i bills con pnl != 0 sono trade; questi tipi hanno pnl valorizzato
TIPI_TRADE = {"3", "5"}
TIPI_FEE = {"3", "5", "8", "9", "13", "26"}
#: OKX public rifiuta l'User-Agent di default di urllib (403): serve un UA da browser
UA_BROWSER = "Mozilla/5.0"


def _get_json(url: str, timeout: int = 10) -> dict:
    """GET pubblico con UA da browser (urllib di default prende 403 su OKX)."""
    req = urllib.request.Request(url, headers={"User-Agent": UA_BROWSER})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())


def leggi_env(path: str) -> dict:
    d = {}
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("#") or "=" not in ln:
            continue
        k, v = ln.split("=", 1)
        d[k.strip()] = v.strip().strip('"').strip("'")
    return d


def prezzo_eur(ccy: str) -> float:
    """Prezzo indicativo di 1 unita' di `ccy` in EUR (spot pubblico)."""
    if ccy in ("EUR", ""):
        return 1.0
    if ccy == "USDC":
        ccy = "USDT"  # USDC ~ USDT per il libro contabile
    for inst in (f"{ccy}-EUR", f"{ccy}-USDT"):
        try:
            r = _get_json(f"{OKX_PUB}/api/v5/market/ticker?instId={inst}")
            px = float(r["data"][0]["last"])
            if inst.endswith("-USDT"):
                e = _get_json(f"{OKX_PUB}/api/v5/market/ticker?instId=USDT-EUR")
                px *= float(e["data"][0]["last"])
            return px
        except Exception:
            continue
    return 0.0


def equity_aggregator(url: str) -> dict:
    d = json.loads(urllib.request.urlopen(url, timeout=15).read())
    return {"equity": d.get("total_equity"), "source": d.get("equity_source"),
            "breakdown": d.get("equity_breakdown"), "ts": d.get("timestamp")}


def bills(ex, inst_type: str, tetto: int = 60) -> tuple[list[dict], bool]:
    """Ritorna (movimenti, completo). `completo=False` se una pagina ha dato errore:
    un elenco troncato NON deve sembrare un totale affidabile."""
    out, after = [], None
    for _ in range(tetto):
        p = {"instType": inst_type, "limit": 100}
        if after:
            p["after"] = after
        try:
            d = ex.privateGetAccountBillsArchive(p)["data"]
        except Exception:
            return out, False
        if not d:
            break
        out += d
        after = d[-1]["billId"]
        if len(d) < 100:
            break
        time.sleep(0.25)
    return out, True


def flussi_eur(ex) -> dict:
    """Depositi e prelievi netti in EUR (best effort: la history puo' essere limitata).
    Il versato affidabile resta quello dichiarato dal proprietario (`--versato`)."""
    tot = 0.0
    dettaglio = []
    completo = True
    for fonte, fn, segno in (("deposito", "privateGetAssetDepositHistory", 1),
                             ("prelievo", "privateGetAssetWithdrawalHistory", -1)):
        try:
            righe = getattr(ex, fn)({"limit": 100})["data"]
        except Exception:
            righe = []
            completo = False
        for r in righe:
            ccy = r.get("ccy") or "EUR"
            try:
                amt = float(r.get("amt") or 0)
            except (TypeError, ValueError):
                continue
            eur = amt * prezzo_eur(ccy) * segno
            tot += eur
            dettaglio.append({"tipo": fonte, "ccy": ccy, "amt": amt,
                              "eur": round(eur, 2), "ts": r.get("ts")})
    return {"netto_eur": round(tot, 2), "n": len(dettaglio),
            "dettaglio": dettaglio, "completo": completo}


# ---------------------------------------------------------------------------
# Riga rendita (REQ-MERL-20261026-021): funding carry + Earn stimato - fee
# ---------------------------------------------------------------------------

def leggi_jsonl(path: str) -> list[dict]:
    """Righe JSON valide di un file .jsonl; le righe corrotte vengono saltate."""
    out = []
    for ln in Path(path).read_text().splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out


def _ts_riga(r: dict):
    """Timestamp epoch della riga di recon (checked_ts, oppure checked_at ISO)."""
    ts = r.get("checked_ts")
    if ts is not None:
        try:
            return float(ts)
        except (TypeError, ValueError):
            pass
    iso = r.get("checked_at")
    if iso:
        try:
            return datetime.fromisoformat(str(iso).replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    return None


def _totale(r: dict, campo: str):
    t = r.get("totale") or {}
    try:
        v = t.get(campo)
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def finestra_recon(righe: list[dict], giorni: float = 7.0) -> dict:
    """Delta funding/fee tra l'ultima riga e la riga piu' vecchia entro ~`giorni`.

    I campi funding/fee delle righe sono CUMULATIVI (dall'apertura della coppia):
    il delta tra le righe di bordo e' il contributo della finestra. Fail-closed:
    serie corta, finestra < 1 giorno o valori assenti -> `motivo` valorizzato.
    """
    out = {"giorni": giorni, "n_righe": len(righe), "motivo": None}
    con_ts = sorted(((t, r) for t, r in ((_ts_riga(r), r) for r in righe) if t is not None),
                    key=lambda x: x[0])
    if len(con_ts) < 2:
        out["motivo"] = f"serie recon insufficiente ({len(con_ts)} riga/e con timestamp)"
        return out
    ultimo_ts, ultimo = con_ts[-1]
    soglia = ultimo_ts - giorni * 86400.0
    base_ts, base = con_ts[0]
    for ts, r in con_ts:
        if ts <= soglia:
            base_ts, base = ts, r
        else:
            break
    span_giorni = (ultimo_ts - base_ts) / 86400.0
    if span_giorni < 1.0:
        out["motivo"] = f"finestra reale {span_giorni:.1f} g < 1 giorno"
        return out
    f_u, f_b = _totale(ultimo, "funding_usdc"), _totale(base, "funding_usdc")
    fe_u, fe_b = _totale(ultimo, "fee_pagate_usdc"), _totale(base, "fee_pagate_usdc")
    if None in (f_u, f_b, fe_u, fe_b):
        out["motivo"] = "valori funding/fee assenti nelle righe di bordo"
        return out
    out.update({"giorni": round(span_giorni, 1),
                "funding_usdc": round(f_u - f_b, 6),
                "fee_usdc": round(fe_u - fe_b, 6),
                "data_base": base.get("date") or base.get("checked_at"),
                "data_fine": ultimo.get("date") or ultimo.get("checked_at")})
    return out


def parse_lending_rate(payload: dict) -> dict:
    """Estrae il tasso Earn corrente dal payload di /finance/savings/lending-rate-summary."""
    out = {"apy": None, "errore": None}
    try:
        if str(payload.get("code")) != "0" or not payload.get("data"):
            out["errore"] = f"API OKX: {payload.get('msg') or 'nessun dato'}"
            return out
        r = payload["data"][0]
        val = r.get("estRate") or r.get("avgRate")
        if val is None:
            out["errore"] = "tassi assenti nel payload"
            return out
        out["apy"] = float(val)
    except (KeyError, TypeError, ValueError, IndexError) as e:
        out["errore"] = f"payload malformato: {type(e).__name__}"
    return out


def tasso_earn_pubblico(ccy: str = "USDC") -> dict:
    """Benchmark passivo: tasso Earn corrente (API OKX pubblica, letto a ogni run)."""
    out = {"ccy": ccy, "apy": None, "ts": None, "errore": None}
    try:
        url = f"{OKX_PUB}/api/v5/finance/savings/lending-rate-summary?ccy={ccy}"
        parsed = parse_lending_rate(_get_json(url))
        out["apy"] = parsed["apy"]
        out["errore"] = parsed["errore"]
        out["ts"] = time.strftime("%Y-%m-%d %H:%M")
    except Exception as e:
        out["errore"] = f"{type(e).__name__}: {e}"
    return out


def earn_conto(ex) -> dict:
    """Saldo e tasso effettivi di Simple Earn (lettura privata, nessun ordine)."""
    out = {"saldo_usdc": None, "apy": None, "errore": None}
    try:
        d = ex.privateGetFinanceSavingsBalance()
        righe = d.get("data") or []
        migliore = None
        for r in righe:
            if r.get("ccy") != "USDC":
                continue
            try:
                amt = float(r.get("loanAmt") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            if migliore is None or amt > migliore[0]:
                try:
                    tasso = float(r.get("rate") or 0)
                except (TypeError, ValueError):
                    tasso = 0.0
                migliore = (amt, tasso)
        if migliore is None:
            out["errore"] = "nessuna riga USDC in financeSavingsBalance"
            return out
        out["saldo_usdc"] = round(migliore[0], 6)
        out["apy"] = migliore[1]
    except Exception as e:
        out["errore"] = f"{type(e).__name__}: {e}"
    return out


def earn_stimato_usdc(saldo_usdc: float, apy: float, giorni: float) -> float:
    """Earn stimato della finestra: saldo x tasso annuo x giorni / 365."""
    return saldo_usdc * apy * giorni / 365.0


def rendita_riga(funding_usdc: float, fee_usdc: float, earn_usdc: float,
                 giorni: float, usdc_eur: float, equity_eur: float) -> dict:
    """Rendita netta del periodo in EUR/giorno e in EUR/giorno per EUR impegnato.

    fee_usdc e' POSITIVO se pagato (segno del recon: fee_pagate_usdc).
    """
    netto_usdc = funding_usdc - fee_usdc + earn_usdc
    eur_giorno = netto_usdc / giorni * usdc_eur
    pct_giorno = eur_giorno / equity_eur * 100.0 if equity_eur > 0 else None
    return {"netto_usdc_periodo": round(netto_usdc, 6),
            "eur_giorno": round(eur_giorno, 4),
            "pct_giorno": round(pct_giorno, 6) if pct_giorno is not None else None}


def calcola_rendita(ex, recon_file: str, giorni: float, equity_eur, data_calcolo: str) -> dict:
    """Orchestratore della riga rendita. Fail-closed: `motivo` se una fonte manca."""
    out = {"giorni": giorni, "data_calcolo": data_calcolo, "motivo": None}
    try:
        equity_eur = float(equity_eur)
    except (TypeError, ValueError):
        equity_eur = None
    if equity_eur is None:
        out["motivo"] = "equity non disponibile (aggregator)"
        return out
    out["equity_eur"] = equity_eur
    try:
        finestra = finestra_recon(leggi_jsonl(recon_file), giorni)
    except OSError as e:
        out["motivo"] = f"recon non leggibile: {e}"
        return out
    out.update({"giorni": finestra.get("giorni", giorni),
                "n_righe": finestra.get("n_righe", 0),
                "funding_usdc": finestra.get("funding_usdc"),
                "fee_usdc": finestra.get("fee_usdc"),
                "data_base": finestra.get("data_base"),
                "data_fine": finestra.get("data_fine")})
    if finestra.get("motivo"):
        out["motivo"] = finestra["motivo"]
        return out
    conto = earn_conto(ex)
    saldo, apy = conto.get("saldo_usdc"), conto.get("apy")
    out["tasso_conto_apy"] = apy
    out["saldo_earn_usdc"] = saldo
    if conto.get("errore") or saldo is None or apy is None:
        # Earn assente: rendita calcolata SENZA Earn, dichiarato esplicitamente
        out["earn_stimato_usdc"] = 0.0
        out["nota_earn"] = (f"Earn conto non disponibile ({conto.get('errore') or 'dati mancanti'})"
                            ": assunto 0")
    else:
        out["earn_stimato_usdc"] = round(earn_stimato_usdc(saldo, apy, out["giorni"]), 6)
    try:
        usdc_eur = prezzo_eur("USDC")
    except Exception:
        usdc_eur = 0.0
    out["usdc_eur"] = usdc_eur
    if usdc_eur <= 0:
        out["motivo"] = "cambio USDC/EUR non disponibile"
        return out
    out.update(rendita_riga(out["funding_usdc"], out["fee_usdc"], out["earn_stimato_usdc"],
                            out["giorni"], usdc_eur, equity_eur))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--env", default="/home/marco/denaro/secrets/main_okx.env")
    ap.add_argument("--equity-url", default="http://[::1]:8912/api/infra.json")
    ap.add_argument("--recon-file", default="/home/marco/hermes-scratch/carry_recon/recon.jsonl")
    ap.add_argument("--giorni", type=float, default=7.0)
    ap.add_argument("--versato", type=float, default=None)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()

    esito: dict = {"data": time.strftime("%Y-%m-%d %H:%M"), "fonti": {}}

    # --- equity (aggregator) ---
    try:
        eq = equity_aggregator(a.equity_url)
        esito["equity_eur"] = eq["equity"]
        esito["fonti"]["equity"] = a.equity_url
    except Exception as e:
        eq = {"equity": None}
        esito["equity_eur"] = None
        esito["errore_equity"] = f"{type(e).__name__}: {e}"

    # --- OKX main: bills, flussi ---
    env = leggi_env(a.env)
    ex = ccxt.okx({"apiKey": env["OKX_API_KEY"], "secret": env["OKX_API_SECRET"],
                   "password": env["OKX_PASSPHRASE"], "hostname": "eea.okx.com",
                   "enableRateLimit": True, "options": {"defaultType": "spot"}})

    tutti = []
    ok_bills = True
    for it in ("SPOT", "SWAP"):
        b, completo = bills(ex, it)
        tutti += b
        ok_bills = ok_bills and completo
    reale = fee = 0.0
    for r in tutti:
        try:
            reale += float(r.get("pnl") or 0)
        except (TypeError, ValueError):
            pass
        try:
            fee += float(r.get("fee") or 0)   # OKX: negativo = pagata
        except (TypeError, ValueError):
            pass
    esito["pnl_realizzato_eur"] = round(reale, 2)
    esito["fee_cumulate_eur"] = round(fee, 2)
    esito["n_bills"] = len(tutti)

    fl = flussi_eur(ex)
    esito["versato_api_eur"] = fl["netto_eur"]
    esito["n_flussi"] = fl["n"]

    versato = a.versato if a.versato is not None else fl["netto_eur"]
    esito["versato_eur"] = versato
    _equity = eq.get("equity")
    if a.versato is not None:
        esito["scarto_versato_eur"] = round(a.versato - fl["netto_eur"], 2)
    elif _equity is not None and abs(versato) < max(1.0, 0.02 * abs(float(_equity))):
        # equity visibile ma flussi API ~0: quasi sempre history depositi limitata —
        # senza --versato il "netto" sarebbe finto (mai guadagni non riconciliati).
        esito["avviso_versato"] = ("flussi depositi/prelievi API ~0 mentre l'equity e' visibile: "
                                   "history limitata; passa --versato <EUR> per il netto vero")

    # --- riga rendita: funding carry + Earn stimato - fee del periodo (REQ-MERL-20261026-021) ---
    esito["rendita"] = calcola_rendita(ex, a.recon_file, a.giorni, _equity, esito["data"])
    esito["benchmark_earn"] = tasso_earn_pubblico()

    # --- fail-closed: il netto esiste SOLO se ogni fonte e' completa ------------------
    # Un totale "best effort" spacciato per verita' e' peggio di nessun totale.
    motivi = []
    if eq.get("equity") is None:
        motivi.append("equity non disponibile (aggregator)")
    if "avviso_versato" in esito:
        motivi.append("versato non affidabile (flussi API ~0; passa --versato)")
    if not ok_bills:
        motivi.append("bills troncati (pagina in errore)")
    if not fl["completo"]:
        motivi.append("flussi depositi/prelievi incompleti")
    esito["fonti"] = {
        "equity": "ok" if eq.get("equity") is not None else "error",
        "bills": "ok" if ok_bills else "partial",
        "flussi": "ok" if fl["completo"] else "partial",
    }
    if not motivi:
        esito["netto_vs_versato_eur"] = round(eq["equity"] - versato, 2)
        esito["stato"] = "RECONCILED"
    else:
        esito["stato"] = "INCOMPLETE"
        esito["motivi_incompletezza"] = motivi

    if a.json:
        print(json.dumps(esito, ensure_ascii=False, indent=2))
        return 0

    print(f"TABELLONE DENARO — {esito['data']}")
    print(f"  versato (netto)      : {versato:>10,.2f} EUR")
    print(f"  equity (aggregator)  : {(eq['equity'] or 0):>10,.2f} EUR   [{eq.get('source')}]")
    print(f"  fee cumulate (OKX)   : {fee:>10,.2f} EUR   ({len(tutti)} movimenti)")
    print(f"  PnL realizzato       : {reale:>10,.2f} EUR")
    if "netto_vs_versato_eur" in esito:
        n = esito["netto_vs_versato_eur"]
        print("  ------------------------------------------------")
        print(f"  NETTO vs VERSATO     : {n:>10,.2f} EUR   {'<-- guadagno' if n > 0 else '<-- perdita'}")
    elif "motivi_incompletezza" in esito:
        print(f"  netto vs versato     : n/d — {'; '.join(esito['motivi_incompletezza'])}")
    if "scarto_versato_eur" in esito:
        print(f"  (scarto versato dichiarato vs API: {esito['scarto_versato_eur']:+,.2f})")

    # --- riga rendita ---
    rend = esito.get("rendita", {})
    if rend.get("eur_giorno") is not None and rend.get("equity_eur"):
        g = rend["giorni"]
        per_eur = rend["eur_giorno"] / rend["equity_eur"]
        print(f"  rendita netta ({g:g}g)    : {rend['eur_giorno']:+,.4f} EUR/giorno"
              f"  su {rend['equity_eur']:,.2f} EUR = {per_eur:+.6f} EUR/giorno per EUR"
              f" ({rend['pct_giorno']:+.4f} %/giorno)  [calcolo {rend['data_calcolo']}]")
        if "nota_earn" in rend:
            print(f"      (funding {rend['funding_usdc']:+.2f} − fee {rend['fee_usdc']:.2f}"
                  f" + earn n/d · {rend['nota_earn']})")
        else:
            print(f"      (funding {rend['funding_usdc']:+.2f} − fee {rend['fee_usdc']:.2f}"
                  f" + earn stimato {rend['earn_stimato_usdc']:+.2f} USDC · tasso conto"
                  f" {rend['tasso_conto_apy'] * 100:.2f} %/anno su"
                  f" {rend['saldo_earn_usdc']:,.2f} USDC · USDC→EUR {rend['usdc_eur']:.4f})")
    elif rend.get("motivo"):
        print(f"  rendita netta          : n/d — {rend['motivo']}")

    bm = esito.get("benchmark_earn", {})
    if bm.get("apy") is not None:
        print(f"  benchmark passivo Earn : {bm['apy'] * 100:,.2f} %/anno"
              f" (OKX {bm.get('ccy', 'USDC')}, letto {bm.get('ts', 'n/d')})")
    else:
        print(f"  benchmark passivo Earn : n/d — {bm.get('errore', 'API OKX non disponibile')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
