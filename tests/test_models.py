from __future__ import annotations

import pytest

from cachekat.models import Finding, Risk


def test_risk_values_are_frozen_contract():
    # wire format for JSON/tests; changing these is a breaking change
    assert Risk.CLEANABLE.value == "cleanable"
    assert Risk.REPORT_ONLY.value == "report-only"
    assert len(Risk) == 2


def test_finding_is_immutable():
    f = Finding(key="x/y", label="x", size_bytes=1, detail="d", risk=Risk.CLEANABLE)
    with pytest.raises(Exception):  # noqa: B017 — dataclass FrozenInstanceError
        f.size_bytes = 2  # type: ignore[misc]
