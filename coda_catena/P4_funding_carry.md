# P4 — Funding carry (X-Perp OKX): misura del netto annualizzato — SPEC DI IMPLEMENTAZIONE

STATO: **MISURATA l'08/10/2026 — verdetto congelato nel registro; spec CONCLUSA, fuori dal gate
di dispatch (vedi `coda_catena/CONCLUSE.md`)**. Esito: 9 simboli su 10 sotto la soglia dell'8%
netto dichiarata PRIMA della misura (DOT promosso, copertura 62 giorni) ⇒ **nessuna allocazione
di capitale**; filone regime-dipendente, da ri-misurare oltre ~180 giorni di storia. Il canary C1
(DOGE, review 2026-10-15) resta fuori scope, tracciato a parte.

- **Obiettivo**: implementare il calcolo del **netto annualizzato** del carry funding
  delta-neutrale (short 1 X-Perp + long spot di pari nozionale) su un paniere di 10 simboli e
  produrre un **verdetto per simbolo** (`promosso` / `archiviato` / `insufficiente`).
  L'implementazione deve usare i costi reali, ignorare i periodi mancanti e riportare un
  intervallo di confidenza.
- **Repo/commit**: repo `grivetto/money` (monorepo di ricerca), commit `e996d336`; root del repo =
  la directory che contiene `src/`, `data/`, `prove/`. Linguaggio: Python 3.11.
- **Input**: `data/funding_xperp.jsonl` (contratto in §4), già presente su disco. Nessuna rete,
  nessuna chiave, nessun ordine.
- **Output**: file `prove/carry/verdetto_<YYYYMMDD>.json` + stampa su stdout con `--json`
  (struttura in §1).
- **Deliverable**: `src/money/carry_netto.py`, `tests/test_p4_carry_netto.py`, l'artefatto JSON.

## 1. Interfacce e formati (esatti, da rispettare alla lettera)
```python
def carica_funding(path: str) -> dict[str, list[tuple[int, float]]]:
    """JSONL -> {simbolo: [(ts_ms, funding), ...]} ordinati per ts. Righe malformate saltate."""

def osservazioni_indipendenti(serie: list[tuple[int, float]]) -> int:
    """Numero di giorni UTC distinti con >= 3 osservazioni."""

def netto_annuo_pct(serie: list[tuple[int, float]], *, costo_ciclo: float = 0.0007,
                    soglia_ingresso: float = 0.0001, uscita_negativi: int = 2,
                    soglia_ribilanciamento: float = 0.02,
                    cicli_anno: int = 12, ribilanciamenti_anno: int = 12) -> dict:
    """{"lordo_annuo_pct","costo_annuo_pct","netto_annuo_pct","ci95","n_episodi"}"""

def verdetto(netto: dict, *, soglia_promozione: float = 0.08) -> str:
    """'promosso' | 'archiviato' | 'insufficiente' — regole in §6."""
```
CLI: `python scripts/carry_netto.py --path data/funding_xperp.jsonl --json`
Formato del JSON di output:
```json
{"data": "YYYY-MM-DD",
 "simboli": {"<simbolo>": {"lordo_annuo_pct": 0.0, "costo_annuo_pct": 0.0,
   "netto_annuo_pct": 0.0, "ci95": [0.0, 0.0], "n_osservazioni_indipendenti": 0,
   "n_episodi": 0, "verdetto": "insufficiente"}}}
```

## 2. Algoritmo (passo per passo, implementabile senza altre informazioni)
1. Caricare le serie per simbolo (§4). Saltare (e contare in un campo `righe_saltate`) le righe
   con `ts` non intero o `funding` non numerico.
2. `lordo_annuo_pct = media(funding) × 3 × 365 × 100` — 3 periodi di funding al giorno.
3. `costo_annuo_pct = (cicli_anno + ribilanciamenti_anno) × costo_ciclo × 100` con i default
   `cicli_anno = 12`, `ribilanciamenti_anno = 12`, `costo_ciclo = 0.0007` (0,07% del nozionale
   per giro). Un **ciclo** è apertura + chiusura della posizione; un **ribilanciamento** è
   l'aggiustamento che si fa quando le due gambe divergono di più del 2% del nozionale.
4. `netto_annuo_pct = lordo_annuo_pct − costo_annuo_pct`.
5. `ci95`: bootstrap sul vettore dei funding — 1.000 ricampionamenti **con reinserimento**, media
   di ciascuno, percentili 2,5% e 97,5%, poi × 3 × 365 × 100. Default 1.000 iterazioni, seed
   fisso `12345` per riproducibilità.
6. **Episodi**: scorrere i periodi in ordine; un episodio inizia quando la media degli ultimi 3
   funding è `> soglia_ingresso` e termina dopo `uscita_negativi = 2` periodi consecutivi con
   funding `< 0`. `n_episodi` = numero di episodi chiusi (+1 se uno è aperto a fine serie). I
   costi NON si ricontano per episodio: il forfait del passo 3 copre 12 cicli/anno.
7. Ripetere 2–4 sulla **finestra OOS** = ultimi 30 giorni di calendario presenti nel file (non
   usati per alcuna scelta). Se il segno del netto OOS differisce dal segno sulla finestra
   completa, il verdetto del simbolo è `insufficiente`.

