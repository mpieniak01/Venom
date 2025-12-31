"""Endpoint projekcji embeddingów do 2D."""

import numpy as np
from fastapi import APIRouter, HTTPException, Query
from sklearn.decomposition import PCA

from venom_core.utils.logger import get_logger

router = APIRouter(prefix="/api/v1/memory", tags=["memory-projection"])

logger = get_logger(__name__)

_vector_store = None
_embedding_service = None


def set_dependencies(vector_store):
    global _vector_store, _embedding_service
    _vector_store = vector_store
    try:
        _embedding_service = vector_store.embedding_service
    except Exception:
        _embedding_service = None


@router.post("/embedding-project")
async def project_embeddings(limit: int = Query(200, ge=2, le=1000)):
    """Prosta projekcja embeddingów do 2D (PCA) i zapis x,y w metadanych."""
    if _vector_store is None or _embedding_service is None:
        raise HTTPException(
            status_code=503, detail="VectorStore lub embedding service niedostępny"
        )

    entries = _vector_store.list_entries(limit=limit)
    texts = [e.get("text") or "" for e in entries]
    ids = [e.get("id") or (e.get("metadata") or {}).get("id") for e in entries]
    if len(texts) < 2:
        return {
            "status": "success",
            "updated": 0,
            "message": "Za mało wpisów do projekcji",
        }

    try:
        vectors = _embedding_service.get_embeddings_batch(texts)
        vectors_np = np.array(vectors)
        pca = PCA(n_components=2)
        coords = pca.fit_transform(vectors_np)
        updated = 0
        for idx, entry_id in enumerate(ids):
            if not entry_id:
                continue
            x_val, y_val = coords[idx].tolist()
            ok = _vector_store.update_metadata(
                entry_id, {"x": float(x_val), "y": float(y_val)}
            )
            if ok:
                updated += 1
        return {"status": "success", "updated": updated}
    except Exception as e:
        logger.exception("Błąd projekcji embeddingów")
        raise HTTPException(status_code=500, detail=f"Projection error: {e}") from e
