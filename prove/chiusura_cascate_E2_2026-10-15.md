# Chiusura E2 — «cascate di liquidazione»: NON PROMUOVIBILE

**Data:** 2026-10-15 · **Esito:** 4/4 test falliti → nessuna promozione, nessuna allocazione di capitale
**Criteri congelati PRIMA dei numeri:** commit `cd07f4b0` · **Motore:** `scripts/chiusura_cascate.py`
**Artefatti:** `prove/chiusura_cascate_2026-10-15.json` · `prove/chiusura_cascate_2026-10-15.txt` · dati morti in `data/cache_morte/` (gitignored, fetch: `scripts/scarica_monete_morte.py`)

## In una riga
Il primo candidato uscito 8/8 dal cancello riparato (14/10, E2) **non supera la chiusura spietata**: quattro test su quattro bocciati. E2 si archivia; il capitale resta dov'è.

## T1 — Fasce di profondità: **FALLITO**
Criterio: ogni fascia con n≥40 positiva · la più profonda t≥2,5 · media(profonda) ≥ media(superficiale).

| Fascia (caduta 3h) | n | media netta | t | positive |
|---|---|---|---|---|
| −8% … −10% | 837 | **−0,182%** | −0,83 | 49,6% |
| −10% … −12% | 343 | +1,451% | 3,40 | 58,0% |
| −12% … −15% | 211 | +2,441% | 4,38 | 67,8% |
| ≤ −15% | 152 | +3,228% | 3,98 | 68,4% |

La fascia base (54% del campione) è **negativa**: la metà del segnale «caduta −8%» è rumore.
Il rimbalzo esiste solo da −10% in giù ed è monotono con la profondità (dose-response) —
osservazione **post-hoc**: non promuovibile senza un esperimento NUOVO su dati freschi.

## T2 — Regime: **FALLITO**
Criterio: col filtro dichiarato (BTC>SMA200) → 2022 ≥ −0,1%, totale ≥ +0,7%, OOS > 0.

- Filtrato: n=983, media **+1,453%** (t 6,21), OOS **+1,63%** — ma **2022 = −7,58%** (n=28):
  i soli trade 2022 che passano il filtro sono i peggiori (crolli LUNA/USTC in contesto bear).
- Criterio (a) fallito → filtro **non adottato** (il tentativo conta comunque in N).
- Nessun filtro semplice salva la coda di regime 2022.

## T3 — Survivorship: **FALLITO**
Criterio: aggregato (superstiti + morte, non filtrato, non cappato) ≥ +0,6%/trade e t ≥ 4,0.

| Simbolo | n | media | t |
|---|---|---|---|
| LUNC-USDT | 61 | −4,59% | −2,03 |
| USTC-USDT | 56 | −3,46% | −2,62 |
| FTT-USDT | 42 | −1,22% | −0,66 |
| SRM-USDT | 47 | +2,66% | 2,44 |
| **Aggregato (1.749 trade)** | | **+0,544%** | **2,72** |

Aggiunte 206 trade «morte» (inclusi i crolli LUNA-maggio 2022 e FTT-novembre 2022, mai visti
dal paniere precedente): la media scende da **+0,875% (t 4,58)** a **+0,544% (t 2,72)**.
Il bias di survivorship vale ~40% della media. L'edge «cascate» non regge sull'universo onesto.

## T4 — DSR (convenzione congelata, N=18): **FALLITO**
- SR addestramento config promossa (cap 5/giorno): **0,195** su 352 osservazioni;
  varianza dei 13 look long = 0,00731.
- DSR N=18: **0,752** (letture A e B coincidono). Sensibilità: N=13 → 0,82 · N=9 → 0,89.
- Sotto la soglia **0,95 in ogni lettura**: non è un problema di convenzione — il candidato non passa.

## Cosa resta
- La famiglia «cascate −8%» su Bybit è **chiusa**. Nessuna allocazione.
- Unica osservazione sopravvissuta (post-hoc, NON promuovibile così com'è): «solo cadute profonde ≤ −10%».
  Per testarla serve un esperimento NUOVO pre-registrato su dati freschi (banco prospettico, zero capitale).
- I numeri cap5 (n=591, +1,455%, t 4,40) restano nel json solo come descrittivi d'archivio.

## Riproduzione
```bash
cd ~/money
.venv/bin/python scripts/scarica_monete_morte.py    # dati monete morte (una tantum) → data/cache_morte/
.venv/bin/python scripts/chiusura_cascate.py        # output: prove/chiusura_cascate_2026-10-15.json
```
