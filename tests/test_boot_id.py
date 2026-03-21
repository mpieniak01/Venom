"""Regression tests for stable boot id across process environment."""

from __future__ import annotations

import importlib

import venom_core.utils.boot_id as boot_id_module


def test_boot_id_uses_environment_value(monkeypatch):
    monkeypatch.setenv("VENOM_BOOT_ID", "env-boot-id")

    reloaded = importlib.reload(boot_id_module)

    assert reloaded.BOOT_ID == "env-boot-id"


def test_boot_id_initializes_environment_when_missing(monkeypatch):
    monkeypatch.delenv("VENOM_BOOT_ID", raising=False)

    reloaded = importlib.reload(boot_id_module)

    assert reloaded.BOOT_ID
    assert reloaded.BOOT_ID == reloaded.os.environ["VENOM_BOOT_ID"]
