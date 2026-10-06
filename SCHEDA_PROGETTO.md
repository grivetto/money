# 🎛️ Scheda progetto — «money» (Denaro)

**Aggiornata: 2026-10-06** · generata dall'agente Hermes (mc2) su richiesta del proprietario
per **analisi esterna (Manus AI)**. Documento autosufficiente: descrive il progetto anche a chi
non ha accesso al repository. **Nessun segreto è incluso**; i nodi sono indicati per nome.

---

## 1. In una riga

> Un banco di ricerca su **denaro vero** per il trading sistematico crypto su **OKX EEA**:
> prima si misura se un edge esiste — ai costi reali dell'account — poi lo si automatizza.
> Il cancello di promozione è codice, e il suo verdetto è vincolante.

Capitale attuale: **~1.100 EUR** (deposito del proprietario del 03/10, riconciliato read-only).
**Nessuna strategia è ancora «promossa»: è l'headline onesta del progetto.**

## 2. Lo stato al 06/10/2026 (TL;DR)

| | |
| :--- | :--- |
| **Ricerca** | Serie P1–P14 + 3 famiglie storiche: **tutte archiviate** tranne *P10=insufficiente* e *P12=descrittiva*. Nessuna promozione. Il filone **carry/funding** è l'unico vivo. |
| **Esecuzione** | **1 canary reale** (carry funding DOGE, spot+perp 1×) su OKX EEA — taglia minima, piena riconciliazione; **review 15/10** con criteri pre-dichiarati. |
| **Capitale** | ~1.100 EUR; deploy della scala carry **gated** sulla review del 15/10 (piano pronto, `docs/20`). |
| **Infrastruttura** | «Fabbrica» ×100 (tick 3s): oltre **139.000 tiri**; job-store; gate JEV; watchdog anti-silenzio; alert Telegram. |
| **Squadra** | **11 esecutori su 4 macchine + regia** (Hermes); consegne con hash byte-exact, review obbligatoria. |
| **Qualità** | **558 test verdi** offline, `ruff` pulito, misure riproducibili in ambienti indipendenti. |

## 3. Cos'è il progetto (contesto)

Sotto il nome *denaro* si sono succedute **quattro** codebase — nessuna ha mai guadagnato un euro.
Il problema non erano i bug: si costruiva *prima* il sistema e si cercava *dopo* qualcosa da
catturare. Questa è la rifondazione (23–30/09/2026): **l'ordine è invertito** — prima si misura
se esiste un edge, poi lo si automatizza. Il codice precedente vive in `legacy/` con la sua
storia: memoria, non fondazione.

| Quando | Cosa | Lezione |
| :--- | :--- | :--- |
| primavera–estate 2026 | le 4 codebase precedenti (ultime: `alpha-omega-trading`, 17 bot, 3 macchine; `denaro2`) | costruire prima e cercare dopo non funziona |
| 2026-09 | audit di `alpha-omega-trading`: «il sistema funziona, su una baracca non supervisionata» (1.486 tick persi in silenzio; 10 incidenti su 12 da un path stantio) | fermarsi; rifondare |
| 2026-09-23→30 | rifondazione: nasce **il cancello** a 8 criteri; gli esperimenti P vengono pre-registrati, misurati, giudicati uno a uno | il cancello non è una linea guida: è codice |
| 2026-10-01 | **primo ordine reale** del progetto (canary C1, carry funding DOGE) | un esperimento, non un raccolto |
| 2026-10-03 | deposito **+1.000 EUR**; la flotta guadagna i suoi agenti, alerting live, post-reboot check | il capitale non crea l'edge — lo rende *visibile* |

## 4. Architettura (nodi, servizi, rete)

