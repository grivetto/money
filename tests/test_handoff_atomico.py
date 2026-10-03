"""Test del protocollo di consegna atomico (lane DSH-win PROTCON, 03/10/2026).

Il modulo vive in fabbrica/handoff_atomico.py, fuori dal package money: si carica per
percorso con importlib (stesso pattern di test_fabbrica_jobs.py). Fixtures locali
(cartella), nessuna rete, nessuna chiave, nessun orologio reale (i timestamp sono iniettati).
"""
from __future__ import annotations

import importlib.util
import json
import os
import threading
from pathlib import Path

import pytest

_RADICE = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location(
    "fabbrica_handoff_atomico", _RADICE / "fabbrica" / "handoff_atomico.py")
assert _SPEC is not None and _SPEC.loader is not None
_mod = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_mod)
ha = _mod


def _pacchetto(cartella):
    d = cartella / "DSHW-EXAMPLE"
    (d / "fabbrica").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "fabbrica" / "modulo.py").write_text("print('ciao')\n", encoding="utf-8")
    (d / "tests" / "test_modulo.py").write_text("# test\n", encoding="utf-8")
    (d / "NOTE.md").write_text("# note\n", encoding="utf-8")
    return d


def _sigillato(cartella, sender="DSH-win"):
    d = _pacchetto(cartella)
    ha.seal(d, sender, now="2026-10-03T12:00:00Z")
    return d


# ---------------------------------------------------------------------------
# 1-3 scrittura atomica e manifest
# ---------------------------------------------------------------------------
def test_scrittura_atomica_sostituisce_e_non_lascia_tmp(cartella):
    p = cartella / "x.bin"
    ha.atomic_write_bytes(p, b"uno")
    ha.atomic_write_bytes(p, b"due")
    assert p.read_bytes() == b"due"
    assert [f.name for f in cartella.iterdir() if ".tmp-" in f.name] == []


def test_manifest_formato_sha256sum(cartella):
    d = _pacchetto(cartella)
    voci = ha.build_manifest(d)
    assert set(voci) == {"NOTE.md", "fabbrica/modulo.py", "tests/test_modulo.py"}
    righe = (d / "MANIFEST.sha256").read_text(encoding="utf-8").splitlines()
    assert len(righe) == 3
    for riga in righe:
        digest, rel = riga.split("  ", 1)          # due spazi: formato sha256sum -c
        assert len(digest) == 64 and rel in voci
        assert digest == voci[rel]
    assert "MANIFEST.sha256" not in voci


def test_manifest_esclude_i_file_di_protocollo(cartella):
    d = _sigillato(cartella)
    voci = ha.read_manifest(d)
    assert "MANIFEST.sha256" not in voci and "READY" not in voci
    assert set(voci) == {"NOTE.md", "fabbrica/modulo.py", "tests/test_modulo.py"}


def test_pycache_ignorata(cartella):
    d = _pacchetto(cartella)
    (d / "fabbrica" / "__pycache__").mkdir()
    (d / "fabbrica" / "__pycache__" / "modulo.cpython-312.pyc").write_bytes(b"\x00\x01")
    ha.seal(d, "DSH-win")
    voci = ha.read_manifest(d)
    assert all("__pycache__" not in v for v in voci)
    assert ha.verify(d)["key"] == ha.chiave_consegna(d)


def test_read_manifest_assente_e_malformato(cartella):
    with pytest.raises(ha.ManifestError):
        ha.read_manifest(cartella)
    d = _pacchetto(cartella)
    (d / "MANIFEST.sha256").write_text("non-un-hash  file\n", encoding="utf-8")
    with pytest.raises(ha.ManifestError):
        ha.read_manifest(d)


# ---------------------------------------------------------------------------
# 4-9 verifica fail-closed
# ---------------------------------------------------------------------------
def test_verify_ok(cartella):
    d = _sigillato(cartella)
    esito = ha.verify(d)
    assert esito["key"] == ha.chiave_consegna(d)
    assert len(esito["voci"]) == 3


def test_verify_file_mancante(cartella):
    d = _sigillato(cartella)
    (d / "NOTE.md").unlink()
    with pytest.raises(ha.ManifestError) as e:
        ha.verify(d)
    assert "manca: NOTE.md" in str(e.value)


def test_verify_hash_diverso(cartella):
    d = _sigillato(cartella)
    (d / "fabbrica" / "modulo.py").write_text("print('cambiato')\n", encoding="utf-8")
    with pytest.raises(ha.ManifestError) as e:
        ha.verify(d)
    assert "hash diverso" in str(e.value)


def test_verify_file_non_dichiarato(cartella):
    d = _sigillato(cartella)
    (d / "INTRUSO.md").write_text("x", encoding="utf-8")
    with pytest.raises(ha.ManifestError) as e:
        ha.verify(d)
    assert "non dichiarato" in str(e.value)
    # strict=False non guarda i file in piu': il manifest torna
    assert ha.verify(d, strict=False)["key"] == ha.chiave_consegna(d)


