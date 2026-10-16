#!/usr/bin/env python3
"""fix_registro_backtick.py — ripara i testi dove i backtick sono stati interpretati
come comandi dalla shell durante l'append al registro.

Il problema: l'append e' stato fatto con un heredoc non quotato, quindi le
sottostringhe tra backtick sono state eseguite come comandi e sostituite con
stringa vuota. Qui si reinseriscono i nomi dei file al posto giusto.
"""
from __future__ import annotations

import re
from pathlib import Path

P = Path("/home/sergio/money/prove/REGISTRO_ESPERIMENTI.md")

# (testo corrotto -> testo corretto)
FIX = [
    ("(modulo  scritto il 27/09", "(modulo `src/money/ricerca/basis_scadenza.py` scritto il 27/09"),
    ("Runner nuovo : 154 future", "Runner nuovo `scripts/misura_basis.py`: 154 future"),
    ("Artefatti: , modulo",
     "Artefatti: `scripts/misura_basis.py`, `prove/E_basis_scadenza.json`, modulo"),
    ("trovato che la ricerca di edge non girava:  dava copertura 0,0%",
     "trovato che la ricerca di edge non girava: `raccogli_funding --report 7` "
     "dava copertura 0,0%"),
    ("non esisteva,  vuota", "non esisteva, `data/tick/` vuota"),
    ("Creati su MARCODG1:  (ogni ora", "Creati su MARCODG1: `money-ricerca-raccolta.timer` (ogni ora"),
    ("e  (ogni 6h", "e `money-ricerca-scansione.timer` (ogni 6h"),
    ("Script: .", "Script: `deploy/scripts/cron_ricerca_{raccolta,scansione}.sh`."),
    ("Artefatti: `prove/P19_funding_multivenue.json`, `prove/P19b_funding_media.json`, , ",
     "Artefatti: `prove/P19_funding_multivenue.json`, `prove/P19b_funding_media.json`, "
     "`scripts/misura_p19.py`, `scripts/misura_p19b.py`."),
    ("Artefatti: , , , , , , ",
     "Artefatti: `scripts/misura_p16.py`, `scripts/misura_p17.py`, `scripts/misura_p18.py`, "
     "`prove/P16_domatore.json`, `prove/P17_sequenziale.json`, `prove/P18_regime.json`."),
    ("Artefatti: , , ",
     "Artefatti: `scripts/misura_p15_mvrv.py`, `prove/P15_mvrv_regime_2026-10-15.md`, "
     "`prove/P15_mvrv_regime.json`."),
    ("setaccia_onchain aveva mostrato", "`setaccia_onchain` aveva mostrato"),
]


def main() -> int:
    t = P.read_text(encoding="utf-8")
    prima = t
    for vecchio, nuovo in FIX:
        if vecchio in t:
            t = t.replace(vecchio, nuovo)
    # pulizia: doppio spazio dopo i due punti, spazi orfani
    t = re.sub(r"Artefatti: (?:, )+", "Artefatti: ", t)
    t = re.sub(r"  +", " ", t)
    if t != prima:
        P.write_text(t, encoding="utf-8")
        print("OK: registro riparato")
    else:
        print("nessuna modifica necessaria")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
