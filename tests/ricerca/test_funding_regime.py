"""Test del modulo P12 funding_regime — PRIMA della misura (regola della catena).

Copre: parsing/dedup/malformate, anti-look-ahead della RULE (decisioni solo su eventi <= t-1),
aritmetica del netto, determinismo del bootstrap, stabilita' (rho), casi vuoti/corti.
"""
import json

import pytest

from money.ricerca import funding_regime as fr


# ---------- parsing ----------

def test_carica_serie_ordina_dedup_conta_malformate(tmp_path):
    p = tmp_path / "f.jsonl"
    righe = [
        {"simbolo": "BTC", "ts": 300, "funding": 0.0003},
        {"simbolo": "BTC", "ts": 100, "funding": 0.0001},
        {"simbolo": "BTC", "ts": 200, "funding": 0.0002},
        {"simbolo": "BTC", "ts": 200, "funding": 0.00025},  # dedup: vince l'ultima
        {"simbolo": "DOGE", "ts": 100, "funding": 0.0005},
        {"simbolo": "X"},                                     # malformata
        "non-json",                                           # malformata
    ]
    p.write_text("\n".join(json.dumps(r) if isinstance(r, dict) else r for r in righe), encoding="utf-8")
    serie, malformate = fr.carica_serie(str(p))
    assert malformate == 2
    btc = serie["BTC"]
    assert btc.ts == (100, 200, 300)
    assert btc.funding == (0.0001, 0.00025, 0.0003)


def test_carica_serie_file_vuoto(tmp_path):
    p = tmp_path / "vuoto.jsonl"
    p.write_text("", encoding="utf-8")
    serie, malformate = fr.carica_serie(str(p))
    assert serie == {} and malformate == 0


# ---------- persistenza ----------

def test_p_media3_anti_lookahead_a_mano():
    v = [0.001, -0.001, 0.001, 0.002, -0.002, 0.003]
    # t=3: media di (v2,v1,v0)=+0.00033 -> v3=+0.002 ok
    # t=4: media di (v3,v2,v1)=+0.00067 -> v4=-0.002 no
    # t=5: media di (v4,v3,v2)=+0.00033 -> v5=+0.003 ok
    assert fr.p_media3_positiva(v) == pytest.approx(2 / 3)
    # p_corrente: coppie (t-1 -> t) con t-1 > 0: t=1 (ok) e t=2 (no, next negativo) -> 1/2
    assert fr.p_corrente_positiva([0.001, 0.001, -0.001, 0.001]) == pytest.approx(1 / 2)


def test_p_media3_serie_corta():
    assert fr.p_media3_positiva([0.001, 0.002, 0.003]) is None
    assert fr.p_corrente_positiva([0.001]) is None


# ---------- RULE: meccanica e anti-look-ahead ----------

def test_regola_meccanica_a_mano():
    v = (0.0001, 0.0001, 0.0001, 0.0001, -0.001, 0.0001, 0.0001, 0.0001, 0.0001)
    s = fr.SerieSimbolo("T", tuple(range(len(v))), v)
    ru = fr.flusso_regola(s)
    ao = fr.flusso_always_on(s)
    # sempre-on: 8 x 1e-4 - 1e-3 = -0.0002
    assert ao.flusso == pytest.approx(-0.0002)
    # regola: entra a t=3 (media3>0), cattura v3=+1e-4, v4=-1e-3 (primo negativo:
    # l'uscita scatta SOLO da t=5, quindi il negativo viene subito), esce prima di t=5;
    # rientra a t=8 (media3(v7,v6,v5)>0), cattura v8=+1e-4 -> 1e-4 - 1e-3 + 1e-4 = -8e-4
    assert ru.flusso == pytest.approx(-0.0008)
    assert ru.eventi_catturati == 3
    assert ru.episodi == 2


def test_regola_non_usa_il_futuro():
    """Perturbare l'evento t non deve cambiare la decisione presa all'evento t."""
    base = [0.0002] * 10 + [0.0001] * 10
    s1 = fr.SerieSimbolo("A", tuple(range(20)), tuple(base))
    # stessa serie ma con un evento negativo al posto t=15 (dopo un lungo tratto positivo)
    mod = list(base)
    mod[15] = -0.01
    s2 = fr.SerieSimbolo("B", tuple(range(20)), tuple(mod))
    ru1 = fr.flusso_regola(s1)
    ru2 = fr.flusso_regola(s2)
    # s1: entra a t=3, nessun negativo -> cattura t=3..19 (17 eventi, 1 episodio)
    assert ru1.episodi == 1 and ru1.eventi_catturati == 17
    # s2: entra a t=3, cattura t=3..15 (il negativo di t=15 viene subito: l'uscita scatta
    # solo da t=16, guardando l'evento t-1); rientra a t=19 -> episodi 2, 14 catture.
    assert ru2.episodi == 2
    assert ru2.eventi_catturati == 14
    assert ru2.negativi_catturati == pytest.approx(-0.01)
    # 7 x 2e-4 (t3..9) + 5 x 1e-4 (t10..14) - 0.01 (t15) + 1e-4 (t19)
    assert ru2.flusso == pytest.approx(7 * 0.0002 + 5 * 0.0001 - 0.01 + 0.0001)


