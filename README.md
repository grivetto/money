# money — il progetto, riscritto da zero

> **Perché questo repository esiste in questa forma.** Sotto il nome *denaro* si sono succeduti
> **quattro** codebase — `C:\dev\denaro` (binance, mobile), questo repo (grid bot, dca, scalper,
> hedge, futures, sentiment), `alpha-omega-trading` (49.162 righe, 17 bot, tre macchine) e
> `~/denaro2` sulle VPS — e **nessuno ha guadagnato un euro**. Non per difetti del codice: perché
> si è costruito *prima* il sistema e *poi* si è cercato qualcosa da catturare.
>
> Qui l'ordine è invertito. Il codice precedente è in `legacy/`, tracciato con la sua storia, come
> memoria di cosa è stato provato — non come base su cui costruire.

## La regola che tiene su tutto

> **Nessuna strategia entra in produzione senza aver superato il cancello**: expectancy netta
> positiva **fuori campione**, ai **costi reali** del conto su cui girerà.

Il cancello non è una linea guida: è codice, e il suo rifiuto è vincolante.

## Le tre macchine

Tre macchine, **una famiglia di strategie ciascuna**, un conto OKX dedicato ciascuna. Non è una
scelta estetica: è la correzione di difetti già osservati sul campo.

| nodo | famiglia | perché lei | cosa deve dimostrare |
| :--- | :--- | :--- | :--- |
| **A** | trend a orizzonte lungo | l'unica con edge **misurato** (t = +4,51 a costo zero su 2,4 anni) | che sopravvive al pedaggio reale |
| **B** | griglia adattiva | copre il regime laterale, dove il trend non fa nulla | che la spaziatura minima supera il pedaggio |
| **C** | momento intraday (4H) | ~8× le occasioni del giornaliero | che regge i costi, che è il suo unico ostacolo |

**Perché un conto per macchina.** Nel progetto precedente ogni bot dichiarava il capitale
dell'*intero* conto: con 7 bot il rischio aggregato era il **14% invece del 2%**, e lo stop di un
bot liquidava a mercato l'inventario di un altro. Misurato, non ipotizzato.

**Perché il rischio è di portafoglio e non di bot.** Il budget del 2% è del *capitale totale*: tre
nodi non possono rischiare tre volte il 2%.

## I moduli, in ordine di importanza

| modulo | cosa fa | stato |
| :--- | :--- | :--- |
| `src/money/costi.py` | la matematica del pedaggio: movimento minimo, frequenza sostenibile, fattibilità | ✅ **verificato** |
| `src/money/dati.py` | barre OHLCV reali, point-in-time, cache locale, nessun look-ahead | in corso |
| `src/money/cancello.py` | il verdetto promuovi / archivia / insufficiente, con prove numeriche | in corso |
| `ricerca/` | le ipotesi, una per file, misurate con lo stesso rig del live | dopo i due sopra |
| `esecuzione/` | ordini idempotenti, riconciliazione, stato esplicito | **dopo** il primo promosso |
| `rischio/` | budget di portafoglio, governatore dei tre nodi | dopo il primo promosso |

### Cosa dice il modulo dei costi (misurato, non stimato)

| | giro misto | giro taker | movimento di pareggio | operazioni sostenibili con edge 2% |
| :--- | :--- | :--- | :--- | :--- |
| OKX EEA **senza** derivati (oggi) | 0,550% | 0,700% | 0,550% | **3,6** |
| OKX EEA **con** X-Perps | 0,180% | 0,200% | 0,180% | **11,1** |

Il pedaggio si abbassa di **3,05 volte** senza aggiungere un euro di capitale: serve un
*appropriateness assessment*, non denaro. È la leva più grande che il progetto abbia mai avuto, e
non è codice.

E il numero che il progetto precedente non aveva mai calcolato: sotto **4 EUR** di capitale, con
minimo d'ordine 1 EUR e un quarto per posizione, **non esiste nessun ordine sensato**.

## Cosa è vietato qui (le lezioni pagate care)

1. **Vietato costruire esecuzione prima di un edge promosso.** Il progetto precedente aveva 17 bot
   e zero trade verificati.
2. **Vietato dichiarare performance senza riconciliarla** con saldi e ordini reali.
3. **Vietato un capitale configurato che il conto non ha.** Un nodo senza fondi deve dire
   `NON FINANZIATO`, non saltare i tick in silenzio (1.486 tick persi — 882 + 604 — senza un solo
   allarme).
4. **Vietato un ordine senza chiave di idempotenza.** Un crash fra invio e salvataggio lascia
   denaro impegnato che il bot non vede.
5. **Vietata la telemetria che legge come fossile.** Un file vecchio non è un bot che gira.
6. **Vietato un LLM nel percorso caldo.** Non riproducibile, e il costo per decisione è comparabile
   all'edge cercato. In shadow sì, a decidere no.
7. **Vietato il path drift**: systemd e cron versionati in `deploy/`, con `PROJECT_ROOT`
   parametrico. È stata la causa di 10 guasti su 12.

## Stato del capitale (verità, non aspirazione)

I conti OKX dietro le chiavi live contengono **~0,15 EUR di dust**. L'ordine di priorità è:
**cancello → primo edge promosso → capitale → frequenza**. Il capitale non crea edge: rende il
guadagno visibile.

## Avvio rapido

```bash
cd C:\dev\money
set PYTHONPATH=C:\dev\money\src
python src\money\costi.py        # la matematica del pedaggio
python -m pytest tests -q        # i test del rig e del cancello
```
