"""Guardia: i clOrdId del canary devono essere DETERMINISTICI, mai basati sull'orologio.

Un id costruito con `time.time()` cambia a ogni retry: dopo un timeout il retry invia
un ordine con id NUOVO invece di essere riconosciuto come duplicato -> posizione doppia.
Questo test fallisce se qualcuno reintroduce quel pattern.
"""
import hashlib
import importlib.util
import re
import sys
from pathlib import Path

CANARY = Path(__file__).resolve().parents[2] / "scripts" / "canary_carry.py"


def _carica_modulo():
    """Carica canary_carry per le funzioni pure, SENZA inquinare sys.modules.

    Il modulo fa `import ccxt` a livello top: c'e' un test (test_dati.py) che asserisce
    `"ccxt" not in sys.modules`. Ripristiniamo lo stato precedente dopo il load, cosi'
    questo file resta un import neutro.
    """
    prima = set(sys.modules)
    spec = importlib.util.spec_from_file_location("_canary_carry_probe", CANARY)
    assert spec and spec.loader, f"impossibile caricare {CANARY}"
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    finally:
        for nome in set(sys.modules) - prima:
            del sys.modules[nome]
    return mod


def test_cid_stabile_deterministico():
    mod = _carica_modulo()
    a = mod.cid_stabile("c1s", "DOGE/USDC|buy|110|2026-10-09")
    b = mod.cid_stabile("c1s", "DOGE/USDC|buy|110|2026-10-09")
    atteso = "c1s" + hashlib.sha256(b"DOGE/USDC|buy|110|2026-10-09").hexdigest()[:10]
    assert a == b == atteso, "lo stesso intento DEVE produrre lo stesso clOrdId"
    assert mod.cid_stabile("c1s", "X") != mod.cid_stabile("c1s", "Y")


def test_nessun_clordid_basato_su_orologio_nel_canary():
    sorgente = CANARY.read_text(encoding="utf-8")
    vietati = re.findall(r"clOrdId\"\s*:\s*\"[^\"]*\"\s*\+\s*str\(int\(time\.time", sorgente)
    vietati += re.findall(r"cid\s*=\s*\"c1[a-z]\"\s*\+\s*str\(int\(time\.time", sorgente)
    assert not vietati, f"clOrdId basato su orologio trovato: {vietati}"