def test_regola_su_tutto_positivo_quota_warmup():
    v = (0.0001,) * 30
    s = fr.SerieSimbolo("T", tuple(range(30)), v)
    ru = fr.flusso_regola(s)
    assert ru.episodi == 1
    assert ru.eventi_catturati == 27  # salta il warmup dei primi 3 eventi
    assert ru.flusso / fr.flusso_always_on(s).flusso == pytest.approx(27 / 30)


def test_dd_flusso():
    v = (0.001, 0.001, -0.003, 0.001)
    s = fr.SerieSimbolo("T", tuple(range(4)), v)
    ao = fr.flusso_always_on(s)
    # cumulata: 0.001, 0.002, -0.001, 0.0 -> dd = 0.002 - (-0.001) = 0.003
    assert ao.dd_flusso == pytest.approx(0.003)


# ---------- economia ----------

def test_netto_esatto():
    x = fr.netto(0.0003, 30, 0.0040)
    assert abs(x - 0.005) < 1e-15
    assert fr.netto(0.0001, 7, 0.0040) == pytest.approx(0.0001 * 7 - 0.0040)


# ---------- bootstrap ----------

def test_bootstrap_deterministico():
    v = [0.0001 * ((-1) ** i) for i in range(120)]
    a = fr.bootstrap_ic90(v, fr._media_di_lista)
    b = fr.bootstrap_ic90(v, fr._media_di_lista)
    assert a == b
    assert a is not None and a[0] <= a[1]


def test_bootstrap_serie_corta():
    assert fr.bootstrap_ic90([0.0001] * 5, fr._media_di_lista) is None


# ---------- stabilita' ----------

def _sim(nome, valore, n=60):
    return fr.SerieSimbolo(nome, tuple(range(n)), (valore,) * n)


def test_stabilita_rho_positiva():
    serie = {"A": _sim("A", 0.0001), "B": _sim("B", 0.0002), "C": _sim("C", 0.0003)}
    st = fr.stabilita(serie)
    assert st["rho"] == pytest.approx(1.0)
    assert st["inversioni"] == 0


def test_stabilita_rho_negativa_con_inversioni():
    # prima meta': A < B < C; seconda meta': A > B > C -> rho = -1, 0 inversioni di segno
    a = (0.0001,) * 30 + (0.0003,) * 30
    b = (0.0002,) * 30 + (0.0002,) * 30
    c = (0.0003,) * 30 + (0.0001,) * 30
    serie = {
        "A": fr.SerieSimbolo("A", tuple(range(60)), a),
        "B": fr.SerieSimbolo("B", tuple(range(60)), b),
        "C": fr.SerieSimbolo("C", tuple(range(60)), c),
    }
    st = fr.stabilita(serie)
    assert st["rho"] == pytest.approx(-1.0)
    assert st["inversioni"] == 0


# ---------- casi limite e report ----------

def test_valuta_su_vuoto_non_esplode():
    r = fr.valuta({})
    assert r["esito"] == "insufficiente"
    testo = fr.report_testo(r, 0)
    assert "P12" in testo and "ESITO" in testo


def test_report_e_json_deterministici(tmp_path):
    p = tmp_path / "f.jsonl"
    righe = []
    for sim, base in (("BTC", 0.0002), ("ETH", -0.0001)):
        for i in range(80):
            righe.append({"simbolo": sim, "ts": 1000 + i, "funding": base + (0.00005 if i % 3 else -0.0002)})
    p.write_text("\n".join(json.dumps(r) for r in righe), encoding="utf-8")
    serie, mal = fr.carica_serie(str(p))
    r1 = fr.valuta(serie)
    r2 = fr.valuta(serie)
    t1, t2 = fr.report_testo(r1, mal), fr.report_testo(r2, mal)
    assert t1 == t2
    js = fr.report_json(r1, mal)
    dati = json.loads(js)  # JSON valido
    assert "esito" in dati and "statistiche" in dati
    assert dati["statistiche"]["BTC"]["n"] == 80
