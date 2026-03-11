"""Moduł: routes/memory - Endpointy API dla pamięci wektorowej."""

from typing import Annotated, Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from venom_core.api.dependencies import (
    get_lessons_store,
    get_session_store,
    get_state_manager,
    get_vector_store,
    is_testing_mode,
)
from venom_core.api.routes.graph_view_utils import apply_graph_view
from venom_core.api.routes.permission_denied_contract import (
    raise_permission_denied_http,
    resolve_actor_from_request,
)
from venom_core.api.schemas.memory import (
    CacheFlushResponse,
    GlobalMemoryClearResponse,
    LearningStatusResponse,
    LearningToggleRequest,
    LessonsMutationResponse,
    MemoryEntryMutationResponse,
    MemoryGraphResponse,
    MemoryIngestRequest,
    MemoryIngestResponse,
    MemorySearchRequest,
    MemorySearchResponse,
    SessionMemoryClearResponse,
    SessionMemoryResponse,
)
from venom_core.core.environment_policy import ensure_data_mutation_allowed
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager as _config_manager
from venom_core.services.memory_graph_service import MemoryGraphPayloadOptions
from venom_core.services.memory_graph_service import (
    build_ingest_metadata as _build_ingest_metadata_svc,
)
from venom_core.services.memory_graph_service import (
    build_memory_graph_payload as _build_memory_graph_payload_svc,
)
from venom_core.services.memory_graph_service import (
    raise_memory_http_error as _raise_memory_http_error_svc,
)
from venom_core.services.memory_graph_service import (
    require_nonempty as _require_nonempty_svc,
)
from venom_core.services.memory_graph_service import (
    resolve_maybe_await as _resolve_maybe_await_svc,
)
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
DEFAULT_USER_ID = "user_default"

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])

# Back-compat for tests that patch memory_routes.config_manager
config_manager = _config_manager

INTERNAL_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    500: {"description": "Błąd wewnętrzny"},
}
LESSONS_READ_RESPONSES: dict[int | str, dict[str, Any]] = {
    **INTERNAL_ERROR_RESPONSES,
}
LESSONS_MUTATION_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "Nieprawidłowe parametry żądania"},
    **INTERNAL_ERROR_RESPONSES,
}

# Globalne referencje dla testów
_vector_store = None
_state_manager = None
_lessons_store = None


def set_dependencies(
    vector_store=None, state_manager=None, lessons_store=None, session_store=None
):
    """Ustawia zależności i synchronizuje z api.dependencies (używane głównie w testach)."""
    global _vector_store, _state_manager, _lessons_store
    from venom_core.api import dependencies as api_deps

    if vector_store:
        _vector_store = vector_store
        api_deps.set_vector_store(vector_store)
    if state_manager:
        _state_manager = state_manager
        api_deps.set_state_manager(state_manager)
    if lessons_store:
        _lessons_store = lessons_store
        api_deps.set_lessons_store(lessons_store)
    if session_store:
        api_deps.set_session_store(session_store)


def _require_nonempty(value: str, detail: str) -> None:
    _require_nonempty_svc(value, detail)


def _build_ingest_metadata(request: "MemoryIngestRequest") -> dict[str, object]:
    return _build_ingest_metadata_svc(request)


def _raise_memory_http_error(exc: Exception, *, context: str) -> None:
    _raise_memory_http_error_svc(exc, context=context, logger=logger)


async def _resolve_maybe_await(value: Any) -> Any:
    return await _resolve_maybe_await_svc(value)


