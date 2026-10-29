# E12 — «Listing drift 24h long-only (OKX EEA)» (pre-registrazione)

**Data:** 2026-10-29 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (universo, regola e finestre congelati PRIMA dei numeri)

## Come nasce (dichiarato)

Missione RANK 3 «listing event-driven» + ricognizione dati REQ-MERL-20261029-026 (dati PRONTI OKX+Bybit: annunci a data+ora, ground truth primo giorno via listTime e candele verificate 8/8 OKX e 7/7 Bybit; delay annuncio→trading 4–24h → l'annuncio NON è tradabile, il primo bar sì; relay cross-venue documentato ma NON testato qui).

**Ipotesi H:** i nuovi listing spot mostrano un drift di brevissimo periodo (prime 24h di contrattazione) positivo e tradabile long-only.

## Universo (congelato)

- Annunci OKX EEA `announcements-new-listings` con data evento **2023-06-01 → 2026-10-01**.
- Solo coppie SPOT `X/QUOTE` con base non stablecoin; esclude il batch di migrazione articoli del 2023-03-03; esclude strumenti di test (pattern `XTEST*`).
- Per l'evento servono: bar 1H OKX dal primo bar con ≥24 bar piene e nessun buco/zero nei primi 24; volume quote nelle prime 24h ≥ **50.000 USDT** (eseguibilità — soglia dichiarata, non ottimizzata).
- **t0** = timestamp del primo bar 1H (≡ listTime; tolleranza verificata ±1h).
- Bybit (annunci tag Spot) = campione secondario di robustness (stessa regola; usato solo nel gate T4).

## Regola (congelata)

- **LONG a open(t0); FLAT al close del 24° bar 1H (il bar che inizia a t0+23h).** Nessun filtro, nessuno stop, nessun aggiustamento intra-evento. Peso: nozionale uguale per evento (ricerca); return per-evento mediati.
- **Costi:** base round-trip **0,30%** dichiarato (fee taker ~0,20% + slippage ~0,10% — il primo bar di un listing ha spread larghi); stress ×2 = 0,60%. Entrata/uscita = cross dello spread, incluso nei costi e non nei prezzi.
- Return per evento = close(24° bar)/open(t0) − 1 − costi.

## Finestre (congelate)

- TRAIN: 2023-06-01 → 2025-06-01 · OOS: 2025-06-01 → 2026-10-01 (taglio = mediano dello storico disponibile; nessuna ottimizzazione).

## Verdetto (congelato)

- **T1** (OOS): n ≥ 60 eventi, media netta > 0, **t ≥ 2,7** (Bonferroni, p≈0,007 su N=7 configurazioni dichiarate della pipeline).
- **T2**: stress costi ×2 → media OOS > 0.
- **T3** (TRAIN): media > 0 e t ≥ 1,5 (coerenza).
- **T4** (robustezza venue): Bybit (spot) — media > 0 con t ≥ 1,0 (finestra OOS se n ≥ 60, altrimenti tutto il periodo con nota).
- **T5** (stabilità): split-half OOS (due metà temporali): media > 0 in ENTRAMBE.
- **PROMOSSA solo con 5/5.** Altrimenti la lane «listing event-driven» si chiude in questa forma: una seconda forma (es. fade condizionale post-dump) richiede NUOVA pre-registrazione con conteggio trial aggiornato.

## Limiti dichiarati

- Entrata/uscita su prezzi di barra (ottimistico; lo stress ×2 copre parte dello slippage).
- Snapshot strumenti OKX = solo correnti: l'universo viene dagli ANNUNCI (che non spariscono); per strumenti delistati vale il primo bar disponibile come ground truth.
- Niente DSR formale (serie a eventi, non giornaliera): molteplicità gestita con soglia Bonferroni e trial dichiarati.
- n atteso OKX ~150–250 nel periodo; OOS ~60–120 → potenza prudenziale dichiarata.

## Cosa consegna l'esecutore (non è la misura ufficiale)

Engine `scripts/e12_listing_drift.py` + test anti-look-ahead (PRIMA dei numeri) + smoke; dati CONGELATI in un file locale (bar 1H dei primi 2 giorni per evento + metadati; niente fetch a tempo di misura); artefatti smoke `prove/e12_listing_drift_smoke.{json,txt}`. La MISURA UFFICIALE la esegue Artù dal repo canonico.
