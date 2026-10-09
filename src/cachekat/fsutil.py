"""Filesystem helpers shared by probes (single implementation, no copies)."""

from __future__ import annotations

import os
from pathlib import Path


def dir_size_bytes(path: Path) -> int:
    """Recursive on-disk size. Missing path -> 0.

    Files that vanish or are locked mid-walk are skipped, so the result is a
    LOWER BOUND. Known limitation, not hidden: for cache directories this
    undershoot is tiny and harmless; revisit if a probe ever needs exactness.
    """
    if not path.exists():
        return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue  # raced-away or locked file (see docstring)
    return total
