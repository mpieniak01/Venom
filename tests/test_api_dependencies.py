"""Tests for API dependency helpers."""

import pytest

from venom_core.api import dependencies as deps


@pytest.fixture(autouse=True)
def clear_dependency_caches():
    deps.get_orchestrator.cache_clear()
    deps.get_state_manager.cache_clear()
    deps.get_vector_store.cache_clear()
    deps.get_graph_store.cache_clear()
    deps.get_lessons_store.cache_clear()
    deps.set_orchestrator(None)
    deps.set_state_manager(None)
    deps.set_vector_store(None)
    deps.set_graph_store(None)
    deps.set_lessons_store(None)
    yield
    deps.get_orchestrator.cache_clear()
    deps.get_state_manager.cache_clear()
    deps.get_vector_store.cache_clear()
    deps.get_graph_store.cache_clear()
    deps.get_lessons_store.cache_clear()


def test_getters_raise_when_missing():
    with pytest.raises(RuntimeError):
        deps.get_orchestrator()
    with pytest.raises(RuntimeError):
        deps.get_state_manager()
    with pytest.raises(RuntimeError):
        deps.get_vector_store()
    with pytest.raises(RuntimeError):
        deps.get_graph_store()
    with pytest.raises(RuntimeError):
        deps.get_lessons_store()


def test_setters_and_getters_return_instances():
    orchestrator = object()
    state_manager = object()
    vector_store = object()
    graph_store = object()
    lessons_store = object()

    deps.set_orchestrator(orchestrator)
    deps.set_state_manager(state_manager)
    deps.set_vector_store(vector_store)
    deps.set_graph_store(graph_store)
    deps.set_lessons_store(lessons_store)

    assert deps.get_orchestrator() is orchestrator
    assert deps.get_state_manager() is state_manager
    assert deps.get_vector_store() is vector_store
    assert deps.get_graph_store() is graph_store
    assert deps.get_lessons_store() is lessons_store
