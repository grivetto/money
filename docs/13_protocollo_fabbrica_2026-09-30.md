# Protocollo d'ufficio della Fabbrica (v1 — 30/09/2026)

Regole uniche per far lavorare insieme Hermes, gli operai (A0-MC2, A0-PC) e il peer DSH.
Ogni incarico e ogni consegna rispettano questo contratto: niente eccezioni non scritte.

## 1. Ruoli (chi fa cosa, chi NON fa cosa)

| Ruolo | Chi | Fa | NON fa |
|---|---|---|---|
| Direttore lavori | Hermes (mc2) | scrive i brief, dispatcha, RIESEGUE i test in review, integra con commit `[hermes]`, misura, aggiorna STATO | non delega la review; non integra senza test verdi |
| Operaio | A0-MC2, A0-PC | esegue UN brief alla volta, consegna artefatti + NOTE.md nel canale indicato | non tocca git; non tocca file fuori scope; non decide |
| Peer | DSH/Stella | consegne di pari livello su spec assegnate, con MANIFEST sha256 | non promuove nulla; non scrive in `src/` se non assegnato |
| Giudice advisory | JEV (TypeSafe) | valuta la qualita' delle spec (gate automatico in fabbrica) | non decide mai; mai enforcement; fail-open |

## 2. Il contratto di un task

Ogni incarico usa il template `docs/template_brief.md` con i 7 blocchi obbligatori:
obiettivo verificabile · contesto (repo+commit/path) · input/output · test che fallisce
senza l'implementazione · criteri di accettazione (checklist) · fuori scope · comando di verifica.

Controllo deterministico PRIMA dell'invio: `python scripts/spec_lint.py <brief> --strict`
(+ parere JEV advisory dal gate della fabbrica, quando disponibile).

## 3. Canale di consegna (uno per destinatario)

- **A0-MC2**: `/a0/usr/workdir/<task>/`
- **A0-PC**: `/a0/usr/workdir/ponte-dsh/` (cartella-ponte sulla macchina Windows)
- **DSH**: `hermes_bridge/dsh/handoff/<ID>/` con MANIFEST sha256 (formato: `<sha256>  <path_relativo>`)

Regola d'oro (da chiudere al piu' presto): scrittura atomica (tmp -> rename), manifest per
ultimo; il consumatore ritira solo con manifest presente e verificato. Mai consegnare segreti;
mai consegnare fuori dal canale indicato.

## 4. Ciclo di vita di un task

    queued -> dispatched -> delivered -> verified (test rieseguiti da Hermes) -> integrated (commit)
                                                                              -> rejected (con motivo scritto)

Registro: `fabbrica/state.json` + `STATO.md` (dal prossimo cantiere: job-store SQLite con lease e dedup).

## 5. Regole non negoziabili

- Test prima dei numeri; il cancello decide; produzione solo su promozione.
- Fail-closed per integrazione/test/manifest; fail-open SOLO per il parere JEV.
- Segreti mai nei brief, nelle consegne, nei log; zero-secret per A0-PC e DSH.
- Un task = un contratto; se non si puo' completare, NOTE.md dice dove ci si e' fermati e perche'.

## 6. Stato d'adozione (30/09/2026)

- [x] Protocollo v1 scritto (questo documento)
- [x] Lint strutturale (`scripts/spec_lint.py`) e gate JEV automatico in fabbrica
- [x] Kill-switch di fabbrica (file `fabbrica/STOP`) e metriche minime (`fabbrica/metrics.prom`)
- [ ] Job-store SQLite (lease/dedup) — prossimo cantiere (vedi `fabbrica/PIANO_HARDENING_2026-09-30.md`)
- [ ] Adozione del template sui prossimi dispatch (A0-MC2, A0-PC, DSH)
- [ ] Consegne atomiche con marker READY
