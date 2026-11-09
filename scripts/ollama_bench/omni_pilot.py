"""Prepare reproducible multimodal pilot cases and summarize observed UI runs."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import statistics
import wave
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

from scripts.ollama_bench.lfm3_cases import _resample

DOCS = (
    Path(__file__).resolve().parents[2]
    / "venom_core"
    / "services"
    / "omni_pilot_documentation.json"
)
TARGETS = ("studio", "full")
CRITERIA = ("intent", "tool", "grounding", "speech", "history")
RED_BOTTOM = "Wyjaśnij czerwony komunikat na dole. Sprawdź w dokumentacji, co zrobić."
RED = "Sprawdź czerwony komunikat w dokumentacji. Co mam zrobić najpierw?"
TOP = "Co według dokumentacji zrobić z komunikatem na górze?"
LEFT = "Co według dokumentacji zrobić z komunikatem po lewej?"
FIRST = "A co mam sprawdzić najpierw?"
NO_CODE = "Wskaż, którego komunikatu dotyczy pytanie lub poproś o brakujący obraz."
NO_DOC = "Poinformuj, że dla tego kodu brak wpisu w dokumentacji. Nie podawaj wymyślonej instrukcji."
TOOL_ERROR = "Poinformuj, że odczyt dokumentacji się nie udał. Nie potwierdzaj sukcesu."

# Colors and coordinates are the only changed cues in the paired layouts.
RED_CARD = "#8e1d2b"
AMBER_CARD = "#654508"
BLUE_CARD = "#17457b"
SCREENS = {
    "stack": (("VEN-413", AMBER_CARD, 48, 138), ("VEN-401", RED_CARD, 48, 288)),
    "swap_code": (("VEN-401", AMBER_CARD, 48, 138), ("VEN-413", RED_CARD, 48, 288)),
    "swap_color": (("VEN-413", RED_CARD, 48, 138), ("VEN-401", BLUE_CARD, 48, 288)),
    "two_red": (("VEN-503", RED_CARD, 48, 138), ("VEN-401", RED_CARD, 48, 288)),
    "side": (("VEN-207", RED_CARD, 48, 180), ("VEN-503", BLUE_CARD, 468, 180)),
    "reverse_side": (("VEN-503", BLUE_CARD, 48, 180), ("VEN-207", RED_CARD, 468, 180)),
    "unknown_bottom": (("VEN-207", BLUE_CARD, 48, 138), ("VEN-999", RED_CARD, 48, 288)),
    "unknown_top": (("VEN-999", AMBER_CARD, 48, 138), ("VEN-413", RED_CARD, 48, 288)),
}


@dataclass(frozen=True)
class Turn:
    """Describe the input and expected behavior of one operator turn."""

    utterance: str
    screen: str | None
    code: str | None
    expected: str = ""
    tool: str = "lookup"


@dataclass(frozen=True)
class Case:
    """Group consecutive turns that share a session and evaluation scope."""

    id: str
    group: str
    turns: tuple[Turn, ...]
    scope: str = "paired"


def cases() -> tuple[Case, ...]:
    """Build stable case IDs for paired UI runs and separate control cases."""
    lookup = (
        Turn(RED_BOTTOM, "stack", "VEN-401"),
        Turn(TOP, "stack", "VEN-413"),
        Turn("Co mówi dokumentacja o kodzie VEN-503?", "side", "VEN-503"),
        Turn("Sprawdź błąd mikrofonu po lewej stronie.", "side", "VEN-207"),
        Turn("Co zrobić z drugim komunikatem? Odpowiedz krótko.", "two_red", "VEN-401"),
        Turn("Wyjaśnij błąd przesyłania obrazu z tego ekranu.", "stack", "VEN-413"),
    )
    layout = (
        Turn(RED_BOTTOM, "swap_code", "VEN-413"),
        Turn(TOP, "swap_code", "VEN-401"),
        Turn(RED, "stack", "VEN-401"),
        Turn(RED, "swap_color", "VEN-413"),
        Turn(LEFT, "side", "VEN-207"),
        Turn(LEFT, "reverse_side", "VEN-503"),
        Turn("Co zrobić z niebieskim komunikatem?", "side", "VEN-503"),
        Turn(
            "Sprawdź komunikat na dole, bez względu na kolor.", "swap_color", "VEN-401"
        ),
    )
    ambiguous = (
        Turn(RED, "two_red", None, NO_CODE, "none"),
        Turn("Sprawdź ten komunikat. Co dalej?", "stack", None, NO_CODE, "none"),
        Turn("Co zrobić z zielonym komunikatem?", "stack", None, NO_CODE, "none"),
        Turn("Sprawdź komunikat z prawej strony.", "two_red", None, NO_CODE, "none"),
        Turn(RED_BOTTOM, None, None, NO_CODE, "none"),
        Turn(
            "",
            "stack",
            None,
            "Poproś o powtórzenie pytania. Nie uruchamiaj narzędzia.",
            "none",
        ),
    )
    missing = (
        Turn(RED_BOTTOM, "unknown_bottom", "VEN-999", NO_DOC, "not_found"),
        Turn(TOP, "unknown_top", "VEN-999", NO_DOC, "not_found"),
        Turn(
            "Sprawdź w instrukcji, co oznacza VEN-999.",
            "unknown_top",
            "VEN-999",
            NO_DOC,
            "not_found",
        ),
        Turn(
            "Sprawdź drugi komunikat i powiedz, czy jest instrukcja.",
            "unknown_bottom",
            "VEN-999",
            NO_DOC,
            "not_found",
        ),
    )
    failure = tuple(
        Turn(turn.utterance, turn.screen, turn.code, TOOL_ERROR, "error")
        for turn in lookup[:4]
    )
    follow_up = (
        (lookup[0], Turn(FIRST, None, "VEN-401", tool="history")),
        (lookup[1], Turn(FIRST, None, "VEN-413", tool="history")),
        (
            lookup[2],
            Turn(
                "Ile mam odczekać?", None, "VEN-503", "Odczekaj 30 sekund.", "history"
            ),
        ),
        (
            lookup[3],
            Turn(
                "W jakim miejscu mam to sprawdzić?",
                None,
                "VEN-207",
                "Sprawdź uprawnienie w przeglądarce.",
                "history",
            ),
        ),
        (
            lookup[0],
            Turn(
                "A co zrobić, jeśli problem wróci?",
                None,
                "VEN-401",
                "Sprawdź ustawienia sesji i spróbuj zalogować się ponownie.",
                "history",
            ),
        ),
        (
            lookup[2],
            Turn(
                "Ile razy mogę ponowić żądanie?",
                None,
                "VEN-503",
                "Dokumentacja zaleca ponowić żądanie tylko raz.",
                "history",
            ),
        ),
        (lookup[0], Turn("Chodziło mi o komunikat na górze.", None, "VEN-413")),
        (lookup[3], Turn("Jednak sprawdź komunikat po prawej.", "side", "VEN-503")),
    )
    return (
        *(
            Case(f"{group}-{index:02}", group, (turn,), scope)
            for group, turns, scope in (
                ("lookup", lookup, "paired"),
                ("layout", layout, "paired"),
                ("unknown", missing, "paired"),
                ("tool-error", failure, "mock_transport"),
            )
            for index, turn in enumerate(turns, 1)
        ),
        *(
            Case(
                f"clarify-{index:02}",
                "clarify",
                (turn,),
                "paired" if turn.screen else "api_control",
            )
            for index, turn in enumerate(ambiguous, 1)
        ),
        *(
            Case(f"follow-up-{index:02}", "follow-up", turns)
            for index, turns in enumerate(follow_up, 1)
        ),
    )


def write_json(path: Path, value: object) -> None:
    """Write UTF-8 JSON for hand editing and manifest hashing."""
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def digest(path: Path) -> str:
    """Calculate the SHA-256 of the exact bytes in a generated artifact."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def render_screens(output: Path, docs: dict) -> None:
    """Render the controlled diagnostic layouts used for paired visual cues."""
    from PIL import Image, ImageDraw, ImageFont

    bold = ImageFont.truetype("DejaVuSans-Bold.ttf", 28)
    small = ImageFont.truetype("DejaVuSans.ttf", 18)
    for key, cards in SCREENS.items():
        image = Image.new("RGB", (880, 480), "#131d2a")
        draw = ImageDraw.Draw(image)
        draw.text((48, 35), "Venom · Panel diagnostyczny", font=bold, fill="white")
        draw.text((48, 77), "Komunikaty systemowe", font=small, fill="#ccd9e7")
        for code, color, x, y in cards:
            draw.rounded_rectangle((x, y, x + 360, y + 105), radius=10, fill=color)
            draw.text((x + 17, y + 15), code, font=bold, fill="white")
            title = docs.get(code, {}).get("title", "VEN-999 · Weryfikacja nieudana")
            draw.text(
                (x + 17, y + 61), title.split(" · ", 1)[1], font=small, fill="white"
            )
        image.save(output / f"{key}.png")


