from __future__ import annotations

from pathlib import Path

from cachekat.models import Risk
from cachekat.probes.pip_cache import probe


def test_probe_measures_fake_cache_tree(tmp_path: Path):
    cache = tmp_path / "pip" / "cache"
    (cache / "wheels" / "ab").mkdir(parents=True)
    (cache / "wheels" / "ab" / "pkg.whl").write_bytes(b"x" * 1000)
    (cache / "http-v2").mkdir()
    (cache / "http-v2" / "chunk").write_bytes(b"y" * 50)

    findings = probe(cache_dir=cache)
    assert len(findings) == 1
    f = findings[0]
    assert f.key == "pip/cache"
    assert f.size_bytes == 1050
    assert f.risk is Risk.CLEANABLE
    assert str(cache) in f.detail


def test_probe_missing_dir_reports_zero_not_error(tmp_path: Path):
    findings = probe(cache_dir=tmp_path / "nope")
    assert findings[0].size_bytes == 0
    assert findings[0].risk is Risk.CLEANABLE
