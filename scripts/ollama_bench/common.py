#!/usr/bin/env python3
"""Wspólne narzędzia dla benchmarków codingowych modeli Ollama."""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib import error, request

DEFAULT_OLLAMA_ENDPOINT = "http://127.0.0.1:11434"


class OllamaError(RuntimeError):
    """Błąd komunikacji z Ollama API."""


@dataclass
class CheckResult:
    """Wynik walidacji kodu (pytest + ruff)."""

    pytest_rc: int
    pytest_output: str
    ruff_rc: int
    ruff_output: str

    @property
    def passed(self) -> bool:
        return self.pytest_rc == 0 and self.ruff_rc == 0

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["passed"] = self.passed
        return data


def utc_now_iso() -> str:
    """Bieżący timestamp UTC w ISO 8601."""
    return datetime.now(timezone.utc).isoformat()


def _join(base: str, path: str) -> str:
    return f"{base.rstrip('/')}/{path.lstrip('/')}"


def _http_json(
    method: str, url: str, payload: dict[str, Any] | None, timeout: int
) -> Any:
    body = None
    headers = {"Content-Type": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")

    req = request.Request(url=url, method=method.upper(), data=body, headers=headers)
    try:
        with request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw)
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise OllamaError(f"HTTP {exc.code} for {url}: {detail}") from exc
    except error.URLError as exc:
        raise OllamaError(f"Network error for {url}: {exc.reason}") from exc


def discover_models(
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT, timeout: int = 30
) -> list[str]:
    """Pobiera listę modeli z `/api/tags` i zwraca posortowane nazwy."""
    data = _http_json(
        "GET", _join(endpoint, "/api/tags"), payload=None, timeout=timeout
    )
    models = data.get("models", []) if isinstance(data, dict) else []
    names = [
        str(item.get("name", "")).strip() for item in models if isinstance(item, dict)
    ]
    filtered = sorted({name for name in names if name})
    if not filtered:
        raise OllamaError("No models discovered from /api/tags")
    return filtered


def ollama_generate(
    model: str,
    prompt: str,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
) -> str:
    """Wywołuje `/api/generate` z `stream=false` i zwraca tekst odpowiedzi."""
    response, _timing = ollama_generate_with_timing(
        model=model,
        prompt=prompt,
        endpoint=endpoint,
        timeout=timeout,
        options=options,
    )
    return response


def _ns_to_seconds(value: Any) -> float | None:
    if isinstance(value, (int, float)) and value >= 0:
        return round(float(value) / 1_000_000_000.0, 6)
    return None


def extract_generate_timing(
    data: dict[str, Any], request_wall_seconds: float
) -> dict[str, Any]:
    """Normalizuje metryki czasu z odpowiedzi Ollama generate."""
    load_seconds = _ns_to_seconds(data.get("load_duration"))
    prompt_eval_seconds = _ns_to_seconds(data.get("prompt_eval_duration"))
    eval_seconds = _ns_to_seconds(data.get("eval_duration"))
    total_seconds = _ns_to_seconds(data.get("total_duration"))

    inference_seconds = None
    if prompt_eval_seconds is not None and eval_seconds is not None:
        inference_seconds = round(prompt_eval_seconds + eval_seconds, 6)

    return {
        "request_wall_seconds": round(request_wall_seconds, 6),
        "total_seconds": total_seconds,
        "load_seconds": load_seconds,
        "prompt_eval_seconds": prompt_eval_seconds,
        "eval_seconds": eval_seconds,
        # Metryki użytkowe do raportowania:
        "warmup_seconds": load_seconds,
        "coding_seconds": eval_seconds,
        "inference_seconds": inference_seconds,
        "prompt_eval_count": data.get("prompt_eval_count"),
        "eval_count": data.get("eval_count"),
        "done": data.get("done"),
        "done_reason": data.get("done_reason"),
    }


