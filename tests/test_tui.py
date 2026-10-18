from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from cachekat.models import Finding, Risk

pytest.importorskip("textual", reason="textual not installed in this env")

from rich.cells import cell_len  # noqa: E402
from textual.widgets import DataTable, RichLog, SelectionList  # noqa: E402

from cachekat.tui import CacheKatApp, ConfirmModal, _fit_row  # noqa: E402


def test_fit_row_ellipsizes_but_keeps_size():
    """The row's price tag must survive; only the label shrinks (a real
    panel-overrun report). Measured in display cells — CJK counts double."""
    long_label = "容器：worldtreeapp-n8n-1（docker.n8n.io/n8nio/n8n:latest）"
    row = _fit_row(long_label, "191.1 MiB", 40)
    text = row.plain
    assert "191.1 MiB" in text          # size always visible
    assert "…" in text                  # label gave way
    assert cell_len(text) <= 40         # never overruns the panel


def test_fit_row_short_label_untouched():
    row = _fit_row("npm cache", "25.4 KiB", 40)
    assert row.plain == "~ npm cache  25.4 KiB"


def _fake_findings(tmp_path: Path) -> list[Finding]:
    d = tmp_path / "victim"
    d.mkdir()
    (d / "x").write_bytes(b"x" * 10)
    return [
        Finding("npm/cache", "npm cache", 10, str(d), Risk.CLEANABLE, d),
        Finding("playwright/chromium-1234", "orphan browser", 10, str(d), Risk.CLEANABLE, d),
        Finding("docker/volumes", "docker volumes", 99, "docker", Risk.REPORT_ONLY),
    ]


