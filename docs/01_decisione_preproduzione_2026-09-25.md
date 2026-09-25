# 01 — Decisione: pre-produzione a secco con 26 EUR

> **Data:** 2026-09-25 · **Autore:** [dsh] (sessione Windows) · **Stato:** decisione del proprietario, attuazione in corso
>
> Questo documento registra una decisione e i fatti che l'hanno motivata. Non promuove
> nessuna strategia: a promuovere è `money/cancello.py`, e finora nessuna l'ha superato.

---

## 1. La decisione

Il proprietario ha bonificato **26 EUR** sul conto OKX **main** e ha chiesto di metterli in
**pre-produzione** in attesa di versare **1000 EUR**.

Pre-produzione, qui, ha un significato preciso e ristretto:

> **banco di prova a secco** — legge il saldo reale, applica la guardia di capitale, calcola
> l'ordine che *verrebbe* inviato e **non invia niente**.

Il progetto non sa fare altro, oggi: `esecuzione/` e `rischio/` non esistono, per scelta
esplicita ("dopo il primo promosso"), e `ricerca/` non conteneva nessuna ipotesi misurata.

## 2. Fatti verificati in sola lettura (2026-09-25)

Letti da **MARCODG1** con la chiave main e `hostname=eea.okx.com`. Nessun ordine inviato,
nessun fondo mosso.

| Voce | Valore |
| :--- | :--- |
| main **trading** | **EUR 26,00304973107057** |
| main **funding** | vuoto |
| ordini aperti | **0** |
| dust residuo | ETH 6,5e-07 · SOL 8,4e-07 · ADA 8,3e-05 · DOGE 8,4e-07 |

Il bonifico è arrivato **ed è già sul conto trading**: non serve il passaggio funding → trading.

### Inventario delle chiavi (solo esito, nessun valore)

| chiave | posizione | esito |
| :--- | :--- | :--- |
| main | `~/denaro_legacy/secrets/main_okx.env` | **viva ma IP-whitelisted**: funziona da MARCODG1 e nuvola, **rifiutata da mc2** |
| vault (7 chiavi) | `~/.denaro_vault/keys_master.env` | tutte **morte** (`50119`) |
| mc2sub1 / nuvolasub1 / marcosub1 | `~/denaro_legacy/secrets/*_okx.env` | vive, funding vuoto |

