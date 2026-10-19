# DONE — audit dei percorsi del capitale (READ-ONLY)

## Cosa ho fatto
1. Copiato (solo lettura) i 6 file in ambito da `mc2` nel workspace, senza toccare `~/money`:
   `~/opencode-scratch/audit-capitale/src_tree/`.
2. Verificato che le copie locali sono **byte-identiche** a quelle remote con `md5sum` su entrambi i lati.
3. Letto i file con lo strumento di lettura locale e i file di contesto via `ssh`.
4. Scritto `AUDIT.md` (solo report: nessuna patch, nessuna modifica al repo).

Nessuno script del progetto è stato eseguito, nessuna chiave letta/stampata, nessun ordine,
nessuna scrittura sotto `~/money`. Le uniche scritture sono i file di questo workspace.

## Comandi esatti usati

### Lettura dei 6 file in ambito (in `~/opencode-scratch/audit-capitale/src_tree/`)
```bash
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/carry_apri.py'      > carry_apri.py
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/carry_multi.py'     > carry_multi.py
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/canary_carry.py'    > canary_carry.py
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/earn_move.py'       > earn_move.py
ssh -o BatchMode=yes mc2 'cat ~/money/src/money/esecuzione/invio.py'    > money/esecuzione/invio.py
ssh -o BatchMode=yes mc2 'cat ~/money/src/money/esecuzione/cancello.py' > money/esecuzione/cancello.py
```
(la creazione di `src_tree/` e delle sottocartelle è locale al workspace)

### Contesto (sempre in sola lettura, via ssh)
```bash
ssh -o BatchMode=yes mc2 'cd ~/money && cat src/money/esecuzione/cancello_carry.py'
ssh -o BatchMode=yes mc2 'cd ~/money && sed -n "1,200p"   src/money/esecuzione/esecutore.py'
ssh -o BatchMode=yes mc2 'cd ~/money && sed -n "200,340p" src/money/esecuzione/esecutore.py'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -n "def verifica_pre_trade" -A 60 src/money/rischio.py'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -n "class ParametriRischio" -A 40 src/money/rischio.py'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -n "rischio_aperto_eur|esposizione_beta_eur" --include=*.py src scripts tests'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -rn "create_order" --include=*.py .'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -rln "invia_gamba" --include=*.py .'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -n "MONEY_KILL_SWITCH" --include=*.py src scripts ops'
ssh -o BatchMode=yes mc2 'cd ~/money && sed -n "60,220p" scripts/okx_ops.py'
ssh -o BatchMode=yes mc2 'cd ~/money && grep -n "chiudi|def cmd_" scripts/carry_multi.py'
ssh -o BatchMode=yes mc2 'cd ~/money && cat tests/esecuzione/test_punto_unico_invio.py'
```

### Verifica di integrità delle copie (entrambi i lati, stesso output)
```bash
ssh -o BatchMode=yes mc2 'cd ~/money && md5sum scripts/carry_apri.py scripts/carry_multi.py \
    scripts/canary_carry.py scripts/earn_move.py src/money/esecuzione/invio.py \
    src/money/esecuzione/cancello.py src/money/esecuzione/cancello_carry.py \
    src/money/esecuzione/esecutore.py scripts/okx_ops.py'
cd ~/opencode-scratch/audit-capitale/src_tree && md5sum carry_apri.py carry_multi.py \
    canary_carry.py earn_move.py money/esecuzione/*.py
```
Esito: hash identici (es. `carry_apri.py 47b67df418d912cc02f0d342b211650d`,
`canary_carry.py 880466c8e21e6502470210b3dfef29d3`).

## Conteggio difetti per severità (totale 37)
| severità | n. | file:riga |
|---|---|---|
| ALTA | 8 | `carry_apri.py:204-214`, `carry_apri.py:216-229`, `carry_apri.py:62-66`, `canary_carry.py:388-403`, `canary_carry.py:429-439`, `canary_carry.py:463-472`, `canary_carry.py:524-557`, `earn_move.py:583-604` |
| MEDIA | 20 | `carry_apri.py:154-163`, `:177-183`, `:165-171`, `:196,217`, `:152,183,220-221`, `:134-259` · `carry_multi.py:56`, `:35-36`, `:82-85`, `:159-188` · `canary_carry.py:343-354`, `:367-374`, `:403-415`, `:187-189` · `earn_move.py:85-86,575-581`, `:633,692`, `:504-511`, `:516-518,552-570` · `cancello.py:30-43` · `okx_ops.py:114,172` (fuori elenco) |
| BASSA | 9 | `carry_apri.py:231-241`, `:197,218`, `:5,12,37,40` · `carry_multi.py:125-129` · `canary_carry.py:531` · `earn_move.py:384,398,407`, `:134,805`, `:516-518,598` · `invio.py:49-50` |

Dettaglio e giustificazione di ogni riga (con fix proposto) in `AUDIT.md`.
