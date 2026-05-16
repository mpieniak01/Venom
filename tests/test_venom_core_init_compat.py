from __future__ import annotations

import importlib
import types
import warnings


def _reload_venom_core_with_import_hook(fake_import_module):
    original_import_module = importlib.import_module
    importlib.import_module = fake_import_module  # type: ignore[assignment]
    try:
        import venom_core

        return importlib.reload(venom_core)
    finally:
        importlib.import_module = original_import_module  # type: ignore[assignment]


def test_venom_core_init_applies_compat_symbols() -> None:
    class _AnyUrl:
        pass

    class _Omit:
        pass

    fake_networks = types.SimpleNamespace()
    fake_openai_types = types.SimpleNamespace(Omit=_Omit)

    def _fake_import(name: str, package: str | None = None):
        if name == "pydantic.networks":
            return fake_networks
        if name == "pydantic":
            return types.SimpleNamespace(AnyUrl=_AnyUrl)
        if name == "openai._types":
            return fake_openai_types
        return importlib.__import__(name, fromlist=["*"])

    _reload_venom_core_with_import_hook(_fake_import)

    assert hasattr(fake_networks, "Url")
    assert isinstance(fake_openai_types.omit, _Omit)


def test_venom_core_init_warns_on_import_failures() -> None:
    def _fake_import(name: str, package: str | None = None):
        if name in {"pydantic.networks", "openai._types"}:
            raise ModuleNotFoundError(name)
        return importlib.__import__(name, fromlist=["*"])

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        _reload_venom_core_with_import_hook(_fake_import)

    messages = [str(item.message) for item in caught]
    assert any("pydantic Url compatibility patch skipped" in msg for msg in messages)
    assert any("openai omit compatibility patch skipped" in msg for msg in messages)
