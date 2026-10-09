"""Core data shapes — explicit types at every boundary, no magic strings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, unique
from pathlib import Path


@unique
class Risk(str, Enum):
    """What a finding is allowed to become.

    CLEANABLE: cache/junk — deleting it only costs a later re-download.
    REPORT_ONLY: valuable or risky (data volumes, vhdx) — show, never clean.
    """

    CLEANABLE = "cleanable"
    REPORT_ONLY = "report-only"


@dataclass(frozen=True)
class Finding:
    """One scan result. Immutable; the report layer renders, probes fill.

    path: the on-disk location this finding measures, when there is one
    (docker rows are CLI-level facts, not paths). Actions consume it —
    parsing paths back out of `detail` (display text) is forbidden.
    """

    key: str  # stable id from cachekat.keys — the wire contract
    label: str  # human name, e.g. "pip download cache"
    size_bytes: int  # 0 when unknown/absent — never negative
    detail: str  # path or explanation shown to the user
    risk: Risk
    path: Path | None = None
    # registry sets this when a probe CRASHED (finding = the crash report):
    # explicit flag at the boundary, no key-string sniffing downstream
    is_error: bool = False