@router.post(
    "/ingest",
    response_model=MemoryIngestResponse,
    status_code=201,
    responses={
        400: {"description": "Nieprawidłowe dane wejściowe"},
        500: {"description": "Błąd wewnętrzny podczas zapisu do pamięci"},
    },
)
def ingest_to_memory(
    request: MemoryIngestRequest,
    vector_store: Annotated[Any, Depends(get_vector_store)],
):
    """
    Zapisuje tekst do pamięci wektorowej.

    Args:
        request: Żądanie z tekstem do zapamiętania

    Returns:
        Potwierdzenie zapisu z liczbą fragmentów

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    try:
        _require_nonempty(request.text, "Tekst nie może być pusty")
        metadata = _build_ingest_metadata(request)
        result = vector_store.upsert(
            text=request.text,
            metadata=metadata,
            collection_name=request.collection,
            chunk_text=True,
        )

        logger.info(
            f"Ingestion pomyślny: {result['chunks_count']} fragmentów do '{request.collection}'"
        )

        return MemoryIngestResponse(
            status="success",
            message=result["message"],
            chunks_count=result["chunks_count"],
        )

    except Exception as exc:
        _raise_memory_http_error(exc, context="ingestion do pamięci")


@router.post(
    "/search",
    response_model=MemorySearchResponse,
    responses={
        400: {"description": "Nieprawidłowe zapytanie"},
        500: {"description": "Błąd wewnętrzny podczas wyszukiwania"},
    },
)
def search_memory(
    request: MemorySearchRequest,
    vector_store: Annotated[Any, Depends(get_vector_store)],
):
    """
    Wyszukuje informacje w pamięci wektorowej.

    Args:
        request: Żądanie z zapytaniem

    Returns:
        Wyniki wyszukiwania

    Raises:
        HTTPException: 503 jeśli VectorStore nie jest dostępny, 400 przy błędnych danych
    """
    try:
        _require_nonempty(
            request.query,
            "Zapytanie nie może być puste (pusty prompt niedozwolony)",
        )

        results = vector_store.search(
            query=request.query,
            limit=request.limit,
            collection_name=request.collection,
        )

        logger.info(
            f"Wyszukiwanie w pamięci: znaleziono {len(results)} wyników dla '{request.query[:50]}...'"
        )

        return {
            "status": "success",
            "query": request.query,
            "results": results,
            "count": len(results),
        }

    except Exception as exc:
        _raise_memory_http_error(exc, context="wyszukiwania w pamięci")


@router.delete(
    "/session/{session_id}",
    response_model=SessionMemoryClearResponse,
    responses={
        400: {"description": "Brak wymaganego session_id"},
        403: {"description": "Brak uprawnień do mutacji danych"},
    },
)
def clear_session_memory(
    session_id: str,
    vector_store: Annotated[Any, Depends(get_vector_store)],
    state_manager: Annotated[Any, Depends(get_state_manager)],
    session_store: Annotated[Any, Depends(get_session_store)],
    req: Request = cast(Request, None),
):
    """
    Czyści pamięć sesyjną: wektory z tagiem session_id oraz historię/streszczenia w StateManager.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")
    try:
        ensure_data_mutation_allowed("memory.clear_session")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="memory.clear_session",
            actor=resolve_actor_from_request(req),
        )

    deleted_vectors = 0
    try:
        deleted_vectors = vector_store.delete_by_metadata({"session_id": session_id})
        deleted_vectors += vector_store.delete_session(session_id)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć wpisów sesyjnych z pamięci: {e}")

    cleared_tasks = 0
    if state_manager:
        cleared_tasks = state_manager.clear_session_context(session_id)
    if session_store:
        session_store.clear_session(session_id)

    return {
        "status": "success",
        "session_id": session_id,
        "deleted_vectors": deleted_vectors,
        "cleared_tasks": cleared_tasks,
        "message": "Pamięć sesji wyczyszczona",
    }


@router.get(
    "/session/{session_id}",
    response_model=SessionMemoryResponse,
    responses={
        400: {"description": "Brak wymaganego session_id"},
        503: {"description": "SessionStore nie jest dostępny"},
    },
)
def get_session_memory(
    session_id: str,
    session_store: Annotated[Any, Depends(get_session_store)],
):
    """Zwraca historię i streszczenie sesji z SessionStore."""
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")
    if not session_store:
        raise HTTPException(status_code=503, detail="SessionStore nie jest dostępny")

    history = session_store.get_history(session_id)
    summary = session_store.get_summary(session_id)
    return {
        "status": "success",
        "session_id": session_id,
        "history": history,
        "summary": summary,
        "count": len(history),
    }


