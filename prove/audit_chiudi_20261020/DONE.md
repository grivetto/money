# DONE — audit `scripts/carry_chiudi.py` (P28), READ-ONLY

Audit avversariale completato. Commit su `mc2:~/money`: `ab5ac4595c971dc4af6d778bce2384569c8a798e`.
Nessuna modifica al repo, nessuna chiave letta, nessun ordine inviato. Tutte le scritture sono nel
workspace `~/opencode-scratch/audit-chiudi/`.

## Comandi esatti usati

Copia in sola lettura dei file (output in `raw/`):

```bash
mkdir -p /home/sergio/opencode-scratch/audit-chiudi/raw
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/carry_chiudi.py' > raw/carry_chiudi.py
ssh -o BatchMode=yes mc2 'cat ~/money/coda_catena/P28_chiusura_carry_multi.md' > raw/P28.md
ssh -o BatchMode=yes mc2 'cat ~/money/tests/test_carry_chiudi.py' > raw/test_carry_chiudi.py
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/canary_carry.py' > raw/canary_carry.py
ssh -o BatchMode=yes mc2 'cat ~/money/src/money/esecuzione/invio.py' > raw/invio.py
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/carry_multi.py' > raw/carry_multi.py
ssh -o BatchMode=yes mc2 'cat ~/money/prove/audit_capitale_20261019/AUDIT.md' > raw/AUDIT_prev.md
ssh -o BatchMode=yes mc2 'cat ~/money/scripts/carry_apri.py' > raw/carry_apri.py
```

Commit e impronte:

```bash
ssh -o BatchMode=yes mc2 'cd ~/money && git rev-parse HEAD && md5sum scripts/carry_chiudi.py coda_catena/P28_chiusura_carry_multi.md tests/test_carry_chiudi.py scripts/canary_carry.py src/money/esecuzione/invio.py scripts/carry_multi.py prove/audit_capitale_20261019/AUDIT.md scripts/carry_apri.py'
```

Grep di controllo su `carry_chiudi.py` (nessun match per `fetch_open_orders`, `amount_to_precision`,
`KILL`, `gate_pre_trade`, `gate_carry`, `posSide`, `marginMode`, `cancello`; solo le righe `mgn_mode`
95 e 465):

```bash
ssh -o BatchMode=yes mc2 'grep -n "fetch_open_orders\|amount_to_precision\|KILL\|gate_pre_trade\|gate_carry\|posSide\|marginMode\|mgn_mode\|cancello" ~/money/scripts/carry_chiudi.py'
ssh -o BatchMode=yes mc2 'grep -c "^def test_" ~/money/tests/test_carry_chiudi.py'
```

Versione ccxt:

```bash
ssh -o BatchMode=yes mc2 'grep -n "ccxt" ~/money/requirements*.txt ~/money/pyproject.toml 2>/dev/null; . ~/money/.venv/bin/activate 2>/dev/null; python -c "import ccxt; print(ccxt.__version__, ccxt.__file__)" 2>&1'
# pyproject.toml:11: "ccxt>=4.0"
# 4.5.54 /usr/local/lib/python3.12/dist-packages/ccxt/__init__.py
```

Sorgente ccxt (forma reale della posizione):

```bash
ssh -o BatchMode=yes mc2 "grep -n 'def parse_position' -A 90 /usr/local/lib/python3.12/dist-packages/ccxt/okx.py | sed -n '1,130p'"
ssh -o BatchMode=yes mc2 "grep -n 'def parse_position' -A 130 /usr/local/lib/python3.12/dist-packages/ccxt/okx.py | sed -n '85,135p'"
ssh -o BatchMode=yes mc2 "sed -n '5950,5990p' /usr/local/lib/python3.12/dist-packages/ccxt/okx.py"
```

Prova offline della forma `contracts` (nessuna chiave, nessuna rete):

```bash
ssh -o BatchMode=yes mc2 'cd /tmp && python3 - <<"PY"
import ccxt
ex = ccxt.okx({"options": {"defaultType": "spot"}})
m = {"id":"DOT-USD_UM_XPERP-310808","symbol":"DOT/USD:USD-310808","base":"DOT","quote":"USD","settle":"USD","type":"swap","spot":False,"margin":False,"swap":True,"linear":True,"inverse":False,"contract":True,"contractSize":1.0,"precision":{"amount":1,"price":0.0001},"limits":{"amount":{"min":1},"price":{}},"active":True}
for pos, ps in [("-8","net"),("8","net")]:
    p = ex.parse_position({"instId":"DOT-USD_UM_XPERP-310808","pos":pos,"posSide":ps,"mgnMode":"isolated","avgPx":"10","markPx":"10","upl":"0","lever":"1","liqPx":"100","mmr":"0","imr":"8","margin":"8","notionalUsd":"80","cTime":"1","uTime":"1"}, m)
    print(pos, ps, "-> contracts=", p["contracts"], "side=", p["side"], "marginMode=", p["marginMode"])
PY'
# -8 net -> contracts= 8.0 side= short marginMode= isolated
#  8 net -> contracts= 8.0 side= long marginMode= isolated
```

Repro mock del difetto A1 (copia del modulo in `prove/`, nessuna rete/chiave/ordine; scrive solo
`prove/stato_repro/`):

```bash
cd /home/sergio/opencode-scratch/audit-chiudi/prove && python3 repro_sign.py
```

