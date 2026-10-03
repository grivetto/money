# P14 — Certificato di consegna + review (A0-mc2 → Hermes)

Consegna A0-mc2 del 2026-10-03 (contesto `guRkI60g`). File originali conservati:
- `misura_p14_A0mc2_consegnato.py` — runner come consegnato (24.161 B; docstring/const ok)
- `test_misura_p14_A0mc2_consegnato.py` — test "13/13" del container (non integrati: coprivano
  solo funzioni pure con mock fragili)
- `NOTE_A0mc2.md` — note della consegna
- `BRIEF-P14.md` — brief inviato
- `misura_p14_integrato_hermes.py` — copia del runner integrato (per confronto)

## Review Hermes (findings)
1. Il runner consegnato NON era integrabile così com'era: import auto-referenziali
   (`from .misura_p14 import ...`), `M`/`get_tariffa`/`t_stat` non definiti nel modulo dopo lo
   spostamento "lazy" degli import (il percorso reale sarebbe crashato), `_pulito`/`_scrivi`
   mancanti, mock-fallback silenziosi in `allena()` (avrebbero avvelenato la misura vera),
   chiamate API errate (`get_tariffa(..., slippage_bp_lato=...)` non esiste; `giudica(...)`
   posizionale) e import sbagliati (`misura_config` importato da `scripts.*`).
2. I test del container passavano perché testavano solo funzioni pure isolate — non
   `main`/`allena` reali.
3. Difetti meccanici già corretti in corsa da Hermes per sbloccare l'agente: 5 stringhe rotte
   (`\n` letterali dentro stringhe, righe 362/367/371/430-432/463-464).

## Integrazione (commit `[hermes] P14: ...`)
Il runner è stato RICOSTRUITO da `scripts/misura_p10.py` (riferimento integrato e funzionante)
applicando SOLO le delta dichiarate P14: universo ampio via selettore (stile P5), griglia
{k:3,5} x {L:60,120} x {R:7,14}, riferimento P10 non eleggibile, stress slippage x2, artefatti
`P14_*`. La selezione (max exp/dd con >= 30 operazioni eseguite; riferimento fuori per
costruzione) è quella dichiarata nella spec pre-registrata.

Test del repo: `tests/test_misura_p14.py` (9 test sulle regole dichiarate; sostituiscono i 13
del container che non coprivano l'integrazione).

Esito misura ufficiale: vedi `prove/P14_momentum_universo.{txt,json}` + voce nel registro.
