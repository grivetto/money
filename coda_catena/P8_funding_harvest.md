# P8 — Raccoglitore funding (X-Perp OKX): raccolta append-only idempotente — SPEC DI IMPLEMENTAZIONE

STATO: **ATTIVO** (integrato 2026-09-29, raccolta schedulata dal 2026-10-01) — spec **CONCLUSA
come infrastruttura integrata**: non è un esperimento, fuori dal gate di dispatch (vedi
`coda_catena/CONCLUSE.md`).

- **Obiettivo**: implementare/mantenere un raccoglitore che scarica i tassi **funding** dei perp
  OKX EEA e li accoda su file, in modo **append-only** e **idempotente**, con una **guardia
  anti-ordini** verificabile. È uno strumento di misura, non una strategia: non decide nulla e
  non invia nulla.
- **Repo/commit**: repo `grivetto/money` (monorepo di ricerca), commit `e996d336`; root del repo =
  la directory che contiene `src/`, `scripts/`, `data/`, `logs/`. Linguaggio: Python 3.11.
- **Input**: endpoint **pubblici** OKX EEA per la storia dei funding rate dei contratti X-Perp
  (nessuna autenticazione, nessuna chiave) + il file esistente `data/funding_xperp.jsonl`
  (da leggere per non duplicare).
- **Output**: `data/funding_xperp.jsonl` accresciuto (righe in §2) e una riga di log per tick in
  `logs/raccolta_funding.log` nel formato `scritti=N duplicati=M errori=K`.
- **Deliverable**: `src/money/raccoglitore_funding.py` (raccolta + guardia),
  `scripts/raccogli_funding.py` (CLI), `tests/test_raccoglitore_funding.py` (test T1–T4).

## 1. Interfacce e formati (esatti, da rispettare alla lettera)
```python
def raccogli_funding_basis(simboli: list[str], giorni: int, path: str, *, client=None) -> dict:
    """Scarica la storia funding degli ultimi `giorni` giorni per i `simboli`, accoda al file
    `path` solo le righe nuove. Ritorna {"scritti": int, "duplicati": int, "errori": int}."""

def verifica_niente_ordini_sorgente(path_modulo: str) -> bool:
    """True se il sorgente NON contiene percorsi di invio ordini; False altrimenti."""

def report_copertura(path: str, data_inizio: str, data_fine: str) -> dict:
    """Copertura per simbolo nella finestra: {"<simbolo>": {"righe": int, "giorni": int}}."""
```
CLI: `python scripts/raccogli_funding.py --giorni 3` → stampa `scritti=N duplicati=M errori=K`.

Funzione di lettura già prevista (in `src/money/report_funding.py`):
```python
def tabella_giornaliera(path_jsonl: str) -> dict:
    """{"righe": [{"giorno","simbolo","n_funding","funding_medio","funding_somma","basis_medio",
    "primo_ts","ultimo_ts"}], "righe_saltate": int}"""
```

## 2. Algoritmo e contratto del file (passo per passo)
1. Per ogni simbolo e per la finestra richiesta, scaricare la storia funding dalla fonte pubblica
   (periodo di funding: **8 ore**; timestamp in **millisecondi UTC**).
2. Normalizzare ogni osservazione in una riga JSON **esattamente** con questo schema:
   `{"simbolo": str, "ts": int (ms UTC), "funding": float (frazione per 8h), "basis_pp": float,
   "fonte": "okx"}` — esempio reale:
   `{"simbolo": "BTC/USD:USD-310404", "ts": 1782720000000, "funding": -0.0001102044624311, "basis_pp": 0.0, "fonte": "okx"}`
   Il campo `basis_pp` resta `0.0` finché non esiste una fonte di mark/index price: la fonte
   funding non lo fornisce (§6, punto aperto).
3. Leggere il file esistente una volta e costruire l'insieme delle chiavi già presenti
   `(simbolo, ts)`. Scrivere **solo in append** le osservazioni con chiave nuova; contare le
   altre come `duplicati`.
4. Contare in `errori` ogni simbolo la cui richiesta fallisce; al termine, se
   `scritti + duplicati ≠ righe scaricate`, marcare il tick come fallito nel log.
5. Scrivere il file con una riga per record, UTF-8, `\n` finale; **mai riscrivere in place**.
6. Emettere nel log la riga `scritti=N duplicati=M errori=K` (una per tick).

