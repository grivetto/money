# P27 — D3 step di scala: abilitazione coppie LTC/AVAX nel gate carry — SPEC DI IMPLEMENTAZIONE
STATO: PRESA_DA Merlino 2026-10-18 (implementazione) — pre-registrata 2026-10-18 (hermes/Artù). REQ-MERL-20261018-011.
Voce OPERATIVA (piano D3, ROADMAP §7: «carry a scala regolata, step +100 € con gate verdi»). Non è un esperimento; fuori dal conteggio tentativi.
Repo: `grivetto/money` · commit di registrazione: `70388b7a` (file di questa voce: `coda_catena/P27_d3_scala_carry.md`).

## Obiettivo (verificabile)
Il gate unico di apertura (`scripts/carry_apri.py`, che importa `COPPIE` da `scripts/carry_multi.py`) supporta anche **LTC** e **AVAX**: dict `COPPIE` esteso con i parametri verificati, dry-run `carry_apri.py --coppia LTC|AVAX` che supera il gate carry (funding atteso baseline 0,01%/8h → payback ~34 periodi ≤ 90) e stampa il piano. Nessuna logica nuova: solo configurazione + test di coerenza.

## Contesto (numeri del 18/10)
- Funding recente (fonte pubblica OKX + archivio): LTC e AVAX a **baseline 0,010%/8h** (≈10,95%/anno lordo, netto ≈7,8% con costi 0,26%×12) — verificato su fonte indipendente il 18/10.
- LINK è momentaneamente fuori gate (funding oscillante, ultimo 0,0006%/8h → payback 532 periodi): LTC/AVAX sono le coppie per lo step.
- Parametri (da ccxt `market.contractSize`, verificati 18/10): **LTC XPerp `LTC-USD_UM_XPERP-310404` ctVal 0,1** (15 ct ≈ 88,9 USD di nozionale); **AVAX XPerp `AVAX-USD_UM_XPERP-310530` ctVal 10** (1 ct ≈ 96,2 USD). Spot: `LTC/USDC`, `AVAX/USDC`. Payback misurati (docs/20): LTC 22g, AVAX 23g — da riportare nel campo `payback_giorni` (convenzione esistente: DOT 8, DOGE 15, LINK 15, ADA 16).
- Cap carry: nozionale totale ≤ 30% del capitale (≈329 €); dopo lo step atteso ≈270 € (DOT+ADA 179,8 + nuova coppia ≈83–90 €).

## Meccanica
- Estendere `COPPIE` in `scripts/carry_multi.py` con `LTC` e `AVAX` (stesso pattern delle esistenti: nome, inst_perp, sym_perp, sym_spot, ct_val, nozionale_eur=90.0, payback_giorni, ccy_spot="USDC").
- Nessun'altra modifica a `carry_apri.py`/`carry_multi.py` (il gate e il calcolo restano quelli esistenti).
- Aggiungere `tests/test_carry_config.py`: coerenza del dict (chiavi richieste presenti, ct_val > 0, nozionale > 0, quote "USDC", unicità inst_perp, calcolo `n_contratti`/`qty_spot` con prezzi sintetici noti — es. LTC px 59,3 → 15 ct; AVAX px 9,616 → 1 ct).

## Input / Output
- **Input:** `scripts/carry_multi.py` (dict COPPIE), niente rete nei test.
- **Output:** dict esteso + test; dry-run (di Artù) che mostra il gate superato per LTC e AVAX.

## Criteri di accettazione
1. `COPPIE` esteso + `tests/test_carry_config.py` con `assert` sui valori attesi (output `pytest -q` per esteso); la suite esistente resta verde.
2. `LEGGIMI.md` con i comandi dry-run per LTC/AVAX che rieseguirà Artù.
3. Handoff `merlino/handoff/P27/` con carry_multi.py (o patch), test, LEGGIMI.md, `MANIFEST.sha256`, `READY` (ultimo).
4. Zero ordini, zero chiavi, zero write su `~/money` (lavoro in `~/merlino-scratch/p27/`).

## Verifica (riproducibile)
Comando di verifica (test offline, rieseguiti da Artù nel venv canonico):
```bash
python -m pytest tests/test_carry_config.py -q
```
Dry-run gate (SOLO Artù, da MARCODG1): `carry_apri.py --coppia LTC` e `--coppia AVAX` → atteso: gate carry ok, piano stampato, nessun ordine.

## Fuori scope
- Modifiche al gate o al calcolo; l'esecuzione dell'apertura (di Artù, dopo il redeem e il dry-run); DOGE (escluso: canary C1 sullo stesso conto); XRP (funding attuale sotto gate).