Impronte locali:

```bash
cd /home/sergio/opencode-scratch/audit-chiudi && md5sum raw/*.py raw/*.md
```

## File letti, con md5

| file su `mc2:~/money` | md5 | copia locale |
|---|---|---|
| `scripts/carry_chiudi.py` | `324559f34835143bd10952804cfb6d26` | `raw/carry_chiudi.py` |
| `coda_catena/P28_chiusura_carry_multi.md` | `43ffd73c77fb8cd212c3f7a2991bda38` | `raw/P28.md` |
| `tests/test_carry_chiudi.py` | `562a5a738839d797a2d849097d8541ff` | `raw/test_carry_chiudi.py` |
| `scripts/canary_carry.py` | `880466c8e21e6502470210b3dfef29d3` | `raw/canary_carry.py` |
| `src/money/esecuzione/invio.py` | `6272631f6082dd5043fbc367e0ee7308` | `raw/invio.py` |
| `scripts/carry_multi.py` | `c701a2f3d6776a765cf842f73d57fd31` | `raw/carry_multi.py` |
| `prove/audit_capitale_20261019/AUDIT.md` | `94195a8733eb0f092d3af10d70e08b12` | `raw/AUDIT_prev.md` |
| `scripts/carry_apri.py` (contesto) | `398ea83085b026860eab84afa9e59197` | `raw/carry_apri.py` |

Le copie in `raw/` hanno gli stessi md5 dei file remoti (verificato con `md5sum`). La tabella
`costi.py` (112-119) è stata letta via `grep` remoto, non copiata; le righe citate sono nel testo
dell'audit.

## Conteggio difetti per severità

| severità | numero |
|---|---|
| ALTA | 3 |
| MEDIA | 10 |
| BASSA | 8 |
| **totale** | **21** |

Tutte le righe riguardano `scripts/carry_chiudi.py`; `scripts/carry_apri.py` è citato solo come
contesto per i campi di stato mancanti (`mgn_mode`, `status`, `qty_spot`/`ct_perp` disponibili).
Dettaglio: 3 ALTA = segno della posizione perp (A1), invio ambiguo (A2), gamba spot assente/naked
long (A3). 10 MEDIA = perp assente su una lettura (M1), `filled` del solo ultimo ordine (M2), cancel
non confermato nel reprice (M3), `free/total` + ordini pendenti (M4), vendita dell'intero saldo (M5),
`mgn_mode`/`posSide` (M6), `partial` non ritentato (M7), stato non atomico/senza lock (M8), stato
fail-open che cancella le altre coppie (M9), eccezioni non gestite tra le gambe (M10). 8 BASSA =
`clOrdId` datato/non persistito, `amount_to_precision` assente, fee del primo ordine persa, minimi
non ricontrollati, eventi senza qty/prezzo, NaN/None/stringhe, gia-chiusa senza aggiornare lo stato,
piano vs qty eseguita.

## Verifiche eseguite

- **24 test** nel file (`grep -c "^def test_"` = 24). Non lanciati: la suite avrebbe scritto cache
  sotto `~/money`; letti integralmente. Il mock usa `contracts` firmato, quindi non copre A1.
- **ccxt 4.5.54**: `parse_position` restituisce `contracts=8.0` sia per `pos=8` sia per `pos=-8`;
  la direzione è in `side` (`long`/`short`). Il codice a `170-175,259` usa `contracts` come se fosse
  firmato: per lo short del carry invia `sell reduceOnly` invece di `buy`.
- **Repro A1** (`prove/repro_sign.py`, mock con forma reale e `reduceOnly` OKX): per una posizione
  short -8 e spot 8, il piano stampa "perp 8 ct" e "sell 8 ct reduceOnly"; l'ordine è
  `('DOT/USD:USD-310808','sell',8.0, {'clOrdId':'dotx...','tdMode':'isolated','reduceOnly':True})`;
  la sede finta rifiuta (un sell reduceOnly non riduce uno short), `RC=1`, stato `chiusura_fallita`,
  perp -8 e spot 8 invariati. Output completo riproducibile con il comando sopra.
- **Fee**: `FEE_SPOT`/`FEE_PERP` (102-103) = `okx_eea_con_perp` 0,0008/0,0010 e
  `okx_eea_swap_lv1` 0,0002/0,0005, come `src/money/costi.py:112-119`.
- **Unico punto di invio**: `grep 'create_order(' scripts/carry_chiudi.py` = 0; solo `invia_gamba`
  (268,291,323,342). `reduceOnly` propagato da `invio.py:44-49`.
- **Nessun kill switch/gate di apertura** in `carry_chiudi.py`: verificato con grep; è l'eccezione
  intenzionale di P28 (chiusura = riduzione di rischio).
- **Nessuna scrittura su `~/money`**: gli `ssh` hanno eseguito solo `cat`, `grep`, `git rev-parse`,
  `md5sum` e una chiamata offline a `parse_position`. Nessuna chiave caricata, nessuna richiesta a
  OKX, nessun ordine.

## Consegna

- `AUDIT.md` — 21 difetti (tabella), sospetti smentiti, limiti.
- `DONE.md` — questo file.
- `handoff/` — copie di `AUDIT.md`, `DONE.md`, `raw/`, `prove/`, `MANIFEST.sha256` (sha256 di tutti
  i file elencati) e `READY` creato per ultimo.
