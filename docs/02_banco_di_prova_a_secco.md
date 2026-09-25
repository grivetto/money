# 02 — Specifica del banco di prova a secco (pre-produzione)

> **Data:** 2026-09-25 · **Autore:** [dsh] · **Destinatario dell'implementazione:** Hermes, in `deploy/`
>
> Questo documento è una **specifica**, non un modulo: `deploy/` è di Hermes (divisione
> confermata il 2026-09-25) e chi muove i soldi ha un proprietario solo. Qui c'è *cosa* deve
> fare il banco e *cosa gli è vietato*, in modo che l'implementazione non debba indovinare.

---

## 1. A cosa serve, in una riga

> Provare **tutta la catena** — chiave → saldo reale → capitale dichiarato → guardia →
> calcolo dell'ordine → riconciliazione — **senza inviare nessun ordine** e senza mentire sul
> capitale configurato.

Serve adesso perché è la catena che dovrà funzionare il giorno dei 1000 EUR. E serve perché il
difetto che ha ucciso il progetto precedente è nato esattamente qui: **1.486 tick saltati in
silenzio** su un conto da 0,15 EUR, con la configurazione che dichiarava 24,83–42,12 EUR per bot.

## 2. Dove gira

Il banco legge il conto **main** di OKX, la cui chiave è **IP-whitelisted**
(`87.106.222.123`, `87.106.3.15` = MARCODG1 e nuvola). Quindi gira su **MARCODG1** o **nuvola**,
non su mc2 (che viene rifiutata). Se in futuro il banco deve leggere un **subaccount**, gira sul
nodo che possiede quel subaccount — un nodo, un conto, una famiglia.

## 3. Ingressi

| ingresso | da dove | regola |
| :--- | :--- | :--- |
| `OKX_API_KEY` / `OKX_API_SECRET` / `OKX_PASSPHRASE` | variabili d'ambiente | **mai** nel codice, mai in git, mai nel log |
| hostname | costante `eea.okx.com` | le chiavi EU falliscono altrove con `50119`, che **sembra** una chiave morta |
| capitale dichiarato | configurazione versionata | deve essere **il capitale reale**, non quello aspirsto (oggi 26 EUR; 1000 EUR dopo il deposito) |
| frazione per posizione | configurazione | usata per il calcolo, non per decidere se operare |

## 4. Passi, in ordine, con l'uscita attesa

1. **Leggi il saldo reale**: `fetch_balance` sul trading **e** sul funding (`{'type': 'funding'}`).
   Il bonifico atterra sul funding: un banco che legge solo il trading dichiara `NON FINANZIATO`
   su un conto che i soldi li ha. Il primo dei due che contiene capitale va riportato **entrambi**.
2. **Calcola l'equity in EUR**, non il solo saldo EUR: saldo EUR + valore di mercato degli asset
   detenuti. Un conto con 20 EUR di SOL e 6 EUR di EUR ha 26 EUR di equity, non 6. (E' il bug
   storico del criterio di drawdown: l'equity che ignora gli ordini aperti produce falsi positivi.)
3. **Applica la guardia di capitale**:
   - `equity >= capitale_dichiarato` → si prosegue;
   - `equity < capitale_dichiarato` → stampa **`NON FINANZIATO`** con i tre numeri (equity reale,
     capitale dichiarato, differenza) ed **esci con codice diverso da zero**.
   - Mai un tick saltato in silenzio: un salto silenzioso è il guasto che questo banco esiste
     per rendere impossibile. Se salta, **lo dice e si conta**.
4. **Calcola l'ordine che verrebbe inviato**: nozionale = `capitale * frazione_per_posizione`,
   arrotondato allo `step_size` dello strumento con `math.floor(nozionale / step) * step`
   (**non** `int(step)`, che con `step_size = 0.001` restituisce 0 — il bug ccxt 4.x del
   progetto precedente), e verifica `nozionale >= min_notional` con `money.costi.verifica_fattibilita`.
5. **Stampa l'ordine** — simbolo, lato, tipo, quantità, prezzo di riferimento, pedaggio atteso per
   giro, tariffa **assunta** (`okx_eea_spot` oggi) — con l'etichetta `DRY-RUN, NON INVIATO`.
6. **Riconcilia**: ordini aperti, posizioni, P&L. Un ordine a mercato senza chiave di
   idempotenza che sopravvive a un crash è denaro impegnato che il bot non vede: se il banco un
   giorno invierà davvero, dovrà farlo con `clOrdId`, mai senza.
7. **Log e metrica**: una riga per esecuzione (timestamp, equity, esito della guardia, ordine
   calcolato) e un item Zabbix per nodo. La telemetria che legge come fossile è vietata: un file
   vecchio non è un bot che gira.

## 5. Divieti (vincolanti)

1. **Nessun percorso di codice che chiami `create_order`.** Non "disattivato da un flag": assente.
   Con un test che lo verifica staticamente, così non può rientrare da una modifica distratta.
2. **Nessun LLM nel percorso caldo**, nemmeno in shadow dentro il banco: costa più dell'edge
   cercato e non è riproducibile.
3. **Nessun capitale dichiarato che il conto non ha.** Se i 26 EUR non bastano per il nozionale
   minimo di una strategia, il banco lo dice invece di arrotondare.
4. **Nessun prelievo, mai.** La chiave ha `withdraw` fra i permessi: il banco non deve poterlo
   usare nemmeno per errore.
5. **Nessun ordine reale finché il cancello non promuove una strategia** e il proprietario non
   finanzia. Il banco nasce a secco e resta a secco finché quelle due condizioni non sono vere.

## 6. Criterio di accettazione

Dal **solo log** del banco deve essere possibile rispondere a queste domande senza aprire una
shell sul nodo:

- il banco è girato? quando, e quante volte?
- quanto valeva il conto in quel momento, trading e funding separati?
- la guardia è passata o ha detto `NON FINANZIATO`, e con quali tre numeri?
- quale ordine avrebbe inviato, con quale pedaggio assunto?
- la riconciliazione quadra (ordini aperti, posizioni)?

Se una di queste richiede di fidarsi della memoria di chi l'ha scritto, il banco non è finito.

## 7. Cosa questo banco non è

Non è una strategia e non produce edge: legge, calcola, dichiara. **Non decide** se una strategia
è buona — quello è `money/cancello.py`, e il suo rifiuto è vincolante anche quando il banco
funziona perfettamente. Un banco di prova che gira bene su una strategia archiviata è un banco di
prova che gira bene e basta.
