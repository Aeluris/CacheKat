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
DOCKER_IMAGES = "docker/images-reclaimable"
DOCKER_BUILD_CACHE = "docker/build-cache"
DOCKER_CONTAINER_PREFIX = "docker/container/"
DOCKER_DAEMON = "docker/daemon"
DOCKER_PS_ERROR = "docker/ps-error"
