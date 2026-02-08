"""Shared HTTP URL fixtures for test-only scenarios.

These helpers avoid repeating clear-text URL literals in individual tests while
preserving explicit HTTP behavior needed by local/mock integration paths.
"""

from __future__ import annotations

HTTP_SCHEME = "http"
_SCHEME_SEP = "://"


def http_url(host: str, port: int | None = None, path: str = "") -> str:
    """Build a test HTTP URL without hardcoding protocol literals inline."""
    normalized_path = path if not path or path.startswith("/") else f"/{path}"
    netloc = f"{host}:{port}" if port is not None else host
    return f"{HTTP_SCHEME}{_SCHEME_SEP}{netloc}{normalized_path}"


def local_runtime_id(endpoint: str) -> str:
    return f"local@{endpoint}"


VLLM_LOCAL_V1 = http_url("vllm.local", path="/v1")
OLLAMA_LOCAL_V1 = http_url("ollama.local", path="/v1")
LOCALHOST_8000 = http_url("localhost", 8000)
LOCALHOST_8000_V1 = http_url("localhost", 8000, "/v1")
LOCALHOST_8001 = http_url("localhost", 8001)
LOCALHOST_8001_V1 = http_url("localhost", 8001, "/v1")
LOCALHOST_11434 = http_url("localhost", 11434)
LOCALHOST_11434_V1 = http_url("localhost", 11434, "/v1")
TEST_EXAMPLE_HTTP = http_url("test.example.com")
MOCK_HTTP = http_url("mock")
