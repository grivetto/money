<p align="center">
  <img src="assets/banner.png" alt="money" width="100%"/>
</p>

# money — «il pedaggio prima della strategia»

<p align="center">
  <img src="assets/icon.svg" alt="money — icon" width="72" height="72"/>
</p>

<p align="center">
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/Python-3.12+-3776AB?style=flat-square&logo=python&logoColor=white" alt="Python 3.12+"></a>
  <a href="https://www.okx.com/en-eu"><img src="https://img.shields.io/badge/OKX-EEA-000000?style=flat-square" alt="OKX EEA"></a>
  <a href="https://github.com/ccxt/ccxt"><img src="https://img.shields.io/badge/CCXT-4.x-1E88E5?style=flat-square" alt="CCXT"></a>
  <a href="https://www.docker.com/"><img src="https://img.shields.io/badge/Docker-Containerized-2496ED?style=flat-square&logo=docker&logoColor=white" alt="Docker"></a>
  <a href="https://www.zabbix.com/"><img src="https://img.shields.io/badge/Zabbix-7.0_LTS-D40000?style=flat-square&logo=zabbix&logoColor=white" alt="Zabbix 7.0 LTS"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-EUPL_1.1-blue.svg?style=flat-square" alt="EUPL 1.1 License"></a>
</p>

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

## 📊 Stato in sintesi — 2026-10-03

> **TL;DR** — un rig di ricerca onesto su denaro vero: il cancello ha archiviato tutte le famiglie
> misurate finora; un canary live (carry DOGE) è dentro la finestra di validazione; capitale
> ~1.100 EUR, e la scala del carry parte solo dopo la review del 15/10.

| | |
| :--- | :--- |
| **Test** | **533 passati**, `ruff` pulito, in **due ambienti indipendenti** |
| **Strategie misurate** | **3** famiglie (una per nodo), tutte giudicate ai costi reali — più gli esperimenti pre-registrati della serie P (P1–P13), ogni verdetto congelato in `prove/` |
| **Verdetti** | **3 archiviate** (famiglie) — il carry live **C1** è nella finestra di validazione canary (review 15/10); **P10** (momentum cross-timeframe): *insufficiente* (23 operazioni < 30 — conservata, non archiviata) |
| **Canary C1 live** | carry di funding DOGE su OKX EEA, completamente riconciliato: funding **+0,0076 USDC**, hedge marcato **+0,20 USDC**, netto ≈ **+0,009 USDC** al giorno 3/14 — taglia volutamente minima |
| **Ordini reali inviati** | **0** dalle strategie di questo repo — il primo bot live del progetto (carry **C1**, DOGE) opera su OKX EEA ed è tracciato in `alpha-omega-trading` (`docs/16`) |
| **Capitale** | **~1.100 EUR** sui conti OKX (verificati in sola lettura) — l'owner ha depositato **+1.000 EUR il 03/10** per la scala del carry (deploy subordinato alla review del 15/10) |
| **Squadra & ops** | **8 esecutori + 1 regia su 3 macchine** (`A0-win` · `A0-mc2` · `DSH-mc2/omarchy/win` · `opencode-mc2/omarchy` · `agy-omarchy`; consegne riviste da Hermes), alerting attivo (`@DenaroAlertBot`), check post-riavvio 34/34 |
| **Ultimo commit** | `main` — vedi `git log` per la testa corrente |

Repository: `C:\dev\money` in locale, `github.com/grivetto/money` in remoto. Pacchetto Python sotto
`src/money/`, test sotto `tests/`, prove sotto `prove/`, decisioni sotto `docs/`.

---

## 📜 La storia — da «La Baracca» al rig misurato

*«La Baracca»* è l'italiano per un aggeggio improvvisato che ha sempre bisogno di un'altra toppa —
e per un anno, tra tentativi e strumenti AI diversi (OpenClaw, Hermes, Agent Zero, DeepSeek TUI),
il progetto è stato esattamente questo: bot che giravano, numeri che non si riconciliavano, zero
euro guadagnati. Il punto di svolta non è stata una feature. È stata una decisione: smettere di
costruire, cominciare a misurare — e fare del misurare un cancello.

