from __future__ import annotations

import subprocess

from cachekat.models import Risk
from cachekat.probes.docker_df import parse_size, probe


def _cp(stdout: str = "", rc: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=rc, stdout=stdout, stderr="")


DF_SAMPLE = "\n".join(
    [
        '{"Type":"Images","TotalCount":17,"Active":5,"Size":"4.2GB","Reclaimable":"2.1GB (50%)"}',
        '{"Type":"Containers","TotalCount":6,"Active":3,"Size":"800MB","Reclaimable":"300MB"}',
        '{"Type":"Local Volumes","TotalCount":4,"Active":3,"Size":"89MB","Reclaimable":"12MB"}',
        '{"Type":"Build Cache","TotalCount":90,"Active":0,'
        '"Size":"1.5GB","Reclaimable":"1.5GB (100%)"}',
    ]
)

PS_SAMPLE = "\n".join(
    [
        '{"Names":"test-bench","Image":"bench-sandbox:1","State":"exited",'
        '"Status":"Exited (0) 2 weeks ago","Size":"191.1MB (virtual 1.2GB)"}',
        '{"Names":"web-app","Image":"webapp:latest","State":"running",'
        '"Status":"Up 3 hours","Size":"50MB (virtual 900MB)"}',
        '{"Names":"one-shot","Image":"alpine","State":"created",'
        '"Status":"Created","Size":"0B (virtual 12MB)"}',
    ]
)


def _fake_docker(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    if cmd[1] == "ps":
        return _cp(PS_SAMPLE)
    return _cp(DF_SAMPLE)


def test_parse_size_variants():
    assert parse_size("516.2MB (55%)") == 516_200_000
    assert parse_size("4.2GB") == 4_200_000_000
    assert parse_size("89MB") == 89_000_000
    assert parse_size("0B") == 0
    assert parse_size("") == 0
    assert parse_size("12B") == 12


def test_probe_happy_path_risk_graded():
    findings = probe(runner=_fake_docker)
    by_key = {f.key: f for f in findings}
    # aggregates
    assert by_key["docker/volumes"].risk is Risk.REPORT_ONLY
    assert "never cleans volumes" in by_key["docker/volumes"].detail
    assert by_key["docker/images-reclaimable"].risk is Risk.REPORT_ONLY
    assert "per-image selection" in by_key["docker/images-reclaimable"].detail
    assert by_key["docker/build-cache"].risk is Risk.CLEANABLE
    assert by_key["docker/build-cache"].size_bytes == 1_500_000_000
    # per-container: individually selectable, each with the loud warning
    bench = by_key["docker/container/test-bench"]
    assert bench.risk is Risk.CLEANABLE
    assert bench.size_bytes == 191_100_000  # local layer, virtual ignored
    assert "CONTAINER ITSELF" in bench.detail and "Volumes are NOT touched" in bench.detail
    assert "Exited (0) 2 weeks ago" in bench.detail
    assert by_key["docker/container/one-shot"].risk is Risk.CLEANABLE
    # running container never offered; aggregate containers row gone
    assert not any(k.startswith("docker/container/web") for k in by_key)
    assert "docker/stopped-containers" not in by_key


def test_probe_ps_failure_keeps_df_findings():
    def flaky(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "ps":
            return _cp("", rc=1)
        return _cp(DF_SAMPLE)

    findings = probe(runner=flaky)
    keys = [f.key for f in findings]
    assert "docker/build-cache" in keys
    assert "docker/ps-error" in keys


def test_probe_docker_not_installed():
    def no_docker(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        msg = "docker not on PATH"
        raise FileNotFoundError(msg)

    assert probe(runner=no_docker) == []


def test_probe_daemon_down_is_report_only():
    findings = probe(runner=lambda cmd: _cp("", rc=1))
    assert len(findings) == 1
    assert findings[0].key == "docker/daemon"
    assert findings[0].risk is Risk.REPORT_ONLY


def test_probe_liar_stdout_none_raises_loud():
    """2026-10-09 incident, pinned: rc=0 + stdout=None (Windows reader
    thread swallowed a GBK decode crash) must fail LOUDLY, not as a cryptic
    'NoneType has no attribute splitlines' downstream."""
    import pytest

    from cachekat.probes.docker_df import _stdout_or_raise

    liar = _cp(stdout=None, rc=0)  # type: ignore[arg-type]
    with pytest.raises(RuntimeError, match="docker ps.*stdout is None"):
        _stdout_or_raise(liar, "docker ps")


def test_run_declares_utf8_explicitly(monkeypatch):
    """Contract: docker speaks UTF-8; the default locale codec (cp936 on
    zh-Windows) must never be used to decode docker output."""
    from cachekat.probes import docker_df

    seen: dict = {}

    def fake_run(cmd, **kwargs):
        seen.update(kwargs)
        return _cp("{}")

    monkeypatch.setattr(docker_df.subprocess, "run", fake_run)
    docker_df._run(["docker", "system", "df"])
    assert seen.get("encoding") == "utf-8"
    assert seen.get("errors") == "replace"


def test_container_label_drops_registry_host():
    """Long registry hosts were panel overruns (2026-10-09); labels carry
    repo:tag only."""
    ps = (
        '{"Names":"worldtreeapp-n8n-1","Image":'
        '"docker.n8n.io/n8nio/n8n:latest","State":"exited",'
        '"Status":"Exited (0) 2 weeks ago","Size":"191.1MB (virtual 1.2GB)"}'
    )

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        return _cp(ps) if cmd[1] == "ps" else _cp(
            '{"Type":"Build Cache","TotalCount":1,"Size":"1B","Reclaimable":"1B"}'
        )

    findings = probe(runner=run)
    label = next(f.label for f in findings if f.key.startswith("docker/container/"))
    assert "n8n:latest" in label
    assert "docker.n8n.io" not in label