def test_verify_percorso_non_sicuro(cartella):
    d = _pacchetto(cartella)
    ha.build_manifest(d)
    (d / "MANIFEST.sha256").write_text("a" * 64 + "  ../fuori.txt\n", encoding="utf-8")
    with pytest.raises(ha.ManifestError) as e:
        ha.verify_manifest(d)
    assert "non sicuro" in str(e.value)


def test_verify_symlink_rifiutato(cartella):
    d = _sigillato(cartella)
    link = d / "fabbrica" / "link.py"
    try:
        os.symlink(d / "fabbrica" / "modulo.py", link)
    except (OSError, NotImplementedError):
        pytest.skip("symlink non creabili in questo ambiente")
    ha.build_manifest(d)
    with pytest.raises(ha.ManifestError) as e:
        ha.verify_manifest(d)
    assert "symlink" in str(e.value)


def test_verify_raccoglie_tutti_i_problemi(cartella):
    d = _sigillato(cartella)
    (d / "NOTE.md").unlink()
    (d / "fabbrica" / "modulo.py").write_text("x\n", encoding="utf-8")
    (d / "INTRUSO.md").write_text("x", encoding="utf-8")
    with pytest.raises(ha.ManifestError) as e:
        ha.verify(d)
    msg = str(e.value)
    assert "3 problemi" in msg and "manca" in msg and "non dichiarato" in msg


# ---------------------------------------------------------------------------
# 10-14 sigillo: READY per ultimo, chiave, risigillo
# ---------------------------------------------------------------------------
def test_ready_scritto_per_ultimo(cartella):
    d = _pacchetto(cartella)
    payload = ha.seal(d, "DSH-win", now="2026-10-03T12:00:00Z")
    assert (d / "READY").exists() and (d / "MANIFEST.sha256").exists()
    ready = json.loads((d / "READY").read_text(encoding="utf-8"))
    assert ready["key"] == ha.chiave_consegna(d) == payload["key"]
    assert ready["protocollo"] == ha.PROTOCOL
    assert ready["sender"] == "DSH-win" and ready["files"] == 3
    assert ready["created_at"] == "2026-10-03T12:00:00Z"


def test_seal_non_risigilla_senza_force(cartella):
    d = _sigillato(cartella)
    with pytest.raises(ha.HandoffError):
        ha.seal(d, "DSH-win")


def test_seal_force_risigilla(cartella):
    d = _sigillato(cartella)
    (d / "NOTE.md").write_text("# note 2\n", encoding="utf-8")
    nuovo = ha.seal(d, "DSH-win", force=True)
    assert nuovo["key"] == ha.chiave_consegna(d)
    assert ha.verify(d)["key"] == nuovo["key"]


def test_chiave_cambia_col_contenuto(cartella):
    d = _sigillato(cartella)
    k1 = ha.chiave_consegna(d)
    ha.seal(d, "DSH-win", force=True)
    assert ha.chiave_consegna(d) == k1            # stesso contenuto -> stessa chiave
    (d / "NOTE.md").write_text("x\n", encoding="utf-8")
    ha.seal(d, "DSH-win", force=True)
    assert ha.chiave_consegna(d) != k1            # un byte diverso -> altra consegna


def test_ready_assente(cartella):
    with pytest.raises(ha.NotReadyError):
        ha.read_ready(cartella / "vuoto")


# ---------------------------------------------------------------------------
# 15-18 presa atomica
# ---------------------------------------------------------------------------
def test_claim_esclusivo(cartella):
    d = _sigillato(cartella)
    info = ha.claim(d, "hermes")
    assert not (d / "READY").exists()
    assert (d / "CLAIMED-hermes").exists()
    assert info["key"] == ha.chiave_consegna(d)
    with pytest.raises(ha.AlreadyClaimedError):
        ha.claim(d, "a0")
    with pytest.raises(ha.AlreadyClaimedError):
        ha.claim(d, "hermes")                     # idempotente per nome


@pytest.mark.parametrize("nome", ["", "a/b", "..", "x" * 65, "a b", "a\\b"])
def test_claim_nome_non_valido(cartella, nome):
    with pytest.raises(ha.HandoffError):
        ha.claim(cartella, nome)


def test_claim_prima_del_sigillo(cartella):
    d = _pacchetto(cartella)
    with pytest.raises(ha.NotReadyError):
        ha.claim(d, "hermes")


def test_verify_dopo_il_claim_non_ha_piu_ready(cartella):
    d = _sigillato(cartella)
    ha.claim(d, "hermes")
    with pytest.raises(ha.NotReadyError):
        ha.verify(d)


def test_claim_concorrenza_un_solo_vincitore(cartella):
    d = _sigillato(cartella)
    esiti = []
    barriera = threading.Barrier(8)

    def racer(i):
        barriera.wait()
        try:
            ha.claim(d, "c%d" % i)
            esiti.append("ok")
        except ha.AlreadyClaimedError:
            esiti.append("perso")

    fili = [threading.Thread(target=racer, args=(i,)) for i in range(8)]
    for t in fili:
        t.start()
    for t in fili:
        t.join()
    assert esiti.count("ok") == 1 and esiti.count("perso") == 7


