from __future__ import annotations

import json
from pathlib import Path

import pytest

from cachekat import keys
from cachekat.i18n import set_lang
from cachekat.models import Risk
from cachekat.probes import wsl_vhdx


@pytest.fixture(autouse=True)
def _english():
    # i18n is process-wide (set once per entry); earlier zh-locale tests
    # would otherwise leak into this module's en assertions
    set_lang("en")
    return None


def test_off_windows_reports_nothing(monkeypatch):
    """Linux/macOS: no Docker Desktop vhdx concept — absence is not an
    error, so no findings AND no error finding. (Patching _on_windows,
    never os.name: patching os.name poisons pathlib's Path dispatch.)"""
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: False)
    assert wsl_vhdx.probe(localappdata="C:\\Users\\x\\AppData\\Local") == []


def test_finds_new_layout_vhdx(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    vhdx = tmp_path / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
    vhdx.parent.mkdir(parents=True)
    vhdx.write_bytes(b"x" * 1024)

    findings = wsl_vhdx.probe(localappdata=str(tmp_path))
    assert len(findings) == 1
    f = findings[0]
    assert f.key == keys.WSL_VHDX_DOCKER_DATA
    # MAINTENANCE grade: data-loss-free compact belongs in the SELECTABLE
    # panel with special confirm warnings — not in report-only anymore
    assert f.risk is Risk.MAINTENANCE
    assert f.size_bytes == 1024
    assert f.path == vhdx
    assert str(vhdx) in f.detail
    assert "nothing deleted" in f.detail  # the honest promise leads
    assert f.preselect is False  # heavy ops are never pre-checked


def test_finds_legacy_layout_vhdx(tmp_path: Path, monkeypatch):
    """Both layouts exist in the wild — a real incident had us probing the
    legacy path on a new install (and vice versa). Probe BOTH."""
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    vhdx = tmp_path / "Docker" / "data" / "ext4.vhdx"
    vhdx.parent.mkdir(parents=True)
    vhdx.write_bytes(b"x" * 512)

    findings = wsl_vhdx.probe(localappdata=str(tmp_path))
    assert len(findings) == 1
    assert findings[0].key == keys.WSL_VHDX_EXT4


def test_no_localappdata_reports_nothing(monkeypatch):
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    assert wsl_vhdx.probe(localappdata=None) == []


def test_vhdx_missing_means_no_findings_not_error(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    (tmp_path / "Docker").mkdir()
    assert wsl_vhdx.probe(localappdata=str(tmp_path), appdata=str(tmp_path)) == []


# --- custom Disk image location (Docker Desktop "move") ---------------------


def _settings(appdata: Path, name: str, payload: str) -> None:
    docker = appdata / "Docker"
    docker.mkdir(parents=True, exist_ok=True)
    (docker / name).write_text(payload, encoding="utf-8")


def test_custom_location_vhdx_found_and_default_leftover_skipped(
    tmp_path: Path, monkeypatch
):
    """After a Docker Desktop move, the live vhdx sits under the custom
    folder and the default-location leftover must NOT be reported (it
    would only mislead: compacting a dead copy is wasted minutes)."""
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    appdata, local = tmp_path / "roaming", tmp_path / "local"
    moved = tmp_path / "DockerDisk" / "wsl" / "disk" / "docker_data.vhdx"
    moved.parent.mkdir(parents=True)
    moved.write_bytes(b"x" * 2048)
    leftover = local / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
    leftover.parent.mkdir(parents=True)
    leftover.write_bytes(b"x" * 4096)
    # the real settings file points at an absolute path that only exists
    # on the user's machine; here we patch the location (its key-reading
    # is covered by the dedicated tests below) and check the precedence
    monkeypatch.setattr(wsl_vhdx, "_custom_disk_location", lambda a: str(tmp_path / "DockerDisk"))

    findings = wsl_vhdx.probe(localappdata=str(local), appdata=str(appdata))
    assert len(findings) == 1
    assert findings[0].path == moved
    assert findings[0].key == keys.WSL_VHDX_DOCKER_DATA


def test_custom_location_without_vhdx_falls_back_to_default(
    tmp_path: Path, monkeypatch
):
    """Settings point at a custom folder, but no vhdx there (move not
    done / failed): default layout still reports. A custom hint is a
    lead, not an authority."""
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    appdata, local = tmp_path / "roaming", tmp_path / "local"
    default = local / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
    default.parent.mkdir(parents=True)
    default.write_bytes(b"x" * 512)
    _settings(appdata, "settings.json", '{"dataFolder": "C:/gone"}')
    monkeypatch.setattr(wsl_vhdx, "_custom_disk_location", lambda a: str(tmp_path / "gone"))

    findings = wsl_vhdx.probe(localappdata=str(local), appdata=str(appdata))
    assert len(findings) == 1
    assert findings[0].path == default


def test_corrupt_settings_file_degrades_to_default_layout(
    tmp_path: Path, monkeypatch
):
    """A broken settings file must never break the probe — it degrades
    to the default layouts silently (settings are a hint, not a gate)."""
    monkeypatch.setattr(wsl_vhdx, "_on_windows", lambda: True)
    appdata, local = tmp_path / "roaming", tmp_path / "local"
    default = local / "Docker" / "wsl" / "disk" / "docker_data.vhdx"
    default.parent.mkdir(parents=True)
    default.write_bytes(b"x" * 512)
    _settings(appdata, "settings-store.json", "{ not json at all")

    findings = wsl_vhdx.probe(localappdata=str(local), appdata=str(appdata))
    assert len(findings) == 1
    assert findings[0].path == default


def test_settings_key_names_are_tolerated(tmp_path: Path):
    """Both settings files, several key spellings — the writer changed
    its mind across Docker Desktop versions; the reader must not."""
    seen: list[str | None] = []
    for name in ("settings-store.json", "settings.json"):
        for key in ("dataFolder", "DataFolder", "diskImageLocation", "DiskImageLocation"):
            appdata = tmp_path / f"{name}-{key}"
            _settings(appdata, name, json.dumps({key: "C:/x"}))
            seen.append(wsl_vhdx._custom_disk_location(str(appdata)))
    assert seen == ["C:/x"] * 8


def test_settings_absent_or_empty_folder_means_no_custom(tmp_path: Path):
    assert wsl_vhdx._custom_disk_location(str(tmp_path)) is None
    appdata = tmp_path / "empty"
    (appdata / "Docker").mkdir(parents=True)
    # file exists but the key is absent
    _settings(appdata, "settings-store.json", '{"other": 1}')
    assert wsl_vhdx._custom_disk_location(str(appdata)) is None
    # value is the empty string — nothing moved, treat as no custom
    _settings(appdata, "settings.json", '{"dataFolder": ""}')
    assert wsl_vhdx._custom_disk_location(str(appdata)) is None
