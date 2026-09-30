"""Test di `money.verifica_provenienza` — manifest SHA256 e verifica byte-per-byte.

PERCHE' QUESTI TEST ESISTONO
============================
Alcuni verdetti di ricerca dipendono da cache dati che vivono fuori da questo repo: se la cache
cambia, il verdetto non e' piu' riproducibile e nessuno se ne accorge (difetto §1.3 dell'audit
dsh, vedi `coda_catena/M1_release_validazione.md` item 12). Questo modulo e' lo strumento che
rende il difetto visibile: manifest deterministico + verifica byte-per-byte con report di file
modificati / mancanti / in piu'. I test bloccano i comportamenti su cui si appoggia il registro:
determinismo, fallimento su un byte cambiato, segnalazione dei file nuovi.

Implementazione: task P9 del nastro, consegnata da Agent Zero (v2.13, 2026-09-30) e integrata
da Hermes dopo review; test adattati alle convenzioni del repo.

Convenzioni: niente `tempfile`/`tmp_path` (la sandbox nega `mkdtemp`) — si usa
`cartella_temporanea()` di `conftest`.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from conftest import cartella_temporanea
from money.verifica_provenienza import (
    crea_manifest,
    leggi_manifest,
    scrivi_manifest,
    verifica,
)


def test_a_manifest_deterministico():
    """(a) Manifest deterministico: due chiamate sulla stessa cartella => identici byte-per-byte."""
    test_dir = cartella_temporanea("p9a")
    (test_dir / "a.txt").write_text("contenuto A")
    (test_dir / "b.txt").write_text("contenuto B")
    (test_dir / "sub").mkdir()
    (test_dir / "sub" / "c.txt").write_text("contenuto C")

    manifest1 = crea_manifest(str(test_dir))
    manifest2 = crea_manifest(str(test_dir))

    assert manifest1 == manifest2, f"Manifest non deterministici:\n1: {manifest1!r}\n2: {manifest2!r}"

    lines = manifest1.strip().split("\n")
    paths = [line.split("  ", 1)[1] for line in lines]
    assert paths == sorted(paths), f"Path non ordinati: {paths}"
    assert manifest1.endswith("\n"), "Manifest deve terminare con newline"


def test_b_verifica_verde():
    """(b) Verifica verde su cartella invariata."""
    test_dir = cartella_temporanea("p9b")
    (test_dir / "file1.txt").write_text("test content")
    (test_dir / "file2.txt").write_text("another content")

    manifest = crea_manifest(str(test_dir))
    result = verifica(str(test_dir), manifest)

    assert result["ok"] is True, f"Verifica dovrebbe essere OK: {result}"
    assert result["ok_count"] == 2, f"ok_count: {result['ok_count']}"
    assert result["modificati_count"] == 0
    assert result["mancanti_count"] == 0
    assert result["in_piu_count"] == 0
    assert result["errore"] is None


def test_c_fallisce_byte_cambiato():
    """(c) FALLISCE se cambia un byte in un file."""
    test_dir = cartella_temporanea("p9c")
    file_path = test_dir / "data.txt"
    file_path.write_text("original content")

    manifest = crea_manifest(str(test_dir))

    file_path.write_text("original contenX")  # 't' -> 'X'

    result = verifica(str(test_dir), manifest)

    assert result["ok"] is False, "Verifica dovrebbe fallire"
    assert result["modificati_count"] == 1, f"modificati_count: {result['modificati_count']}"
    assert "data.txt" in result["modificati_files"]
    assert result["ok_count"] == 0


def test_d_fallisce_file_mancante():
    """(d) FALLISCE se un file manca."""
    test_dir = cartella_temporanea("p9d")
    (test_dir / "keep.txt").write_text("keep")
    (test_dir / "remove.txt").write_text("remove")

    manifest = crea_manifest(str(test_dir))

    (test_dir / "remove.txt").unlink()

    result = verifica(str(test_dir), manifest)

    assert result["ok"] is False, "Verifica dovrebbe fallire"
    assert result["mancanti_count"] == 1, f"mancanti_count: {result['mancanti_count']}"
    assert "remove.txt" in result["mancanti_files"]
    assert result["ok_count"] == 1
    assert "keep.txt" in result["ok_files"]


def test_e_segnala_file_in_piu():
    """(e) Segnala i file 'in piu'' (non presenti nel manifest)."""
    test_dir = cartella_temporanea("p9e")
    (test_dir / "original.txt").write_text("original")

    manifest = crea_manifest(str(test_dir))

    (test_dir / "extra.txt").write_text("extra")

    result = verifica(str(test_dir), manifest)

    assert result["ok"] is False, "Verifica dovrebbe fallire per file in piu'"
    assert result["in_piu_count"] == 1, f"in_piu_count: {result['in_piu_count']}"
    assert "extra.txt" in result["in_piu_files"]
    assert result["ok_count"] == 1
    assert "original.txt" in result["ok_files"]


