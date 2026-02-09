import asyncio
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from venom_core.core.intent_manager import IntentManager


def test_normalize_text_removes_diacritics_and_punctuation():
    normalized = IntentManager._normalize_text("  Zażółć, gęślą! Jaźń??  ")
    assert normalized == "zazo c gesla jazn"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Która godzina?", "pl"),
        ("Wie spät ist es?", "de"),
        ("What time is it?", "en"),
        ("", ""),
    ],
)
def test_detect_language(text: str, expected: str):
    assert IntentManager._detect_language(text) == expected


def test_merge_lexicons_combines_entries_and_overrides_threshold():
    base = {
        "intents": {
            "HELP_REQUEST": {
                "phrases": ["pomoc"],
                "regex": ["^help$"],
                "threshold": 0.9,
            }
        }
    }
    override = {
        "intents": {
            "HELP_REQUEST": {
                "phrases": ["help", "pomoc"],
                "regex": ["^hilfe$"],
                "threshold": 0.8,
            }
        }
    }

    merged = IntentManager._merge_lexicons(base, override)
    cfg = merged["intents"]["HELP_REQUEST"]
    assert cfg["threshold"] == pytest.approx(0.8)
    assert cfg["phrases"] == ["pomoc", "help"]
    assert cfg["regex"] == ["^help$", "^hilfe$"]


def test_should_learn_phrase_applies_guardrails():
    manager = IntentManager(kernel=MagicMock())

    assert manager._should_learn_phrase("jak uruchomic testy") is True
    assert manager._should_learn_phrase("https://example.com/test") is False
    assert manager._should_learn_phrase("a") is False
    assert manager._should_learn_phrase("to jest bardzo dluga fraza " * 8) is False


def test_phrase_exists_matches_normalized_form():
    manager = IntentManager(kernel=MagicMock())
    lexicon = {"intents": {"HELP_REQUEST": {"phrases": ["Co potrafisz?"], "regex": []}}}

    assert manager._phrase_exists("HELP_REQUEST", "co potrafisz", lexicon) is True
    assert manager._phrase_exists("HELP_REQUEST", "inna fraza", lexicon) is False


def test_match_intent_lexicon_prefers_regex_and_similarity():
    lexicon = {
        "intents": {
            "TIME_REQUEST": {
                "phrases": ["ktora godzina"],
                "regex": ["^czas$"],
                "threshold": 0.8,
            },
            "HELP_REQUEST": {
                "phrases": ["co potrafisz"],
                "regex": [],
                "threshold": 0.8,
            },
        }
    }
    intent, score, _ = IntentManager._match_intent_lexicon("czas", lexicon)
    assert intent == "TIME_REQUEST"
    assert score == pytest.approx(1.0)

    intent2, score2, top2 = IntentManager._match_intent_lexicon("co potrafisz", lexicon)
    assert intent2 == "HELP_REQUEST"
    assert score2 >= 0.8
    assert top2


@pytest.mark.asyncio
async def test_classify_from_keywords_for_help_and_time_and_infra():
    kernel = MagicMock()
    service = MagicMock()
    service.get_chat_message_content = AsyncMock(side_effect=Exception("no llm"))
    kernel.get_service.return_value = service

    manager = IntentManager(kernel=kernel)
    manager._append_user_phrase = MagicMock()

    assert (
        await manager._classify_from_keywords(
            manager._normalize_text("co potrafisz"), "co potrafisz", "pl"
        )
        == "HELP_REQUEST"
    )
    assert (
        await manager._classify_from_keywords(
            manager._normalize_text("ktora godzina"), "ktora godzina", "pl"
        )
        == "TIME_REQUEST"
    )
    assert (
        await manager._classify_from_keywords(
            manager._normalize_text("status usług"), "status usług", "pl"
        )
        == "INFRA_STATUS"
    )


@pytest.mark.asyncio
async def test_classify_intent_perf_keyword_shortcut():
    manager = IntentManager(kernel=MagicMock())
    result = await manager.classify_intent("parallel perf")
    assert result == "GENERAL_CHAT"


def test_apply_lexicon_tie_break_prefers_tool_intent():
    manager = IntentManager(kernel=MagicMock())
    best = manager._apply_lexicon_tie_break(
        "GENERAL_CHAT", [("GENERAL_CHAT", 0.9), ("TIME_REQUEST", 0.89)]
    )
    assert best == "TIME_REQUEST"


def test_build_intent_chat_history_variants():
    manager = IntentManager(kernel=MagicMock())
    user_history = manager._build_intent_chat_history(
        system_prompt="SYSTEM", user_input="hello", system_as_user=True
    )
    system_history = manager._build_intent_chat_history(
        system_prompt="SYSTEM", user_input="hello", system_as_user=False
    )

    assert len(user_history.messages) == 1
    assert "Klasyfikuj intencję" in str(user_history.messages[0].content)
    assert len(system_history.messages) == 2


