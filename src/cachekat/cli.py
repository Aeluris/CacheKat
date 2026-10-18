"""CLI entry point: `cachekat scan` (read-only report), `cachekat tui`,
and `cachekat vhdx` (Docker Desktop WSL2 disk compact command list).

Language: every invocation resolves --lang (default auto: system locale,
zh* -> zh, else en) and resets the i18n state — no cross-call leakage.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict

from cachekat import __version__, probes  # noqa: F401  (probe registration by import)
from cachekat.i18n import resolve_lang, set_lang, t
from cachekat.models import Finding, Risk
from cachekat.probes.wsl_vhdx import find_vhdx
from cachekat.registry import run_scan


def human_size(n: int) -> str:
    steps = ("B", "KiB", "MiB", "GiB", "TiB")
    size = float(n)
    for unit in steps:
        if size < 1024 or unit == steps[-1]:
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"  # pragma: no cover (loop always returns above)


def format_table(findings: list[Finding]) -> str:
    lines = [
        t("scan_title"),
        "=" * 64,
    ]
    for f in findings:
        marker = "~" if f.risk is Risk.CLEANABLE else "!"
        lines.append(
            f"[{marker}] {f.label:<28} {human_size(f.size_bytes):>10}"
            f"  {f.detail}"
        )
    lines.append("=" * 64)
    reclaimable = sum(f.size_bytes for f in findings if f.risk is Risk.CLEANABLE)
    lines.append(t("scan_summary", size=human_size(reclaimable)))
    if any(f.risk is Risk.REPORT_ONLY for f in findings):
        lines.append(t("scan_report_note"))
    return "\n".join(lines)


def to_json(findings: list[Finding]) -> str:
    rows = [
        asdict(f)
        | {
            "risk": f.risk.value,
            "path": str(f.path) if f.path is not None else None,
        }
        for f in findings
    ]
    return json.dumps(rows, ensure_ascii=False, indent=2)


# --- cachekat vhdx ---------------------------------------------------------


def vhdx_report(
    localappdata: str | None, optimize_available: bool, appdata: str | None = None
) -> str:
    """The compact command list. CacheKat only PRINTS commands — running
    them is the user's call, because step 1 stops every WSL distro and
    Docker Desktop (a whole-machine pause, not a cache decision)."""
    found = find_vhdx(localappdata, appdata)
    if not found:
        return t("wsl_vhdx_cli_missing")
    lines: list[str] = [t("wsl_vhdx_cli_title"), ""]
    for _, p in found:
        lines.append(
            t("wsl_vhdx_cli_found", path=str(p), size=human_size(p.stat().st_size))
        )
    lines += ["", t("wsl_vhdx_cli_stop_warning"), f"  {t('wsl_vhdx_cli_step_shutdown')}", ""]
    if optimize_available:
        lines.append(t("wsl_vhdx_cli_step2_optimize"))
        for _, p in found:
            lines.append(f'  Optimize-VHD -Path "{p}" -Mode Full')
    else:
        lines.append(t("wsl_vhdx_cli_step2_diskpart"))
        for _, p in found:
            lines += [
                f'  select vdisk file="{p}"',
                "  attach vdisk readonly",
                "  compact vdisk",
                "  detach vdisk",
            ]
    lines += ["", t("wsl_vhdx_cli_note")]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cachekat",
        description="See which dev caches eat your disk. Scans are read-only; "
        "cleaning is always an explicit, confirmed choice.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_scan = sub.add_parser("scan", help="read-only scan and report")
    p_scan.add_argument("--json", action="store_true", help="machine-readable output")
    p_scan.add_argument("--lang", default="auto", choices=["auto", "en", "zh"])
    p_tui = sub.add_parser("tui", help="interactive TUI (select, confirm, clean)")
    p_tui.add_argument("--lang", default="auto", choices=["auto", "en", "zh"])
    p_vhdx = sub.add_parser(
        "vhdx",
        help="Docker Desktop WSL2 disk: print a compact command list "
        "(report-only — commands are yours to run, not ours)",
    )
    p_vhdx.add_argument("--lang", default="auto", choices=["auto", "en", "zh"])
    args = parser.parse_args(argv)

    set_lang(resolve_lang(args.lang))

    if args.command == "tui":
        from cachekat.tui import run_app  # lazy: keeps scan light without textual

        return run_app(lang=args.lang)

    if args.command == "vhdx":
        if sys.platform != "win32":
            print(t("wsl_vhdx_cli_windows_only"))
            return 0
        from cachekat.actions import optimize_vhd_available

        print(
            vhdx_report(
                os.environ.get("LOCALAPPDATA"), optimize_vhd_available(),
                os.environ.get("APPDATA"),
            )
        )
        return 0

    findings = run_scan()
    if args.command == "scan":
        print(to_json(findings) if args.json else format_table(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
