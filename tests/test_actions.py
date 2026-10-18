from __future__ import annotations

import subprocess
from pathlib import Path

from cachekat.actions import clean
from cachekat.models import Finding, Risk


def _cp(rc: int = 0, out: str = "", err: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=out, stderr=err)


def _fake_cache(tmp_path: Path, size: int = 100) -> Path:
    d = tmp_path / "victim"
    d.mkdir()
    (d / "x").write_bytes(b"x" * size)
    return d


# --- the refusal path is the feature ---------------------------------------


def test_report_only_refused_even_in_dry_run(tmp_path: Path):
    f = Finding("docker/volumes", "volumes", 10, "d", Risk.REPORT_ONLY, tmp_path)
    for dry in (False, True):
        r = clean(f, dry_run=dry)
        assert not r.ok
        assert "refused" in r.detail


def test_dry_run_never_touches_disk(tmp_path: Path):
    d = _fake_cache(tmp_path)
    f = Finding("npm/cache", "npm", 100, str(d), Risk.CLEANABLE, d)
    r = clean(f, dry_run=True)
    assert r.ok and "[dry-run]" in r.detail
    assert d.exists() and (d / "x").exists()  # untouched


# --- rmtree family -----------------------------------------------------------


def test_npm_rmtree_removes_dir(tmp_path: Path):
    d = _fake_cache(tmp_path)
    f = Finding("npm/cache", "npm", 100, str(d), Risk.CLEANABLE, d)
    r = clean(f)
    assert r.ok and not d.exists()


def test_playwright_orphan_rmtree(tmp_path: Path):
    d = _fake_cache(tmp_path, size=7)
    f = Finding("playwright/chromium-1234", "orphan", 7, str(d), Risk.CLEANABLE, d)
    assert clean(f).ok and not d.exists()


def test_rmtree_without_path_fails_honestly(tmp_path: Path):
    f = Finding("npm/cache", "npm", 1, "somewhere", Risk.CLEANABLE, None)
    r = clean(f)
    assert not r.ok and "no path" in r.detail


# --- CLI family (runner injection) -------------------------------------------


def test_pip_purge_uses_current_interpreter():
    import sys

    seen: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return _cp(out="Files removed")

    f = Finding("pip/cache", "pip", 50, "p", Risk.CLEANABLE)
    r = clean(f, runner=fake_runner)
    assert r.ok
    assert seen[0] == [sys.executable, "-m", "pip", "cache", "purge"]


def test_docker_build_cache_runs_builder_prune():
    seen: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return _cp()

    f = Finding("docker/build-cache", "bc", 5, "d", Risk.CLEANABLE)
    assert clean(f, runner=fake_runner).ok
    assert seen == [["docker", "builder", "prune", "-f"]]


def test_docker_container_rm_per_name():
    # no -f on purpose: a container started after the scan refuses naturally
    seen: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return _cp(out="test-bench")

    f = Finding("docker/container/test-bench", "c", 5, "d", Risk.CLEANABLE)
    assert clean(f, runner=fake_runner).ok
    assert seen == [["docker", "rm", "test-bench"]]


def test_retired_image_key_runs_rmi_without_force():
    """Per-image selection exists now (0.5.0): the action is rmi WITHOUT
    -f, so an image still referenced by any container refuses naturally."""
    seen: list[list[str]] = []

    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return _cp()

    f = Finding("docker/image/dd44ee55ff6", "img", 5, "d", Risk.CLEANABLE)
    assert clean(f, runner=fake_runner).ok
    assert seen == [["docker", "rmi", "dd44ee55ff6"]]


def test_old_image_aggregate_key_is_dead():
    """The pre-0.5.0 report-only aggregate key must fail loudly, not
    silently pretend — it was replaced by per-image findings."""
    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        raise AssertionError("no docker command may run for a dead key")

    f = Finding("docker/images-reclaimable", "img", 5, "d", Risk.CLEANABLE)
    r = clean(f, runner=fake_runner)
    assert not r.ok
    assert "no clean action" in r.detail


