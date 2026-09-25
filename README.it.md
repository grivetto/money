![money](assets/banner.png)

# money — «il pedaggio prima della strategia»

> **Nessuna strategia entra in produzione senza aver superato il cancello:** expectancy netta
> positiva **fuori campione**, ai **costi reali** del conto su cui girerà.
> Il cancello non è una linea guida: è codice, e il suo rifiuto è vincolante.

Sotto il nome *denaro* si sono succedute **quattro** codebase — `C:\dev\denaro` (Binance, mobile),
il precedente `money` (grid, DCA, scalper, hedge, futures, sentiment), `alpha-omega-trading`
(49.162 righe, 17 bot, tre macchine) e `~/denaro2` sulle VPS — e **nessuna ha guadagnato un euro**.
Non per difetti del codice: perché si è costruito *prima* il sistema e *dopo* si è cercato qualcosa
da catturare. Qui l'ordine è invertito, e il codice precedente vive in `legacy/`, tracciato con la
sua storia, come memoria di cosa è stato provato — non come base su cui costruire.

<p align="center">
  <a href="README.md"><b>English</b></a> •
  <a href="README.it.md"><b>Italiano</b></a> •
  <a href="README.es.md"><b>Español</b></a> •
  <a href="README.th.md"><b>ไทย</b></a>
</p>

---

## 📊 Stato in sintesi — 2026-09-25

| | |
| :--- | :--- |
| **Test** | **136 passati**, `ruff` pulito, in **due ambienti indipendenti** |
| **Strategie misurate** | **3** famiglie (una per nodo), tutte giudicate ai costi reali |
| **Verdetti** | **3 archiviate** — niente promosso, quindi niente in produzione |
| **Ordini reali inviati** | **0** (e resta così finché il cancello non promuove e il proprietario non finanzia) |
| **Capitale** | **26,0030 EUR** sul conto OKX main, verificati in sola lettura; la flotta live contiene ~0,15 EUR di dust |
| **Ultimo commit** | `main` — vedi `git log` per la testa corrente |

Repository: `C:\dev\money` in locale, `github.com/grivetto/money` in remoto. Pacchetto Python sotto
`src/money/`, test sotto `tests/`, prove sotto `prove/`, decisioni sotto `docs/`.

---

## 🏛 Architettura — dalla barra al verdetto

![Dalla barra al verdetto](assets/architettura.svg)

La pipeline è a senso unico e non ha scorciatoie: **entrano barre reali, esce un verdetto
numerico**. Niente entra in produzione da sinistra del cancello.

```
OKX EEA (eea.okx.com)          barre OHLCV reali, point-in-time, in cache, nessun look-ahead
      |
      v
money/dati.py                  Barra, SerieBarre, Scarica, walk-forward con embargo
      |
      v
money/ricerca/                 una ipotesi per file: simula(...) -> Esito
      |                        qui niente puo' promuovere niente da solo
      v
money/cancello.py              8 criteri, 3 verdetti, ogni motivo porta il suo numero
      |
      v
promosso / archiviato / insufficiente          il verdetto e' vincolante
```

### Le tecnologie usate

