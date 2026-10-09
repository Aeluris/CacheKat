from __future__ import annotations

import pytest

from cachekat.i18n import _STRINGS, resolve_lang, set_lang, t


@pytest.fixture(autouse=True)
def _restore_en():
    yield
    set_lang("en")  # global i18n state must not leak into other test modules


def test_every_key_has_en_and_zh():
    # the bilingual contract: one missing side is a broken key
    for key, entry in _STRINGS.items():
        assert entry.get("en"), key
        assert entry.get("zh"), key


def test_t_switches_and_formats():
    set_lang("zh")
    assert t("confirm_title", verb="X", n=2, size="1 B") == "X 2 项，约 1 B："
    set_lang("en")
    assert t("confirm_title", verb="X", n=2, size="1 B") == "X 2 items, ~1 B:"


def test_t_missing_key_fails_loudly():
    with pytest.raises(KeyError):
        t("no_such_key_ever")


def test_resolve_lang_explicit_and_env(monkeypatch):
    assert resolve_lang("zh") == "zh"
    assert resolve_lang("en") == "en"
    monkeypatch.setenv("LANG", "zh_CN.UTF-8")
    assert resolve_lang("auto") == "zh"
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    assert resolve_lang("auto") == "en"


def test_consequence_bilingual_warning_intact():
    # hard requirement from the 2026-10-08 incident, in BOTH languages:
    # the container warning must say container-itself, not cache
    from cachekat.actions import consequence
    from cachekat.models import Finding, Risk

    f = Finding("docker/container/x", "c", 1, "d", Risk.CLEANABLE)
    assert "CONTAINER ITSELF" in consequence(f)
    set_lang("zh")
    assert "容器本体" in consequence(f)
