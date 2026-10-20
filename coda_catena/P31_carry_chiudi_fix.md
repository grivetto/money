# P31 — `carry_chiudi.py`: la chiusura del carry deve poter chiudere (fix ALTA audit 20/10)

Data: 2026-10-20 · Base: `ab5ac459` (o HEAD con P30 se già integrata) · Autore spec: Artù
Origine: `prove/audit_chiudi_20261020/AUDIT.md` (audit avversariale indipendente, 21 difetti).
Qui si chiudono **solo** i 3 ALTA + i 3 MEDIA che stanno sullo stesso percorso di denaro.
Tutto il resto (M3, M4, M6, M9, M10, B1-B8) va in P32: **non allargare il perimetro**.

## Perché è urgente (misurato, non ipotizzato)

Lettura read-only dell'account OKX main dal nodo nuvola (20/10 23:01 CEST, zero ordini):

```
POSIZIONI SWAP APERTE: 3
  ADA/USD:USD-310404     contracts=39.0  side=short  pos=-39  mgn=isolated lev=1.0
  DOT/USD:USD-310808     contracts=78.0  side=short  pos=-78  mgn=isolated lev=1.0
  DOGE/USD:USD-310404    contracts=11.0  side=short  pos=-11  mgn=isolated lev=1.0
ORDINI APERTI: 0
```

`ccxt` restituisce `contracts` **positivo** e la direzione in `side` (`info.pos` è il
valore con segno). Il codice attuale legge `contracts` e ne deduce il lato: per le due
coppie carry reali (DOT e ADA, entrambe **short**) il piano e l'ordine escono **sell
reduceOnly su una posizione short** → OKX non riduce nulla. Tradotto: **oggi
`carry_chiudi.py` non è in grado di chiudere le coppie carry in produzione.**

## Vincoli (identici a P29/P30)

- Zero write su `~/money` dal tuo scratch: consegni un handoff con `MANIFEST.sha256` + `READY`.
- **Un fix = un test che PRIMA fallisce** e poi passa. Il rosso va nel `LEGGIMI.md` con l'output vero.
- Niente refactoring oltre il fix puntuale. Suite esistente verde. Ruff pulito.
- Compatibilità: il file di stato `data/carry_multi/stato.json` deve restare leggibile da
  `carry_multi.py status` e da `carry_apri.py` (campi nuovi **solo in aggiunta**).
- La chiusura **non** passa dai gate di apertura (è riduzione di rischio): non cambiarlo.

## Fix richiesti

### F1 (ALTA) — lato e taglia della gamba perp dalla forma reale di ccxt

`scripts/carry_chiudi.py:170-175` (`qty_perp`), `:259` (`chiudi_perp`), `:380` (`stampa_piano`).

Oggi `qty_perp` fa `return float(p["contracts"])`, che è **sempre >= 0**; `:259` e `:380`
scelgono `side = "sell" if ct > 0 else "buy"`. Per uno short `ct=+78` → `sell` (sbagliato).

Fix:
- la direzione viene da `p["side"]` (`short` → chiusura `buy`, `long` → `sell`); la taglia da `abs(contracts)`.
- `qty_perp` deve restituire un valore **con segno** solo se lo ricava da una fonte affidabile
  (`side` + `abs(contracts)`), altrimenti restituire la taglia e la direzione separatamente.
  Scelta libera, purché **un solo** punto decida lato e taglia, usato sia dal piano sia dall'invio.
- niente `info["pos"]` come fonte primaria: usarlo solo come controllo di coerenza
  (se `info.pos` e `side` si contraddicono → exit 1, nessun ordine).

Test che deve fallire prima:
1. posizione short nella forma reale (`contracts=78.0`, `side="short"`) → il piano stampa
   `buy 78 ct reduceOnly` e l'ordine inviato ha `side="buy"`.
2. posizione long (`contracts=5.0`, `side="long"`) → `sell 5 ct`.
3. coerenza: `contracts=78.0`, `side="short"`, `info.pos="+78"` (contraddittori) → exit 1, zero ordini.

### F2 (ALTA) — eccezione su `create_order` ≠ "ordine non inviato"

`scripts/carry_chiudi.py:270-273` (perp) e `:324-327` (spot): qualunque eccezione diventa
`esito="invio_fallito"` e il codice prosegue come se nulla fosse stato inviato.

Scenario reale: `RequestTimeout` dopo che OKX ha accettato → l'ordine vive, il codice dice
"fallito", lo spot non viene toccato e può restare nudo.

