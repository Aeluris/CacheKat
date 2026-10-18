from __future__ import annotations

import json
from pathlib import Path

import pytest

from cachekat.cli import format_table, human_size, main, to_json
from cachekat.models import Finding, Risk
from cachekat.registry import register


def test_version_flag_reports_package_version(capsys: pytest.CaptureFixture[str]):
    """`cachekat --version` must agree with the package version — version
    info lives in exactly one place (`cachekat.__version__`)."""
    from cachekat import __version__

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out


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


# --- cachekat vhdx ----------------------------------------------------------


def test_vhdx_report_optimize_path(tmp_path: Path):
    from cachekat.cli import vhdx_report

    vhdx = tmp_path / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
    vhdx.parent.mkdir(parents=True)
    vhdx.write_bytes(b"x" * 2048)

    report = vhdx_report(str(tmp_path), optimize_available=True)
    assert str(vhdx) in report
    assert "wsl --shutdown" in report  # step 1: the full-stop warning
    assert 'Optimize-VHD -Path "' in report
    assert "diskpart" not in report


def test_vhdx_report_diskpart_fallback(tmp_path: Path):
    """No Hyper-V management tools -> diskpart script, never a crash."""
    from cachekat.cli import vhdx_report

    vhdx = tmp_path / "Docker" / "data" / "ext4.vhdx"
    vhdx.parent.mkdir(parents=True)
    vhdx.write_bytes(b"x" * 512)

    report = vhdx_report(str(tmp_path), optimize_available=False)
    assert f'select vdisk file="{vhdx}"' in report
    assert "compact vdisk" in report
    assert "detach vdisk" in report
    # the fallback NOTICE names Optimize-VHD (it explains why); the
    # COMMAND must not appear — diskpart is the only path offered
    assert "Optimize-VHD -Path" not in report


def test_vhdx_report_missing_disk_is_honest(tmp_path: Path):
    from cachekat.cli import vhdx_report

    report = vhdx_report(str(tmp_path), optimize_available=True)
    assert "no Docker Desktop vhdx found" in report


def test_vhdx_cli_off_windows_says_so(capsys: pytest.CaptureFixture[str], monkeypatch):
    # sys.platform, not os.name — patching os.name poisons pathlib
    monkeypatch.setattr("sys.platform", "linux")
    rc = main(["vhdx", "--lang", "en"])
    assert rc == 0
    assert "Windows-only" in capsys.readouterr().out