| Livello | Tecnologia | Perché questa |
| :--- | :--- | :--- |
| Linguaggio | **Python** (`requires-python >= 3.11`; eseguito su 3.12.3 e 3.14.5) | l'unico linguaggio in cui il rig di ricerca del progetto precedente si poteva verificare riga per riga |
| Accesso all'exchange | **ccxt >= 4.0** contro **`eea.okx.com`** | le chiavi EU funzionano *solo* sull'endpoint EEA: su `okx.com` ogni chiave risponde `50119 "API key doesn't exist"`, che sembra esattamente una chiave morta |
| Dati di mercato | **OKX EEA REST**, candele giornaliere e 4h/1h, paginazione | una sede, un timeframe per nodo: il rig di ricerca e il rig live devono leggere gli stessi dati |
| Integrità dei dati | **`money/dati.py`** — epoch in millisecondi UTC, `vista_fino_a`, `finestre_indici`, `iterazioni_walk_forward(embargo=1)`, `SerieBarre.verifica()` | il look-ahead è il difetto che produce numeri eccellenti e conti in perdita, e non lascia traccia |
| Modellazione del dominio | **`dataclasses`** (`frozen=True`), `enum`, type hints completi, funzioni pure | il modulo dei costi non fa I/O: non può mentire, e si testa in millisecondi |
| Modello dei costi | **`money/costi.py`** — frazioni, mai percentuali (`0.0035`, non `0.35`) | così nessun errore di fattore 100 può nascondersi in una moltiplicazione |
| Cancello | **`money/cancello.py`** — IC bootstrap al 90% con seme fisso, t-stat, profit factor, drawdown, copertura del pedaggio, rilevanza economica, indipendenza dai blocchi | un criterio che non vedi non può essere discusso |
| Test | **pytest >= 8** (136 test), **ruff >= 0.5** (`line-length = 120`, regole `E9`+`F`) | solo regole che intercettano errori reali: una CI che grida sempre non protegge niente |
| Config e pacchetto | **PyYAML >= 6**, **setuptools** (layout `src/`) | `pytest` importa il pacchetto da `src/` senza installazione, così la suite gira su un checkout appena fatto |
| Prove | **artefatti JSON e testo** in `prove/`, decisioni in Markdown in `docs/` | una misura che non si può rileggere è un'opinione |
| Controllo di versione | **git**, un solo scrittore per percorso, systemd e cron da versionare in `deploy/` | nel progetto precedente `systemd` e `crontab` non erano versionati, ed è stata la causa di 10 guasti su 12 |
| Deliberatamente **assenti** | nessun LLM nel percorso caldo, nessun framework async, nessun codice che invia ordini, nessuna dashboard web | il costo per decisione di un LLM è comparabile all'edge che si sta cercando; l'esecuzione si costruisce *dopo* la prima promozione |

### Le tre macchine

Tre macchine, **una famiglia di strategie ciascuna**, un conto OKX dedicato ciascuna. Non è una
scelta estetica: è la correzione di un difetto misurato sul campo.

| nodo | famiglia | cosa deve dimostrare | verdetto |
| :--- | :--- | :--- | :--- |
| **A** | trend a orizzonte lungo | che sopravvive al pedaggio reale | **archiviato** |
| **B** | griglia adattiva | che la spaziatura minima batte il pedaggio | **archiviato** |
| **C** | momento a 4 ore | che regge i costi | **archiviato** |

**Perché un conto per macchina.** Nel progetto precedente ogni bot dichiarava il capitale
dell'*intero* conto: con 7 bot il rischio aggregato era il **14% invece del 2%**, e lo stop di un
bot liquidava l'inventario di un altro. Misurato, non ipotizzato.

**Perché il rischio è di portafoglio.** Il budget del 2% è del capitale *totale*: tre nodi non
possono rischiare il 2% ciascuno.

---

## 🚦 Il cancello — 8 criteri, 3 verdetti

Tutti e otto devono passare. Il verdetto è uno di tre, e "insufficiente" è un verdetto vero, non
una scusa.

| # | Criterio | Soglia |
| :--- | :--- | :--- |
| 1 | Numerosità | `>= 30` operazioni, altrimenti **insufficiente** |
| 2 | Expectancy | IC bootstrap al 90%, estremo inferiore `> 0`, seme fisso |
| 3 | t-statistic | `> 1,65` (una coda, 5%) — riportato **sempre**, anche quando fallisce |
| 4 | Profit factor | `> 1,20` |
| 5 | Drawdown | `<= 25%` del capitale |
| 6 | **Pedaggio coperto** | expectancy netta `>= 3x` il costo per giro della tariffa assunta |
| 7 | Rilevanza economica | `>= 10 EUR/anno` attesi, su un capitale di riferimento di 1000 EUR |
| 8 | Indipendenza dai blocchi | togliendo il blocco migliore l'expectancy non deve diventare negativa |

Il criterio 6 è quello che il progetto precedente non aveva mai avuto. Il criterio 8 esiste perché
il progetto precedente aveva **tutto il rendimento in un blocco su tre** e nessuno se n'era
accorto.

---

## 💰 L'economia — misurata, non stimata

La tariffa non è più un'assunzione: si legge dal conto.

| tariffa | maker | taker | giro misto | provenienza |
| :--- | ---: | ---: | ---: | :--- |
| `okx_eea_spot` | 0,20% | 0,35% | **0,550%** | confermata dal conto (`privateGetAccountTradeFee`) |
| `okx_eea_con_perp` | 0,08% | 0,10% | 0,180% | assunzione conservativa, tenuta di proposito |
| `okx_eea_swap_lv1` | 0,02% | 0,05% | **0,070%** | misurata sul conto, valida solo con i derivati attivi (`acctLv 2`) |

