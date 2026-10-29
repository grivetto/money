"""Il codice vivo non deve usare ``assert`` come controllo di sicurezza.

Python -O elimina le istruzioni assert. Nel progetto questo sarebbe pericoloso perché
le invarianti della ricerca e dell'esecuzione devono restare attive anche quando il
processo viene avviato in modalità ottimizzata.

Scope (esteso 29/10/2026, audit Manus P0-3): src/ + scripts/ + ops/ + fabbrica/.
Esclusioni dichiarate: file `*.bak*` (backup storici, non eseguiti) e `legacy/`.
"""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCOPE = ("src", "scripts", "ops", "fabbrica")


def test_il_codice_vivo_non_contiene_assert_runtime():
    """Gli assert appartengono ai test, non ai moduli eseguiti con denaro o dati reali."""
    assert_nodes: list[str] = []
    for nome_dir in SCOPE:
        for path in sorted((ROOT / nome_dir).rglob("*.py")):
            if ".bak" in path.name:
                continue
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            for node in ast.walk(tree):
                if isinstance(node, ast.Assert):
                    assert_nodes.append(f"{path.relative_to(ROOT)}:{node.lineno}")

    assert assert_nodes == [], (
        "assert runtime trovati nel codice vivo; usare un controllo esplicito che resti attivo "
        f"con python -O: {assert_nodes}"
    )