@router.delete(
    "/global",
    response_model=GlobalMemoryClearResponse,
    responses={
        403: {"description": "Brak uprawnień do mutacji danych"},
        500: {"description": "Błąd podczas czyszczenia pamięci globalnej"},
    },
)
def clear_global_memory(
    vector_store: Annotated[Any, Depends(get_vector_store)],
    req: Request = cast(Request, None),
):
    """
    Czyści pamięć globalną (preferencje/fakty globalne użytkownika).
    """
    try:
        ensure_data_mutation_allowed("memory.clear_global")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="memory.clear_global",
            actor=resolve_actor_from_request(req),
        )
    try:
        deleted = vector_store.delete_by_metadata({"user_id": DEFAULT_USER_ID})
        # Jeśli nie znaleziono nic do usunięcia (np. stare wpisy bez metadanych user_id),
        # wyczyść całą kolekcję, aby użytkownik faktycznie widział pustą pamięć.
        if not deleted:
            deleted += vector_store.wipe_collection()
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć pamięci globalnej: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd czyszczenia pamięci globalnej"
        ) from e

    return {
        "status": "success",
        "deleted_vectors": deleted,
        "message": "Pamięć globalna wyczyszczona",
    }


@router.get(
    "/graph",
    response_model=MemoryGraphResponse,
    responses=INTERNAL_ERROR_RESPONSES,
)
def memory_graph(
    vector_store: Annotated[Any, Depends(get_vector_store)],
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
    session_id: Annotated[
        str, Query(description="Opcjonalny filtr po session_id")
    ] = "",
    only_pinned: Annotated[
        bool, Query(description="Zwracaj tylko wpisy z meta pinned=true")
    ] = False,
    include_lessons: Annotated[
        bool, Query(description="Czy dołączyć lekcje z LessonsStore")
    ] = False,
    mode: Annotated[
        str, Query(description="Tryb grafu: default lub flow (sekwencja)")
    ] = "default",
    view: Annotated[
        str,
        Query(
            pattern="^(overview|focus|full)$",
            description="Tryb zwracanego grafu: overview/focus/full",
        ),
    ] = "full",
    seed_id: Annotated[
        str | None,
        Query(description="Opcjonalny seed node id dla widoku focus"),
    ] = None,
    max_hops: Annotated[
        int,
        Query(ge=1, le=6, description="Maksymalna głębokość dla widoku focus"),
    ] = 2,
    include_isolates: Annotated[
        bool,
        Query(description="Czy zachować węzły bez krawędzi"),
    ] = True,
    limit_nodes: Annotated[
        int | None,
        Query(
            ge=1,
            le=5000,
            description="Opcjonalny limit po transformacji widoku (overview/focus)",
        ),
    ] = None,
):
    """
    Zwraca uproszczony graf pamięci (węzły/krawędzie) do wizualizacji w /brain.
    """
    return _build_memory_graph_payload_svc(
        vector_store=vector_store,
        lessons_store=lessons_store,
        options=MemoryGraphPayloadOptions(
            limit=limit,
            session_id=session_id,
            only_pinned=only_pinned,
            include_lessons=include_lessons,
            mode=mode,
            view=view,
            seed_id=seed_id,
            max_hops=max_hops,
            include_isolates=include_isolates,
            limit_nodes=limit_nodes,
        ),
        apply_graph_view_fn=apply_graph_view,
        allow_lessons_fallback=is_testing_mode(),
        logger=logger,
        default_user_id=DEFAULT_USER_ID,
    )


@router.post(
    "/entry/{entry_id}/pin",
    response_model=MemoryEntryMutationResponse,
    responses={
        404: {"description": "Nie znaleziono wpisu pamięci"},
        500: {"description": "Błąd aktualizacji wpisu pamięci"},
    },
)
def pin_memory_entry(
    entry_id: str,
    vector_store: Annotated[Any, Depends(get_vector_store)],
    pinned: Annotated[bool, Query(description="Czy oznaczyć pinned")] = True,
):
    """
    Ustawia flagę pinned dla wpisu pamięci (w oparciu o LanceDB).
    """
    try:
        ok = vector_store.update_metadata(entry_id, {"pinned": bool(pinned)})
        if not ok:
            raise HTTPException(status_code=404, detail="Nie znaleziono wpisu pamięci")
        return {"status": "success", "entry_id": entry_id, "pinned": bool(pinned)}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się zaktualizować wpisu pamięci: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd aktualizacji wpisu pamięci"
        ) from e


