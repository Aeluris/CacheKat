# CacheKat 🐈

[English](README.md) | [中文](README.zh-CN.md)

[![ci](https://github.com/Aeluris/CacheKat/actions/workflows/ci.yml/badge.svg)](https://github.com/Aeluris/CacheKat/actions/workflows/ci.yml)
[![pypi](https://img.shields.io/pypi/v/cachekat?label=PyPI)](https://pypi.org/project/cachekat/)
[![python](https://img.shields.io/pypi/pyversions/cachekat)](https://pypi.org/project/cachekat/)
[![license](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> A TUI to see which dev caches eat your disk — and reclaim space safely,
> risk-graded. **Never touches your data.**

**Main view** (left: cleanable items, select with `space`, run with `c`;
right: report-only facts, visible but untouchable — the layout itself
teaches the safety model) and the **confirm gate** (nothing cleans without
an explicit yes; each row states its plain-words consequence; dry-run `d`
rehearses with the disk untouched):

| Main view | Confirm gate |
|:---:|:---:|
| ![main view](https://raw.githubusercontent.com/Aeluris/CacheKat/main/docs/screenshots/en-main.png) | ![confirm gate](https://raw.githubusercontent.com/Aeluris/CacheKat/main/docs/screenshots/en-confirm.png) |

## Why

Every developer machine accumulates caches that nobody watches: pip wheels,
npm tarballs, playwright browsers (old versions pile up per release), docker
build cache, dangling images, stopped containers... A fresh scan answers the
only question that matters: **who is eating the disk, and what is actually
safe to reclaim?**

## Safety model (the feature)

| Category | Behavior |
|---|---|
| True caches (pip, npm, playwright orphans, docker build cache) | Selectable — each row states its plain-words consequence before anything runs |
| **Docker volumes (your data)** | **Report-only. Never cleaned. No flag unlocks this.** |
| Docker stopped containers / retired images | Cleanable **one by one**. Containers: each row warns that `docker rm` deletes the container **itself** (recreate via `docker run`/`compose up`; volumes untouched). Images: dangling layers and extra versions of a repo are listed per image, each removed by its own `docker rmi` **without `-f`** — any image a container still references refuses removal on its own. |
| **Docker Desktop WSL2 disk (vhdx) — maintenance** | Selectable, deletes NOTHING: compacting returns the free space inside the vhdx to Windows. The confirm gate warns (admin rights / every WSL distro stops / minutes). Tool runs the stop + writes a self-elevating script; running the script — with its own UAC consent — is your click, not ours. |
| Anything the probe cannot judge | Honest report-only ("liveness unknown"), never a guess |

- Every scan is read-only; cleaning is an explicit, confirmed selection.
- Dry-run mode (`d`): rehearse exactly what would happen — disk untouched.
- Probes that fail surface as visible error rows, never swallowed.

## Install

```
pipx install cachekat
```

Or from source: `pipx install git+https://github.com/Aeluris/CacheKat.git`

## Use

```
cachekat tui             # interactive: scan -> select -> confirm -> clean
cachekat scan            # read-only report: who eats the disk
cachekat scan --json     # machine-readable
cachekat vhdx            # Windows: Docker Desktop disk size + compact command list
# every command accepts --lang auto|en|zh (auto follows the system language)
```

Docker rows need the docker daemon running — if the TUI shows
`docker daemon unreachable`, start Docker Desktop and press `r` to rescan.

## How it works

```text
scan (read-only) → risk-grade → select → confirm → clean
```

Every step funnels through explicit safety gates — probes crash into visible
error rows, data lands in report-only, cleaning needs an explicit yes, and
dry-run rehearses with the disk untouched:

![lifecycle](https://raw.githubusercontent.com/Aeluris/CacheKat/main/docs/diagrams/lifecycle-en.png)

See [CHANGELOG.md](CHANGELOG.md) for details, [CONTRIBUTING.md](CONTRIBUTING.md)
to help, [AGENTS.md](AGENTS.md) for the engineering rulebook.

## License

[MIT](LICENSE) — © 2026 Aeluris
