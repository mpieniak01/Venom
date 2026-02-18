from venom_core.main import app


def test_academy_jobs_openapi_response_model_binding():
    """Kontrakt OpenAPI: /api/v1/academy/jobs musi mieć jawny model odpowiedzi."""
    schema = app.openapi()
    get_op = schema["paths"]["/api/v1/academy/jobs"]["get"]
    content_schema = get_op["responses"]["200"]["content"]["application/json"]["schema"]
    assert content_schema["$ref"] == "#/components/schemas/AcademyJobsListResponse"
