"""Playwright browser cache probe — orphan-version aware.

Liveness comes from the installed playwright package's browsers.json
(driver/package/browsers.json). When playwright is not importable in this
interpreter we CANNOT tell orphans from in-use browsers — the finding is
REPORT_ONLY with that stated, instead of a guess.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

from cachekat import keys
from cachekat.fsutil import dir_size_bytes
from cachekat.i18n import t
from cachekat.models import Finding, Risk
from cachekat.registry import register


def browsers_dir() -> Path:
    """Playwright's download roots per platform (PLAYWRIGHT_BROWSERS_PATH wins)."""
    env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if env:
        return Path(env)
    home = Path.home()
    if sys.platform == "win32":
        return home / "AppData" / "Local" / "ms-playwright"
    if sys.platform == "darwin":
        return home / "Library" / "Caches" / "ms-playwright"
    xdg = os.environ.get("XDG_CACHE_HOME")
    return Path(xdg) / "ms-playwright" if xdg else home / ".cache" / "ms-playwright"


def needed_revisions(browsers_json: Path | None = None) -> set[str] | None:
    """Revisions the installed playwright wants, e.g. {"chromium-1148"}.

    None = playwright not importable (or browsers.json unreadable) — caller
    must treat liveness as unknown.
    """
    bj = browsers_json
    if bj is None:
        spec = importlib.util.find_spec("playwright")
        if spec is None or not spec.submodule_search_locations:
            return None
        pkg = Path(next(iter(spec.submodule_search_locations)))
        bj = pkg / "driver" / "package" / "browsers.json"
    if not bj.exists():
        return None
    try:
        data = json.loads(bj.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    revs = {
        f"{b.get('name')}-{b.get('revision')}"
        for b in data.get("browsers", [])
        if b.get("name") and b.get("revision")
    }
    return revs or None


@register("playwright")
def probe(browsers_root: Path | None = None, needed: set[str] | None = ...) -> list[Finding]:
    """Both params exist for tests (fake tree + fake revision set).

    `needed=...` (default) means: derive from the installed playwright.
    Pass an explicit set (possibly None) to pin behaviour in tests.
    """
    d = browsers_root if browsers_root is not None else browsers_dir()
    if not d.exists():
        return []
    revs = needed_revisions() if needed is ... else needed
    # hidden entries (".links" = playwright's driver registry) are infra, not
    # browsers — never counted, never cleaned
    entries = sorted(p for p in d.iterdir() if p.is_dir() and not p.name.startswith("."))
    if revs is None:
        total = sum(dir_size_bytes(e) for e in entries)
        return [
            Finding(
                key=keys.PLAYWRIGHT_BROWSERS,
                label=t("pw_unknown_label"),
                size_bytes=total,
                detail=t("pw_unknown_detail", path=d),
                risk=Risk.REPORT_ONLY,
                path=d,
            )
        ]
    findings: list[Finding] = []
    for e in entries:
        in_use = e.name in revs
        findings.append(
            Finding(
                key=f"{keys.PLAYWRIGHT_PREFIX}{e.name}",
                label=t("pw_orphan_label" if not in_use else "pw_inuse_label", name=e.name),
                size_bytes=dir_size_bytes(e),
                detail=str(e) + ("" if in_use else f" — {t('pw_orphan_detail')}"),
                risk=Risk.REPORT_ONLY if in_use else Risk.CLEANABLE,
                path=e,
            )
        )
    return findings
