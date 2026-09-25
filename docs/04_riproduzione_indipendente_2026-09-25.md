# 04 — Riproduzione indipendente delle misure (2026-09-25)

> **Autore:** [dsh] · **Scopo:** verificare che i verdetti di `docs/03` non dipendano
> dall'ambiente di chi li ha prodotti.
>
> Perché serve: una misura è un'affermazione, e un'affermazione fatta dallo stesso processo che
> l'ha generata non è una verifica. Qui la stessa suite e le stesse misure girano su **un'altra
> macchina, un altro Python e un'altra versione di ccxt**, partendo da un **clone pulito di
> `origin/main`** — cioè dal solo artefatto pubblicato, senza lo stato locale di chi ha scritto.

---

## 1. Metodo

Sul nodo **mc2** (Linux), da zero:

```bash
git clone https://github.com/grivetto/money.git /tmp/money_clean
cd /tmp/money_clean                                  # commit 9eeb418a
export MONEY_CACHE=/tmp/money_cache_mc2               # cache fuori dal repo
python -m pytest tests -q
python scripts/misura_trend_lungo.py
python scripts/misura_momento_4h.py
python scripts/misura_griglia.py
```

## 2. Ambienti confrontati

| | ambiente A (autore) | ambiente B (riproduzione) |
| :--- | :--- | :--- |
| macchina | Windows, workstation locale | mc2, Linux |
| Python | 3.14.5 | **3.12.3** |
| ccxt | 4.5.40 | **4.5.84** |
| provenienza del codice | copia di lavoro | **clone pulito di `origin/main`** |
| commit | `9eeb418a` | `9eeb418a` |

## 3. Risultati

**Suite di test:** `136 passed` in entrambi gli ambienti.

**Verdetti e numeri chiave** — identici, cifra per cifra:

| misura | ambiente A | ambiente B (mc2, clone pulito) |
| :--- | :--- | :--- |
| A — storia intera | n=35 · **+1,959026%** · t **0,821** · PF 1,420 · DD 53,18% | n=35 · **+1,959026%** · t **0,821** · PF 1,420 · DD 53,18% |
| A — addestramento | n=19 · +4,624118% | n=19 · +4,624118% |
| A — verifica walk-forward | n=16 · **−1,206%** · t −0,44 | n=16 · **−1,206%** · t −0,44 |
| A — finestre corte | 2/9 positive | 2/9 positive |
| A — con X-Perps | archiviato · +2,329% · 5,91 EUR/anno | archiviato · +2,329% · 5,91 EUR/anno |
| B — percorsi conservativo | n=1581 · **−1,1823%** · t **−8,539** · PF 0,569 · copertura −2,150× | n=1581 · **−1,1823%** · t **−8,539** · PF 0,569 · copertura −2,150× |
| B — percorso ottimista | n=1886 · −0,81% · t −6,844 | n=1886 · −0,81% · t −6,844 |
| C — 4h verifica | n=247 · **−0,3599%** · t −0,683 · PF 0,884 | n=247 · **−0,3599%** · t −0,683 · PF 0,884 |
| C — 1d verifica | n=45 · −1,6656% · t −0,761 | n=45 · −1,6656% · t −0,761 |

Nessuna differenza. Nessun verdetto cambia.

## 4. Cosa dimostra, e cosa no

**Dimostra** che le misure:

- **non dipendono dall'ambiente**: versioni diverse di Python e ccxt, sistemi operativi diversi,
  stessa aritmetica;
- **non dipendono dallo stato locale** di chi le ha prodotte: il clone non conteneva né cache né
  file non pubblicati, quindi tutto il necessario era nell'artefatto;
- **non dipendono dall'ordine di esecuzione** delle tre misure: sono state rieseguite in sequenza
  in una cache nuova.

**Non dimostra** che il *metodo* sia corretto. È lo stesso codice eseguito altrove: se la regola
di simulazione avesse un difetto concettuale, questo test lo riprodurrebbe fedelmente in entrambi
gli ambienti. La verifica forte sarebbe **una seconda implementazione indipendente** della stessa
ipotesi — due agenti che scrivono due motori e confrontano i numeri. Qui non è stato fatto, e
dichiararlo è più utile che nasconderlo dietro un "verificato".

Resta vero, ed è la ragione per cui questo documento esiste: il progetto precedente misurava molto
e riconciliava poco, e la differenza fra "l'ho misurato" e "l'ho misurato due volte in due posti"
è la stessa che c'è fra "detto" e "verificato".

## 5. Igiene trovata durante la riproduzione

Dal clone pulito, l'esecuzione dei runner lascia cartelle non tracciate (`risultati/`, `report/`,
`dati_cache/`), perché i loro percorsi di output predefiniti non erano in `.gitignore`. Corretto:
le prove curate stanno in `prove/`, e gli output grezzi dei runner non devono sporcare
`git status` di chi riproduce.
