"""Textual TUI: scan -> select -> confirm -> clean (dry-run switchable).

Logic spine (deliberately boring and hard to misuse):
- left panel: CLEANABLE findings, selectable (space); right panel: REPORT_ONLY,
  visible but untouchable — the layout itself teaches the safety model.
- `c` opens a confirm modal listing exactly what will run; nothing cleans
  without an explicit yes.
- `d` toggles dry-run: actions describe what they WOULD do, disk untouched.
- clean runs in a worker thread; results land in the log panel, honestly
  (failures included — never swallowed).

All UI copy goes through cachekat.i18n.t — no hardcoded user-facing text.
Language is set once at construction (CLI --lang, default auto by locale).
"""

from __future__ import annotations

from collections.abc import Callable

from rich.markup import escape
from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.binding import Binding, BindingsMap
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    RichLog,
    SelectionList,
    Static,
)

from cachekat.actions import ActionResult, clean, consequence
from cachekat.cli import human_size
from cachekat.i18n import resolve_lang, set_lang, t
from cachekat.models import Finding, Risk
from cachekat.registry import run_scan

FindingsFn = Callable[[], list[Finding]]


def _fit_row(label: str, size: str, width: int) -> Text:
    """One selection-list row: `~ label  size`, measured in display cells.

    Long labels ellipsize; the size column stays visible — a row without its
    price tag is a lie (user report: container rows overran the
    left panel edge). Full label still shows in the confirm modal."""
    marker = Text("~ ", style="green")
    size_txt = Text(size, style="dim")
    # fudge: toggle button + gutter + trailing padding (~6 cells)
    budget = width - size_txt.cell_len - marker.cell_len - 6
    label_txt = Text(label)
    if budget > 4 and label_txt.cell_len > budget:
        label_txt.truncate(budget, overflow="ellipsis")
    return Text.assemble(marker, label_txt, Text("  "), size_txt)


class ConfirmModal(ModalScreen[bool]):
    """The one gate between selection and deletion."""

    BINDINGS = [
        Binding("y,enter", "confirm", "confirm", show=False),
        Binding("escape,n", "cancel", "cancel", show=False),
    ]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="dialog"):
            yield Static(self._message, classes="msg")
            with Horizontal(classes="buttons"):
                yield Button(t("yes_button"), id="yes", variant="error")
                yield Button(t("no_button"), id="no", variant="default")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "yes")

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)


