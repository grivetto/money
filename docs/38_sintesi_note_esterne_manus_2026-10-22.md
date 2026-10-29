# 38 — Sintesi note esterne: Manus AI «Analisi tecnica e proposta di migliorie» (2026-10-22)

Fonte: `~/Analisi tecnica e proposta di migliorie — 2026-10-22.docx` (owner, 29/10).
Audit al commit `5eef5706` su clone pulito. Review e integrazione: Artù, 29/10/2026.
Mappatura proposta → esito, con conferma del metodo dove il punto tocca capitale/misure.

## Stato per proposta (10/10 mappate)

| # | Proposta Manus | Esito | Verifica |
|---|---|---|---|
| P0-1 | CI verde, lint deterministico (F541) | **FATTO 29/10** | `ruff check .` → All checks passed (12 errori in `scripts/crosssec_mom_vol.py`: f-string annidate sintassi 3.12 che rompevano la CI 3.11; riscritte compatibili 3.11 + F541 rimosse); `compileall -q src scripts ops` ok |
| P0-2 | Bloccare deriva dipendenze | **FATTO (preesistente, verificato)** | `requirements-dev.lock` presente (22/10) e CI `ci.yml` con matrice Python 3.11/3.12/3.14 e `uv pip compile` documentato |
| P0-3 | Fail-closed sul percorso capitale | **PARZIALE → chiusa fase 1** | 4 assert operativi convertiti in `raise` fail-closed (`scripts/misura_p26.py`, `scripts/misura_p13.py`, `ops/alerts/watch_alerts.py`, `fabbrica/fabbrica.py`); `tests/test_no_runtime_assert.py` ESTESO a src+scripts+ops+fabbrica (esclusi `*.bak*`) → 1 passed. **Aperto (fase 2)**: audit `except Exception` per-modulo sul percorso capitale |
| P0-4 | README discrepanze numeriche | **FATTO 29/10** | Conteggi test 1.004/1.021 → 1.052 nei README ×4 (it/es/th/en), numero verificato con `pytest --collect-only`. Badge automatico: posticipato (serve lavoro CI, non blocca) |
| P1-5 | Coverage dominio finanziario | **APERTO-ADOTTATO** | pytest-cov + soglie separate per contabilità/costi/esecuzione/ricerca — in coda dopo P0 |
| P1-6 | Separare offline/network/live | **APERTO-ADOTTATO** | I test sono già offline; manca la classificazione formale per job e script operativi |
| P1-7 | Manifest per artefatti di ricerca | **APERTO-ADOTTATO (priorità alta)** | commit+seed+hash dati+parametri pre-registrati per ogni run: rafforza il metodo pre-registrazione. Da specificare come lane di manutenzione |
| P2-8 | legacy/ non eseguibile + retention | **APERTO-ADOTTATO** | legacy/ già fuori da CI; mancano README legacy e policy retention artefatti pesanti |
| P2-9 | TODO mark/index in carry_delta_neutral | **GIÀ RISOLTO fail-closed** | Verificato oggi: il modulo fa `raise NotImplementedError` senza dati mark/index reali — nessun fallback silenzioso (era già così al 22/10; il punto di Manus è superato in partenza) |
| P2-10 | Controlli statici (pip-audit, secret scan, type check) | **APERTO-ADOTTATO** | dopo la stabilizzazione; ordine dichiarato da Manus e condiviso: prima lint/riproducibilità, poi nuovi gate |

## Conferma del metodo (punti che toccano capitale/misure)

- P0-3: le guardie convertite sono sul percorso di MISURA (verdetti P13/P26) e di allarme
  (watch_alerts, fabbrica): con `python -O` non possono più sparire. La fase 2 (except Exception)
  seguirà la stessa regola: ogni cattura classificata fail_closed / degraded_read_only /
  best_effort_notification, con test.
- P2-9: nessun valore sostitutivo silenzioso nel percorso che produce un verdetto: confermato.

## Roadmap adottata (riordino rispetto a Manus)

1. **Questa settimana**: P1-7 manifest artefatti (spec) + P0-3 fase 2 (audit except, perimetro esecuzione/riconciliazione).
2. **Settimane 2-3**: P1-5 coverage + P1-6 classificazione job.
3. **Settimane 4-6**: P2-8 legacy/retention + P2-10 controlli statici.

I punti aperti vanno in `coda_catena/` come spec o in REQ a Merlino con criteri di accettazione,
non eseguiti a braccio.
