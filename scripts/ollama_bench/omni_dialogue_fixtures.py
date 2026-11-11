"""Render and verify the offline Polish Omni dialogue fixtures."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from scripts.ollama_bench.omni_pilot import digest, write_json
from scripts.ollama_bench.polish_benchmark import render_audio, render_image
from scripts.ollama_bench.polish_cases import Scenario

CASES = Path(__file__).with_name("omni_dialogue_cases.json")
LOCK = Path(__file__).with_name("omni_dialogue.lock.json")
GROUPS = {"speech": 12, "vision": 12, "context": 12, "clarify": 12}


def _definitions() -> dict:
    data = json.loads(CASES.read_text(encoding="utf-8"))
    cases = data["cases"]
    if Counter(case["group"] for case in cases) != GROUPS:
        raise ValueError("Expected 12 scenarios per dialogue group")
    if len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Duplicate dialogue scenario ID")
    return data


def prepare(folder: Path, voices: list[Path], font: Path) -> Path:
    """Materialize a new local folder. Nothing here is input to training."""
    from piper import PiperVoice

    if len({digest(path) for path in voices}) != 2:
        raise ValueError("Use two distinct voices")
    renderers = [PiperVoice.load(path, use_cuda=False) for path in voices]
    definition = _definitions()
    folder.mkdir(parents=True)
    media: dict[str, str] = {}
    cases = definition["cases"]
    family_indices = {
        family: index % len(voices)
        for index, family in enumerate(
            dict.fromkeys((case["group"], case["family"]) for case in cases)
        )
    }
    for case in cases:
        index = family_indices[case["group"], case["family"]]
        case["voice_index"] = index
        for number, turn in enumerate(case["turns"], start=1):
            stem = f"{case['id']}-{number}"
            scene = turn.get("scene") or {}
            scenario = Scenario(
                id=stem,
                group=case["group"],
                family=case["family"],
                prompt=turn["prompt"],
                expected=tuple(case["expected"]),
                scene=tuple(tuple(card) for card in scene.get("cards", ())),
                scene_title=scene.get("title", ""),
            )
            audio = folder / f"{stem}.wav"
            render_audio(scenario, audio, renderers[index])
            turn["wav"] = audio.name
            media[audio.name] = digest(audio)
            if scenario.scene:
                image = folder / f"{stem}.png"
                render_image(scenario, image, font)
                turn["image"] = image.name
                media[image.name] = digest(image)
    manifest = folder / "manifest.json"
    write_json(
        manifest,
        {
            **definition,
            "case_definition_sha256": digest(CASES),
            "recording_origin": "synthetic",
            "voices": [
                {
                    "name": path.name,
                    "sha256": digest(path),
                    "config_sha256": digest(Path(str(path) + ".json")),
                }
                for path in voices
            ],
            "font_sha256": digest(font),
            "media_sha256": media,
        },
    )
    return manifest


def verify(folder: Path) -> dict:
    manifest = folder / "manifest.json"
    locked = json.loads(LOCK.read_text(encoding="utf-8"))
    if digest(manifest) != locked["manifest_sha256"]:
        raise ValueError("Dialogue fixture manifest does not match the frozen version")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if data["case_definition_sha256"] != digest(CASES):
        raise ValueError("Dialogue case definitions changed after freezing")
    for name, checksum in data["media_sha256"].items():
        path = folder / name
        if Path(name).name != name or path.is_symlink() or digest(path) != checksum:
            raise ValueError(f"Invalid dialogue fixture: {name}")
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    render = commands.add_parser("prepare")
    render.add_argument("folder", type=Path)
    render.add_argument("--voice", type=Path, action="append", required=True)
    render.add_argument("--font", type=Path, required=True)
    check = commands.add_parser("verify")
    check.add_argument("folder", type=Path)
    args = parser.parse_args()
    if args.action == "prepare":
        if len(args.voice) != 2:
            parser.error("Provide exactly two --voice paths")
        manifest = prepare(args.folder, args.voice, args.font)
        print(digest(manifest))
    else:
        manifest = verify(args.folder)
        print(
            f"{len(manifest['cases'])} cases, {len(manifest['media_sha256'])} verified assets"
        )


if __name__ == "__main__":
    main()
