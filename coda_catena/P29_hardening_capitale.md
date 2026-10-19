# P29 — Hardening dei percorsi del capitale (fix audit 19/10) — VOCE DI MANUTENZIONE

STATO: PRE-REGISTRATA 2026-10-19 (Artù) — implementazione Merlino (REQ-MERL-20261019-013). Fuori dal conteggio tentativi (manutenzione/robustezza, non esperimento).
Repo: `grivetto/money` · fonte: `prove/audit_capitale_20261019/AUDIT.md` (37 difetti: 8 ALTA · 20 MEDIA · 9 BASSA) + verifica Artù `REVIEW_AUDIT.md` (8/8 ALTA confermati).

## Obiettivo
Chiudere i difetti **P1** (percorso carry + earn, quello toccato dal piano D3) con **test di regressione che RIPRODUCONO il difetto** (evidenza rosso→verde per ciascun fix). Niente refactoring, niente cambi di design oltre al fix puntuale.

## Fix richiesti (P1)

### carry_apri.py
1. **`funding_atteso` con `abs()` (righe 52-70)** — rimuovere `abs()`: il segno va conservato; un funding recente negativo deve arrivare al gate (che già rifiuta `funding_atteso <= 0`, `cancello_carry.py:125-127`). Test: mock con funding negativo → gate ok=False.
2. **Fill parziale gamba spot (righe 204-214)** — se `filled1 > 0`: liquidare il riempito (sell, attesa esito, evento con qty) oppure STOP esplicito con qty registrata; il messaggio «nessuna gamba scoperta» è vietato quando `filled1 > 0`. Test: mock fill parziale → unwind chiamato / evento con qty.
3. **Invio perp fallito (righe 216-229)** — unwind automatico dello spot riempito (stesso pattern del canary, `canary_carry.py:461-472`) con verifica dell'esito e stato/evento `gamba_scoperta` (qty + esito). Test: mock invio perp KO → unwind eseguito e registrato.
4. **Preflight (righe 154-163)** — aggiungere il controllo del **saldo spot del simbolo** (come C1, `canary_carry.py:297-302`): se il saldo spot atteso ≠ 0 → rifiuto (spot nudo residuo). Test: mock saldo spot > 0 → rifiuto.

### earn_move.py
5. **Ramo `except` (righe 596-604)** — prima di uscire, **lettura dei saldi** (savings/funding/trading) registrata nel log (nota con esito della lettura) + messaggio esplicito «NON rilanciare senza aver verificato i saldi». Test: eccezione simulata sulla POST → il log contiene la lettura e la nota.
6. **`attendi_funding` (righe 504-511)** — attesa a **delta** (`saldo >= saldo_iniziale + amt`), non a soglia assoluta. Test: funding già ≥ amt ma senza credito nuovo → non ritorna True subito (timeout).
7. **Attesa post-transfer nel ramo purchase (righe 573-581)** — usare il **poll esteso** (`RECONCILIA_POLL_N × RECONCILIA_INTERVAL_S`, come il redeem) al posto di 10×1s. Test: credito lento (oltre 10s, entro 120s) → il purchase procede.

## Vincoli
- Lavoro in `~/merlino-scratch/p29/`; zero write su `~/money`; zero ordini/chiavi; suite esistente verde.
- **Un fix per test**: ogni test deve fallire PRIMA del fix (documentare il rosso nel LEGGIMI) e passare dopo.
- NON toccare: dict `COPPIE`, soglie di `cancello_carry`, design del gate, comportamento dry-run.
- Difetti P2 (canary: reprice/close/unwind/lock) e P3 (MEDIA/BASSA residue) restano per REQ successive — NON in questa voce.

## Criteri di accettazione
1. Fix 1-7 + test di regressione (output `pytest -q` per esteso; evidenza rosso→verde per ciascun fix).
2. Suite completa verde (978 attesi + nuovi).
3. `LEGGIMI.md` con la mappa fix → test → comando.
4. Handoff `merlino/handoff/P29/` con `MANIFEST.sha256` + `READY` (ultimo).

## Verifica (riproducibile)
```bash
cd ~/money && .venv/bin/python -m pytest tests/ -k "carry_apri or earn_move" -q
```
+ riesame del diff da parte di Artù (fix puntuali, nessun cambio collaterale).

## Riferimenti
`prove/audit_capitale_20261019/AUDIT.md` · `prove/audit_capitale_20261019/REVIEW_AUDIT.md` · `scripts/carry_apri.py` · `scripts/earn_move.py` · `scripts/canary_carry.py` (pattern di riferimento) · REQ-MERL-20261019-013.
