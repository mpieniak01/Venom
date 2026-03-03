import pytest

from scripts.ollama_bench.common import (
    ensure_files_map,
    extract_generate_timing,
    extract_json_object,
    extract_python_code_fence,
    normalize_model_code,
    parse_model_files_response,
)
from scripts.ollama_bench.scoreboard import aggregate


def test_extract_json_object_handles_markdown_fence():
    raw = """
    model output

    ```json
    {"files": {"solution.py": "print('ok')"}, "notes": "done"}
    ```
    """
    parsed = extract_json_object(raw)
    assert parsed["files"]["solution.py"] == "print('ok')"


def test_ensure_files_map_rejects_path_traversal():
    payload = {"files": {"../evil.py": "print('x')"}}
    with pytest.raises(ValueError, match="Unsafe file path"):
        ensure_files_map(payload)


def test_ensure_files_map_normalizes_escaped_newlines():
    payload = {
        "files": {
            "solution.py": "def x():\\n    return 1\\n",
        }
    }
    files = ensure_files_map(payload)
    assert files["solution.py"].splitlines() == ["def x():", "    return 1"]


def test_extract_python_code_fence_prefers_fenced_code():
    raw = """
    opis
    ```python
    def safe_divide(a, b):
        return None if b == 0 else a / b
    ```
    dodatkowy tekst
    """
    code = extract_python_code_fence(raw)
    assert "def safe_divide" in code


def test_parse_model_files_response_falls_back_to_code_fence_for_single_file():
    raw = """
    ```python
    def safe_divide(a: float, b: float) -> float | None:
        if b == 0:
            return None
        return a / b
    ```
    To jest opis.
    """
    files = parse_model_files_response(raw, ("solution.py",))
    assert "solution.py" in files
    assert "def safe_divide" in files["solution.py"]


def test_parse_model_files_response_remaps_single_unknown_file_name():
    raw = """
    ```json
    {
      "files": {
        "path.py": "def safe_divide(a, b):\\n    return None if b == 0 else a / b\\n"
      },
      "notes": "short"
    }
    ```
    """
    files = parse_model_files_response(raw, ("solution.py",))
    assert "solution.py" in files
    assert "def safe_divide" in files["solution.py"]


def test_parse_model_files_response_does_not_use_json_fence_as_python_code():
    raw = """
    ```json
    {
      "files": {
        "path.py": ""
      }
    }
    ```
    """
    with pytest.raises(ValueError, match="No fenced code block found"):
        parse_model_files_response(raw, ("solution.py",))


def test_normalize_model_code_removes_control_chars():
    raw = "print('ok')\x00\x01\n"
    assert normalize_model_code(raw) == "print('ok')\n"


def test_extract_generate_timing_maps_ollama_fields():
    payload = {
        "total_duration": 3_500_000_000,
        "load_duration": 1_200_000_000,
        "prompt_eval_duration": 500_000_000,
        "eval_duration": 1_100_000_000,
        "prompt_eval_count": 120,
        "eval_count": 220,
        "done": True,
        "done_reason": "stop",
    }
    timing = extract_generate_timing(payload, request_wall_seconds=3.7)
    assert timing["total_seconds"] == 3.5
    assert timing["warmup_seconds"] == 1.2
    assert timing["coding_seconds"] == 1.1
    assert timing["inference_seconds"] == 1.6
    assert timing["request_wall_seconds"] == 3.7


def test_scoreboard_aggregate_ranks_models_by_score():
    artifacts = [
        {
            "run_type": "single_task",
            "model": "m1",
            "task_id": "python_simple",
            "passed": True,
        },
        {
            "run_type": "single_task",
            "model": "m1",
            "task_id": "python_complex",
            "passed": True,
        },
        {
            "run_type": "feedback_loop",
            "model": "m1",
            "task_id": "python_complex_bugfix",
            "solved": True,
            "rounds": [{"round": 1}],
        },
        {
            "run_type": "single_task",
            "model": "m2",
            "task_id": "python_simple",
            "passed": True,
        },
        {
            "run_type": "single_task",
            "model": "m2",
            "task_id": "python_complex",
            "passed": False,
        },
        {
            "run_type": "feedback_loop",
            "model": "m2",
            "task_id": "python_complex_bugfix",
            "solved": False,
            "rounds": [{"round": 1}, {"round": 2}, {"round": 3}],
        },
    ]

    rows = aggregate(artifacts)
    assert rows[0].model == "m1"
    assert rows[1].model == "m2"
    assert rows[0].score > rows[1].score


def test_scoreboard_gives_zero_speed_points_without_loop_success():
    artifacts = [
        {
            "run_type": "single_task",
            "model": "m0",
            "task_id": "python_complex",
            "passed": False,
        },
        {
            "run_type": "feedback_loop",
            "model": "m0",
            "task_id": "python_complex_bugfix",
            "solved": False,
            "rounds": [],
        },
    ]
    rows = aggregate(artifacts)
    assert rows[0].score == 0.0