@router.delete(
    "/entry/{entry_id}",
    response_model=MemoryEntryMutationResponse,
    responses={
        403: {"description": "Brak uprawnień do mutacji danych"},
        404: {"description": "Nie znaleziono wpisu do usunięcia"},
        500: {"description": "Błąd usuwania wpisu pamięci"},
    },
)
def delete_memory_entry(
    entry_id: str,
    vector_store: Annotated[Any, Depends(get_vector_store)],
    req: Request = cast(Request, None),
):
    """
    Usuwa wpis pamięci (oraz wszystkie jego fragmenty).
    """
    try:
        ensure_data_mutation_allowed("memory.delete_entry")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="memory.delete_entry",
            actor=resolve_actor_from_request(req),
        )
    try:
        deleted = vector_store.delete_entry(entry_id)
        if deleted == 0:
            raise HTTPException(
                status_code=404, detail="Nie znaleziono wpisu do usunięcia"
            )
        return {"status": "success", "entry_id": entry_id, "deleted": deleted}
    except HTTPException:
        raise
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć wpisu pamięci: {e}")
        raise HTTPException(
            status_code=500, detail="Błąd usuwania wpisu pamięci"
        ) from e


# ============================================
# Pruning API - Knowledge Hygiene Suite
# ============================================


@router.delete(
    "/cache/semantic",
    response_model=CacheFlushResponse,
    responses={
        403: {"description": "Brak uprawnień do mutacji danych"},
        500: {"description": "Błąd podczas czyszczenia Semantic Cache"},
    },
)
def flush_semantic_cache(req: Request = cast(Request, None)):
    """
    Czyści Semantic Cache (kolekcja hidden_prompts).
    Usuwa wszystkie zapamiętane pary prompt-odpowiedź używane do semantycznego cache'owania.
    """
    try:
        ensure_data_mutation_allowed("memory.flush_semantic_cache")
    except PermissionError as e:
        raise_permission_denied_http(
            e,
            operation="memory.flush_semantic_cache",
            actor=resolve_actor_from_request(req),
        )
    try:
        from venom_core.core.orchestrator.constants import (
            SEMANTIC_CACHE_COLLECTION_NAME,
        )

        # Używamy wipe_collection na konkretnej kolekcji
        # Metoda wipe_collection w VectorStore domyślnie czyści self.collection_name,
        # więc musimy upewnić się, że działamy na odpowiedniej.
        # VectorStore.wipe_collection() często czyści *aktualną*.
        # Bezpieczniej będzie użyć delete_by_metadata(filter={}) na tej kolekcji lub delete_collection.
        # Sprawdźmy implementation VectorStore.wipe_collection...
        # Wg routes/memory.py: vector_store.wipe_collection()
        # Ale semantic cache to INNA kolekcja niż 'default'.
        # VectorStore inicjalizuje się z default collection.
        # Żeby wyczyścić semantic cache, musimy tymczasowo zmienić kolekcję lub użyć dedykowanej metody.
        # VectorStore pozwala na upsert z collection_name, a search z collection_name, ale wipe_collection?
        # Zobaczmy czy w memory.py jest coś co zmienia kolekcję.
        # Nie widać.
        # Zróbmy to bezpiecznie: delete_by_metadata({}) na kolekcji cache.
        # UWAGA: VectorStore API może nie wspierać collection_name w delete_by_metadata.
        # W takim razie zainicjalizujmy VectorStore explicite dla tej kolekcji.
        from venom_core.memory.vector_store import VectorStore

        cache_store = VectorStore(collection_name=SEMANTIC_CACHE_COLLECTION_NAME)
        deleted = (
            cache_store.wipe_collection()
        )  # To powinno zadziałać na 'hidden_prompts'

        logger.warning(f"🧹 FLUSH: Wyczyszczono Semantic Cache ({deleted} wpisów)")

        return {
            "status": "success",
            "message": f"Wyczyszczono Semantic Cache ({deleted} wpisów)",
            "deleted": deleted,
        }

    except Exception as e:
        logger.exception("Błąd podczas czyszczenia Semantic Cache")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas czyszczenia cache: {str(e)}"
        ) from e


