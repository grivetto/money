# P5 — Donchian puro su universo ESTESO (robustezza del t-stat)
STATO: PRESA_DA hermes 2026-09-27
DATI: USDT-lungo (2020-10-01 -> oggi; confine 2024-06-01)

## Perche' esiste (nato dalla misura, non dalla speranza)
Sull'universo da 10 simboli il Donchian puro (config 55/20) passa 6/8 criteri con margini
enormi (IC90 positivo, copertura 14,5x, PF 1,97, EUR/anno +474) e cade solo su t=1,620
(vs 1,650) e DD 47%. Il t e' funzione di n: con piu' simboli indipendenti la stima si
stringe intorno alla media vera SE l'edge e' reale. Questo e' un test di ROBUSTEZZA,
dichiarato prima del risultato: universo = tutte le coppie USDT di eea.okx.com con
copertura >= 95% dal 2020-10-01 (la lista la decide la copertura, non noi).

## Regola (identica al nodo I, nessun parametro nuovo)
Entrata: chiusura > max(massimi[i-55 .. i-1]) -> apertura i+1. Uscita: chiusura <
min(minimi[j-21 .. j-2]) -> apertura j. Una posizione alla volta. Stessa griglia 6 config,
stesso protocollo, stessa verifica.

## Cosa NON e' 
Non e' un tentativo di "far passare" variando l'universo: se l'edge fosse di 10 simboli
solo, allargare lo diluisce e il verdetto peggiora. Il test e' a due esiti e li accettiamo
entrambi. Il DD resta comunque da domare: P2/P3 restano la priorita' vera.
