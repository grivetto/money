# E1 — Economia unitaria: scheda costi + cost-to-edge + benchmark (INFRASTRUTTURA di misura)

STATO: CONSEGNATA e INTEGRATA (30/09/2026 — v. "Esito" in fondo; NON consuma gradi di
libertà di ricerca: non è una famiglia di strategia)

## 1. Obiettivo verificabile
Costruire il modulo `src/money/economia.py` che, dai ritorni di una misura, produce la
SCHEDA ECONOMICA (decomposizione lordo→netto per operazione, cost-to-edge, scenario
stressato) e i BENCHMARK di confronto (buy&hold, equal-weight, cash) col relativo test di
incrementalità. Riferimento: revisione Manus 30/09 (`docs/14_redditivita_manus_2026-09-30.md`).

## 2. Contesto
- repository: money @ commit `77d7f7af` (percorso di lavoro: /home/sergio/money su mc2)
- linguaggio: Python 3.11+, SOLO stdlib; nessuna rete; nessun I/O fuori dai tmp dei test
- convenzioni di costo: quelle di `money.ricerca.donchian_breakout` (pedaggio + slippage per
  lato); `ritorno_netto(lordo) = (1-s)(1+lordo)(1-s) - 1 - pedaggio`, con s = slippage per lato
- termini operativi: "lordo" = ritorno per operazione prima dei costi; "netto" = dopo
  fee+spread+slippage; "pedaggio" = movimento minimo di pareggio (`money.costi.movimento_minimo`);
  "cost-to-edge" = costo totale medio / edge lordo medio.

## 3. Fuori scope
- NON modificare moduli esistenti: `src/money/` resta invariato (solo file NUOVI);
- niente integrazione nei script di misura (la fa il revisore, non l'esecutore);
- niente CLI, niente rete, niente database, niente dati reali (solo input sintetici nei test);
- niente nuovi modelli di costo: pedaggio e slippage sono parametri PASSATI dal chiamante.

## 4. Specifica input/output

`src/money/economia.py` espone (firme esatte):

```python
def percentili(valori: list[float], q: float) -> float
# percentile con interpolazione lineare, q in (0,1]; ValueError su lista vuota o q fuori range

def scheda_economica(lordi: list[float], netti: list[float], pedaggio: float,
                     costo_stress_extra: float = 0.0) -> dict
# ritorna le chiavi: "n", "edge_lordo_medio", "edge_lordo_mediano", "netto_medio",
# "costo_medio", "costo_p95", "cost_to_edge", "copertura_pedaggio",
# "netto_stress_medio", "cost_to_edge_stress"
# costo_i = lordi_i - netti_i (per operazione); costo_medio = media dei costo_i;
# costo_p95 = percentili(costo_i, 0.95); cost_to_edge = costo_medio / edge_lordo_medio
# (None se edge_lordo_medio <= 0); copertura_pedaggio = netto_medio / pedaggio;
# netto_stress_i = netti_i - costo_stress_extra -> "netto_stress_medio";
# cost_to_edge_stress = (costo_medio + costo_stress_extra) / edge_lordo_medio (None se <= 0)

def benchmark_buyhold(chiusure: list[float], i_da: int, i_a: int) -> float
# chiusure[i_a] / chiusure[i_da] - 1; ValueError se finestra non valida

def benchmark_equal_weight(serie_per_simbolo: dict[str, list[float]],
                           i_da: int, i_a: int) -> float
# media aritmetica dei buy&hold dei singoli simboli; ValueError su dict vuoto

def incrementalita(valore_nuovo: float, valore_baseline: float) -> float
# valore_nuovo - valore_baseline
```

Input: liste di float / dict di liste e indici; Output: dict/float come sopra.
Errori: ValueError su liste vuote o finestre non valide (i_a <= i_da), dichiarati nei test.

## 5. Test prima del codice
- `test_scheda_numeri_esatti`: lordi e netti noti calcolati a mano → ogni campo della scheda
  verificato al decimale; il test deve fallire PRIMA dell'implementazione, e per la ragione
  corretta (modulo assente);
- `test_cost_to_edge_none_con_edge_negativo`: edge_lordo_medio <= 0 → None, non un numero;
- `test_stress_applica_lo_stack`: con costo_stress_extra=X i campi stressati cambiano della
  quantità esatta;
- `test_percentile_p95_interpolato`: caso noto di percentile con interpolazione;
- `test_benchmark_buyhold_e_equal_weight`: serie sintetiche a valori esatti;
- `test_incrementalita_zero_contro_se_stesso`: x - x = 0.0;
- `test_errori_dichiarati`: ValueError su input vuoto / finestra invalida.

## 6. Criteri di accettazione
- [ ] `python -m pytest tests/test_economia.py -q` verde (tutti i test sopra presenti)
- [ ] suite completa verde (nessuna regressione)
- [ ] ruff pulito
- [ ] nessuna modifica a file esistenti; solo `src/money/economia.py` + `tests/test_economia.py`
- [ ] output riproducibile dal commit indicato (solo stdlib)
- [ ] NOTE.md con cosa fatto + comando di verifica + risultato

## 7. Procedura di verifica
```bash
cd /home/sergio/money
python -m pytest tests/test_economia.py -q
python -m pytest -q
```

---

## Esito (30/09/2026, POST-numeri — sola registrazione)
**CONSEGNATA e INTEGRATA.** Esecutore: A0-PC (Agent Zero v2.13) su brief autosufficiente
(lint 7/7); consegna recuperata via endpoint file-browser, rieseguita in scratch (7/7) e
integrata da Hermes: `src/money/economia.py` + `tests/test_economia.py` (suite completa
verde). La spec resta la fonte del contratto: ogni estensione passa da qui.
