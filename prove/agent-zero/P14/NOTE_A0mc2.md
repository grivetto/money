# P14 — Momentum Cross-Sectional (Broad Universe)

## File prodotti

| File | Descrizione |
|------|-------------|
| `p14/misura_p14.py` | Misura P14 (adattata da P10): lazy imports, griglia 8 varianti, universo ampio, riga riferimento P10 non selezionabile, stress slippage x2 |
| `p14/test_misura_p14.py` | Test unitari puri (nessuna dipendenza `money`, nessuna rete) |
| `p14/BRIEF-P14.md` | Brief originale del task |
| `p14/refs/` | File reference originali (misura_p10.py, misura_p5.py, universo.py, momentum_cross.py) |
| `p14/prove/` | Cartella artefatti (P14_momentum_universo.txt, P14_momentum_universo.json) — generati da Hermes sul repo canonico |

## Verifica sintassi

```
cd /a0/usr/workdir/p14
python -m py_compile misura_p14.py  && echo OK
# → misure_p14.py: SYNTAX OK
python -m py_compile test_misura_p14.py && echo OK
# → test_misura_p14.py: SYNTAX OK
```

## Esecuzione test (nel container)

Comando:
```
cd /a0/usr/workdir/p14 && python -B test_misura_p14.py
```

Output reale:
```
.............
----------------------------------------------------------------------
Ran 13 tests in 0.002s

OK
```

13/13 test superati nel container senza pacchetto `money` e senza rete.

---
*Nota: la misura vera con scaricamento dati e universi reali viene eseguita da Hermes sul repo canonico.*