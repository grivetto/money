# Task ID: <uuid> — <titolo breve>

> Template-contratto per incarichi ad agenti senza storia (A0-MC2, A0-PC, DSH).
> Compilare OGNI sezione. Validazione prima dell'invio: `python scripts/spec_lint.py <questo-file> --strict`

## 1. Obiettivo verificabile
Implementare <una sola cosa> affinche' <comportamento osservabile e misurabile>.

## 2. Contesto autonomo
- repository: money @ commit `abc1234` (SHA reale del repo; per task su altre macchine: percorso esatto)
- percorso di lavoro: /home/sergio/money/<...>
- file rilevanti: <elenco preciso>
- vincoli: solo stdlib | niente rete | niente dati live | ...
- termini definiti: <definizioni operative dei termini ambigui>

## 3. Fuori scope
- non modificare <file/aree>
- non usare dati live, exchange o rete esterna
- non cambiare API o schema oltre quanto indicato

## 4. Specifica input/output
Input: <schema JSON o firma funzione, con esempio>
Output: <schema JSON o file prodotto, con esempio>
Errori: <casi e messaggi attesi>

## 5. Test prima del codice
- test_<nome>: dato <fixture concreta>, atteso <assert verificabile>;
  il test deve fallire PRIMA dell'implementazione, e per la ragione corretta
- test_<edge>: dato <fixture>, atteso <assert>

## 6. Criteri di accettazione
- [ ] test nuovi verdi
- [ ] suite esistente verde
- [ ] ruff/lint verdi
- [ ] nessuna modifica fuori scope
- [ ] output riproducibile dal commit indicato
- [ ] NOTE.md con cosa fatto + come verificato

## 7. Procedura di verifica
```bash
<pytest tests/<file> -q>
<eventuale comando di prova end-to-end>
```

## 8. Consegna
Scrivere i file nel percorso di lavoro, poi copiarli nel canale di consegna indicato
(es. `ponte-dsh/` per A0-PC, `workdir/<task>/` per A0-MC2). Riportare infine:
- commit: <sha>
- file modificati: <elenco>
- test eseguiti: <comando + risultato>
- rischi residui: <elenco>