def render_audio(
    output: Path, cases_to_run: tuple[Case, ...], model: Path
) -> dict[str, str]:
    """Render one mono WAV per distinct utterance, including silence for an empty turn."""

    from piper import PiperVoice
    from piper.config import SynthesisConfig

    voice = PiperVoice.load(model)
    config = SynthesisConfig(noise_scale=0, noise_w_scale=0)
    audio = {}
    for text in dict.fromkeys(
        turn.utterance for case in cases_to_run for turn in case.turns
    ):
        name = f"question-{len(audio) + 1:02}.wav"
        if text:
            buffer = io.BytesIO()
            with wave.open(buffer, "wb") as wav:
                voice.synthesize_wav(text, wav, config)
            _resample(buffer.getvalue(), output / name)
        else:
            with wave.open(str(output / name), "wb") as wav:
                wav.setparams((1, 2, 16000, 0, "NONE", "not compressed"))
                wav.writeframes(bytes(64000))
        audio[text] = name
    return audio


def turn_spec(turn: Turn, audio: dict[str, str], docs: dict) -> dict:
    """Resolve media filenames and expected documentation evidence for a turn."""
    spec = asdict(turn)
    spec["audio"] = audio[turn.utterance]
    spec["image"] = f"{turn.screen}.png" if turn.screen else None
    spec["expected"] = (
        turn.expected or docs[turn.code]["content"].split(". ", 1)[0] + "."
    )
    if turn.tool in {"lookup", "history"}:
        spec["source"] = docs[turn.code]["title"]
    return spec


