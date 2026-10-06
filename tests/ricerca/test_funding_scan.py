"""Test del modulo S2 funding_scan — PRIMA della misura (regola della catena).

Fixture sintetiche, nessuna rete. Copre: parsing/dedup/malformate (inclusi
valori non finiti), aggregazione giornaliera dagli ts REALI (non da un
numero assunto di eventi/giorno), convenzione dei segni (short riceve su
funding positivo), aritmetica del netto con i costi dichiarati, criteri di
lettura, anomalia del canary, persistenza, casi vuoti/corti, determinismo
dei report.
"""
import json
from datetime import datetime, timezone

import pytest

from money.costi import Tariffa, Venue
from money.ricerca import funding_scan as fs


def _tariffa() -> Tariffa:
    """Tariffa fissa e nota (come okx_eea_con_perp): i test non dipendono
    dalla tabella reale e l'aritmetica e' controllabile a mano."""
    return Tariffa(Venue.OKX_EEA, maker=0.0008, taker=0.0010, condizione="test")


def _ms(anno: int, mese: int, giorno: int, ora: int = 0) -> int:
    return int(datetime(anno, mese, giorno, ora, tzinfo=timezone.utc).timestamp() * 1000)


def _scrivi(p, righe) -> str:
    p.write_text("\n".join(json.dumps(r) if isinstance(r, dict) else r
                           for r in righe) + "\n", encoding="utf-8")
    return str(p)


def _serie(simbolo: str, ts, funding) -> fs.SerieFunding:
    return fs.SerieFunding(simbolo, tuple(ts), tuple(funding))


COSTO_CICLO = 0.0018 + 2 * 0.0004   # giro misto + 2 x slippage = 0,26%


# ---------- caricamento ----------

def test_carica_serie_ordina_dedup_e_malformate(tmp_path):
    p = tmp_path / "f.jsonl"
    righe = [
        {"simbolo": "BTC", "ts": 300, "funding": 0.0003},
        {"simbolo": "BTC", "ts": 100, "funding": 0.0001},
        {"simbolo": "BTC", "ts": 200, "funding": 0.0002},
        {"simbolo": "BTC", "ts": 200, "funding": 0.00025},  # dedup: vince l'ultima
        {"simbolo": "DOGE", "ts": 100, "funding": 0.0005},
        {"simbolo": "X"},                                     # malformata: manca ts
        "non-json",                                            # malformata
        {"simbolo": "NAN", "ts": 1, "funding": "NaN"},        # non finito: malformata
    ]
    serie, malformate, lette = fs.carica_serie(_scrivi(p, righe))
    assert lette == 8 and malformate == 3
    btc = serie["BTC"]
    assert btc.ts == (100, 200, 300)
    assert btc.funding == (0.0001, 0.00025, 0.0003)


def test_carica_serie_file_vuoto(tmp_path):
    p = tmp_path / "vuoto.jsonl"
    p.write_text("", encoding="utf-8")
    serie, malformate, lette = fs.carica_serie(str(p))
    assert serie == {} and malformate == 0 and lette == 0


# ---------- aggregazione giornaliera dagli ts reali ----------

def test_aggrega_giornaliera_dagli_ts_reali():
    d1 = _ms(2026, 6, 29)
    # tre eventi nello stesso giorno UTC (ogni 8h) + uno il giorno dopo
    ts = [d1, d1 + 8 * 3600 * 1000, d1 + 16 * 3600 * 1000, d1 + 24 * 3600 * 1000]
    s = _serie("T", ts, [0.0001, 0.0002, 0.0003, -0.0004])
    atteso = ((d1, 0.0006), (d1 + 86_400_000, -0.0004))
    ottenuto = fs.aggrega_giornaliera(s)
    assert len(ottenuto) == 2
    assert ottenuto[0][0] == atteso[0][0]
    assert ottenuto[0][1] == pytest.approx(atteso[0][1])
    assert ottenuto[1][0] == atteso[1][0]
    assert ottenuto[1][1] == pytest.approx(atteso[1][1])


def test_giorni_storia_e_n_giorni_con_buco():
    # 3 osservazioni sparse su 11 giorni di calendario: lo span conta, i
    # giorni con dati sono 3 (il criterio ">= 60 giorni" usa n_giorni).
    d = _ms(2026, 6, 29)
    ts = [d, d + 86_400_000, d + 10 * 86_400_000]
    st = fs.statistiche(_serie("T", ts, [0.0001, 0.0001, 0.0001]), tariffa=_tariffa())
    assert st.giorni_storia == 11
    assert st.n_giorni == 3


# ---------- segni, medie e netto ----------

