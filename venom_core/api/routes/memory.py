"""Moduł: routes/memory - Endpointy API dla pamięci wektorowej."""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from venom_core.api.dependencies import get_lessons_store
from venom_core.config import SETTINGS
from venom_core.memory.lessons_store import LessonsStore
from venom_core.services.config_manager import config_manager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)
DEFAULT_USER_ID = "user_default"

router = APIRouter(prefix="/api/v1/memory", tags=["memory"])


# Modele
class MemoryIngestRequest(BaseModel):
    """Model żądania ingestion do pamięci."""

    text: str
    category: str = "general"
    collection: str = "default"


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


# Dependency - będzie ustawione w main.py
_vector_store = None
_state_manager = None
_lessons_store = None
_embedding_service = None


def set_dependencies(vector_store, state_manager=None, lessons_store=None):
    """Ustaw zależności dla routera."""
    global _vector_store, _state_manager, _lessons_store, _embedding_service
    _vector_store = vector_store
    _state_manager = state_manager
    _lessons_store = lessons_store
    try:
        _embedding_service = vector_store.embedding_service
    except Exception:
        _embedding_service = None


def _ensure_vector_store():
    global _vector_store
    if _vector_store is not None:
        return _vector_store
    try:
        from venom_core.memory.vector_store import VectorStore

        _vector_store = VectorStore()
        logger.info("VectorStore zainicjalizowany leniwie w API")
    except Exception as e:
        logger.warning(f"Nie udało się zainicjalizować VectorStore: {e}")
        raise HTTPException(
            status_code=503,
            detail="VectorStore nie jest dostępny. Upewnij się, że dependencies są zainstalowane.",
        ) from e
    return _vector_store


@router.post("/ingest", response_model=MemoryIngestResponse, status_code=201)
async def ingest_to_memory(request: MemoryIngestRequest):
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

        vector_store = _ensure_vector_store()

        # Zapisz do pamięci
        metadata = {"category": request.category}
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
async def search_memory(request: MemorySearchRequest):
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

        vector_store = _ensure_vector_store()

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
async def clear_session_memory(session_id: str):
    """
    Czyści pamięć sesyjną: wektory z tagiem session_id oraz historię/streszczenia w StateManager.
    """
    if not session_id:
        raise HTTPException(status_code=400, detail="session_id jest wymagane")

    vector_store = _ensure_vector_store()
    deleted_vectors = 0
    try:
        deleted_vectors = vector_store.delete_by_metadata({"session_id": session_id})
        deleted_vectors += vector_store.delete_session(session_id)
    except Exception as e:  # pragma: no cover
        logger.warning(f"Nie udało się usunąć wpisów sesyjnych z pamięci: {e}")

    cleared_tasks = 0
    if _state_manager:
        cleared_tasks = _state_manager.clear_session_context(session_id)

    return {
        "status": "success",
        "session_id": session_id,
        "deleted_vectors": deleted_vectors,
        "cleared_tasks": cleared_tasks,
        "message": "Pamięć sesji wyczyszczona",
    }


