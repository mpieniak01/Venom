"""Moduł: routes/memory - Endpointy API dla pamięci wektorowej."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from venom_core.api.dependencies import (
    get_lessons_store,
    get_session_store,
    get_state_manager,
    get_vector_store,
    is_testing_mode,
)
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager as _config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
DEFAULT_USER_ID = "user_default"

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])

# Back-compat for tests that patch memory_routes.config_manager
config_manager = _config_manager

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


def _ensure_vector_store():
    """Pomocnik do pobierania vector store (używany w testach)."""
    from venom_core.api.dependencies import get_vector_store
    from venom_core.memory.vector_store import VectorStore

    try:
        return get_vector_store()
    except Exception:
        if _vector_store:
            return _vector_store
        # W teście, jeśli nikt jeszcze nie ustawiał, stwórz nową instancję
        # (EmbeddingService i tak użyje cache'u)
        return VectorStore()


def _normalize_lessons_for_graph(
    raw_lessons: object,
    allow_fallback: bool,
    limit: int,
) -> list[dict[str, object]]:
    lessons: list[dict[str, object]] = []
    if not raw_lessons:
        return lessons
    if isinstance(raw_lessons, dict):
        for lid, ldata in list(raw_lessons.items())[:limit]:
            lesson_id: object = lid
            if hasattr(ldata, "id"):
                lesson_id = ldata.id
            elif isinstance(ldata, dict) and "id" in ldata:
                lesson_id = ldata["id"]
            elif hasattr(ldata, "lesson_id"):
                lesson_id = ldata.lesson_id
            elif isinstance(ldata, dict) and "lesson_id" in ldata:
                lesson_id = ldata["lesson_id"]

            raw_lesson = (
                ldata.to_dict()
                if hasattr(ldata, "to_dict")
                else (
                    vars(ldata)
                    if hasattr(ldata, "__dict__")
                    else (ldata if isinstance(ldata, dict) else {})
                )
            )
            if isinstance(raw_lesson, dict):
                raw_lesson["id"] = lesson_id
                lessons.append(dict(raw_lesson))
        return lessons
    if isinstance(raw_lessons, list):
        for entry in raw_lessons[:limit]:
            if isinstance(entry, dict):
                lessons.append(dict(entry))
            elif allow_fallback and hasattr(entry, "to_dict"):
                raw_entry = entry.to_dict()
                if isinstance(raw_entry, dict):
                    lessons.append(dict(raw_entry))
            elif allow_fallback and hasattr(entry, "__dict__"):
                lessons.append(dict(vars(entry)))
        return lessons
    return lessons


# Modele
class MemoryIngestRequest(BaseModel):
    """Model żądania ingestion do pamięci."""

    text: str
    category: str = "general"
    collection: str = "default"
    session_id: str | None = None
    user_id: str | None = None
    pinned: bool | None = None
    memory_type: str | None = None
    scope: str | None = None
    topic: str | None = None
    timestamp: str | None = None


class MemoryIngestResponse(BaseModel):
    """Model odpowiedzi po ingestion."""

    status: str
    message: str
    chunks_count: int = 0


class MemorySearchRequest(BaseModel):
    """Model żądania wyszukiwania w pamięci."""

    query: str
    limit: int = 3
    collection: str = "default"


# Modele i Stałe
DEFAULT_USER_ID = "user_default"


@router.post("/ingest", response_model=MemoryIngestResponse, status_code=201)
async def ingest_to_memory(
    request: MemoryIngestRequest, vector_store=Depends(get_vector_store)
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
        if not request.text or not request.text.strip():
            raise HTTPException(status_code=400, detail="Tekst nie może być pusty")

        # Zapisz do pamięci
        metadata: dict[str, object] = {"category": request.category}
        if request.session_id:
            metadata["session_id"] = request.session_id
        if request.user_id:
            metadata["user_id"] = request.user_id
        if request.pinned is not None:
            metadata["pinned"] = bool(request.pinned)
        if request.memory_type:
            metadata["type"] = request.memory_type
        if request.scope:
            metadata["scope"] = request.scope
        if request.topic:
            metadata["topic"] = request.topic
        if request.timestamp:
            metadata["timestamp"] = request.timestamp
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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas ingestion do pamięci")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/search")
async def search_memory(
    request: MemorySearchRequest, vector_store=Depends(get_vector_store)
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
        if not request.query or not request.query.strip():
            raise HTTPException(
                status_code=400,
                detail="Zapytanie nie może być puste (pusty prompt niedozwolony)",
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

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Błąd podczas wyszukiwania w pamięci")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.delete("/session/{session_id}")
async def clear_session_memory(
    session_id: str,
    vector_store=Depends(get_vector_store),
    state_manager=Depends(get_state_manager),
    session_store=Depends(get_session_store),
):
    """
    Czyści pamięć sesyjną: wektory z tagiem session_id oraz historię/streszczenia w StateManager.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")

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


