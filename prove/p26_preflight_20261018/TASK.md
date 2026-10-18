# TASK — Preflight dati P26 (cointegrazione v2): salute dell'archivio candele USDT

Sei un operaio di analisi del progetto "money". Produci il PREFLIGHT DATI per la spec P26 (cointegrazione rolling su universo esteso). Lavora SOLO dentro ~/opencode-scratch/p26-preflight/ (crea la directory).

## Perche'
La spec P26 richiede candele giornaliere USDT con storia lunga: addestramento [2020-01-01, 2024-06-01), verifica [2024-06-01, oggi]. Prima di implementare va certificato che l'archivio regga: copertura, buchi, varianza. Un dataset difettoso farebbe morire la voce al cancello per un problema di raccolta.

## Dati
Su mc2, cartella ~/money/data/cache/: file `okx_eea_<SYM>-USDT_1d.json` (circa 90 file).
Formato: {"venue":"okx_eea","hostname":"eea.okx.com","simbolo":"BTC/USDT","timeframe":"1d","barre":[[ts_ms,o,h,l,c,v],...]} — ts_ms millisecondi UTC, o/h/l/c prezzi, v volume.

Accesso: leggi via ssh BatchMode (es. ssh -o BatchMode=yes mc2 'cat ~/money/data/cache/okx_eea_BTC-USDT_1d.json'), oppure copia i file nel tuo scratch con scp (sono ~100-180 KB ciascuno). NON scrivere nulla su mc2.

## Cosa produrre (per OGNI file)
1. simbolo, n barre, primo e ultimo giorno (ISO UTC)
2. copertura % su [2020-01-01, 2024-06-01) e su [2024-06-01, ultima barra] (barre presenti / giorni attesi)
3. n giorni mancanti (buchi) nel range totale + i 5 buchi piu' lunghi (da-a, durata giorni)
4. volume medio giornaliero su [2020-01-01, 2024-06-01)
5. min/max del close (verifica varianza non degenere: min==max sarebbe un problema)

Riepilogo:
- classifica TUTTE le coppie per volume medio di addestramento (decrescente)
- VERDETTO per coppia: IDONEA se copertura >= 95% in ENTRAMBE le finestre E prima barra <= 2020-01-01; altrimenti NON IDONEA con motivo
- lista finale "candidate top 30": le prime 30 IDONEE per volume (input per P26; se ce ne sono meno di 30, elencale tutte e dichiaralo)

## Output (in ~/opencode-scratch/p26-preflight/)
- `p26_preflight.json` — tutti i numeri
- `p26_preflight.md` — tabelle leggibili (per file + classifica + verdetti)
- `DONE.md` — comando esatto eseguito, output sintetico, anomalie

## Regole
- SOLO lettura dei dati; NON modificare nulla su mc2; scrivi SOLO nel tuo scratch.
- Niente chiavi. Rete solo via ssh verso mc2 per leggere i file.
- Usa python3; se pandas manca, usa stdlib json+datetime (dichiaralo nel report). Se serve un venv, crealo con uv (come nel task E2).
- Numeri ESATTI, mai stimati. Se un file e' illeggibile, scrivilo nel report, non inventare.
- Il range "oggi" = ultima barra presente; dichiara la data usata come fine finestra di verifica.
