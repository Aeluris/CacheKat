"""Single home for every user-facing string (standing design decision).

Rules:
- ALL UI copy goes through `t()` — hardcoded user-facing text is a review
  blocker (see AGENTS.md conventions).
- en is the source of truth; zh is a full table. A missing zh entry falls
  back to en (never crashes the TUI); a missing KEY fails loudly.
- Language is a process-wide choice set once at entry (CLI flag -> set_lang);
  runtime hot-switching is deliberately out of scope until real users ask.
"""

from __future__ import annotations

import locale
import os
import sys

Lang = str  # "en" | "zh"

_LANG: Lang = "en"  # safe default until an entry point resolves it

_STRINGS: dict[str, dict[str, str]] = {
    # --- TUI chrome -------------------------------------------------------
    "banner_title": {
        "en": "🐈 CacheKat — dev cache checkup",
        "zh": "🐈 CacheKat — 开发缓存体检",
    },
    "col_item": {"en": "item", "zh": "项"},
    "col_size": {"en": "size", "zh": "大小"},
    "col_note": {"en": "note", "zh": "说明"},
    "key_all": {"en": "select all", "zh": "全选"},
    "key_none": {"en": "clear selection", "zh": "清空选择"},
    "key_dry": {"en": "dry-run on/off", "zh": "干跑 开/关"},
    "key_clean": {"en": "clean selected", "zh": "清理选中"},
    "key_rescan": {"en": "rescan", "zh": "重新扫描"},
    "key_quit": {"en": "quit", "zh": "退出"},
    "left_label": {
        "en": "cleanable (select with space, run with c)",
        "zh": "可清理（勾选后 c 执行）",
    },
    "right_label": {
        "en": "report-only (data / uncertain)",
        "zh": "只报不动（数据/判不准）",
    },
    "log_label": {"en": "action log", "zh": "执行日志"},
    "scanning": {"en": "scanning…", "zh": "扫描中…"},
    "summary_line": {
        "en": "reclaimable total {size} · selected {n} items ({sel}) · {dry}",
        "zh": "可回收合计 {size} · 已选 {n} 项（{sel}）· {dry}",
    },
    "dry_on": {
        "en": "dry-run ON (rehearse — nothing is deleted)",
        "zh": "干跑 开（只演示，不删任何东西）",
    },
    "dry_off": {
        "en": "dry-run OFF (clean executes for real)",
        "zh": "干跑 关（c 执行即真删）",
    },
    "notify_busy": {"en": "scanning, wait a beat", "zh": "扫描中，稍等"},
    "notify_none_selected": {
        "en": "nothing selected — press space on a row",
        "zh": "没勾任何可清项——space 勾选",
    },
    "confirm_dry": {"en": "dry-run", "zh": "干跑演示"},
    "confirm_real": {"en": "DELETE", "zh": "真删"},
    "confirm_title": {
        "en": "{verb} {n} items, ~{size}:",
        "zh": "{verb} {n} 项，约 {size}：",
    },
    "notify_cancelled": {
        "en": "cancelled — nothing touched",
        "zh": "已取消，什么都没动",
    },
    "notify_done": {"en": "{ok}/{n} done ({mode})", "zh": "{ok}/{n} 项完成（{mode}）"},
    "mode_dry": {"en": "dry-run", "zh": "干跑"},
    "mode_real": {"en": "executed", "zh": "已执行"},
    "yes_button": {"en": "confirm [Y]", "zh": "确认 [Y]"},
    "no_button": {"en": "cancel [Esc]", "zh": "取消 [Esc]"},
    # --- scan CLI ----------------------------------------------------------
    "scan_title": {
        "en": "CacheKat scan (read-only — nothing is deleted)",
        "zh": "CacheKat 扫描（只读——不删任何东西）",
    },
    "scan_report_note": {
        "en": "[!] lines are report-only — CacheKat never cleans those",
        "zh": "[!] 行为只报不动——CacheKat 永不清理它们",
    },
    "scan_summary": {
        "en": "reclaimable (cache, re-download cost only): {size}",
        "zh": "可回收（缓存，重下代价而已）：{size}",
    },
    "probe_failed_label": {
        "en": "{probe} probe failed — full reason in the log below",
        "zh": "{probe} 探针崩溃——完整原因见下方执行日志",
    },
    # --- actions.consequence ------------------------------------------------
    "cons_pip": {
        "en": "purge pip download cache — packages re-download on next install",
        "zh": "清空 pip 下载缓存——下次装包重新下载",
    },
    "cons_npm": {
        "en": "delete the npm cache directory — npm re-downloads on demand",
        "zh": "删除 npm 缓存目录——用时重新下载",
    },
    "cons_build_cache": {
        "en": "docker builder prune -f — removes ORPHANED build cache only "
        "(in-use cache untouched); next build re-runs cold steps",
        "zh": "docker builder prune -f——只删无主构建缓存（在用的不动）；"
        "下次构建重跑冷步骤",
    },
    "cons_container": {
        "en": "docker rm — deletes the CONTAINER ITSELF, not a cache; "
        "recreate with docker run / compose up if needed. Volumes untouched",
        "zh": "docker rm——删除的是容器本体（不是缓存）；需要时用 "
        "docker run/compose 重建。卷不受影响",
    },
    "cons_playwright": {
        "en": "delete this browser directory — `playwright install` "
        "re-downloads if ever needed",
        "zh": "删除该浏览器目录——需要时 `playwright install` 重下",
    },
    "cons_none": {
        "en": "no clean action for this finding",
        "zh": "此条目暂无可执行清理",
    },
    # --- docker probe -------------------------------------------------------
    "dock_volumes_label": {"en": "docker volumes (data!)", "zh": "docker 卷（数据！）"},
    "dock_volumes_detail": {
        "en": "{n} volumes — CacheKat never cleans volumes",
        "zh": "{n} 个卷——CacheKat 永不清理卷",
    },
    "dock_images_label": {
        "en": "docker unused images (report-only)",
        "zh": "docker 未用镜像（只报）",
    },
    "dock_images_detail": {
        "en": "docker image prune -a would remove ALL unused images — "
        "per-image selection pending; use `docker rmi` yourself meanwhile",
        "zh": "docker image prune -a 会删掉全部未用镜像——逐镜像勾选待做；"
        "需要清理请自己 `docker rmi` 挑着删",
    },
    "dock_build_label": {"en": "docker build cache", "zh": "docker 构建缓存"},
    "dock_build_detail": {
        "en": "build cache layers, per docker system df (builder prune keeps in-use cache)",
        "zh": "构建缓存层，docker system df 口径（builder prune 保留在用缓存）",
    },
    "dock_container_label": {
        "en": "container: {name} ({image})",
        "zh": "容器：{name}（{image}）",
    },
    "dock_container_detail": {
        "en": "{status} — docker rm deletes the CONTAINER ITSELF, not a "
        "cache; recreate via docker run / compose up. Volumes are NOT touched",
        "zh": "{status}——docker rm 删除的是容器本体而非缓存；可 docker "
        "run/compose 重建。卷不受影响",
    },
    "dock_daemon_unreachable": {
        "en": "docker CLI exists but exited {rc} — start Docker Desktop, "
        "then press r in the TUI to rescan",
        "zh": "docker CLI 存在但退出码 {rc}——启动 Docker Desktop 后在 "
        "TUI 里按 r 重扫",
    },
    "dock_daemon_timeout": {
        "en": "docker CLI exists but `docker system df` timed out",
        "zh": "docker CLI 存在但 `docker system df` 超时",
    },
    "dock_ps_timeout": {
        "en": "container listing timed out",
        "zh": "容器列表获取超时",
    },
    "dock_ps_failed": {
        "en": "exited {rc} — container listing unavailable",
        "zh": "退出码 {rc}——容器列表不可用",
    },
    "dock_ps_timeout_label": {"en": "docker ps timed out", "zh": "docker ps 超时"},
    "dock_ps_failed_label": {"en": "docker ps failed", "zh": "docker ps 失败"},
    "dock_daemon_label": {
        "en": "docker daemon unreachable",
        "zh": "docker 守护进程连不上",
    },
    "dock_daemon_timeout_label": {
        "en": "docker daemon timed out",
        "zh": "docker 守护进程超时",
    },
    # --- playwright probe ----------------------------------------------------
    "pw_orphan_label": {
        "en": "playwright {name} (orphan)",
        "zh": "playwright {name}（孤儿）",
    },
    "pw_inuse_label": {"en": "playwright {name}", "zh": "playwright {name}"},
    "pw_orphan_detail": {
        "en": "not referenced by installed playwright",
        "zh": "未被当前 playwright 引用",
    },
    "pw_unknown_label": {
        "en": "playwright browsers (liveness unknown)",
        "zh": "playwright 浏览器（活性未知）",
    },
    "pw_unknown_detail": {
        "en": "{path} — playwright package not importable here, cannot tell "
        "orphans from in-use",
        "zh": "{path}——此环境 import 不到 playwright 包，判不了哪些在用",
    },
}


