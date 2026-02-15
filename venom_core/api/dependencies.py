"""Moduł: dependencies - Wstrzykiwanie zależności dla FastAPI."""

import os
from functools import lru_cache
from typing import Optional

from venom_core.core.orchestrator import Orchestrator
from venom_core.core.state_manager import StateManager
from venom_core.core.tracer import RequestTracer
from venom_core.memory.graph_store import CodeGraphStore
from venom_core.memory.lessons_store import LessonsStore
from venom_core.memory.vector_store import VectorStore
from venom_core.services.session_store import SessionStore


def is_testing_mode() -> bool:
    """Sprawdza dynamicznie, czy Venom działa w trybie testowym."""
    return bool(os.getenv("PYTEST_CURRENT_TEST"))


# Globalne referencje do serwisów (inicjalizowane w lifespan)
_orchestrator: Optional[Orchestrator] = None
_state_manager: Optional[StateManager] = None
_vector_store: Optional[VectorStore] = None
_graph_store: Optional[CodeGraphStore] = None
_lessons_store: Optional[LessonsStore] = None
_session_store: Optional[SessionStore] = None
_request_tracer: Optional[RequestTracer] = None


def set_orchestrator(orchestrator: Orchestrator):
    """Ustaw globalną instancję orchestratora."""
    global _orchestrator
    _orchestrator = orchestrator
    get_orchestrator.cache_clear()


def set_state_manager(state_manager: StateManager):
    """Ustaw globalną instancję state managera."""
    global _state_manager
    _state_manager = state_manager
    get_state_manager.cache_clear()


def set_vector_store(vector_store: VectorStore):
    """Ustaw globalną instancję vector store."""
    global _vector_store
    _vector_store = vector_store
    get_vector_store.cache_clear()


def set_graph_store(graph_store: CodeGraphStore):
    """Ustaw globalną instancję graph store."""
    global _graph_store
    _graph_store = graph_store
    get_graph_store.cache_clear()


def set_lessons_store(lessons_store: LessonsStore):
    """Ustaw globalną instancję lessons store."""
    global _lessons_store
    _lessons_store = lessons_store
    get_lessons_store.cache_clear()


def set_session_store(session_store: SessionStore):
    """Ustaw globalną instancję session store."""
    global _session_store
    _session_store = session_store
    get_session_store.cache_clear()


def set_request_tracer(request_tracer: RequestTracer):
    """Ustaw globalną instancję request tracer."""
    global _request_tracer
    _request_tracer = request_tracer
    get_request_tracer.cache_clear()


@lru_cache()
def get_orchestrator() -> Orchestrator:
    """
    Pobierz instancję Orchestratora (dependency injection).

    Returns:
        Orchestrator: Instancja orchestratora

    Raises:
        RuntimeError: Jeśli orchestrator nie został zainicjalizowany
    """
    if _orchestrator is None:
        raise RuntimeError("Orchestrator nie jest dostępny")
    return _orchestrator


@lru_cache()
def get_state_manager() -> StateManager:
    """
    Pobierz instancję StateManager (dependency injection).

    Returns:
        StateManager: Instancja state managera

    Raises:
        RuntimeError: Jeśli state manager nie został zainicjalizowany
    """
    global _state_manager
    if _state_manager is None:
        if is_testing_mode():
            _state_manager = StateManager()
        else:
            raise RuntimeError("StateManager nie jest dostępny")
    return _state_manager


@lru_cache()
def get_vector_store() -> VectorStore:
    """
    Pobierz instancję VectorStore (dependency injection).

    Returns:
        VectorStore: Instancja vector store

    Raises:
        RuntimeError: Jeśli vector store nie został zainicjalizowany
    """
    global _vector_store
    if _vector_store is None:
        if is_testing_mode():
            _vector_store = VectorStore()
        else:
            raise RuntimeError("VectorStore nie jest dostępny")
    return _vector_store


@lru_cache()
def get_graph_store() -> CodeGraphStore:
    """
    Pobierz instancję CodeGraphStore (dependency injection).

    Returns:
        CodeGraphStore: Instancja graph store

    Raises:
        RuntimeError: Jeśli graph store nie został zainicjalizowany
    """
    global _graph_store
    if _graph_store is None:
        if is_testing_mode():
            _graph_store = CodeGraphStore()
        else:
            raise RuntimeError("CodeGraphStore nie jest dostępny")
    return _graph_store


@lru_cache()
def get_lessons_store() -> LessonsStore:
    """
    Pobierz instancję LessonsStore (dependency injection).

    Returns:
        LessonsStore: Instancja lessons store

    Raises:
        RuntimeError: Jeśli lessons store nie został zainicjalizowany
    """
    global _lessons_store
    if _lessons_store is None:
        if is_testing_mode():
            vs = get_vector_store()
            _lessons_store = LessonsStore(vector_store=vs)
        else:
            raise RuntimeError("LessonsStore nie jest dostępny")
    return _lessons_store


@lru_cache()
def get_session_store() -> SessionStore:
    """
    Pobierz instancję SessionStore (dependency injection).

    Returns:
        SessionStore: Instancja session store

    Raises:
        RuntimeError: Jeśli session store nie został zainicjalizowany
    """
    global _session_store
    if _session_store is None:
        if is_testing_mode():
            _session_store = SessionStore()
        else:
            raise RuntimeError("SessionStore nie jest dostępny")
    return _session_store


@lru_cache()
def get_request_tracer() -> RequestTracer:
    """
    Pobierz instancję RequestTracer (dependency injection).

    Returns:
        RequestTracer: Instancja request tracer

    Raises:
        RuntimeError: Jeśli request tracer nie został zainicjalizowany
    """
    global _request_tracer
    if _request_tracer is None:
        if is_testing_mode():
            _request_tracer = RequestTracer()
        else:
            raise RuntimeError("RequestTracer nie jest dostępny")
    return _request_tracer