| Quando | Cosa è successo | La lezione |
| :--- | :--- | :--- |
| **2026, primavera → estate** | La serie `denaro`: quattro codebase una dopo l'altra — Binance su un telefono, il primo `money` (grid, DCA, scalper, hedge, futures, sentiment), `alpha-omega-trading` (49.162 righe, 17 bot, tre macchine), `denaro2` sulle VPS | costruire *prima* il sistema e cercare *dopo* qualcosa da catturare non funziona |
| **2026-09** | L'audit di `alpha-omega-trading` (`docs/01`): «il sistema funziona, su una baracca non supervisionata» — servizi non versionati, capitali che i conti non avevano, 1.486 tick persi in silenzio, 10 guasti su 12 da un solo path obsoleto | fermarsi; rifondare |
| **2026-09-23 → 30** | La rifondazione: questo repository trasforma la regola in codice — il **cancello a 8 criteri**; gli esperimenti della serie P sono pre-registrati, misurati e giudicati uno a uno; ogni famiglia misurata finora è archiviata | il cancello non è una linea guida: è codice, e il suo rifiuto è vincolante |
| **2026-10-01** | Il **primo ordine reale** del progetto viene eseguito su OKX EEA; nasce il **canary C1** (carry di funding DOGE, spot + hedge perp) — taglia minima, completamente riconciliato | un esperimento, non un raccolto |
| **2026-10-03** | L'owner deposita **+1.000 EUR**; la flotta guadagna i suoi agenti (`DSH`, `A0`, `opencode`, `agy`), l'alerting live e il check post-riavvio (34/34) | il capitale non crea l'edge — rende *visibile* il guadagno |

Oggi il codice vecchio vive in `legacy/` come memoria, non come fondamenta, e solo il rig di
ricerca può avvicinarsi alla produzione: **prima cosa catturare, poi il sistema.** Questo
repository è il "poi".

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

### Il sistema attorno alla pipeline — aggiornato 03/10/2026 (sera)

![Denaro — foto del sistema, 03/10/2026](FOTO_SISTEMA_2026-10-03.png)

```
                     ┌──────────────────────── mc2 — l'hub ──────────────────────────┐
                     │ Hermes — direzione, misure, review, unico scrittore git       │
                     │ fabbrica master — un'azione ogni 3 s (×100 dal 02/10)         │
                     │ Zabbix 7.0 «Money» (38 host) · A0-mc2 + DSH-mc2 (:3080)       │
                     │ fabbrica worker (5 s) · raccolta funding (4 h) · canale DSH   │
                     └───────────┬─────────────────────────────────────┬─────────────┘
                                 │ tailscale / ssh                     │ brief e consegne
                ┌────────────────▼───────────────────┐   ┌────────────▼────────────────────┐
                │ MARCODG1 — trading e web           │   │ A0-win + DSH-win (PC, Windows)  │
                │ · canary live — carry DOGE, 1×     │   │ operai / peer, protocollo file  │
                │ · banco a secco — read-only, rc=2  │   └─────────────────────────────────┘
                │ · aggregator :8912 → 34 bot        │
                │ · dashboard :8913 · landing :8914  │
                │ · Grafana :3000 · health :8911     │
                └────────────────────────────────────┘
     nuvola — posto di monitoraggio: health · exporter · Zabbix agent + tunnel · fabbrica worker (5 s)

     aiutanti — opencode-mc2 · opencode-omarchy · agy-omarchy: esecutori free
     JEV (TypeSafe): giudice advisory
```

