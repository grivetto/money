"""conftest dei test di `money` — percorsi e isolamento senza `tempfile`.

PERCHE' QUESTA `cartella_temporanea()` ESISTE (e non si usa `tmp_path`)
=====================================================================
In questo ambiente la creazione di directory temporanee **e' negata dalla sandbox**:
`tempfile.mkdtemp()` e la fixture `tmp_path` di pytest falliscono con `PermissionError`
prima ancora di arrivare al codice sotto test. Il risultato, quando succede, e' il peggiore
possibile: la suite diventa rossa per un problema di permessi e non per un errore di logica,
e dopo due giorni di rossi "noti" nessuno guarda piu' la suite — che e' esattamente cio' che
era successo nel progetto precedente, dove i test erano stati commentati "temporaneamente".

La scoperta fatta allora, verificata qui: `os.makedirs()` (e `Path.mkdir()`) dentro il repo
**funziona**, mentre `mkdtemp()` no. Quindi l'isolamento si ottiene con una cartella locale
`.pytmp/` nella radice del repo, con un nome unico per chiamata (contatore + pid), e senza
dipendere dalla sandbox di sistema.

Alternative scartate: `tmp_path` (negata, vedi sopra); `pytest --basetemp` (stesso problema,
stessa directory di sistema); una cartella fissa condivisa (i test si calpestano a vicenda e
il fallimento dipende dall'ordine di esecuzione, cioe' dal caso).
"""
from __future__ import annotations

import itertools
import os
import sys
from pathlib import Path

import pytest

#: Radice del repo: `tests/conftest.py` -> parents[1].
RADICE = Path(__file__).resolve().parents[1]

#: Il pacchetto vive in `src/`: si aggiunge a `sys.path` qui invece di dichiarare
#: `pythonpath = ["src"]` in pyproject.toml, cosi' i test girano anche su un checkout appena
#: fatto, senza installazione e senza toccare la configurazione del progetto.
_SRC = RADICE / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_CARTELLA_BASE = RADICE / ".pytmp"
_contatore = itertools.count()


def cartella_temporanea(nome: str = "t") -> Path:
    """Crea e ritorna una cartella isolata dentro `<repo>/.pytmp/`.

    Il nome e' unico per processo e per chiamata (`nome-<pid>-<contatore>`), cosi' due test
    non condividono mai lo stesso percorso anche se girano in parallelo o se un test precedente
    ha lasciato file dietro. Non si cancella niente: se un test fallisce, i file che ha scritto
    restano li' da guardare — cosa che `tmp_path` non fa, e che nel progetto precedente
    costava mezz'ora di debug ogni volta.
    """
    _CARTELLA_BASE.mkdir(parents=True, exist_ok=True)
    percorso = _CARTELLA_BASE / f"{nome}-{os.getpid()}-{next(_contatore)}"
    percorso.mkdir(parents=True, exist_ok=True)
    return percorso


@pytest.fixture
def cartella() -> Path:
    """Fixture: una cartella isolata per il test che la chiede."""
    return cartella_temporanea("test")


# ---------------------------------------------------------------------------
# LA PATCH ALLA RADICE: perche' non basta `cartella_temporanea`
# ---------------------------------------------------------------------------
# Scoperto eseguendo la suite completa: `cartella_temporanea()` risolve i test che la
# chiamano, ma il modulo `money.dati` usa `tempfile.mkdtemp()` **al proprio interno**, e
# quelli fallivano ancora — 21 test rossi con `PermissionError`, indistinguibili da un
# errore di logica.
#
# La causa e' isolata e non e' "il temp di sistema": e' **`mkdtemp`** a essere rifiutata.
# `os.makedirs` funziona. Quindi si sostituisce `mkdtemp` con la stessa logica costruita
# su `os.makedirs`, e si punta la base dentro `.pytmp/` del repo. Cosi' si riparano in un
# punto solo tutte le strade che ci passano attraverso — `TemporaryDirectory`, `tmp_path`
# di pytest, e ogni chiamata interna al progetto — senza toccare nemmeno un test.
#
# La lezione vale oltre questo file: una suite che fallisce per l'ambiente e' peggio di
# una suite assente, perche' insegna a ignorarla.

def _mkdtemp_scrutable(suffix: str | None = None, prefix: str | None = None,
                       dir: str | None = None, max_tentativi: int = 100) -> str:
    """`tempfile.mkdtemp` rifatta su `os.makedirs`, che in questo ambiente funziona."""
    import tempfile

    base = dir or tempfile.gettempdir()
    pre = prefix if prefix is not None else tempfile.gettempprefix()
    suf = suffix or ""
    os.makedirs(base, exist_ok=True)
    for _ in range(max_tentativi):
        nome = os.path.join(base, f"{pre}{next(tempfile._get_candidate_names())}{suf}")
        try:
            os.makedirs(nome, exist_ok=False)
            return nome
        except FileExistsError:
            continue
    raise FileExistsError(f"mkdtemp: nessun nome libero in {base} dopo {max_tentativi} tentativi")


def _cleanup_non_fatale(self) -> None:  # pragma: no cover - ambiente, non logica
    """Chiude il finalizer senza cancellare a forza: il chmod qui puo' essere negato."""
    try:
        self._finalizer.detach()
    except Exception:
        pass


def pytest_configure(config) -> None:  # pragma: no cover - ambiente, non logica
    """Dirotta il temp nel repo e sostituisce `mkdtemp` alla radice.

    La `mkdir` e' protetta da `try`: se il repo e' in sola lettura (CI, checkout montato
    read-only, sandbox piu' stretta), senza quel `try` pytest **non parte affatto** —
    `INTERNALERROR: PermissionError` prima di raccogliere un solo test. Un guasto opaco
    che nasconde l'intera suite e' peggio di una suite rossa: si ripiega sul temp di
    sistema e si continua, dichiarandolo.
    """
    import tempfile

    base = _CARTELLA_BASE
    try:
        base.mkdir(parents=True, exist_ok=True)
    except OSError:
        base = Path(tempfile.gettempdir()) / f"money-pytmp-{os.getpid()}"
        try:
            base.mkdir(parents=True, exist_ok=True)
        except OSError:
            import pytest as _pytest
            _pytest.exit("nessuna base temporanea scrivibile: atteso .pytmp/ nel repo "
                         "oppure una directory temporanea di sistema", returncode=3)
    tempfile.tempdir = str(base)
    os.environ.setdefault("TMPDIR", str(base))
    os.environ.setdefault("TMP", str(base))
    os.environ.setdefault("TEMP", str(base))
    tempfile.mkdtemp = _mkdtemp_scrutable                  # type: ignore[assignment]
    tempfile.TemporaryDirectory.cleanup = _cleanup_non_fatale  # type: ignore[method-assign]
    # NB: NON impostare PYTEST_TMP_NUM. Pytest deduce il numero delle basetemp dalla base
    # esistente; forzandolo, `tmp_path` punta a una cartella che non esiste e il fixture
    # muore in setup. Errore gia' commesso una volta: non ripeterlo.
    os.environ.pop("PYTEST_TMP_NUM", None)