**Aprire gli X-Perps abbassa il pedaggio di 7,86 volte senza aggiungere un euro di capitale.** Il
conto oggi è `acctLv: "1"` (solo spot): la tariffa swap è uno scenario, non un costo pagato, e la
suite di test vieta di sostituire l'assunzione con il numero misurato finché il livello del conto
non sale davvero.

E il numero che il progetto precedente non aveva mai calcolato: **sotto 4 EUR di capitale**, con un
minimo d'ordine di 1 EUR e un quarto per posizione, **non esiste nessun ordine sensato**.

---

## 🧪 Testing — e la riproduzione indipendente

```
136 passed
ruff check . → All checks passed
```

Eseguiti in **due ambienti**, da un **clone pulito** di `origin/main`:

| | ambiente A (autore) | ambiente B (riproduzione) |
| :--- | :--- | :--- |
| macchina | workstation Windows | mc2, Linux |
| Python | 3.14.5 | 3.12.3 |
| ccxt | 4.5.40 | 4.5.84 |

Le misure si riproducono **cifra per cifra**: nodo A `+1,959026%`, t `0,821`, PF `1,420`,
DD `53,18%`; nodo B `-1,1823%`, t `-8,539`, PF `0,569`, copertura del pedaggio `-2,150x`. Vedi
`docs/04_riproduzione_indipendente_2026-09-25.md`.

Quello che dimostra è che i numeri non dipendono dall'ambiente e che il repository pubblicato è
autosufficiente. Quello che **non** dimostra è che il metodo sia giusto: è lo stesso codice
eseguito altrove. La verifica forte sarebbe **una seconda implementazione indipendente** — due
agenti che scrivono due motori e confrontano i numeri. Non è stata fatta, e dirlo è più utile che
nasconderlo dietro un "verificato".

---

## 📉 I tre verdetti — cosa ha archiviato il cancello, e perché

| nodo | verdetto | il numero che lo decide |
| :--- | :--- | :--- |
| A — trend lungo | **archiviato** | in campione `+1,96%/op`, **fuori campione `-1,21%/op`** (t `-0,44`); solo 2 finestre corte su 9 positive, e **0 finestre con >= 5 operazioni** |
| B — griglia adattiva | **archiviato** | **1581 operazioni**, netta `-1,18%/op`, **t `-8,54`**, PF `0,569` |
| C — momento 4h | **archiviato** | 4h netta `-0,36%/op`, 1d netta `-1,67%/op`; la leva dei costi si vede (copertura `-0,654` → `1,716`, EUR/anno `-208` → `+69,61`) e **non basta lo stesso** |

Tre risultati che sopravvivono ai verdetti:

1. **Per il trend il pedaggio è irrilevante.** Fuori campione l'edge cambia segno; aprire gli
   X-Perps vale **0,94 EUR/anno** su quell'edge. Nessun taglio di commissioni crea un edge.
2. **La griglia ha un difetto strutturale, non di taratura.** Una sweep a spaziatura fissa è
   negativa da `0,10%` a `7,00%`; il pareggio **non è stato raggiunto nemmeno a 12,7x il
   pedaggio**, e il 98,672% delle operazioni aveva spaziatura *sopra* il pedaggio (4,4x–8,6x)
   perdendo comunque 1,18% per operazione. Il motivo: +1 ciclo rende `s`, ma −1 rottura di banda
   liquida l'inventario a mercato e costa circa `3s`. La diagnosi del progetto precedente ("la
   spaziatura è sotto il pedaggio") era **corretta ma incompleta**: alzarla non basta.
3. **La leva dei costi è reale e ora misurata, e non promuove nulla.** Sul 4H cambia 1 criterio su
   8 (rilevanza economica) e il verdetto non si muove.

Verbale completo: `docs/03_verdetti_2026-09-25.md`, prove grezze in `prove/`.

---

## 🚫 Cosa è vietato qui (lezioni pagate in contanti)

1. **Vietato costruire esecuzione prima di un edge promosso.** Il progetto precedente aveva 17 bot
   e zero trade verificati.
2. **Vietato dichiarare performance senza riconciliarla** con saldi e ordini reali.
3. **Vietato un capitale configurato che il conto non ha.** Un nodo senza fondi deve dire
   `NON FINANZIATO`, non saltare i tick in silenzio (1.486 tick persi senza un solo allarme).
4. **Vietato un ordine senza chiave di idempotenza.** Un crash fra invio e salvataggio lascia
   denaro impegnato che il bot non vede.
