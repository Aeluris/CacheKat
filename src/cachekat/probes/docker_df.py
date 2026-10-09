"""Docker disk usage probe — `docker system df --format json`, risk-graded.

Red line: Local Volumes are data, REPORT_ONLY forever. Sizes come from
docker's own numbers (reclaimable for cleanable rows).
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from cachekat import keys
from cachekat.i18n import t
from cachekat.models import Finding, Risk
from cachekat.registry import register

RunFn = Callable[[list[str]], subprocess.CompletedProcess[str]]

_DF_TIMEOUT = 30  # seconds; system df on a big machine can take a while
_DF_CMD = ["docker", "system", "df", "--format", "{{json .}}"]


@dataclass(frozen=True)
class _Row:
    type: str
    size_bytes: int
    reclaimable_bytes: int
    count: int


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    # encoding is EXPLICIT: docker speaks UTF-8 on every platform. With the
    # default locale codec (cp936 on zh-Windows) a non-ASCII byte sequence
    # crashes the hidden Windows reader thread inside communicate() — the
    # exception is swallowed by the thread and we get stdout=None, rc=0
    # (2026-10-09 real-machine incident, see tests/test_docker_probe.py).
    return subprocess.run(
        cmd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=_DF_TIMEOUT,
    )


def parse_size(text: str) -> int:
    """'516.2MB (55%)' -> 516_200_000 (docker uses decimal SI units)."""
    s = text.split("(")[0].strip().replace(" ", "")
    if not s or s == "0B":
        return 0
    # longest-first is load-bearing: "516.2MB" also ends with "B"
    units = {"TB": 10**12, "GB": 10**9, "MB": 10**6, "KB": 10**3, "B": 1}
    for suffix, mult in units.items():
        if s.endswith(suffix):
            num = s[: -len(suffix)]
            try:
                value = float(num) if "." in num else int(num)
            except ValueError:
                return 0
            return int(value * mult)
    return 0


def _parse_rows(stdout: str) -> list[_Row]:
    rows: list[_Row] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        d = json.loads(line)  # malformed line = probe error, surfaces upstream
        rows.append(
            _Row(
                type=str(d.get("Type", "")),
                size_bytes=parse_size(str(d.get("Size", ""))),
                reclaimable_bytes=parse_size(str(d.get("Reclaimable", ""))),
                count=int(d.get("TotalCount", 0) or 0),
            )
        )
    return rows


def _findings_from_rows(rows: list[_Row]) -> list[Finding]:
    """Aggregate rows: volumes/images/build-cache. Containers are NOT here —
    they are per-container findings from `docker ps` (user selects each one;
    deleting a container is removing the thing itself, not a cache)."""
    findings: list[Finding] = []
    for r in rows:
        if r.type == "Local Volumes":
            findings.append(
                Finding(
                    key=keys.DOCKER_VOLUMES,
                    label=t("dock_volumes_label"),
                    size_bytes=r.size_bytes,
                    detail=t("dock_volumes_detail", n=r.count),
                    risk=Risk.REPORT_ONLY,
                )
            )
        elif r.type == "Images":
            findings.append(
                Finding(
                    key=keys.DOCKER_IMAGES,
                    label=t("dock_images_label"),
                    size_bytes=r.reclaimable_bytes,
                    detail=t("dock_images_detail"),
                    risk=Risk.REPORT_ONLY,
                )
            )
        elif r.type == "Build Cache":
            findings.append(
                Finding(
                    key=keys.DOCKER_BUILD_CACHE,
                    label=t("dock_build_label"),
                    size_bytes=r.reclaimable_bytes,
                    detail=t("dock_build_detail"),
                    risk=Risk.CLEANABLE,
                )
            )
    return findings


# per-container: stopped states only — running/paused/restarting never listed
_STOPPED_STATES = {"exited", "created", "dead"}
_PS_CMD = ["docker", "ps", "-a", "-s", "--format", "{{json .}}"]


def _short_image(image: str) -> str:
    """'docker.n8n.io/n8nio/n8n:latest' -> 'n8n:latest' — registry hosts
    are noise in a list row (2026-10-09 user report: rows overran the
    panel). The TUI ellipsizes too, but labels shouldn't START at hopeless."""
    return image.rsplit("/", 1)[-1]


def _container_findings(run: RunFn) -> list[Finding]:
    """One finding per stopped container, each CLEANABLE but individually
    chosen. The warning is load-bearing: docker rm removes the CONTAINER
    ITSELF, not a cache (2026-10-08 incident, explicit design decision)."""
    try:
        cp = run(_PS_CMD)
    except subprocess.TimeoutExpired:
        return [
            Finding(
                key=keys.DOCKER_PS_ERROR,
                label=t("dock_ps_timeout_label"),
                size_bytes=0,
                detail=t("dock_ps_timeout"),
                risk=Risk.REPORT_ONLY,
            )
        ]
    if cp.returncode != 0:
        return [
            Finding(
                key=keys.DOCKER_PS_ERROR,
                label=t("dock_ps_failed_label"),
                size_bytes=0,
                detail=t("dock_ps_failed", rc=cp.returncode),
                risk=Risk.REPORT_ONLY,
            )
        ]
    findings: list[Finding] = []
    for line in _stdout_or_raise(cp, "docker ps").splitlines():
        if not line.strip():
            continue
        d = json.loads(line)
        if str(d.get("State", "")) not in _STOPPED_STATES:
            continue  # running/paused containers are never offered
        names = str(d.get("Names", "")).split()
        if not names:
            continue
        name = names[0]
        findings.append(
            Finding(
                key=f"{keys.DOCKER_CONTAINER_PREFIX}{name}",
                label=t(
                    "dock_container_label",
                    name=name,
                    image=_short_image(str(d.get("Image", "?"))),
                ),
                size_bytes=parse_size(str(d.get("Size", ""))),
                detail=t("dock_container_detail", status=d.get("Status", "?")),
                risk=Risk.CLEANABLE,
            )
        )
    return findings


def _stdout_or_raise(cp: subprocess.CompletedProcess[str], cmd_name: str) -> str:
    """rc=0 with stdout=None is a LIE: communicate() swallows reader-thread
    crashes (the 2026-10-09 zh-Windows GBK decode incident). Refuse to guess."""
    if cp.stdout is None:
        msg = (
            f"{cmd_name} exited rc={cp.returncode!r} but stdout is None — "
            "a swallowed pipe-reader crash; see _run's encoding note"
        )
        raise RuntimeError(msg)
    return cp.stdout


@register("docker")
def probe(runner: RunFn | None = None) -> list[Finding]:
    """runner param exists for tests (canned CompletedProcess injection)."""
    run = runner or _run
    try:
        cp = run(_DF_CMD)
    except FileNotFoundError:
        return []  # docker not installed on this machine — nothing to report
    except subprocess.TimeoutExpired:
        return [
            Finding(
                key=keys.DOCKER_DAEMON,
                label=t("dock_daemon_timeout_label"),
                size_bytes=0,
                detail=t("dock_daemon_timeout"),
                risk=Risk.REPORT_ONLY,
            )
        ]
    if cp.returncode != 0:
        return [
            Finding(
                key=keys.DOCKER_DAEMON,
                label=t("dock_daemon_label"),
                size_bytes=0,
                detail=t("dock_daemon_unreachable", rc=cp.returncode),
                risk=Risk.REPORT_ONLY,
            )
        ]
    findings = _findings_from_rows(_parse_rows(_stdout_or_raise(cp, "docker system df")))
    findings.extend(_container_findings(run))
    return findings
