"""Test del PromotionArtifact: la chiave che sblocca il capitale di validazione.

Ogni garanzia fail-closed ha un test che la fa SCATTARE (non solo il caso felice).
"""
import json
from datetime import datetime, timedelta, timezone

import pytest

from money.esecuzione import promozione as PR


def _crea(**kw):
    base = dict(strategy_id="x1", nome="prova", capitale_max_eur=100.0,
                n_tentativi_ipotesi=24, n_tentativi_cumulativi=311838, dsr=0.97)
    base.update(kw)
    return PR.crea(**base)


def test_crea_valido_e_verifica_hash():
    a = _crea()
    assert a.verdetto == "PROMOSSA"
    assert a.hash.startswith("promo")
    a.valida()  # non solleva


def test_rifiuta_dsr_sotto_soglia_alla_creazione():
    with pytest.raises(PR.PromozioneInvalida):
        _crea(dsr=0.5)


def test_rifiuta_capitale_non_positivo():
    with pytest.raises(PR.PromozioneInvalida):
        _crea(capitale_max_eur=0.0)


def test_hash_manomesso_rifiutato():
    a = _crea()
    manomesso = PR.PromotionArtifact(**{**a.a_dict(), "capitale_max_eur": 9999.0})
    with pytest.raises(PR.PromozioneInvalida):
        manomesso.valida()


def test_scadenza_rifiutata():
    a = _crea(ttl_giorni=1)
    futuro = datetime.now(timezone.utc) + timedelta(days=2)
    with pytest.raises(PR.PromozioneInvalida):
        a.valida(adesso=futuro)


def test_tentativi_cumulativi_incoerenti_rifiutati():
    # il costruttore firma gia' passando da valida(): l'incoerenza e' rifiutata alla creazione
    with pytest.raises(PR.PromozioneInvalida):
        _crea(n_tentativi_ipotesi=1000, n_tentativi_cumulativi=10)


def test_scrittura_e_rilettura(tmp_path):
    a = _crea()
    p = PR.scrivi(a, tmp_path)
    assert p.exists()
    riletto = PR.leggi(p)
    assert riletto.hash == a.hash
    assert riletto.capitale_max_eur == 100.0


def test_leggi_file_manomesso_solleva(tmp_path):
    a = _crea()
    p = PR.scrivi(a, tmp_path)
    d = json.loads(p.read_text())
    d["dsr"] = 0.99  # cambia un byte: l'hash non regge piu'
    p.write_text(json.dumps(d))
    with pytest.raises(PR.PromozioneInvalida):
        PR.leggi(p)