## 3. Parametri e vincoli numerici (tutti espliciti)
| vincolo | valore | note |
|---|---|---|
| rate limit | ≤ 5 richieste/s | backoff esponenziale su HTTP 429 |
| timeout per richiesta | 20 s | massimo 3 retry per simbolo |
| finestra per tick | ≤ 7 giorni | il cron usa `--giorni 3` |
| storia minima accettata | 90 giorni | sotto questa soglia la copertura è dichiarata parziale |
| idempotenza | 1 scrittura per `(simbolo, ts)` | nessun duplicato ammesso |
| runtime del tick | < 120 s | per 10 simboli × 3 giorni |
| dipendenze | stdlib + `ccxt` | nessun'altra |
| path scrivibili | `data/`, `logs/` | nessun altro |
| simboli | 10 contratti USD-margined: BTC, ETH, SOL, XRP, DOGE, ADA, AVAX, LINK, LTC, DOT | suffissi `*-310404`, `*-310530`, `*-310523`, `*-310808` |

## 4. Stato attuale della raccolta (misurato al 2026-10-08)
2.932 righe; finestra 2026-06-29 → 2026-10-08 (101 giorni); 305 righe per 9 simboli su 10
(DOT 187 righe / 62 giorni); 17,9% dei periodi con funding negativo; cron attivo ogni 4 ore al
minuto `:13` sul nodo `mc2`; tick recenti con `errori=0`. Il consumatore di questi dati è la
misura di carry funding (spec P4), che richiede ≥ 30 giorni distinti per simbolo.

## 5. Test falsificabile (devono FALLIRE se l'implementazione è assente o sbagliata)
In `tests/test_raccoglitore_funding.py`:
- **T1 (idempotenza)**: due esecuzioni consecutive sulla **stessa finestra** ⇒ la seconda riporta
  `scritti=0` e **assert** che il numero di righe del file e il suo contenuto non cambiano.
- **T2 (guardia anti-ordini)**: `verifica_niente_ordini_sorgente(<modulo>)` è `True` sul modulo di
  raccolta e `False` su un modulo-esca che contiene una chiamata di invio ordini — **assert**
  statica sul sorgente, senza rete.
- **T3 (resilienza di rete)**: con la fonte irraggiungibile, `errori > 0` e **assert** che il file
  resta valido (nessuna riga parziale o troncata) e che il tick successivo recupera le righe.
- **T4 (deduplica su chiave)**: inserendo a mano nel file una riga già presente e rieseguendo,
  `scritti=0` — **assert** sul conteggio.

## 6. Criteri di accettazione (checklist misurabile)
- [ ] `python -m pytest tests/test_raccoglitore_funding.py tests/test_report_funding.py -q` → tutti verdi;
- [ ] `python scripts/raccogli_funding.py --giorni 3` → `errori=0` e
      `scritti + duplicati == righe scaricate`;
- [ ] append-only idempotente verificato da T1/T4;
- [ ] `verifica_niente_ordini_sorgente` presente e verde (T2);
- [ ] copertura per simbolo ≥ 3 osservazioni/giorno sulla finestra raccolta;
- [ ] **punto aperto documentato**: `basis_pp` resta `0.0` (la fonte funding non fornisce il
      mark/index price); un punto di raccolta basis separato si aggiunge solo se richiesto
      esplicitamente dalla misura che lo consuma.

## 7. Fuori scope, vincoli e impatto sul trading
- **Impatto sul trading: NULLO.** Nessun ordine, nessuna chiave privata, nessuna modifica ai
  moduli di esecuzione o ai bot; solo endpoint pubblici e scrittura su `data/` e `logs/`.
- **Divieti espliciti**: non introdurre percorsi che chiamino funzioni di invio ordini (la guardia
  T2 esiste per questo); non modificare i moduli dei costi; non scrivere fuori da `data/` e
  `logs/`.
- Qualunque estensione che introduca invio ordini richiede una **spec separata** e
  l'autorizzazione esplicita dell'owner.

## 8. Procedura di verifica (comandi esatti)
```bash
cd ~/money
python scripts/raccogli_funding.py --giorni 3      # atteso: scritti=N duplicati=M errori=0
python -m pytest tests/test_raccoglitore_funding.py tests/test_report_funding.py -q
tail -5 logs/raccolta_funding.log                  # storico dei tick del cron (ogni 4h)
python - <<'PY'
from money.report_funding import tabella_giornaliera
t = tabella_giornaliera("data/funding_xperp.jsonl")
print("righe aggregate:", len(t["righe"]), "| scartate:", t["righe_saltate"])
PY
```

## 9. Contesto (non necessario all'implementazione, per il registro)
Certificato di consegna in `prove/agent-zero/P8B/`; esito della tabella aggregata riportato in
`prove/REGISTRO_ESPERIMENTI.md` (sezione Infrastruttura). La raccolta alimenta la misura di carry
funding (spec P4), che è la sola famiglia non direzionale del progetto.
