# E4 — «cascate profonde» (pre-registrazione)

**Data:** 2026-10-21 · **Autore:** Artù · **Stato:** PRE-REGISTRATA (questa voce è scritta PRIMA dei numeri)
**Origine:** E2 (cascate, soglia −8%) è stata bocciata il 15/10 dai test di chiusura: la fascia
[−8,−10) è metà del campione e vale −0,18% (t −0,83) = rumore. Nella stessa misura è emersa una
dose-response monotona **solo da −10% in giù** (+1,45% / +2,44% / +3,23%). Quella osservazione era
post-hoc e quindi **non promuovibile**. E4 è l'ipotesi nuova, dichiarata qui, con un test pulito.

## Ipotesi (una sola, congelata)

Dopo una caduta di 3 ore **≤ −10%** con volume ≥ 3× la media a 72 ore, sul perp/spot 1h:
il rendimento long a 12 ore è **positivo al netto dei costi**, e l'effetto **cresce con la
profondità** della caduta.

## Regola operativa (nessuna griglia, nessuna variante usata per il verdetto)

- evento: `close[i] / close[i-3] - 1 ≤ −0,10` **e** `volume[i] / media72(volume)[i] ≥ 3`
- cooldown 12 ore per simbolo (un solo ingresso per episodio)
- ingresso: apertura della barra i+1
- stop: 2,5 × ATR(14) verificato intrabarra, distanza massima 50% (gap = uscita all'apertura)
- uscita: chiusura a H = 12 ore
- lato: **long** (lo short non è testato e non entra nel verdetto)
- costi: taker 0,28% round-trip (fee OKX EEA con perp + slippage), stress ×2 = 0,56%

## Campioni (dichiarati prima)

| Set | Fonte | Periodo | Ruolo |
| :--- | :--- | :--- | :--- |
| TRAIN | Bybit 1h, 59 simboli | 2021-12-02 → 2024-05-31 | coerenza e DSR |
| OOS-1 | Bybit 1h, stessi simboli | 2024-06-01 → 2026-10-12 | tenuta temporale |
| OOS-2 | **OKX 1h** (`data/ohlcv_xperp.jsonl`) | 2024-06 → 2026-10 | **cross-exchange, il test pulito** |

Limite dichiarato: la dose-response è stata *vista* sui dati Bybit (tutto il periodo), quindi
nessun sotto-periodo Bybit è davvero fuori campione. L'unico hold-out non contaminato è **OKX**:
per questo OOS-2 ha il peso maggiore e i criteri non si aggiustano dopo aver visto i numeri.

## Criteri di promozione (4/4, nessun credito parziale)

- **T1 — cross-exchange:** OOS-2 (OKX) media netta > 0 **e** t ≥ 2,0 **e** n ≥ 30.
- **T2 — tenuta temporale:** OOS-1 (Bybit 2024-06→2026-10) media netta > 0 **e** t ≥ 2,0.
- **T3 — costi raddoppiati:** su OOS-2 la media con costi ×2 (0,56%) resta > 0.
- **T4 — coerenza train:** TRAIN media netta ≥ +0,50% e t ≥ 3,0.
- **DSR:** N cumulativo = **21** tentativi (18 di E2 + 3 soglie di E4: −10, −12, −15), varianza
  dagli SR di addestramento; PASS se DSR ≥ 0,95. La soglia −10% è l'unica che entra nel verdetto;
  −12 e −15 sono dichiarate ora solo per contare i look (e correggere la selezione).

## Cosa NON è

- Non è una griglia di soglie: si testa **una** soglia.
- Non è un cambio di regola dopo i numeri: se T1-T4 non passano, E4 è **archiviata** e la
  famiglia «cascate» si chiude (E2 + E4 = due bocciature, stop).
- Non è un'autorizzazione a operare: anche con 4/4 serve il canary a taglia minima (14 giorni)
  con riconciliazione esatta, come C1.

## Artefatti attesi

- `scripts/e4_cascate_profonde.py` — misura e verdetto.
- `prove/e4_cascate_profonde_2026-10-21.json` — numeri grezzi per set.
- Voce nel `prove/REGISTRO_ESPERIMENTI.md` con l'esito, qualunque esso sia.

## Misura del risultato

Il filone è chiuso quando il verdetto è emesso su OOS-2 (OKX) con la regola congelata sopra.
PASS → canary; FAIL → famiglia chiusa, si passa al filone successivo.