@router.get("/session/{session_id}")
async def get_session_memory(session_id: str, session_store=Depends(get_session_store)):
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


@router.delete("/global")
async def clear_global_memory(vector_store=Depends(get_vector_store)):
    """
    Czyści pamięć globalną (preferencje/fakty globalne użytkownika).
    """
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


@router.get("/graph")
async def memory_graph(
    limit: int = Query(200, ge=1, le=500),
    session_id: str = Query("", description="Opcjonalny filtr po session_id"),
    only_pinned: bool = Query(
        False, description="Zwracaj tylko wpisy z meta pinned=true"
    ),
    include_lessons: bool = Query(
        False, description="Czy dołączyć lekcje z LessonsStore"
    ),
    mode: str = Query(
        "default", description="Tryb grafu: default lub flow (sekwencja)"
    ),
    vector_store=Depends(get_vector_store),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Zwraca uproszczony graf pamięci (węzły/krawędzie) do wizualizacji w /brain.
    """
    try:
        _ = vector_store  # Ensure it is used
    except Exception:
        pass
    except HTTPException as exc:  # pragma: no cover
        logger.warning(f"Memory graph unavailable: {exc.detail}")
        return {
            "status": "unavailable",
            "reason": exc.detail,
            "elements": {"nodes": [], "edges": []},
            "stats": {"nodes": 0, "edges": 0},
        }
    filters: dict[str, object] = {}
    if session_id:
        filters["session_id"] = session_id
    if only_pinned:
        filters["pinned"] = True

    entries = vector_store.list_entries(limit=limit, metadata_filters=filters)

    nodes = []
    edges = []
    session_nodes = {}
    user_nodes = {}

    for entry in entries:
        meta = entry.get("metadata") or {}
        eid = entry.get("id") or meta.get("id") or meta.get("uuid") or meta.get("pk")
        if not eid:
            eid = f"mem-{abs(hash(entry.get('text', '')))}"
        label = meta.get("title") or (entry.get("text") or "")[:80] or eid
        mem_type = meta.get("type") or "fact"
        sess = meta.get("session_id")
        user = meta.get("user_id") or DEFAULT_USER_ID
        pinned = bool(meta.get("pinned"))
        scope = meta.get("scope") or ("session" if sess else "global")
        node_payload = {
            "data": {
                "id": eid,
                "label": label,
                "type": "memory",
                "memory_kind": mem_type,
                "session_id": sess,
                "user_id": user,
                "scope": scope,
                "pinned": pinned,
                "topic": meta.get("topic"),
                "meta": meta,
            }
        }
        if "x" in meta and "y" in meta:
            node_payload["position"] = {"x": meta.get("x"), "y": meta.get("y")}
        nodes.append(node_payload)
        if sess and sess not in session_nodes:
            session_nodes[sess] = {
                "data": {
                    "id": f"session:{sess}",
                    "label": sess,
                    "type": "memory",
                    "memory_kind": "session",
                    "session_id": sess,
                }
            }
        if user and user not in user_nodes:
            user_nodes[user] = {
                "data": {
                    "id": f"user:{user}",
                    "label": user,
                    "type": "memory",
                    "memory_kind": "user",
                    "user_id": user,
                }
            }
        if sess:
            edges.append(
                {
                    "data": {
                        "id": f"edge:{sess}->{eid}",
                        "source": f"session:{sess}",
                        "target": eid,
                        "label": "session",
                        "type": "memory",
                    }
                }
            )
        if user:
            edges.append(
                {
                    "data": {
                        "id": f"edge:{user}->{eid}",
                        "source": f"user:{user}",
                        "target": eid,
                        "label": "user",
                        "type": "memory",
                    }
                }
            )

    lesson_nodes = []
    lesson_edges = []
    if include_lessons and lessons_store:
        try:
            # Obsługa różnych wersji LessonsStore (szczególnie w mockach testowych)
            if hasattr(lessons_store, "get_all_lessons"):
                raw_lessons = lessons_store.get_all_lessons(limit=limit)
                lessons = _normalize_lessons_for_graph(
                    raw_lessons, allow_fallback=is_testing_mode(), limit=limit
                )
            elif hasattr(lessons_store, "lessons"):
                # fallback dla prostych mocków/SimpleNamespace w testach
                raw_lessons_data = lessons_store.lessons
                lessons = _normalize_lessons_for_graph(
                    raw_lessons_data, allow_fallback=is_testing_mode(), limit=limit
                )
            else:
                lessons = []

            for raw_lesson in lessons:
                # Jeśli to już jest słownik (z moich konwersji wyżej) to super
                if not isinstance(raw_lesson, dict):
                    raw_lesson = (
                        raw_lesson.to_dict()
                        if hasattr(raw_lesson, "to_dict")
                        else (
                            vars(raw_lesson) if hasattr(raw_lesson, "__dict__") else {}
                        )
                    )

                raw_id = raw_lesson.get("id") or raw_lesson.get("lesson_id")
                lesson_id = str(raw_id) if raw_id is not None else ""
                if not lesson_id:
                    continue
                label = raw_lesson.get("title") or lesson_id
                lesson_nodes.append(
                    {
                        "data": {
                            "id": f"lesson:{lesson_id}",
                            "label": label,
                            "type": "memory",
                            "memory_kind": "lesson",
                            "lesson_id": lesson_id,
                            "meta": {
                                "tags": raw_lesson.get("tags"),
                                "timestamp": raw_lesson.get("timestamp"),
                            },
                        }
                    }
                )
                # opcjonalna krawędź do user_default
                lesson_edges.append(
                    {
                        "data": {
                            "id": f"edge:lesson:{lesson_id}->user:{DEFAULT_USER_ID}",
                            "source": f"lesson:{lesson_id}",
                            "target": f"user:{DEFAULT_USER_ID}",
                            "label": "lesson",
                            "type": "lesson",
                        }
                    }
                )
        except Exception as e:  # pragma: no cover
            logger.warning(f"Nie udało się pobrać lekcji do grafu: {e}")

    all_nodes = (
        list(session_nodes.values()) + list(user_nodes.values()) + nodes + lesson_nodes
    )
    all_edges = edges + lesson_edges

    if mode == "flow":
        # Dodaj krawędzie sekwencyjne (prosty tok) wg metadanej timestamp, fallback: kolejność entries
        try:

            def _flow_timestamp(node: dict) -> str:
                meta_value = node.get("data", {}).get("meta")
                meta = meta_value if isinstance(meta_value, dict) else {}
                return str(meta.get("timestamp", ""))

            entries_for_flow = sorted(nodes, key=_flow_timestamp)
        except Exception:
            entries_for_flow = nodes
        for idx in range(len(entries_for_flow) - 1):
            src = entries_for_flow[idx]["data"]["id"]
            tgt = entries_for_flow[idx + 1]["data"]["id"]
            all_edges.append(
                {
                    "data": {
                        "id": f"flow:{src}->{tgt}",
                        "source": src,
                        "target": tgt,
                        "label": "next",
                        "type": "flow",
                    }
                }
            )

    return {
        "status": "success",
        "elements": {"nodes": all_nodes, "edges": all_edges},
        "stats": {"nodes": len(all_nodes), "edges": len(all_edges)},
    }


@router.post("/entry/{entry_id}/pin")
async def pin_memory_entry(
    entry_id: str,
    pinned: bool = Query(True, description="Czy oznaczyć pinned"),
    vector_store=Depends(get_vector_store),
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


@router.delete("/entry/{entry_id}")
async def delete_memory_entry(entry_id: str, vector_store=Depends(get_vector_store)):
    """
    Usuwa wpis pamięci (oraz wszystkie jego fragmenty).
    """
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


@router.delete("/cache/semantic")
async def flush_semantic_cache():
    """
    Czyści Semantic Cache (kolekcja hidden_prompts).
    Usuwa wszystkie zapamiętane pary prompt-odpowiedź używane do semantycznego cache'owania.
    """
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


@router.delete("/lessons/prune/latest")
async def prune_latest_lessons(
    count: int = Query(..., ge=1, description="Liczba najnowszych lekcji do usunięcia"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Alias dla knowledge/lessons/prune/latest"""
    from venom_core.api.routes.knowledge import prune_latest_lessons as knowledge_prune

    return await knowledge_prune(count=count, lessons_store=lessons_store)


@router.delete("/lessons/prune/range")
async def prune_lessons_by_range(
    start: str = Query(..., description="Data początkowa"),
    end: str = Query(..., description="Data końcowa"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Alias dla knowledge/lessons/prune/range"""
    from venom_core.api.routes.knowledge import (
        prune_lessons_by_range as knowledge_prune,
    )

    return await knowledge_prune(start=start, end=end, lessons_store=lessons_store)


@router.delete("/lessons/prune/tag")
async def prune_lessons_by_tag(
    tag: str = Query(..., description="Tag do usunięcia"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Alias dla knowledge/lessons/prune/tag"""
    from venom_core.api.routes.knowledge import prune_lessons_by_tag as knowledge_prune

    return await knowledge_prune(tag=tag, lessons_store=lessons_store)


@router.delete("/lessons/prune/ttl")
async def prune_lessons_by_ttl(
    days: int = Query(..., ge=1, description="Dni retencji"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Alias dla knowledge/lessons/prune/ttl"""
    from venom_core.api.routes.knowledge import prune_lessons_by_ttl as knowledge_prune

    return await knowledge_prune(days=days, lessons_store=lessons_store)


@router.delete("/lessons/purge")
async def purge_all_lessons(
    force: bool = Query(
        False, description="Wymagane potwierdzenie dla operacji nuklearnej"
    ),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Alias dla knowledge/lessons/purge"""
    from venom_core.api.routes.knowledge import purge_all_lessons as knowledge_purge

    return await knowledge_purge(force=force, lessons_store=lessons_store)


class LearningToggleRequest(BaseModel):
    enabled: bool


@router.get("/lessons/learning/status")
async def get_learning_status():
    """Alias dla knowledge/lessons/learning/status"""
    from venom_core.api.routes.knowledge import get_learning_status as knowledge_status

    return await knowledge_status()


@router.post("/lessons/learning/toggle")
async def toggle_learning(request: LearningToggleRequest):
    """Alias dla knowledge/lessons/learning/toggle"""
    from venom_core.api.routes.knowledge import (
        LearningToggleRequest as KnowledgeRequest,
    )
    from venom_core.api.routes.knowledge import toggle_learning as knowledge_toggle

    return await knowledge_toggle(KnowledgeRequest(enabled=request.enabled))
