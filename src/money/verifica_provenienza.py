"""
Modulo verificatore di provenienza - solo stdlib.
Calcola manifest SHA256 deterministico e verifica integrità file.

Task P9 del nastro Denaro: consegnato da Agent Zero (v2.13, 2026-09-30), integrato da
Hermes dopo review. Test: tests/test_verifica_provenienza.py.
"""
import hashlib
import os
from typing import Dict, List


def _calcola_sha256(filepath: str) -> str:
    """Calcola SHA256 di un file in chunk per gestire file grandi."""
    sha256 = hashlib.sha256()
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def _trova_file_ricorsivo(directory: str) -> List[str]:
    """Trova tutti i file ricorsivamente, restituisce path relativi ordinati."""
    file_list = []
    for root, dirs, files in os.walk(directory):
        # Ordina dirs per ricorsione deterministica
        dirs.sort()
        for file in sorted(files):
            full_path = os.path.join(root, file)
            rel_path = os.path.relpath(full_path, directory)
            # Normalizza separatori per cross-platform
            rel_path = rel_path.replace('\\', '/')
            file_list.append(rel_path)
    return sorted(file_list)


def _parse_manifest(manifest: str) -> Dict[str, str]:
    """Parsa manifest in dict {path: sha256}. Solleva ValueError se malformato."""
    result = {}
    if not manifest:
        return result
    for line_num, line in enumerate(manifest.splitlines(), 1):
        line = line.rstrip('\n\r')
        if not line:
            continue
        parts = line.split('  ', 1)
        if len(parts) != 2:
            raise ValueError(f"Manifest malformato alla riga {line_num}: '{line}'")
        sha256, path = parts
        if len(sha256) != 64:
            raise ValueError(f"SHA256 non valido alla riga {line_num}: '{sha256}'")
        # Valida che sia hex valido
        try:
            bytes.fromhex(sha256)
        except ValueError:
            raise ValueError(f"SHA256 non valido (non hex) alla riga {line_num}: '{sha256}'")
        result[path] = sha256
    return result


def crea_manifest(directory: str) -> str:
    """
    Crea manifest deterministico per una directory.
    
    Args:
        directory: Percorso directory da scansionare
    
    Returns:
        Stringa manifest: righe '<sha256>  <path_relativo>' ordinate per path,
        con newline finale. Stesso contenuto => stesso manifest byte-per-byte.
    """
    if not os.path.isdir(directory):
        raise ValueError(f"Non è una directory: {directory}")
    
    file_paths = _trova_file_ricorsivo(directory)
    
    if not file_paths:
        return ""  # Manifest vuoto per cartella vuota
    
    lines = []
    for rel_path in file_paths:
        full_path = os.path.join(directory, rel_path)
        sha256 = _calcola_sha256(full_path)
        lines.append(f"{sha256}  {rel_path}")
    
    # Unisci con newline e aggiungi newline finale
    return '\n'.join(lines) + '\n'


def verifica(directory: str, manifest: str) -> Dict:
    """
    Verifica una directory contro un manifest.
    
    Args:
        directory: Percorso directory da verificare
        manifest: Stringa manifest (output di crea_manifest)
    
    Returns:
        Dict con:
        - ok: bool complessivo
        - ok_count, modificati_count, mancanti_count, in_piu_count
        - ok_files, modificati_files, mancanti_files, in_piu_files
        - errore: stringa se manifest malformato
    """
    # Parsa manifest atteso
    try:
        expected = _parse_manifest(manifest)
    except ValueError as e:
        return {
            'ok': False,
            'ok_count': 0,
            'modificati_count': 0,
            'mancanti_count': 0,
            'in_piu_count': 0,
            'ok_files': [],
            'modificati_files': [],
            'mancanti_files': [],
            'in_piu_files': [],
            'errore': f"Manifest malformato: {e}"
        }
    
    # File attuali nella directory
    current_files = _trova_file_ricorsivo(directory)
    current_map = {}
    for rel_path in current_files:
        full_path = os.path.join(directory, rel_path)
        current_map[rel_path] = _calcola_sha256(full_path)
    
    ok_files = []
    modificati_files = []
    mancanti_files = []
    in_piu_files = []
    
    # Controlla file nel manifest
    for rel_path, expected_sha in expected.items():
        if rel_path not in current_map:
            mancanti_files.append(rel_path)
        elif current_map[rel_path] != expected_sha:
            modificati_files.append(rel_path)
        else:
            ok_files.append(rel_path)
    
    # File in più (presenti ora ma non nel manifest)
    for rel_path in current_map:
        if rel_path not in expected:
            in_piu_files.append(rel_path)
    
    ok = (len(modificati_files) == 0 and len(mancanti_files) == 0 and len(in_piu_files) == 0)
    
    return {
        'ok': ok,
        'ok_count': len(ok_files),
        'modificati_count': len(modificati_files),
        'mancanti_count': len(mancanti_files),
        'in_piu_count': len(in_piu_files),
        'ok_files': ok_files,
        'modificati_files': modificati_files,
        'mancanti_files': mancanti_files,
        'in_piu_files': in_piu_files,
        'errore': None
    }


def scrivi_manifest(path: str, manifest: str) -> None:
    """Scrive manifest su file."""
    with open(path, 'w', encoding='utf-8') as f:
        f.write(manifest)


def leggi_manifest(path: str) -> str:
    """Legge manifest da file."""
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()
