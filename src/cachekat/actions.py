"""Clean/maintenance actions, one per finding key. The refusal path is the feature.

Rules:
- REPORT_ONLY findings are refused, always — even in dry-run, even by
  internal callers. There is no flag that unlocks this.
- MAINTENANCE findings never delete anything: the vhdx compact action
  stops WSL, then WRITES a self-elevating script and tells the user to
  run it. The tool itself never runs the admin part.
- dry_run=True must not touch disk or run any CLI, period.
- Unknown cleanable keys fail loudly ("no clean action implemented") —
  pretending to clean is worse than admitting we can't.
"""

from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from cachekat import keys
from cachekat.i18n import t
from cachekat.models import Finding, Risk

_TIMEOUT = 600  # docker prunes can be slow on big machines
_PS_TIMEOUT = 30  # capability probe; must never hang the TUI

# Docker Desktop processes that keep the WSL VM alive. If ANY of these is
# running, `wsl --shutdown` is pointless — Docker relaunches its distro
# within seconds. We refuse and ask the user to quit Docker Desktop from
# the tray; killing Docker's processes ourselves is NOT our call.
_DOCKER_PROCESSES = (
    "Docker Desktop",
    "com.docker.backend",
    "com.docker.build",
    "com.docker.dev-envs",
)


def optimize_vhd_available(run: _Runner | None = None) -> bool:
    """Optimize-VHD needs the Hyper-V management tools (an optional Windows
    feature). Asking PowerShell is more honest than assuming — an absent
    cmdlet is why compact scripts fall back to diskpart, not a broken
    install. Also consumed by the `cachekat vhdx` CLI report."""
    if sys.platform != "win32":
        return False
    if run is None:
        run = _run_ps
    try:
        cp = run(["powershell", "-NoProfile", "-Command", "Get-Command Optimize-VHD"])
    except (OSError, subprocess.TimeoutExpired):
        return False
    return cp.returncode == 0


def _run_ps(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=_PS_TIMEOUT,
    )


@dataclass(frozen=True)
class ActionResult:
    key: str
    ok: bool
    detail: str


class _Runner(Protocol):
    def __call__(self, cmd: list[str]) -> subprocess.CompletedProcess[str]: ...


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    # explicit UTF-8: same zh-Windows reader-thread hazard as probes (a
    # swallowed decode crash surfaces as stdout=None, see docker_df._run)
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=_TIMEOUT,
    )


def _cmd_action(
    finding: Finding, dry_run: bool, run: _Runner, cmd: list[str], desc: str
) -> ActionResult:
    if dry_run:
        return ActionResult(finding.key, True, f"[dry-run] would {desc}")
    cp = run(cmd)
    if cp.returncode == 0:
        tail = (cp.stdout or "").strip().splitlines()
        return ActionResult(finding.key, True, f"{desc}: {tail[-1]}" if tail else desc)
    err = (cp.stderr or cp.stdout or "").strip().splitlines()
    return ActionResult(
        finding.key, False, f"{desc} failed (exit {cp.returncode}): {err[-1] if err else ''}"
    )


def _rmtree_action(finding: Finding, dry_run: bool) -> ActionResult:
    if finding.path is None:
        return ActionResult(finding.key, False, "no path on finding — cannot remove")
    desc = f"delete {finding.path}"
    if dry_run:
        return ActionResult(finding.key, True, f"[dry-run] would {desc}")
    shutil.rmtree(finding.path)
    return ActionResult(finding.key, True, desc)


# docker prunes: -f skips their interactive prompt; our TUI is the prompt.
# A real incident: image prune -a / container prune are indiscriminate
# ("unused"/"stopped" != unwanted — a user's persistent test bench was
# pruned). Both docker rows are REPORT_ONLY now; only build cache (true
# cache semantics) remains cleanable here.
_DOCKER_ACTIONS = {
    keys.DOCKER_BUILD_CACHE: (
        ["docker", "builder", "prune", "-f"],
        "docker builder prune -f",
    ),
}

