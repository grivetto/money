# coda_catena/ — la coda di lavoro della catena crea → testa → promuovi/archivia

COME FUNZIONA (regole della catena, 2026-09-27, Hermes direttore d'orchestra)
============================================================================

1. Ogni file `P*.md` e' una SPEC di famiglia: ipotesi, meccanica precisa (entrata, uscita,
   anti-look-ahead), griglia dichiarata, universo e dati.
2. Chi e' libero (Hermes su mc2, DSH/Agent Zero su Windows, eventuali sub-agent) **prende**
   una spec scrivendo in testa `STATO: PRESA_DA <chi> <data>` — una sola volta, primo arriva.
3. Si implementa in `src/money/ricerca/<nome>.py` seguendo le convenzioni dei nodi H-O
   (costi da `money.costi`, Esito del cancello, nessuna eccezione su zero operazioni).
4. Test obbligatori in `tests/ricerca/` PRIMA dei numeri (anti-look-ahead, chiusura di tutte
   le operazioni, costi).
5. Verdetto con `scripts/misura_catena*.py` (stesso protocollo: griglia dichiarata provata
   tutta in addestramento, verifica OOS, `giudica`, scenari tariffa).
6. Artefatti in `prove/<nodo>.{txt,json}`. Se archivia: si archivia, niente "quasi".
7. DSH resta proprietario di docs/ e della narrativa dei verdetti; Hermes di deploy,
   esecuzione e di questa coda. Chi prende una spec aggiorna lo STATO nel file.

DATI LUNGHI (la chiave di volta, verificata 2026-09-27)
=======================================================
Le coppie **USDT** su eea.okx.com arrivano a **gennaio 2019** (le EUR solo a 2023-12).
Per le spec marcate `DATI: USDT-lungo`: universo USDT, INIZIO 2019-01-01, CONFINE
2024-06-01 (addestramento 5,4 anni, verifica 2,3 anni). Fee identiche (a livello conto).
La conferma finale prima della promozione si rifa' SEMPRE sulle EUR (campione corto).

STATO DELLA CODA
================
- P1_trend_atr_stop.md ...... FATTA, ARCHIVIATA (ipotesi chandelier smentita; A/B: Donchian 6/8)
- P2_momentum_vol_target.md . LIBERA -> ASSEGNATA a dsh (priorita' massima: fix DD)
- P3_trend_filtro_200g.md ... PRESA_DA agent-zero 2026-09-27 (codice in site/projects/denaro-p3, integrazione Hermes dopo review)
- P4_funding_carry.md ....... PARCHEGGIATA (funding EEA = 96gg di storia, verificato da dsh: niente misura)
- P5_donchian_esteso.md ..... LIBERA -> la prende hermes (robustezza t su universo esteso)