## 3. Parametri di default (tutti espliciti, modificabili solo per iscritto prima della misura)
| parametro | default | significato |
|---|---|---|
| `costo_ciclo` | 0,0007 | fee swap taker/maker andata+ritorno, in frazione del nozionale |
| `soglia_ingresso` | 0,0001 | media degli ultimi 3 funding sopra cui si entra (0,01%/periodo) |
| `uscita_negativi` | 2 | periodi consecutivi con funding < 0 che chiudono l'episodio |
| `soglia_ribilanciamento` | 0,02 | divergenza delle gambe che impone un ribilanciamento |
| `cicli_anno` | 12 | cicli di apertura/chiusura stimati in un anno |
| `ribilanciamenti_anno` | 12 | ribilanciamenti stimati in un anno |
| `soglia_promozione` | 0,08 | netto annualizzato minimo per `promosso` |
| bootstrap | 1.000, seed 12345 | ricampionamenti per il `ci95` |

## 4. Dati: contratto esatto e stato attuale
- **File**: `data/funding_xperp.jsonl`, append-only, una riga JSON per osservazione.
- **Riga**: `{"simbolo": str, "ts": int (ms epoch UTC), "funding": float (frazione per periodo di
  8h), "basis_pp": float (0.0 = non popolato), "fonte": str ("okx")}`.
- **Esempio reale**: `{"simbolo": "BTC/USD:USD-310404", "ts": 1782720000000, "funding":
  -0.0001102044624311, "basis_pp": 0.0, "fonte": "okx"}`
- **Paniere**: 10 contratti USD-margined su OKX EEA — BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK,
  LTC, DOT (suffissi di scadenza `*-310404`, `*-310530`, `*-310523`, `*-310808`).
- **Stato al 2026-10-08** (misurato): 2.932 righe; finestra 2026-06-29 → 2026-10-08 (101 giorni);
  305 righe per 9 simboli su 10 (DOT 187 righe / 62 giorni); 17,9% dei periodi con funding < 0.
- **Lordi già misurati** (utili come valore atteso per un test di plausibilità):
  ADA +9,51% · DOGE +9,67% · DOT +18,43% · LINK +9,46% · LTC +7,07% · XRP +7,98% ·
  AVAX +6,68% · SOL +3,06% · ETH −0,21% · BTC −3,37%.

## 5. Test falsificabile (devono FALLIRE se l'implementazione è assente o sbagliata)
In `tests/test_p4_carry_netto.py`:
- **T1 (uccisione)**: serie sintetica con **funding a zero** su 30 giorni e ≥ 3 osservazioni/giorno
  ⇒ **assert** `netto_annuo_pct <= 0` e `verdetto(...) == "archiviato"`. Un'implementazione che
  dimentica i costi produce un netto a 0 e **fallisce** qui.
- **T2 (monotonia dei costi)**: con la stessa serie, aumentando `costo_ciclo` il netto deve
  diminuire in modo monotono — **assert** su tre valori crescenti di costo.
- **T3 (OOS)**: serie sintetica con segno opposto negli ultimi 30 giorni rispetto al resto ⇒
  **assert** `verdetto(...) == "insufficiente"`.
- **T4 (intervallo)**: su una serie a varianza nota, `ci95` contiene la media — **assert** sui
  due estremi (con seed fisso il risultato è deterministico).

## 6. Criteri di accettazione (misurabili, dichiarati PRIMA della misura)
- [ ] `python -m pytest tests/test_p4_carry_netto.py -q` → 6 passed;
- [ ] `python scripts/carry_netto.py --json` produce il JSON del §1 per tutti i 10 simboli, con
      `n_osservazioni_indipendenti >= 30` su almeno 9 simboli;
- [ ] netto annualizzato per simbolo `>= 8%` dopo i costi, con `ci95` riportato;
- [ ] verdetto `insufficiente` se il netto OOS cambia segno;
- [ ] nessun simbolo con netto `< 0` risulta `promosso`.

## 7. Fuori scope, vincoli e impatto sul trading
- **Impatto sul trading: NULLO.** Nessun ordine live, nessuna chiave API, nessun ordine simulato
  inoltrato, nessuna modifica ai moduli dei bot; nessuna scrittura fuori da `src/`, `tests/`,
  `prove/carry/`.
- **Divieti espliciti**: non modificare i moduli di esecuzione o di costo; non usare rete durante
  la misura; non usare leva (la leva massima ipotizzata è 1x e comunque richiede autorizzazione
  separata dell'owner); non introdurre dipendenze oltre a stdlib + `pandas`/`numpy`.
- **Budget anti-data-mining**: al massimo **12 configurazioni di soglia**, dichiarate prima della
  misura e contate nel registro.
- **Risorse**: runtime della misura `< 60 s`; nessuna scrittura su `data/` (sola lettura).
- **Finestra dati**: minimo 90 giorni; nessuna interpolazione dei periodi mancanti.

## 8. Procedura di verifica (comandi esatti)
```bash
cd ~/money
python -m pytest tests/test_p4_carry_netto.py -q          # atteso: 6 passed
python scripts/carry_netto.py --path data/funding_xperp.jsonl --json | head -20
python - <<'PY'
import json, statistics as st                     # controllo di plausibilità sui lordi
per = {}
for ln in open("data/funding_xperp.jsonl"):
    r = json.loads(ln); per.setdefault(r["simbolo"], []).append(r["funding"])
for s, v in sorted(per.items()):
    print(f"{s:22s} n={len(v):4d} lordo_ann={st.mean(v)*3*365*100:+.2f}%")
PY
```

## 9. Contesto (non necessario all'implementazione, per il registro)
La raccolta dei funding è attiva da cron ogni 4h (log `logs/raccolta_funding.log`, righe
`scritti=/duplicati=/errori=`). La misura formale si esegue quando la maturità dichiarata (≥ 30
giorni distinti per simbolo) è soddisfatta — oggi sì su 9 simboli su 10. Il verdetto e gli
artefatti si registrano in `prove/REGISTRO_ESPERIMENTI.md` (sezione carry). Esiste un esperimento
canary già autorizzato su un singolo simbolo, tracciato separatamente: questa spec non lo tocca.
