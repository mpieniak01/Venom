from __future__ import annotations

from venom_core.utils.voice_metadata import (
    build_voice_reasoning_summary,
    build_voice_session_insights,
    build_voice_trace_annotations,
    infer_voice_emotion,
    infer_voice_session_mode,
)


def test_infer_voice_emotion_returns_neutral_for_empty_text():
    label, confidence, source = infer_voice_emotion("", "")

    assert label == "neutral"
    assert confidence == 0.0
    assert source == "none"


def test_infer_voice_emotion_detects_question_as_confusion():
    label, confidence, source = infer_voice_emotion(
        transcript="Co to jest kwadrat?",
        response="To figura geometryczna.",
    )

    assert label == "confused"
    assert confidence > 0.15
    assert source == "hybrid"


def test_infer_voice_emotion_avoids_false_positive_on_short_substrings():
    label, confidence, source = infer_voice_emotion(
        transcript="To jest okno, a nie zagadka.",
        response="Terazyk to tylko przykład.",
    )

    assert label == "neutral"
    assert confidence == 0.15
    assert source == "hybrid"


def test_infer_voice_emotion_detects_frustration_from_keywords():
    label, confidence, source = infer_voice_emotion(
        transcript="To nie dziala, mam problem i wszystko sie zawiesza.",
        response="",
    )

    assert label == "frustrated"
    assert confidence > 0.4
    assert source == "transcript"


def test_infer_voice_emotion_uses_response_source_when_no_transcript():
    label, confidence, source = infer_voice_emotion(
        transcript="",
        response="Super, dzięki!",
    )

    assert label == "positive"
    assert confidence > 0.15
    assert source == "response"


def test_infer_voice_emotion_marks_urgency_from_exclamation_marks():
    label, confidence, source = infer_voice_emotion(
        transcript="To jest pilne!!!",
        response="",
    )

    assert label == "urgent"
    assert confidence > 0.5
    assert source == "transcript"


def test_build_voice_reasoning_summary_returns_none_when_disabled():
    assert build_voice_reasoning_summary() is None


def test_build_voice_reasoning_summary_includes_enabled_fields():
    summary = build_voice_reasoning_summary(
        transcript="Ile to jest dwa razy dwa?",
        response="Dwa razy dwa to cztery.",
        voice_mode="summary",
        pipeline_id="gemma4_audio_piper",
        raw_thinking_available=True,
        reasoning_summary_enabled=True,
        emotion_label="curious",
    )

    assert summary is not None
    assert "pipeline=gemma4_audio_piper" in summary
    assert "mode=summary" in summary
    assert "input=Ile to jest dwa razy dwa?" in summary
    assert "output=Dwa razy dwa to cztery." in summary
    assert "emotion=curious" in summary
    assert "thinking=available" in summary
    assert "summary=enabled" in summary


def test_build_voice_session_insights_reports_reasoning_and_emotion():
    payload = build_voice_session_insights(
        transcript="To nie dziala, masakra, wszystko sie zawiesza.",
        response="",
        voice_mode="deep",
        pipeline_id="gemma4_audio_native",
        reasoning_summary_enabled=True,
        emotion_detection_enabled=True,
        emotion_response_style_enabled=True,
        raw_thinking_available=False,
    )

    assert payload["reasoning_summary_enabled"] is True
    assert payload["reasoning_summary_status"] == "summary"
    assert payload["raw_thinking_available"] is False
    assert payload["emotion_detection_enabled"] is True
    assert payload["emotion_response_style_enabled"] is True
    assert payload["emotion_label"] == "frustrated"
    assert payload["emotion_confidence"] is not None
    assert payload["emotion_source"] == "transcript"
    assert payload["reasoning_summary"] is not None


def test_build_voice_session_insights_prefers_raw_thinking_status():
    payload = build_voice_session_insights(
        transcript="",
        response="",
        voice_mode="standard",
        pipeline_id="gemma4_audio_native",
        reasoning_summary_enabled=False,
        emotion_detection_enabled=False,
        emotion_response_style_enabled=False,
        raw_thinking_available=True,
    )

    assert payload["reasoning_summary_status"] == "raw_available"
    assert payload["reasoning_summary"] is not None
    assert payload["emotion_label"] is None
    assert payload["emotion_confidence"] is None
    assert payload["emotion_source"] == "none"


def test_infer_voice_session_mode_prefers_native_audio_for_multi_runtime():
    assert (
        infer_voice_session_mode(
            voice_pipeline_mode="native_multi_runtime",
            pipeline_id="multi_runtime_piper",
            decoder_source="multi_runtime",
            native_audio_ms=1234.0,
        )
        == "native_audio"
    )


def test_build_voice_trace_annotations_marks_audio_only_no_ops():
    annotations = build_voice_trace_annotations(
        [
            "input_router",
            "image_preprocessor",
            "ocr_or_vision",
            "retrieval",
            "main_generation",
            "assistant_postprocess",
            "audio_output",
        ],
        voice_pipeline_mode="native_multi_runtime",
        pipeline_id="multi_runtime_piper",
        decoder_source="multi_runtime",
        native_audio_ms=1234.0,
    )

    assert [item["status"] for item in annotations[:4]] == [
        "active",
        "no-op",
        "no-op",
        "no-op",
    ]
    assert annotations[4]["note"] == "Gemma response"
    assert annotations[5]["note"] == "response shaping"
    assert annotations[6]["note"] == "tts output"
