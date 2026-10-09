# Contributing to CacheKat

Thanks for considering a contribution — a small tool like this lives on
quality over quantity of PRs.

## Read this first

- [`AGENTS.md`](AGENTS.md) is the rulebook (it applies to humans too):
  safety boundaries, architecture layers, conventions. The short version:
  - **Never widen a destructive action.** `REPORT_ONLY` findings stay
    untouchable; per-item selection is the only path to cleaning assets.
  - **No silent stubs.** If a probe or action cannot run, it must surface as
    a visible failure — never be swallowed to look green.
  - All user-facing strings go through `cachekat.i18n` (en source of truth,
    zh full table; a string missing either side fails the tests).
  - Finding keys come from `cachekat/keys.py` — no fresh string literals in
    src code. Tests intentionally pin the literal strings (contract tests).

## Development setup

```
git clone https://github.com/Aeluris/CacheKat.git
cd CacheKat
python -m venv .venv && .venv/bin/pip install -e .[dev]   # Windows: .venv\Scripts\pip
ruff check src tests
pytest -q
```

## Ground rules

1. Branch from `main`; keep PRs single-purpose.
2. `ruff check src tests && pytest -q` must be green locally — CI runs the
   same on ubuntu + windows × Python 3.10/3.12.
3. New probes: one file per cache family under `src/cachekat/probes/`,
   register via `@register(...)`, and unit-test with fake paths
   (`tmp_path`) — **tests never touch real caches**.
4. Commits: short English imperative subject.
5. Open an issue before large changes — a quick design discussion saves
   everyone a review round.

## Reporting bugs / ideas

Open an issue with: OS, Python version, `cachekat scan --json` output
(redact anything private — paths and container names are yours to keep).

## License

MIT — by contributing you agree your contributions land under it too.