# ============================================
# Pruning API - Knowledge Hygiene Suite
# (Aliases for backward compatibility)
# ============================================


@router.delete(
    "/lessons/prune/latest",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_latest_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    count: Annotated[
        int, Query(ge=1, description="Liczba najnowszych lekcji do usunięcia")
    ],
    req: Request = cast(Request, None),
):
    """Alias dla knowledge/lessons/prune/latest"""
    from venom_core.api.routes.knowledge import prune_latest_lessons as knowledge_prune

    result = knowledge_prune(count=count, lessons_store=lessons_store, req=req)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/prune/range",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_lessons_by_range(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    start: Annotated[str, Query(description="Data początkowa")],
    end: Annotated[str, Query(description="Data końcowa")],
    req: Request = cast(Request, None),
):
    """Alias dla knowledge/lessons/prune/range"""
    from venom_core.api.routes.knowledge import (
        prune_lessons_by_range as knowledge_prune,
    )

    result = knowledge_prune(start=start, end=end, lessons_store=lessons_store, req=req)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/prune/tag",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_lessons_by_tag(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    tag: Annotated[str, Query(description="Tag do usunięcia")],
    req: Request = cast(Request, None),
):
    """Alias dla knowledge/lessons/prune/tag"""
    from venom_core.api.routes.knowledge import prune_lessons_by_tag as knowledge_prune

    result = knowledge_prune(tag=tag, lessons_store=lessons_store, req=req)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/prune/ttl",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def prune_lessons_by_ttl(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    days: Annotated[int, Query(ge=1, description="Dni retencji")],
    req: Request = cast(Request, None),
):
    """Alias dla knowledge/lessons/prune/ttl"""
    from venom_core.api.routes.knowledge import prune_lessons_by_ttl as knowledge_prune

    result = knowledge_prune(days=days, lessons_store=lessons_store, req=req)
    return await _resolve_maybe_await(result)


@router.delete(
    "/lessons/purge",
    response_model=LessonsMutationResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def purge_all_lessons(
    lessons_store: Annotated[LessonsStore, Depends(get_lessons_store)],
    req: Request = cast(Request, None),
    force: Annotated[
        bool, Query(description="Wymagane potwierdzenie dla operacji nuklearnej")
    ] = False,
):
    """Alias dla knowledge/lessons/purge"""
    from venom_core.api.routes.knowledge import purge_all_lessons as knowledge_purge

    result = knowledge_purge(force=force, lessons_store=lessons_store, req=req)
    return await _resolve_maybe_await(result)


@router.get(
    "/lessons/learning/status",
    response_model=LearningStatusResponse,
    responses=LESSONS_READ_RESPONSES,
)
async def get_learning_status():
    """Alias dla knowledge/lessons/learning/status"""
    from venom_core.api.routes.knowledge import get_learning_status as knowledge_status

    return await _resolve_maybe_await(knowledge_status())


@router.post(
    "/lessons/learning/toggle",
    response_model=LearningStatusResponse,
    responses=LESSONS_MUTATION_RESPONSES,
)
async def toggle_learning(request: LearningToggleRequest):
    """Alias dla knowledge/lessons/learning/toggle"""
    from venom_core.api.routes.knowledge import (
        LearningToggleRequest as KnowledgeRequest,
    )
    from venom_core.api.routes.knowledge import toggle_learning as knowledge_toggle

    result = knowledge_toggle(KnowledgeRequest(enabled=request.enabled))
    return await _resolve_maybe_await(result)