def ollama_generate_with_timing(
    model: str,
    prompt: str,
    endpoint: str = DEFAULT_OLLAMA_ENDPOINT,
    timeout: int = 120,
    options: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any]]:
    """Wywołuje `/api/generate` i zwraca (response_text, timing_metrics)."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if options:
        payload["options"] = options

    started_at = time.perf_counter()
    data = _http_json(
        "POST", _join(endpoint, "/api/generate"), payload, timeout=timeout
    )
    request_wall_seconds = time.perf_counter() - started_at
    if not isinstance(data, dict):
        raise OllamaError("Invalid /api/generate response shape")
    response = data.get("response")
    if not isinstance(response, str) or not response.strip():
        raise OllamaError("Empty response from /api/generate")
    timing = extract_generate_timing(data, request_wall_seconds=request_wall_seconds)
    return response, timing


def extract_json_object(text: str) -> dict[str, Any]:
    """Wyciąga pierwszy poprawny obiekt JSON z odpowiedzi modelu."""
    direct = text.strip()
    try:
        parsed = json.loads(direct)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    fence_match = re.search(r"```(?:json)?\s*(\{[\s\S]*\})\s*```", text, re.IGNORECASE)
    if fence_match:
        candidate = fence_match.group(1)
        parsed = json.loads(candidate)
        if isinstance(parsed, dict):
            return parsed

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("Unable to extract JSON object from model response")


def ensure_files_map(payload: dict[str, Any]) -> dict[str, str]:
    """Waliduje kontrakt odpowiedzi modelu i zwraca mapę plików."""
    files = payload.get("files")
    if not isinstance(files, dict):
        raise ValueError("Payload must contain object field 'files'")

    output: dict[str, str] = {}
    for path, content in files.items():
        if not isinstance(path, str) or not path.strip():
            raise ValueError("File path key must be non-empty string")
        if not isinstance(content, str):
            raise ValueError(f"File content for '{path}' must be string")
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError(f"Unsafe file path: {path}")
        output[path] = normalize_model_code(content)

    if not output:
        raise ValueError("'files' cannot be empty")
    return output


def extract_python_code_fence(text: str) -> str:
    """Wyciąga pierwszy blok kodu z odpowiedzi modelu."""
    blocks = re.finditer(r"```([^\n`]*)\n([\s\S]*?)```", text)
    parsed_blocks: list[tuple[str, str]] = []
    for match in blocks:
        lang = match.group(1).strip().lower()
        code = match.group(2).strip()
        if code:
            parsed_blocks.append((lang, code))

    for lang, code in parsed_blocks:
        if lang in {"python", "py"}:
            return code

    for lang, code in parsed_blocks:
        if lang in {"json", "yaml", "yml", "xml"}:
            continue
        compact = code.lstrip()
        if compact.startswith("{") or compact.startswith("["):
            continue
        if re.search(r"\b(def|class|import|from|return|if|for|while)\b", code):
            return code

    raise ValueError("No fenced code block found in model response")


def extract_python_code_unfenced(text: str) -> str:
    """Wyciąga kod Python z odpowiedzi bez fenced code block (fallback)."""
    if "```" in text:
        raise ValueError("Fenced block present; use fenced parser first")

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    start_idx = None
    code_start_re = re.compile(
        r"^\s*(from\s+\w+|import\s+\w+|def\s+\w+\s*\(|class\s+\w+|if\s+.+:|for\s+.+:|while\s+.+:|try:|with\s+.+:|@|#|[A-Za-z_]\w*\s*=|print\s*\()"
    )
    for idx, line in enumerate(lines):
        if code_start_re.search(line):
            start_idx = idx
            break
    if start_idx is None:
        raise ValueError("No obvious unfenced Python code found")

    candidate = "\n".join(lines[start_idx:]).strip()
    if not candidate:
        raise ValueError("Unfenced Python candidate is empty")
    if candidate.startswith("{") or candidate.startswith("["):
        raise ValueError("Unfenced candidate looks like JSON, not Python code")

    # Minimal guard: require at least one Python-shaped token.
    if not re.search(
        r"\b(def|class|import|from|return|if|for|while|try|with|assert|print)\b",
        candidate,
    ):
        raise ValueError("Unfenced candidate does not look like Python code")
    return candidate


def parse_model_files_response(
    raw: str, required_files: tuple[str, ...]
) -> dict[str, str]:
    """Parsuje odpowiedź modelu do mapy plików (JSON, a dla 1-pliku: fallback code-fence)."""
    if not required_files:
        raise ValueError("required_files cannot be empty")

    single_required = len(required_files) == 1
    required = required_files[0] if single_required else None

    try:
        payload = extract_json_object(raw)
    except (ValueError, json.JSONDecodeError) as json_exc:
        payload = None
        payload_error = json_exc
    else:
        try:
            files = ensure_files_map(payload)
            missing = [path for path in required_files if path not in files]
            if not missing:
                return files
            if single_required:
                for _path, content in files.items():
                    if content.strip():
                        return {required: content}
        except ValueError as files_exc:
            payload_error = files_exc
        else:
            payload_error = ValueError(
                f"Model response missing required files: {missing}"
            )

        if single_required:
            for key in (required, "code", "content", "solution", "python"):
                value = payload.get(key)
                if isinstance(value, str):
                    normalized = normalize_model_code(value)
                    if normalized.strip():
                        return {required: normalized}

    if single_required:
        try:
            code = extract_python_code_fence(raw)
        except ValueError as fence_exc:
            try:
                code = extract_python_code_unfenced(raw)
            except ValueError:
                raise fence_exc
        normalized = normalize_model_code(code)
        if normalized.strip():
            return {required: normalized}
        raise ValueError("Extracted code block is empty")

    raise ValueError(
        f"Could not parse JSON payload and no safe fallback for multi-file task: {payload_error}"
    ) from payload_error


def normalize_model_code(content: str) -> str:
    """Normalizuje kod zwrócony przez model (escaped newline/control chars)."""
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").lstrip("\ufeff")

    # Modele czasem zwracają kod jako jeden string z literalnym "\\n" zamiast realnych linii.
    if "\n" not in normalized and ("\\n" in normalized or "\\r" in normalized):
        normalized = (
            normalized.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        )

    # Usuwa znaki kontrolne (w tym NUL), zostawiając tab/newline.
    cleaned = "".join(ch for ch in normalized if ch in {"\n", "\t"} or ord(ch) >= 32)
    return cleaned


def run_checks(workdir: Path, timeout: int = 60) -> CheckResult:
    """Uruchamia pytest i ruff check w katalogu roboczym zadania."""
    python_bin = sys.executable or "python3"
    pytest_cmd = [python_bin, "-m", "pytest", "-q"]
    ruff_cmd = [python_bin, "-m", "ruff", "check", "."]

    pytest_proc = subprocess.run(
        pytest_cmd,
        cwd=workdir,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    ruff_proc = subprocess.run(
        ruff_cmd,
        cwd=workdir,
        text=True,
        capture_output=True,
        timeout=timeout,
        check=False,
    )

    pytest_output = (pytest_proc.stdout + "\n" + pytest_proc.stderr).strip()
    ruff_output = (ruff_proc.stdout + "\n" + ruff_proc.stderr).strip()
    return CheckResult(
        pytest_rc=pytest_proc.returncode,
        pytest_output=pytest_output,
        ruff_rc=ruff_proc.returncode,
        ruff_output=ruff_output,
    )


def build_workspace(files: dict[str, str], tests: dict[str, str]) -> Path:
    """Tworzy tymczasowy katalog testowy i zapisuje pliki zadania."""
    root = Path(tempfile.mkdtemp(prefix="ollama-bench-"))
    for rel_path, content in {**files, **tests}.items():
        path = root / rel_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def safe_snippet(text: str, limit: int = 3000) -> str:
    """Obcina logi do rozsądnej długości."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n...<trimmed {len(text) - limit} chars>"
