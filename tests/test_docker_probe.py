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


IMAGES_SAMPLE = "\n".join(
    [
        # single-version image in normal use — must NOT be listed
        '{"Repository":"alpine","Tag":"3.19","ID":"c1aaabc123",'
        '"Size":"7.8MB","CreatedSince":"2 months ago"}',
        # retired versions of one repo: old + new pinned side by side
        '{"Repository":"ghcr.io/owner/app","Tag":"v1.2","ID":"aa11bb22cc3",'
        '"Size":"900MB","CreatedSince":"3 weeks ago"}',
        '{"Repository":"ghcr.io/owner/app","Tag":"v2.0","ID":"bb22cc33dd4",'
        '"Size":"1.2GB","CreatedSince":"4 days ago"}',
        # dangling layer: upgrade orphan
        '{"Repository":"<none>","Tag":"<none>","ID":"dd44ee55ff6",'
        '"Size":"850MB","CreatedSince":"3 weeks ago"}',
    ]
)


def _fake_docker(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    if cmd[1] == "ps":
        return _cp(PS_SAMPLE)
    if cmd[1] == "images":
        return _cp(IMAGES_SAMPLE)
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
    assert by_key["docker/build-cache"].risk is Risk.CLEANABLE
    assert by_key["docker/build-cache"].size_bytes == 1_500_000_000
    # per-image rows replaced the old blanket report-only aggregate
    assert "docker/images-reclaimable" not in by_key
    # dangling layer: cleanable AND preselected (deleting costs a re-pull)
    dangling = by_key["docker/image/dd44ee55ff6"]
    assert dangling.risk is Risk.CLEANABLE
    assert dangling.preselect is True
    assert dangling.size_bytes == 850_000_000
    # retired versions: cleanable, NOT preselected (user picks the live one)
    old = by_key["docker/image/aa11bb22cc3"]
    new = by_key["docker/image/bb22cc33dd4"]
    assert old.risk is Risk.CLEANABLE and old.preselect is False
    assert new.risk is Risk.CLEANABLE and new.preselect is False
    assert old.size_bytes == 900_000_000 and new.size_bytes == 1_200_000_000
    # single-version image in use: not our business, never listed
    assert not any(f.key == "docker/image/c1aaabc123" for f in findings)
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
    """Real incident, pinned: rc=0 + stdout=None (Windows reader
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
    """Long registry hosts were panel overruns (real user report); labels carry
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


def test_image_listing_failure_is_report_only():
    def flaky(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "images":
            return _cp("", rc=1)
        if cmd[1] == "ps":
            return _cp(PS_SAMPLE)
        return _cp(DF_SAMPLE)

    findings = probe(runner=flaky)
    by_key = {f.key: f for f in findings}
    assert "docker/images-error" in by_key
    assert by_key["docker/images-error"].risk is Risk.REPORT_ONLY


def test_multi_tag_one_image_is_one_finding():
    """Same image id under two tags is one row (docker prints one line per
    tag) — no double counting in the summary bar."""
    sample = "\n".join(
        [
            '{"Repository":"app","Tag":"v1","ID":"ff11ff11ff1",'
            '"Size":"10MB","CreatedSince":"1 day ago"}',
            '{"Repository":"app","Tag":"latest","ID":"ff11ff11ff1",'
            '"Size":"10MB","CreatedSince":"1 day ago"}',
            '{"Repository":"app","Tag":"v0","ID":"ee22ee22ee2",'
            '"Size":"9MB","CreatedSince":"1 year ago"}',
        ]
    )

    def run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        if cmd[1] == "images":
            return _cp(sample)
        if cmd[1] == "ps":
            return _cp("")
        return _cp(DF_SAMPLE)

    findings = probe(runner=run)
    image_rows = [f for f in findings if f.key.startswith("docker/image/")]
    assert sorted(f.key for f in image_rows) == [
        "docker/image/ee22ee22ee2",
        "docker/image/ff11ff11ff1",
    ]