class CacheKatApp(App[None]):
    TITLE = "CacheKat"

    CSS = """
    Screen { layout: vertical; }

    #banner {
        dock: top; height: 1; padding: 0 2;
        background: $accent 20%; text-style: bold;
    }
    #summary {
        dock: top; height: 3; padding: 0 2;
        border: round $accent; content-align: center middle;
        background: $surface;
    }
    #body { height: 1fr; }
    #left, #right { width: 1fr; height: 1fr; padding: 0 1; }
    #left { border: round $success; }
    #right { border: round $error 60%; }
    #left-label, #right-label, #log-label { text-style: bold; padding: 0 1; }
    #cleanable { border: none; background: transparent; height: 1fr; }
    #report { border: none; height: 1fr; }
    #log { height: 10; border: round $panel; padding: 0 1; }
    ConfirmModal { align: center middle; }
    .dialog {
        width: 78; height: auto; max-width: 95%;
        border: thick $accent; background: $surface; padding: 1 2;
    }
    .dialog .msg { padding: 0 1; margin-bottom: 1; }
    .dialog .buttons { height: auto; align-horizontal: center; }
    .dialog Button { margin: 0 2; }
    """

    BINDINGS = [
        Binding("a", "all", "all"),
        Binding("n", "none", "none"),
        Binding("d", "dry", "dry-run"),
        Binding("c", "clean", "clean"),
        Binding("r", "rescan", "rescan"),
        Binding("q", "quit", "quit"),
    ]

    def __init__(
        self, findings_provider: FindingsFn | None = None, lang: str = "auto"
    ) -> None:
        set_lang(resolve_lang(lang))  # language FIRST (it feeds compose())
        super().__init__()
        # Localize the footer bindings. Class BINDINGS are merged and baked
        # at class-creation time (__init_subclass__), so swapping the class
        # attribute does nothing (a real-world miss). The instance
        # _bindings map is OUR copy — REBUILD it from the current one,
        # preserving every built-in (ctrl+p palette, ctrl+q quit, ...) and
        # only replacing our six descriptions.
        override = {
            "all": t("key_all"),
            "none": t("key_none"),
            "dry": t("key_dry"),
            "clean": t("key_clean"),
            "rescan": t("key_rescan"),
            "quit": t("key_quit"),
        }
        rebuilt = BindingsMap()
        for key, b in self._bindings:
            desc = override.get(b.action, b.description)
            rebuilt.bind(
                key, b.action, desc, show=b.show, key_display=b.key_display,
                priority=b.priority,
            )
        self._bindings = rebuilt
        self._provider = findings_provider or run_scan
        self._findings: list[Finding] = []
        self._pending: list[Finding] = []
        self._dry = False
        self._busy = False
        self._results: list[ActionResult] = []

    def compose(self) -> ComposeResult:
        yield Static(t("banner_title"), id="banner")
        yield Static(t("scanning"), id="summary")
        with Horizontal(id="body"):
            with Vertical(id="left"):
                yield Static(t("left_label"), id="left-label")
                yield SelectionList(id="cleanable")
            with Vertical(id="right"):
                yield Static(t("right_label"), id="right-label")
                yield DataTable(id="report")
        yield Static(t("log_label"), id="log-label")
        yield RichLog(id="log", markup=True)
        # the real Footer (restored on a second attempt): clickable
        # bindings + built-in command palette button (^p) — the Static keybar
        # placeholder could not do either
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#report", DataTable).add_columns(
            t("col_item"), t("col_size"), t("col_note")
        )
        self._kick_scan()

    # --- scanning -----------------------------------------------------------

    def _kick_scan(self) -> None:
        self._busy = True
        self._render_summary(t("scanning"))
        self._scan_worker()

    @work(thread=True, exclusive=True)
    def _scan_worker(self) -> None:
        findings = self._provider()
        self.call_from_thread(self._render, findings)

    def _render(self, findings: list[Finding]) -> None:
        self._findings = findings
        self._busy = False
        sel = self.query_one("#cleanable", SelectionList)
        sel.clear_options()
        panel_w = sel.size.width or 60  # 0 before first layout — sane fallback
        for f in findings:
            if f.risk is Risk.CLEANABLE:
                sel.add_option(
                    (_fit_row(f.label, human_size(f.size_bytes), panel_w), f.key)
                )
        table = self.query_one("#report", DataTable)
        table.clear()
        for f in findings:
            if f.risk is Risk.REPORT_ONLY:
                table.add_row(f.label, human_size(f.size_bytes), f.detail, key=f.key)
        # probe crash reports ALSO land in the log panel: the table's note
        # column truncates ("AttributeErro"…), the log shows the whole line
        # with the raise site (a real Windows case)
        log = self.query_one("#log", RichLog)
        for f in findings:
            if f.is_error:
                log.write(f"[red]✘[/red] {escape(f.label)}\n    {escape(f.detail)}")
        self._render_summary()

    def _render_summary(self, extra: str = "") -> None:
        total = sum(f.size_bytes for f in self._findings if f.risk is Risk.CLEANABLE)
        selected = self._selected_keys()
        chosen = sum(
            f.size_bytes for f in self._findings if f.risk is Risk.CLEANABLE and f.key in selected
        )
        dry = t("dry_on") if self._dry else t("dry_off")
        text = t(
            "summary_line",
            size=f"[b]{human_size(total)}[/b]",
            n=len(selected),
            sel=human_size(chosen),
            dry=dry,
        )
        if extra:
            text += f"\n{extra}"
        self.query_one("#summary", Static).update(text)

    def _selected_keys(self) -> list[str]:
        # no blanket except here (audit): a failing query means a
        # real bug (widget missing) and must crash loudly, not silently
        # behave as "nothing selected"
        sel = self.query_one("#cleanable", SelectionList).selected
        return [str(v) for v in sel]

    # --- bindings -----------------------------------------------------------

    def action_all(self) -> None:
        self.query_one("#cleanable", SelectionList).select_all()
        self._render_summary()

    def action_none(self) -> None:
        self.query_one("#cleanable", SelectionList).deselect_all()
        self._render_summary()

    def action_dry(self) -> None:
        self._dry = not self._dry
        self._render_summary()

    def action_rescan(self) -> None:
        self._kick_scan()

    def action_clean(self) -> None:
        if self._busy:
            self.notify(t("notify_busy"), severity="warning")
            return
        chosen = [
            f
            for f in self._findings
            if f.risk is Risk.CLEANABLE and f.key in self._selected_keys()
        ]
        if not chosen:
            self.notify(t("notify_none_selected"), severity="information")
            return
        size = human_size(sum(f.size_bytes for f in chosen))
        verb = t("confirm_dry") if self._dry else t("confirm_real")
        # Hard lesson: item names alone don't warn — every line carries
        # a plain-words consequence from actions.consequence()
        lines = "\n".join(
            f"~ {f.label}（{human_size(f.size_bytes)}）\n    ↳ {consequence(f)}"
            for f in chosen
        )
        self.push_screen(
            ConfirmModal(t("confirm_title", verb=verb, n=len(chosen), size=size) + "\n" + lines),
            callback=self._on_confirm,
        )
        self._pending = chosen  # stash for the callback

    def _on_confirm(self, ok: bool) -> None:
        chosen = self._pending
        if not ok:
            self.notify(t("notify_cancelled"))
            return
        self._busy = True
        self._clean_worker(chosen)

    @work(thread=True, exclusive=True)
    def _clean_worker(self, chosen: list[Finding]) -> None:
        results = [clean(f, dry_run=self._dry) for f in chosen]
        self.call_from_thread(self._show_results, results)

    def _show_results(self, results: list[ActionResult]) -> None:
        self._results = results
        self._busy = False
        log = self.query_one("#log", RichLog)
        for r in results:
            mark = "✔" if r.ok else "✘"
            style = "" if r.ok else "[red]"
            log.write(f"{style}{mark} {escape(r.key)} — {escape(r.detail)}")
        ok_n = sum(1 for r in results if r.ok)
        mode = t("mode_dry") if self._dry else t("mode_real")
        self.notify(t("notify_done", ok=ok_n, n=len(results), mode=mode))


def run_app(lang: str = "auto") -> int:
    CacheKatApp(lang=lang).run()
    return 0
