#!/usr/bin/env python3
"""Report mensile executive (FASE 1 roadmap) — testo + JSON per Telegram.

Contenuti (ROADMAP.md §3): capitale di chiusura (banco), rendita realizzata NETTA
(Earn+carry, fee detratte), costi, netto, incidenti, decisioni richieste.
Obiettivo di progetto: <=15 min/mese del proprietario, report che basta a sé stesso.

REGOLA D'ORO: dato mancante = riga "dati insufficienti". MAI numeri ipotizzati.
Solo lettura: nessun ordine, nessuna chiave, nessun write su ~/money.

Fonti (tutte artefatti con schema esistente, dichiarate nel JSON di output):
- banco a secco   logs/banco_secco.jsonl (MARCODG1): equity/saldi per comparto,
                  ogni 5', chiave read-only, riconciliazione con l'exchange.
- canary C1       /home/marco/canary/canary_state.json: funding cumulato, ts_open.
- carry multi     data/carry_stato.json (MARCODG1): uPL mark-to-market (non realizzato).
- fee             prove/C1_review_2026-10-15.json: fee osservate (spot-only).
- incidenti       ~/.denaro_alerts/sent.log: audit di ogni invio alert (schema
                  "YYYY-MM-DD HH:MM:SS | messaggio").
- decisioni       ROADMAP.md §7: voci "**D<N> ·" + risposte "**D<N>: SÌ/NO".
- scommessa       ops/dashboard/scommessa.json: valore e tetto della scommessa airdrop.
- costi fissi     file JSON opzionale (--costi-file) con schema dichiarato in LEGGIMI.

Metodo di attribuzione cambio-vs-resto: IDENTICO a ops/alerts/watch_alerts.py
(rate implicito USDC->EUR da savings con fallback funding; effetto cambio =
Dtasso x esposizione USD media (inizio+fine)/2; resto = delta - cambio). Il
capitale è in $: senza la scomposizione un movimento FX sembra una perdita.

La rendita calcolata dal banco è già NETTA delle fee per costruzione (l'equity
reale è post-fee): la voce "fee" quantifica dove esiste una fonte (review C1),
altrimenti dichiara "dati insufficienti".

Uso (dallo scratch):
  python report_mensile.py --mese 2026-10 \
      --banco-file data/banco_secco.jsonl \
      --canary-state-file data/canary_state.json \
      --carry-multi-file data/carry_stato.json \
      --fee-file data/C1_review_2026-10-15.json \
      --sent-log data/sent.log --roadmap data/ROADMAP.md \
      --scommessa-file data/scommessa.json \
      --json-out report_2026-10.json --testo-out report_2026-10.txt
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

INS = "dati insufficienti"
OK = "ok"


# ---------------------------------------------------------------------------
# 1. Lettura e parsing del banco a secco (stessa semantica di watch_alerts.py)
# ---------------------------------------------------------------------------

def _ts(d: dict) -> float | None:
    """Timestamp UNIX di una riga del banco (ISO 8601, Z o +00:00)."""
    try:
        s = str(d.get("timestamp", "")).replace("Z", "+00:00")
        return datetime.datetime.fromisoformat(s).timestamp()
    except Exception:  # noqa: BLE001
        return None


def parse_banco(testo: str) -> list[dict]:
    """Righe JSONL del banco con equity numerica e timestamp valido, ordinate per ts."""
    fuori = []
    for ln in (testo or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if isinstance(d.get("equity_eur"), (int, float)) and d.get("timestamp"):
            fuori.append(d)
    fuori.sort(key=lambda d: _ts(d) or 0.0)
    return fuori


def rate_implicito(d: dict) -> float | None:
    """Tasso implicito USDC->EUR (Simple Earn; fallback funding). Come watch_alerts,
    con soglia >1 USDC: i saldi dust (0.0076 USDC) producono rate folli e non validi."""
    try:
        sa = d.get("equity_savings_eur")
        us = (d.get("saldi_savings") or {}).get("USDC")
        if sa and us and float(us) > 1.0:
            return float(sa) / float(us)
        fu = d.get("equity_funding_eur")
        uf = (d.get("saldi_funding") or {}).get("USDC")
        if fu and uf and float(uf) > 1.0:
            return float(fu) / float(uf)
    except Exception:  # noqa: BLE001
        pass
    return None


def esposizione_usd(d: dict, rate: float) -> float | None:
    """Esposizione in dollari del totale: USDC (3 comparti) + cripto stimata in USD."""
    try:
        st = d.get("saldi_trading") or {}
        sf = d.get("saldi_funding") or {}
        ss = d.get("saldi_savings") or {}
        usdc = sum(float(x.get("USDC") or 0) for x in (st, sf, ss))
        cripto_eur = (float(d.get("equity_trading_eur") or 0)
                      - float(st.get("USDC") or 0) * rate
                      - float(st.get("EUR") or 0))
        return usdc + max(cripto_eur, 0.0) / rate
    except Exception:  # noqa: BLE001
        return None


def esposizione_usd_comparto(d: dict, comparto: str, rate: float) -> float | None:
    """Esposizione in dollari di un comparto (trading/funding/savings)."""
    try:
        saldi = d.get(f"saldi_{comparto}") or {}
        usdc = float(saldi.get("USDC") or 0)
        cripto_eur = (float(d.get(f"equity_{comparto}_eur") or 0)
                      - usdc * rate
                      - float(saldi.get("EUR") or 0))
        return usdc + max(cripto_eur, 0.0) / rate
    except Exception:  # noqa: BLE001
        return None


def _prima_dopo(rows: list[dict], ts_min: float) -> dict | None:
    return next((d for d in rows if (_ts(d) or 0.0) >= ts_min), None)


def _ultima_prima(rows: list[dict], ts_max: float) -> dict | None:
    presi = [d for d in rows if (_ts(d) or 0.0) <= ts_max]
    return presi[-1] if presi else None


def _iso_di(d: dict) -> str:
    return str(d.get("timestamp", ""))


# ---------------------------------------------------------------------------
# 2. Attribuzione cambio-vs-resto (mese) — formula del digest
# ---------------------------------------------------------------------------

def _periodo_righe(rows: list[dict], da_iso: str, a_iso: str) -> tuple[float, float, list[dict]]:
    """(t0, t1, righe nel periodo) — nessun dato sintetico."""
    t0 = datetime.datetime.fromisoformat(da_iso.replace("Z", "+00:00")).timestamp()
    t1 = datetime.datetime.fromisoformat(a_iso.replace("Z", "+00:00")).timestamp()
    return t0, t1, [d for d in rows if t0 <= (_ts(d) or 0.0) <= t1]


def ultimo_rate(rows: list[dict], t0: float, t1: float) -> float | None:
    """Ultimo tasso implicito valido nel periodo (per le conversioni in €)."""
    for d in reversed(rows):
        ts = _ts(d) or 0.0
        if t0 <= ts <= t1:
            r = rate_implicito(d)
            if r:
                return r
    return None


def _comparti_letti(d: dict) -> frozenset[str]:
    """Insieme dei comparti presenti nella riga (copertura del banco)."""
    return frozenset(c for c in ("trading", "funding", "savings")
                     if d.get(f"equity_{c}_eur") is not None)


def attribuzione(rows: list[dict], da_iso: str, a_iso: str) -> dict:
    """Variazione del totale sul periodo richiesto + scomposizione cambio-vs-resto.

    Il delta in € è calcolabile senza tasso (numeri puri). La scomposizione
    richiede: (1) tasso implicito USDC->EUR su almeno 2 campioni e (2) la stessa
    copertura di comparti a inizio e fine sotto-periodo — se il banco ha iniziato
    a leggere un comparto a metà periodo (es. savings dal 14/10, capitale in
    transito prima), la scomposizione si restringe al sotto-periodo coerente,
    dichiarato; altrimenti è "dati insufficienti" (mai numeri ipotizzati).
    """
    if len(rows) < 2:
        return {"stato": INS, "motivo": "meno di 2 campioni del banco nel periodo"}
    try:
        t0, t1, _ = _periodo_righe(rows, da_iso, a_iso)
    except Exception:  # noqa: BLE001
        return {"stato": INS, "motivo": "finestra temporale non interpretabile"}
    prima = _prima_dopo(rows, t0)
    ultima = _ultima_prima(rows, t1)
    if prima is None or ultima is None or prima is ultima:
        return {"stato": INS,
                "motivo": "nessun campione (o un solo campione) del banco nel periodo"}
    delta = float(ultima["equity_eur"]) - float(prima["equity_eur"])
    out = {"stato": OK, "delta_eur": delta,
           "delta_da": _iso_di(prima), "delta_a": _iso_di(ultima)}
    copertura = _comparti_letti(ultima)
    con_rate = [d for d in rows if t0 <= (_ts(d) or 0.0) <= t1
                and rate_implicito(d) and _comparti_letti(d) == copertura]
    if len(con_rate) < 2:
        out["scomposizione"] = {"stato": INS,
                                "motivo": ("tasso implicito USDC->EUR e/o copertura "
                                           "coerente dei comparti non disponibili su "
                                           "2 campioni del periodo (capitale in "
                                           "transito o banco senza USDC)")}
        return out
    p0, p1 = con_rate[0], con_rate[-1]
    r0, r1 = rate_implicito(p0), rate_implicito(p1)
    e0, e1 = esposizione_usd(p0, r0), esposizione_usd(p1, r1)
    if not e0 or not e1:
        out["scomposizione"] = {"stato": INS, "motivo": "esposizione USD non calcolabile"}
        return out
    cambio = (r1 - r0) * (e0 + e1) / 2.0
    sc = {"stato": OK, "da": _iso_di(p0), "a": _iso_di(p1),
          "cambio_eur": cambio,
          "resto_eur": (float(p1["equity_eur"]) - float(p0["equity_eur"])) - cambio,
          "rate_da": r0, "rate_a": r1}
    if p0 is not prima or p1 is not ultima:
        sc["nota"] = (f"sotto-periodo: scomposizione possibile solo da "
                      f"{_iso_di(p0)[:10]} (tasso implicito e copertura dei "
                      "comparti coerenti); NON spiega il delta dell'intero periodo")
    out["scomposizione"] = sc
    return out


def attribuzione_comparto(rows: list[dict], comparto: str, da_iso: str, a_iso: str) -> dict:
    """Attribuzione di un comparto sullo STESSO sotto-periodo della scomposizione."""
    base = attribuzione(rows, da_iso, a_iso)
    sc = base.get("scomposizione", {})
    if base.get("stato") != OK or sc.get("stato") != OK:
        return {"stato": INS, "motivo": sc.get("motivo", base.get("motivo", ""))}
    p0 = next((d for d in rows if _iso_di(d) == sc["da"]), None)
    p1 = next((d for d in rows if _iso_di(d) == sc["a"]), None)
    if p0 is None or p1 is None:
        return {"stato": INS, "motivo": "campioni del sotto-periodo non trovati"}
    if (p0.get(f"equity_{comparto}_eur") is None
            or p1.get(f"equity_{comparto}_eur") is None):
        return {"stato": INS,
                "motivo": f"comparto {comparto} non presente nel banco nel sotto-periodo"}
    r0, r1 = sc["rate_da"], sc["rate_a"]
    e0 = esposizione_usd_comparto(p0, comparto, r0)
    e1 = esposizione_usd_comparto(p1, comparto, r1)
    if e0 is None or e1 is None:
        return {"stato": INS, "motivo": f"esposizione USD del comparto {comparto} n/d"}
    delta = (float(p1[f"equity_{comparto}_eur"])
             - float(p0[f"equity_{comparto}_eur"]))
    cambio = (r1 - r0) * (e0 + e1) / 2.0
    out = {"stato": OK, "comparto": comparto, "delta_eur": delta,
           "cambio_eur": cambio, "resto_eur": delta - cambio,
           "da": sc["da"], "a": sc["a"]}
    # trasferimento interno? (stessa euristica di rendita_earn: segni USDC opposti)
    try:
        def _du(c: str) -> float:
            s0 = (p0.get(f"saldi_{c}") or {}).get("USDC")
            s1 = (p1.get(f"saldi_{c}") or {}).get("USDC")
            if s0 is None or s1 is None:
                return 0.0
            return float(s1) - float(s0)
        d_c = _du(comparto)
        d_altri = sum(_du(c) for c in ("trading", "funding", "savings") if c != comparto)
        if d_c and d_altri and d_c * d_altri < 0 and abs(d_altri) > abs(d_c) / 2:
            out["nota_trasferimento"] = (f"variazione USDC ({d_c:+.2f}) compensata dagli "
                                         f"altri comparti ({d_altri:+.2f}): trasferimento "
                                         "interno, non rendita del comparto")
    except Exception:  # noqa: BLE001
        pass
    return out


# ---------------------------------------------------------------------------
# 3. Rendita Earn (Simple Earn, USDC: misurabile senza effetto cambio)
# ---------------------------------------------------------------------------

def rendita_earn(rows: list[dict], da_iso: str, a_iso: str, rate_fine: float | None) -> dict:
    """Delta USDC del comparto savings nel periodo (interesse realizzato; fee Earn = 0).

    Il banco non registra i trasferimenti interni: se la variazione USDC dei
    savings ha segno opposto a quella di trading+funding (movimento compensato),
    è un trasferimento, non rendita: stato "dati insufficienti" con i numeri
    misurati nel motivo (mai interpretati come interesse).
    """
    try:
        t0 = datetime.datetime.fromisoformat(da_iso.replace("Z", "+00:00")).timestamp()
        t1 = datetime.datetime.fromisoformat(a_iso.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return {"stato": INS, "motivo": "finestra temporale non interpretabile"}
    con_savings = [d for d in rows if (d.get("saldi_savings") or {}).get("USDC")
                   and t0 <= (_ts(d) or 0.0) <= t1]
    if len(con_savings) < 2:
        return {"stato": INS,
                "motivo": "comparto savings non letto dal banco nel periodo "
                          "(saldi_savings assenti)"}
    prima, ultima = con_savings[0], con_savings[-1]
    delta_usdc = float(ultima["saldi_savings"]["USDC"]) - float(prima["saldi_savings"]["USDC"])

    def _delta_usdc(comparto: str) -> float | None:
        cc = [d for d in rows if (d.get(f"saldi_{comparto}") or {}).get("USDC")
              and t0 <= (_ts(d) or 0.0) <= t1]
        if len(cc) < 2:
            return None
        return float(cc[-1][f"saldi_{comparto}"]["USDC"]) - float(cc[0][f"saldi_{comparto}"]["USDC"])

    dt, df = _delta_usdc("trading"), _delta_usdc("funding")
    delta_altri = sum(x for x in (dt, df) if x is not None)
    if delta_usdc and delta_altri and delta_usdc * delta_altri < 0 \
            and abs(delta_altri) > abs(delta_usdc) / 2:
        return {"stato": INS,
                "motivo": (f"variazione USDC dei savings ({delta_usdc:+.4f}) compensata "
                           f"da trading+funding ({delta_altri:+.4f}): trasferimento "
                           "interno, la rendita da interesse non è separabile senza "
                           "il ledger dei movimenti")}
    out = {"stato": OK, "delta_usdc": delta_usdc, "da": _iso_di(prima), "a": _iso_di(ultima),
           "fee_eur": 0.0, "nota_fee": "Simple Earn: nessuna fee dichiarata da OKX"}
    if rate_fine:
        out["eur"] = delta_usdc * rate_fine
    else:
        out["eur"] = None
        out["stato_eur"] = INS
    return out


# ---------------------------------------------------------------------------
# 4. Carry: C1 (canary_state) e multi-coppia (carry_stato, uPL non realizzato)
# ---------------------------------------------------------------------------

def carry_c1_da_stato(stato: dict, da_iso: str, rate_fine: float | None) -> dict:
    """Funding cumulato C1. Se la posizione è stata aperta DOPO l'inizio del mese,
    last_funding è la rendita del periodo (apertura -> fine mese); se aperta PRIMA,
    la quota del mese non è ricavabile dallo stato (manca la serie): dati insufficienti."""
    try:
        ts_open = datetime.datetime.fromisoformat(
            str(stato.get("ts_open", "")).replace("Z", "+00:00")).timestamp()
        t0 = datetime.datetime.fromisoformat(da_iso.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        return {"stato": INS, "motivo": "canary_state senza ts_open valido"}
    last_funding = stato.get("last_funding")
    if not isinstance(last_funding, (int, float)):
        return {"stato": INS, "motivo": "canary_state senza last_funding"}
    if ts_open < t0:
        return {"stato": INS,
                "motivo": ("posizione aperta prima del mese e serie funding non "
                           "disponibile nello stato: quota del mese non ricavabile")}
    out = {"stato": OK, "funding_usdc": float(last_funding),
           "da": str(stato.get("ts_open")), "a": str(stato.get("last_check")),
           "inst": stato.get("inst"), "nota": "funding cumulato dall'apertura (nel mese)"}
    if rate_fine:
        out["eur"] = float(last_funding) * rate_fine
    else:
        out["eur"] = None
        out["stato_eur"] = INS
    return out


def carry_multi_da_stato(stato: dict) -> dict:
    """Carry multi-coppia: uPL mark-to-market (NON realizzato) + flag apertura."""
    try:
        aperte = [(nome, c) for nome, c in (stato.get("coppie") or {}).items()
                  if isinstance(c, dict) and c.get("aperta")]
        if not aperte and not stato.get("coppie"):
            return {"stato": INS, "motivo": "carry_stato assente o senza coppie"}
        out = {"stato": OK,
               "nozionale_totale_eur": stato.get("nozionale_totale_eur"),
               "upl_totale_eur": stato.get("upl_totale"),
               "coppie_aperte": len(aperte),
               "coppie": {n: {"nozionale_eur": c.get("nozionale_eur"),
                              "upl_eur": c.get("upl"),
                              "ts_apri": c.get("ts_apri")}
                          for n, c in aperte},
               "nota": "uPL mark-to-market, NON realizzato; "
                       "funding incassato: dati insufficienti (nessun artefatto)"}
        return out
    except Exception:  # noqa: BLE001
        return {"stato": INS, "motivo": "carry_stato non leggibile"}


# ---------------------------------------------------------------------------
# 5. Fee, costi, netto (aritmetica pura, testata)
# ---------------------------------------------------------------------------

def rendita_netta(lordo_eur: float, fee_eur: float) -> float:
    """Rendita al netto delle fee: lordo - fee (aritmetica di report)."""
    return lordo_eur - fee_eur


def netto_mensile(rendita_netta_eur: float, costi_mensili_eur: float) -> float:
    """Netto del mese: rendita netta - costi fissi (aritmetica di report)."""
    return rendita_netta_eur - costi_mensili_eur


def fee_da_review(review: dict) -> dict:
    """Fee osservate dalla review canary (schema prove/C1_review_*.json)."""
    try:
        f = review.get("fee") or {}
        obs = f.get("observed_total")
        if not isinstance(obs, (int, float)):
            return {"stato": INS, "motivo": "review senza fee.observed_total numerico"}
        return {"stato": OK, "osservate_eur": float(obs),
                "scope": str(f.get("observed_scope", "n/d")),
                "nota": str(f.get("criterion_pass", "n/d"))}
    except Exception:  # noqa: BLE001
        return {"stato": INS, "motivo": "review non leggibile"}


def costi_da_file(testo: str | None) -> dict:
    """Costi fissi mensili da file JSON (schema: {"voci":[{"voce","importo_eur_mese","fonte"}]})."""
    if not testo:
        return {"stato": INS,
                "motivo": ("nessun artefatto con costi reali verificati "
                           "(--costi-file assente); ROADMAP stima ~31 EUR/mese "
                           "DA CONFERMARE, non inclusa nel netto")}
    try:
        d = json.loads(testo)
        voci = d.get("voci")
        if not isinstance(voci, list) or not voci:
            return {"stato": INS, "motivo": "costi-file senza voci"}
        totale = 0.0
        ok_voci = []
        for v in voci:
            imp = v.get("importo_eur_mese")
            if not isinstance(imp, (int, float)):
                return {"stato": INS, "motivo": "voce costo senza importo numerico"}
            totale += float(imp)
            ok_voci.append({"voce": str(v.get("voce")), "importo_eur_mese": float(imp),
                            "fonte": str(v.get("fonte", "n/d"))})
        return {"stato": OK, "totale_eur_mese": totale, "voci": ok_voci}
    except Exception as e:  # noqa: BLE001
        return {"stato": INS, "motivo": f"costi-file illeggibile ({type(e).__name__})"}


# ---------------------------------------------------------------------------
# 6. Incidenti (audit alert) e decisioni (ROADMAP)
# ---------------------------------------------------------------------------

def incidenti_da_sentlog(righe: list[str], mese: str) -> dict:
    """Alert di allarme (⚠️) del mese dall'audit sent.log, raggruppati per categoria.

    Categoria = testo dell'alert con i numeri normalizzati (#), così una serie di
    anomalie dello stesso tipo non genera 100 righe identiche nel report.
    """
    conteggio = 0
    categorie: dict[str, int] = {}
    prefisso = f"{mese}-"
    for ln in righe or []:
        if not ln.startswith(prefisso):
            continue
        if "|" not in ln or "⚠️" not in ln:
            continue
        testo = ln.split("|", 1)[1].strip()
        while testo and (testo[0] in "⚠️✅🫀" or testo[0].isspace()):
            testo = testo[1:]
        categoria = re.sub(r"[-+]?\d[\d.,]*", "#", testo)
        conteggio += 1
        categorie[categoria] = categorie.get(categoria, 0) + 1
    if not righe:
        return {"stato": INS, "motivo": "audit alert (sent.log) assente"}
    return {"stato": OK, "conteggio": conteggio,
            "categorie": dict(sorted(categorie.items(), key=lambda kv: -kv[1])),
            "fonte": "~/.denaro_alerts/sent.log"}


def decisioni_da_roadmap(testo: str | None) -> dict:
    """Decisioni aperte da ROADMAP.md §7: voci "**D<N> ·" senza risposta "**D<N>: SÌ/NO"."""
    if not testo:
        return {"stato": INS, "motivo": "ROADMAP.md assente o illeggibile"}
    voci: dict[str, str] = {}
    for ln in testo.splitlines():
        m = re.match(r"^\s*(?:\d+\.\s*)?\*\*D(\d+)\s*·\s*([^*\n]+)\*\*", ln)
        if m:
            voci[m.group(1)] = m.group(2).strip()
    risposte: set[str] = set()
    for ln in testo.splitlines():
        m = re.match(r"^\s*[-*]\s*\*\*D(\d+):\s*(S[IÌ]|NO)\b", ln, re.IGNORECASE)
        if m:
            risposte.add(m.group(1))
    if not voci:
        return {"stato": INS, "motivo": "nessuna voce di decisione riconosciuta in ROADMAP.md"}
    aperte = [f"D{n} · {t}" for n, t in voci.items() if n not in risposte]
    return {"stato": OK, "aperte": aperte, "decise": len(risposte),
            "totale": len(voci), "fonte": "ROADMAP.md"}


def scommessa_da_json(testo: str | None) -> dict:
    """Scommessa asimmetrica (airdrop farming): valore corrente e tetto di perdita."""
    if not testo:
        return {"stato": INS, "motivo": "scommessa.json assente"}
    try:
        d = json.loads(testo)
        return {"stato": OK, "valore_eur": d.get("valore_eur"),
                "tetto_perdita_eur": d.get("tetto_perdita_eur"),
                "fase": d.get("fase"), "rete": d.get("rete")}
    except Exception as e:  # noqa: BLE001
        return {"stato": INS, "motivo": f"scommessa.json illeggibile ({type(e).__name__})"}


# ---------------------------------------------------------------------------
# 7. Composizione del report (testo + JSON)
# ---------------------------------------------------------------------------

def _f(x: float | None) -> str:
    return INS if x is None else f"{x:,.2f}"


def _finestra(mese: str, fino_iso: str | None) -> tuple[str, str]:
    """(da_iso, a_iso) del mese; --fino tronca la chiusura (mese in corso)."""
    da = f"{mese}-01T00:00:00Z"
    if fino_iso:
        return da, fino_iso
    anno, mm = int(mese[:4]), int(mese[5:7])
    ultimo = [31, 28 + (1 if (anno % 4 == 0 and anno % 100 != 0) or anno % 400 == 0 else 0),
              31, 30, 31, 30, 31, 31, 30, 31, 30, 31][mm - 1]
    return da, f"{mese}-{ultimo:02d}T23:59:59Z"


def genera_report(*, mese: str, banco_rows: list[dict], canary_stato: dict | None,
                  carry_stato: dict | None, review: dict | None,
                  sent_righe: list[str] | None, roadmap: str | None,
                  scommessa: str | None, costi: str | None,
                  fino_iso: str | None, comando: str, hash_artefatti: dict | None = None) -> dict:
    """Assembla il report completo. Nessun numero viene inventato: dove manca il
    dato la voce è {stato: 'dati insufficienti', motivo: ...}."""
    da_iso, a_iso = _finestra(mese, fino_iso)
    rep: dict = {
        "tipo": "report_mensile", "mese": mese,
        "generato_il": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "finestra_richiesta": {"da": da_iso, "a": a_iso},
        "comando": comando,
    }
    if hash_artefatti:
        rep["hash_artefatti"] = hash_artefatti

    # -- capitale (ultima lettura del banco nel periodo) --
    try:
        t1 = datetime.datetime.fromisoformat(a_iso.replace("Z", "+00:00")).timestamp()
    except Exception:  # noqa: BLE001
        t1 = None
    ultima = _ultima_prima(banco_rows, t1) if t1 is not None else None
    if ultima is None:
        rep["capitale"] = {"stato": INS, "motivo": "nessuna lettura del banco nel periodo"}
    else:
        rep["capitale"] = {
            "stato": OK, "ts": _iso_di(ultima), "esito": ultima.get("esito"),
            "chiusura_eur": float(ultima["equity_eur"]),
            "trading_eur": ultima.get("equity_trading_eur"),
            "funding_eur": ultima.get("equity_funding_eur"),
            "savings_eur": ultima.get("equity_savings_eur"),
            "ordini_aperti": ultima.get("ordini_aperti"),
            "riconciliazione_quadra": ultima.get("riconciliazione_quadra"),
            "chiave_solo_lettura": ultima.get("chiave_solo_lettura"),
        }

    # -- rendita totale scomposta cambio vs resto --
    attr = attribuzione(banco_rows, da_iso, a_iso)
    rep["rendita"] = {"totale": attr}
    try:
        t0f, t1f, _ = _periodo_righe(banco_rows, da_iso, a_iso)
        rate_fine = ultimo_rate(banco_rows, t0f, t1f)
    except Exception:  # noqa: BLE001
        rate_fine = None
    comparti = {}
    for c in ("trading", "funding", "savings"):
        comparti[c] = attribuzione_comparto(banco_rows, c, da_iso, a_iso)
    rep["rendita"]["comparti"] = comparti

    # -- Earn (USDC) --
    rep["rendita"]["earn"] = rendita_earn(banco_rows, da_iso, a_iso, rate_fine)

    # -- carry --
    rep["rendita"]["carry"] = {}
    rep["rendita"]["carry"]["c1"] = (carry_c1_da_stato(canary_stato, da_iso, rate_fine)
                                     if canary_stato else
                                     {"stato": INS, "motivo": "canary_state assente"})
    rep["rendita"]["carry"]["multi"] = (carry_multi_da_stato(carry_stato)
                                        if carry_stato else
                                        {"stato": INS, "motivo": "carry_stato assente"})

    # -- fee --
    rep["rendita"]["fee"] = (fee_da_review(review) if review else
                             {"stato": INS, "motivo": "review canary assente"})
    rep["rendita"]["nota_netto"] = ("la rendita dal banco è già netta delle fee "
                                    "(equity reale post-fee); la voce fee quantifica "
                                    "dove esiste una fonte")

    # -- costi e netto --
    rep["costi"] = costi_da_file(costi)
    sc = attr.get("scomposizione", {}) if attr.get("stato") == OK else {}
    if rep["costi"].get("stato") == OK and sc.get("stato") == OK:
        rep["netto"] = {"stato": OK,
                        "eur_mese": netto_mensile(sc["resto_eur"],
                                                  rep["costi"]["totale_eur_mese"]),
                        "rendita_netta_eur": sc["resto_eur"],
                        "costi_eur": rep["costi"]["totale_eur_mese"],
                        "periodo_rendita": {"da": sc["da"], "a": sc["a"]}}
    else:
        motivo_parti = []
        if sc.get("stato") != OK:
            motivo_parti.append(f"rendita: {sc.get('motivo', 'scomposizione non disponibile')}")
        if rep["costi"].get("stato") != OK:
            motivo_parti.append(f"costi: {rep['costi'].get('motivo', 'n/d')}")
        rep["netto"] = {"stato": INS, "motivo": "; ".join(motivo_parti) or INS}
        if sc.get("stato") == OK:
            rep["netto"]["rendita_netta_senza_costi_eur"] = sc["resto_eur"]

    # -- incidenti --
    rep["incidenti"] = incidenti_da_sentlog(sent_righe or [], mese)

    # -- decisioni --
    rep["decisioni"] = decisioni_da_roadmap(roadmap)

    # -- scommessa --
    rep["scommessa"] = scommessa_da_json(scommessa)

    return rep


def componi_testo(rep: dict) -> str:
    """Testo leggibile senza contesto (stile digest, ma mensile ed executive)."""
    mese = rep["mese"]
    righe = [f"📊 Denaro — report mensile {mese}",
             f"Generato il {rep['generato_il'][:19]}Z (comando in calce)"]
    fin = rep.get("finestra_richiesta", {})
    righe.append(f"Finestra richiesta: {fin.get('da')} → {fin.get('a')}")

    cap = rep.get("capitale", {})
    if cap.get("stato") == OK:
        righe.append("")
        righe.append(f"Capitale (ultima lettura {cap['ts']}): {_f(cap['chiusura_eur'])} €")
        righe.append(f"  trading {_f(cap.get('trading_eur'))} € · "
                     f"funding {_f(cap.get('funding_eur'))} € · "
                     f"Simple Earn {_f(cap.get('savings_eur'))} €")
        righe.append(f"  banco: esito {cap.get('esito', 'n/d')} · ordini aperti "
                     f"{cap.get('ordini_aperti', 'n/d')} · riconciliazione "
                     f"{cap.get('riconciliazione_quadra', 'n/d')}")
    else:
        righe.append(f"Capitale: {INS} — {cap.get('motivo', '')}")

    rend = rep.get("rendita", {})
    tot = rend.get("totale", {})
    righe.append("")
    if tot.get("stato") == OK:
        righe.append(f"Variazione totale ({tot['delta_da'][:16]}Z → {tot['delta_a'][:16]}Z): "
                     f"{tot['delta_eur']:+.2f} € (numeri in €, nessun tasso richiesto)")
        sc = tot.get("scomposizione", {})
        if sc.get("stato") == OK:
            righe.append(f"Scomposizione cambio-vs-resto ({sc['da'][:16]}Z → {sc['a'][:16]}Z):")
            righe.append(f"  cambio {sc['cambio_eur']:+.2f} € · resto (rendita operativa, "
                         f"già netta di fee) {sc['resto_eur']:+.2f} €")
            if sc.get("nota"):
                righe.append(f"  {sc['nota']}")
        else:
            righe.append(f"Scomposizione cambio-vs-resto: {INS} — {sc.get('motivo', '')}")
    else:
        righe.append(f"Variazione del periodo: {INS} — {tot.get('motivo', '')}")
        righe.append("  (nessun numero ipotizzato)")

    for c, etichetta in (("savings", "Simple Earn"), ("funding", "funding"), ("trading", "trading")):
        cc = rend.get("comparti", {}).get(c, {})
        if cc.get("stato") == OK:
            righe.append(f"  · {etichetta}: Δ {cc['delta_eur']:+.2f} € "
                         f"(cambio {cc['cambio_eur']:+.2f} · resto {cc['resto_eur']:+.2f})")
            if cc.get("nota_trasferimento"):
                righe.append(f"      ⚠ {cc['nota_trasferimento']}")
        else:
            righe.append(f"  · {etichetta}: {INS} ({cc.get('motivo', '')})")

    earn = rend.get("earn", {})
    righe.append("")
    if earn.get("stato") == OK:
        eur = earn.get("eur")
        righe.append(f"Rendita Earn (interesse USDC, fee 0): "
                     f"{earn['delta_usdc']:+.4f} USDC"
                     + (f" = {eur:+.2f} €" if eur is not None else
                        f" (valore in €: {INS})"))
        righe.append(f"  periodo {earn['da'][:16]}Z → {earn['a'][:16]}Z · "
                     "assunzione: nessun versamento/prelievo (il banco non registra "
                     "i trasferimenti)")
        if earn.get("nota_trasferimento"):
            righe.append(f"  ⚠ {earn['nota_trasferimento']}")
    else:
        righe.append(f"Rendita Earn: {INS} — {earn.get('motivo', '')}")

    carry = rend.get("carry", {})
    c1 = carry.get("c1", {})
    if c1.get("stato") == OK:
        eur = c1.get("eur")
        righe.append(f"Carry C1 ({c1.get('inst')}): funding cumulato "
                     f"{c1['funding_usdc']:+.4f} USDC"
                     + (f" = {eur:+.2f} €" if eur is not None else f" (€: {INS})"))
        righe.append(f"  dall'apertura {str(c1.get('da'))[:16]} → {str(c1.get('a'))[:16]}")
    else:
        righe.append(f"Carry C1: {INS} — {c1.get('motivo', '')}")
    multi = carry.get("multi", {})
    if multi.get("stato") == OK:
        righe.append(f"Carry multi ({multi.get('coppie_aperte')} coppie aperte): "
                     f"nozionale {_f(multi.get('nozionale_totale_eur'))} € · "
                     f"uPL {_f(multi.get('upl_totale_eur'))} €")
        righe.append(f"  {multi.get('nota', '')}")
    else:
        righe.append(f"Carry multi: {INS} — {multi.get('motivo', '')}")

    fee = rend.get("fee", {})
    if fee.get("stato") == OK:
        righe.append(f"Fee osservate (review canary): {fee['osservate_eur']:.2f} € "
                     f"[{fee.get('scope', 'n/d')}]")
    else:
        righe.append(f"Fee: {INS} — {fee.get('motivo', '')}")
    righe.append(rend.get("nota_netto", ""))

    righe.append("")
    costi = rep.get("costi", {})
    if costi.get("stato") == OK:
        righe.append(f"Costi fissi: {costi['totale_eur_mese']:.2f} €/mese")
        for v in costi.get("voci", []):
            righe.append(f"  · {v['voce']}: {v['importo_eur_mese']:.2f} € ({v['fonte']})")
    else:
        righe.append(f"Costi fissi: {INS} — {costi.get('motivo', '')}")

    netto = rep.get("netto", {})
    if netto.get("stato") == OK:
        righe.append(f"Netto del mese: {netto['eur_mese']:+.2f} € "
                     f"(rendita {netto['rendita_netta_eur']:+.2f} − costi "
                     f"{netto['costi_eur']:.2f})")
    else:
        righe.append(f"Netto del mese: {INS} — {netto.get('motivo', '')}")
        if netto.get("rendita_netta_senza_costi_eur") is not None:
            righe.append(f"  rendita operativa senza costi fissi: "
                         f"{netto['rendita_netta_senza_costi_eur']:+.2f} €")

    inc = rep.get("incidenti", {})
    righe.append("")
    if inc.get("stato") == OK:
        righe.append(f"Incidenti (alert ⚠️ inviati nel mese, audit {inc['fonte']}): "
                     f"{inc['conteggio']}")
        for cat, n in list((inc.get("categorie") or {}).items())[:8]:
            righe.append(f"  · ×{n}  {cat}")
        if len(inc.get("categorie") or {}) > 8:
            righe.append(f"  · … e altre {len(inc['categorie']) - 8} categorie (JSON completo)")
    else:
        righe.append(f"Incidenti: {INS} — {inc.get('motivo', '')}")

    dec = rep.get("decisioni", {})
    righe.append("")
    if dec.get("stato") == OK:
        righe.append(f"Decisioni richieste ({dec['fonte']}): "
                     f"{len(dec.get('aperte', []))} aperte su {dec.get('totale')} voci")
        for a in dec.get("aperte", []):
            righe.append(f"  · {a}")
        if not dec.get("aperte"):
            righe.append("  nessuna decisione aperta")
    else:
        righe.append(f"Decisioni richieste: {INS} — {dec.get('motivo', '')}")

    sc = rep.get("scommessa", {})
    if sc.get("stato") == OK:
        righe.append(f"Scommessa airdrop ({sc.get('rete', 'n/d')}): valore "
                     f"{_f(sc.get('valore_eur'))} € · tetto perdita "
                     f"{_f(sc.get('tetto_perdita_eur'))} €")
        righe.append(f"  fase: {sc.get('fase', 'n/d')}")
    else:
        righe.append(f"Scommessa airdrop: {INS} — {sc.get('motivo', '')}")

    righe.append("")
    righe.append(f"Regola: ogni riga \"{INS}\" è un dato assente nelle fonti, "
                 "mai un numero ipotizzato.")
    righe.append(f"Comando: {rep.get('comando', 'n/d')}")
    return "\n".join(righe)


# ---------------------------------------------------------------------------
# 8. I/O e CLI
# ---------------------------------------------------------------------------

def _leggi_file(path: str) -> str | None:
    p = Path(path).expanduser()
    return p.read_text(encoding="utf-8") if p.exists() else None


def _leggi_json(path: str | None) -> dict | None:
    if not path:
        return None
    try:
        return json.loads(_leggi_file(path) or "")
    except Exception:  # noqa: BLE001
        return None


def _ssh_leggi(target: str, tail: int = 0) -> str:
    """Legge un file remoto via ssh (BatchMode, nessuna chiave exchange coinvolta)."""
    host, _, path = target.partition(":")
    cmd = f"cat {path}" if not tail else f"tail -n {int(tail)} {path}"
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                        host, cmd], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"ssh {host} fallito ({r.returncode}): {r.stderr.strip()[:200]}")
    return r.stdout or ""


def _hash_bytes(nome: str, testo: str | None) -> dict[str, str] | None:
    if testo is None:
        return None
    return {nome: hashlib.sha256(testo.encode("utf-8")).hexdigest()}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Report mensile Denaro (FASE 1 roadmap).")
    ap.add_argument("--mese", default=None,
                    help="mese da reportare YYYY-MM (default: mese corrente)")
    ap.add_argument("--fino", default=None,
                    help="ISO finale della finestra (mese parziale), es. 2026-10-16T23:59:59Z")
    ap.add_argument("--banco-file", default=None, help="banco_secco.jsonl locale")
    ap.add_argument("--banco-ssh", default=None,
                    help="banco via ssh HOST:PATH (es. MARCODG1:/home/marco/money/logs/banco_secco.jsonl)")
    ap.add_argument("--banco-righe", type=int, default=20000,
                    help="righe da leggere via ssh (default 20000)")
    ap.add_argument("--canary-state-file", default=None, help="canary_state.json locale")
    ap.add_argument("--canary-state-ssh", default=None, help="canary_state via ssh HOST:PATH")
    ap.add_argument("--carry-multi-file", default=None, help="carry_stato.json locale")
    ap.add_argument("--carry-multi-ssh", default=None, help="carry_stato via ssh HOST:PATH")
    ap.add_argument("--fee-file", default=None, help="review canary JSON (fee osservate)")
    ap.add_argument("--sent-log", default=None, help="audit alert sent.log")
    ap.add_argument("--roadmap", default=None, help="ROADMAP.md")
    ap.add_argument("--scommessa-file", default=None, help="scommessa.json")
    ap.add_argument("--costi-file", default=None, help="JSON costi fissi (schema in LEGGIMI)")
    ap.add_argument("--json-out", default=None, help="scrivi JSON qui")
    ap.add_argument("--testo-out", default=None, help="scrivi il testo qui")
    ap.add_argument("--invia", action="store_true",
                    help="invia il testo su Telegram via tools/alert_lib (se disponibile)")
    args = ap.parse_args(argv)

    mese = args.mese or datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m")
    comando = "report_mensile.py " + " ".join(f'"{a}"' if " " in a else a for a in argv)

    hash_art: dict[str, str] = {}
    # -- banco --
    if args.banco_ssh:
        try:
            testo_banco = _ssh_leggi(args.banco_ssh, args.banco_righe)
        except RuntimeError as e:
            print(f"ERRORE: {e}", file=sys.stderr)
            return 1
    else:
        testo_banco = _leggi_file(args.banco_file) if args.banco_file else ""
    banco_rows = parse_banco(testo_banco)
    h = _hash_bytes("banco_secco.jsonl", testo_banco)
    if h:
        hash_art.update(h)

    # -- stato canary / carry / review (ssh o file) --
    def _carica(ssh_arg: str | None, file_arg: str | None, nome: str) -> tuple[dict | None, dict]:
        testo = None
        if ssh_arg:
            try:
                testo = _ssh_leggi(ssh_arg)
            except RuntimeError as e:
                print(f"AVVISO {nome}: ssh fallito ({e}) — trattato come assente", file=sys.stderr)
        elif file_arg:
            testo = _leggi_file(file_arg)
        d = None
        if testo:
            try:
                d = json.loads(testo)
            except Exception:  # noqa: BLE001
                print(f"AVVISO {nome}: JSON illeggibile — trattato come assente", file=sys.stderr)
        return d, (_hash_bytes(nome, testo) or {})

    canary_stato, h1 = _carica(args.canary_state_ssh, args.canary_state_file, "canary_state.json")
    hash_art.update(h1)
    carry_stato, h2 = _carica(args.carry_multi_ssh, args.carry_multi_file, "carry_stato.json")
    hash_art.update(h2)
    review, h3 = _carica(None, args.fee_file, "review_canary.json")
    hash_art.update(h3)

    testo_roadmap = _leggi_file(args.roadmap) if args.roadmap else None
    hash_art.update(_hash_bytes("ROADMAP.md", testo_roadmap) or {})
    testo_sent = _leggi_file(args.sent_log) if args.sent_log else ""
    sent_righe = (testo_sent or "").splitlines()
    hash_art.update(_hash_bytes("sent.log", testo_sent) or {})
    testo_scommessa = _leggi_file(args.scommessa_file) if args.scommessa_file else None
    hash_art.update(_hash_bytes("scommessa.json", testo_scommessa) or {})
    testo_costi = _leggi_file(args.costi_file) if args.costi_file else None
    hash_art.update(_hash_bytes("costi.json", testo_costi) or {})

    rep = genera_report(mese=mese, banco_rows=banco_rows, canary_stato=canary_stato,
                        carry_stato=carry_stato, review=review, sent_righe=sent_righe,
                        roadmap=testo_roadmap, scommessa=testo_scommessa, costi=testo_costi,
                        fino_iso=args.fino, comando=comando, hash_artefatti=hash_art)
    testo = componi_testo(rep)
    json_out = json.dumps(rep, indent=1, ensure_ascii=False)

    if args.testo_out:
        Path(args.testo_out).expanduser().write_text(testo + "\n", encoding="utf-8")
    else:
        print(testo)
    if args.json_out:
        Path(args.json_out).expanduser().write_text(json_out + "\n", encoding="utf-8")
    if args.invia:
        inviato = _invia_telegram(testo)
        print("invio Telegram:", "ok" if inviato else "non disponibile (tools/alert_lib assente)")
    return 0


def _invia_telegram(testo: str) -> bool:
    """Invio su Telegram via tools/alert_lib (stesso percorso di watch_alerts.py)."""
    candidati = []
    base = Path(__file__).resolve().parent
    candidati.append(base / "alerts")                # modulo in ops/ -> ops/alerts/
    candidati.append(base.parent / "ops" / "alerts") # fallback
    candidati.append(base.parent / "tools")          # modulo in ops/
    candidati.append(base / "tools")                 # modulo in root
    for c in candidati:
        if (c / "alert_lib.py").exists():
            sys.path.insert(0, str(c))
            try:
                from alert_lib import invia_o_spool  # noqa: PLC0415
                return bool(invia_o_spool(testo))
            except Exception:  # noqa: BLE001
                return False
    return False


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
