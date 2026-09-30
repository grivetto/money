"""Test del lint strutturale spec (deterministico, nessuna rete)."""
from __future__ import annotations

from money.spec_lint import lint_text, missing

BRIEF_OK = """# Task ID: abc-123
## 1. Obiettivo
Implementare il modulo X affinche' il comando Y restituisca Z.

## 2. Contesto autonomo
- repository: money @ commit abc1234
- percorso: /home/sergio/money
- vincoli: solo stdlib

## 3. Fuori scope
- non modificare src/money/rischio.py

## 4. Specifica input/output
Input: dict {"serie": [float, ...]}
Output: tupla (lo, hi)
Errori: ValueError su serie vuota

## 5. Test prima del codice
- test_base: data una serie, atteso (lo, hi) corretti; assert lo < hi
Il test deve fallire prima dell'implementazione.

## 6. Criteri di accettazione
- [ ] test nuovi verdi
- [ ] suite esistente verde

## 7. Procedura di verifica
```bash
pytest tests/test_x.py -q
```
"""


def test_brief_completo_tutto_ok() -> None:
    checks = lint_text(BRIEF_OK)
    assert missing(checks) == []


def test_mancano_io_e_fuori_scope() -> None:
    checks = lint_text("Obiettivo: fare la cosa. Test con atteso 1. Criteri di accettazione ok.")
    m = missing(checks)
    assert "input_output" in m
    assert "fuori_scope" in m


def test_sha_richiesto_per_repo_commit() -> None:
    senza = lint_text("obiettivo x. repository money senza sha. input output")
    assert "repo_commit" in missing(senza)
    con = lint_text("obiettivo x. repository money, commit deadbeef. input output")
    assert "repo_commit" not in missing(con)


def test_checklist_conta_come_criteri() -> None:
    testo = "obiettivo. input output. - [ ] uno\n- [ ] due"
    assert "criteri" not in missing(lint_text(testo))


def test_testo_vuoto_non_crasha() -> None:
    checks = lint_text("")
    assert len(checks) == 7
    assert len(missing(checks)) >= 5
