"""Shared dependencies for system-related routes."""

from __future__ import annotations

from typing import Any

_background_scheduler: Any = None
_service_monitor: Any = None
_state_manager: Any = None
_llm_controller: Any = None
_model_manager: Any = None
_request_tracer: Any = None
_hardware_bridge: Any = None


def set_dependencies(
    background_scheduler,
    service_monitor,
    state_manager=None,
    llm_controller=None,
    model_manager=None,
    request_tracer=None,
    hardware_bridge=None,
) -> None:
    global \
        _background_scheduler, \
        _service_monitor, \
        _state_manager, \
        _llm_controller, \
        _model_manager, \
        _request_tracer, \
        _hardware_bridge
    _background_scheduler = background_scheduler
    _service_monitor = service_monitor
    _state_manager = state_manager
    _llm_controller = llm_controller
    _model_manager = model_manager
    _request_tracer = request_tracer
    _hardware_bridge = hardware_bridge


def get_background_scheduler():
    return _background_scheduler


def get_service_monitor():
    return _service_monitor


def get_state_manager():
    return _state_manager


def get_llm_controller():
    return _llm_controller


def get_model_manager():
    return _model_manager


def get_request_tracer():
    return _request_tracer


def get_hardware_bridge():
    return _hardware_bridge
