"""Wspolne zaleznosci dla routerow /models."""

from venom_core.services.runtime_dependencies import (
    set_model_manager as _set_runtime_model_manager,
)

_model_manager = None
_model_registry = None


def set_dependencies(model_manager, model_registry=None):
    """Ustaw zaleznosci dla routerow modeli."""
    global _model_manager, _model_registry
    _model_manager = model_manager
    _model_registry = model_registry
    _set_runtime_model_manager(model_manager)


def get_model_manager():
    return _model_manager


def get_model_registry():
    return _model_registry
