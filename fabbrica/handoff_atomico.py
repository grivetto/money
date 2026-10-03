#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Protocollo di consegna atomico per la Fabbrica — lane DSH-win (PROTCON), 03/10/2026.

Cosa risolve
------------
Gli handoff tra agenti erano "scrivi i file e spera": se la scrittura si interrompeva a
meta', il ricevente vedeva una cartella incompleta e la integrava lo stesso; se due
riceventi guardavano insieme, entrambi integravano; se il mittente recapitava due volte
(ricarica, retry), la stessa consegna finiva integrata due volte. Questo modulo chiude i
tre casi con quattro primitive, tutte **fail-closed**:

1. **Sigillo** (`seal`): l'albero dei file + `MANIFEST.sha256`, e il marker `READY`
   scritto **per ultimo**, in modo atomico (`tmp` -> `fsync` -> `rename`). `READY`
   esiste solo se il pacchetto e' completo; contiene la *chiave di consegna*
   (= sha256 del manifest), che e' anche la chiave di idempotenza.
2. **Verifica** (`verify`): ogni file della consegna confrontato con l'hash nel manifest;
   i file non dichiarati nel manifest sono un errore, non un dettaglio. Symlink rifiutati.
3. **Presa atomica** (`claim`): `rename(READY -> CLAIMED-<claimer>)`, esclusivo a livello
   di filesystem: un solo ricevente vince, gli altri vedono `AlreadyClaimedError`.
4. **Idempotenza** (`Ledger` + `integrate_once`): chiave = hash del manifest; la stessa
   consegna non si integra mai due volte, nemmeno con retry o crash. La presa in carico
   scrive `inflight` (O_EXCL) prima di integrare e `done` dopo: un crash lascia
   `inflight`, che NON e' `done` ed e' riprovabile.

Solo stdlib. Nessuna rete, nessuna chiave, nessun ordine. I tempi sono iniettabili
(`now`) per i test.

Protocollo sul filo (albero, marker, claim, idempotenza, CLI): `fabbrica/PROTOCOLLO.md`.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = "MANIFEST.sha256"
READY_NAME = "READY"
CLAIM_PREFIX = "CLAIMED-"
PROTOCOL = "handoff-atomico/1"
_CHUNK = 1 << 20
_CLAIMER_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
_RIGA_RE = re.compile(r"^([0-9a-fA-F]{64})[ \t]+\*?(.+?)\s*$")

__all__ = [
    "MANIFEST_NAME", "READY_NAME", "CLAIM_PREFIX", "PROTOCOL",
    "HandoffError", "ManifestError", "NotReadyError", "AlreadyClaimedError",
    "sha256_bytes", "sha256_file", "atomic_write_bytes", "atomic_write_text",
    "elenca_file", "build_manifest", "read_manifest", "verify_manifest",
    "chiave_consegna", "seal", "read_ready", "verify", "claim",
    "Ledger", "integrate_once", "main",
]


# ---------------------------------------------------------------------------
# Errori (tutti fail-closed: chi chiama NON deve proseguire)
# ---------------------------------------------------------------------------
class HandoffError(Exception):
    """Errore del protocollo di consegna."""


class ManifestError(HandoffError):
    """Il manifest non torna con l'albero: la consegna non e' integrabile."""


class NotReadyError(HandoffError):
    """Marker `READY` assente: la consegna non e' (ancora) sigillata."""


class AlreadyClaimedError(HandoffError):
    """`READY` gia' preso da un altro ricevente."""


# ---------------------------------------------------------------------------
# Primitive di filesystem: hash, fsync, scrittura atomica
# ---------------------------------------------------------------------------
def _now_iso(now=None) -> str:
    """Timestamp ISO-Z. `now`: None=adesso, numero=epoch, stringa=passata cosi' com'e'."""
    if now is None:
        istante = datetime.now(timezone.utc)
    elif isinstance(now, (int, float)):
        istante = datetime.fromtimestamp(float(now), timezone.utc)
    else:
        return str(now)
    return istante.strftime("%Y-%m-%dT%H:%M:%SZ")