# what each clean actually does, in plain words — the confirm modal shows
# these BEFORE anything runs (hard lesson: item names alone don't warn).
# Wording lives in cachekat.i18n (en source of truth, zh table).
_CONSEQUENCE_KEYS = {
    keys.PIP_CACHE: "cons_pip",
    keys.NPM_CACHE: "cons_npm",
    keys.DOCKER_BUILD_CACHE: "cons_build_cache",
}


def consequence(finding: Finding) -> str:
    """One plain sentence about what cleaning this finding does."""
    if finding.key.startswith(keys.WSL_VHDX_PREFIX):
        return t("cons_vhdx_maintenance")
    if finding.key.startswith(keys.DOCKER_IMAGE_PREFIX):
        return t("cons_image")
    if finding.key.startswith(keys.DOCKER_CONTAINER_PREFIX):
        return t("cons_container")
    if finding.key in _CONSEQUENCE_KEYS:
        return t(_CONSEQUENCE_KEYS[finding.key])
    if finding.key.startswith(keys.PLAYWRIGHT_PREFIX):
        return t("cons_playwright")
    return t("cons_none")


# --- vhdx maintenance (MAINTENANCE grade — step 1: stop WSL, write script) ---


def _docker_desktop_running(run: _Runner) -> bool:
    cp = run(["tasklist"])
    if cp.returncode != 0:
        # cannot even list processes -> treat as "maybe running": refuse,
        # never guess "stopped" (guessing is how data gets hurt)
        return True
    listing = (cp.stdout or "").lower()
    return any(name.lower() in listing for name in _DOCKER_PROCESSES)


_COMPACT_SCRIPT = """\
# CacheKat - Docker Desktop WSL2 disk compact (generated {date})
# Target: {vhdx}
# Nothing is deleted; this only returns free space inside the vhdx to Windows.
# The script asks for admin itself (UAC prompt = your consent).
#
# ASCII-only on purpose: Windows PowerShell 5.1 reads a BOM-less file as
# ANSI (system codepage), where a stray em dash can scramble parsing.
# (We also emit a BOM via utf-8-sig, belt and suspenders.)

$ErrorActionPreference = "Stop"
$principal = New-Object Security.Principal.WindowsPrincipal(
    [Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {{
    # relaunch self elevated. NOTE: the arg variable MUST NOT be $args -
    # that is a read-only automatic variable; assigning it kills the
    # script before the UAC ever shows (a real user-reported flash-close)
    $relaunchArgs = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    Start-Process powershell -Verb RunAs -ArgumentList $relaunchArgs
    exit
}}

$vhdx = "{vhdx}"
try {{
    Write-Host "compacting $vhdx (minutes on big disks - do not interrupt)"
{body}

    $size = (Get-Item $vhdx).Length
    Write-Host ""
    Write-Host "done. vhdx now: $([math]::Round($size / 1GB, 1)) GiB"
    Write-Host "Docker Desktop starts normally on next launch."
}} catch {{
    # a failed compact must not flash-close: the error stays on screen
    # so the user can see WHAT failed (nothing gets damaged - the
    # operation simply stopped at the failure point)
    Write-Host ""
    Write-Host "FAILED: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "nothing was damaged - the compact stopped at the failure point"
}} finally {{
    Read-Host "press Enter to close"
}}
"""

_OPTIMIZE_BODY = 'Optimize-VHD -Path $vhdx -Mode Full'
_DISKPART_BODY = """\
$dp = "select vdisk file=`"$vhdx`"`nattach vdisk readonly`ncompact vdisk`ndetach vdisk"
$dp | diskpart"""


