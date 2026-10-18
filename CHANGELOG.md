# Changelog

All notable changes to CacheKat are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.6.5] — 2026-10-18

### Added
- The vhdx probe now follows a custom Docker Desktop "Disk image
  location" (moved disks): reads the folder from Docker Desktop's
  settings file (settings-store.json or legacy settings.json, tolerant
  of every known key spelling), probes several sub-layouts under it,
  and when the moved disk exists the default-location leftover is
  skipped so you never compact a dead copy. Broken/missing settings
  degrade silently to the default layouts — settings are a lead, not
  an authority. `cachekat vhdx` reports the same move-aware paths.

## [0.6.4] — 2026-10-18

### Changed
- The vhdx result now points users at a copy-pasteable PowerShell command
  (`-NoProfile -ExecutionPolicy Bypass -File ...`) instead of the
  right-click "Run with PowerShell" menu item, which loads the profile,
  gates execution differently and — worst — closes its window on any
  failure, dropping the error message. The command form keeps every
  error visible; verified on a real machine.

## [0.6.3] — 2026-10-18

### Fixed
- Generated script is now ASCII-only with a UTF-8 BOM: Windows
  PowerShell 5.1 decodes BOM-less files as the ANSI system codepage,
  where non-ASCII punctuation (an em dash in a comment/host string) can
  scramble parsing. Belt and suspenders — either alone survives a
  misconfigured reader.

## [0.6.2] — 2026-10-18

### Fixed
- Generated compact script died before the UAC prompt ever showed
  (user-reported flash-close): it assigned `$args`, a read-only
  PowerShell automatic variable — with `ErrorActionPreference = "Stop"`
  the script terminated instantly. Now uses a plain variable, and the
  compact body runs inside try/catch/finally so ANY failure (not just
  this one) stays on screen instead of flash-closing. Tests pin the
  known automatic-variable minefield statically — Linux CI cannot run
  PowerShell semantics, so the next defense line is the real machine.

## [0.6.1] — 2026-10-16

### Changed
- Wording/layout polish from real-machine feedback: the vhdx confirm
  gate now renders its warnings one per line (aligned, scannable) instead
  of a wrapped paragraph; the action log result and the summary-bar
  maintenance note are trimmed to one line each.
- Confirm-modal verb follows the selection: maintenance-only or mixed
  selections say "RUN" (执行), not "DELETE" (真删) — a compact that
  deletes nothing must not be titled like a deletion.

## [0.6.0] — 2026-10-16

### Added
- Maintenance grade: a third risk tier for data-loss-free but heavy
  operations. The Docker Desktop WSL2 disk (vhdx) moves from report-only
  into the selectable panel — compacting deletes nothing, so it is not
  "cleaning" and not junk either; its confirm gate carries the special
  warnings (admin rights, every WSL distro stops, minutes of runtime).
- Selecting the vhdx row and confirming runs step 1 of the compact plan:
  CacheKat refuses while Docker Desktop is running (its backend would
  relaunch WSL seconds later — quit it from the tray, never killed by
  us), then stops WSL (`wsl --shutdown`), then writes a self-elevating
  compact script (Optimize-VHD, diskpart fallback) next to the vhdx.
  Running the script is the user's click: its own UAC prompt is the
  consent, and the tool never executes the admin part itself.

### Changed
- Summary bar counts maintenance separately, labelled as potential
  (the vhdx file size is an upper bound; compacting returns only the
  free space inside it).

## [0.5.0] — 2026-10-16

### Added
- Docker: retired images are now listed per image — dangling layers
  (untagged upgrade orphans) and extra versions of repositories you keep
  multiple versions of. Each row cleans via its own confirmed
  `docker rmi` **without `-f`**: an image any container still references
  refuses removal on its own, and volumes are never touched. Dangling
  rows start pre-checked (low-risk, confirm gate unchanged); retired
  versions never do — only you know which one is live.