def test_statistiche_segni_e_netto():
    d = _ms(2026, 6, 29)
    ts = [d, d + 86_400_000, d + 2 * 86_400_000]
    s = _serie("T", ts, [0.0010, 0.0010, -0.0005])
    st = fs.statistiche(s, tariffa=_tariffa(), cicli_all_anno=1)
    assert st.n == 3 and st.n_giorni == 3
    assert st.media_giornaliera == pytest.approx(0.0005)
    assert st.mediana_giornaliera == pytest.approx(0.0010)
    assert st.annuo_lordo == pytest.approx(0.0005 * 365)
    # short riceve su funding positivo: netto short = lordo - 1 ciclo
    assert st.netto_annualizzato_short == pytest.approx(0.0005 * 365 - COSTO_CICLO)
    assert st.netto_annualizzato_long == pytest.approx(-0.0005 * 365 - COSTO_CICLO)
    assert st.lato_favorevole == "short"
    assert st.netto_annualizzato == pytest.approx(0.0005 * 365 - COSTO_CICLO)
    # giorni positivi: 2 su 3 per lo short, 1 su 3 per il long
    assert st.frazione_giorni_positivi_short == pytest.approx(2 / 3)
    assert st.frazione_giorni_positivi_long == pytest.approx(1 / 3)


def test_lato_favorevole_long():
    d = _ms(2026, 6, 29)
    ts = [d + i * 86_400_000 for i in range(3)]
    s = _serie("T", ts, [-0.0005, -0.0005, -0.0005])
    st = fs.statistiche(s, tariffa=_tariffa())
    assert st.lato_favorevole == "long"
    assert st.frazione_giorni_positivi_short == pytest.approx(0.0)
    assert st.netto_annualizzato == pytest.approx(0.0005 * 365 - 12 * COSTO_CICLO)


def test_costi_default_vengono_da_money_costi():
    d = _ms(2026, 6, 29)
    st = fs.statistiche(_serie("T", (d,), (0.0001,)))
    # okx_eea_con_perp: giro misto 0,18% + 2 x slippage 0,04% = 0,26%
    assert st.costo_ciclo == pytest.approx(0.0026)
    assert st.cicli_all_anno == 12


def test_payback_giorni():
    d = _ms(2026, 6, 29)
    st = fs.statistiche(_serie("T", (d,), (0.0010,)), tariffa=_tariffa())
    assert st.payback_giorni == pytest.approx(COSTO_CICLO / 0.0010)
    st0 = fs.statistiche(_serie("Z", (d,), (0.0,)), tariffa=_tariffa())
    assert st0.payback_giorni is None


# ---------- persistenza ----------

def test_autocorr_persistenza():
    # lag-1 (money.statistica): serie monotone -> positiva, alternata -> negativa
    assert fs._autocorr([1.0, 2.0, 3.0, 4.0]) == pytest.approx(0.25)
    assert fs._autocorr([1.0, -1.0, 1.0, -1.0]) == pytest.approx(-0.75)
    assert fs._autocorr([0.0001]) is None
    assert fs._autocorr([]) is None


# ---------- anomalia del canary ----------

def test_anomalia_canary_singolo_giorno():
    d = _ms(2026, 6, 29)
    ts = [d + i * 86_400_000 for i in range(3)]
    s = _serie("T", ts, [0.0001, 0.006, 0.0001])  # giorno 2: 0,6% > 0,5%
    st = fs.statistiche(s, tariffa=_tariffa())
    assert st.anomalia
    assert st.max_giornaliero_assoluto == pytest.approx(0.006)
    assert st.giorno_max_ts == d + 86_400_000


def test_senza_anomalia_sotto_soglia():
    d = _ms(2026, 6, 29)
    ts = [d + i * 86_400_000 for i in range(3)]
    st = fs.statistiche(_serie("T", ts, [0.0001] * 3), tariffa=_tariffa())
    assert not st.anomalia


# ---------- criteri di lettura ----------

def _serie_60g(simbolo, valori):
    d = _ms(2026, 6, 29)
    ts = [d + i * 86_400_000 for i in range(60)]
    return _serie(simbolo, ts, tuple(valori))


def test_candidato_criteri_completi():
    # 60 giorni, salto di livello (persistenza > 0), carry netto positivo
    st = fs.statistiche(_serie_60g("A", [0.0002] * 30 + [0.0003] * 30),
                         tariffa=_tariffa())
    c = fs.criteri_di_lettura(st)
    assert c["persistenza_positiva"]
    assert c["storia_60g"]
    assert c["netto_positivo"]
    assert c["senza_anomalie"]
    assert c["candidato"]


def test_storia_insufficiente_59_giorni():
    d = _ms(2026, 6, 29)
    ts = [d + i * 86_400_000 for i in range(59)]
    st = fs.statistiche(_serie("B", ts, [0.0002] * 59), tariffa=_tariffa())
    assert not fs.criteri_di_lettura(st)["storia_60g"]
    assert not fs.criteri_di_lettura(st)["candidato"]


