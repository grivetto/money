# Proposta di miglioramenti — audit 2026-10-16

## Ambito dell’audit

L’analisi è stata eseguita sul branch `main` del repository `grivetto/money` clonato il 16/10/2026. Il progetto presenta già una struttura di ricerca molto più rigorosa rispetto al vecchio codebase: separazione tra dati, ricerca, costi, cancello e prove; test offline; controlli di provenienza; gestione fail-closed nel preflight; nessun LLM nel percorso caldo.

La suite dichiarata nel README è ampia e il lavoro principale non dovrebbe consistere nell’aggiungere altre strategie prima di aver dimostrato un edge. Le modifiche di questo branch sono quindi volutamente conservative e non cambiano le soglie statistiche, le strategie, il capitale o il percorso di invio degli ordini.

## Risultati prioritari

### P0 — installazione CI non fail-fast

Il workflow `.github/workflows/ci.yml` eseguiva:

```bash
pip install -e ".[dev]" 2>/dev/null || pip install -e . || true
```

Questa riga poteva dichiarare verde la fase di installazione anche dopo il fallimento dell’installazione delle dipendenze di sviluppo. Il comando successivo installava comunque solo `pytest` e `ruff`, quindi una dipendenza necessaria per i test poteva mancare senza rendere immediatamente evidente il motivo.

La patch sostituisce il fallback con:

```bash
python -m pip install -e ".[dev]"
python -m pip check
```

Il job ora fallisce se il pacchetto o le dipendenze non sono installabili e controlla esplicitamente la coerenza dell’ambiente Python.

### P1 — numerosità effettiva e assert runtime

Il cancello richiede ora sia `n >= 30` sia `n_effettivo >= 30`. Il numero grezzo di operazioni
non è una misura sufficiente quando i ritorni sono serialmente correlati o le posizioni si
sovrappongono: un campione di 100 operazioni può contenere meno di 30 osservazioni indipendenti.

Il criterio di indipendenza dai blocchi è ora **fail-closed**: se la scomposizione non è
valutabile, il criterio fallisce invece di essere considerato superato.

L’audit ha inoltre trovato quattro `assert` nei moduli di ricerca:

- chiusura di una posizione in `trend_lungo.py`;
- invariante della linea MACD in `scansione3.py`;
- indice di ingresso in `scansione.py`;
- allineamento degli indici ADF in `p13_cointegrazione.py`.

La CI esegue anche `python -O -m pytest`, modalità che rimuove gli `assert`. Un’invariante runtime non deve scomparire perché il processo è stato avviato con ottimizzazione.

La patch sostituisce i tre assert con `RuntimeError` espliciti e fail-closed. Il comportamento nominale resta invariato; cambia soltanto il comportamento in caso di corruzione dello stato o violazione dell’invariante.

È stato aggiunto `tests/test_no_runtime_assert.py`, che analizza l’AST dei moduli in `src/` e impedisce la reintroduzione accidentale di `assert` nel codice vivo.

## Verifiche da eseguire

Prima del merge:

```bash
python -m pip install -e ".[dev]"
python -m pip check
python -m pytest -q
python -O -m pytest -q
ruff check .
python -m compileall -q src scripts ops
```

Il branch non abilita trading live, non modifica chiavi API, non modifica soglie del cancello e non introduce chiamate di rete nei test.

## Miglioramenti successivi proposti, non inclusi in questa patch

1. Aggiungere un job CI con Python 3.11 e 3.12, perché il progetto dichiara `requires-python >= 3.11` ma oggi la CI verifica soltanto Python 3.12.
2. Generare e conservare un report di coverage per il codice finanziario, senza imporre inizialmente una soglia artificiale che premi quantità invece di qualità.
3. Aggiungere un controllo CI che verifichi che gli script live richiedano esplicitamente un flag di produzione e non partano mai in live per default.
4. Integrare PBO/CSCV nel percorso principale che produce i dati di selezione. Il modulo statistico
   già espone `pbo_cscv`, ma il runner principale non produce ancora un PBO completo e verificabile;
   non va quindi inserito nell’artefatto con un valore inventato.
5. Rendere esplicita la provenienza della tariffa nel formato degli artefatti di prova, collegando la misura all’hash del commit e alla data di verifica dell’account.
6. Separare ulteriormente test offline, test con rete pubblica e test con credenziali, con job distinti e credenziali sempre assenti nel job standard.

Questi interventi richiedono decisioni di compatibilità o accesso agli ambienti operativi e non sono stati inseriti automaticamente nel branch conservativo.
