# P30 — Hardening del canary C1 (fix P2 audit 19/10) — VOCE DI MANUTENZIONE

STATO: PRE-REGISTRATA 2026-10-20 (Artù) — implementazione Merlino (REQ-MERL-20261020-014). Fuori dal conteggio tentativi (manutenzione/robustezza, non esperimento).
Repo: `grivetto/money` · fonte: `prove/audit_capitale_20261019/AUDIT.md` (37 difetti) + verifica Artù `REVIEW_AUDIT.md` (priorità **P2 = canary C1: voci 4,5,6,8 + lock su stato**).

## Obiettivo
Chiudere i difetti **P2** sul percorso canary (`scripts/canary_carry.py`, canary DOGE **live**), con **test di regressione che RIPRODUCONO il difetto** (evidenza rosso→verde per ciascun fix). Niente refactoring, niente cambi di design oltre al fix puntuale.

## Fix richiesti (P2 — canary C1)
1. **Reprice spot — over-buy (AUDIT: canary_carry.py:388-403).** Se `fetch_order` fallisce → `filled_prev=0` → `residuo = Q_SPOT`: si rinvia la taglia PIENA ignorando il riempito (race lettura/cancel). Fix: leggere il fill effettivo DOPO la cancel e rinviare `residuo = Q_SPOT - filled_effettivo`; se il fill non è leggibile → FERMARSI e richiedere riconciliazione manuale (mai rinviare la taglia piena).
2. **Reprice perp — over-short (AUDIT: canary_carry.py:429-439).** Dopo la cancel si rinvia l'intera `ct` (residuo non calcolato). Fix: `residuo = ct - filled` dell'ordine cancellato; rinviare solo il residuo; stop se il fill non è leggibile.
3. **Unwind spot — esito scartato (AUDIT: canary_carry.py:463-472).** Il risultato di `attesa_fill` è scartato e si dichiara «spot liquidato per tornare flat». Fix: valutare esito E saldo residuo; registrare l'esito nell'evento; uscire con «NON FLAT (residuo X)» quando l'esito != closed — mai dichiarare flat senza verifica.
4. **Close non atomica (AUDIT: canary_carry.py:524-557).** Lo spot è venduto per intero qualunque sia l'esito della chiusura perp; lo stato è marcato `closed` con residui (solo stampati). Fix: vendere lo spot solo se il residuo perp è 0 (altrimenti la copertura resta e si esce con esito esplicito); NON scrivere `status: closed` finché `pos_residua` è vero.
5. **Lock sullo stato (AUDIT: canary_carry.py:187-189 + 90-95).** `salva_state` scrive senza lock; l'intento è persistito lì; `open` concorrenti non esclusi → doppia apertura. Fix: lock esclusivo (pattern `Esecutore`, `src/money/esecuzione/esecutore.py:288`) attorno a carica/intento/invio/salvataggio.

## Fuori da questa voce (P3 — REQ successiva)
- `canary_carry.py:403-415,452-453` oo1/avg1/fee1 non aggiornati dopo reprice (MEDIA, bookkeeping).
- `canary_carry.py:367-374` fallback cross silenzioso su set-leverage fallito; `:343-354` `convert` senza cancello; `:531` mgnMode dallo stato locale; idempotenza `okx_ops`; `cancello.py` `rischio_aperto_eur` strutturalmente morto; prezzi senza `price_to_precision` in carry_apri; BASSA residue.

## Vincoli
- Lavoro in `~/merlino-scratch/p30/`; zero write su `~/money`; zero ordini/chiavi; suite esistente verde.
- **Un fix per test**: ogni test deve fallire PRIMA del fix (documentare il rosso nel LEGGIMI) e passare dopo. Estendi `tests/test_canary_carry.py` (esiste) o nuovo file — dichiara la scelta.
- NON toccare: meccanica di apertura/chiusura oltre i fix, soglie, gate, kill switch; il canale stato/eventi esistente resta compatibile (campi nuovi solo in aggiunta).

## Criteri di accettazione
1. Fix 1-5 + test di regressione (output `pytest -q` per esteso; evidenza rosso→verde per ciascun fix).
2. Suite completa verde (991 attesi + nuovi) nel venv canonico.
3. `LEGGIMI.md` con la mappa fix → test → comando + comandi read-only per Artù (`canary_carry.py status --quiet`).
4. Handoff `merlino/handoff/P30/` con `MANIFEST.sha256` + `READY` (ultimo).

## Verifica (riproducibile)
```bash
cd ~/money && .venv/bin/python -m pytest tests/test_canary_carry.py -q
```
+ riesame del diff da parte di Artù (fix puntuali, nessun cambio collaterale).

## Riferimenti
`prove/audit_capitale_20261019/AUDIT.md` · `prove/audit_capitale_20261019/REVIEW_AUDIT.md` · `scripts/canary_carry.py` · `src/money/esecuzione/esecutore.py` (pattern lock) · REQ-MERL-20261020-014.