def result_template(manifest: Path, suite: list[dict]) -> dict:
    """Allocate paired results bound to the manifest bytes and the required turn checks."""
    return {
        "manifest_sha256": digest(manifest),
        "build": None,
        "model": None,
        "runtime": None,
        "rows": [
            {
                "target": target,
                "case": case["id"],
                "turns": [
                    {
                        "checks": {
                            key: None
                            for key in CRITERIA
                            if key != "history" or index > 0
                        },
                        "latency_ms": None,
                        "trace": None,
                        "error": None,
                    }
                    for index, _ in enumerate(case["turns"])
                ],
            }
            for target in TARGETS
            for case in suite
            if case["scope"] == "paired"
        ],
    }


def prepare(output: Path, voice_model: Path) -> None:
    """Freeze media and documentation with a manifest and a blank results template."""
    docs = json.loads(DOCS.read_text(encoding="utf-8"))
    voice_config = voice_model.with_suffix(".onnx.json")
    voice_hash = digest(voice_model)
    config_hash = digest(voice_config)
    case_set = cases()
    output.mkdir(parents=True)
    render_screens(output, docs)
    audio = render_audio(output, case_set, voice_model)
    doc_copy = output / DOCS.name
    doc_copy.write_bytes(DOCS.read_bytes())
    suite = [
        {
            "id": case.id,
            "group": case.group,
            "scope": case.scope,
            "turns": [turn_spec(turn, audio, docs) for turn in case.turns],
        }
        for case in case_set
    ]
    manifest = output / "manifest.json"
    write_json(
        manifest,
        {
            "version": 1,
            "voice": {
                "kind": "synthetic-piper",
                "model_sha256": voice_hash,
                "config_sha256": config_hash,
            },
            "files": {path.name: digest(path) for path in sorted(output.iterdir())},
            "cases": suite,
        },
    )
    write_json(output / "results-template.json", result_template(manifest, suite))


