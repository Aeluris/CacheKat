"""CLI entry point: `cachekat scan` (read-only report) and `cachekat tui`.

Language: every invocation resolves --lang (default auto: system locale,
zh* -> zh, else en) and resets the i18n state — no cross-call leakage.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from cachekat import probes  # noqa: F401  (probe registration by import)
from cachekat.i18n import resolve_lang, set_lang, t
from cachekat.models import Finding, Risk
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="cachekat",
        description="See which dev caches eat your disk. Scans are read-only; "
        "cleaning is always an explicit, confirmed choice.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_scan = sub.add_parser("scan", help="read-only scan and report")
    p_scan.add_argument("--json", action="store_true", help="machine-readable output")
    p_scan.add_argument("--lang", default="auto", choices=["auto", "en", "zh"])
    p_tui = sub.add_parser("tui", help="interactive TUI (select, confirm, clean)")
    p_tui.add_argument("--lang", default="auto", choices=["auto", "en", "zh"])
    args = parser.parse_args(argv)

    set_lang(resolve_lang(args.lang))

    if args.command == "tui":
        from cachekat.tui import run_app  # lazy: keeps scan light without textual

        return run_app(lang=args.lang)

    findings = run_scan()
    if args.command == "scan":
        print(to_json(findings) if args.json else format_table(findings))
    return 0


if __name__ == "__main__":
    sys.exit(main())