def test_consequence_wording_covers_all_cleanable_families():
    from cachekat.actions import consequence

    pip_f = Finding("pip/cache", "p", 1, "d", Risk.CLEANABLE)
    assert "re-download" in consequence(pip_f)
    pw_f = Finding("playwright/chromium-1234", "pw", 1, "d", Risk.CLEANABLE)
    assert "playwright install" in consequence(pw_f)
    bc_f = Finding("docker/build-cache", "bc", 1, "d", Risk.CLEANABLE)
    assert "ORPHANED" in consequence(bc_f)
    ct_f = Finding("docker/container/test-bench", "c", 1, "d", Risk.CLEANABLE)
    # hard requirement from the real incident: the warning must say
    # container-itself, not cache
    assert "CONTAINER ITSELF" in consequence(ct_f)
    img_f = Finding("docker/image/dd44ee55ff6", "img", 1, "d", Risk.CLEANABLE)
    # the image warning must say: refuses when referenced, re-pullable
    assert "no -f used" in consequence(img_f)
    assert "docker pull" in consequence(img_f)


def test_cmd_failure_surfaces_stderr():
    def bad_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return _cp(rc=1, err="boom: daemon down")

    f = Finding("docker/build-cache", "bc", 5, "d", Risk.CLEANABLE)
    r = clean(f, runner=bad_runner)
    assert not r.ok and "boom: daemon down" in r.detail


def test_docker_dry_run_skips_runner():
    called = []

    def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        called.append(cmd)
        return _cp()

    f = Finding("docker/build-cache", "bc", 5, "d", Risk.CLEANABLE)
    r = clean(f, dry_run=True, runner=runner)
    assert r.ok and not called


# --- unknown key --------------------------------------------------------------


def test_unknown_cleanable_key_fails_loudly():
    f = Finding("future/thing", "t", 1, "d", Risk.CLEANABLE)
    r = clean(f)
    assert not r.ok and "no clean action" in r.detail


# --- vhdx maintenance action (MAINTENANCE grade, step 1) ------------------------

import sys  # noqa: E402


def _vhdx_finding(vhdx: Path) -> Finding:
    return Finding(
        "wsl/vhdx/docker_data", "docker disk", vhdx.stat().st_size,
        str(vhdx), Risk.MAINTENANCE, path=vhdx,
    )


def _win(monkeypatch) -> None:
    # sys.platform, never os.name (patching os.name poisons pathlib)
    monkeypatch.setattr(sys, "platform", "win32")


def test_vhdx_refused_when_docker_desktop_running(tmp_path: Path, monkeypatch):
    _win(monkeypatch)
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        assert cmd[0] == "tasklist"
        return _cp(out="Docker Desktop\tcom.docker.backend\t100\tConsole")

    r = clean(_vhdx_finding(vhdx), runner=run, script_dir=tmp_path)
    assert not r.ok
    assert "is running" in r.detail  # refuses; never kills processes


def test_vhdx_refused_when_tasklist_fails(tmp_path: Path, monkeypatch):
    """Cannot even list processes -> assume maybe-running and refuse —
    guessing 'stopped' is how data gets hurt."""
    _win(monkeypatch)
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)
    r = clean(_vhdx_finding(vhdx), runner=lambda cmd: _cp(rc=1), script_dir=tmp_path)
    assert not r.ok


def test_vhdx_dry_run_touches_nothing(tmp_path: Path, monkeypatch):
    _win(monkeypatch)
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)
    called: list[list[str]] = []

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        called.append(cmd)
        return _cp()

    r = clean(_vhdx_finding(vhdx), dry_run=True, runner=run, script_dir=tmp_path)
    assert r.ok
    assert called == [["tasklist"]]  # wsl --shutdown NOT run in dry-run
    assert list(tmp_path.iterdir()) == [vhdx]  # no script written


