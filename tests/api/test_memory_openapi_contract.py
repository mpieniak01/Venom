from venom_core.main import app


def test_memory_openapi_response_model_bindings_wave_1():
    """Kontrakt OpenAPI: endpointy memory Wave-1 muszą mieć jawne response modele."""
    schema = app.openapi()
    paths = schema["paths"]

    expected_refs = {
        ("/api/v1/memory/search", "post"): "#/components/schemas/MemorySearchResponse",
        (
            "/api/v1/memory/session/{session_id}",
            "delete",
        ): "#/components/schemas/SessionMemoryClearResponse",
        (
            "/api/v1/memory/session/{session_id}",
            "get",
        ): "#/components/schemas/SessionMemoryResponse",
        (
            "/api/v1/memory/global",
            "delete",
        ): "#/components/schemas/GlobalMemoryClearResponse",
        ("/api/v1/memory/graph", "get"): "#/components/schemas/MemoryGraphResponse",
        (
            "/api/v1/memory/entry/{entry_id}/pin",
            "post",
        ): "#/components/schemas/MemoryEntryMutationResponse",
        (
            "/api/v1/memory/entry/{entry_id}",
            "delete",
        ): "#/components/schemas/MemoryEntryMutationResponse",
        (
            "/api/v1/memory/lessons/prune/latest",
            "delete",
        ): "#/components/schemas/LessonsMutationResponse",
        (
            "/api/v1/memory/lessons/prune/range",
            "delete",
        ): "#/components/schemas/LessonsMutationResponse",
        (
            "/api/v1/memory/lessons/prune/tag",
            "delete",
        ): "#/components/schemas/LessonsMutationResponse",
        (
            "/api/v1/memory/lessons/prune/ttl",
            "delete",
        ): "#/components/schemas/LessonsMutationResponse",
        (
            "/api/v1/memory/lessons/purge",
            "delete",
        ): "#/components/schemas/LessonsMutationResponse",
        (
            "/api/v1/memory/lessons/learning/status",
            "get",
        ): "#/components/schemas/LearningStatusResponse",
        (
            "/api/v1/memory/lessons/learning/toggle",
            "post",
        ): "#/components/schemas/LearningStatusResponse",
    }

    for (path, method), expected_ref in expected_refs.items():
        operation = paths[path][method]
        response_schema = operation["responses"]["200"]["content"]["application/json"][
            "schema"
        ]
        assert response_schema["$ref"] == expected_ref
