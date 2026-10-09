from __future__ import annotations

import json
from pathlib import Path

import pytest

from cachekat.cli import format_table, human_size, main, to_json
from cachekat.models import Finding, Risk
from cachekat.registry import register


def test_scan_json_is_parseable(capsys: pytest.CaptureFixture[str]):
    rc = main(["scan", "--json"])
    out = capsys.readouterr().out
    assert rc == 0
    rows = json.loads(out)
    assert any(r["key"] == "pip/cache" for r in rows)
    assert all(r["risk"] in ("cleanable", "report-only") for r in rows)


def test_scan_table_renders(capsys: pytest.CaptureFixture[str]):
    rc = main(["scan"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "pip download cache" in out
    assert "read-only" in out


def test_run_scan_surfaces_probe_crash_as_finding():
    # fixture-style cleanup: a bare register() here would leak into other
    # tests (registry pollution inflates later counts)
    from cachekat import registry

    @register("boomtest")
    def boom() -> list[Finding]:
        msg = "exploded"
        raise RuntimeError(msg)

    try:
        findings = registry.run_scan()
    finally:
        registry._REGISTRY.pop("boomtest", None)

    err = [f for f in findings if f.key == "boomtest/error"]
    assert err and "exploded" in err[0].detail
    assert err[0].risk is Risk.REPORT_ONLY
    # crash detail must be self-sufficient: exception type + raise site
    # (a real case: a Windows AttributeError was truncated to "AttributeErro"
    # by the TUI column — where it happened stayed invisible)
    assert "RuntimeError" in err[0].detail
    assert "@test_cli.py:" in err[0].detail
    assert "in boom" in err[0].detail
    assert err[0].is_error is True


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(1536) == "1.5 KiB"
    assert human_size(2 * 1024**3) == "2.0 GiB"


def test_table_marks_report_only(tmp_path: Path):
    f = Finding(key="v/ol", label="volumes", size_bytes=5, detail="d", risk=Risk.REPORT_ONLY)
    assert "!" in format_table([f])
    assert '"report-only"' in to_json([f])
