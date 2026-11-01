# E19 — «basis trade su futures datati BTC» (pre-registrazione)

**Data:** 2026-11-01 · **Autore:** Artù · **Stato:** ARCHIVIATA — VENUE_BLOCKED (01/11, gate n.1 fallito: futures datati non negoziabili per profilo retail OKX EEA)

## Come nasce (dichiarato)

Dalla chiusura di E15 (carry funding a soglia, morta di turnover: 106 switch/38 giorni, costi
31,80 EUR contro 4,53 EUR di funding lordo) e dalla dottrina del 31/10 (tesi economica
obbligatoria). Il difetto di E15 non era il carry: era l'inseguimento del funding episodico.
Il basis sui futures DATATI elimina il difetto alla radice: nessun funding che flip-flop ogni
8 ore, convergenza a zero per vincolo contrattuale alla scadenza, 2 trade a trimestre.

Misura puntuale del 31/10 (NON conta come evidenza, solo come ancoraggio):
- BTC-USD-261225 (scad. 25/12/2026, 55gg): future 78.021 vs spot 77.497 → basis +0,68%
  ≈ 4,5%/anno lordo.
- BTC-USD-270326 (scad. 26/03/2027, 146gg): future 79.112 → basis +2,08% ≈ 5,2%/anno lordo.
- Benchmark: Earn flessibile USDC 3,32%/anno.
- Strumento verificato live: 285 contratti FUTURES attivi, BTC-USD-261225 in stato "live",
  ctVal 100 USD, lotSz 0,1 (granularità compatibile con ~1.000 EUR).

## Tesi economica (congelata)

(a) **Controparte:** lo speculatore a leva che compra futures datati per non gestire il
funding ogni 8 ore; (b) **perché perde:** paga un premio (contango) che per vincolo di
contratto converge a zero rispetto all'indice alla scadenza (settlement); (c) **perché
persiste:** la domanda speculativa di futures datati non è arbitrata a zero perché i desk
istituzionali hanno vincoli di bilancio e capitale; il retail con ~1.000 EUR non smuove il
premio, lo incassa.

## Regola operativa (zero gradi di libertà)

- Universo: BTC only. Future datati coin-margined `BTC-USD-YYMMDD` su OKX. Nessuna aggiunta
  di simboli senza nuova pre-registrazione.
- Ingresso: alle 08:00 UTC di ogni giorno, sul contratto con `15 <= DTE <= 90`, se il basis
  annualizzato `B = (F/S - 1) * 365/DTE >= 0,0800` (8,00%) → long spot BTC-USDT (nozionale N)
  + short future BTC-USD (stesso nozionale in USD). Un solo contratto attivo alla volta.
- Uscita: settlement alla scadenza naturale (il future converge per contratto) + vendita dello
  spot contestuale alle 08:00 UTC del giorno di scadenza. Uscita anticipata SOLO se il basis
  residuo scende sotto 0,05% assoluti.
- Sizing: N = 40% del capitale del comparto (cap dichiarato, coerente col comparto carry
  esistente). Nessuna leva. Il sizing NON si ottimizza.
- Costi (dichiarati): spot taker 0,10% in + 0,10% out; future taker 0,05% in; settlement fee
  0,01% (DA VERIFICARE sul contratto); slippage 1bp/lato. Stress: costi x2.

## Campioni

- TRAIN: primi 60% dei giorni-campione dei dump storici OKX (futures datati + spot).
- OOS: ultimi 40% dei giorni-campione (nessun dato visto prima).
- Il campione si costruisce DAL dump storico; se il dump non copre >= 400 giorni-campione,
  l'esperimento si chiude DATA_BLOCKED senza spec attivabile.

## Criteri (4 + DSR)

- T1: basis medio realizzato netto annualizzato >= Earn (3,32%) + 1,5pp, su OOS.
- T2: n >= 200 giorni-campione in posizione.
- T3: a costi x2 il basis medio netto resta >= Earn.
- T4: nessun singolo contratto con basis netto negativo.
- DSR >= 0,95 con N = 3 (look della famiglia: P21, E15, E19).

## Criterio di kill

- Basis medio realizzato netto < Earn; OPPURE 2 contratti consecutivi con basis < 4% annuo
  all'ingresso; OPPURE il prodotto risulta non negoziabile per il profilo EEA retail
  (gate n.1, da verificare PRIMA del motore); OPPURE dump storico insufficiente
  (DATA_BLOCKED).

## Contratto di verifica

- Repo grivetto/money, motore `scripts/e19_basis_trimestrale.py`, artefatti
  `prove/e19_basis_trimestrale/`, test anti-look-ahead in `tests/ricerca/`.
- Preflight dati (step 1): scaricare i dump OKX futures datati BTC-USD (dal 2023) + candele
  spot BTC-USDT; calcolare il basis realizzato per contratto; verificare la negoziabilità EEA.
- Procedura di misura: preflight → spec attiva → motore → test anti-look-ahead PRIMA dei
  numeri → misura ufficiale → confronto bit-a-bit con smoke indipendente.

## Limiti dichiarati

- Il numerino puntuale del 31/10 NON è evidenza: è solo il motivo per spendere il tempo di
  scaricare lo storico. Se lo storico smentisce, si chiude senza spec attivabile.
- Futures datati su OKX: profondità dump e liquidità dei contratti lontani da verificare.
- Il basis può allargarsi temporaneamente (mark-to-market): non è drawdown di capitale ma va
  registrato.
