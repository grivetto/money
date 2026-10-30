# E13 — «Listing drift 24h long-only (OKX SPOT, universo globale)» (pre-registrazione)

**Data:** 2026-10-30 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (universo, regola, finestre e gate congelati PRIMA dei numeri)
**Repo:** grivetto/money, base commit `0507eb1c` (30/10/26) · dati ricognizione REQ-MERL-20261029-026 (congelata, MANIFEST `2006b716` e `7ab6dcf4`).

## Come nasce (dichiarato)

Estensione dichiarata di E12 (REGISTRO 29/10: «effect size il più forte misurato finora; un'eventuale prosecuzione (universo più ampio per potenza statistica) è possibile SOLO come nuova pre-registrazione (E13) con dati e finestre nuovi»). E12 è risultata 4/5: T1 FALSO per numerosità sull'universo EEA (n OOS 23 < 60; media OOS +69,99%, t 2,024) — non per segno; Bybit intero n=323, media +533,05%, t 8,530. E13 NON è una variante pescata dal risultato: cambia SOLO l'universo di selezione (dal feed annunci EEA al listTime globale), con regola e finestre IDENTICHE — la numerosità OOS passa da decine a centinaia di eventi.

## Obiettivo

Misurare, con potenza statistica sufficiente, se il drift positivo delle prime 24h di contrattazione di un nuovo listing spot è una proprietà dell'evento «nuovo strumento su OKX» (attenzione/flussi in entrata) e non del canale annuncio. Esito atteso: verdetto congelato 5/5 sì/no, con numeri per finestra, trimestre e sensibilità dichiarate.

## Universo (congelato)

- Strumenti **SPOT OKX** (www≡EEA) dallo snapshot strumenti del 29/10/26 (ricognizione REQ-MERL-20261029-026, congelato), con **listTime ∈ [2023-06-01, 2026-10-01)**.
- **Un evento = uno strumento** (instId). Multi-book (stesso token su più quote): più eventi; sensibilità dichiarata col collapse a 1 evento per token (quote col t0 più antico).
- Esclusioni: base stablecoin (insieme dichiarato nel codice), tokenized stocks `x*/USDC` (classe equity), pattern `XTEST*`, strumenti senza listTime.
- **t0** = timestamp del primo bar 1H (≡ listTime; tolleranza verificata ±1h; scostamenti annotati).
- Filtri di eseguibilità (sui primi 24 bar, identici a E12): 24 bar orari consecutivi dal t0, nessun buco, nessuno zero (o/h/l/c>0, vol>0, bar piena); **volume quote prime 24h ≥ 50.000** (valuta di quotazione, senza conversione FX).
- Conteggi di ricognizione (stima, non vincolo): 1.064 strumenti in finestra, ~827 basi crypto; OOS potenziale ~800 strumenti prima dei filtri → **n atteso dopo filtri: 300–600** (prudenziale).

## Regola (congelata — IDENTICA a E12)

- **LONG a open(t0); FLAT al close del 24° bar 1H (il bar che inizia a t0+23h).** Nessun filtro, nessuno stop, nessun aggiustamento intra-evento.
- **Costi:** base round-trip **0,30%** dichiarato; stress ×2 = **0,60%**. Return per evento = close(24° bar)/open(t0) − 1 − costi.

## Finestre (congelate — IDENTICHE a E12)

- TRAIN: listTime < 2025-06-01 · OOS: 2025-06-01 ≤ listTime < 2026-10-01.

## Input / Output

- **Input:** freeze dati congelato (bar 1H dei primi 2 giorni per tutti gli strumenti dell'universo + campione Bybit; metadati eventi) — nessun fetch a tempo di misura.
- **Output:** artefatti `prove/e13_listing_drift.{json,txt}` (per-evento, esclusioni con motivo, per-finestra, per-trimestre, sensibilità) + voce nel REGISTRO.

## Verdetto (congelato)

- **T1** (OOS): **n ≥ 100** eventi, media netta > 0, **t ≥ 2,7** (Bonferroni, N=7 configurazioni dichiarate della pipeline — come E12).
- **T2**: stress costi ×2 → media OOS > 0.
- **T3** (TRAIN): media > 0 e t ≥ 1,5.
- **T4** (venue): Bybit spot, stesso metodo di selezione (listTime via API pubblica, bar da `market/kline`), stessi filtri — media > 0 con t ≥ 1,0; finestra OOS se n ≥ 100, altrimenti intero periodo con nota.
- **T5** (stabilità): split-half OOS (per t0): media > 0 in ENTRAMBE le metà.
- **PROMOSSA solo con 5/5.** Se fallisce: lane «listing event-driven» chiusa DEFINITIVAMENTE (nessuna seconda forma).

## Limiti dichiarati (da riportare nel verdetto)

- **(L1) Sopravvivenza:** l'universo è composto solo da strumenti ANCORA listati al 29/10/26; i delistati 2023–26 non sono recuperabili (OKX 51001) → possibile sovrastima del drift; mitigazioni: (i) la finestra misurata è di 24h e il delisting è quasi sempre successivo al giorno 1; (ii) T4 su Bybit ha struttura delistati diversa; (iii) in caso di promozione: canary a taglia minima con verifica live — il bias diventa un parametro monitorato, non un'assunzione.
- **(L2) Multi-book**: contati per strumento; sensibilità collapse dichiarata.
- **(L3) Bar bucate/zero**: lettura stretta (come E12); sensibilità lettura larga dichiarata.
- **(L4) Ondate concentrate**: 2026-02/03 = ~465 strumenti (≈44% dell'universo): il report include medie per trimestre e split-half; nessuna interpretazione senza guardare entrambe le metà.
- **(L5) Niente DSR formale** (serie a eventi, non giornaliera): molteplicità gestita con Bonferroni N=7 + trial dichiarati, come E12.

## Test falsificabile

I test anti-look-ahead (adattati da E12) DEVONO FALLIRE se l'engine introduce una sbirciata al futuro: il test è atteso rosso se l'entry usa close(t0) invece di open(t0); se l'exit legge oltre il 24° bar; se i filtri (volume/zero) usano bar oltre la 24ª; se la selezione evento usa informazioni ≥ t0. Il mutate-demo gira 3 mutazioni e tutte devono risultare rilevate (ennesimo rosso atteso), PRIMA di guardare i numeri.

## Criteri di accettazione (checklist consegna esecutore)

- [ ] Freeze completo con MANIFEST verificabile (sha256sum -c OK) e conteggi universo per classe/trimestre
- [ ] Engine `scripts/e13_listing_drift.py` conforme alla spec (regola identica a E12)
- [ ] Test anti-look-ahead + mutate-demo verdi PRIMA dei numeri (log di evidenza)
- [ ] Smoke su dati congelati con esiti T1–T5 e artefatti `prove/e13_listing_drift_smoke.{json,txt}`
- [ ] Handoff con README + delta repo pronto (manuale l'integrazione: Artù)

## Fuori scope

Short e fade; orizzonti oltre le 24h; esecuzione su venue diverse da OKX (Bybit è SOLO verifica); ottimizzazione di soglie/quote/finestre; tokenized stocks e stablecoin; qualsiasi modifica delle lane già chiuse (E12 resta com'è).

## Procedura di verifica

```bash
# esercizio dei test (dal layout del repo)
cd ~/money && .venv/bin/python -m pytest tests/ricerca/test_e13_antilookahead.py -q
# smoke rigenerabile sui dati congelati
.venv/bin/python scripts/e13_listing_drift.py --freeze prove/e13_listing_drift/freeze --json prove/e13_listing_drift.json --txt prove/e13_listing_drift.txt
# lint della presente spec: 7/7 attesi
.venv/bin/python scripts/spec_lint.py coda_catena/E13_listing_drift_universo.md
```

## Cosa consegna l'esecutore (non è la misura ufficiale)

Freeze dati (bar 1H dei primi 2 giorni per TUTTI gli strumenti dell'universo + campione Bybit; metadati eventi; MANIFEST) → engine `scripts/e13_listing_drift.py` (loader dagli universi listTime; stessa logica di `e12_listing_drift.py`) → test anti-look-ahead + mutate-demo PRIMA dei numeri → smoke su dati congelati. La MISURA UFFICIALE la esegue Artù dal repo canonico.

## Se passa

Proposta di canary (decisione Artù): taglia fissa minima per evento, max esposizione simultanea, solo strumenti ammessi, fee/slippage riconciliati ex-post. La spec operativa si scrive solo con l'esito in mano.
