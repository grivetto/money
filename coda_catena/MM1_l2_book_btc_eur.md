# MM1 — Misura del book L2 BTC-EUR (OKX EEA) e test di fattibilità del market making

STATO: **IN RACCOLTA dal 2026-10-23 15:30 CEST** (7 giorni; review 2026-10-30).
Repo: `grivetto/money` · commit di registrazione: `0ff5fb0d` (raccoglitore + check veglia).
Registrazione nel `prove/REGISTRO_ESPERIMENTI.md` PRIMA dei numeri formali (il 23/10 15:27-15:32
ci sono stati solo smoke test di 2-3 minuti, dichiarati come tali e non usati come misura).

## Obiettivo (verificabile)
Decidere, con dati reali e una regola dichiarata prima, se il **market making a due lati** su
BTC-EUR spot OKX EEA è economicamente possibile alla tariffa del conto, e produrre gli input
misurati (fill rate, adverse selection) per la lane «ingressi maker su 1h/4h».
Esiti ammessi: `MM-possibile` (solo allora si passa alla simulazione di P&L) oppure
`MM-archiviata-per-aritmetica` (nessuna simulazione: la lane si chiude).

## Ipotesi
- H1 (fattibilità): lo spread mediano del book BTC-EUR EEA è almeno pari al costo di andata e
  ritorno delle fee maker (16 bps con maker 8 bps/lato, misurato il 23/10 15:31 CEST via
  `GET /api/v5/account/trade-fee?instType=SPOT&instId=BTC-EUR` → `maker=-0.0008`, `taker=-0.001`).
- H2 (fill): un ordine limite al touch viene eseguito quando un trade aggressore stampa al
  prezzo del livello o oltre; la quota di fill e il movimento avverso a 5/30/60 s sono misurabili
  dai dati raccolti.

## Input / Output
- **Input**: feed WebSocket pubblico EEA `wss://wseea.okx.com:8443/ws/v5/public`, canali
  `books` (400 livelli) e `trades` per `BTC-EUR`. Nessuna chiave, nessun ordine.
- **Output macchina**: `data/l2/BTC-EUR_YYYY-MM-DD.jsonl` (1 riga/s: mid, best bid/ask e size,
  spread bps, depth bid/ask a 1/5/10/20/50/100 bps, imbalance 50/100 bps, n livelli) e
  `data/l2/BTC-EUR_trades_YYYY-MM-DD.jsonl` (ts, px, sz, side, tradeId). Heartbeat `data/l2/l2_stato.json`.
- **Output decisione**: `prove/MM1_l2_btc_eur_YYYY-MM-DD.json` + `.md` con: copertura, distribuzione
  spread (mediana/p10/p90), depth in EUR, volume scambiato, fill rate simulato e adverse selection.

## Regola di decisione (dichiarata PRIMA dei numeri formali)
1. Qualità dati (necessaria): copertura ≥ 95% della finestra, gap massimo ≤ 5 min, book non
   incrociato (bid < ask) in ≥ 99,9% delle righe con book non vuoto. Se fallisce → `insufficiente`,
   si raccoglie di nuovo una settimana (una sola riapertura).
2. **MM-possibile** solo se: `spread_mediano_bps > 16 bps` (costo RT maker) **E** depth mediana
   a 5 bps ≥ 50.000 EUR per lato (size minima operabile ~25 €, quindi il vincolo di depth è
   largamente soddisfatto ma va verificato nei minuti di stress).
3. Altrimenti `MM-archiviata-per-aritmetica`: la lane market making a due lati non si riapre
   senza un cambio di tariffa (tier VIP/accordo MM) documentato.
4. In ogni caso si riportano i numeri H2 (fill rate e adverse selection) come input della lane
   «ingressi maker», che resta distinta e non viene decisa qui.

## Test falsificabile
- `tests/` non toccati da questa lane (raccolta dati). Il test che deve fallire senza
  l'implementazione: eseguire `python scripts/raccoglitore_l2_okx.py` con `L2_WS_URL` non valido
  deve produrre **0 righe valide** e log di errore; con host valido entro 10 s deve produrre
  **almeno 1 riga con `n_bid=400` e `n_ask=400`** (assert sul file di output).
- Assert di integrità sul dataset: nessuna riga con `best_bid >= best_ask`; `depth_*` monotona
  non decrescente al crescere della soglia bps; `exchange_ts` non futuro rispetto a `ts`.

## Criteri di accettazione
- [ ] 7 giorni di copertura ≥ 95% con heartbeat sempre < 120 s (veglia `marcodg1` già configurata)
- [ ] report `prove/MM1_l2_btc_eur_2026-10-30.{json,md}` con la regola di decisione applicata
- [ ] numeri H2 (fill rate, adverse selection 5/30/60 s) riportati anche in caso di archiviazione MM
- [ ] nessun ordine inviato, nessuna chiave usata dal raccoglitore (guard clause attiva)

## Fuori scope (confini espliciti)
- NON si inviano ordini e non si tocca il capitale: questa lane è sola misura.
- NON si modifica il motore di rischio, il canary C1, le unit dei bot o la config di produzione.
- NON si modifica la lane intraday maker (solo input): la sua spec sarà separata.
- NON si cambia tariffa/account: la fee è un dato, non una variabile.

## Comando di verifica riproducibile
```bash
# stato raccoglitore su MARCODG1
ssh marco@marcodg1 "pgrep -af raccoglitore_l2_okx; cat /home/marco/money/data/l2/l2_stato.json; wc -l /home/marco/money/data/l2/BTC-EUR_$(date -u +%F).jsonl"
# freschezza + allarme veglia
ssh marco@marcodg1 "sudo -n systemctl start money-veglia.service; journalctl -u money-veglia.service -n 30 --no-pager | grep l2_stato"
```