def test_app_renders_panels_and_summary(tmp_path: Path):
    async def scenario() -> tuple[int, int, str]:
        app = CacheKatApp(findings_provider=lambda: _fake_findings(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            sel = app.query_one("#cleanable", SelectionList)
            table = app.query_one("#report", DataTable)
            summary = str(app.query_one("#summary").content)
            return len(sel.selected), table.row_count, summary

    sel_count, rows, summary = asyncio.run(scenario())
    assert sel_count == 0  # nothing pre-selected: cleaning is opt-in
    assert rows == 1  # report-only visible in its own panel
    assert "20 B" in summary  # two cleanable findings, 10 B each


def test_preselected_findings_start_checked(tmp_path: Path):
    """Probe-graded low-risk rows (dangling docker layers) start checked —
    a DEFAULT, not a bypass: the user can uncheck, the confirm gate
    still lists every consequence before anything runs."""

    def provider() -> list[Finding]:
        return [
            Finding(
                "docker/image/dd44ee55ff6", "docker dangling layer", 10,
                "upgrade orphan", Risk.CLEANABLE, preselect=True,
            ),
            Finding(
                "docker/image/aa11bb22cc3", "image: app:v1.2", 10,
                "retired version", Risk.CLEANABLE,
            ),
            Finding("npm/cache", "npm cache", 10, "d", Risk.CLEANABLE, tmp_path),
        ]

    async def scenario() -> set[str]:
        app = CacheKatApp(findings_provider=provider)
        async with app.run_test() as pilot:
            await pilot.pause()
            sel = app.query_one("#cleanable", SelectionList)
            return set(sel.selected)

    checked = asyncio.run(scenario())
    assert checked == {"docker/image/dd44ee55ff6"}  # dangling yes, others no


def test_maintenance_row_is_selectable_and_summarized(tmp_path: Path):
    """MAINTENANCE (vhdx compact) sits in the LEFT panel like a cache —
    the safety lives in the confirm gate, not the placement."""

    def provider() -> list[Finding]:
        return [
            Finding(
                "wsl/vhdx/docker_data", "Docker Desktop WSL2 磁盘（维护）", 3000,
                "d", Risk.MAINTENANCE, path=tmp_path / "d.vhdx",
            ),
            Finding("docker/volumes", "docker volumes", 99, "docker", Risk.REPORT_ONLY),
        ]

    async def scenario() -> tuple[int, int, str]:
        app = CacheKatApp(findings_provider=provider, lang="zh")
        async with app.run_test() as pilot:
            await pilot.pause()
            sel = app.query_one("#cleanable", SelectionList)
            summary = str(app.query_one("#summary").content)
            table = app.query_one("#report", DataTable)
            return len(sel.selected), table.row_count, summary

    sel_count, rows, summary = asyncio.run(scenario())
    assert sel_count == 0  # selectable but NOT pre-checked (heavy op)
    assert rows == 1  # volumes stay in the report-only panel
    assert "维护" in summary  # maintenance counted separately, honest label
    assert "潜在" in summary  # potential-only, not promised space


def test_confirm_modal_for_maintenance_uses_run_verb_and_tidy_lines(tmp_path: Path):
    """Two regressions pinned (real user feedback): the modal used to say
    '真删 33.1 GiB' for a compact that deletes NOTHING, and the multi-line
    consequence wrapped ugly mid-sentence. Now: verb follows content,
    warnings render one per line."""

    def provider() -> list[Finding]:
        return [
            Finding(
                "wsl/vhdx/docker_data", "Docker Desktop WSL2 磁盘（维护）", 3000,
                "d", Risk.MAINTENANCE, path=tmp_path / "d.vhdx",
            ),
        ]

    async def scenario() -> str:
        app = CacheKatApp(findings_provider=provider, lang="zh")
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")  # select all (the one maintenance row)
            await pilot.press("c")  # open the confirm gate
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            from textual.widgets import Static

            return str(app.screen.query_one(".msg", Static).content)

    text = asyncio.run(scenario())
    assert "执行 1 项" in text  # RUN, not DELETE — the verb follows content
    assert "真删" not in text  # nothing is deleted in a compact
    assert "不删任何数据" in text  # the honest promise leads the block
    assert "⚠" in text  # warnings as their own lines
    assert text.count("↳") == 1  # one arrow head, rest indented under it


def test_confirm_then_dry_run_leaves_disk_alone(tmp_path: Path):
    async def scenario() -> tuple[bool, int, Path]:
        d = tmp_path / "victim"
        app = CacheKatApp(findings_provider=lambda: _fake_findings(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")  # select all cleanable
            await pilot.press("d")  # dry-run ON
            await pilot.press("c")  # open confirm modal
            await pilot.pause()
            assert isinstance(app.screen, ConfirmModal)
            await pilot.press("y")  # confirm
            await pilot.pause(0.3)
            return app._results and app._results[0].ok, len(app._results), d

    ok, n, d = asyncio.run(scenario())
    assert ok and n == 2  # two cleanable findings processed
    assert (d / "x").exists()  # dry-run: disk untouched


def test_footer_bindings_localized_and_palette_kept(tmp_path: Path):
    # regression (a real zh-footer incident): class BINDINGS are baked at
    # class creation, localization happens on the instance _bindings copy —
    # this pins BOTH the mechanism and the ctrl+p built-in it must preserve
    async def scenario() -> tuple[set[str], bool]:
        app = CacheKatApp(findings_provider=lambda: _fake_findings(tmp_path), lang="zh")
        async with app.run_test() as pilot:
            await pilot.pause()
            descs = {str(ab.binding.description) for ab in app.screen.active_bindings.values()}
            has_palette = "ctrl+p" in app.screen.active_bindings
            return descs, has_palette

    descs, has_palette = asyncio.run(scenario())
    assert "全选" in descs and "干跑 开/关" in descs
    assert has_palette


def test_cancel_cleans_nothing(tmp_path: Path):
    async def scenario() -> list:
        app = CacheKatApp(findings_provider=lambda: _fake_findings(tmp_path))
        async with app.run_test() as pilot:
            await pilot.pause()
            await pilot.press("a")
            await pilot.press("c")
            await pilot.pause()
            await pilot.press("escape")  # modal cancel
            await pilot.pause(0.2)
            return app._results

    assert asyncio.run(scenario()) == []


def test_probe_crash_reported_in_log_panel(tmp_path: Path):
    """A crashed probe must be visible in FULL in the log panel — the table's
    note column truncates, the log doesn't (a real Windows case)."""

    def with_crash() -> list[Finding]:
        return _fake_findings(tmp_path) + [
            Finding(
                "docker/error", "docker 探针崩溃", 0,
                "AttributeError @ docker_df.py:42 in _parse_rows: 'NoneType' …",
                Risk.REPORT_ONLY, is_error=True,
            )
        ]

    async def scenario() -> str:
        app = CacheKatApp(findings_provider=with_crash, lang="zh")
        async with app.run_test() as pilot:
            await pilot.pause()
            log = app.query_one("#log", RichLog)
            return "".join(getattr(line, "text", "") for line in log.lines)

    text = asyncio.run(scenario())
    assert "docker/error" not in text  # crash row is labeled, not raw key
    assert "探针崩溃" in text
    assert "@ docker_df.py:42" in text