def _vhdx_maintenance_action(
    finding: Finding, dry_run: bool, run: _Runner, script_dir: Path | None = None
) -> ActionResult:
    """Step 1 of the two-step plan (user-approved 2026-10-16): the TOOL
    stops WSL and writes a self-elevating script; the USER runs the admin
    part. The tool never executes the compact itself."""
    if sys.platform != "win32":
        return ActionResult(finding.key, False, "refused: vhdx compact is Windows-only")
    if finding.path is None or not finding.path.is_file():
        return ActionResult(finding.key, False, "vhdx not found — rescan (r)")
    if _docker_desktop_running(run):
        return ActionResult(finding.key, False, t("vhdx_act_docker_running"))
    if dry_run:
        return ActionResult(
            finding.key, True, t("vhdx_act_dry", script=_script_name(finding))
        )
    cp = run(["wsl", "--shutdown"])
    if cp.returncode != 0:
        err = (cp.stderr or cp.stdout or "").strip().splitlines()
        return ActionResult(
            finding.key, False, f"wsl --shutdown failed (exit {cp.returncode}): "
            f"{err[-1] if err else ''}"
        )
    target_dir = script_dir if script_dir is not None else finding.path.parent
    script = _write_compact_script(finding.path, target_dir)
    return ActionResult(finding.key, True, t("vhdx_act_done", script=str(script)))


def _script_name(finding: Finding) -> str:
    return _compact_script_path(finding.path, finding.path.parent).name


def _compact_script_path(vhdx: Path, target_dir: Path) -> Path:
    return target_dir / "cachekat-compact-docker-vhdx.ps1"


def _write_compact_script(vhdx: Path, target_dir: Path) -> Path:
    body = _OPTIMIZE_BODY if optimize_vhd_available() else _DISKPART_BODY
    script = _compact_script_path(vhdx, target_dir)
    # utf-8-sig = BOM: Windows PowerShell 5.1 needs it to read the file as
    # UTF-8 at all; BOM-less files are decoded as the ANSI system codepage
    script.write_text(
        _COMPACT_SCRIPT.format(
            date=datetime.date.today().isoformat(), vhdx=str(vhdx), body=body
        ),
        encoding="utf-8-sig",
    )
    return script


def clean(
    finding: Finding, *, dry_run: bool = False, runner: _Runner | None = None,
    script_dir: Path | None = None,
) -> ActionResult:
    run = runner if runner is not None else _run
    if finding.risk is Risk.REPORT_ONLY:
        return ActionResult(finding.key, False, "refused: report-only is never cleaned")
    if finding.risk is Risk.MAINTENANCE:
        if finding.key.startswith(keys.WSL_VHDX_PREFIX):
            return _vhdx_maintenance_action(finding, dry_run, run, script_dir)
        return ActionResult(
            finding.key, False, "no maintenance action implemented for this finding"
        )
    if finding.key == keys.PIP_CACHE:
        cmd = [sys.executable, "-m", "pip", "cache", "purge"]
        return _cmd_action(finding, dry_run, run, cmd, "pip cache purge")
    if finding.key == keys.NPM_CACHE:
        return _rmtree_action(finding, dry_run)
    if finding.key.startswith(keys.PLAYWRIGHT_PREFIX):
        return _rmtree_action(finding, dry_run)
    if finding.key.startswith(keys.DOCKER_CONTAINER_PREFIX):
        # name derivation by documented prefix-strip (see cachekat/keys.py):
        # docker names never contain "/", display text is never parsed
        name = finding.key.removeprefix(keys.DOCKER_CONTAINER_PREFIX)
        # no -f: a container that started since the scan refuses naturally,
        # and docker rm never touches volumes
        return _cmd_action(finding, dry_run, run, ["docker", "rm", name], f"docker rm {name}")
    if finding.key.startswith(keys.DOCKER_IMAGE_PREFIX):
        # id derivation by the same documented prefix-strip contract:
        # docker short ids are hex, no "/", display text is never parsed.
        # no -f: an image still referenced by ANY container (running or
        # stopped) refuses removal naturally; rmi never touches volumes
        image_id = finding.key.removeprefix(keys.DOCKER_IMAGE_PREFIX)
        return _cmd_action(
            finding, dry_run, run, ["docker", "rmi", image_id], f"docker rmi {image_id}"
        )
    if finding.key in _DOCKER_ACTIONS:
        cmd, desc = _DOCKER_ACTIONS[finding.key]
        return _cmd_action(finding, dry_run, run, cmd, desc)
    return ActionResult(finding.key, False, "no clean action implemented for this finding")
