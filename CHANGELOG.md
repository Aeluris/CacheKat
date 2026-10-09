# Changelog

All notable changes to CacheKat are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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
