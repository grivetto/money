#!/usr/bin/env python3
"""ipotesi_veloce.py — LO SCREENER. Prende l'ipotesi di un'AI e la uccide o la promuove.

PERCHE' ESISTE
==============
Un LLM non ha dati ne' esecuzione: chiedergli un backtest produce numeri inventati.
Il suo mestiere e' PROP_RE un'ipotesi (meccanismo, regole, spazio di ricerca). Il nostro
e' VERIFICARLA. Questo script chiude il ciclo: prende un'ipotesi in formato fisso e la
misura in minuti sui dati reali, col motore esistente e i costi veri del conto.

NON reimplementa nulla: usa `money.ricerca.scansione` (stessa convenzione del rig: decisione
alla chiusura della barra i, esecuzione all'apertura di i+1, costi `money.costi` + slippage,
DSR corretto per selezione multipla). Se uno screener misura diversamente dal rig, ha gia'
perso: questo usa esattamente lo stesso motore del cancello.

FORMATO DELL'IPOTESI (JSON)
===========================
{
  "nome": "stringa breve",
  "autore": "chi l'ha proposta",
  "timeframe": "1d",
  "inizio": "2020-10-01",
  "fine": "2026-10-08",
  "confine": "2024-06-01",
  "simboli": ["BTC/USDT", "ETH/USDT"],
  "configs": [
    {"famiglia": "rsi2", "periodo": 2, "soglia_in": 10.0, "soglia_out": 60.0}
  ]
}
Famiglie disponibili (dal motore): sma_cross, mom_abs, donchian, reversion_z, rsi2,
weekday, turn_month. Per una famiglia NUOVA serve un `--estensione` (modulo Python che
espone `stato_fn(barre, cfg)`), e lo spazio di ricerca va dichiarato nel JSON.

USO
===
  .venv/bin/python scripts/ipotesi_veloce.py --ipotesi prove/ipotesi/mia.json
  .venv/bin/python scripts/ipotesi_veloce.py --ipotesi mia.json --stress 2.0
  .venv/bin/python scripts/ipotesi_veloce.py --ipotesi mia.json --estensione path.py

Verdetto per selezione:
  PROMOSSA  = n_oos >= 30, expectancy netta > 0, t > 0, DSR >= 0.95
  RESPINTA  = tutto il resto, col motivo primario.

Il conteggio dei tentativi per il DSR e' quello DELL'IPOTESI (questo e' lo screening di
un'ipotesi nuova, non una nuova caccia): se vuoi includere anche i tentativi storici
cumulativi, passa `--cumulativi N`.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# --- bootstrap dei percorsi (stessa convenzione di caccia_continua.py) -----------------
for _antenato in Path(__file__).resolve().parents:
    _src = _antenato / "src"
    if (_src / "money" / "__init__.py").exists():
        for _p in (str(_src), str(_antenato)):
            if _p not in sys.path:
                sys.path.insert(0, _p)
        break
sys.path.insert(0, str(Path(__file__).resolve().parent))

from money.costi import get_tariffa  # noqa: E402
from money.dati import Scarica  # noqa: E402
from money.esecuzione import promozione as PR  # noqa: E402
from money.ricerca import scansione as S  # noqa: E402
from money.statistica import sharpe_deflazionato  # noqa: E402
from scansione import SLIPPAGE_PER_LATO, TARIFFA, carica_universo  # noqa: E402

RADICE = Path(__file__).resolve().parents[1]
OUT_DIR = RADICE / "prove" / "ipotesi"


def _famiglie_disponibili() -> tuple:
    return ("sma_cross", "mom_abs", "donchian", "reversion_z", "rsi2", "weekday", "turn_month")


def carica_estensione(path: str):
    """Carica un modulo che espone `stato_fn(barre, cfg)` per famiglie NUOVE.

    Ritorna (stato_fn, famiglie): le `famiglie` sono l'attributo opzionale `FAMIGLIE`
    (tuple di nomi) che l'estensione puo' dichiarare, per il fail-closed della validazione.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location("_estensione_ipotesi", path)
    if not spec or not spec.loader:
        raise SystemExit(f"estensione non caricabile: {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "stato_fn"):
        raise SystemExit("l'estensione deve esporre `stato_fn(barre, cfg)`")
    return mod.stato_fn, tuple(getattr(mod, "FAMIGLIE", ()))


def valida(ip: dict, famiglie_extra: tuple = ()) -> None:
    """Fail-closed sull'ipotesi: senza questi campi non si misura nulla.

    `famiglie_extra` = famiglie fornite da un'--estensione (il controllo di appartenenza
    deve includerle, altrimenti l'estensione e' inutile).
    """
    mancanti = [c for c in ("nome", "timeframe", "inizio", "fine", "confine",
                            "simboli", "configs") if not ip.get(c)]
    if mancanti:
        raise SystemExit(f"ipotesi incompleta: mancano {mancanti}")
    if not isinstance(ip["configs"], list) or not ip["configs"]:
        raise SystemExit("`configs` deve essere una lista non vuota")
    disponibili = tuple(_famiglie_disponibili()) + tuple(famiglie_extra)
    for i, cfg in enumerate(ip["configs"]):
        if not cfg.get("famiglia"):
            raise SystemExit(f"configs[{i}] senza `famiglia`")
        if cfg["famiglia"] not in disponibili:
            raise SystemExit(
                f"configs[{i}] famiglia ignota {cfg['famiglia']!r}: disponibili "
                f"{disponibili} (o passa --estensione)")


def _dsr_valore(sel: dict):
    """Il DSR della selezione, normalizzato a float in un punto solo.

    Chiave corrente: `dsr_selezione` (DSR sulla finestra di addestramento — fix del
    giudice statistico, 13/10). Gli artefatti precedenti al fix usavano `dsr_oos` (DSR
    mal calcolato sulla verifica): si legge ancora, per non rompere la visualizzazione
    della cronologia; i risultati freschi portano sempre `dsr_selezione`.
    Il valore puo' arrivare come float o come dict {"dsr": ...}: entrambe le forme.
    """
    raw = sel.get("dsr_selezione")
    if raw is None:
        raw = sel.get("dsr_oos")
    if isinstance(raw, dict):
        return raw.get("dsr")
    return raw


def dsr_effettivo(sel: dict, *, n_cumulativo: int, varianza_sharpe: float) -> tuple:
    """(dsr_effettivo, dsr_locale, dsr_cumulativo) — correzione Manus 03/11 (P1a).

    Il DSR che decide e' il piu' prudente fra quello locale della scansione (N dell'ipotesi)
    e quello ricalcolato con l'N cumulativo (tentativi dell'ipotesi + storici). Il ricalcolo
    usa lo Sharpe e la numerosita' della finestra di ADDESTRAMENTO (dove la selezione e'
    avvenuta, fix 13/10) e la varianza degli Sharpe dei tentativi dichiarata dalla scansione.
    Fail-closed: senza Sharpe o con campione corto -> dsr_effettivo None (mai un default
    permissivo).
    """
    dsr_locale = _dsr_valore(sel)
    if not n_cumulativo or n_cumulativo < 1:
        return dsr_locale, dsr_locale, None
    tr = sel.get("train") or {}
    sr = tr.get("sharpe")
    n_tr = tr.get("n")
    if sr is None or not n_tr or n_tr < 2:
        return None, dsr_locale, None
    try:
        out = sharpe_deflazionato(float(sr), int(n_tr), int(n_cumulativo),
                                  float(varianza_sharpe))
    except ValueError:
        return None, dsr_locale, None
    dsr_cum = out["dsr"]
    eff = min(dsr_locale, dsr_cum) if dsr_locale is not None else dsr_cum
    return eff, dsr_locale, dsr_cum


def verdetto(sel: dict, *, min_op: int, soglia_dsr: float) -> tuple[str, str]:
    """(PROMOSSA/RESPINTA, motivo). L'ordine dei controlli e' deliberato."""
    o = sel.get("oos") or {}
    tr = sel.get("train") or {}
    # Fail-closed (correzione Manus 03/11): se lo screener ha calcolato il DSR effettivo
    # (chiave presente, anche se None = non calcolabile) quello DECIDE. Il fallback sul
    # DSR locale vale SOLO per artefatti legacy che non hanno la chiave.
    if "dsr_effettivo" in sel:
        dsr = sel["dsr_effettivo"]
    else:
        dsr = _dsr_valore(sel)
    if (o.get("n") or 0) < min_op:
        return "RESPINTA", f"verifica con {o.get('n') or 0} operazioni < {min_op} (campione insufficiente)"
    if not ((o.get("expectancy") or 0.0) > 0.0):
        return "RESPINTA", f"expectancy di verifica {o.get('expectancy')} non positiva"
    if not ((o.get("t_stat") or 0.0) > 0.0):
        return "RESPINTA", f"t-stat {o.get('t_stat')} non positivo (effetto indistinguibile da zero)"
    if dsr is None or dsr < soglia_dsr:
        extra = " cumulativo" if sel.get("dsr_cumulativo") is not None else ""
        return "RESPINTA", (f"DSR{extra} {dsr if dsr is None else round(dsr, 4)} "
                            f"< {soglia_dsr} (selezione multipla)")
    return "PROMOSSA", (f"n={o.get('n')} exp={o.get('expectancy'):.4f} t={o.get('t_stat'):.2f} "
                        f"DSR={dsr:.4f} (train n={tr.get('n')}, exp={tr.get('expectancy')})")


def _gate_report(e: dict, cross: dict) -> dict:
    """Report per gate (correzione Manus 03/11): ogni proposta dichiara il proprio esito
    per gate, con i numeri — mai un solo "non passa"."""
    o = e.get("oos") or {}
    return {
        "G1_screener": {
            "esito": e.get("verdetto"),
            "motivo": e.get("motivo"),
            "n_oos": o.get("n"),
            "expectancy": o.get("expectancy"),
            "t_stat": o.get("t_stat"),
            "dsr": e.get("dsr"),
            "dsr_locale": e.get("dsr_locale"),
            "dsr_cumulativo": e.get("dsr_cumulativo"),
        },
        "G2_cross_simbolo": {
            "esito": cross.get("verdetto_meccanismo"),
            "quota_positiva": cross.get("quota_positiva"),
            "media_attesa": cross.get("media_attesa"),
            "n_simboli": cross.get("n_simboli"),
        },
        "G3_sblocco": e.get("sblocco"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Screener di ipotesi (verifica coi costi veri)")
    ap.add_argument("--ipotesi", required=True, help="file JSON dell'ipotesi")
    ap.add_argument("--stress", type=float, default=1.0,
                    help="moltiplicatore slippage (>1 = scenario avverso)")
    ap.add_argument("--cumulativi", type=int, default=0,
                    help="tentativi storici cumulativi da aggiungere al conteggio DSR")
    ap.add_argument("--estensione", default="", help="modulo con stato_fn per famiglie nuove")
    ap.add_argument("--promuovi", action="store_true",
                    help="se una selezione e' PROMOSSA, scrive un artefatto di fase (default: "
                         "PaperArtifact PASS_PAPER, capitale CONGELATO)")
    ap.add_argument("--live", action="store_true",
                    help="con --promuovi: scrive un PromotionArtifact (sblocca il capitale) "
                         "invece del PaperArtifact di default")
    ap.add_argument("--capitale", type=float, default=100.0,
                    help="capitale massimo che la promozione autorizza (default 100 EUR)")
    ap.add_argument("--json", action="store_true", help="stampa solo il risultato JSON")
    a = ap.parse_args()

    ip = json.loads(Path(a.ipotesi).read_text(encoding="utf-8"))

    # l'estensione va caricata PRIMA della validazione: le sue famiglie devono
    # superare il fail-closed, altrimenti l'estensione e' inutile.
    stato_fn = S.stato_per_config
    famiglie_extra: tuple = ()
    if a.estensione:
        stato_fn, famiglie_extra = carica_estensione(a.estensione)
    valida(ip, famiglie_extra=famiglie_extra)

    slippage = SLIPPAGE_PER_LATO * float(a.stress)
    tariffa = get_tariffa(TARIFFA)

    dati = carica_universo(Scarica(), tuple(ip["simboli"]), ip["inizio"], ip["fine"])
    if not dati:
        raise SystemExit("nessun simbolo con dati validi: ipotesi non misurabile")

    res = S.scansiona(dati, griglia=tuple(ip["configs"]), stato_fn=stato_fn,
                      confine=ip["confine"], tariffa=tariffa, slippage=slippage)

    # DSR onesto: se richiesto, il conteggio dei tentativi include anche lo storico cumulativo.
    n_eff = res["meta"]["n_trials_valutabili"] + max(0, a.cumulativi)
    var_sharpe = res["meta"].get("varianza_sharpe_train") or 0.0

    # Correzione Manus 03/11 (P1a): --cumulativi deve CAMBIARE il DSR usato dal verdetto,
    # non solo il campo dell'artefatto. Il DSR cumulativo ricalcola il deflated Sharpe
    # della selezione (finestra di ADDESTRAMENTO, come da fix 13/10) con l'N cumulativo;
    # vale il piu' prudente fra locale e cumulativo (fail-closed: senza ingredienti -> None).
    for sel in res["selezioni"]:
        if a.cumulativi > 0:
            eff, loc, cum = dsr_effettivo(sel, n_cumulativo=n_eff,
                                          varianza_sharpe=var_sharpe)
        else:
            loc = _dsr_valore(sel)
            eff, cum = loc, None
        sel["dsr_locale"] = loc
        sel["dsr_cumulativo"] = cum
        sel["dsr_effettivo"] = eff
        sel["n_cumulativo"] = n_eff

    esiti = []
    for sel in res["selezioni"]:
        v, motivo = verdetto(sel, min_op=S.MIN_OP, soglia_dsr=S.SOGLIA_DSR)
        esiti.append({
            "config": sel["chiave"], "simbolo": sel["simbolo"],
            "train": sel["train"], "oos": sel["oos"],
            "dsr": sel["dsr_effettivo"], "dsr_locale": sel["dsr_locale"],
            "dsr_cumulativo": sel["dsr_cumulativo"], "n_cumulativo": sel["n_cumulativo"],
            "verdetto": v, "motivo": motivo,
        })

    # --- consistenza cross-simbolo: il meccanismo regge su PIU' simboli, o e' un caso? ---
    # Una selezione puo' vincere su un simbolo per fortuna. Il test forte e' la MEDIA del
    # meccanismo su TUTTI i simboli: se la configurazione ha expectancy OOS positiva solo
    # sul "migliore" e negativa altrove, non e' un edge -- e' selezione.
    per_config: dict = {}
    for t in res["trials"]:
        per_config.setdefault(t["chiave"], []).append(t)
    consistenza = []
    for chiave in sorted(per_config):
        oos_exp = [t["oos"]["expectancy"] for t in per_config[chiave]
                   if (t["oos"]["n"] or 0) >= S.MIN_OP and t["oos"]["expectancy"] is not None]
        if not oos_exp:
            consistenza.append({"config": chiave, "n_simboli": 0, "quota_positiva": None,
                                "media_attesa": None, "verdetto_meccanismo": "NON_TESTABILE"})
            continue
        quota = sum(1 for x in oos_exp if x > 0) / len(oos_exp)
        media = sum(oos_exp) / len(oos_exp)
        # PROMOSSO solo se la MAGGIORANZA dei simboli e' positiva E la media e' positiva.
        vm = "COERENTE" if (quota >= 0.6 and media > 0) else "NON COERENTE"
        consistenza.append({"config": chiave, "n_simboli": len(oos_exp),
                            "quota_positiva": round(quota, 3), "media_attesa": round(media, 6),
                            "verdetto_meccanismo": vm})

    # --- report per gate (correzione Manus 03/11): ogni proposta dichiara il suo esito
    # per gate, con i numeri — mai un solo "non passa" --------------------------------
    coerenti = {c["config"]: c for c in consistenza}
    for e in esiti:
        cross = coerenti.get(e["config"], {})
        if e["verdetto"] == "PROMOSSA" and cross.get("verdetto_meccanismo") == "COERENTE":
            e["sblocco"] = "pass_paper"
        else:
            e["sblocco"] = "bloccato"
        e["gate"] = _gate_report(e, cross)

    out = {
        "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "ipotesi": ip.get("nome"), "autore": ip.get("autore"),
        "finestre": {"inizio": ip["inizio"], "confine": ip["confine"], "fine": ip["fine"]},
        "stress_slippage": a.stress,
        "tariffa": TARIFFA,
        "n_config": len(ip["configs"]), "n_trials_valutabili": res["meta"]["n_trials_valutabili"],
        "n_tentativi_dsr": n_eff,
        "candidati": len(res["candidati"]),
        "selezioni": esiti,
        "consistenza_meccanismo": consistenza,
    }

    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=1))
    else:
        print(f"SCREENER — {ip.get('nome')}  [{ip.get('autore', 'n/d')}]")
        print(f"  finestre: train {ip['inizio']}..{ip['confine']} | verifica {ip['confine']}..{ip['fine']}")
        print(f"  costo: tariffa {TARIFFA} | slippage/lato {slippage:.5f} (stress x{a.stress})")
        print(f"  prove: {len(ip['configs'])} config x {len(dati)} simboli | "
              f"tentativi valutabili {res['meta']['n_trials_valutabili']} | DSR su N={n_eff}")
        print("  " + "-" * 84)
        if not esiti:
            print("  nessuna configurazione ha prodotto una selezione (tutte insufficienti)")
        for e in esiti:
            o = e["oos"]; tr = e["train"]
            flag = "PROMOSSA" if e["verdetto"] == "PROMOSSA" else "respin."
            print(f"  [{flag:8s}] {e['config'][:44]:44s} {e['simbolo']:10s} "
                  f"tr n={tr.get('n'):>3} exp={_f(tr.get('expectancy'))} | "
                  f"oos n={o.get('n'):>3} exp={_f(o.get('expectancy'))} "
                  f"t={_f(o.get('t_stat'))} dsr={_f(e['dsr'])}")
            print(f"             -> {e['motivo']}")
        print("  " + "-" * 84)
        print(f"  VERDETTO: {out['candidati']} promosse / {len(esiti)} selezioni")

    if not a.json:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        slug = "".join(c if (c.isalnum() or c in "-_") else "_" for c in str(ip.get("nome", "ipotesi")))[:60]
        p = OUT_DIR / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{slug}.json"
        p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  artefatto: {p.relative_to(RADICE)}")

    # --- fase post-gate (correzione Manus 03/11): default PASS_PAPER, capitale CONGELATO.
    # Il capitale di validazione (~100 EUR) NON si arma per "testare l'infra": si arma solo
    # con --live esplicito, quando un'ipotesi supera il cancello E il meccanismo e' coerente
    # su piu' simboli. Senza --live si scrive un PaperArtifact (prove/pass_paper/).
    if a.promuovi:
        promosse = [e for e in esiti if e["verdetto"] == "PROMOSSA"]
        if not promosse:
            print("  [promozione] NESSUNA selezione PROMOSSA: il capitale resta congelato.")
            return 0
        # la migliore promossa, ma solo se il meccanismo e' coerente cross-simbolo
        migliore = max(promosse, key=lambda e: e["oos"].get("expectancy") or 0.0)
        mc = coerenti.get(migliore["config"], {})
        if mc.get("verdetto_meccanismo") != "COERENTE":
            print(f"  [promozione] RIFIUTATA: il meccanismo {migliore['config']} non e' "
                  f"coerente cross-simbolo ({mc.get('quota_positiva')} positivi). "
                  "Una selezione su un simbolo fortunato non basta.")
            return 0
        metriche = {"oos": migliore["oos"], "train": migliore["train"],
                    "simbolo": migliore["simbolo"], "config": migliore["config"],
                    "dsr_locale": migliore["dsr_locale"],
                    "dsr_cumulativo": migliore["dsr_cumulativo"],
                    "n_cumulativo": migliore["n_cumulativo"]}
        costi = {"tariffa": TARIFFA, "slippage_lato": slippage}
        if a.live:
            # Manus 03/11: --live NON salta la fase paper. Serve un PaperArtifact PASS_PAPER
            # valido (firma, non scaduto) per la STESSA strategia, scritto in prove/pass_paper/.
            sid = _slug(migliore["config"])
            paper_ok = False
            cart = RADICE / "prove" / "pass_paper"
            for pf in sorted(cart.glob("*.paper.json")) if cart.exists() else []:
                try:
                    pa = PR.leggi_paper(pf)   # valida hash, DSR>=0.95 e TTL (solleva se invalido)
                except Exception:
                    continue
                if pa.strategy_id == sid:
                    paper_ok = True
                    break
            if not paper_ok:
                print(f"  [promozione] LIVE RIFIUTATO: nessun PaperArtifact PASS_PAPER valido e "
                      f"non scaduto per {sid} in prove/pass_paper/. Esegui prima senza --live.")
                return 0
            art = PR.crea(
                strategy_id=_slug(migliore["config"]), nome=str(ip.get("nome")),
                capitale_max_eur=float(a.capitale),
                n_tentativi_ipotesi=res["meta"]["n_trials_valutabili"],
                n_tentativi_cumulativi=max(n_eff, res["meta"]["n_trials_valutabili"]),
                dsr=float(migliore["dsr"]), costi=costi, metriche=metriche)
            pp = PR.scrivi(art, RADICE / "prove" / "promozioni")
            print(f"  [promozione] ARTEFATTO LIVE SCRITTO: {pp.relative_to(RADICE)}")
            print(f"  [promozione] capitale autorizzato {art.capitale_max_eur:.0f} EUR, "
                  f"scade {art.scade[:10]}, DS R {art.dsr:.4f}, "
                  f"N cumulativo {art.n_tentativi_cumulativi}")
        else:
            art = PR.crea_paper(
                strategy_id=_slug(migliore["config"]), nome=str(ip.get("nome")),
                dsr=float(migliore["dsr"]), costi=costi, metriche=metriche)
            pp = PR.scrivi_paper(art, RADICE / "prove" / "pass_paper")
            print(f"  [pass_paper] ARTEFATTO SCRITTO: {pp.relative_to(RADICE)} "
                  f"(capitale CONGELATO: per sbloccarlo serve --live)")
    return 0


def _slug(testo: str) -> str:
    return "".join(c if (c.isalnum() or c in "-_") else "_" for c in testo)[:48]


def _f(x) -> str:
    return f"{x:+.4f}" if isinstance(x, float) else ("n/d" if x is None else str(x))


if __name__ == "__main__":
    sys.exit(main())