*Un solo anello: idea → spec pre-registrata (`coda_catena/` + `REGISTRO`) → esecutore → review
(test rieseguiti nel repo) → misura (artefatti congelati in `prove/`) → cancello a 8 criteri →
promozione/archivio → banco a secco → canary → live a taglia minima. Gli esecutori — `A0-mc2`,
`A0-win`, `DSH-mc2/omarchy/win`, `opencode-mc2/omarchy`, `agy-omarchy` — consegnano a Hermes; il
**nodo agenti** (Omarchy) ospita `DSH-omarchy` e `opencode-omarchy` come servizi systemd
(loopback-only, raggiunti via tunnel ssh); niente entra senza review. Visual:
[`FOTO_SISTEMA_2026-10-03.html`](FOTO_SISTEMA_2026-10-03.html) · [`.png`](FOTO_SISTEMA_2026-10-03.png) ·
[`FOTO_SQUADRA_2026-10-03.html`](FOTO_SQUADRA_2026-10-03.html) · [`.png`](FOTO_SQUADRA_2026-10-03.png).
Foto precedenti: [`ARCHITETTURA_2026-09-30.md`](ARCHITETTURA_2026-09-30.md) ·
[`ARCHITETTURA_2026-10-01.md`](ARCHITETTURA_2026-10-01.md).*

![La squadra — 03/10/2026](FOTO_SQUADRA_2026-10-03.png)

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
| Test | **pytest >= 8** (533 test), **ruff >= 0.5** (`line-length = 120`, regole `E9`+`F`) | solo regole che intercettano errori reali: una CI che grida sempre non protegge niente |
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
533 passed
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
├── tests/                    533 test offline
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
python -m pytest tests -q          # 533 passed
ruff check .

# rimisura una ipotesi su barre reali OKX EEA (nessuna chiave: dati pubblici)
export MONEY_CACHE=/tmp/money_cache
python scripts/misura_trend_lungo.py

# guarda il cancello decidere sulla stessa serie a due pedaggi diversi
python demo_cancello.py
```

---

## 🚧 Lavoro aperto, in ordine di valore

1. **Il primo edge promosso manca ancora — è il titolo onesto.** Il cancello ha archiviato ogni
   famiglia misurata finora; la tesi viva (carry di funding) è in validazione, non ancora promossa.
   Finché un edge non passa, nulla scala: è la regola uno del percorso, non un umore.
2. **Review del canary C1 — 15/10.** La finestra di 14 giorni chiude con criteri pre-registrati
   (`alpha-omega-trading`, `docs/16`); con esito positivo parte la scala multi-coppia del carry —
   piano scritto e pronto (`docs/20`), subordinato all'OK dell'owner.
3. **Release di validazione M1** (regole dal 30/09): block bootstrap, DSR/PBO, scenari di costo
   ×3 — `coda_catena/M1_release_validazione.md`; propone anche l'allineamento cancello↔mandato
   (DD 10% al sizing di deploy) — in attesa dell'OK dell'owner.
4. **Coda di ricerca:** P10 chiusa *insufficiente* (23 < 30 operazioni, non archiviata) — la
   prossima corsia la rimisura con più campioni. Il registro della serie P
   (`prove/REGISTRO_ESPERIMENTI.md`) è l'unica entrata per nuove ipotesi.
5. **Una quarta domanda, non una quarta strategia.** Con tre famiglie archiviate, la domanda non è
   più "quale strategia adesso" ma **cosa rende un edge trovabile** con questo pedaggio, su questi
   mercati, con questo capitale.

---

## 🗺 Percorso di scalabilità

```
cancello (fatto) → primo edge promosso (manca ancora) → capitale (arrivato: ~1,1k EUR, deploy subordinato alla review del 15/10) → frequenza
```

L'ordine non è negoziabile, ed è l'esatto inverso di quello che ha fatto il progetto precedente.

---

## ⚖️ Disclaimer

Questo è codice di ricerca su un conto reale da **~1.100 EUR** — di cui un canary (carry di
funding DOGE) opera a taglia volutamente minima, autorizzato dall'owner e completamente
riconciliato. Le strategie di questo repo non inviano ordini, e il repo non ha un modulo di
esecuzione per scelta. Niente di quanto scritto è consulenza finanziaria. Le cripto-attività
possono perdere tutto il loro valore; la matematica in `costi.py` esiste esattamente per mostrare
quanto spesso succede in silenzio, un pedaggio alla volta.

## 📄 Licenza

Rilasciato sotto la **European Union Public Licence v. 1.1 (EUPL-1.1)**. Vedi [LICENSE](LICENSE).
Il progetto padre (`alpha-omega-trading`) è rilasciato sotto la stessa licenza.