**Conseguenza operativa:** il banco di prova che legge il conto main gira su **MARCODG1** o
**nuvola** (la whitelist dell'account è `87.106.222.123,87.106.3.15`), oppure serve una chiave
con l'IP di mc2 in whitelist.

### La tariffa non è un'assunzione: è stata letta dall'account

`privateGetAccountTradeFee` / `privateGetAccountConfig` sul conto main, 2026-09-25:

| | maker | taker | giro misto |
| :--- | ---: | ---: | ---: |
| SPOT (Lv1, reale) | 0,20% | 0,35% | **0,550%** |
| SWAP (Lv1, se i derivati fossero attivi) | 0,02% | 0,05% | **0,070%** |

Due conseguenze:

1. L'assunzione `okx_eea_spot` di `costi.py` (giro misto 0,550%) è **confermata dall'account**.
2. `costi.py` assume per i derivati `okx_eea_con_perp` = giro misto **0,180%**, mentre il conto
   espone **0,070%**: l'assunzione è **2,6 volte più pessimistica del reale**. È un errore nella
   direzione sicura (non gonfia l'edge), ma è un numero da allineare — e va riverificato quando
   `acctLv` passa a 2, perché oggi l'account è in **`acctLv: "1"`** e i derivati non sono
   operabili: la tabella SWAP è quella che si applicherebbe, non una tariffa già pagata.

Stato dell'account: `acctLv "1"` · `kycLv "2"` · `perm read_only,withdraw,trade` · `level Lv1` ·
`settleCcy USD` (gli swap sono regolati in stablecoin, non in EUR: cambia la valuta di
regolamento e introduce esposizione stablecoin).

**Trappola documentata, per non ripeterla:** con `hostname=okx.com` (globale) tutte le chiavi
EEA rispondono `50119 "API key doesn't exist"` e sembrano morte. Le chiavi EU funzionano
**solo** su `eea.okx.com`. Una lettura sbagliata dell'hostname produce un falso allarme
identico a un guasto vero.

## 3. Perché 26 EUR non possono essere "in produzione"

La soglia di rilevanza economica del cancello è **10 EUR/anno**, calibrata su
`CAPITALE_RIFERIMENTO_DEFAULT = 1000`. Le conseguenze cambiano con il capitale:

| | 26 EUR | 1000 EUR |
| :--- | ---: | ---: |
| per posizione (25% del capitale) | 6,50 EUR | 250,00 EUR |
| pedaggio spot per giro (0,550% misto) | 0,036 EUR | 1,375 EUR |
| con X-Perps (0,180%) | 0,012 EUR | 0,450 EUR |
| rendimento netto annuo per superare i 10 EUR/anno | **38,5%** | **1,0%** |
| operazioni/anno necessarie con edge netto 1%/op | 154 | 4 |

**A 26 EUR il vincolo è il capitale, non la strategia.** Il cancello, a quella scala, o dice
`insufficiente` o promuove solo attraverso un'estrapolazione che dichiara esso stesso essere
un limite superiore. La soglia **non si abbassa** per far passare qualcosa: si dichiara.

Corollario: **non** accendere la flotta precedente con 26 EUR. I bot live dichiarano 24,83–42,12
EUR di capitale ciascuno; con 26 EUR sul conto la guardia "equity inattendibile" salterebbe i
tick su tutti — cioè riprodurrebbe i 1.486 tick persi in silenzio che il progetto vieta.

## 4. Le tre macchine e il nodo giusto per 26 EUR

Architettura confermata: **un nodo = una famiglia di strategie = un subaccount OKX dedicato**.
I 26 EUR sono sul **main**, che non è un nodo: la destinazione (quale subaccount) resta una
decisione aperta del proprietario, e va presa prima dei 1000 EUR, non dopo.

| nodo | famiglia | cosa deve dimostrare prima di operare |
| :--- | :--- | :--- |
| A | trend a orizzonte lungo | che sopravvive al pedaggio reale |
| B | griglia adattiva | che la spaziatura minima supera il pedaggio |
| C | momento a 4 ore | che regge i costi (il suo unico ostacolo) |

## 5. Divisione dei percorsi (confermata con Hermes, 2026-09-25 01:24 UTC)

| chi | cosa |
| :--- | :--- |
| **[dsh]** | `src/money/ricerca/`, `dati`/`cancello`/`costi`, test, `docs/` |
| **Hermes** | `deploy/` (systemd + cron versionati, `PROJECT_ROOT` parametrico), esecuzione reale, governatore dei tre nodi, telemetria |

Canale unico: `~/hermes_bridge/dsh/requests.md` ↔ `results.md`. `_hermes_msg.md` resta archivio.

## 6. La leva che non è codice

L'*appropriateness assessment* per aprire gli **X-Perps** porta il pedaggio da 0,550% a 0,180%
per giro — **3,05×** — senza aggiungere un euro di capitale. È la leva più grande che il
progetto abbia, e non si compra con il codice: si fa sul conto. Con 26 EUR conta più di
qualunque strategia.

## 7. Aperti (non chiusi da questo documento)

- [ ] **X-Perps**: assessment da fare sul conto (proprietario). Senza, si opera a 0,550%/giro.
- [ ] **Destinazione dei 26 EUR**: main o subaccount del nodo A/B/C (proprietario).
- [ ] **`.env_mc2` mancante su mc2** → `denaro-node-mc2.service` in restart loop (`NRestarts=1362`),
      `Failed to load environment files`. Unit **enabled**, guasto silenzioso. Dominio Hermes,
      segnalato e non toccato.
- [ ] **PAT GitHub in chiaro** in `~/.bash_history` di marco: da revocare (Hermes ha escalato).
- [ ] **Banco di prova a secco**: da scrivere in `deploy/` (Hermes) con la guardia
      `NON FINANZIATO` e la lettura del saldo.
- [x] **Push di `money`**: fatto il 2026-09-25 (`c82366e0..8f5624c1` → `origin/main`).

## 8. Cosa questo documento non dice

Non dice che una strategia funziona: nessuna è passata dal cancello. Non dice che 26 EUR
renderanno: dice che sono il banco di prova della catena. La sequenza resta
**cancello → primo edge promosso → capitale → frequenza**, e il capitale non crea edge:
rende il guadagno visibile.
