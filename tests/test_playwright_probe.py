from __future__ import annotations

from pathlib import Path

from cachekat.models import Risk
from cachekat.probes.playwright_cache import needed_revisions, probe


def _fake_root(tmp_path: Path) -> Path:
    root = tmp_path / "ms-playwright"
    for name, size in (("chromium-1148", 100), ("firefox-9999", 50)):
        d = root / name
        d.mkdir(parents=True)
        (d / "binary").write_bytes(b"x" * size)
    return root


def test_orphans_split_from_in_use(tmp_path: Path):
    root = _fake_root(tmp_path)
    findings = probe(browsers_root=root, needed={"chromium-1148"})
    by_key = {f.key: f for f in findings}
    assert by_key["playwright/chromium-1148"].risk is Risk.REPORT_ONLY
    assert by_key["playwright/firefox-9999"].risk is Risk.CLEANABLE
    assert "orphan" in by_key["playwright/firefox-9999"].label


def test_liveness_unknown_is_honest_report_only(tmp_path: Path):
    root = _fake_root(tmp_path)
    findings = probe(browsers_root=root, needed=None)
    assert len(findings) == 1
    f = findings[0]
    assert f.risk is Risk.REPORT_ONLY
    assert f.size_bytes == 150
    assert "liveness unknown" in f.label


def test_missing_dir_returns_nothing(tmp_path: Path):
    assert probe(browsers_root=tmp_path / "nope", needed=None) == []


def test_needed_revisions_from_fake_browsers_json(tmp_path: Path):
    bj = tmp_path / "browsers.json"
    bj.write_text(
        '{"browsers": [{"name": "chromium", "revision": "1148"},'
        ' {"name": "ffmpeg", "revision": "1005"}]}',
        encoding="utf-8",
    )
    assert needed_revisions(browsers_json=bj) == {"chromium-1148", "ffmpeg-1005"}


def test_needed_revisions_unreadable_json(tmp_path: Path):
    bj = tmp_path / "browsers.json"
    bj.write_text("{not json", encoding="utf-8")
    assert needed_revisions(browsers_json=bj) is None
    assert needed_revisions(browsers_json=tmp_path / "missing.json") is None
