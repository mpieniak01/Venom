import json
from pathlib import Path

import venom_core.core.hidden_prompts as hidden


def test_get_cached_hidden_response_prefers_active(tmp_path: Path, monkeypatch):
    hidden.HIDDEN_PROMPTS_PATH = tmp_path / "hidden.jsonl"
    hidden.ACTIVE_HIDDEN_PROMPTS_PATH = tmp_path / "active.json"

    # zapis agregowanych (score)
    hidden.HIDDEN_PROMPTS_PATH.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "prompt": "Co to jest kwadrat?",
                        "approved_response": "stara definicja",
                        "intent": "QA",
                        "timestamp": "2024-01-01T00:00:00",
                    }
                )
            ]
        ),
        encoding="utf-8",
    )

    # aktywny wpis (powinien mieć priorytet)
    hidden.ACTIVE_HIDDEN_PROMPTS_PATH.write_text(
        json.dumps(
            {
                "items": [
                    {
                        "prompt": "Co to jest kwadrat?",
                        "approved_response": "nowa definicja",
                        "intent": "QA",
                        "prompt_hash": "hash1",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    resp = hidden.get_cached_hidden_response("Co to jest kwadrat?", intent="QA")
    assert resp == "nowa definicja"


def test_get_cached_hidden_response_respects_min_score(tmp_path: Path, monkeypatch):
    hidden.HIDDEN_PROMPTS_PATH = tmp_path / "hidden.jsonl"
    hidden.ACTIVE_HIDDEN_PROMPTS_PATH = tmp_path / "active.json"

    # wpis z niskim score (pojedynczy)
    hidden.HIDDEN_PROMPTS_PATH.write_text(
        json.dumps(
            {
                "prompt": "Co to jest koło?",
                "approved_response": "definicja kola",
                "intent": "QA",
                "timestamp": "2024-01-01T00:00:00",
            }
        ),
        encoding="utf-8",
    )

    resp_none = hidden.get_cached_hidden_response(
        "Co to jest koło?", intent="QA", min_score=2
    )
    assert resp_none is None

    resp_hit = hidden.get_cached_hidden_response(
        "Co to jest koło?", intent="QA", min_score=1
    )
    assert resp_hit == "definicja kola"
