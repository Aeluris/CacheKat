from __future__ import annotations

from pathlib import Path

from cachekat.models import Risk
from cachekat.probes.npm_cache import probe, resolve_cache_dir


def test_probe_measures_fake_npm_cache(tmp_path: Path):
    d = tmp_path / "npm"
    (d / "_cacache").mkdir(parents=True)
    (d / "_cacache" / "content-v2").mkdir()
    (d / "_cacache" / "content-v2" / "f").write_bytes(b"x" * 300)
    (d / "_logs").mkdir()
    (d / "_logs" / "log").write_bytes(b"y" * 10)

    findings = probe(cache_dir=d)
    f = findings[0]
    assert f.key == "npm/cache"
    assert f.size_bytes == 310
    assert f.risk is Risk.CLEANABLE


def test_probe_missing_dir_is_zero(tmp_path: Path):
    f = probe(cache_dir=tmp_path / "nope")[0]
    assert f.size_bytes == 0


def test_resolve_prefers_npm_cli_answer():
    def fake_runner(cmd: str) -> str:
        assert cmd == "npm"
        return "  /custom/npm-cache\n"

    assert resolve_cache_dir(runner=fake_runner) == Path("/custom/npm-cache")


def test_resolve_falls_back_when_npm_missing(monkeypatch):
    def boom(cmd: str) -> str:
        msg = "npm not on PATH"
        raise FileNotFoundError(msg)

    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("LOCALAPPDATA", "/fake-local")
    assert resolve_cache_dir(runner=boom) == Path("/fake-local") / "npm-cache"
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setenv("HOME", "/home/fakeuser")
    # Path.home() on Windows resolves USERPROFILE, not HOME — set both so the
    # test is honest on every platform (CI 2026-10-08 windows cells were red)
    monkeypatch.setenv("USERPROFILE", "/home/fakeuser")
    assert resolve_cache_dir(runner=boom) == Path("/home/fakeuser") / ".npm"
