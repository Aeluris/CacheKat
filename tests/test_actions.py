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


def test_docker_images_still_refused():
    def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        raise AssertionError("image prune must never run (per-image selection pending)")

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