def test_f_ordine_stabile_sottocartelle():
    """(f) Ordine stabile con sottocartelle (create in ordine non alfabetico)."""
    test_dir = cartella_temporanea("p9f")
    (test_dir / "zeta").mkdir()
    (test_dir / "zeta" / "a.txt").write_text("a")
    (test_dir / "alpha").mkdir()
    (test_dir / "alpha" / "b.txt").write_text("b")
    (test_dir / "root.txt").write_text("root")

    manifest = crea_manifest(str(test_dir))

    lines = manifest.strip().split("\n")
    paths = [line.split("  ", 1)[1] for line in lines]
    expected_order = ["alpha/b.txt", "root.txt", "zeta/a.txt"]
    assert paths == expected_order, f"Ordine errato: {paths} != {expected_order}"

    result = verifica(str(test_dir), manifest)
    assert result["ok"] is True


def test_g_cartella_vuota_e_manifest_malformato():
    """(g) Cartella vuota => manifest vuoto; manifest malformato => errore chiaro."""
    test_dir = cartella_temporanea("p9g")
    empty_dir = test_dir / "empty"
    empty_dir.mkdir()

    manifest = crea_manifest(str(empty_dir))
    assert manifest == "", f"Cartella vuota deve produrre manifest vuoto: {manifest!r}"

    result = verifica(str(empty_dir), manifest)
    assert result["ok"] is True
    assert result["ok_count"] == 0

    malformed1 = "abc123  file.txt\nnot_a_valid_line\n"
    result = verifica(str(empty_dir), malformed1)
    assert result["ok"] is False
    assert result["errore"] is not None
    assert "malformato" in result["errore"].lower()

    malformed2 = "short  file.txt\n"
    result = verifica(str(empty_dir), malformed2)
    assert result["ok"] is False
    assert result["errore"] is not None
    assert "sha256" in result["errore"].lower() or "non valido" in result["errore"].lower()

    malformed3 = "g" * 64 + "  file.txt\n"
    result = verifica(str(empty_dir), malformed3)
    assert result["ok"] is False
    assert result["errore"] is not None


def test_extra_scrivi_leggi_manifest():
    """Extra: scrivi_manifest e leggi_manifest tornano lo stesso contenuto.

    Nota di review: il manifest va scritto FUORI dalla cartella scansionata — altrimenti
    diventa lui stesso un file "in piu'" e la verifica fallisce (bug trovato in review,
    sistemato qui).
    """
    base = cartella_temporanea("p9x")
    scan_dir = base / "scan"
    scan_dir.mkdir()
    (scan_dir / "test.txt").write_text("test")

    manifest = crea_manifest(str(scan_dir))
    manifest_path = base / "manifest.txt"

    scrivi_manifest(str(manifest_path), manifest)
    read_back = leggi_manifest(str(manifest_path))

    assert read_back == manifest, f"Manifest letto diverso: {read_back!r} != {manifest!r}"

    result = verifica(str(scan_dir), read_back)
    assert result["ok"] is True


def test_extra_file_grande():
    """Extra: file grande (>8KB) — verifica del chunk reading e dello SHA corretto."""
    test_dir = cartella_temporanea("p9y")
    large_content = "x" * 20000
    (test_dir / "large.txt").write_text(large_content)

    manifest = crea_manifest(str(test_dir))
    result = verifica(str(test_dir), manifest)

    assert result["ok"] is True
    assert result["ok_count"] == 1

    expected_sha = hashlib.sha256(large_content.encode()).hexdigest()
    actual_sha = manifest.strip().split("\n")[0].split("  ", 1)[0]
    assert actual_sha == expected_sha, f"SHA errato: {actual_sha} != {expected_sha}"


def test_extra_unicode_filenames():
    """Extra: nomi file unicode."""
    test_dir = cartella_temporanea("p9z")
    (test_dir / "文件.txt").write_text("contenuto cinese")
    (test_dir / "файл.txt").write_text("contenuto russo")

    manifest = crea_manifest(str(test_dir))
    result = verifica(str(test_dir), manifest)

    assert result["ok"] is True
    assert result["ok_count"] == 2
    assert "文件.txt" in manifest
    assert "файл.txt" in manifest
