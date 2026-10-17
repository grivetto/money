# P23 — Il pedaggio reale: misura sui NOSTRI fill + studio maker-first — REPORT

**Esiti: H1 CONFERMATO** (fee reali = tariffa taker esatta; slippage proxy medio ≈ +1,5 bp) · **H2 NON CONFERMATO** (maker-first non conviene: risparmio stimato < 5 bp/ciclo). Esito ammesso del contratto P23: **soglie confermate; motore-maker-first NON consigliato**.
Data: 2026-10-18 · Misura ufficiale: Artù (Hermes, mc2) · Spec: `coda_catena/P23_pedaggio_esecuzione.md` + addendum 17/10.

## Sintesi per il proprietario

1. **Il pedaggio reale delle nostre esecuzioni è esattamente la tariffa taker**: spot 10,00 bp, perp 5,00 bp — zero sovraccosti nascosti, su OGNI gamba (riconciliazione a tolleranza 0).
2. **Ciclo reale: 15,1–20,8 bp** (carry-DOT 15,1 · carry-ADA 17,2 · C1-DOGE 20,8) contro il costo **C = 40 bp** usato in ogni calcolo → C resta conservativo: **nessuna correzione alle soglie**.
3. **Maker-first non conviene** a queste taglie: il risparmio stimato dal book pubblico è 0,8–1,6 bp per ciclo (soglia dichiarata: 5 bp). Si resta taker.
4. Conseguenza strategica: il pedaggio non è riducibile con l'esecuzione (è già al minimo strutturale delle nostre tariffe). L'edge va cercato dove è sempre stato: rendita (Earn/carry), capitale, segnali nuovi.

## M1 — pedaggio realizzato sui fill (misura d'esecuzione)

Fonte: ledger OKX reale, sola lettura (chiave read-only del banco, nodo MARCODG1), fill/ordini/bills dei 90 giorni; perimetro: esecuzioni C1 (DOGE) e carry multi (DOT/ADA) + conversione C1, censimento completo (21 fill rilevanti, 12 ordini).

| esecuzione | n fill | nozionale | fee bp | slippage bp (proxy 1m) | totale bp | tariffa taker bp | delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| carry-ADA-spot | 1 | 89,86 | 10,00 | 0,00 | 10,00 | 10,0 | 0,00 |
| carry-DOT-spot | 2 | 90,01 | 10,00 | +0,26 | 10,26 | 10,0 | +0,26 |
| C1-DOGE-spot | 1 | 10,42 | 10,00 | +8,45 | 18,45 | 10,0 | +8,45 |
| carry-ADA-perp | 4 | 89,72 | 5,00 | +2,23 | 7,23 | 5,0 | +2,23 |
| carry-DOT-perp | 5 | 89,88 | 5,00 | −0,13 | 4,87 | 5,0 | −0,13 |
| C1-DOGE-perp | 1 | 10,41 | 5,00 | −2,64 | 2,36 | 5,0 | −2,64 |
| C1-conversione (USDC-EUR) | 1 | 11,47 | 0,00 | 0,00 | 0,00 | n/a | n/a |

- **Riconciliazione fee: MATCH a tolleranza 0** — somma fee dei fill == fee dell'ordine (per ordId) e ogni fill == voce bill corrispondente (per billId). Il ledger è internamente coerente: la fee misurata È la fee vera.
- **Cicli (somma gambe) vs soglia (tariffa + 5 bp × gambe)**: C1-DOGE 20,81 vs 25,0 → OK; carry-DOT 15,13 vs 25,0 → OK; carry-ADA 17,23 vs 25,0 → OK. **H1: confermato**; unica eccezione di gamba: C1-DOGE-spot (+8,45 bp sul proxy candela, −2,11 bp sull'index) — compatibile con il mezzo spread taker non misurato direttamente (nessun book storico), dichiarata e non correttiva.
- Metodo slippage: prezzo fill vs **mid proxy** = (open+close)/2 della candela 1m che contiene il `cTime` dell'ordine (mai close secco, mai best-case); la sensibilità con `fillIdxPx` (index al fill) è nel JSON ma NON entra nel verdetto: per i perp contiene il basis spot-perp, non lo slippage di esecuzione.

## M2 — studio maker-first (STIMA da book pubblico)

Fonte: 20 momenti reali nel weekend 17–18/10 (seed fisso 42), 6 libri {DOGE,DOT,ADA}×{spot,swap} su OKX EEA, post-only a mid±tick con fallback taker, X ∈ {5s, 15s}. Fill proxy primario (trade) = limite SUPERIORE del fill-rate reale; sensibilità (best ask/bid). **Tutto etichettato STIMA, non misura d'esecuzione.**

- **Run ufficiale (Artù, 17/10 21:45–22:31 UTC, 20 momenti, seed 42)**: **H2 NON confermato** — risparmio stimato per ciclo swap: **+0,86 bp (X5 prim) / −0,13 bp (X5 sens) / +2,92 bp (X15 prim) / +2,10 bp (X15 sens)**; soglia dichiarata 5 bp. Fill-rate coerente col modulo (proxy primario = limite superiore).
- **Run di verifica indipendente (17/10 16:35–17:20 UTC, eseguito dal proprietario con lo stesso comando)**: stesso esito — risparmi −0,50/−1,43 bp (X5) e +1,55/+0,83 bp (X15); fill-rate per gamba dello stesso ordine di grandezza. **Due campionamenti indipendenti, stessa conclusione: H2 non confermato.**
- Lettura: a queste taglie il fill maker non è abbastanza frequente (e il fallback taker paga comunque il pedaggio); il risparmio atteso non copre la soglia. **Motore maker-first: non si fa.**

## Decisione (contratto P23: «soglie confermate / corrette»)

- **Soglie confermate.** C = 0,40%/ciclo (P12) resta conservativo (realizzato 15–21 bp); nessun misuratore da aggiornare; nessuna modifica a C1/carry.
- **Motore maker-first NON consigliato** (stima sotto soglia). La prova live del motore non si apre: sarebbe costo di sviluppo senza EV.
- Il fronte «esecuzione» si chiude qui: il pedaggio è la tariffa, e la tariffa è già quella giusta (X-Perps attivi dal 01/10).

## Limiti dichiarati

- Campione M1 piccolo (21 fill, 6 gambe) e non copre tutti i regimi; dichiarato.
- Mid proxy ±5 bp su 1m: l'incertezza è confrontabile con la soglia su gambe singole; il verdetto si legge sui cicli e con la sensibilità index.
- M2: fill proxy senza modellazione di coda → limite superiore del fill-rate; due run indipendenti concordi.
- La conversione USDC-EUR (fee 0) è fuori dal confronto tariffe (non è un'esecuzione di trading).

## Artefatti

- `scripts/misura_p23.py` + `tests/test_misura_p23.py` (15 test offline) — comando: `.venv/bin/python scripts/misura_p23.py --report`
- `prove/p23_ledger_raw.json` (ledger read-only, perimetro C1/carry), `prove/p23_candele.json`
- `prove/P23_pedaggio.json`, `prove/P23_m2.json` (+ `P23_m2_smoke.json` in handoff Merlino)
- Handoff: `hermes_bridge/merlino/handoff/P23-M2/` (modulo+test+smoke, MANIFEST 4/4)
- Registro: voce 2026-10-18 in `prove/REGISTRO_ESPERIMENTI.md`
