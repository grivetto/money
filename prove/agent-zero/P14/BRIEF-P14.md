# BRIEF-P14 — Runner di misura «momentum cross-sectional su universo ampio»
Repo di destinazione: `grivetto/money` @ `ff3223f6`. Brief autosufficiente: i file di riferimento sono in `refs/` accanto a questo file.

## Obiettivo
Scrivere `misura_p14.py`: adattamento del runner P10 (`refs/misura_p10.py`) per l'esperimento P14
— momentum cross-sectional (long/flat top-k) su **UNIVERSO AMPIO** — più `test_misura_p14.py` con
test OFFLINE. La misura vera NON si esegue qui: la esegue Hermes sul repo canonico.

## Contesto (leggi questi riferimenti prima di scrivere)
- `refs/misura_p10.py` — il runner esistente: struttura, caricamento dati, griglia, selezione su
  addestramento, verifica OOS, cancello, artefatti. È il MODELLO da adattare.
- `refs/momentum_cross.py` — il motore `money.ricerca.momentum_cross` (config, backtest, griglia
  esistente). NON si modifica.
- `refs/misura_p5.py` + `refs/universo.py` — come si carica l'UNIVERSO AMPIO con il selettore
  `money.ricerca.universo` (copertura >=95% sulla finestra). Riprendi le stesse chiamate.
- Finestra dati identica a P10: 2020-10-01 -> 2026-09-25; confine addestramento 2024-06-01.

## Input / Output
- Input: barre dai dati di riferimento (nel runner: come in `refs/misura_p10.py`, dai moduli
  `money.dati` / cache); NIENTE rete nei test.
- Output richiesto:
  1. `misura_p14.py` che: (a) carica l'universo ampio via selettore; (b) griglia dichiarata
     **{k: 3,5} x {L: 60,120} x {R: 7,14}** (8 varianti) provate SOLO su addestramento;
     (c) selezione max `expectancy_netta/dd_portafoglio` (n>=30 operazioni di training);
     (d) **riga di riferimento NON selezionabile**: config P10 (k=2, L=120, R=14) valutata sullo
     stesso universo, esclusa dalla selezione; (e) verifica OOS UNICA; (f) scenari costi:
     primario `okx_eea_spot` + slippage 4bp/lato, secondario `okx_eea_con_perp`, **stress slippage
     x2**; (g) artefatti `prove/P14_momentum_universo.txt` e `.json` (stesso stile di P10).
  2. `test_misura_p14.py`: test offline su dati sintetici delle FUNZIONI PURE del runner
     (dichiarazione griglia, selezione, costruzione righe artefatto). Niente rete, niente chiavi.
  3. `NOTE.md`: elenco file, comando di verifica ed esito REALE (output incollato).

## Test (devono fallire senza l'implementazione)
- le 8 varianti della griglia sono esattamente {3,5}x{60,120}x{7,14} (assert);
- la selezione sceglie per max exp/dd su righe sintetiche (atteso calcolabile a mano);
- la riga di riferimento NON è eleggibile alla selezione;
- la costruzione dell'artefatto produce le chiavi attese (assert su dict/JSON).

## Criteri di accettazione (checklist)
- [ ] `misura_p14.py` e `test_misura_p14.py` presenti nella cartella di consegna;
- [ ] test eseguiti con esito REALE incollato in NOTE.md (n/N passed);
- [ ] nessuna modifica ai file in `refs/` (sola lettura);
- [ ] solo stdlib + import dal repo come indicato; nessuna chiave, nessuna rete nei test.

## Fuori scope (non toccare)
- NON eseguire la misura completa (niente download dati massivi, niente run lunghi);
- NON modificare il motore `momentum_cross.py` né il runner P10;
- NON toccare exchange, servizi, systemd, cartelle fuori da questa workdir.

## Comando di verifica
```bash
cd /a0/usr/workdir/p14 && python -B test_misura_p14.py
```
Atteso: N passed, 0 failed (incollare l'output in NOTE.md). Hermes rifà poi la verifica nel repo.

## Consegna
Cartella: `/a0/usr/workdir/p14/` — file: `misura_p14.py`, `test_misura_p14.py`, `NOTE.md`.
Firma con l'elenco file e l'esito reale. NO segreti, NO stampe di chiavi.
