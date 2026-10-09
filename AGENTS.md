# AGENTS.md — CacheKat

Rules for any coding agent (or human contributor) working in this repo.
Read this fully before the first commit of a session.

## Mission

A read-only-first TUI that shows which dev caches eat the disk
(Docker, pip, npm, playwright, more later) and reclaims space through
**explicit, risk-graded, confirmed** actions. Windows + Linux first.

## Hard boundaries (violating any of these = the change is rejected)

1. **Never auto-delete.** Every destructive action requires: user selection +
   confirmation. `REPORT_ONLY` findings (Docker volumes, WSL vhdx, unused
   images until per-image selection exists) are NEVER cleaned by the tool —
   not behind a flag, not ever. Stopped containers are cleanable ONLY as
   individually selected findings, each carrying the "docker rm deletes the
   CONTAINER ITSELF, not a cache" warning, and the action uses `docker rm`
   WITHOUT -f so a container started after the scan refuses naturally
   (2026-10-08 incident: a blanket container prune killed a persistent test
   bench; per-item + loud warnings is the fix mandated after the incident).
2. **No silent stubs.** A probe that cannot run must surface as an error
   Finding (see `registry.run_scan`). Swallowing exceptions to look green is
   the worst offense in this repo.
3. **Tests green before commit.** `ruff check src tests && pytest -q` must
   pass locally. CI runs the same on ubuntu + windows, Python 3.10/3.12.
4. **Zero runtime deps until M2.** The only allowed runtime dependency from
   M2 on is `textual`. Everything else: standard library. Adding a dep needs
   an explicit reason in the PR.
5. **Data shapes are explicit.** Cross-boundary data = dataclasses from
   `models.py` (`Finding`, `Risk`). No magic strings — risk levels are enum
   members, probe ids are checked at registration.
6. **Interface convergence.** Probes register in exactly one place
   (`registry.register`); CLI/TUI consume via `run_scan()`/`all_probes()`
   only. No probe imports from the CLI layer.

## Workflow per milestone (one acceptance gate each, no skipping)

- M0 skeleton: registry + `cachekat scan` + pip probe + CI — DONE 2026-10-08
- M1 probes: docker / npm / playwright (fake-path unit tests per probe) — DONE 2026-10-08
- M2 TUI: textual app, selection, confirmation, dry-run, actions layer — DONE 2026-10-08
- M3 open-source prep: README EN/中文, GIF, LICENSE (MIT), CONTRIBUTING
- M4 public flip: v0.1.0 tag, topics, announcement

Note (M2+): textual is the single runtime dependency. TUI tests use Textual's
headless Pilot via `App.run_test` wrapped in `asyncio.run` — no pytest-asyncio
needed. `actions.clean(finding)` is the ONLY sanctioned entry to destructive
operations; its refusal of REPORT_ONLY is the safety contract, do not bypass.

## Conventions

- Commits: short English imperative subject (`add npm cache probe`).
- **All user-facing strings go through `cachekat.i18n.t`** — en is the source
  of truth, zh is a full table; a new string without both entries fails
  `test_every_key_has_en_and_zh`. Hardcoded UI copy is a review blocker.
- Probe modules: one file per cache family under `src/cachekat/probes/`,
  exposing `probe(...) -> list[Finding]` + path-override params for tests.
- Tests must never touch real caches: always `tmp_path` fakes.
- Before finishing any task, grep yourself:
  `rg -n "TODO|FIXME|XXX|pass$" src/ tests/` — leftover markers need an
  issue link or must go.
- Error messages user-facing: plain English sentence, no traceback dumps.
