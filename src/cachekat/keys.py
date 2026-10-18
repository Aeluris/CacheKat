"""Finding-key contract — the single source of every key string.

Probes emit these keys; actions dispatch on them; the TUI passes them as
selection values. src code MUST use these constants — no fresh literals.
Tests intentionally pin the literal strings (contract tests: if a key ever
changes, tests fail loudly rather than silently following the constant).
"""

from __future__ import annotations

PIP_CACHE = "pip/cache"
NPM_CACHE = "npm/cache"

PLAYWRIGHT_PREFIX = "playwright/"
PLAYWRIGHT_BROWSERS = "playwright/browsers"

DOCKER_VOLUMES = "docker/volumes"
DOCKER_BUILD_CACHE = "docker/build-cache"
DOCKER_CONTAINER_PREFIX = "docker/container/"
# per-image: <short-id> is appended (hex, no "/" — same strip-prefix
# contract as containers). "unused images" become individually selectable,
# replacing the old blanket report-only aggregate.
DOCKER_IMAGE_PREFIX = "docker/image/"
DOCKER_IMAGES_ERROR = "docker/images-error"
DOCKER_DAEMON = "docker/daemon"
DOCKER_PS_ERROR = "docker/ps-error"

# Docker Desktop WSL2 disk (ext4.vhdx). REPORT_ONLY forever: the file is
# the docker store itself — we report size and hand out compact COMMANDS
# (see cli.py `vhdx`), the tool never touches it.
WSL_VHDX_PREFIX = "wsl/vhdx/"
WSL_VHDX_DOCKER_DATA = "wsl/vhdx/docker_data"  # %LOCALAPPDATA%\Docker\wsl\disk\
WSL_VHDX_EXT4 = "wsl/vhdx/ext4"  # %LOCALAPPDATA%\Docker\data\ (legacy layout)
