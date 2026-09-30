# Dossier X-Perps / acctLv 2 — decisione del proprietario (30/09/2026)

Domanda: passare il conto OKX EEA al profilo derivati (X-Perps, "acctLv 2") — quanto costa?

## Risposta breve
- **Aprirlo è GRATIS**: nessun canone, nessun abbonamento, nessun costo per le chiavi.
  Richiede solo l'"appropriateness assessment" MiFID II (questionario di idoneità, ~5
  minuti nell'app/web). Se non si passa, l'accesso è bloccato (test vincolante).
- **Non è un costo: è uno SCONTO.** Con il conto X-Perps aperto le commissioni **SPOT EEA**
  scendono: maker 0.200% → **0.080%**, taker 0.350% → **0.100%** (giro misto spot
  0.550% → **0.180%**). Fonte: pagina fee EEA di OKX (framework apr-2026), verificata da
  fonti indipendenti ago/set-2026; coincide con la nostra ipotesi `okx_eea_con_perp`.
- Fee X-Perps (derivati): 0.02% maker / 0.05% taker → giro ~**0.070%** (7.86x vs spot attuale).

## Cosa serve (solo il proprietario, ~10 minuti)
1. In app/web: Trading → **"Sblocca X-Perps"** → completare il questionario di
   appropriatezza (MiFID II). Nessun deposito richiesto; nessun obbligo di usare la leva.
2. Impostazioni → **Modalità conto**: attivare "Spot e Futures" (pannello singola valuta).
   Vincolo tecnico: il cambio richiede 0 ordini aperti e 0 posizioni — il conto ORA è
   pulito (verificato dal banco: 0 ordini, 0 posizioni, 100.0047 EUR nel funding).
3. (Dopo l'attivazione) aggiorniamo le costanti di costo del repo con un test che le
   sblocca — da quel momento le misure usano i costi nuovi (voci NUOVE nel registro;
   i verdetti passati restano quelli registrati).

## Cosa cambia per il progetto
- **Costi**: spot 0.550% → 0.180% per giro (3.05x); derivati 0.070% (7.86x). Ogni misura
  futura (P10, P11, P12, carry) va giudicata anche a questi costi.
- **Carry/funding diventa operabile**: il triage del 30/09 (+5.09%/anno lordo medio,
  83-92% periodi positivi sui major — `prove/P4_triage_carry_2026-09-30.*`) richiede il
  lato SHORT perp, che oggi (acctLv 1) non possiamo aprire. I tassi del triage vengono da
  OKX EEA — lo stesso venue di X-Perps (funding 4h/8h).
- **Rischi/regole**: si sblocca l'accesso a prodotti a leva (cap 10x, negative balance
  protection MiFID, margini continui). Regole di progetto INVARIATE: leva 1x, nessun
  ordine live senza promozione del cancello + autorizzazione esplicita; il profilo si
  attiva come INFRASTRUTTURA, non come permesso di fare trading. Il banco resta read-only.

## Caveat
Numeri dalle pagine pubbliche OKX EEA (ago/set 2026): **prima di attivare, guarda la
pagina fee nel TUO account** (le due tabelle spot appaiono affiancate) — se divergono,
vince quello che vedi tu.

## Fonti
- OKX "Updates to OKX EEA Trading Fees" (apr 2026): due tabelle spot EEA; la soglia è
  l'apertura del conto derivati; X-Perps base 0.02%/0.05%.
- OKX "Introduction to Unified Account" (EEA): modalità conto Spot / Spot-Futures /
  Multi-currency; per attivarle serve l'assessment.
- Copertura indipendente dell'epoca X-Perps (lancio apr 2026): futures a 5 anni, funding,
  cap 10x, assessment obbligatorio.

---
*Preparato da Hermes — richiesta azione: SOLO proprietario (questionario + modalità conto).*