def _windows_prefers_zh() -> bool:
    """Ask Windows directly: GetUserDefaultUILanguage LANGID, primary
    language 0x04 = Chinese (a real-world bug: cmd sets no LANG and
    locale.getlocale() returns (None, None) — auto never resolved zh)."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        lang_id = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return (lang_id & 0x3FF) == 0x04
    except Exception:  # noqa: BLE001 — detection must never crash the app
        return False


def _system_prefers_zh() -> bool:
    """Env vars first (POSIX semantics: first set var wins), then the OS
    native call on Windows, locale last. getdefaultlocale is NOT used:
    deprecated, removed in 3.15."""
    for var in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        val = os.environ.get(var, "")
        if val:
            return val.lower().startswith("zh")
    if sys.platform == "win32":
        return _windows_prefers_zh()
    try:
        loc = locale.getlocale()[0] or ""
    except ValueError:
        loc = ""
    return loc.lower().startswith("zh")


def resolve_lang(spec: str) -> Lang:
    """'auto' follows the system preference (zh* -> zh, else en)."""
    if spec in ("en", "zh"):
        return spec
    return "zh" if _system_prefers_zh() else "en"


def set_lang(lang: Lang) -> None:
    global _LANG
    if lang not in ("en", "zh"):
        msg = f"unknown lang {lang!r}"
        raise ValueError(msg)
    _LANG = lang


def current_lang() -> Lang:
    return _LANG


def t(key: str, **fmt: object) -> str:
    """Translate `key` in the active language. Missing zh -> en fallback."""
    entry = _STRINGS.get(key)
    if entry is None:
        msg = f"missing i18n key {key!r}"
        raise KeyError(msg)
    text = entry.get(_LANG) or entry["en"]
    return text.format(**fmt) if fmt else text
