"""npm cache probe. Prefers asking npm itself; falls back to default paths."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from cachekat import keys
from cachekat.fsutil import dir_size_bytes
from cachekat.models import Finding, Risk
from cachekat.registry import register

RunFn = Callable[[str], str]  # cmd -> stdout (raises OSError when missing)

_NPM_TIMEOUT = 10  # seconds; `npm config get cache` should be near-instant


def npm_default_cache_dir() -> Path:
    """npm's documented defaults when we cannot ask npm itself."""
    if sys.platform == "win32":
        local = os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local"
        return Path(local) / "npm-cache"
    return Path.home() / ".npm"


def _subprocess_stdout(cmd: str) -> str:
    exe = shutil.which(cmd)  # resolves npm.cmd on Windows
    if exe is None:
        msg = f"{cmd} not on PATH"
        raise FileNotFoundError(msg)
    cp = subprocess.run(
        [exe, "config", "get", "cache"],
        capture_output=True, text=True,
        encoding="utf-8", errors="replace",  # npm paths may carry non-ASCII
        timeout=_NPM_TIMEOUT,
    )
    if cp.returncode != 0:
        msg = f"{cmd} exited {cp.returncode}"
        raise RuntimeError(msg)
    return cp.stdout


def resolve_cache_dir(runner: RunFn | None = None) -> Path:
    """npm config get cache (authoritative) -> default paths (fallback)."""
    run = runner or _subprocess_stdout
    try:
        out = run("npm").strip()
    except (OSError, RuntimeError, subprocess.SubprocessError):
        return npm_default_cache_dir()
    if out:
        return Path(out)
    return npm_default_cache_dir()


@register("npm")
def probe(cache_dir: Path | None = None) -> list[Finding]:
    """cache_dir param exists for tests (fake tree injection)."""
    d = cache_dir if cache_dir is not None else resolve_cache_dir()
    return [
        Finding(
            key=keys.NPM_CACHE,
            label="npm cache (_cacache/_npx/_logs)",
            size_bytes=dir_size_bytes(d),
            detail=str(d),
            risk=Risk.CLEANABLE,
            path=d,
        )
    ]
