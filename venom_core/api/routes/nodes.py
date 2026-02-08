"""Moduł: routes/nodes - Endpointy API dla distributed nodes (Nexus)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/nodes", tags=["nodes"])

NODES_LIST_RESPONSES = {
    503: {"description": "NodeManager nie jest dostępny"},
    500: {"description": "Błąd wewnętrzny podczas pobierania listy węzłów"},
}
NODE_INFO_RESPONSES = {
    503: {"description": "NodeManager nie jest dostępny"},
    404: {"description": "Węzeł o podanym ID nie istnieje"},
    500: {"description": "Błąd wewnętrzny podczas pobierania informacji o węźle"},
}
NODE_EXECUTE_RESPONSES = {
    400: {"description": "Węzeł jest offline lub żądanie jest nieprawidłowe"},
    404: {"description": "Węzeł o podanym ID nie istnieje"},
    503: {"description": "NodeManager nie jest dostępny"},
    504: {"description": "Przekroczono timeout wykonywania na węźle"},
    500: {"description": "Błąd wewnętrzny podczas wykonywania na węźle"},
}


class NodeExecuteRequest(BaseModel):
    """Model żądania wykonania skilla na węźle."""

    skill_name: str
    method_name: str
    parameters: dict = {}
    timeout: int = 30


# Dependencies - będą ustawione w main.py
_node_manager = None


def set_dependencies(node_manager):
    """Ustaw zależności dla routera."""
    global _node_manager
    _node_manager = node_manager


@router.get("", responses=NODES_LIST_RESPONSES)
async def list_nodes(online_only: bool = False):
    """
    Zwraca listę zarejestrowanych węzłów.

    Args:
        online_only: Czy zwrócić tylko węzły online (domyślnie False)

    Returns:
        Lista węzłów z ich informacjami

    Raises:
        HTTPException: 503 jeśli NodeManager nie jest dostępny
    """
    if _node_manager is None:
        raise HTTPException(
            status_code=503,
            detail="NodeManager nie jest dostępny - włącz tryb Nexus (ENABLE_NEXUS=true)",
        )

    try:
        nodes = _node_manager.list_nodes(online_only=online_only)
        nodes_data = [node.to_dict() for node in nodes]
        return {
            "status": "success",
            "count": len(nodes_data),
            "online_count": len([n for n in nodes if n.is_online]),
            "nodes": nodes_data,
        }
    except Exception as e:
        logger.exception("Błąd podczas pobierania listy węzłów")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.get("/{node_id}", responses=NODE_INFO_RESPONSES)
async def get_node_info(node_id: str):
    """
    Zwraca szczegółowe informacje o węźle.

    Args:
        node_id: ID węzła

    Returns:
        Informacje o węźle

    Raises:
        HTTPException: 404 jeśli węzeł nie istnieje, 503 jeśli NodeManager nie jest dostępny
    """
    if _node_manager is None:
        raise HTTPException(
            status_code=503,
            detail="NodeManager nie jest dostępny - włącz tryb Nexus (ENABLE_NEXUS=true)",
        )

    try:
        node = _node_manager.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Węzeł {node_id} nie istnieje")

        return {"status": "success", "node": node.to_dict()}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Błąd podczas pobierania informacji o węźle {node_id}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e


@router.post("/{node_id}/execute", responses=NODE_EXECUTE_RESPONSES)
async def execute_on_node(node_id: str, request: NodeExecuteRequest):
    """
    Wykonuje skill na określonym węźle.

    Args:
        node_id: ID węzła docelowego
        request: Żądanie wykonania

    Returns:
        Wynik wykonania

    Raises:
        HTTPException: 404 jeśli węzeł nie istnieje, 400 jeśli węzeł offline,
                      503 jeśli NodeManager nie jest dostępny, 504 jeśli timeout
    """
    if _node_manager is None:
        raise HTTPException(
            status_code=503,
            detail="NodeManager nie jest dostępny - włącz tryb Nexus (ENABLE_NEXUS=true)",
        )

    try:
        # Sprawdź czy węzeł istnieje
        node = _node_manager.get_node(node_id)
        if node is None:
            raise HTTPException(status_code=404, detail=f"Węzeł {node_id} nie istnieje")

        # Sprawdź czy węzeł jest online
        if not node.is_online:
            raise HTTPException(
                status_code=400,
                detail=f"Węzeł {node_id} jest offline. Upewnij się że węzeł jest uruchomiony i połączony.",
            )

        # Wykonaj skill na węźle
        result = await _node_manager.execute_on_node(
            node_id=node_id,
            skill_name=request.skill_name,
            method_name=request.method_name,
            parameters=request.parameters,
            timeout=request.timeout,
        )

        return {"status": "success", "result": result}

    except HTTPException:
        raise
    except TimeoutError:
        raise HTTPException(
            status_code=504,
            detail=f"Timeout podczas wykonywania na węźle {node_id} po {request.timeout}s",
        )
    except Exception as e:
        logger.exception(f"Błąd podczas wykonywania na węźle {node_id}")
        raise HTTPException(status_code=500, detail=f"Błąd wewnętrzny: {str(e)}") from e