Fix: nel `except` di `invia_gamba`:
- cercare l'ordine per `clOrdId` (`fetch_order(cid)` / `fetch_open_orders` filtrato) e, se
  esiste, annullarlo e **rileggere** posizione/saldo;
- registrare `esito="incerto"` con `ordine` e `clOrdId` nell'evento, e **non** proseguire
  alla gamba successiva: exit 1 con messaggio "verifica manuale";
- solo se la ricerca prova che l'ordine non esiste → `invio_fallito` come oggi.

Test che deve fallire prima: mock che solleva su `create_order` ma registra l'ordine come
presente in `fetch_open_orders` → il codice deve annullarlo, scrivere `esito="incerto"` e
uscire 1 senza inviare la gamba spot.

### F3 (ALTA) — la gamba spot "assente" non si decide col solo saldo trading

`scripts/carry_chiudi.py:309-350` (`chiudi_spot`), `:503-511`, `:520-521`, `:535-539`.

Oggi: se il saldo trading della moneta è 0, lo spot è "assente" e si prosegue; la
riconciliazione attende 0 e dichiara `closed` anche se la qty è finita in funding/earn
(spot nudo non segnalato). Inoltre `voce["qty_spot"]` dello stato (scritto da
`carry_apri.py:326-329`) è disponibile e viene ignorato.

Fix:
- leggere anche funding/earn (`fetch_balance({"type": "funding"})`, e se il conto lo espone
  il saldo Simple Earn) e sommare;
- confrontare il totale con `voce["qty_spot"]`: se lo stato dice `> 0` e il totale reale è 0
  → **exit 2**, nessun ordine, messaggio con la qty attesa;
- se `assente` ma `qty_spot` di stato > tolleranza → non scrivere `closed`: scrivere
  `chiusura_fallita` con `nota_chiudi` che dice dove può essere la gamba (funding/earn).

Test che deve fallire prima: stato con `qty_spot=90`, saldo trading 0, funding 90 → exit 2
(zero ordini). Secondo test: stato `qty_spot=0`, tutto 0 → `closed` con `nota_chiudi`
"gamba spot assente (qty attesa 0)".

### F4 (MEDIA, stesso percorso) — "perp assente" con una sola lettura

`scripts/carry_chiudi.py:251-257`, `:501-502`. Una `fetch_positions` vuota/stale fa vendere
lo spot e lascia lo short nudo. Fix: due letture concordanti a ~1s, oppure poll breve; se lo
stato dice `ct_perp != 0` e la lettura dice 0 → exit 1, nessun ordine.

Test: prima lettura vuota, seconda con `-78` → nessun ordine spot, exit 1.

### F5 (MEDIA, stesso percorso) — qty spot: usare la qty della coppia, non l'intero saldo

`scripts/carry_chiudi.py:313`, `:323`. Oggi vende tutto il saldo della moneta: 90 DOT del
carry + 100 DOT manuali → vende 190. Fix: `q = min(q_reale, voce["qty_spot"] + toll)`;
se `q_reale - qty_spot > toll` → exit 2 con la differenza (serve un `--qty` esplicito).

Test: saldo 190, stato 90 → nessun ordine, exit 2; saldo 90.05, stato 90 → vende 90.05.

### F6 (MEDIA, stesso percorso) — fill cumulato dopo reprice

`scripts/carry_chiudi.py:301-304`, `:351-354`, `:521`, `:531`: `filled` è solo l'ultimo
ordine; dopo un reprice il residuo/attesa sono sbagliati. Fix: sommare i fill di primo e
secondo ordine (o leggere il saldo finale) e usare quel totale per residuo, attesa e fee.

Test: primo ordine fill 3 su 8, cancel, reprice fill 5 → `filled=8`, attesa 0, fee sommate.

## Consegna

- `handoff/P31/` con: `diff_p31.diff`, `carry_chiudi.py`, `test_carry_chiudi_p31.py`,
  `rosso_pre_fix.txt`, `LEGGIMI.md` (mappa fix→test, comandi esatti, output rosso/verde), `MANIFEST.sha256`, `READY`.
- Nel `LEGGIMI.md` dichiara esplicitamente: quali test coprono la forma reale di ccxt
  (`contracts` positivo + `side`), e che `stampa_piano` e `chiudi_perp` usano lo stesso punto.
- Se un fix richiede una scelta di design non coperta qui, **fermati e scrivila in
  `results.md`**: non inventare.