```
                 ┌────────────────────── mc2 — hub / regia ──────────────────────┐
                 │ Hermes (regia: misure, review, dispatch, git)                 │
                 │ fabbrica master ×100 (tick 3s) · job-store · gate JEV · lint   │
                 │ repo ~/money · A0-mc2 · DSH-mc2 (:4080) · crontab · Zabbix     │
                 └───────┬────────────────────────────────┬──────────────────────┘
                         │ Tailscale / ssh                 │ brief & consegne (file)
        ┌────────────────▼──────────────────┐   ┌─────────▼──────────────────────┐
        │ MARCODG1 — trading + web          │   │ PC Windows (dietro NAT)        │
        │ · canary C1 (DOGE carry, 1×)      │   │ · A0-win · DSH-win (:3080)     │
        │ · banco a secco read-only (rc=2)  │   │ · opencode/agy (esecutori)     │
        │ · web: health :8911 · aggregator  │   └────────────────────────────────┘
        │   :8912 · dashboard :8913 ·       │
        │   landing :8914 · Grafana :3000   │        ┌───────────────────────────┐
        │ · Zabbix · cloudflared · watchdog │        │ OKX EEA (eea.okx.com)     │
        └───────────────────────────────────┘        │ spot · X-Perps · funding  │
   nuvola: monitoring post (health, exporter,        └───────────────────────────┘
   Zabbix agent, worker)      omarchy: nodo agenti (DSH-omarchy :5080,
                              opencode-omarchy; loopback + tunnel ssh)
```

- **Rete**: Tailscale tra i nodi; nessuna porta pubblica per gli agenti; push git **solo via mc2**.
- **Un bot per conto** (regola dura), capitali isolati per strategia.
- **Web**: `denaro.grivetto.eu` (dashboard live) e `web.grivetto.eu` (landing) via cloudflared.

## 5. La pipeline di ricerca (il cuore del progetto)

```
IDEA → candidati.json → spec pre-registrata (coda_catena/ + REGISTRO: varianti dichiarate PRIMA)
     → esecutore (A0 / DSH / opencode / agy) → consegna con MANIFEST sha256
     → review Hermes (test RIESEGUITI nel repo) → integrazione (commit [hermes])
     → MISURA su dati reali (artefatti in prove/) → CANCELLO (8 criteri)
     → promossa | archiviata | insufficiente → banco a secco → canary → live taglia minima → scala
```

**Il cancello** (`src/money/cancello.py`) — tutti e 8 devono passare:

| # | Criterio | Soglia |
| :--- | :--- | :--- |
| 1 | Numerosità | ≥ 30 operazioni (altrimenti «insufficiente») |
| 2 | Expectancy | IC bootstrap 90%, estremo inferiore > 0 |
| 3 | t-statistic | > 1,65 (sempre riportato, anche se fallisce) |
| 4 | Profit factor | > 1,20 |
| 5 | Drawdown | ≤ 25% del capitale |
| 6 | **Pedaggio coperto** | expectancy netta ≥ 3× il costo di round-trip |
| 7 | Rilevanza economica | ≥ 10 EUR/anno su 1000 EUR di riferimento |
| 8 | Indipendenza dai blocchi | togliendo il blocco migliore, expectancy non negativa |

Il protocollo «referee ostile» (`docs/18`) blocca per costruzione: look-ahead, survivorship,
data snooping, overfitting. Ogni misura nasce da una voce nel registro **prima** del primo numero.

## 6. Verdetti della ricerca (stato al 06/10)

| Esperimento | Tema | Verdetto | Il numero che decide |
| :--- | :--- | :--- | :--- |
| P1 chandelier ATR | stop in uscita | ❌ archiviata | lo stop peggiora tutto (DD 55,6%) |
| P2 vol targeting | sizing | ❌ archiviata | DD serializzato giù, DD di portafoglio no |
| P3 filtro SMA200 | trend | ❌ archiviata | 6/8: exp +9,01%/op ma t 1,58 e DD 45,5% |
| P5 Donchian esteso | trend | ❌ archiviata | l'edge non regge l'allargamento (61 coppie) |
| P6 cap concorrenza | portafoglio | ❌ archiviata | DD portafoglio 37,8% > 25% |
| P10 momentum cross | momentum | ⚠️ **insufficiente** | 23 op < 30 (non promuove/non archivia) |
| P11 vol breakout ATR | volatilità | ❌ archiviata | DD 77,2%; exp −4,60% |
| P12 funding regime | carry | 📝 descrittiva | regola «uscita al primo negativo» perde 0/10 netto → baseline = always-on |
| P13 cointegrazione | pairs | ❌ archiviata | 0 coppie su 45 passano lo screening |
| P14 momentum universo | momentum | ❌ archiviata | OOS: exp −1,93%, DD 73,3%; 7/8 KO |
| Famiglie A/B/C | trend / grid / 4h | ❌ archiviate | vedi `docs/03` (grid: difetto strutturale, non di tuning) |