5. **Vietata la telemetria che legge come fossile.** Un file vecchio non è un bot che gira.
6. **Vietato un LLM nel percorso caldo.** In shadow sì, a decidere no.
7. **Vietato il path drift**: systemd e cron versionati in `deploy/`, con `PROJECT_ROOT`
   parametrico. È stata la causa di 10 guasti su 12.
8. **Vietato abbassare una soglia per far passare qualcosa.** Se il cancello archivia, si archivia.

---

## 📁 Struttura del repository

```
money/
├── src/money/
│   ├── costi.py              la matematica del pedaggio: movimento minimo, frequenza sostenibile, fattibilita'
│   ├── dati.py               barre OHLCV reali, point-in-time, cache, nessun look-ahead
│   ├── cancello.py           il cancello di promozione: 8 criteri, 3 verdetti
│   └── ricerca/              le ipotesi, una per file
│       ├── trend_lungo.py        nodo A — trend a orizzonte lungo
│       ├── griglia_adattiva.py   nodo B — griglia adattiva
│       └── momento_4h.py         nodo C — momento a 4 ore
├── scripts/                  runner di misura, uno per ipotesi, piu' le verifiche indipendenti
├── tests/                    136 test offline
├── docs/                     01 decisione · 02 specifica del banco a secco · 03 verdetti · 04 riproduzione
├── prove/                    prove grezze: verdetti, JSON, confronto con l'evidenza precedente
├── assets/                   banner e diagramma di architettura
├── legacy/                   la codebase precedente, con la sua storia — memoria, non fondamenta
└── pyproject.toml
```

---

## 🛠 Avvio rapido

```bash
git clone https://github.com/grivetto/money.git
cd money

# la matematica del pedaggio
python src/money/costi.py

# tutta la suite (offline, nessuna chiave, nessuna rete)
python -m pytest tests -q          # 136 passed
ruff check .

# rimisura una ipotesi su barre reali OKX EEA (nessuna chiave: dati pubblici)
export MONEY_CACHE=/tmp/money_cache
python scripts/misura_trend_lungo.py

# guarda il cancello decidere sulla stessa serie a due pedaggi diversi
python demo_cancello.py
```

---

## 🚧 Lavoro aperto, in ordine di valore

1. **Decisione del proprietario — assessment X-Perps.** `acctLv` 1 → 2. È la leva più grande che il
   progetto abbia, vale 7,86x sul pedaggio, e non è codice. Su EEA può dipendere da MiCA: da
   verificare con OKX.
2. **Decisione del proprietario — dove vanno i 26 EUR.** Il conto main non è un nodo:
   l'architettura è un nodo = una famiglia = un subaccount dedicato.
3. **Decisione del proprietario — i 1000 EUR.** A 26 EUR la soglia di rilevanza del cancello
   chiede il 38,5% netto all'anno; a 1000 EUR ne chiede l'1,0%. Il capitale non crea l'edge: rende
   il guadagno visibile.
4. **Banco di prova a secco** (specifica in `docs/02`): legge il saldo reale, applica la guardia
   `NON FINANZIATO`, calcola l'ordine e **non invia niente**. L'implementazione appartiene a
   `deploy/`.
5. **Una quarta domanda, non una quarta strategia.** Con tre famiglie archiviate, la domanda non è
   più "quale strategia adesso" ma **cosa rende un edge trovabile** con questo pedaggio, su questi
   mercati, con questo capitale.

---

## 🗺 Percorso di scalabilità

```
cancello (fatto) → primo edge promosso (manca) → capitale (26 EUR ora, 1000 EUR dopo) → frequenza
```

L'ordine non è negoziabile, ed è l'esatto inverso di quello che ha fatto il progetto precedente.

---

## ⚖️ Disclaimer

Questo è codice di ricerca su un conto reale da 26 EUR. Non invia ordini, e non ha un modulo di
esecuzione per scelta. Niente di quanto scritto è consulenza finanziaria. Le cripto-attività
possono perdere tutto il loro valore; la matematica in `costi.py` esiste esattamente per mostrare
quanto spesso succede in silenzio, un pedaggio alla volta.

## 📄 Licenza

**In questo repository non esiste alcun file `LICENSE`.** Il progetto padre
(`alpha-omega-trading`) è rilasciato nel **pubblico dominio**. Una licenza per `money` non è stata
dichiarata e non è stata inventata qui: è una decisione del proprietario.
