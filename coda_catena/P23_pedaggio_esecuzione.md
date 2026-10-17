# P23 — Il pedaggio reale: misura sui NOSTRI fill + studio maker-first
STATO: PRESA_DA Hermes 2026-10-17 — pre-registrata 2026-10-16 (hermes). M1 (fill reali, chiave read-only) di Hermes; M2 (studio maker-first) DELEGATO a Merlino — REQ-MERL-20261017-004, consegna `handoff/P23-M2/`. Interpretazioni ufficiali: addendum in coda (PRIMA di qualsiasi numero).
Repo: grivetto/alpha-omega-trading · commit di registrazione: ea7ae01b (file di questa voce: `coda_catena/P23_pedaggio_esecuzione.md`).

## Obiettivo (verificabile)
Misurare il pedaggio EFFETTIVO delle nostre esecuzioni reali (canary C1 DOGE + carry DOT/ADA) contro le tariffe teoriche usate in ogni calcolo (spot 0,08/0,10% · swap 0,02/0,05% · C ciclo 0,40% P12), e quantificare il margine di un approccio maker-first. Output: tabella per gamba (fee effettiva, slippage vs mid, totale bp) + decisione "soglie confermate / corrette".

## Contesto
Il criterio 6 del cancello richiede expectancy ≥ 3× pedaggio: ogni bp non misurato è incertezza su TUTTE le soglie. Per la prima volta abbiamo fill reali (C1, carry) leggibili dal banco read-only. Finora abbiamo SEMPRE usato tariffe, mai il realizzato.

## Ipotesi
- H1 (realizzato): il pedaggio effettivo per gamba sui fill reali è ≤ tariffa dichiarata + 5bp (slippage medio piccolo alle taglie minime).
- H2 (maker-first): con ordini post-only + fallback taker dopo X s (stima da book pubblico L1, NON esecuzione), il costo atteso per gamba swap scende verso il lato maker; risparmio stimato ≥ 5bp per ciclo di carry.

## Meccanica
- M1 (misura, primaria): dal ledger reale via chiave read-only (bills/fills OKX): per ogni fill delle esecuzioni C1 e carry — fee effettiva, prezzo fill vs mid al timestamp dell'ordine (slippage), totale bp per gamba; riconciliato per strumento e ordine. NESSUNA scrittura.
- M2 (studio, secondaria): replay su book pubblico (snapshot L1) di 20 momenti fissi (seme fisso): simulare post-only a mid±tick con timeout X ∈ {5s, 15s} e fallback taker; stimare fill-rate e costo atteso per gamba. Dichiarato in output: STIMA, non misura d'esecuzione.
- Criterio H1: se il realizzato è peggiore > 5bp → aggiornare il costo C in OGNI misuratore (voce di manutenzione: variante di costi dichiarata).

## Griglia dichiarata
X ∈ {5s, 15s} (2 valori); momenti book: 20 fissi. NIENT'ALTRO.

## Universo e campionamento
Fill reali: esecuzioni C1 + carry disponibili (censimento completo, non campione). Book: endpoint pubblico OKX (L1), 20 momenti nel weekend in corso (liquidità reale, non ideale). I fill sono pochi e non coprono tutti i regimi: dichiarato in ogni output.

## Criteri di stop / esiti ammessi
- Se il ledger è insufficiente (troppo pochi fill per leggere lo slippage) → rimandata al prossimo ciclo di esecuzione, tracciata come promemoria (non forzare numeri).
- Esiti ammessi: {confermato, corretto+costi-aggiornati, motore-maker-first-consigliato}; in OGNI caso si consegna la tabella bp.

## Anti-bias
- Slippage calcolato vs mid al timestamp dell'ordine (mai vs close di candela, mai best-case).
- Nessun ordine reale in questa voce: la prova live del motore maker-first sarà una voce separata con autorizzazione esplicita.
- Nessuna stampa di chiavi o valori sensibili; solo esiti e numeri aggregati.

## Fuori scope
- Ordini reali (proibiti in questa voce); modifiche al canary/carry in produzione; qualunque scrittura sugli exchange.

## Contratto di consegna (per l'implementatore)
Input: chiave read-only del banco (già disponibile al processo hermes) + endpoint pubblici OKX. Output atteso: `scripts/misura_p23.py`, `P23_pedaggio.json` (tabella bp per gamba), `P23_report.md` (sintesi + decisione), test dedicati.
Criteri di accettazione:
- [ ] tabella bp per OGNI gamba delle esecuzioni reali (fee effettiva + slippage vs mid)
- [ ] riconciliazione fee: somma fee misurate == fee nel ledger (atteso match esatto, tolleranza 0)
- [ ] studio maker-first con fill-rate e costo atteso per X ∈ {5s, 15s}, dichiarato come stima
- [ ] zero ordini, zero scritture su exchange
Comando di verifica:
```bash
.venv/bin/python -m pytest tests/ -k p23 -q
.venv/bin/python scripts/misura_p23.py --report
```
## Riferimenti
docs/16 (C1) · E1 · P12 M2 (costi) · cancello criterio 6 · carry_multi.

## Addendum 2026-10-17 (Artù) — esecuzione della voce: M2 delegato a Merlino, M1 a Hermes. PRIMA di qualsiasi numero, interpretazioni ufficiali:
1. **Ripartizione:** M1 (fill reali, chiave read-only del banco) resta di Hermes. M2 (studio maker-first su book pubblico) è DELEGATO a Merlino — REQ-MERL-20261017-004, canale `hermes_bridge/merlino/`, consegna `handoff/P23-M2/`. L'integrazione in `scripts/misura_p23.py` e la misura UFFICIALE restano di Hermes.
2. **Strumenti M2:** {DOGE, DOT, ADA} × {spot, swap} su OKX EEA, endpoint PUBBLICI (gli stessi delle esecuzioni reali: C1 DOGE, carry DOT/ADA). Zero chiavi, zero ordini, zero scritture.
3. **Momenti:** 20 istanti indipendenti nel weekend 17–18/10/2026, scelti con regola deterministica riproducibile (seme fisso, dichiarato); in ciascun istante si campionano i 6 libri (20 osservazioni per libro). Nessun filtro sulle ore: liquidità reale, non ideale.
4. **Simulazione (per libro × X ∈ {5s, 15s}):** post-only a P_buy = mid − tick / P_sell = mid + tick (tick = tick size dello strumento; mid al momento dell'ordine); finestra X s; se non fillato → fallback taker (costo = taker fee + attraversamento spread vs mid).
5. **Fill proxy (senza modellazione di coda → limite SUPERIORE del fill-rate, dichiararlo):** primario = un trade pubblico stampa ≤ P_buy (sell: ≥ P_sell) entro X s; sensibilità = best_ask ≤ P_buy / best_bid ≥ P_sell. Riportare entrambi.
6. **Output:** fill-rate e costo atteso (bp) per gamba × X (bound primario + sensibilità), confronto con le tariffe correnti (`money.costi`), risposta a H2 («risparmio ≥5bp per ciclo?»). Tutto etichettato **STIMA, non misura d'esecuzione**.
7. Invarianti: zero ordini, zero scritture su exchange, zero write su `~/money`; consegna con `MANIFEST.sha256` + `READY`; `LEGGIMI.md` col comando esatto che rieseguirà Artù (run ufficiale: 20 momenti reali, weekend).