**Infrastruttura di ricerca integrata** (non consuma gradi di libertà): P8/P8B raccoglitore
funding+basis (cron 4h), P9 verificatore di provenienza, E1 economia unitaria (schede costo-edge),
J1 job-store della fabbrica, PROTCON (protocollo di consegna atomico), C1REV (review del canary).

**Rivelazioni chiave finora:**
1. **Funding EEA ≠ funding globale**: su OKX EEA BTC/ETH hanno funding *negativo* → il carry va
   scelto sui dati del venue, non sulla letteratura.
2. **Il pedaggio è il vero giudice**: spot round-trip 0,550%; con X-Perps scende a 0,070% (7,86×).
   Sotto ~4 EUR di capitale *non esiste un ordine sensato*.
3. **Il trend muore OOS** (il pedaggio non è il collo di bottiglia: il segno dell'edge sì).
4. **Il momentum cross è chiuso con potenza adeguata** (P10 → P14 su universo ampio: archiviato).

## 7. L'unico esperimento vivo: canary C1

- **Carry funding DOGE**: spot long + X-Perp short (1×, isolated), taglia minima — aperto il
  01/10 alle 00:43, **prima esecuzione reale del progetto**.
- Finestra di validazione 14 giorni; **review il 15/10** con criteri pre-dichiarati (`docs/16`);
  in caso di esito verde → deploy della scala multi-pair (piano `docs/20`, gated sull'owner).
- Stato: riconciliazione OK, funding incassato, monitor ogni 10–30 min; alert Telegram.

## 8. La «fabbrica» (il nastro automatico)

Ciclo produttivo automatico che trasforma idee di trading in candidati verificati:
`candidato → spec → test → cancello → (promozione | archivio)`.
Un tick esegue **una** azione utile e aggiorna uno stato leggibile (`fabbrica/STATO.md`).
Non tocca i mercati, non inventa numeri: ciò che richiede giudizio viene marcato come AZIONE owner.

- Cadenza **3 s** (×100 dal 02/10; master su mc2 + worker sui nodi @5s); **139.588 tiri** al 06/10.
- **Job-store**: coda con lease/dedup/retry (WAL); **gate JEV** (TypeSafe, advisory, fail-open)
  e **lint spec** a 7 blocchi su ogni spec.
- **Watchdog anti-silenzio** → alert Telegram (`@DenaroAlertBot`, canale unico; max 1/ora + rientro).
- **Kill-switch**: file `fabbrica/STOP` — il nastro si ferma, la ricerca no.

## 9. Economia e costi (misurati, non stimati)

| Tariffa | maker | taker | round-trip misto | Provenienza |
| :--- | ---: | ---: | ---: | :--- |
| spot OKX EEA | 0,20% | 0,35% | **0,550%** | dall'account (`privateGetAccountTradeFee`) |
| con X-Perps | 0,08% | 0,10% | 0,180% | assunzione conservativa |
| swap/perps | 0,02% | 0,05% | **0,070%** | dall'account (con derivati attivi) |

Costi di progetto: ~**9 EUR/mese** VPS + ~**22 EUR/mese** servizi AI (`docs/22`).
Soglia economica del cancello: expectancy ≥ 3× pedaggio — sotto, il sistema non parte.

## 10. Squadra e metodo di lavoro

- **11 esecutori su 4 macchine + la regia** — famiglie: `A0` (Agent Zero), `DSH` (DeepSeek
  Harness), `opencode`, `agy`; nomenclatura ufficiale `<tool>-<macchina>` (es. `A0-win`,
  `DSH-omarchy`, `opencode-mc2`). Modelli **solo online** (no inference locale).
- **Consegne**: PROTCON — protocollo atomico con MANIFEST sha256 (provenienza byte-exact);
  ogni consegna passa la **review di Hermes** (i test si rieseguono nel repo) prima dell'integrazione.
- **Git**: un solo writer (mc2), commit piccoli e motivati, prefisso `[hermes]`; push via mc2.

## 11. Monitoraggio e affidabilità («zero silenzi»)

Zabbix 7.0 (gruppo «Money») · Grafana · dashboard/landing web · **alert Telegram** ·
watchdog fabbrica · post-reboot check · health per nodo. Lezione fondante: *un componente giù
senza alert è un incidente* — hardening nato da incidenti reali (mc2 offline, fossili health,
cron drift) oggi versionati in `deploy/`.

## 12. Qualità e riproducibilità

- **558 test offline** (nessuna chiave, nessuna rete) + `ruff` pulito — veloce su checkout fresco.
- Le misure si riproducono **cifra per cifra** su ambienti indipendenti (Windows 3.14 / mc2 3.12;
  `docs/04`). Limite dichiarato: è lo *stesso codice* altrove — non una seconda implementazione.
- La provenienza degli artefatti è verificata (P9, MANIFEST sha256).

## 13. Come si esegue (chi clona il repo)

```bash
git clone https://github.com/grivetto/money && cd money
python -m pytest tests -q        # 558 passed (offline)
python src/money/costi.py        # la matematica del pedaggio
MONEY_CACHE=/tmp/mc python scripts/misura_trend_lungo.py   # ri-misura su dati reali OKX (pubblici)
python demo_cancello.py          # il cancello che decide a due pedaggi diversi
```

## 14. Organizzazione del repository

```
src/money/     costi · dati · cancello · statistica · rischio · contabilità · economia · ricerca/
tests/         558 test offline          scripts/   runner di misura + cruscotto + canary
docs/          01–22: decisioni, protocolli, dossier, incidenti, costi
prove/         evidenze raw (verdetti, JSON, consegne con hash) — congelate
coda_catena/   spec pre-registrate       fabbrica/  il nastro (regole + STATO)
deploy/        systemd + cron versionati legacy/    le codebase precedenti (memoria)
```

## 15. Domande aperte — dove un aiuto esterno serve (per Manus)

1. **Metodo**: il cancello (8 criteri) + la pre-registrazione sono abbastanza forti?
   Vedete buchi metodologici o criteri mancanti?
2. **Ricerca**: con pedaggio spot ~0,55% round-trip (0,07% via perp), dati daily/4h, capitale
   ~1k EUR — quale **classe di edge** ha più probabilità di passare il cancello? Suggerimenti
   concreti e testabili (niente letteratura senza numeri).
3. **Infrastruttura**: orchestrazione a eventi vs polling a 3s; come accorgersi di *deviazioni
   silenziose* (tick fermi, code che non avanzano); segreti multi-nodo; formato dei brief per
   agenti autonomi senza contesto (oggi la «self-containedness» delle spec è bassa: 0,08–0,29).
4. **Codice**: review libera del repository — punti di forza, debolezze, priorità.

## 16. Invarianti (non negoziabili)

1. Nessuna esecuzione prima di un edge promosso.
2. Nessuna affermazione di performance senza riconciliazione con l'exchange.
3. Nessun capitale configurato che l'account non ha.
4. Nessun ordine senza chiave di idempotenza.
5. Nessuna telemetria che legge come un fossile.
6. Nessun LLM nel percorso caldo (in ombra sì, a decidere no).
7. Nessun path drift: systemd e cron versionati.
8. Nessuna soglia abbassata per far passare qualcosa.

Regole dure: mai aggirare risk manager/kill-switch/limiti; un bot per conto; segreti mai in
git/log/chat; fail-closed su test e integrazione, fail-open **solo** per il gate JEV (advisory).

---

*Fonti interne: `README.md` · `ARCHITETTURA_2026-10-01.md` · `docs/` (01–22) ·
`prove/REGISTRO_ESPERIMENTI.md` · `fabbrica/STATO.md` · `vault/` (Sala di Controllo) ·
`BRIEF_MANUS_*` (29–30/09, per la parte fabbrica).*
*Questo documento aggiorna il quadro d'insieme per l'analisi esterna del 06/10/2026.*
