"""Shared acquisition checks; do not confuse a nonempty file with valid electrochemistry."""
from pathlib import Path

def saved_ok(path, sanity_check=True):
    if not sanity_check:
        return True
    p = Path(path)
    return p.is_file() and p.stat().st_size > 0

def require_keys(params, required):
    missing = set(required) - set(params)
    if missing:
        raise ValueError(f"Missing technique parameter(s): {sorted(missing)}")
