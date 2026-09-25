# 05 — I derivati sono sbloccati: cosa cambia, misurato

> **Data:** 2026-09-25 · **Verificato in sola lettura** da MARCODG1 con la chiave main,
> `hostname=eea.okx.com`. Nessun ordine inviato, nessun fondo mosso.
>
> L'account è passato a `acctLv 2`: i derivati sono operabili. Questa è **la leva più grande che il
> progetto abbia**, e questo documento dice esattamente quanto vale e cosa **non** cambia.

---

## 1. Cosa è cambiato sul conto

| | prima (25/09, mattina) | ora |
| :--- | :--- | :--- |
| `acctLv` | `"1"` (solo spot) | **`"2"`** |
| `settleCcy` | `USD` | **`USDC`** |
| tariffa SPOT | maker 0,20% · taker 0,35% | invariata |
| tariffa SWAP | non applicabile | **maker 0,02% · taker 0,05%** |
| **giro misto swap** | — | **0,070%** |
| saldo **trading** | EUR 26,0030 | **vuoto** (`totalEq: 0`) |
| saldo **funding** | vuoto | **EUR 26,0030** |
| ordini aperti | 0 | **0** |

Il pedaggio per giro scende da **0,550%** a **0,070%**: **7,86×**. È esattamente il valore che
`costi.py` porta come `okx_eea_swap_lv1`, misurato dall'account **prima** che i derivati fossero
attivi. Da oggi non è più uno scenario: è la tariffa applicabile.

## 2. Il denaro è nel funding, e il trading è vuoto

I 26,0030 EUR non sono spariti: sono nel **funding account**, mentre il conto trading ha
`totalEq: 0`. Nessun bot può piazzare un ordine su un saldo che sta lì, e nessuna lettura del solo
trading account lo vede.

È precisamente il caso per cui `docs/02` (banco a secco) prescrive di leggere **entrambi** i
comparti: un banco che guarda solo il trading dichiarerebbe `NON FINANZIATO` su un conto che i soldi
li ha — e sarebbe un falso allarme indistinguibile da un conto vuoto.

**Il passaggio funding → trading è un movimento di denaro**: non l'ho fatto e non lo faccio senza
un'istruzione esplicita.

## 3. Nessuno swap è regolato in EUR

Dei **492** swap disponibili su OKX EEA: **477 regolati in USDT**, 15 in cripto (BTC, ETH, SOL,
DOGE, XRP, BCH, LTC, ADA, DOT, ETC, FIL, HYPE, LINK, SUI, UNI), **zero in EUR**.

L'EUR quindi non è la valuta di regolamento dei derivati. Servono una conversione EUR → USDT (che
paga lo spread e la fee spot) oppure l'accettazione dell'EUR come collaterale nel conto unificato —
quest'ultima **non l'ho verificata**, va chiesta a OKX.

## 4. I tagli minimi: cosa è raggiungibile con 26 EUR

Nozionale minimo = `contractSize × prezzo` (misurato il 2026-09-25):

| strumento | taglio | prezzo | nozionale minimo |
| :--- | ---: | ---: | ---: |
| BTC/USDT:USDT | 0,01 | 83.784,20 | **837,84 USDT** |
| ETH/USDT:USDT | 0,1 | 2.681,58 | 268,16 USDT |
| XRP/USDT:USDT | 100 | 1,5533 | 155,33 USDT |
| SOL/USDT:USDT | 1,0 | 121,03 | 121,03 USDT |
| DOGE/USDT:USDT | 1.000 | 0,09798 | 97,98 USDT |
| ADA/USDT:USDT | 100 | 0,2534 | 25,34 USDT |
| LINK/USDT:USDT | 1,0 | 13,747 | 13,75 USDT |
| AVAX/USDT:USDT | 1,0 | 10,485 | 10,48 USDT |
| UNI/USDT:USDT | 1,0 | 9,438 | 9,44 USDT |
| DOT/USDT:USDT | 1,0 | 1,1908 | **1,19 USDT** |

Con ~28 USDT e **leva 1×**, sono raggiungibili DOT, UNI, AVAX, LINK e ADA; **non** lo sono BTC,
DOGE, SOL, ETH, XRP. Cioè: il costo per operare è sceso di 7,86×, ma **gli strumenti su cui il
progetto ha misurato l'edge** (BTC/ETH/SOL) restano fuori portata con questo capitale a 1×.

## 5. La regola che i derivati rendono urgente: leva 1×

OKX offre **fino a 10×**. La ricerca del progetto precedente (`docs/20` §20.5) prescrive, come
requisito e non come consiglio:

> *Cap di leva esplicito. I derivati permettono leva 100x; il sizing attuale impegna ~17% di
> nozionale con rischio 2%. Va reso **impossibile** superare 1x, indipendentemente dai parametri.*

Con 26 EUR di margine e 10×, un movimento avverso del 10% liquida la posizione. In `money` **non
esiste nessun modulo di esecuzione**, quindi oggi nessuno può inviare ordini — ma questo significa
anche che **il cap a 1× non è implementato da nessuna parte**: è una condizione da soddisfare
*prima* del primo ordine, non dopo.

## 6. Cosa NON cambia

**Il cancello ha archiviato tutte e tre le famiglie, e la tariffa più bassa non le promuove.**

| nodo | a 0,550% (spot) | a 0,070% (swap, ora applicabile) |
| :--- | :--- | :--- |
| A — trend lungo | archiviato | **archiviato** — gli X-Perps valgono 0,94 EUR/anno su quell'edge (4,97 → 5,91) |
| B — griglia adattiva | archiviato (t −8,54) | **archiviato** — nemmeno 3× meno pedaggio la salva |
| C — momento 4h | archiviato (copertura −0,654) | **archiviato** — copertura 1,716 e EUR/anno da −208,51 a **+69,61**, **1 criterio su 8 cambia**, il verdetto no |

Il pedaggio era una **condizione necessaria**, non sufficiente. L'ha detto il cancello prima che il
conto lo rendesse vero, che è esattamente il motivo per cui esiste.

## 7. Prossimi passi, in ordine

1. **Trasferimento funding → trading** dei 26 EUR (movimento di denaro: decisione del proprietario).
2. **Conversione EUR → USDT** per avere margine nella valuta di regolamento — oppure verifica
   dell'EUR come collaterale con OKX.
3. **Cap di leva a 1× implementato** prima di qualunque ordine, ovunque l'esecuzione venga scritta.
4. **Banco di prova a secco** (`docs/02`, implementazione in `deploy/`): resta il passo che precede
   il primo ordine.
5. **La prossima ipotesi** va scelta sapendo che il pedaggio ora è 0,070% — non perché il pedaggio
   sia sceso, ma perché ora è **misurato sul conto** e non stimato.
