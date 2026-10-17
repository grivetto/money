"""Test di report_mensile.py — REQ-MERL-20261017-003.

Fixture: 2 mesi sintetici con numeri noti (settembre/ottobre fittizi).
L'aritmetica del netto e la detrazione delle fee sono verificate qui:
  mese A: lordo 10.00, fee 1.50 -> rendita netta 8.50; costi 31.00 -> netto -22.50
  mese B: lordo 12.00, fee 2.00 -> rendita netta 10.00; costi 31.00 -> netto -21.00
Il banco sintetico è costruito per produrre cambio +50.00 EUR esatti
(rate 0.90 -> 0.95 su esposizione 1000 USDC costante), così il resto del banco
DEVE essere lordo - fee: è la verifica della detrazione.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops"))
import report_mensile as rm  # noqa: E402

MESE_A = "2026-09"
MESE_B = "2026-10"


def riga(ts: str, eq: float, trading: float = 0.0, funding: float = 0.0,
         savings: float = 900.0, usdc: float = 1000.0) -> dict:
    return {"nome": "banco_secco", "timestamp": ts, "esito": "PASS",
            "equity_eur": eq, "equity_trading_eur": trading,
            "equity_funding_eur": funding, "equity_savings_eur": savings,
            "saldi_trading": {"EUR": trading}, "saldi_funding": {"EUR": 0.0},
            "saldi_savings": {"USDC": usdc}, "ordini_aperti": 0,
            "riconciliazione_quadra": "si", "chiave_solo_lettura": "si"}


def banco_mese(mese: str, resto: float) -> list[dict]:
    """Banco sintetico di un mese: cambio +50.00 EUR, resto = resto (in EUR, trading)."""
    eq0 = 900.0
    eq1 = eq0 + 50.0 + resto
    return [
        riga(f"{mese}-01T00:00:00Z", eq0),
        riga(f"{mese}-28T23:59:00Z", eq1, trading=resto, savings=950.0),
    ]


def costi_file(totale_parziale: list[tuple[str, float]]) -> str:
    voci = [{"voce": n, "importo_eur_mese": v, "fonte": "fixture test"}
            for n, v in totale_parziale]
    return json.dumps({"voci": voci})


# ---------------------------------------------------------------- parsing

def test_parse_banco_valide_e_ordinate():
    testo = "\n".join([
        json.dumps(riga("2026-09-02T00:00:00Z", 901.0)),
        "riga rotta non json",
        json.dumps(riga("2026-09-01T00:00:00Z", 900.0)),
        json.dumps({"nome": "x", "timestamp": "2026-09-03T00:00:00Z"}),  # senza equity
    ])
    righe = rm.parse_banco(testo)
    assert [r["timestamp"] for r in righe] == ["2026-09-01T00:00:00Z", "2026-09-02T00:00:00Z"]


def test_rate_implicito_savings_fallback_none():
    d = {"equity_savings_eur": 950.0, "saldi_savings": {"USDC": 1000.0}}
    assert rm.rate_implicito(d) == 0.95
    d2 = {"equity_funding_eur": 190.0, "saldi_funding": {"USDC": 200.0}}
    assert abs(rm.rate_implicito(d2) - 0.95) < 1e-12
    assert rm.rate_implicito({"equity_eur": 100.0}) is None


def test_esposizione_usd():
    d = riga("2026-09-01T00:00:00Z", 900.0)
    assert abs(rm.esposizione_usd(d, 0.90) - 1000.0) < 1e-9  # solo USDC
    d2 = riga("2026-09-01T00:00:00Z", 900.0, trading=100.0)
    d2["saldi_trading"] = {"EUR": 0.0, "USDC": 0.0}  # cripto stimata 100 EUR
    assert abs(rm.esposizione_usd(d2, 0.90) - (1000.0 + 100.0 / 0.90)) < 1e-9
    assert abs(rm.esposizione_usd({"equity_eur": 1.0}, 0.90) - 0.0) < 1e-12  # come il digest: 0


# ---------------------------------------------------------------- attribuzione

def test_attribuzione_aritmetica_esatta():
    rows = banco_mese(MESE_A, 8.50)
    attr = rm.attribuzione(rows, f"{MESE_A}-01T00:00:00Z", f"{MESE_A}-30T23:59:59Z")
    assert attr["stato"] == "ok"
    assert abs(attr["delta_eur"] - 58.50) < 1e-9          # 958.50-900.00
    sc = attr["scomposizione"]
    assert sc["stato"] == "ok"
    assert abs(sc["cambio_eur"] - 50.0) < 1e-9            # (0.95-0.90)*1000
    assert abs(sc["resto_eur"] - 8.50) < 1e-9


def test_attribuzione_senza_rate_scomposizione_insufficiente():
    rows = [
        {"nome": "banco_secco", "timestamp": "2026-09-01T00:00:00Z",
         "equity_eur": 900.0, "equity_funding_eur": 900.0,
         "saldi_funding": {"EUR": 900.0}},  # nessun USDC -> rate n/d
        {"nome": "banco_secco", "timestamp": "2026-09-30T00:00:00Z",
         "equity_eur": 899.0, "equity_funding_eur": 899.0,
         "saldi_funding": {"EUR": 899.0}},
    ]
    attr = rm.attribuzione(rows, f"{MESE_A}-01T00:00:00Z", f"{MESE_A}-30T23:59:59Z")
    assert attr["stato"] == "ok"                # il delta in EUR è calcolabile
    assert abs(attr["delta_eur"] - (-1.0)) < 1e-9
    sc = attr["scomposizione"]
    assert sc["stato"] == "dati insufficienti"
    assert "cambio_eur" not in sc               # nessun numero ipotizzato


def test_attribuzione_copertura_comparti_cambia_mai_rendita_fantasma():
    # Caso reale 10/2026: dal 10/10 il banco legge trading+funding (savings non
    # letti, capitale in transito); dal 14/10 legge anche i savings. La
    # scomposizione NON deve partire dal 10/10 (produrrebbe un resto fantasma
    # di ~+990 EUR): deve partire dal primo campione con copertura completa.
    rows = [
        {"nome": "banco_secco", "timestamp": "2026-10-10T21:51:00Z",
         "equity_eur": 105.93, "equity_trading_eur": 14.0, "equity_funding_eur": 91.93,
         "saldi_trading": {"EUR": 0.0, "USDC": 11.0}, "saldi_funding": {"USDC": 100.0}},
        # 14/10: il banco inizia a leggere i savings -> equity torna al reale
        {"nome": "banco_secco", "timestamp": "2026-10-14T00:04:00Z",
         "equity_eur": 1099.99, "equity_trading_eur": 20.0, "equity_funding_eur": 94.0,
         "equity_savings_eur": 985.99,
         "saldi_trading": {"EUR": 0.0, "USDC": 11.0}, "saldi_funding": {"USDC": 100.0},
         "saldi_savings": {"USDC": 1100.0}},
        {"nome": "banco_secco", "timestamp": "2026-10-16T23:50:00Z",
         "equity_eur": 1095.99, "equity_trading_eur": 18.0, "equity_funding_eur": 94.0,
         "equity_savings_eur": 983.99,
         "saldi_trading": {"EUR": 0.0, "USDC": 11.0}, "saldi_funding": {"USDC": 100.0},
         "saldi_savings": {"USDC": 1100.0}},
    ]
    attr = rm.attribuzione(rows, "2026-10-01T00:00:00Z", "2026-10-16T23:59:59Z")
    sc = attr["scomposizione"]
    assert sc["stato"] == "ok"
    assert sc["da"].startswith("2026-10-14")        # NON il 10/10 (copertura diversa)
    # il resto del sotto-periodo è piccolo (mark-to-market), non +990
    assert abs(sc["resto_eur"]) < 20.0
    assert "sotto-periodo" in sc["nota"]


def test_attribuzione_comparto_savings_solo_usdc():
    rows = banco_mese(MESE_A, 8.50)
    c = rm.attribuzione_comparto(rows, "savings", f"{MESE_A}-01T00:00:00Z",
                                 f"{MESE_A}-30T23:59:59Z")
    assert c["stato"] == "ok"
    assert abs(c["delta_eur"] - 50.0) < 1e-9       # 950-900: solo cambio
    assert abs(c["cambio_eur"] - 50.0) < 1e-9
    assert abs(c["resto_eur"] - 0.0) < 1e-9


# ---------------------------------------------------------------- Earn

def test_rendita_earn_delta_usdc_e_conversione():
    rows = [
        riga(f"{MESE_A}-01T00:00:00Z", 900.0, usdc=1000.0),
        riga(f"{MESE_A}-30T23:59:00Z", 950.19, usdc=1000.2),  # +0.2 USDC
    ]
    e = rm.rendita_earn(rows, f"{MESE_A}-01T00:00:00Z", f"{MESE_A}-30T23:59:59Z", 0.95)
    assert e["stato"] == "ok"
    assert abs(e["delta_usdc"] - 0.2) < 1e-12
    assert abs(e["eur"] - 0.19) < 1e-12
    assert e["fee_eur"] == 0.0


def test_rendita_earn_senza_savings():
    rows = [
        {"nome": "banco_secco", "timestamp": "2026-09-01T00:00:00Z", "equity_eur": 900.0},
        {"nome": "banco_secco", "timestamp": "2026-09-30T00:00:00Z", "equity_eur": 901.0},
    ]
    e = rm.rendita_earn(rows, f"{MESE_A}-01T00:00:00Z", f"{MESE_A}-30T23:59:59Z", None)
    assert e["stato"] == "dati insufficienti"
    assert "delta_usdc" not in e


def test_rendita_earn_flag_trasferimento():
    rows = [
        riga(f"{MESE_A}-01T00:00:00Z", 900.0, usdc=1000.0),
        riga(f"{MESE_A}-30T23:59:00Z", 900.0, usdc=800.0),  # -200 USDC savings
    ]
    rows[0]["saldi_funding"] = {"USDC": 100.0}
    rows[1]["saldi_funding"] = {"USDC": 300.0}  # +200 USDC funding: trasferimento
    e = rm.rendita_earn(rows, f"{MESE_A}-01T00:00:00Z", f"{MESE_A}-30T23:59:59Z", 0.95)
    assert e["stato"] == "dati insufficienti"
    assert "trasferimento" in e["motivo"]
    assert "-200.0000" in e["motivo"]  # i numeri misurati sono nel motivo, mai come rendita


# ---------------------------------------------------------------- carry

def test_carry_c1_apertura_nel_mese():
    stato = {"ts_open": f"{MESE_A}-05T12:00:00+00:00", "last_funding": 0.0447,
             "last_check": f"{MESE_A}-28T23:00:00+00:00", "inst": "DOGE-USD_UM_XPERP"}
    c = rm.carry_c1_da_stato(stato, f"{MESE_A}-01T00:00:00Z", 0.95)
    assert c["stato"] == "ok"
    assert abs(c["funding_usdc"] - 0.0447) < 1e-12
    assert abs(c["eur"] - 0.0447 * 0.95) < 1e-12


def test_carry_c1_apertura_prima_del_mese():
    stato = {"ts_open": "2026-08-20T12:00:00+00:00", "last_funding": 0.1,
             "last_check": f"{MESE_A}-28T23:00:00+00:00"}
    c = rm.carry_c1_da_stato(stato, f"{MESE_A}-01T00:00:00Z", 0.95)
    assert c["stato"] == "dati insufficienti"


def test_carry_multi_upl_non_realizzato():
    stato = {"nozionale_totale_eur": 179.79, "upl_totale": -0.1436,
             "coppie": {"DOT": {"aperta": True, "nozionale_eur": 89.9, "upl": -1.99,
                                "ts_apri": "2026-10-15T23:00:02+00:00"}}}
    m = rm.carry_multi_da_stato(stato)
    assert m["stato"] == "ok"
    assert "NON realizzato" in m["nota"]


# ---------------------------------------------------------------- fee / costi / netto

def test_rendita_netta_detrazione_fee():
    assert abs(rm.rendita_netta(10.00, 1.50) - 8.50) < 1e-12
    assert abs(rm.rendita_netta(12.00, 2.00) - 10.00) < 1e-12


def test_netto_mensile_aritmetica():
    assert abs(rm.netto_mensile(8.50, 31.00) - (-22.50)) < 1e-12
    assert abs(rm.netto_mensile(10.00, 31.00) - (-21.00)) < 1e-12


def test_fee_da_review():
    assert rm.fee_da_review({"fee": {"observed_total": 1.50,
                                     "observed_scope": "spot-only"}})["osservate_eur"] == 1.50
    assert rm.fee_da_review({"fee": {"observed_total": "n/d"}})["stato"] == "dati insufficienti"
    assert rm.fee_da_review({})["stato"] == "dati insufficienti"


def test_costi_da_file_e_assenti():
    c = rm.costi_da_file(costi_file([("VPS", 9.0), ("AI", 22.0)]))
    assert c["stato"] == "ok"
    assert abs(c["totale_eur_mese"] - 31.0) < 1e-12
    assert rm.costi_da_file(None)["stato"] == "dati insufficienti"
    assert "DA CONFERMARE" in rm.costi_da_file(None)["motivo"]


# ---------------------------------------------------------------- incidenti / decisioni

def test_incidenti_solo_mese_richiesto_e_raggruppati():
    righe = [
        f"{MESE_A}-04 01:30:05 | ⚠️ canary C1: exit 1",
        f"{MESE_A}-04 02:30:05 | ⚠️ canary C1: exit 1",
        f"{MESE_A}-05 03:00:05 | ⚠️ canary C1: ANOMALIE: funding cum 0.0107",
        f"{MESE_A}-05 04:00:05 | ⚠️ canary C1: ANOMALIE: funding cum 0.0118",
        f"{MESE_B}-01 00:00:05 | ⚠️ equity sotto soglia",
        f"{MESE_A}-06 09:00:05 | 🫀 Denaro — check giornaliero",  # non allarme
    ]
    inc = rm.incidenti_da_sentlog(righe, MESE_A)
    assert inc["stato"] == "ok"
    assert inc["conteggio"] == 4
    # i numeri sono normalizzati (anche "C1" -> "C#"): le due ANOMALIE collassano
    assert "canary C#: ANOMALIE: funding cum #" in inc["categorie"]
    assert inc["categorie"]["canary C#: ANOMALIE: funding cum #"] == 2
    assert inc["categorie"]["canary C#: exit #"] == 2
    assert rm.incidenti_da_sentlog([], MESE_A)["stato"] == "dati insufficienti"


ROADMAP_SINT = """# ROADMAP