def sha256_bytes(dati: bytes) -> str:
    """sha256 esadecimale di `dati`."""
    return hashlib.sha256(dati).hexdigest()


def sha256_file(percorso) -> str:
    """sha256 esadecimale di un file, letto a blocchi (file grandi senza caricarli in RAM)."""
    h = hashlib.sha256()
    with open(percorso, "rb") as f:
        for blocco in iter(lambda: f.read(_CHUNK), b""):
            h.update(blocco)
    return h.hexdigest()


def _fsync_dir(percorso) -> None:
    """Rende persistente una voce di directory (create/rename). Best-effort (Windows: no-op)."""
    try:
        fd = os.open(str(percorso), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def atomic_write_bytes(percorso, dati: bytes, mode: int = 0o644) -> Path:
    """Scrive `percorso` atomicamente: tmp nella stessa cartella -> fsync -> os.replace.

    Mai un file a meta': o c'e' il contenuto vecchio, o quello nuovo. Il rename e'
    atomico anche tra processi, quindi un lettore non vede mai il tmp.
    """
    percorso = Path(percorso)
    tmp = percorso.with_name("%s.tmp-%d-%s" % (percorso.name, os.getpid(), os.urandom(4).hex()))
    with open(tmp, "wb") as f:
        f.write(dati)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass
    os.replace(tmp, percorso)
    _fsync_dir(percorso.parent)
    return percorso


def atomic_write_text(percorso, testo: str, mode: int = 0o644) -> Path:
    """Come `atomic_write_bytes`, su testo UTF-8."""
    return atomic_write_bytes(percorso, testo.encode("utf-8"), mode=mode)


# ---------------------------------------------------------------------------
# Albero, manifest, verifica
# ---------------------------------------------------------------------------
def _e_protocollo(nome: str, manifest_name: str) -> bool:
    """True se il file e' generato dal protocollo stesso: fuori dal manifest e non 'extra'."""
    return (nome == manifest_name or nome == READY_NAME or nome.startswith(CLAIM_PREFIX)
            or nome == READY_NAME + ".lock" or ".tmp-" in nome)


def elenca_file(root, manifest_name: str = MANIFEST_NAME, exclude=()) -> list:
    """Percorsi relativi POSIX dei file del pacchetto, ordinati.

    Esclude i file di protocollo (`MANIFEST.sha256`, `READY`, `CLAIMED-*`, `*.tmp-*`),
    gli artefatti di build (`__pycache__/`) e quelli in `exclude`. Non segue i symlink di
    directory (`os.walk(followlinks=False)`).
    """
    root = Path(root)
    esclusi = {Path(e).as_posix() for e in exclude}
    fuori = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")   # artefatti, non payload
        rel_dir = Path(dirpath).relative_to(root)
        for nome in sorted(filenames):
            if _e_protocollo(nome, manifest_name):
                continue
            rel = (rel_dir / nome).as_posix() if str(rel_dir) != "." else nome
            if rel in esclusi:
                continue
            fuori.append(rel)
    return sorted(fuori)


def riga_manifest(rel: str, digest: str) -> str:
    """Riga nel formato di `sha256sum`: `<hash>  <percorso>` (due spazi)."""
    return "%s  %s\n" % (digest, rel)


def build_manifest(root, manifest_name: str = MANIFEST_NAME, exclude=()) -> dict:
    """Calcola gli hash di `root` e SCRIVE `<root>/MANIFEST.sha256` (atomicamente).

    Ritorna `{percorso_relativo: sha256}`. Il manifest NON contiene se' stesso.
    """
    root = Path(root)
    voci = {rel: sha256_file(root / rel) for rel in elenca_file(root, manifest_name, exclude)}
    testo = "".join(riga_manifest(rel, voci[rel]) for rel in sorted(voci))
    atomic_write_text(root / manifest_name, testo)
    return voci


def read_manifest(root, manifest_name: str = MANIFEST_NAME) -> dict:
    """Legge e valida `MANIFEST.sha256`. Solleva `ManifestError` se assente o malformato."""
    percorso = Path(root) / manifest_name
    try:
        testo = percorso.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ManifestError("manifest assente: %s" % percorso)
    voci: dict = {}
    for n, riga in enumerate(testo.splitlines(), 1):
        if not riga.strip() or riga.lstrip().startswith("#"):
            continue
        m = _RIGA_RE.match(riga)
        if not m:
            raise ManifestError("riga %d del manifest non valida: %r" % (n, riga))
        digest, rel = m.group(1).lower(), m.group(2)
        if rel in voci:
            raise ManifestError("voce ripetuta nel manifest: %s" % rel)
        voci[rel] = digest
    return voci


def verify_manifest(root, manifest_name: str = MANIFEST_NAME, exclude=(), strict: bool = True) -> dict:
    """Confronta l'albero con il manifest. Ritorna le voci se torna; altrimenti `ManifestError`.

    Fail-closed e completo: raccoglie TUTTI i problemi (mancanti, hash diversi, percorsi non
    sicuri, symlink, e con `strict=True` i file non dichiarati) e li riporta insieme.
    """
    root = Path(root)
    voci = read_manifest(root, manifest_name)
    problemi = []
    for rel, atteso in voci.items():
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts:
            problemi.append("percorso non sicuro nel manifest: %s" % rel)
            continue
        f = root / rel
        if not f.is_file():
            problemi.append("manca: %s" % rel)
            continue
        if f.is_symlink():
            problemi.append("symlink non ammesso: %s" % rel)
            continue
        reale = sha256_file(f)
        if reale != atteso:
            problemi.append("hash diverso: %s (atteso %s, trovato %s)" % (rel, atteso[:12], reale[:12]))
    if strict:
        dichiarati = set(voci)
        for rel in elenca_file(root, manifest_name, exclude):
            if rel not in dichiarati:
                problemi.append("non dichiarato nel manifest: %s" % rel)
    if problemi:
        raise ManifestError("manifest non verificato (%d problemi):\n  - %s"
                            % (len(problemi), "\n  - ".join(problemi)))
    return voci


def chiave_consegna(root, manifest_name: str = MANIFEST_NAME) -> str:
    """Chiave di consegna/idempotenza = sha256 dei byte di `MANIFEST.sha256`."""
    percorso = Path(root) / manifest_name
    try:
        return sha256_bytes(percorso.read_bytes())
    except FileNotFoundError:
        raise ManifestError("manifest assente: %s" % percorso)


# ---------------------------------------------------------------------------
# Sigillo (mittente): READY scritto per ULTIMO
# ---------------------------------------------------------------------------
def seal(root, sender: str, manifest_name: str = MANIFEST_NAME, ready_name: str = READY_NAME,
         exclude=(), force: bool = False, now=None) -> dict:
    """Sigilla il pacchetto: manifest, poi `READY` per ultimo (atomico). Ritorna il payload.

    `READY` contiene la chiave di consegna, il mittente, l'istante e il numero di file.
    Se `READY` esiste gia' solleva `HandoffError` (una consegna sigillata non si risigilla
    per sbaglio): `force=True` lo consente, consapevolmente.
    """
    root = Path(root)
    ready = root / ready_name
    if ready.exists() and not force:
        raise HandoffError("consegna gia' sigillata: %s (usa force=True per ri-sigillare)" % ready)
    voci = build_manifest(root, manifest_name, exclude)
    payload = {
        "protocollo": PROTOCOL,
        "key": chiave_consegna(root, manifest_name),
        "manifest": manifest_name,
        "sender": sender,
        "created_at": _now_iso(now),
        "files": len(voci),
    }
    atomic_write_text(ready, json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
    return payload


def read_ready(root, ready_name: str = READY_NAME) -> dict:
    """Legge il marker `READY`. `NotReadyError` se assente, `HandoffError` se illeggibile."""
    percorso = Path(root) / ready_name
    try:
        testo = percorso.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise NotReadyError("marker READY assente: %s" % percorso)
    try:
        return json.loads(testo)
    except ValueError as e:
        raise HandoffError("READY illeggibile: %s" % e)


def verify(root, manifest_name: str = MANIFEST_NAME, ready_name: str = READY_NAME,
           exclude=(), strict: bool = True) -> dict:
    """Verifica completa fail-closed: READY presente, manifest coerente, chiave allineata.

    Ritorna `{"ready": ..., "voci": ..., "key": ...}`. Qualunque incoerenza solleva.
    """
    ready = read_ready(root, ready_name)
    voci = verify_manifest(root, manifest_name, exclude, strict)
    attesa = chiave_consegna(root, manifest_name)
    if ready.get("key") != attesa:
        raise ManifestError("chiave di consegna non allineata: READY=%r manifest=%r"
                            % (ready.get("key"), attesa))
    if ready.get("manifest") != manifest_name:
        raise ManifestError("READY dichiara un manifest diverso: %r" % ready.get("manifest"))
    return {"ready": ready, "voci": voci, "key": attesa}


# ---------------------------------------------------------------------------
# Presa atomica (ricevente)
# ---------------------------------------------------------------------------
def _vincitori(root) -> list:
    return sorted(p.name[len(CLAIM_PREFIX):] for p in Path(root).glob(CLAIM_PREFIX + "*"))


@contextlib.contextmanager
def _claim_gate(root):
    """Serializza la presa dove il rename NON e' esclusivo (Windows).

    Su POSIX non fa nulla: `os.rename` e' atomico e il primo che lo esegue vince. Su Windows
    il filesystem lascia passare piu' rename dello stesso sorgente: un lock `O_EXCL` riduce la
    presa a un solo vincitore. Il lock e' tenuto per il tempo di un rename; se un processo
    muore mentre lo tiene, viene recuperato dopo 10 secondi (altrimenti bloccherebbe per sempre).
    """
    if os.name != "nt":
        yield
        return
    root = Path(root)
    lock = root / (READY_NAME + ".lock")
    for _ in range(1000):
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except OSError:
            # Su Windows un lock tenuto da un altro thread da' PermissionError, non
            # FileExistsError: qualunque OSError qui e' contesa, si aspetta e si riprova.
            try:
                eta = time.time() - lock.stat().st_mtime
            except FileNotFoundError:
                continue
            except OSError:
                eta = 0.0
            if eta > 10:                         # lock stantio (crash): si recupera
                try:
                    os.unlink(lock)
                except OSError:
                    pass
                continue
            time.sleep(0.002)
            continue
        try:
            os.close(fd)
            yield
        finally:
            try:
                os.unlink(lock)
            except OSError:
                pass
        return
    raise HandoffError("lock di presa non acquisito: %s" % lock)


def claim(root, claimer: str, ready_name: str = READY_NAME, now=None) -> dict:
    """Presa atomica della consegna: `rename(READY -> CLAIMED-<claimer>)`.

    Il rename e' il cancello: un solo ricevente lo esegue, gli altri trovano la sorgente
    gia' spostata e ricevono `AlreadyClaimedError`. Idempotente per nome: se `claimer` ha
    gia' preso (esiste `CLAIMED-<claimer>`), solleva `AlreadyClaimedError`.
    """
    if not _CLAIMER_RE.match(claimer or ""):
        raise HandoffError("nome claimer non valido: %r (ammessi [A-Za-z0-9._-], max 64)" % claimer)
    root = Path(root)
    ready = root / ready_name
    dest = root / (CLAIM_PREFIX + claimer)
    if dest.exists():
        raise AlreadyClaimedError("consegna gia' presa da %s" % claimer)
    if not ready.exists():
        vincitori = _vincitori(root)
        if vincitori:
            raise AlreadyClaimedError("consegna gia' presa da: %s" % ", ".join(vincitori))
        raise NotReadyError("marker READY assente: %s" % ready)
    try:
        payload = read_ready(root, ready_name)
    except NotReadyError:
        vincitori = _vincitori(root)
        if vincitori:
            raise AlreadyClaimedError("consegna gia' presa da: %s" % ", ".join(vincitori))
        raise
    with _claim_gate(root):
        # dentro il cancello: chi trova ancora READY lo sposta; per gli altri e' persa
        if not ready.exists() or dest.exists():
            vincitori = _vincitori(root)
            raise AlreadyClaimedError("consegna presa da un altro ricevente: %s" % ", ".join(vincitori))
        try:
            os.rename(ready, dest)          # atomico su POSIX: un solo vincitore
        except OSError as e:
            vincitori = _vincitori(root)
            if vincitori or not ready.exists():
                raise AlreadyClaimedError("consegna presa da un altro ricevente: %s" % ", ".join(vincitori))
            raise e
    _fsync_dir(root)
    return {"claimer": claimer, "claimed_at": _now_iso(now), "key": payload.get("key"),
            "path": str(dest)}


def stato(root, manifest_name: str = MANIFEST_NAME, ready_name: str = READY_NAME) -> dict:
    """Fotografia del pacchetto: READY, chiave, numero file, claimers, esito verifica."""
    root = Path(root)
    out = {"root": str(root), "presenti": sorted(p.name for p in root.iterdir()) if root.exists() else [],
           "ready": False, "key": None, "files": None, "claimed_by": _vincitori(root),
           "verifica": None}
    try:
        ready = read_ready(root, ready_name)
        out["ready"] = True
        out["key"] = ready.get("key")
        out["files"] = ready.get("files")
    except HandoffError as e:
        out["verifica"] = str(e)
        return out
    try:
        verify(root, manifest_name, ready_name)
        out["verifica"] = "OK"
    except HandoffError as e:
        out["verifica"] = str(e)
    return out


# ---------------------------------------------------------------------------
# Idempotenza (registro su filesystem)
# ---------------------------------------------------------------------------
class Ledger:
    """Registro di idempotenza: una chiave = hash del manifest.

    Stati per chiave (marker creati in O_EXCL, quindi atomici):
      - `<key>.done`     -> integrata: non si integra mai piu';
      - `<key>.inflight` -> presa in carico, esito non ancora registrato.
    Un crash lascia `inflight` (NON `done`): la consegna resta riprovabile, ma nessuno la
    integra in parallelo senza accorgersene.
    """

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _p(self, key: str, stato: str) -> Path:
        return self.root / ("%s.%s" % (key, stato))

    def is_done(self, key: str) -> bool:
        return self._p(key, "done").exists()

    def has_inflight(self, key: str) -> bool:
        return self._p(key, "inflight").exists()

    def _crea(self, percorso: Path, meta) -> bool:
        try:
            fd = os.open(str(percorso), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w") as f:
            f.write(json.dumps(meta or {}, sort_keys=True, ensure_ascii=False) + "\n")
            f.flush()
            os.fsync(f.fileno())
        _fsync_dir(self.root)
        return True

    def begin(self, key: str, meta=None) -> bool:
        """Marca `inflight`. True se preso ora da noi, False se gia' in corso.

        Se la chiave e' gia' `done`, solleva `HandoffError`: una consegna integrata non si
        riapre.
        """
        if self.is_done(key):
            raise HandoffError("chiave gia' integrata: %s" % key)
        return self._crea(self._p(key, "inflight"), meta)

    def commit(self, key: str, meta=None) -> None:
        """Registra `done` (O_EXCL) e libera `inflight`."""
        self._crea(self._p(key, "done"), meta)
        try:
            os.unlink(self._p(key, "inflight"))
        except FileNotFoundError:
            pass
        _fsync_dir(self.root)

    def abort(self, key: str) -> None:
        """Fallimento: libera `inflight`, la consegna torna riprovabile."""
        try:
            os.unlink(self._p(key, "inflight"))
        except FileNotFoundError:
            pass

    def done_keys(self) -> list:
        return sorted(p.name[: -len(".done")] for p in self.root.glob("*.done"))

    def stats(self) -> dict:
        return {"done": len(list(self.root.glob("*.done"))),
                "inflight": len(list(self.root.glob("*.inflight")))}


def integrate_once(root, ledger_root, claimer: str, integra, manifest_name: str = MANIFEST_NAME,
                   ready_name: str = READY_NAME, exclude=(), now=None) -> dict:
    """Integra una consegna AL PIU' UNA VOLTA. Ordine fail-closed.

    verifica (manifest + chiave) -> presa atomica -> idempotenza -> `integra(root)`.

    Ritorna `{"status": ...}`:
      - `"integrated"`: `integra` eseguita ORA da noi, `done` registrato;
      - `"duplicate"`:  chiave gia' `done`; `integra` NON richiamata;
      - `"in-flight"`:  un altro ricevente ha la chiave in corso; nessuna integrazione;
      - `"already-claimed"`: READY preso da un altro prima del nostro claim.
    Se `integra` solleva, `inflight` viene liberato e l'eccezione risale (riprovabile).
    """
    ledger = Ledger(ledger_root)
    # La chiave si legge dal MANIFEST: sopravvive al claim (READY no). Cosi' la stessa
    # consegna non si integra due volte nemmeno quando READY e' gia' stato preso.
    try:
        key = chiave_consegna(root, manifest_name)
    except ManifestError:
        key = None
    if key and ledger.is_done(key):
        return {"status": "duplicate", "key": key}
    try:
        esito = verify(root, manifest_name, ready_name, exclude)
    except NotReadyError as e:
        if _vincitori(root):
            return {"status": "already-claimed", "key": key, "motivo": str(e)}
        raise
    key = esito["key"]
    if ledger.is_done(key):
        return {"status": "duplicate", "key": key}
    try:
        presa = claim(root, claimer, ready_name, now)
    except AlreadyClaimedError as e:
        return {"status": "already-claimed", "key": key, "motivo": str(e)}
    if not ledger.begin(key, {"claimer": claimer, "root": str(root), "at": _now_iso(now)}):
        return {"status": "in-flight", "key": key}
    try:
        risultato = integra(root)
    except BaseException:
        ledger.abort(key)
        raise
    ledger.commit(key, {"claimer": claimer, "root": str(root), "at": _now_iso(now),
                        "claim_file": presa.get("path")})
    return {"status": "integrated", "key": key, "result": risultato, "claim": presa}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv=None) -> int:
    """CLI del protocollo: seal | verify | claim | key | status."""
    p = argparse.ArgumentParser(prog="handoff_atomico",
                                description="Protocollo di consegna atomico (fabbrica)")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("seal", help="crea MANIFEST.sha256 e READY (per ultimo)")
    s.add_argument("root")
    s.add_argument("--sender", required=True)
    s.add_argument("--exclude", action="append", default=[])
    s.add_argument("--force", action="store_true")

    v = sub.add_parser("verify", help="verifica READY + manifest (fail-closed)")
    v.add_argument("root")
    v.add_argument("--exclude", action="append", default=[])
    v.add_argument("--no-strict", action="store_true")

    c = sub.add_parser("claim", help="presa atomica READY -> CLAIMED-<claimer>")
    c.add_argument("root")
    c.add_argument("--claimer", required=True)

    k = sub.add_parser("key", help="stampa la chiave di consegna (hash del manifest)")
    k.add_argument("root")

    t = sub.add_parser("status", help="fotografia del pacchetto (JSON)")
    t.add_argument("root")

    a = p.parse_args(argv)
    try:
        if a.cmd == "seal":
            out = seal(a.root, a.sender, exclude=a.exclude, force=a.force)
        elif a.cmd == "verify":
            esito = verify(a.root, exclude=a.exclude, strict=not a.no_strict)
            out = {"verifica": "OK", "key": esito["key"], "files": len(esito["voci"])}
        elif a.cmd == "claim":
            out = claim(a.root, a.claimer)
        elif a.cmd == "key":
            out = {"key": chiave_consegna(a.root)}
        else:
            out = stato(a.root)
    except HandoffError as e:
        print("ERRORE: %s" % e, file=sys.stderr)
        return 2
    print(json.dumps(out, sort_keys=True, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
