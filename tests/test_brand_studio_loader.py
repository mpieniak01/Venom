from __future__ import annotations

import types

from venom_core.api.schemas.brand_studio import ContentCandidate
from venom_core.services import brand_studio_loader as loader


class _Settings:
    BRAND_STUDIO_MODE = "disabled"
    BRAND_STUDIO_EXTENSION_MODULE = ""


def test_loader_returns_none_when_disabled():
    settings = _Settings()
    settings.BRAND_STUDIO_MODE = "disabled"
    loader.reset_brand_studio_provider_cache()
    assert loader.get_brand_studio_provider(settings) is None


def test_loader_returns_stub_for_stub_mode():
    settings = _Settings()
    settings.BRAND_STUDIO_MODE = "stub"
    loader.reset_brand_studio_provider_cache()
    provider = loader.get_brand_studio_provider(settings)
    assert provider is not None
    candidates = provider.list_candidates(limit=2, min_score=0.0)
    assert candidates
    assert isinstance(candidates[0], ContentCandidate)


def test_loader_falls_back_to_stub_when_extension_missing():
    settings = _Settings()
    settings.BRAND_STUDIO_MODE = "extension"
    settings.BRAND_STUDIO_EXTENSION_MODULE = "missing.module.path"
    loader.reset_brand_studio_provider_cache()
    provider = loader.get_brand_studio_provider(settings)
    assert provider is not None
    assert provider.list_candidates(limit=1)


def test_loader_uses_extension_module_provider(monkeypatch):
    class _Provider:
        def list_candidates(self, **kwargs):
            _ = kwargs
            return []

        def generate_drafts(self, **kwargs):
            _ = kwargs
            raise NotImplementedError

        def queue_draft(self, **kwargs):
            _ = kwargs
            raise NotImplementedError

        def publish(self, **kwargs):
            _ = kwargs
            raise NotImplementedError

        def list_queue(self):
            return []

        def list_audit(self):
            return []

    module = types.ModuleType("brand_ext_ok")
    module.create_provider = lambda: _Provider()

    def _fake_import(name: str):
        if name == "brand_ext_ok":
            return module
        raise ImportError(name)

    monkeypatch.setattr(loader.importlib, "import_module", _fake_import)

    settings = _Settings()
    settings.BRAND_STUDIO_MODE = "extension"
    settings.BRAND_STUDIO_EXTENSION_MODULE = "brand_ext_ok"

    loader.reset_brand_studio_provider_cache()
    provider = loader.get_brand_studio_provider(settings)
    assert isinstance(provider, _Provider)
