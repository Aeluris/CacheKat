"""Clean actions, one per finding key. The refusal path is the feature.

Rules:
- REPORT_ONLY findings are refused, always — even in dry-run, even by
  internal callers. There is no flag that unlocks this.
- dry_run=True must not touch disk or run any CLI, period.
- Unknown cleanable keys fail loudly ("no clean action implemented") —
  pretending to clean is worse than admitting we can't.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Protocol

from cachekat import keys
from cachekat.i18n import t
from cachekat.models import Finding, Risk

_TIMEOUT = 600  # docker prunes can be slow on big machines


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
# 2026-10-08 incident: image prune -a / container prune are indiscriminate
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
# these BEFORE anything runs (2026-10-08 lesson: item names alone don't warn).
# Wording lives in cachekat.i18n (en source of truth, zh table).
_CONSEQUENCE_KEYS = {
    keys.PIP_CACHE: "cons_pip",
    keys.NPM_CACHE: "cons_npm",
    keys.DOCKER_BUILD_CACHE: "cons_build_cache",
}


def consequence(finding: Finding) -> str:
    """One plain sentence about what cleaning this finding does."""
    if finding.key.startswith(keys.DOCKER_CONTAINER_PREFIX):
        return t("cons_container")
    if finding.key in _CONSEQUENCE_KEYS:
        return t(_CONSEQUENCE_KEYS[finding.key])
    if finding.key.startswith(keys.PLAYWRIGHT_PREFIX):
        return t("cons_playwright")
    return t("cons_none")


def clean(
    finding: Finding, *, dry_run: bool = False, runner: _Runner | None = None
) -> ActionResult:
    run = runner if runner is not None else _run
    if finding.risk is not Risk.CLEANABLE:
        return ActionResult(finding.key, False, "refused: report-only is never cleaned")
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
    if finding.key in _DOCKER_ACTIONS:
        cmd, desc = _DOCKER_ACTIONS[finding.key]
        return _cmd_action(finding, dry_run, run, cmd, desc)
    return ActionResult(finding.key, False, "no clean action implemented for this finding")
