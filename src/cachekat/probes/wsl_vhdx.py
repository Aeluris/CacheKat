"""Docker Desktop WSL2 disk (ext4.vhdx) probe — MAINTENANCE grade, Windows-only.

The vhdx IS the docker store. Deleting junk inside docker never shrinks
it; only compacting returns the space (the suitcase metaphor: it keeps
its size until you squeeze it). Compacting deletes NOTHING — it is a
data-loss-free but heavy maintenance op: admin rights, every WSL distro
stopped, minutes of runtime. That is the MAINTENANCE risk grade: it sits
in the selectable (left) panel like a cache, but its confirm gate
carries the special warnings, and the action generates a self-elevating
script rather than deleting anything.

Path facts (probe, guess NEITHER):
- default, Docker Desktop ~4.30+: %LOCALAPPDATA%\\Docker\\wsl\\disk\\docker_data.vhdx
- default, legacy:                  %LOCALAPPDATA%\\Docker\\data\\ext4.vhdx
- custom "Disk image location":     Docker Desktop writes the folder to
  its settings file (%APPDATA%\\Docker\\settings-store.json, or the older
  settings.json) and moves the vhdx there. The in-settings key and the
  on-disk sub-layout under the custom folder are NOT documented as a
  stable contract, so we read several key spellings and probe several
  sub-layouts — whatever exists wins. A custom hit takes precedence: it
  is the live disk; a leftover vhdx at the default location (a failed or
  partial move) would only mislead.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from cachekat import keys
from cachekat.i18n import t
from cachekat.models import Finding, Risk
from cachekat.registry import register

_VHDX_CANDIDATES = (
    (keys.WSL_VHDX_DOCKER_DATA, ("Docker", "wsl", "disk", "docker_data.vhdx")),
    (keys.WSL_VHDX_EXT4, ("Docker", "data", "ext4.vhdx")),
)

# settings files: settings-store.json is the newer format, settings.json
# the older one; both have carried the disk location under spellings we
# accept below. A broken/unreadable settings file is NOT an error here:
# it is a hint, so we degrade silently to the default layouts.
_SETTINGS_FILES = ("settings-store.json", "settings.json")
_DATA_FOLDER_KEYS = ("dataFolder", "DataFolder", "diskImageLocation", "DiskImageLocation")

# sub-layouts probed under a custom disk location. The exact layout is
# undocumented, so every plausible one is tried; only an existing file
# wins. (name, key) pairs must map back to the keys actions route on.
_CUSTOM_SUB_LAYOUTS = (
    ("wsl", "disk", "docker_data.vhdx", keys.WSL_VHDX_DOCKER_DATA),
    ("disk", "docker_data.vhdx", keys.WSL_VHDX_DOCKER_DATA),
    ("docker_data.vhdx", keys.WSL_VHDX_DOCKER_DATA),
    ("data", "ext4.vhdx", keys.WSL_VHDX_EXT4),
    ("ext4.vhdx", keys.WSL_VHDX_EXT4),
)


def _custom_disk_location(appdata: str | None) -> str | None:
    """Read the "Disk image location" out of Docker Desktop settings.

    Returns the folder, or None when there is no settings file, no key,
    or the file is not valid JSON (settings is a hint, not authority)."""
    if not appdata:
        return None
    docker_dir = Path(appdata) / "Docker"
    for name in _SETTINGS_FILES:
        settings = docker_dir / name
        if not settings.is_file():
            continue
        try:
            data = json.loads(settings.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        for key in _DATA_FOLDER_KEYS:
            value = data.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def candidate_paths(
    localappdata: str | None, appdata: str | None = None
) -> list[tuple[str, Path]]:
    """Key + path pairs, custom location FIRST then defaults; empty
    off-Windows/no-profile. Custom-first is what makes a moved disk win
    over a leftover default copy."""
    if not localappdata:
        return []
    out: list[tuple[str, Path]] = []
    custom = _custom_disk_location(appdata if appdata is not None else os.environ.get("APPDATA"))
    if custom:
        base = Path(custom)
        for *parts, name, key in _CUSTOM_SUB_LAYOUTS:
            out.append((key, base.joinpath(*parts, name)))
    base = Path(localappdata)
    out += [(key, base.joinpath(*parts)) for key, parts in _VHDX_CANDIDATES]
    return out


def find_vhdx(localappdata: str | None, appdata: str | None = None) -> list[tuple[str, Path]]:
    """Existing vhdx files with move-aware precedence: a hit under the
    custom disk location wins and default-layout leftovers are skipped
    (they would only mislead after a move). No custom hit → both default
    layouts report as before."""
    hits = [
        (key, path)
        for key, path in candidate_paths(localappdata, appdata)
        if path.is_file()
    ]
    custom = _custom_disk_location(appdata)
    if custom:
        base = Path(custom)
        custom_hits = [(key, p) for key, p in hits if base in p.parents]
        if custom_hits:
            return custom_hits
    return hits


def _localappdata() -> str | None:
    return os.environ.get("LOCALAPPDATA")


def _on_windows() -> bool:
    # split out so tests can fake the platform WITHOUT faking os.name
    # (patching os.name poisons pathlib: Path() dispatches on it)
    return sys.platform == "win32"


@register("wsl_vhdx")
def probe(localappdata: str | None = None, appdata: str | None = None) -> list[Finding]:
    """localappdata/appdata overrides exist for tests (no real vhdx needed)."""
    local = localappdata if localappdata is not None else _localappdata()
    app = appdata if appdata is not None else os.environ.get("APPDATA")
    if not _on_windows() or not local:
        # off-Windows there is no Docker Desktop vhdx concept — nothing
        # to report, and no error either (absence is not a failure)
        return []
    findings: list[Finding] = []
    for key, path in find_vhdx(local, app):
        findings.append(
            Finding(
                key=key,
                label=t("wsl_vhdx_label"),
                size_bytes=path.stat().st_size,
                detail=t("wsl_vhdx_detail", path=str(path)),
                risk=Risk.MAINTENANCE,
                path=path,
            )
        )
    return findings
