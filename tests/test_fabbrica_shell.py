"""La fabbrica non usa piu' la shell: shlex + allowlist + niente metacaratteri.

Il test dimostrativo: con shell=True un ';' avrebbe concatenato un secondo
comando; ora il comando intero viene RIFIUTATO e il file NON viene creato.
Revisione Manus 06/10, finding 4.1.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_RADICE = Path(__file__).resolve().parents[1]


def _carica(nome_file, nome_mod):
    spec = importlib.util.spec_from_file_location(nome_mod, _RADICE / "fabbrica" / nome_file)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_metacaratteri_rifiutati_e_nulla_viene_eseguito(tmp_path):
    fab = _carica("fabbrica.py", "fabbrica_shell_meta")
    marker = tmp_path / "creato.txt"
    rc, out = fab.sh("echo ciao; touch %s" % marker)
    assert rc == 98 and "RIFIUTATO" in out
    assert not marker.exists()


def test_binario_fuori_allowlist_rifiutato():
    fab = _carica("fabbrica.py", "fabbrica_shell_allow")
    rc, out = fab.sh("rm -rf /tmp/qualcosa")
    assert rc == 98 and "allowlist" in out


def test_comando_lecito_funziona():
    fab = _carica("fabbrica.py", "fabbrica_shell_ok")
    rc, out = fab.sh("git -C %s rev-parse --short HEAD" % _RADICE)
    assert rc == 0 and out.strip()


def test_cwd_esplicito_per_i_comandi_che_ne_hanno_bisogno(tmp_path):
    fab = _carica("fabbrica.py", "fabbrica_shell_cwd")
    (tmp_path / "file_marker_xyz").write_text("")
    rc, out = fab.sh("ls", cwd=str(tmp_path))
    assert rc == 0 and "file_marker_xyz" in out
