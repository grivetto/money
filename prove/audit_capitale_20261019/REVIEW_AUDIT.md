# Review dell'audit capitale (consegna opencode-omarchy, 19/10) — verifica di Artù

Consegna: `AUDIT.md` (37 difetti: 8 ALTA · 20 MEDIA · 9 BASSA, citazioni file:riga) + `DONE.md` (comandi).
Verifica indipendente di Artù sui claim ALTA: lettura diretta del codice su mc2.

## Claim ALTA — esito della verifica
Tutti gli 8 CONFERMATI (verificati riga per riga):

1. `carry_apri.py:62-66` — `funding_atteso` applica `abs()`: il segno è cancellato e il gate non può
   mai rifiutare un funding negativo (la protezione n.2 di `cancello_carry` è strutturalmente morta).
2. `carry_apri.py:204-214` — fill parziale sulla gamba spot: annulla il residuo ma NON liquida il
   riempito, nessuno stato scritto → spot nudo non registrato.
3. `carry_apri.py:216-229` — invio perp fallito: solo print «richiede unwind manuale», nessun unwind
   automatico (il canary nella stessa situazione liquida lo spot), nessuno stato persistito.
4. `canary_carry.py:429-439` — reprice perp: rinvia la taglia PIENA (residuo non calcolato) → over-short.
5. `canary_carry.py:463-472` — unwind spot: esito di `attesa_fill` scartato, dichiara «flat» senza verifica.
6. `canary_carry.py:524-557` — close non atomica: lo spot è venduto indipendentemente dall'esito del
   perp; stato marcato `closed` con residui (i residui restano solo nell'evento/stampa).
7. `earn_move.py:583-604` — nessuna riconciliazione nel ramo `except`: POST riuscita con risposta persa
   → FAIL_EXEC senza verifica dei saldi → rischio doppio movimento su re-run.
8. `canary_carry.py:388-403` — reprice spot: `fetch_order` fallito → `filled_prev=0` → rinvia Q_SPOT
   intero (over-buy).

## Claim MEDIA selezionati — confermati a campione
- `carry_apri.py:154-163` preflight senza saldo spot; `:177-183` equity calcolata e mai usata;
  `:196,217` prezzi senza `price_to_precision`; nessun lock/stato-prima-dell'invio.
- `earn_move.py:504-511` `attendi_funding` a soglia assoluta (non delta vs saldo iniziale);
  `:573-581` poll corto (10x1s) per l'attesa post-transfer nel ramo purchase.
- `canary_carry.py:367-374` fallback cross silenzioso su set-leverage fallito.
- `cancello.py:30-43` `rischio_aperto_eur` default 0.0 e nessun chiamante di produzione → tetto di
  calore di portafoglio mai attivo.

## Priorità di fix (proposta)
- **P1 — percorso D3 (redeem + apertura):** carry_apri (1,2,3 + preflight saldo spot + capienza/equity)
  e earn_move (7 + attendi_funding a delta + poll esteso nel ramo purchase).
- **P2 — canary C1:** 4,5,6,8 + lock su stato.
- **P3 — MEDIA/BASSA residue** (idempotenza okx_ops, docstring, fail-open minori).
Stato: REQ di fix da dispatchare a Merlino dopo P28. Mitigazioni operative già inserite nella
checklist D3 del 20/10 (redeem: mai re-run su esito incerto; apertura: controllare fill parziale e unwind).
