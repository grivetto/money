"""money.mosaico — carry dinamico market-neutral (MOSAICO-4), nucleo deterministico.

Questa e' la fetta SICURA del sistema descritto in «MOSAICO-4 — sistema di trading
event-driven per quattro macchine» (§11 del documento): modelli, economia, segnale,
macchina a stati. Non contiene alcun percorso live, non apre ordini, non tocca chiavi.

Regola fondante (eredita da P0, docs/27): l'UNICO punto che puo' inviare un ordine e'
`money.esecuzione.invio.invia_gamba`. Qui si decide SOLO se un hedge group e'
economicamente valido e come transita negli stati; l'invio vive altrove.

La distribuzione su quattro macchine (§6) resta un traguardo documentato: prima il
simulatore fault-injected (§8 Fase 1), poi shadow, poi canary. Nessun nodo live ora.
"""
