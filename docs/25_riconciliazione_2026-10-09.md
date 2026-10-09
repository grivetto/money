# 25 — Riconciliazione e audit fee (2026-10-09)

Prima misura ripetibile che risponde a «stiamo guadagnando?» senza sensazioni.
Tutto in **sola lettura** sul conto main OKX EEA (chiave IP-bound → eseguito da MARCODG1).

## 1. Fee reali (privateGetAccountTradeFee, 09/10/2026)

| Prodotto | maker | taker | giro misto | note |
|---|---|---|---|---|
| SPOT (acctLv 2, con derivati) | 0,080% | 0,100% | **0,180%** | tariffa corrente del conto |
| SWAP/perp | 0,020% | 0,050% | **0,070%** | 2,5× più economico dello spot |
| SPOT senza derivati (stress) | 0,200% | 0,350% | 0,550% | scenario conservativo, NON la realtà |

Conseguenza: **lo 0,7% è uno scenario di stress, non il muro reale.** La caccia S4 usa già
`okx_eea_con_perp` (0,18% misto) → **il gate non è mal tarato** e le 156k config non sono
state scartate per una fee sbagliata.

## 2. Attività reale del conto

- Bills archive (SPOT+SWAP): **186 movimenti**, di cui fee cumulate **−0,95 EUR**, PnL
  realizzato **0,00 EUR**. → il conto **non ha mai tradato davvero**; la flotta è paper.
- Versato (netto, dagli ultimi flussi): in attesa di riversamento completo dello storico;
  valore di riferimento del proprietario ≈ **1.067 EUR**.
- Equity (aggregator, `equity_source=balances`): **1.100,34 EUR**.
- **Netto vs versato: ≈ +33 EUR.** Ma è **variazione di prezzo sul capitale**, non PnL da
  trading (fee 0,95 € e realizzato 0 lo dimostrano).

## 3. Perché il filone indicatori-su-OHLCV è esaurito

Stato caccia S4 (09/10): **5.170 «papabili»** su **311.838 tentativi cumulativi**.

- expectancy **out-of-sample**: mediana **+0,96%**, max +7,5% → positiva
- **DSR** (Sharpe deflazionato): mediana **~0,011**, max 0,125, contro soglia **0,95**
- **0 / 5.170 passano**

Lettura: con 311k tentativi, quegli «+1% out-of-sample» sono **indistinguibili dal caso**
(multiple-testing). Il DSR fa il suo lavoro. **Non è un problema di fee né di gate: è
assenza di edge nello spazio cercato.** Filoni già chiusi: trend (P1-P5), momentum
(P10/P14), cointegrazione (P13, 0/45 coppie), carry funding (P4: 0,68% lordo vs soglia 8%).

## 4. Carry funding — stato

Funding attuale sui major: media **+0,0006%/8h ≈ +0,68% annuo lordo** (BTC +2%, ETH −2,9%,
SOL −0,4%, DOT +11%). Sotto qualunque soglia sensata → **nessuna allocazione** (coerente
con P4). Il filone resta **regime-dipendente**: ri-misurare quando la storia supera ~180 gg.

## 5. Rendimento sul capitale fermo (guadagno senza edge)

Il capitale main è **1.068 EUR in EUR nel wallet funding, a rendimento zero**. OKX Earn
disponibile (misurato): **USDT 3,5%**, **USDC ~5,8% stimato** (≈4,4% medio) → **+37…53 EUR/anno**,
ritirabili. Piccolo ma **positivo e garantito**. Decisione di allocazione: **in attesa del
proprietario** (movimento reale = richiede autorizzazione).

## 6. Strumento

`scripts/tabellone.py` — libro contabile versato→equity→fee→realizzato, ripetibile, multi-nodo.
Uso: `tabellone.py --env <secrets/main_okx.env> --equity-url <aggregator> --versato <N>`.
Da eseguire sul nodo dove la chiave main è utilizzabile (MARCODG1/nuvola).

## 7. Prossimo passo concreto

1. **Decidere** l'allocazione del capitale fermo (Earn) — azione positiva immediata.
2. **Non allocare capitale a strategie** finché non emerge un edge che sopravvive al DSR.
3. **Rivedere la calibrazione del gate**: con 311k tentativi la soglia DSR 0.95 è di fatto
   irraggiungibile per costruzione — serve una decisione metodologica esplicita (cosa
   accettiamo come «edge»), non un'ennesima caccia.
4. **Criterio di stop**: se dopo la revisione del gate non emerge nulla di net-positive, il
   filone indicatori è chiuso e restano solo (a) capitale in yield, (b) infra in manutenzione.
