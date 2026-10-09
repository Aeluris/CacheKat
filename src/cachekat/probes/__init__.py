"""Probes: one module per cache family. Import side effect = registration."""

from cachekat.probes import docker_df, npm_cache, pip_cache, playwright_cache

__all__ = ["docker_df", "npm_cache", "pip_cache", "playwright_cache"]
