"""pip download cache probe (M0 reference probe)."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from cachekat import keys
from cachekat.fsutil import dir_size_bytes
from cachekat.models import Finding, Risk
from cachekat.registry import register


def pip_cache_dir() -> Path:
    """Platform cache dir per pip docs (https://pip.pypa.io/en/stable/topics/caching/)."""
    home = Path.home()
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or home / "AppData" / "Local"
        return Path(local) / "pip" / "cache"
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "pip"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg) / "pip" if xdg else home / ".cache" / "pip"


@register("pip")
def probe(cache_dir: Path | None = None) -> list[Finding]:
    """cache_dir param exists for tests (fake tree injection)."""
    d = cache_dir if cache_dir is not None else pip_cache_dir()
    return [
        Finding(
            key=keys.PIP_CACHE,
            label="pip download cache",
            size_bytes=dir_size_bytes(d),
            detail=str(d),
            risk=Risk.CLEANABLE,
            path=d,
        )
    ]