def turn_status(turn: dict) -> str:
    """Treat errors or failed criteria as failures and ungraded turns as pending."""
    if turn["error"] or any(value is False for value in turn["checks"].values()):
        return "fail"
    return (
        "pass" if all(value is True for value in turn["checks"].values()) else "pending"
    )


def summarize(manifest_path: Path, results_path: Path) -> dict:
    """Validate observed turns and aggregate outcomes and latency by interface."""
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    expected = result_template(manifest_path, manifest["cases"])
    if results["manifest_sha256"] != expected["manifest_sha256"]:
        raise ValueError("results manifest hash mismatch")
    required = {(row["target"], row["case"]): row["turns"] for row in expected["rows"]}
    observed = {(row["target"], row["case"]): row["turns"] for row in results["rows"]}
    if set(observed) != set(required) or len(results["rows"]) != len(required):
        raise ValueError(
            "results must include exactly one row for each target and paired case"
        )
    groups = {case["id"]: case["group"] for case in manifest["cases"]}
    report = {"run": {name: results[name] for name in ("build", "model", "runtime")}}
    statuses = {}
    for target in TARGETS:
        counts: Counter[str] = Counter()
        by_group: dict[str, Counter[str]] = {}
        timings = []
        for key, turns in observed.items():
            if key[0] != target:
                continue
            for observed_turn, required_turn in zip(turns, required[key], strict=True):
                checks = observed_turn["checks"]
                if checks.keys() != required_turn["checks"].keys() or any(
                    value is not None and type(value) is not bool
                    for value in checks.values()
                ):
                    raise ValueError(f"invalid checks: {key}")
                timing = observed_turn["latency_ms"]
                if timing is not None:
                    if (
                        type(timing) not in {int, float}
                        or not math.isfinite(timing)
                        or timing < 0
                    ):
                        raise ValueError(f"invalid latency: {key}")
                    timings.append(timing)
                if (
                    turn_status(observed_turn) != "pending"
                    and not observed_turn["trace"]
                ):
                    raise ValueError(f"missing evidence reference: {key}")
            flags = {turn_status(turn) for turn in turns}
            status = (
                "fail"
                if "fail" in flags
                else ("pending" if "pending" in flags else "pass")
            )
            statuses[key] = status
            counts[status] += 1
            by_group.setdefault(groups[key[1]], Counter())[status] += 1
        timings.sort()
        report[target] = {
            "cases": dict(counts),
            "groups": by_group,
            "latency_samples": len(timings),
            "median_ms": statistics.median(timings) if timings else None,
            "p95_ms": timings[math.ceil(0.95 * len(timings)) - 1] if timings else None,
        }
    if any(status != "pending" for status in statuses.values()) and not all(
        report["run"].values()
    ):
        raise ValueError(
            "observed results require build, model, and runtime identities"
        )
    report["paired"] = dict(
        Counter(
            f"{statuses['studio', case]}/{statuses['full', case]}"
            for target, case in required
            if target == "studio"
        )
    )
    return report


def main() -> None:
    """Dispatch media preparation or emit a JSON report from completed measurements."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    generate = commands.add_parser("prepare")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--piper-model", type=Path, required=True)
    report = commands.add_parser("summarize")
    report.add_argument("manifest", type=Path)
    report.add_argument("results", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.output, args.piper_model)
    else:
        print(
            json.dumps(
                summarize(args.manifest, args.results), ensure_ascii=False, indent=2
            )
        )


if __name__ == "__main__":
    main()
