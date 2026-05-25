"""Helpers for voice reasoning and emotion metadata."""

from __future__ import annotations

import re
from typing import Any, Literal

EmotionLabel = Literal[
    "neutral",
    "curious",
    "frustrated",
    "confused",
    "positive",
    "urgent",
    "calm",
]
EmotionSource = Literal["none", "transcript", "response", "hybrid"]
ReasoningStatus = Literal["disabled", "summary", "raw_available"]
VoiceSessionMode = Literal["native_audio", "whisper_llm_piper", "unknown"]
VoiceTraceStageStatus = Literal["active", "no-op", "disabled", "unknown"]

EMOTION_BASELINE_SCORES: dict[EmotionLabel, float] = {
    "neutral": 0.1,
    "curious": 0.0,
    "frustrated": 0.0,
    "confused": 0.0,
    "positive": 0.0,
    "urgent": 0.0,
    "calm": 0.0,
}

EMOTION_KEYWORD_SETS: dict[EmotionLabel, tuple[str, ...]] = {
    "frustrated": (
        "nie działa",
        "problem",
        "błąd",
        "blad",
        "masakra",
        "zawiesza",
        "wolniej",
        "wolny",
        "zły",
        "zla",
    ),
    "confused": (
        "nie rozumiem",
        "nie wiem",
        "co to",
        "dlaczego",
        "jak to",
        "o co chodzi",
    ),
    "curious": (
        "?",
        "jak",
        "dlaczego",
        "czy",
        "możesz",
        "mozesz",
        "sprawdź",
        "sprawdz",
    ),
    "positive": (
        "dzięki",
        "super",
        "świetnie",
        "swietnie",
        "ok",
        "dobrze",
        "fajnie",
    ),
    "urgent": ("pilne", "natychmiast", "szybko", "teraz", "już", "juz"),
    "calm": (
        "spokojnie",
        "dobrze",
        "w porządku",
        "w porzadku",
        "wystarczy",
        "cicho",
    ),
}


def _normalize_text(value: str | None) -> str:
    return str(value or "").strip().lower()


def _contains_keyword(text: str, keyword: str) -> bool:
    if not keyword:
        return False
    if keyword == "?":
        return "?" in text
    pattern = rf"(?<!\w){re.escape(keyword)}(?!\w)"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _resolve_emotion_source(transcript_text: str, response_text: str) -> EmotionSource:
    if transcript_text and response_text:
        return "hybrid"
    if transcript_text:
        return "transcript"
    return "response"


def infer_voice_session_mode(
    *,
    voice_pipeline_mode: str | None = None,
    pipeline_id: str | None = None,
    decoder_source: str | None = None,
    native_audio_ms: float | None = None,
) -> VoiceSessionMode:
    pipeline_mode = _normalize_text(voice_pipeline_mode)
    if pipeline_mode == "native_multi_runtime":
        return "native_audio"
    if pipeline_mode == "whisper_llm_piper":
        return "whisper_llm_piper"

    pipeline = _normalize_text(pipeline_id)
    decoder = _normalize_text(decoder_source)
    if pipeline == "multi_runtime_piper" or decoder == "multi_runtime":
        return "native_audio"
    if pipeline == "whisper_llm_piper" or decoder == "faster_whisper":
        return "whisper_llm_piper"
    if native_audio_ms is not None:
        return "native_audio"
    return "unknown"


def _voice_trace_stage_label(stage: str) -> str:
    return {
        "input_router": "Input router",
        "image_preprocessor": "Image preprocessor",
        "ocr_or_vision": "OCR / vision",
        "retrieval": "Retrieval",
        "main_generation": "Main generation",
        "assistant_postprocess": "Assistant postprocess",
        "audio_output": "Audio output",
    }.get(stage, stage.replace("_", " ").title())


def build_voice_trace_annotations(
    execution_trace: list[str] | tuple[str, ...] | None = None,
    *,
    voice_pipeline_mode: str | None = None,
    pipeline_id: str | None = None,
    decoder_source: str | None = None,
    native_audio_ms: float | None = None,
) -> list[dict[str, Any]]:
    """Build readable trace annotations for voice-only sessions."""

    trace = [
        str(stage or "").strip()
        for stage in list(execution_trace or [])
        if str(stage or "").strip()
    ]
    if not trace:
        return []

    mode = infer_voice_session_mode(
        voice_pipeline_mode=voice_pipeline_mode,
        pipeline_id=pipeline_id,
        decoder_source=decoder_source,
        native_audio_ms=native_audio_ms,
    )
    audio_only = mode in {"native_audio", "whisper_llm_piper"}
    annotations: list[dict[str, Any]] = []
    for stage in trace:
        status: VoiceTraceStageStatus = "active"
        note: str | None = None
        if audio_only and stage in {"image_preprocessor", "ocr_or_vision", "retrieval"}:
            status = "no-op"
            note = "audio-only voice session"
        elif audio_only and stage == "input_router":
            note = "audio input routed"
        elif stage == "main_generation":
            note = "Gemma response"
        elif stage == "assistant_postprocess":
            note = "response shaping"
        elif stage == "audio_output":
            note = "tts output"

        annotations.append(
            {
                "stage": stage,
                "label": _voice_trace_stage_label(stage),
                "status": status,
                "note": note,
            }
        )
    return annotations