@router.delete("/global")
async def clear_global_memory():
    """
    Czyści pamięć globalną (preferencje/fakty globalne użytkownika).
    """
    vector_store = _ensure_vector_store()
    try:
        deleted = vector_store.delete_by_metadata({"user_id": DEFAULT_USER_ID})
        # Dev/test: jeśli są pozostałości bez user_id, wyczyść całą kolekcję
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
):
    """
    Zwraca uproszczony graf pamięci (węzły/krawędzie) do wizualizacji w /brain.
    """
    try:
        vector_store = _ensure_vector_store()
    except HTTPException as exc:  # pragma: no cover
        logger.warning(f"Memory graph unavailable: {exc.detail}")
        return {
            "status": "unavailable",
            "reason": exc.detail,
            "elements": {"nodes": [], "edges": []},
            "stats": {"nodes": 0, "edges": 0},
        }
    filters = {}
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
    if include_lessons and _lessons_store:
        try:
            for lesson_id, lesson in (_lessons_store.lessons or {}).items():
                label = getattr(lesson, "title", None) or lesson_id
                lesson_nodes.append(
                    {
                        "data": {
                            "id": f"lesson:{lesson_id}",
                            "label": label,
                            "type": "memory",
                            "memory_kind": "lesson",
                            "lesson_id": lesson_id,
                            "meta": {
                                "tags": getattr(lesson, "tags", None),
                                "timestamp": getattr(lesson, "timestamp", None),
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
            entries_for_flow = sorted(
                nodes,
                key=lambda n: (n["data"].get("meta") or {}).get("timestamp", ""),
            )
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
    entry_id: str, pinned: bool = Query(True, description="Czy oznaczyć pinned")
):
    """
    Ustawia flagę pinned dla wpisu pamięci (w oparciu o LanceDB).
    """
    vector_store = _ensure_vector_store()
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
async def delete_memory_entry(entry_id: str):
    """
    Usuwa wpis pamięci (oraz wszystkie jego fragmenty).
    """
    vector_store = _ensure_vector_store()
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


@router.delete("/lessons/prune/latest")
async def prune_latest_lessons(
    count: int = Query(..., ge=1, description="Liczba najnowszych lekcji do usunięcia"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Usuwa n najnowszych lekcji z magazynu.

    Args:
        count: Liczba lekcji do usunięcia
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Liczba usuniętych lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    try:
        deleted = lessons_store.delete_last_n(count)

        logger.info(f"Pruning: Usunięto {deleted} najnowszych lekcji")

        return {
            "status": "success",
            "message": f"Usunięto {deleted} najnowszych lekcji",
            "deleted": deleted,
        }

    except Exception as e:
        logger.exception("Błąd podczas usuwania najnowszych lekcji")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.delete("/lessons/prune/range")
async def prune_lessons_by_range(
    start: str = Query(
        ..., description="Data początkowa w formacie ISO 8601 (np. 2024-01-01T00:00:00)"
    ),
    end: str = Query(
        ..., description="Data końcowa w formacie ISO 8601 (np. 2024-01-31T23:59:59)"
    ),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Usuwa lekcje z podanego zakresu czasu.

    Args:
        start: Data początkowa (ISO 8601)
        end: Data końcowa (ISO 8601)
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Liczba usuniętych lekcji

    Raises:
        HTTPException: 400 przy błędnym formacie daty, 503 jeśli LessonsStore niedostępny
    """
    try:
        # Parsuj daty ISO 8601 (obsługa 'Z' suffix)
        start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
        end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))

    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail=f"Błędny format daty. Użyj ISO 8601 (np. 2024-01-01T00:00:00): {str(e)}",
        ) from e

    try:
        deleted = lessons_store.delete_by_time_range(start_dt, end_dt)

        logger.info(f"Pruning: Usunięto {deleted} lekcji z zakresu {start} - {end}")

        return {
            "status": "success",
            "message": f"Usunięto {deleted} lekcji z zakresu {start} - {end}",
            "deleted": deleted,
            "start": start,
            "end": end,
        }

    except Exception as e:
        logger.exception("Błąd podczas usuwania lekcji po zakresie czasu")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.delete("/lessons/prune/tag")
async def prune_lessons_by_tag(
    tag: str = Query(..., description="Tag do wyszukania i usunięcia"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Usuwa lekcje zawierające dany tag.

    Args:
        tag: Tag do wyszukania
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Liczba usuniętych lekcji

    Raises:
        HTTPException: 503 jeśli LessonsStore nie jest dostępny
    """
    try:
        deleted = lessons_store.delete_by_tag(tag)

        logger.info(f"Pruning: Usunięto {deleted} lekcji z tagiem '{tag}'")

        return {
            "status": "success",
            "message": f"Usunięto {deleted} lekcji z tagiem '{tag}'",
            "deleted": deleted,
            "tag": tag,
        }

    except Exception as e:
        logger.exception("Błąd podczas usuwania lekcji po tagu")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.delete("/lessons/purge")
async def purge_all_lessons(
    force: bool = Query(
        False, description="Wymagane potwierdzenie dla operacji nuklearnej"
    ),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """
    Czyści całą bazę lekcji (opcja nuklearna).

    Args:
        force: Musi być ustawione na True dla potwierdzenia
        lessons_store: Instancja LessonsStore (dependency injection)

    Returns:
        Potwierdzenie operacji

    Raises:
        HTTPException: 400 jeśli brak potwierdzenia, 503 jeśli LessonsStore niedostępny
    """
    if not force:
        raise HTTPException(
            status_code=400,
            detail="Operacja wymaga potwierdzenia. Ustaw parametr force=true",
        )

    try:
        lesson_count = len(lessons_store.lessons)
        success = lessons_store.clear_all()

        if not success:
            raise HTTPException(
                status_code=500, detail="Nie udało się wyczyścić bazy lekcji"
            )

        logger.warning(
            f"💣 PURGE: Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)"
        )

        return {
            "status": "success",
            "message": f"💣 Wyczyszczono całą bazę lekcji ({lesson_count} lekcji)",
            "deleted": lesson_count,
        }

    except Exception as e:
        logger.exception("Błąd podczas czyszczenia bazy lekcji")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas czyszczenia bazy: {str(e)}"
        ) from e


@router.delete("/lessons/prune/ttl")
async def prune_lessons_by_ttl(
    days: int = Query(..., ge=1, description="Liczba dni retencji (TTL)"),
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Usuwa lekcje starsze niż TTL w dniach."""
    try:
        deleted = lessons_store.prune_by_ttl(days)
        return {
            "status": "success",
            "message": f"Usunięto {deleted} lekcji starszych niż {days} dni",
            "deleted": deleted,
            "days": days,
        }
    except Exception as e:
        logger.exception("Błąd podczas usuwania lekcji po TTL")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas usuwania lekcji: {str(e)}"
        ) from e


@router.post("/lessons/dedupe")
async def dedupe_lessons(
    lessons_store: LessonsStore = Depends(get_lessons_store),
):
    """Deduplikuje lekcje na podstawie podpisu treści."""
    try:
        removed = lessons_store.dedupe_lessons()
        return {
            "status": "success",
            "message": f"Usunięto {removed} zduplikowanych lekcji",
            "removed": removed,
        }
    except Exception as e:
        logger.exception("Błąd podczas deduplikacji lekcji")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas deduplikacji lekcji: {str(e)}"
        ) from e


@router.get("/lessons/learning/status")
async def get_learning_status():
    """Zwraca status globalnego zapisu lekcji."""
    return {"status": "success", "enabled": SETTINGS.ENABLE_META_LEARNING}


class LearningToggleRequest(BaseModel):
    enabled: bool


@router.post("/lessons/learning/toggle")
async def toggle_learning(request: LearningToggleRequest):
    """Włącza/wyłącza globalny zapis lekcji."""
    try:
        SETTINGS.ENABLE_META_LEARNING = request.enabled
        config_manager.update_config({"ENABLE_META_LEARNING": request.enabled})
        return {
            "status": "success",
            "enabled": SETTINGS.ENABLE_META_LEARNING,
        }
    except Exception as e:
        logger.exception("Błąd podczas zmiany stanu uczenia")
        raise HTTPException(
            status_code=500, detail=f"Błąd podczas zmiany stanu: {str(e)}"
        ) from e
