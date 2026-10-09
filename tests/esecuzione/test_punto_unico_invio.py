"""Guardia: un SOLO punto di invio ordini in tutto il repository.

Sprint P0 (docs/26 §5, «Suggerimenti per Hermes» §5): il coordinatore è l'unico
componente autorizzato a usare `create_order`. Se un altro file reintroduce la chiamata
diretta, il criterio "un solo percorso live" è violato: questo test lo blocca.
"""
from pathlib import Path

RADICE = Path(__file__).resolve().parents[2]
#: unici file dove la stringa `create_order(` puo' comparire
AMMESSI = {"src/money/esecuzione/invio.py"}


def _file_python():
    for base in ("src", "scripts", "ops"):
        for p in (RADICE / base).rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


def test_un_solo_punto_create_order():
    import re
    #: solo CHIAMATE reali (`.create_order(`), non le stringhe di pattern nei verificatori
    chiamata = re.compile(r"\.create_order\(")
    colpevoli = []
    for p in _file_python():
        rel = p.relative_to(RADICE).as_posix()
        if rel in AMMESSI:
            continue
        if chiamata.search(p.read_text(encoding="utf-8")):
            colpevoli.append(rel)
    assert not colpevoli, (
        "create_order chiamato fuori dal punto unico di invio "
        f"(money/esecuzione/invio.py): {colpevoli}")


def test_il_punto_unico_esiste_e_chiama_create_order():
    p = RADICE / "src/money/esecuzione/invio.py"
    assert p.exists(), "manca il punto unico di invio (money/esecuzione/invio.py)"
    assert "create_order(" in p.read_text(encoding="utf-8")