## 7. Le decisioni

1. **D1 · Taglio costi** — AI e VPS.
2. **D2 · Dormienti** — funding in Earn.
3. **D3 · Carry** — scala a step.

### Risposte del proprietario

- **D2: SÌ, con preflight** — ok.
- **D3: SÌ, a step con i gate** — ok.
"""


def test_decisioni_aperte():
    dec = rm.decisioni_da_roadmap(ROADMAP_SINT)
    assert dec["stato"] == "ok"
    assert dec["aperte"] == ["D1 · Taglio costi"]
    assert dec["totale"] == 3 and dec["decise"] == 2
    assert rm.decisioni_da_roadmap(None)["stato"] == "dati insufficienti"
    assert rm.decisioni_da_roadmap("nessuna voce D qui")["stato"] == "dati insufficienti"


# ---------------------------------------------------------------- report completo 2 mesi

REVIEW_A = {"fee": {"observed_total": 1.50, "observed_scope": "spot-only",
                    "criterion_pass": "N/D"}}
REVIEW_B = {"fee": {"observed_total": 2.00, "observed_scope": "spot-only",
                    "criterion_pass": "N/D"}}


def _report_mese(mese: str, resto: float, review: dict) -> dict:
    return rm.genera_report(
        mese=mese, banco_rows=banco_mese(mese, resto), canary_stato=None,
        carry_stato=None, review=review, sent_righe=[], roadmap=ROADMAP_SINT,
        scommessa=None, costi=costi_file([("VPS", 9.0), ("AI", 22.0)]),
        fino_iso=None, comando="test",
        hash_artefatti={"fixture": "hash"})


def test_report_mese_a_aritmetica_netto_e_fee():
    rep = _report_mese(MESE_A, 8.50, REVIEW_A)
    tot = rep["rendita"]["totale"]
    assert tot["stato"] == "ok"
    sc = tot["scomposizione"]
    assert abs(sc["resto_eur"] - 8.50) < 1e-9
    # detrazione fee: resto == lordo - fee (10.00 - 1.50)
    assert abs(sc["resto_eur"] - rm.rendita_netta(10.00, 1.50)) < 1e-9
    assert rep["rendita"]["fee"]["osservate_eur"] == 1.50
    # netto: rendita netta - costi (8.50 - 31.00)
    assert rep["netto"]["stato"] == "ok"
    assert abs(rep["netto"]["eur_mese"] - rm.netto_mensile(8.50, 31.00)) < 1e-9
    # capitale di chiusura
    assert abs(rep["capitale"]["chiusura_eur"] - 958.50) < 1e-9
    assert rep["capitale"]["riconciliazione_quadra"] == "si"


def test_report_mese_b_aritmetica_netto_e_fee():
    rep = _report_mese(MESE_B, 10.00, REVIEW_B)
    sc = rep["rendita"]["totale"]["scomposizione"]
    assert abs(sc["resto_eur"] - 10.00) < 1e-9
    assert abs(sc["resto_eur"] - rm.rendita_netta(12.00, 2.00)) < 1e-9
    assert rep["rendita"]["fee"]["osservate_eur"] == 2.00
    assert abs(rep["netto"]["eur_mese"] - rm.netto_mensile(10.00, 31.00)) < 1e-9
    assert abs(rep["capitale"]["chiusura_eur"] - 960.00) < 1e-9


def test_report_senza_rate_nessun_numero_ipotizzato():
    rows = [
        {"nome": "banco_secco", "timestamp": "2026-09-01T00:00:00Z",
         "equity_eur": 900.0, "equity_funding_eur": 900.0,
         "saldi_funding": {"EUR": 900.0}},
        {"nome": "banco_secco", "timestamp": "2026-09-30T00:00:00Z",
         "equity_eur": 899.0, "equity_funding_eur": 899.0,
         "saldi_funding": {"EUR": 899.0}},
    ]
    rep = rm.genera_report(mese=MESE_A, banco_rows=rows, canary_stato=None,
                           carry_stato=None, review=None, sent_righe=None,
                           roadmap=None, scommessa=None, costi=None,
                           fino_iso=None, comando="test")
    assert rep["capitale"]["stato"] == "ok"  # il capitale c'è
    assert rep["rendita"]["totale"]["stato"] == "ok"  # delta calcolabile
    assert rep["rendita"]["totale"]["scomposizione"]["stato"] == "dati insufficienti"
    assert rep["rendita"]["earn"]["stato"] == "dati insufficienti"
    assert rep["netto"]["stato"] == "dati insufficienti"
    assert rep["costi"]["stato"] == "dati insufficienti"
    testo = rm.componi_testo(rep)
    assert "dati insufficienti" in testo
    assert "mai un numero ipotizzato" in testo


def test_report_mese_senza_dati_non_crasha():
    rep = rm.genera_report(mese=MESE_A, banco_rows=[], canary_stato=None,
                           carry_stato=None, review=None, sent_righe=None,
                           roadmap=None, scommessa=None, costi=None,
                           fino_iso=None, comando="test")
    assert rep["capitale"]["stato"] == "dati insufficienti"
    testo = rm.componi_testo(rep)
    assert testo.startswith(f"📊 Denaro — report mensile {MESE_A}")


def test_componi_testo_contiene_sezioni():
    rep = _report_mese(MESE_A, 8.50, REVIEW_A)
    testo = rm.componi_testo(rep)
    for sezione in ("Capitale", "Variazione", "Rendita Earn", "Costi fissi",
                    "Netto del mese", "Incidenti", "Decisioni richieste"):
        assert sezione in testo, f"sezione mancante: {sezione}"
    assert "-22.50" in testo
    assert "8.50" in testo


# ---------------------------------------------------------------- CLI end-to-end

def test_cli_end_to_end(tmp_path: Path):
    banco = tmp_path / "banco.jsonl"
    banco.write_text("\n".join(json.dumps(r) for r in banco_mese(MESE_A, 8.50)),
                     encoding="utf-8")
    costi = tmp_path / "costi.json"
    costi.write_text(costi_file([("VPS", 9.0), ("AI", 22.0)]), encoding="utf-8")
    review = tmp_path / "review.json"
    review.write_text(json.dumps(REVIEW_A), encoding="utf-8")
    sent = tmp_path / "sent.log"
    sent.write_text(f"{MESE_A}-04 01:30:05 | ⚠️ canary C1: exit 1\n", encoding="utf-8")
    roadmap = tmp_path / "ROADMAP.md"
    roadmap.write_text(ROADMAP_SINT, encoding="utf-8")
    json_out = tmp_path / "out.json"
    testo_out = tmp_path / "out.txt"
    rc = rm.main(["--mese", MESE_A, "--banco-file", str(banco),
                  "--costi-file", str(costi), "--fee-file", str(review),
                  "--sent-log", str(sent), "--roadmap", str(roadmap),
                  "--json-out", str(json_out), "--testo-out", str(testo_out)])
    assert rc == 0
    d = json.loads(json_out.read_text(encoding="utf-8"))
    assert d["tipo"] == "report_mensile"
    assert d["mese"] == MESE_A
    assert abs(d["rendita"]["totale"]["scomposizione"]["resto_eur"] - 8.50) < 1e-9
    assert d["netto"]["stato"] == "ok"
    assert d["hash_artefatti"]["banco_secco.jsonl"]
    assert d["comando"]  # comando esatto registrato
    t = testo_out.read_text(encoding="utf-8")
    assert "report mensile" in t
    assert d["incidenti"]["conteggio"] == 1


def test_finestra_mese_e_troncamento():
    assert rm._finestra("2026-02", None) == ("2026-02-01T00:00:00Z", "2026-02-28T23:59:59Z")
    assert rm._finestra("2024-02", None)[1] == "2024-02-29T23:59:59Z"  # bisestile
    assert rm._finestra("2026-10", "2026-10-16T23:59:59Z") == \
        ("2026-10-01T00:00:00Z", "2026-10-16T23:59:59Z")