- `cachekat vhdx` (Windows): reports the Docker Desktop WSL2 disk size
  and prints a compact command list — `Optimize-VHD` when the Hyper-V
  management tools exist, a diskpart fallback when they don't — including
  the `wsl --shutdown` full-stop warning. CacheKat only prints commands;
  the vhdx itself is report-only, never touched.

### Changed
- Docker: the report-only "unused images" aggregate row is gone,
  replaced by the per-image list above. The registry gains a `wsl_vhdx`
  probe (report-only; off-Windows it stays silent).

## [0.4.11] — 2026-10-09

### Added
- `cachekat --version` — the CLI now reports the package version from the
  single source `cachekat.__version__`.

### Changed
- CHANGELOG: the 0.2.0 -> 0.4.8 jump is now annotated (versions in between
  were internal iterations, never published).

## [0.4.10] — 2026-10-09

### Changed
- README (en/zh): internal roadmap section replaced by a "How it works"
  lifecycle sequence diagram (bilingual, rendered from Mermaid); dev roadmap
  moved to AGENTS.md where it belongs.

## [0.4.9] — 2026-10-09

### Changed
- README (en/zh): badge row moved under the title and extended with a PyPI
  version badge and a pyversions badge; the two screenshots now sit
  side-by-side and reference absolute URLs so they render on the PyPI page
  too; roadmap entries no longer use internal milestone codes.

## [0.4.8] — 2026-10-09 — first PyPI release

(Versions 0.2.1–0.4.7 were internal iterations during development and were
never published; everything they shipped is folded into this entry.)

### Fixed
- **zh-Windows docker crash (a real incident)**: docker output was decoded
  with the locale codec (cp936); a non-ASCII byte sequence in `docker ps`
  JSON crashed the hidden Windows pipe-reader thread — communicate() swallows
  that exception and returns stdout=None, so the probe died with a cryptic
  AttributeError. All subprocess calls now declare `encoding="utf-8,
  errors="replace"`; rc=0 + stdout=None additionally fails loudly with a
  self-describing RuntimeError.
- Left-panel rows no longer overrun the panel edge: labels ellipsize by
  display cells (CJK-aware) while the size column stays visible; docker
  container labels drop the registry host (`docker.n8n.io/n8nio/n8n:latest`
  -> `n8n:latest`). Full labels still show in the confirm modal.
- Probe crash reports carry the raise site (`file:line in func`) and land in
  full in the TUI log panel (the table's note column truncates).
- zh footer now actually localizes: Textual bakes class bindings at class
  creation; localization now rebuilds the instance binding map, preserving
  built-ins (ctrl+p palette, ctrl+q).
- Windows auto-language detection: asks the OS directly
  (`GetUserDefaultUILanguage`) instead of relying on env/locale.
- Dry-run state in the summary bar is self-explaining in both languages.
- Audit pass: single key source (`cachekat/keys.py`), no blanket except in
  selection, honest docstrings, neutral incident wording.

### Changed (safety, after a real incident)
- Docker stopped containers are no longer blanket-pruned: each container is
  an individually selected finding carrying a "docker rm deletes the
  CONTAINER ITSELF, not a cache" warning; `docker rm` runs WITHOUT `-f` so a
  container started after the scan refuses naturally.
- Docker unused images are report-only until per-image selection exists.
- Confirm modal lists the plain-words consequence of every selected item.

## [0.2.0] — 2026-10-08

### Added
- Textual TUI: scan -> select -> confirm -> clean, with dry-run switch,
  worker-thread scans, honest result log.
- Actions layer: per-key clean implementations; REPORT_ONLY is refused
  always, even in dry-run; unknown keys fail loudly.
- `Finding.path` explicit data shape (no path parsing from display text).

## [0.1.0-dev] — 2026-10-08

### Added
- Probe registry, read-only `cachekat scan` (table/JSON), pip probe.
- docker (system df + per-container), npm, playwright (orphan-aware) probes.
- CI matrix: ubuntu + windows × Python 3.10/3.12.
- Full i18n ground: en/zh string tables, `--lang auto|en|zh`.
