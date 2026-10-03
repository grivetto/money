# PROTOCOLLO — consegna atomica degli handoff

Lane: **DSH-win (PROTCON)**, 03/10/2026. Compagno di questo file: `fabbrica/handoff_atomico.py`
(solo stdlib), test in `tests/test_handoff_atomico.py`.

Il problema che chiude, in una riga: **un handoff non deve mai essere integrato a meta',
due volte, o da due riceventi insieme.** Le primitive qui sotto sono tutte fail-closed:
in dubbio, NON si integra e si dice perche'.

---

## 1. Struttura di una consegna

```
handoff/<ID>/
  NOTE.md               # comando + esito REALE (a carico del mittente)
  <albero del repo>     # i file da integrare, nel layout del repo (es. fabbrica/, tests/)
  MANIFEST.sha256       # generato da seal(); NON contiene se stesso
  READY                 # JSON, scritto PER ULTIMO
```

- `MANIFEST.sha256`: formato di `sha256sum` — una riga per file,
  `<sha256>  <percorso relativo>` (due spazi). Copre tutti i file del pacchetto.
- `READY`: JSON `{protocollo, key, manifest, sender, created_at, files}`.
  `key` = sha256 dei **byte di MANIFEST.sha256**: e' la chiave di consegna e, insieme,
  la chiave di idempotenza.
- Fuori dal manifest e considerati non-payload: `MANIFEST.sha256`, `READY`,
  `CLAIMED-*`, `*.tmp-*`. Non sono "extra" e non fanno fallire la verifica.

**Regola d'oro:** `READY` esiste **solo** se il pacchetto e' completo. Non si copia a
mano, non si crea "vuoto per far partire la review": lo scrive `seal()` per ultimo.

## 2. Ordine del mittente

1. Scrivere i payload (l'albero dei file da integrare).
2. Scrivere `NOTE.md` con il comando e l'esito **reale** (output incollato, non "sembra ok").
3. Sigillare: `seal(root, sender)` — calcola e scrive il manifest, poi scrive `READY`
   per ultimo, atomicamente (`tmp` -> `fsync` -> `rename`).
4. (Consigliato) Verificare: `verify(root)`.

Trasporto: il protocollo **non trasporta** (niente rete, niente ssh: lo fa il chiamante).
Se il trasporto puo' riordinare i file, trasferire i payload e ricreare/incollare `READY`
per ultimo — cosi' un ricevente non vede mai un pacchetto "pronto" incompleto.

## 3. Ricevente — presa atomica

`claim(root, claimer)` esegue `rename(READY -> CLAIMED-<claimer>)`:

- il rename e' atomico a livello di filesystem: **un solo** ricevente lo esegue;
- gli altri trovano la sorgente gia' spostata e ricevono `AlreadyClaimedError`
  (non un silenzio, non una seconda integrazione);
- e' idempotente per nome: se `CLAIMED-<claimer>` esiste gia', solleva
  `AlreadyClaimedError`;
- nome claimer validato (`[A-Za-z0-9._-]{1,64}`), cosi' non si scrive fuori dalla cartella.

Su **POSIX** (dove gira la fabbrica) il rename e' l'unico cancello e non lascia stato: nessun
lock da recuperare. Su **Windows** il filesystem lascia passare piu' rename dello stesso
sorgente, quindi la presa e' serializzata da un lock `O_EXCL` (`READY.lock`), tenuto per il
tempo di un rename e recuperato dopo 10 s se un processo muore mentre lo tiene.

## 4. Integrazione idempotente

`integrate_once(root, ledger_root, claimer, integra)`, nell'ordine:

1. **verifica** (manifest + chiave) — fail-closed;
2. **presa atomica** (`claim`);
3. **idempotenza**: se la chiave e' gia' `done` -> `duplicate`, `integra` NON
   viene richiamata;
4. **in-flight** (`O_EXCL`): se un altro ricevente ha la chiave in corso -> `in-flight`;
5. **integra**, poi registra `done`; se `integra` solleva, libera `inflight`
   e l'eccezione risale (riprovabile).

Stati ritornati: `integrated` | `duplicate` | `in-flight` |
`already-claimed`.

Il registro (`Ledger`) e' una cartella con due marker per chiave:
`<key>.inflight` (presa in carico) e `<key>.done` (integrata). Entrambi creati in
`O_EXCL`: la creazione e' il cancello, non un `if` seguito da una scrittura.
**Un crash lascia `inflight`, non `done`**: nessuno integra in parallelo senza
accorgersene, e la consegna resta riprovabile.

La chiave e' il **contenuto**: stesso manifest = stessa consegna = una sola integrazione;
un byte diverso in un payload cambia l'hash e quindi la chiave.

## 5. Cosa e' fail-closed (nessun override silenzioso)

| condizione | errore |
| :--- | :--- |
| `READY` assente | `NotReadyError` |
| manifest assente o malformato | `ManifestError` |
| file mancante, hash diverso | `ManifestError` |
| percorso assoluto o con `..` nel manifest | `ManifestError` |
| symlink fra i file dichiarati | `ManifestError` |
| file presente ma non dichiarato (strict) | `ManifestError` |
| `key` in `READY` != sha256 del manifest | `ManifestError` |
| risigillo senza `force=True` | `HandoffError` |

La verifica raccoglie **tutti** i problemi e li riporta insieme: un manifest rotto si vede
tutto in un colpo, non un errore per giro.

## 6. CLI

```
python fabbrica/handoff_atomico.py seal   <dir> --sender DSH-win [--exclude p] [--force]
python fabbrica/handoff_atomico.py verify <dir> [--no-strict]
python fabbrica/handoff_atomico.py claim  <dir> --claimer hermes
python fabbrica/handoff_atomico.py key    <dir>
python fabbrica/handoff_atomico.py status <dir>
```

Esito: `0` ok, `2` errore di protocollo (con messaggio su stderr). Le uscite di
`seal`/`verify`/`claim`/`key`/`status` sono JSON.

## 7. API (import dalla fabbrica)

```python
from handoff_atomico import seal, verify, claim, integrate_once, Ledger, chiave_consegna

payload = seal(dest, sender="DSH-win")            # manifest + READY (per ultimo)
esito   = verify(dest)                            # fail-closed; esito["key"]
r       = integrate_once(dest, "./ledger", claimer="hermes",
                         integra=lambda root: copia_nel_repo(root))
```

## 8. Cosa NON fa (e non deve fare)

- non trasporta file (nessuna rete, nessuna credenziale);
- non cancella ne' riscrive una consegna integrata;
- non giudica il *contenuto* della consegna: verifica l'integrita', non la correttezza;
- non legge segreti, `.env` o chiavi: i payload restano fuori dal protocollo.

## 9. Adozione in `fabbrica/`

- nel tick, al posto del solo `sha256sum -c`: `verify()` (aggiunge READY, chiave,
  extra-file e symlink al controllo);
- la chiave di consegna entra come `idempotency_key` nel job-store:
  `"handoff:" + key` — cosi' la stessa consegna non produce due job;
- `claim` prima di integrare, `integrate_once` per l'integrazione.

-- [dsh] lane PROTCON, 03/10/2026
