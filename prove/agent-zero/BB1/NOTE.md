# NOTE - Task BB1: Bootstrap a Blocchi Sensibilità

## Cosa è stato fatto

Creati tre file nella cartella di lavoro `/a0/usr/workdir`:

1. **bootstrap_blocchi.py** - Modulo Python autonomo (solo stdlib) per moving-block bootstrap della media
2. **test_bootstrap_blocchi.py** - Suite di test con 8 test (6 richiesti + 2 extra)
3. **NOTE.md** - Questo file

## Funzioni implementate

### `ic90_blocchi(serie, blocco, livello=0.90, n_ricampiona=2000, seme=12345)`
- Moving-block bootstrap della MEDIA
- Restituisce tupla (estremo_inferiore, estremo_superiore) per intervallo di confidenza
- Deterministico con seme fisso
- Gestisce:
  - Serie < 2 osservazioni → ValueError chiaro
  - Blocco < 1 → ValueError chiaro
  - Blocco >= lunghezza serie → clamp a n (lunghezza serie)
  - Serie costante → IC degenere [valore, valore] ampiezza 0

### `sensibilita(serie, blocchi=(5,10,20,40,80), **kw)`
- Calcola IC per ogni lunghezza blocco richiesta
- Restituisce lista dizionari [{blocco, ic_inf, ic_sup, ampiezza}] in ordine
- Passa **kw a ic90_blocchi

## Comandi eseguiti

```bash
cd /a0/usr/workdir
python test_bootstrap_blocchi.py
```

## Esito REALE

**8 test eseguiti, 8 PASS, 0 FAIL**

```
✓ test_determinismo: (3.5, 7.4) == (3.5, 7.4)
✓ test_serie_corta: ValueError corretto: Serie deve avere almeno 2 osservazioni
✓ test_serie_vuota: ValueError corretto: Serie deve avere almeno 2 osservazioni
✓ test_serie_costante: IC degenere [5.0, 5.0]
✓ test_blocco_ge_serie: clamp funziona, IC = (3.0, 3.0)
✓ test_iid_serie: IC=[-0.0781, 0.2774], ampiezza=0.3555
✓ test_sensibilita_ordine_lunghezze: 4 risultati in ordine corretto
✓ test_blocco_invalido: ValueError corretto: Blocco deve essere >= 1
✓ test_livello_personalizzato: IC90 ampiezza=3.6000, IC95 ampiezza=4.4000

==================================================
RISULTATO: 8 PASS, 0 FAIL su 8 test
==================================================
```

## Dettaglio test richiesti (a-f)

| Test | Descrizione | Esito |
|------|-------------|-------|
| (a) | Determinismo: stesso seme → stessi estremi | PASS |
| (b) | Serie corta (<2 obs) → ValueError chiaro | PASS |
| (c) | Serie costante → IC degenere gestito | PASS |
| (d) | Blocco >= lunghezza serie → clamp dichiarato | PASS |
| (e) | Serie i.i.d. simulata, blocco=1 → IC ragionevole | PASS |
| (f) | sensibilita() → tutte le lunghezze, in ordine | PASS |

## Copia-ponte

I tre file sono stati copiati anche in `/a0/usr/workdir/ponte-dsh/` (cartella contenente `a0-a-dsh.md`).

## Note tecniche

- Solo standard library Python (random, math, typing)
- Nessuna dipendenza esterna, nessuna rete
- Determinismo garantito da `random.seed(seme)` a ogni chiamata
- Metodo percentilico per IC bootstrap
- Clamp automatico del blocco alla lunghezza della serie (comportamento dichiarato)
- Indici percentili con floor/ceil per copertura corretta