def test_normalize_llm_intent_with_embedded_label():
    manager = IntentManager(kernel=MagicMock())
    assert (
        manager._normalize_llm_intent("The intent is COMPLEX_PLANNING")
        == "COMPLEX_PLANNING"
    )
    assert manager._normalize_llm_intent("UNKNOWN") == "GENERAL_CHAT"


@pytest.mark.asyncio
async def test_classify_from_llm_timeout_returns_general_chat():
    kernel = MagicMock()
    kernel.get_service.return_value = MagicMock()
    manager = IntentManager(kernel=kernel)
    manager._request_intent_response = AsyncMock(side_effect=asyncio.TimeoutError())

    result = await manager._classify_from_llm("hello", "hello", "en")
    assert result == "GENERAL_CHAT"


@pytest.mark.asyncio
async def test_classify_from_llm_system_role_fallback_path():
    kernel = MagicMock()
    kernel.get_service.return_value = MagicMock()
    manager = IntentManager(kernel=kernel)
    manager._append_user_phrase = MagicMock()
    manager._request_intent_response = AsyncMock(
        side_effect=[Exception("system role not supported"), "HELP_REQUEST"]
    )

    result = await manager._classify_from_llm("co potrafisz", "co potrafisz", "pl")
    assert result == "HELP_REQUEST"


def test_load_lexicon_and_cache(tmp_path, monkeypatch):
    manager = IntentManager(kernel=MagicMock())
    manager._lexicon_cache.clear()

    monkeypatch.setattr(IntentManager, "LEXICON_DIR", tmp_path)
    monkeypatch.setattr(
        IntentManager, "LEXICON_FILES", {"pl": "intent_lexicon_pl.json"}
    )
    payload = {"intents": {"HELP_REQUEST": {"phrases": ["pomoc"], "regex": []}}}
    (tmp_path / "intent_lexicon_pl.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    loaded = manager._load_lexicon("pl")
    assert loaded == payload

    # cache hit path
    (tmp_path / "intent_lexicon_pl.json").unlink()
    loaded_cached = manager._load_lexicon("pl")
    assert loaded_cached == payload
    assert manager._load_lexicon("xx") == {}


def test_load_user_lexicon_and_parse_error(tmp_path, monkeypatch):
    manager = IntentManager(kernel=MagicMock())
    monkeypatch.setattr(IntentManager, "USER_LEXICON_DIR", tmp_path)

    valid = tmp_path / "intent_lexicon_user_pl.json"
    valid.write_text(
        '{"intents":{"HELP_REQUEST":{"phrases":["pomoc"]}}}', encoding="utf-8"
    )
    assert manager._load_user_lexicon("pl")["intents"]["HELP_REQUEST"]["phrases"] == [
        "pomoc"
    ]

    broken = tmp_path / "intent_lexicon_user_en.json"
    broken.write_text("{", encoding="utf-8")
    assert manager._load_user_lexicon("en") == {}


def test_append_user_phrase_persists_to_user_lexicon(tmp_path, monkeypatch):
    manager = IntentManager(kernel=MagicMock())
    monkeypatch.setattr(IntentManager, "USER_LEXICON_DIR", tmp_path)
    monkeypatch.setattr(manager, "_load_lexicon", lambda _lang: {"intents": {}})
    monkeypatch.setattr(manager, "_load_user_lexicon", lambda _lang: {"intents": {}})

    manager._append_user_phrase("HELP_REQUEST", "jak uruchomic testy", "pl")
    path = tmp_path / "intent_lexicon_user_pl.json"
    assert path.exists()
    data = json.loads(path.read_text(encoding="utf-8"))
    assert "jak uruchomic testy" in data["intents"]["HELP_REQUEST"]["phrases"]


def test_init_with_builder_failure_in_test_mode(monkeypatch):
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "1")

    class DummyBuilder:
        def build_kernel(self):
            raise RuntimeError("boom")

    monkeypatch.setattr("venom_core.core.intent_manager.KernelBuilder", DummyBuilder)
    manager = IntentManager(kernel=None)
    assert manager.kernel is None
    assert manager._llm_disabled is True


@pytest.mark.asyncio
async def test_classify_intent_with_llm_error_falls_back_to_help():
    manager = IntentManager(kernel=MagicMock())
    manager._classify_from_lexicon = MagicMock(return_value="")
    manager._classify_from_keywords = AsyncMock(return_value="")
    manager._classify_from_llm = AsyncMock(side_effect=RuntimeError("llm fail"))

    result = await manager.classify_intent("co potrafisz")
    assert result == "HELP_REQUEST"


@pytest.mark.asyncio
async def test_classify_from_llm_non_system_error_returns_general_chat():
    manager = IntentManager(kernel=MagicMock())
    manager._request_intent_response = AsyncMock(side_effect=Exception("network error"))
    result = await manager._classify_from_llm("hello", "hello", "en")
    assert result == "GENERAL_CHAT"
