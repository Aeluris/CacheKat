"""Probe registry — the ONE place probes register. Interface convergence."""

from __future__ import annotations

import os
import traceback
from collections.abc import Callable, Iterable
from typing import TypeVar

from cachekat.i18n import t
from cachekat.models import Finding, Risk

ProbeFn = Callable[..., list[Finding]]
T = TypeVar("T", bound=ProbeFn)

_REGISTRY: dict[str, ProbeFn] = {}


def register(probe_id: str) -> Callable[[T], T]:
    """Decorator: register a probe under a stable id. Duplicate ids are a bug."""

    def deco(fn: T) -> T:
        if probe_id in _REGISTRY:
            msg = f"probe id {probe_id!r} already registered"
            raise ValueError(msg)
        _REGISTRY[probe_id] = fn
        return fn

    return deco


def all_probes() -> Iterable[tuple[str, ProbeFn]]:
    return sorted(_REGISTRY.items())


def _crash_detail(exc: Exception) -> str:
    """One-line crash report: exception type, raise site, message.

    Real-world case: a probe crashed on a Windows machine and the
    TUI's narrow table column truncated the detail to "AttributeErro" —
    invisible WHERE. The raise site (file:line in func) makes the next
    screenshot self-sufficient."""
    tb = exc.__traceback__
    last = traceback.extract_tb(tb)[-1] if tb else None
    where = (
        f" @{os.path.basename(last.filename)}:{last.lineno} in {last.name}"
        if last
        else ""
    )
    return f"{type(exc).__name__}{where}: {exc}"


def run_scan() -> list[Finding]:
    """Run every probe. A crashing probe becomes a visible error finding —
    failures are surfaced, never swallowed (anti-fake-work clause)."""
    findings: list[Finding] = []
    for probe_id, fn in all_probes():
        try:
            findings.extend(fn())
        except Exception as exc:  # noqa: BLE001 — deliberate: report, don't die
            findings.append(
                Finding(
                    key=f"{probe_id}/error",
                    label=t("probe_failed_label", probe=probe_id),
                    size_bytes=0,
                    detail=_crash_detail(exc),
                    risk=Risk.REPORT_ONLY,
                    is_error=True,
                )
            )
    return findings
