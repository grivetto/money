"""Vault utilities with atomic writes to prevent JSON corruption"""
import os, json, tempfile

def atomic_write(path, data):
    """Write JSON data atomically: write to tmp file, then rename"""
    dirpath = os.path.dirname(path) or '.'
    tmp = tempfile.NamedTemporaryFile(mode='w', dir=dirpath, prefix='.tmp_', suffix='.json', delete=False)
    try:
        json.dump(data, tmp, indent=2)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp.close()
        os.replace(tmp.name, path)
    except:
        os.unlink(tmp.name, exist_ok=True)
        raise

def atomic_read(path, default=None):
    """Read JSON safely, return default if corrupted"""
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default if default is not None else {}