def _apply_keyword_scores(combined: str, scores: dict[EmotionLabel, float]) -> None:
    for label, keywords in EMOTION_KEYWORD_SETS.items():
        for keyword in keywords:
            if keyword == "?":
                scores["curious"] += combined.count("?") * 0.25
            elif _contains_keyword(combined, keyword):
                scores[label] += 0.6 if len(keyword) > 3 else 0.2


def infer_voice_emotion(
    transcript: str = "",
    response: str = "",
) -> tuple[EmotionLabel, float, EmotionSource]:
    """Infer a lightweight emotion label from voice text.

    The goal is observability and UI hints, not a formal sentiment model.
    """

    transcript_text = _normalize_text(transcript)
    response_text = _normalize_text(response)
    combined = " ".join(
        part for part in (transcript_text, response_text) if part
    ).strip()
    if not combined:
        return "neutral", 0.0, "none"

    scores: dict[EmotionLabel, float] = dict(EMOTION_BASELINE_SCORES)
    _apply_keyword_scores(combined, scores)

    if "!" in combined:
        scores["urgent"] += min(0.5, combined.count("!") * 0.15)

    source = _resolve_emotion_source(transcript_text, response_text)

    label = max(scores, key=lambda emotion: scores[emotion])
    confidence = max(scores.values())
    if confidence <= 0.1:
        return "neutral", 0.15, source
    return label, min(0.99, round(0.35 + confidence, 2)), source


def build_voice_reasoning_summary(
    *,
    transcript: str = "",
    response: str = "",
    voice_mode: str = "standard",
    pipeline_id: str | None = None,
    raw_thinking_available: bool = False,
    reasoning_summary_enabled: bool = False,
    emotion_label: EmotionLabel = "neutral",
) -> str | None:
    """Build a short, user-facing reasoning summary for diagnostics."""

    if not raw_thinking_available and not reasoning_summary_enabled:
        return None

    pieces: list[str] = []
    mode = str(voice_mode or "standard").strip() or "standard"
    pipeline = str(pipeline_id or "").strip()
    if pipeline:
        pieces.append(f"pipeline={pipeline}")
    pieces.append(f"mode={mode}")

    transcript_text = transcript.strip()
    response_text = response.strip()
    if transcript_text:
        pieces.append(f"input={transcript_text[:96]}")
    if response_text:
        pieces.append(f"output={response_text[:96]}")
    if emotion_label != "neutral":
        pieces.append(f"emotion={emotion_label}")
    if raw_thinking_available:
        pieces.append("thinking=available")
    if reasoning_summary_enabled:
        pieces.append("summary=enabled")
    return " | ".join(pieces)


def build_voice_session_insights(
    *,
    transcript: str = "",
    response: str = "",
    voice_mode: str = "standard",
    pipeline_id: str | None = None,
    reasoning_summary_enabled: bool = False,
    emotion_detection_enabled: bool = False,
    emotion_response_style_enabled: bool = False,
    raw_thinking_available: bool = False,
) -> dict[str, Any]:
    """Build a compact metadata payload for voice session observability."""

    emotion_label: EmotionLabel = "neutral"
    emotion_confidence: float | None = None
    emotion_source: EmotionSource = "none"
    if emotion_detection_enabled:
        emotion_label, emotion_confidence, emotion_source = infer_voice_emotion(
            transcript,
            response,
        )

    summary = build_voice_reasoning_summary(
        transcript=transcript,
        response=response,
        voice_mode=voice_mode,
        pipeline_id=pipeline_id,
        raw_thinking_available=raw_thinking_available,
        reasoning_summary_enabled=reasoning_summary_enabled,
        emotion_label=emotion_label,
    )

    reasoning_summary_status: ReasoningStatus = "disabled"
    if raw_thinking_available:
        reasoning_summary_status = "raw_available"
    elif reasoning_summary_enabled or emotion_detection_enabled:
        reasoning_summary_status = "summary"

    return {
        "reasoning_summary_enabled": reasoning_summary_enabled,
        "reasoning_summary_status": reasoning_summary_status,
        "reasoning_summary": summary,
        "raw_thinking_available": raw_thinking_available,
        "emotion_detection_enabled": emotion_detection_enabled,
        "emotion_response_style_enabled": emotion_response_style_enabled,
        "emotion_source": emotion_source,
        "emotion_label": emotion_label if emotion_detection_enabled else None,
        "emotion_confidence": emotion_confidence if emotion_detection_enabled else None,
    }