# ---------------------------------------------------------------------------
# 19-22 registro di idempotenza
# ---------------------------------------------------------------------------
def test_ledger_done_e_inflight(cartella):
    led = ha.Ledger(cartella / "ledger")
    assert led.begin("abc") is True
    assert led.begin("abc") is False
    assert led.has_inflight("abc") and not led.is_done("abc")
    led.abort("abc")
    assert led.begin("abc") is True
    led.commit("abc", {"x": 1})
    assert led.is_done("abc") and not led.has_inflight("abc")
    assert led.done_keys() == ["abc"]
    with pytest.raises(ha.HandoffError):
        led.begin("abc")
    assert led.stats() == {"done": 1, "inflight": 0}


def test_ledger_begin_concorrenza_un_solo_vincitore(cartella):
    led = ha.Ledger(cartella / "ledger")
    esiti = []
    barriera = threading.Barrier(8)

    def racer():
        barriera.wait()
        esiti.append(led.begin("k"))

    fili = [threading.Thread(target=racer) for _ in range(8)]
    for t in fili:
        t.start()
    for t in fili:
        t.join()
    assert esiti.count(True) == 1 and esiti.count(False) == 7


# ---------------------------------------------------------------------------
# 23-28 integrazione al piu' una volta
# ---------------------------------------------------------------------------
def test_integrate_once_integra_e_non_raddoppia(cartella):
    d = _sigillato(cartella)
    led = cartella / "ledger"
    chiamate = []
    r1 = ha.integrate_once(d, led, "hermes", lambda root: chiamate.append(str(root)) or "ok")
    assert r1["status"] == "integrated" and len(chiamate) == 1
    assert (d / "CLAIMED-hermes").exists()
    # stessa consegna, stesso contenuto: nuova READY, chiave invariata -> duplicate
    ha.seal(d, "DSH-win", force=True)
    r2 = ha.integrate_once(d, led, "hermes", lambda root: chiamate.append(str(root)) or "ok")
    assert r2["status"] == "duplicate"
    assert len(chiamate) == 1                     # NON richiamata
    assert ha.Ledger(led).stats() == {"done": 1, "inflight": 0}


def test_integrate_once_fallimento_libera_inflight(cartella):
    d = _sigillato(cartella)
    led = cartella / "ledger"

    def esplode(root):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError):
        ha.integrate_once(d, led, "hermes", esplode)
    key = ha.chiave_consegna(d)
    registro = ha.Ledger(led)
    assert not registro.is_done(key) and not registro.has_inflight(key)   # riprovabile
    ha.seal(d, "DSH-win", force=True)
    r = ha.integrate_once(d, led, "hermes2", lambda root: "ok")
    assert r["status"] == "integrated"


def test_integrate_once_non_integra_se_corrotto(cartella):
    d = _sigillato(cartella)
    led = cartella / "ledger"
    (d / "fabbrica" / "modulo.py").write_text("manomesso\n", encoding="utf-8")
    chiamate = []
    with pytest.raises(ha.ManifestError):
        ha.integrate_once(d, led, "hermes", lambda root: chiamate.append(1))
    assert chiamate == []
    assert ha.Ledger(led).stats() == {"done": 0, "inflight": 0}


def test_integrate_once_inflight_concorrente(cartella):
    d = _sigillato(cartella)
    led = cartella / "ledger"
    ha.Ledger(led).begin(ha.chiave_consegna(d))
    chiamate = []
    r = ha.integrate_once(d, led, "hermes", lambda root: chiamate.append(1))
    assert r["status"] == "in-flight" and chiamate == []


def test_integrate_once_already_claimed(cartella):
    d = _sigillato(cartella)
    led = cartella / "ledger"
    ha.claim(d, "altro")
    chiamate = []
    r = ha.integrate_once(d, led, "hermes", lambda root: chiamate.append(1))
    assert r["status"] == "already-claimed" and chiamate == []


def test_integrate_once_secondo_ricevente_dopo_il_primo(cartella):
    d = _sigillato(cartella)
    led = cartella / "ledger"
    chiamate = []
    assert ha.integrate_once(d, led, "hermes", lambda root: chiamate.append(1))["status"] == "integrated"
    # un secondo ricevente sulla stessa cartella: READY non c'e' piu' -> niente seconda integrazione
    r = ha.integrate_once(d, led, "a0", lambda root: chiamate.append(1))
    assert r["status"] in ("already-claimed", "duplicate") and len(chiamate) == 1


# ---------------------------------------------------------------------------
# 29 CLI e stato
# ---------------------------------------------------------------------------
def test_status_e_cli(cartella):
    d = _sigillato(cartella)
    s = ha.stato(d)
    assert s["ready"] is True and s["verifica"] == "OK" and s["key"] == ha.chiave_consegna(d)
    assert s["files"] == 3 and s["claimed_by"] == []
    assert ha.main(["verify", str(d)]) == 0
    assert ha.main(["key", str(d)]) == 0
    assert ha.main(["status", str(d)]) == 0
    assert ha.main(["verify", str(cartella / "assente")]) == 2
