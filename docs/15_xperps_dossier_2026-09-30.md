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

## Verifiche live (30/09/2026 sera — dalla main key su MARCODG1)
- **acctLv = 2** confermato live; key perm `read_only,withdraw,trade`; posMode `net_mode`.
- **Spot via API operativo**: comprato 10 USDC a 0,88258 EUR (ordine eseguito e riconciliato; fee riportata 0,0 — da riverificare nei bills al prossimo fill).
- **USDT oscurato per compliance EEA**: USDT/EUR respinto (`51155 local compliance restrictions`) → collaterale utilizzabile = **USDC** (X-Perps USD-margined: USD/USDC/USDG).
- **Strumento X-Perp abilitato al conto**: `DOT-USD_UM_XPERP-310808` — set-leverage 1× cross ACCETTATO (min 1 contratto = 1 DOT ≈ 1,2 USD nozionale).
- **Ordini X-Perp via API respinti: `50124 This API Key does not have trading permission for the market`** (batch E singolo, cross E isolated → non è ordType/margin mode: è abilitazione account/key). Causa documentata OKX: *"API users must accept the X-Perp risk disclosure via the OKX web or app interface before API trading is enabled. Sub-accounts must each accept the disclosure separately."* → **Azione proprietario**: OKX web/app → sezione X-Perps → accettare il risk disclosure (compare al primo ordine/sezione); poi retest immediato via API.
- **Fondi per il test**: 20 EUR spostati funding→trading (transId 2037966931); residuo: trading 11,1742 EUR + 10 USDC, funding 80,0030 EUR. Nessun ordine aperto, nessuna posizione (verificato).
- Strumenti operativi: `scripts/okx_probe_acct.py` (diagnostica), `scripts/okx_ops.py` (transfer / acquisto / ordine-test con annullo). Ordine mai a mercato: sempre limite lontano + cancel.

## ESITO 01/10/2026 — SBLOCCO X-PERP API ✅

**La "risk disclosure" non è mai comparsa** in web né app (cercata invano dal proprietario): non era quello il blocco. Root cause reale del `50124`, in due strati:
1. **Chiave vecchia (30/09)**: creata PRIMA dell'abilitazione X-Perps → il permesso di mercato non si aggiorna sulle chiavi esistenti: serve una **chiave NUOVA** (confermato anche da caso identico in community OKX).
2. **Primo tentativo di chiave nuova**: creata **dentro il sub-account `marcosub1`** (il selettore-account del sito era su quel contesto) → uid ≠ main, saldo sub ~0: sembrava "nuova ma bloccata", in realtà era la chiave di un ALTRO conto (ordini respinti a margine `51008`, non più per permessi).
3. **Chiave nuova sul contesto MAIN** (Read+Trade, niente withdraw; IP whitelist `87.106.222.123`): **`50124` SUPERATO AL PRIMO COLPO**.

**Ricevute (live, da MARCODG1)**:
- `ORDER CREATO: 3969650118501240832` → cancel, `filled=0`.
- Replica con script ufficiale `hermes_okx_ops.py order-probe`: `ORDER CREATO: 3969650868207915008`, `ordini aperti visti: 1`, `cancel inviato`, `stato_finale=canceled filled=0.0`.
- Stato post-test: 0 ordini pendenti; posizione test del proprietario (2 DOT X-Perp, isolated 3x, TP 1,2693) intatta.
- 01/10 00:36 — **posizione di prova CHIUSA su richiesta del proprietario** (`close-position`, code 0; TP cancellato in automatico): exit 1.2373, 2 ct, **pnl +0.0098**, fee chiusura 0.0012373. Fee account FUTURES Lv1 verificata dall'endpoint: **maker 0.02% / taker 0.05%** (confermata anche sui fill: taker esatto). Anomalia registrata: la fee di APERTURA via app risultava 0.006162 (~0.25% del nozionale ≈ 5×) — da riosservare al canary; il percorso API (il nostro) è confermato a tariffa piena standard. Netto complessivo del test app: ≈ +0.0024 USDC.
- Chiave installata: `~/denaro/secrets/main_okx.env` su MARCODG1 (backup vecchia: `main_okx.env.bak-20260930`).

**Conseguenza**: il **carry/funding (P8) è ora operabile via API**; prossimo passo = esecuzione minima (canary) con le regole di sempre (leva 1×, promozione + autorizzazione esplicita, un bot per conto).

---
*Preparato da Hermes — verifiche live del 30/09. Aggiornato 01/10/2026: X-Perp API operativi (vedi ESITO sopra).*