def test_vhdx_shutdown_failure_surfaces_stderr(tmp_path: Path, monkeypatch):
    _win(monkeypatch)
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[0] == "tasklist":
            return _cp()
        return _cp(rc=1, err="boom: wsl locked")

    r = clean(_vhdx_finding(vhdx), runner=run, script_dir=tmp_path)
    assert not r.ok
    assert "boom: wsl locked" in r.detail


def test_vhdx_writes_self_elevating_diskpart_script(tmp_path: Path, monkeypatch):
    _win(monkeypatch)
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)
    scripts = tmp_path / "out"
    scripts.mkdir()

    monkeypatch.setattr("cachekat.actions.optimize_vhd_available", lambda run=None: False)

    r = clean(_vhdx_finding(vhdx), runner=lambda cmd: _cp(), script_dir=scripts)
    assert r.ok
    script = scripts / "cachekat-compact-docker-vhdx.ps1"
    assert script.is_file()
    body = script.read_text(encoding="utf-8-sig")
    # BOM present: PowerShell 5.1 reads BOM-less files as ANSI codepage
    assert script.read_bytes()[:3] == b"\xef\xbb\xbf"
    # self-elevation: the script asks for admin itself (UAC = user consent)
    assert "-Verb RunAs" in body
    # diskpart fallback body, the four canonical steps
    assert "compact vdisk" in body and "detach vdisk" in body
    assert str(vhdx) in body
    assert "Nothing is deleted" in body  # the honest promise, in the script
    assert str(script) in r.detail  # result tells the user where it is
    _assert_powershell_hygiene(body)


def _assert_powershell_hygiene(body: str) -> None:
    """Pins the flash-close incident (0.6.2): a PowerShell read-only
    AUTOMATIC variable ($args) was assigned before the UAC relaunch,
    killing the script silently — window flashed closed, no prompt.
    Plus the 0.6.3 encoding fix: ASCII-only body (Windows PowerShell 5.1
    decodes BOM-less files as the ANSI codepage, where an em dash can
    scramble parsing). Linux CI cannot run PowerShell semantics, so we
    pin the known minefield statically."""
    for banned in ("$args", "$input", "$error", "$host", "$matches"):
        assert f"{banned} =" not in body, f"assigning automatic {banned} is a crash"
    assert body.isascii(), "script body must be ASCII-only for codepage safety"
    # a failure must stay ON SCREEN — never flash-close without a cause
    assert "FAILED:" in body
    assert "catch" in body and "finally" in body


def test_vhdx_optimize_body_when_cmdlet_available(tmp_path: Path, monkeypatch):
    _win(monkeypatch)
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)
    scripts = tmp_path / "out"
    scripts.mkdir()

    monkeypatch.setattr("cachekat.actions.optimize_vhd_available", lambda run=None: True)

    r = clean(_vhdx_finding(vhdx), runner=lambda cmd: _cp(), script_dir=scripts)
    assert r.ok
    body = (scripts / "cachekat-compact-docker-vhdx.ps1").read_text(encoding="utf-8")
    assert "Optimize-VHD -Path $vhdx -Mode Full" in body
    assert "diskpart" not in body


def test_vhdx_refused_off_windows(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    vhdx = tmp_path / "docker_data.vhdx"
    vhdx.write_bytes(b"x" * 10)
    r = clean(_vhdx_finding(vhdx), runner=lambda cmd: _cp(), script_dir=tmp_path)
    assert not r.ok and "Windows-only" in r.detail


def test_vhdx_consequence_carries_the_special_warnings():
    from cachekat.actions import consequence

    f = Finding("wsl/vhdx/docker_data", "docker disk", 10, "d", Risk.MAINTENANCE)
    text = consequence(f)
    assert "deletes NOTHING" in text  # data safety
    assert "WSL" in text and "stops" in text  # full-stop warning
    assert "admin" in text  # privilege warning
    assert "minutes" in text  # duration warning
    assert text.count("\n") >= 4  # structured one-per-line, not a wall