def test_netto_negativo_dopo_costi():
    # carry lordo positivo ma sotto il pedaggio annuo (12 cicli x 0,26%)
    st = fs.statistiche(_serie_60g("C", [0.00001] * 60), tariffa=_tariffa())
    c = fs.criteri_di_lettura(st)
    assert c["storia_60g"] and not c["netto_positivo"] and not c["candidato"]


def test_anomalia_esclude_dal_candidato():
    # carry solido ma con un giorno a 0,6%: "da verificare", non candidato
    # (il picco spezza anche la persistenza: non e' un edge misurabile)
    valori = [0.0002] * 30 + [0.006] + [0.0002] * 29
    st = fs.statistiche(_serie_60g("D", valori), tariffa=_tariffa())
    c = fs.criteri_di_lettura(st)
    assert c["storia_60g"] and c["netto_positivo"]
    assert not c["senza_anomalie"] and not c["candidato"]


def test_serie_costante_non_ha_persistenza_misurabile():
    # varianza nulla -> autocorrelazione 0.0: nessuna persistenza misurabile
    st = fs.statistiche(_serie_60g("E", [0.0002] * 60), tariffa=_tariffa())
    assert st.autocorr == 0.0
    assert not fs.criteri_di_lettura(st)["persistenza_positiva"]


# ---------- scansione end-to-end ----------

def test_scansione_classifica_candidati_e_anomalie(tmp_path):
    d = _ms(2026, 6, 29)
    righe = []
    for i in range(60):   # AAA: carry short solido e persistente
        righe.append({"simbolo": "AAA", "ts": d + i * 86_400_000,
                      "funding": 0.0002 if i < 30 else 0.0003})
    for i in range(60):   # BBB: carry troppo debole per il pedaggio
        righe.append({"simbolo": "BBB", "ts": d + i * 86_400_000,
                      "funding": 0.00001})
    righe.append({"simbolo": "CCC", "ts": d, "funding": 0.0002})
    righe.append({"simbolo": "CCC", "ts": d + 86_400_000, "funding": 0.006})
    risultato = fs.scansione(_scrivi(tmp_path / "f.jsonl", righe))
    meta = risultato["meta"]
    assert meta["n_simboli"] == 3 and meta["malformate"] == 0 and meta["righe"] == 122
    assert meta["n_esclusi_anomalia"] == 1
    # CCC (giorno a 0,6%) e' "da verificare": fuori dalla classifica
    classifica = [r["simbolo"] for r in risultato["classifica"]]
    assert classifica == ["AAA", "BBB"]
    assert classifica[0] == "AAA"           # miglior netto annualizzato
    assert "AAA" in risultato["candidati"]
    assert "BBB" not in risultato["candidati"]
    assert [x["simbolo"] for x in risultato["da_verificare"]] == ["CCC"]
    assert risultato["da_verificare"][0]["giorno"] == _iso_local(d + 86_400_000)
    # AAA: 60 giorni, media giornaliera 0,025%, netto annuo positivo
    aaa = risultato["per_simbolo"]["AAA"]
    assert aaa["n_giorni"] == 60
    assert aaa["media_giornaliera"] == pytest.approx(0.00025)
    assert aaa["netto_annualizzato"] == pytest.approx(
        0.00025 * 365 - 12 * COSTO_CICLO)
    assert aaa["criteri"]["candidato"]


def _iso_local(giorno_ms: int) -> str:
    return datetime.fromtimestamp(giorno_ms / 1000,
                                  tz=timezone.utc).date().isoformat()


def test_scansione_file_vuoto(tmp_path):
    p = tmp_path / "vuoto.jsonl"
    p.write_text("", encoding="utf-8")
    risultato = fs.scansione(str(p))
    assert risultato["meta"]["n_simboli"] == 0
    testo = fs.report_testo(risultato)
    assert "NON promozione" in testo


# ---------- report ----------

def test_report_deterministici_e_json_valido(tmp_path):
    d = _ms(2026, 6, 29)
    righe = []
    for sim, base in (("AAA", 0.0002), ("BBB", -0.0001)):
        for i in range(60):
            righe.append({"simbolo": sim, "ts": d + i * 86_400_000,
                          "funding": base + (0.00005 if i % 3 else -0.0002)})
    percorso = _scrivi(tmp_path / "f.jsonl", righe)
    r1 = fs.scansione(percorso)
    r2 = fs.scansione(percorso)
    assert fs.report_testo(r1) == fs.report_testo(r2)
    assert fs.report_json(r1) == fs.report_json(r2)
    dati = json.loads(fs.report_json(r1))
    assert dati["meta"]["n_simboli"] == 2
    assert set(dati["per_simbolo"]) == {"AAA", "BBB"}
    assert "criteri" in dati["per_simbolo"]["AAA"]
    assert [r["simbolo"] for r in dati["classifica"]][0] == "AAA"
    testo = fs.report_testo(r1)
    assert "S2" in testo and "CANDIDATI" in testo and "DA VERIFICARE" in testo
