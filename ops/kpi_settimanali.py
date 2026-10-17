#!/usr/bin/env python3
"""KPI settimanali per il digest del lunedì (FASE 1 ROADMAP §3) — P25.

Sezione KPI del digest settimanale:
  1. Rendita netta 7g (€) scomposta cambio-vs-resto — STESSA metodologia di
     ops/alerts/watch_alerts.py::_attribuzione (banco a secco via ssh MARCODG1):
     il capitale è in $, un movimento FX non deve sembrare una perdita.
  2. Fee pagate 7g (€) da logs/fee_ledger.jsonl (collector scripts/raccogli_fee_ledger.py).
     Ledger mancante/vuoto => riga "fee: dati insufficienti", MAI numeri inventati.
     Fee in USDC/USD convertite col tasso EUR implicito del banco; fee in altra
     valuta escluse e contate a parte ("escluse N voci (valuta non convertibile)").
     Fee di conversione USDC-EUR a 0: incluse (sono 0).
  3. Distanza dal break-even: rendita netta mensilizzata (resto × 30/7) meno costi
     mensili; capitale attuale vs capitale-break-even stimato
     (costi ÷ rendita% realizzata), formula e limiti del campione corto dichiarati.

Costanti dichiarate: COSTI_MENSILI_TARGET_EUR = 16.0 (ROADMAP D1: AI ≤10 + VPS ≤6,
owner 17/10/2026), sovrascrivibile da prove/report_costi.json con campo
`totale_mese_eur`.

Solo lettura: nessun ordine, nessuna chiave exchange coinvolta, nessuna scrittura
su ~/money (l'eventuale --json-out scrive solo dove richiesto esplicitamente).
Il digest giornaliero resta invariato: questa sezione esiste solo con --settimanale
(il cron la usa il lunedì).

Uso:
  ops/kpi_settimanali.py --settimanale                     # dry-run: testo su stdout
  ops/kpi_settimanali.py --settimanale --invia             # + Telegram via alert_lib
  ops/kpi_settimanali.py --settimanale --json-out k.json  # artefatto JSON
  ops/kpi_settimanali.py --settimanale --banco-file b.jsonl --fee-file f.jsonl
    (modalità offline per test/smoke: zero rete)

Cron (mc2, lunedì 09:00):
  0 9 * * 1  cd /home/sergio/money && python3 ops/kpi_settimanali.py \
             --settimanale --invia >> logs/kpi_settimanali.log 2>&1
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path

INS = "dati insufficienti"
OK = "ok"

COSTI_MENSILI_TARGET_EUR = 16.0  # ROADMAP D1 (AI ≤10 + VPS ≤6), owner 17/10/2026
GIORNI_DEFAULT = 7
BANCO_SSH_DEFAULT = "MARCODG1:/home/marco/money/logs/banco_secco.jsonl"
FEE_SSH_DEFAULT = "MARCODG1:/home/marco/money/logs/fee_ledger.jsonl"
COSTI_FILE_DEFAULT = "/home/sergio/money/prove/report_costi.json"

FEE_CCY_EUR = {"EUR"}
FEE_CCY_USD = {"USDC", "USD"}

FORMULA_BREAKEVEN = ("mensilizzata = resto_7g × 30/7; distanza = mensilizzata − costi mensili; "
                     "capitale_break_even = costi_mensili ÷ (mensilizzata ÷ capitale attuale)")
LIMITI_BREAKEVEN = "limite: campione corto (7 giorni), la % realizzata è volatile, stima indicativa"


# ---------------------------------------------------------------------------
# 1. Banco a secco: parsing + metodologia di attribuzione (watch_alerts.py)
# ---------------------------------------------------------------------------

def _ts_di(d: dict) -> float:
    return datetime.datetime.fromisoformat(
        str(d["timestamp"]).replace("Z", "+00:00")).timestamp()


def _iso_di(d: dict) -> str:
    return str(d.get("timestamp", ""))


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
    fuori.sort(key=lambda d: _ts_di(d))
    return fuori


def rate_implicito(d: dict) -> float | None:
    """Tasso implicito USDC→EUR del campione (Simple Earn; fallback funding).

    Identico a watch_alerts._rate_of (nessuna soglia anti-dust: fedeltà alla
    metodologia citata dalla spec P25).
    """
    try:
        sa = d.get("equity_savings_eur")
        us = (d.get("saldi_savings") or {}).get("USDC")
        if sa and us:
            return float(sa) / float(us)
        fu = d.get("equity_funding_eur")
        uf = (d.get("saldi_funding") or {}).get("USDC")
        if fu and uf:
            return float(fu) / float(uf)
    except Exception:  # noqa: BLE001
        pass
    return None


def esposizione_usd(d: dict, rate: float) -> float | None:
    """Quanta parte del capitale è in dollari: USDC (3 comparti) + valore cripto."""
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


def attribuzione(rows: list[dict], secondi: float) -> dict | None:
    """(Δequity, effetto cambio, resto) sull'ultimo `secondi` della serie del banco.

    Stessa metodologia di watch_alerts._attribuzione: effetto cambio = Δtasso ×
    esposizione valutaria media (inizio+fine)/2; resto = delta − cambio. In più
    dichiara il periodo effettivo (da/a) usato per i numeri.
    """
    if len(rows) < 2:
        return None
    ultimo = rows[-1]
    t0 = _ts_di(ultimo) - secondi
    prima = next((d for d in rows if _ts_di(d) >= t0), None)
    if prima is None or prima is ultimo:
        return None
    r0, r1 = rate_implicito(prima), rate_implicito(ultimo)
    if not r0 or not r1:
        return None
    e0, e1 = esposizione_usd(prima, r0), esposizione_usd(ultimo, r1)
    if not e0 or not e1:
        return None
    delta = float(ultimo["equity_eur"]) - float(prima["equity_eur"])
    cambio = (r1 - r0) * (e0 + e1) / 2.0
    return {"delta_eur": delta, "cambio_eur": cambio, "resto_eur": delta - cambio,
            "da": _iso_di(prima), "a": _iso_di(ultimo),
            "ts_da": _ts_di(prima), "ts_a": _ts_di(ultimo),
            "rate_da": r0, "rate_a": r1}


# ---------------------------------------------------------------------------
# 2. Fee dal ledger (logs/fee_ledger.jsonl, schema P25)
# ---------------------------------------------------------------------------

def parse_ledger(testo: str) -> list[dict]:
    """Righe JSONL del ledger con billId e ts (epoca OKX in ms)."""
    fuori = []
    for ln in (testo or "").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
        except Exception:  # noqa: BLE001
            continue
        if d.get("billId") and d.get("ts") is not None:
            fuori.append(d)
    return fuori


def fee_da_ledger(righe: list[dict] | None, ts_da_s: float, ts_a_s: float,
                  rate: float | None) -> dict:
    """Somma delle fee 7g in €. Nessun numero inventato.

    - righe None          -> ledger assente: dati insufficienti.
    - fee in EUR          -> sommate direttamente.
    - fee in USDC/USD     -> × tasso implicito del banco; senza tasso: escluse e
                             contate come non convertibili. fee = 0: incluse (sono 0).
    - fee in altra valuta -> escluse e contate ("valuta non convertibile").
    - ts fuori finestra   -> contate a parte (fuori_periodo), non sommate.
    Somma dichiarata solo se sostenuta da almeno una voce inclusa (incluse >= 1).
    """
    if righe is None:
        return {"stato": INS,
                "motivo": "logs/fee_ledger.jsonl assente (collector mai girato o file "
                          "non leggibile)"}
    somma = 0.0
    incluse = 0
    escluse_ccy = 0
    fuori = 0
    scartate = 0
    da_ms, a_ms = float(ts_da_s) * 1000.0, float(ts_a_s) * 1000.0
    for r in righe:
        try:
            ts = float(r.get("ts"))
            fee = float(r.get("fee"))
            ccy = str(r.get("feeCcy") or "")
        except Exception:  # noqa: BLE001
            scartate += 1
            continue
        if ts < da_ms or ts > a_ms:
            fuori += 1
            continue
        if ccy in FEE_CCY_EUR:
            somma += fee
            incluse += 1
        elif ccy in FEE_CCY_USD:
            if fee == 0.0:
                somma += 0.0  # fee di conversione USDC-EUR a 0: inclusa (sono 0)
                incluse += 1
            elif rate:
                somma += fee * rate
                incluse += 1
            else:
                escluse_ccy += 1
        else:
            escluse_ccy += 1
    out = {"incluse": incluse, "escluse_ccy": escluse_ccy,
           "fuori_periodo": fuori, "scartate": scartate, "rate_usdc_eur": rate}
    if incluse >= 1:
        out["stato"] = OK
        out["somma_eur"] = somma
    else:
        out["stato"] = INS
        parti = []
        if escluse_ccy:
            parti.append(f"{escluse_ccy} voce/i escluse (valuta non convertibile)")
        if fuori:
            parti.append(f"{fuori} voce/i fuori finestra")
        if scartate:
            parti.append(f"{scartate} voce/i malformate scartate")
        if not parti:
            parti.append("ledger vuoto (nessuna voce)")
        out["motivo"] = "nessuna voce di fee convertibile nel periodo: " + "; ".join(parti)
    return out


# ---------------------------------------------------------------------------
# 3. Costi mensili e break-even (aritmetica pura, testata)
# ---------------------------------------------------------------------------

def costi_mensili(testo_report_costi: str | None) -> dict:
    """Costi mensili: default COSTI_MENSILI_TARGET_EUR (ROADMAP D1), sovrascrivibile
    da prove/report_costi.json con campo `totale_mese_eur`. La fonte è dichiarata."""
    out = {"valore_eur_mese": COSTI_MENSILI_TARGET_EUR,
           "fonte": (f"ROADMAP D1 (default, AI ≤10 + VPS ≤6): "
                     f"{COSTI_MENSILI_TARGET_EUR:.2f} €/mese")}
    if testo_report_costi:
        try:
            d = json.loads(testo_report_costi)
        except Exception:  # noqa: BLE001
            out["nota"] = "prove/report_costi.json illeggibile: uso il default ROADMAP"
            return out
        v = d.get("totale_mese_eur") if isinstance(d, dict) else None
        if isinstance(v, (int, float)):
            out = {"valore_eur_mese": float(v),
                   "fonte": f"prove/report_costi.json (totale_mese_eur={float(v):.2f})"}
        else:
            out["nota"] = ("prove/report_costi.json senza campo totale_mese_eur "
                           "numerico: uso il default ROADMAP")
    return out


def break_even(resto_7g_eur: float, capitale_eur: float,
               costi_eur_mese: float) -> dict:
    """Distanza dal break-even (mensilizzazione 30/7). Formula e limiti dichiarati."""
    mensilizzata = resto_7g_eur * 30.0 / 7.0
    out = {"mensilizzata_eur_mese": mensilizzata,
           "costi_eur_mese": costi_eur_mese,
           "distanza_eur_mese": mensilizzata - costi_eur_mese,
           "capitale_attuale_eur": capitale_eur,
           "formula": FORMULA_BREAKEVEN,
           "limiti": LIMITI_BREAKEVEN}
    if capitale_eur and capitale_eur > 0 and mensilizzata > 0:
        out["stato"] = OK
        out["capitale_break_even_eur"] = costi_eur_mese * capitale_eur / mensilizzata
    else:
        out["stato"] = INS
        out["capitale_break_even_eur"] = None
        out["motivo"] = ("rendita mensilizzata ≤ 0 o capitale non disponibile: "
                         "il capitale di break-even non è calcolabile "
                         "(nessun numero ipotizzato)")
    return out


# ---------------------------------------------------------------------------
# 4. Composizione (JSON + testo)
# ---------------------------------------------------------------------------

def genera_kpi(banco_rows: list[dict], righe_ledger: list[dict] | None,
               costi_testo: str | None = None, giorni: int = GIORNI_DEFAULT,
               comando: str = "", hash_artefatti: dict[str, str] | None = None) -> dict:
    """Assembla il KPI settimanale. Nessun numero viene inventato: dove manca il
    dato la voce è {stato: 'dati insufficienti', motivo: ...}."""
    kpi: dict = {"tipo": "kpi_settimanali",
                 "generato_il": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                 "giorni": giorni,
                 "comando": comando}
    if hash_artefatti:
        kpi["hash_artefatti"] = hash_artefatti

    attr = attribuzione(banco_rows, giorni * 86400)
    if attr:
        kpi["rendita"] = {"stato": OK, **attr}
        kpi["periodo_effettivo"] = {"da": attr["da"], "a": attr["a"],
                                    "secondi": giorni * 86400}
    else:
        kpi["rendita"] = {"stato": INS,
                          "motivo": ("attribuzione 7g non disponibile: banco con meno "
                                     "di 2 campioni, senza tasso implicito USDC→EUR o "
                                     "con esposizione non calcolabile")}
        kpi["periodo_effettivo"] = {"stato": INS}

    ultima = banco_rows[-1] if banco_rows else None
    kpi["capitale_attuale_eur"] = float(ultima["equity_eur"]) if ultima else None

    rate = rate_implicito(ultima) if ultima else None
    if attr:
        kpi["fee"] = fee_da_ledger(righe_ledger, attr["ts_da"], attr["ts_a"], rate)
    else:
        kpi["fee"] = {"stato": INS,
                      "motivo": "finestra 7g non determinabile (banco insufficiente)"}

    kpi["costi"] = costi_mensili(costi_testo)
    resto = attr["resto_eur"] if attr else None
    cap = kpi["capitale_attuale_eur"]
    if resto is not None and cap is not None:
        kpi["break_even"] = break_even(resto, cap, kpi["costi"]["valore_eur_mese"])
    else:
        kpi["break_even"] = {"stato": INS,
                             "motivo": "rendita 7g o capitale non disponibili",
                             "formula": FORMULA_BREAKEVEN,
                             "limiti": LIMITI_BREAKEVEN}
    return kpi


def componi_testo(kpi: dict) -> str:
    """Testo leggibile senza contesto (stile digest)."""
    righe = ["📈 Denaro — KPI settimanali (lunedì)"]
    per = kpi.get("periodo_effettivo", {})
    if per.get("da"):
        righe.append(f"Periodo effettivo: {str(per['da'])[:16]}Z → {str(per['a'])[:16]}Z "
                     f"({kpi.get('giorni', '?')}g)")
    r = kpi.get("rendita", {})
    if r.get("stato") == OK:
        righe.append(f"Rendita netta 7g: {r['delta_eur']:+.2f} € "
                     f"(cambio {r['cambio_eur']:+.2f} € · resto {r['resto_eur']:+.2f} €)")
    else:
        righe.append(f"Rendita netta 7g: {INS} — {r.get('motivo', '')}")
    f = kpi.get("fee", {})
    if f.get("stato") == OK:
        riga = (f"Fee 7g: {f['somma_eur']:.2f} € — "
                f"{f['incluse']} {'voce' if f['incluse'] == 1 else 'voci'}")
        if f.get("escluse_ccy"):
            riga += (f"; escluse {f['escluse_ccy']} "
                     f"{'voce' if f['escluse_ccy'] == 1 else 'voci'} "
                     f"(valuta non convertibile)")
        if f.get("fuori_periodo"):
            riga += f"; {f['fuori_periodo']} fuori finestra"
        righe.append(riga)
    else:
        righe.append(f"Fee 7g: {INS} — {f.get('motivo', '')}")
    be = kpi.get("break_even", {})
    c = kpi.get("costi", {})
    righe.append("Break-even:")
    if be.get("stato") == OK:
        righe.append(f"  rendita mensilizzata (resto × 30/7): "
                     f"{be['mensilizzata_eur_mese']:+.2f} €/mese")
        righe.append(f"  costi mensili: {c.get('valore_eur_mese', 0):.2f} €/mese "
                     f"({c.get('fonte', 'n/d')})")
        righe.append(f"  distanza dal break-even: {be['distanza_eur_mese']:+.2f} €/mese")
        righe.append(f"  capitale attuale: {be['capitale_attuale_eur']:.2f} € · "
                     f"capitale break-even stimato: "
                     f"{be['capitale_break_even_eur']:,.2f} €")
    else:
        righe.append(f"  {INS} — {be.get('motivo', '')}")
    righe.append(f"  formula: {be.get('formula', FORMULA_BREAKEVEN)}")
    if be.get("limiti"):
        righe.append(f"  {be['limiti']}")
    righe.append(f"Regola: ogni riga \"{INS}\" è un dato assente nelle fonti, "
                 "mai un numero ipotizzato.")
    righe.append(f"Comando: {kpi.get('comando', 'n/d')}")
    return "\n".join(righe)


# ---------------------------------------------------------------------------
# 5. I/O, ssh e CLI
# ---------------------------------------------------------------------------

def _ssh_leggi(target: str, tail: int = 0) -> str:
    """Legge un file remoto via ssh (BatchMode, nessuna chiave exchange coinvolta)."""
    host, _, path = target.partition(":")
    cmd = f"tail -n {int(tail)} {path}" if tail else f"cat {path}"
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10",
                        host, cmd], capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        raise RuntimeError(f"ssh {host} fallito ({r.returncode})")
    return r.stdout or ""


def _hash_bytes(nome: str, testo: str | None) -> dict[str, str]:
    return {} if testo is None else \
        {nome: hashlib.sha256(testo.encode("utf-8")).hexdigest()}


def _invia_telegram(testo: str) -> bool:
    """Invio su Telegram via tools/alert_lib (stesso percorso di watch_alerts.py)."""
    candidati = []
    base = Path(__file__).resolve().parent
    candidati.append(base / "alerts")                # modulo in ops/ -> ops/alerts/
    candidati.append(base.parent / "ops" / "alerts")  # fallback
    candidati.append(base.parent / "tools")           # modulo in ops/
    candidati.append(base / "tools")                  # modulo in root
    for c in candidati:
        if (c / "alert_lib.py").exists():
            sys.path.insert(0, str(c))
            try:
                from alert_lib import invia_o_spool  # noqa: PLC0415
                return bool(invia_o_spool(testo))
            except Exception:  # noqa: BLE001
                return False
    return False


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="KPI settimanali per il digest del lunedì (P25).")
    ap.add_argument("--settimanale", action="store_true",
                    help="componi la sezione KPI settimanali (richiesto; il digest "
                         "giornaliero resta invariato)")
    ap.add_argument("--giorni", type=int, default=GIORNI_DEFAULT,
                    help=f"finestra di attribuzione in giorni (default {GIORNI_DEFAULT})")
    ap.add_argument("--banco-ssh", default=None,
                    help="banco via ssh HOST:PATH (default MARCODG1)")
    ap.add_argument("--banco-file", default=None, help="banco_secco.jsonl locale (offline)")
    ap.add_argument("--banco-righe", type=int, default=2500,
                    help="righe da leggere via ssh (default 2500)")
    ap.add_argument("--fee-ssh", default=None,
                    help="fee_ledger via ssh HOST:PATH (default MARCODG1)")
    ap.add_argument("--fee-file", default=None, help="fee_ledger.jsonl locale (offline)")
    ap.add_argument("--costi-file", default=COSTI_FILE_DEFAULT,
                    help="JSON costi (campo totale_mese_eur); assente -> default ROADMAP")
    ap.add_argument("--json-out", default=None, help="scrivi l'artefatto JSON qui")
    ap.add_argument("--invia", action="store_true",
                    help="invia su Telegram via tools/alert_lib")
    args = ap.parse_args(argv)

    if not args.settimanale:
        print("uso: kpi_settimanali.py --settimanale [--invia] [--json-out F] "
              "[--banco-file F] [--fee-file F]", file=sys.stderr)
        return 2

    comando = "kpi_settimanali.py " + " ".join(f'"{a}"' if " " in a else a for a in argv)
    hash_art: dict[str, str] = {}

    # -- banco (ssh di default, come il digest) --
    try:
        if args.banco_ssh:
            testo_banco = _ssh_leggi(args.banco_ssh, args.banco_righe)
        elif args.banco_file:
            p = Path(args.banco_file).expanduser()
            testo_banco = p.read_text(encoding="utf-8") if p.exists() else ""
        else:
            testo_banco = _ssh_leggi(BANCO_SSH_DEFAULT, args.banco_righe)
    except (RuntimeError, OSError) as e:
        print(f"ERRORE: banco non leggibile ({e})", file=sys.stderr)
        return 1
    banco_rows = parse_banco(testo_banco)
    hash_art.update(_hash_bytes("banco_secco.jsonl", testo_banco))

    # -- fee ledger (ssh di default; assente => 'dati insufficienti', non un crash) --
    righe_ledger: list[dict] | None = None
    testo_fee: str | None = None
    try:
        if args.fee_ssh:
            try:
                testo_fee = _ssh_leggi(args.fee_ssh)
            except RuntimeError:
                testo_fee = None
        elif args.fee_file:
            p = Path(args.fee_file).expanduser()
            testo_fee = p.read_text(encoding="utf-8") if p.exists() else None
        else:
            try:
                testo_fee = _ssh_leggi(FEE_SSH_DEFAULT)
            except RuntimeError:
                testo_fee = None
    except OSError:
        testo_fee = None
    if testo_fee is not None:
        hash_art.update(_hash_bytes("fee_ledger.jsonl", testo_fee))
        righe_ledger = parse_ledger(testo_fee)

    # -- costi (file opzionale) --
    testo_costi: str | None = None
    if args.costi_file:
        p = Path(args.costi_file).expanduser()
        if p.exists():
            testo_costi = p.read_text(encoding="utf-8")
    hash_art.update(_hash_bytes("report_costi.json", testo_costi))

    kpi = genera_kpi(banco_rows, righe_ledger, costi_testo=testo_costi,
                     giorni=args.giorni, comando=comando, hash_artefatti=hash_art)
    testo = componi_testo(kpi)
    print(testo)
    if args.json_out:
        Path(args.json_out).expanduser().write_text(
            json.dumps(kpi, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    if args.invia:
        if _invia_telegram(testo):
            print("invio Telegram: ok")
        else:
            print("invio Telegram: FALLITO (tools/alert_lib non disponibile o invio "
                  "fallito)", file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
