"""Controlled prompts and synthetic media for the local LFM3 evaluation."""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

PL = "W szafie stoją trzy czerwone pudełka, a na biurku leży klucz."
EN = "The green parcel is beside the door. Please leave it there."
INTENT = "Zatrzymaj nagrywanie i zapisz ostatnie zdjęcie."
VISION_QUESTION = "Jaki kolor ma koło po prawej stronie? Podaj sam kolor."
TTS_TEXTS = (
    "Proszę położyć żółtą książkę na półce.",
    "W Szczebrzeszynie chrząszcz brzmi w trzcinie.",
    "Spotkajmy się jutro o ósmej przy wejściu.",
)

SCHEMA = {
    "type": "object",
    "properties": {"count": {"type": "integer"}, "ready": {"type": "boolean"}},
    "required": ["count", "ready"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Case:
    id: str
    prompt: str
    expected: str
    media: tuple[str, ...] = ()
    system: str = ""


TEXT = (
    Case(
        "T01",
        "Odpowiedz pełnym zdaniem po polsku: gdzie leży klucz? Klucz leży pod krzesłem.",
        "Pełne zdanie po polsku: pod krzesłem.",
    ),
    Case(
        "T02",
        "Answer in a full English sentence: where is the key? The key is under the chair.",
        "A full English sentence: under the chair.",
    ),
    Case(
        "T03",
        "Start with 7. Double it, subtract 2, then divide by 3. Reply with the three intermediate results separated by commas.",
        "14, 12, 4 in order.",
    ),
    Case(
        "T04",
        "Return a JSON object with count equal to 3 and ready equal to false.",
        '{"count": 3, "ready": false} with correct types.',
    ),
    Case(
        "T05",
        "Use the tool to look up the color of item VEN-42, then report only the color from the tool response.",
        "lookup_item(item_id=VEN-42), then indigo from the fixture.",
    ),
    Case(
        "T06",
        'What exception does int("abc") raise in Python and why? One sentence.',
        "ValueError, since abc cannot be parsed as an integer.",
    ),
    Case(
        "T07",
        "Give exactly two command lines, no execution: list changed tracked paths relative to HEAD, then print the current working directory.",
        "git diff --name-only HEAD (or equivalent), then pwd.",
    ),
    Case(
        "T08",
        "Ada is older than Bo. Bo is older than Cy. Who is the youngest? Reply with the name only.",
        "Cy.",
    ),
    Case(
        "T09",
        "What is the label I asked you to remember? Reply with the label only.",
        "mewa-73 from the earlier turn.",
    ),
    Case(
        "T10",
        "What is the exact temperature in my living room now? Say whether you can verify it. No sensor reading is available.",
        "Explicit inability to verify and no invented value or tool result.",
    ),
    Case(
        "T11",
        "Reply with exactly one word and exactly three words at the same time. If the requirements conflict, explain why.",
        "Identify the mutually exclusive word counts.",
    ),
    Case(
        "T12",
        "Write the next three even numbers after 10, in ascending order, and nothing else.",
        "12, 14, 16 in order.",
    ),
)

MEDIA = (
    Case("M01", TEXT[0].prompt, TEXT[0].expected),
    Case(
        "M02",
        "Jakie dwa kształty widać na obrazie? Podaj ich kolory.",
        "Czerwony kwadrat i niebieskie koło.",
        ("scene.png",),
    ),
    Case("M03", VISION_QUESTION, "Niebieski.", ("scene.png",)),
    Case("M04", "Przepisz dokładnie napis na obrazie.", "VENOM 42", ("scene.png",)),
    Case("M05", "", PL, ("pl.wav",), "Perform ASR in Polish."),
    Case("M06", "", EN, ("en.wav",), "Perform ASR in English."),
    Case(
        "M09",
        "Podaj obie czynności z nagrania jako tekst. Niczego nie wykonuj.",
        "Zatrzymać nagrywanie i zapisać ostatnie zdjęcie.",
        ("intent.wav",),
    ),
    Case(
        "M10",
        "Odpowiedz po polsku na pytanie z nagrania, używając obrazu.",
        "Niebieski.",
        ("scene.png", "question.wav"),
    ),
    Case(
        "M11",
        "What colors appear in the video and in which order?",
        "Red first, then blue.",
        ("silent.mp4",),
    ),
    Case(
        "M12",
        "What colors appear in order and during which color is the tone audible?",
        "Red then blue, tone only during blue.",
        ("sound.mp4",),
    ),
    Case(
        "M15",
        "Describe the sound briefly without inventing a source.",
        "Two short tones/beeps, no speech.",
        ("beeps.wav",),
    ),
    Case(
        "M16",
        "Czy na nagraniu słychać mowę i czy otrzymałeś obraz? Odpowiedz tekstem.",
        "Brak mowy, brak obrazu.",
        ("silence.wav",),
    ),
    Case(
        "M16-noise",
        "Czy na nagraniu słychać mowę i czy otrzymałeś obraz? Odpowiedz tekstem.",
        "Szum, brak mowy, brak obrazu.",
        ("noise.wav",),
    ),
)


def ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y", *args],
        check=True,
        timeout=60,
    )


def make_fixtures(directory: Path, piper_model: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    directory.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (448, 280), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((55, 48, 169, 162), fill="#ed2020")
    draw.ellipse((280, 48, 394, 162), fill="#165fff")
    font = ImageFont.truetype("DejaVuSans-Bold.ttf", 44)
    draw.text((224, 218), "VENOM 42", font=font, fill="black", anchor="mm")
    image.save(directory / "scene.png")
    references = {"pl": PL, "en": EN, "intent": INTENT, "question": VISION_QUESTION}
    (directory / "references.json").write_text(
        json.dumps(references, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for name in ("pl", "intent", "question"):
        piper_output = subprocess.run(
            [
                sys.executable,
                "-m",
                "piper",
                "-m",
                str(piper_model),
                "-f",
                "-",
                "--noise-scale",
                "0",
                "--noise-w-scale",
                "0",
            ],
            input=references[name].encode(),
            stdout=subprocess.PIPE,
            check=True,
            timeout=60,
        ).stdout
        _resample(piper_output, directory / f"{name}.wav")
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        f"flite=text={EN}:voice=slt",
        "-ar",
        "16000",
        str(directory / "en.wav"),
    )
    for name, source in {
        "silence": "anullsrc=r=16000:cl=mono",
        "noise": "anoisesrc=r=16000:a=0.12:s=26",
        "beeps": "aevalsrc=0.2*sin(2*PI*660*t)*between(t\\,0.25\\,0.55)+0.2*sin(2*PI*440*t)*between(t\\,1.25\\,1.55):s=16000",
    }.items():
        ffmpeg("-f", "lavfi", "-i", source, "-t", "2", str(directory / f"{name}.wav"))
    ffmpeg(
        "-f",
        "lavfi",
        "-i",
        "color=red:s=320x240:r=8:d=3",
        "-f",
        "lavfi",
        "-i",
        "color=blue:s=320x240:r=8:d=3",
        "-filter_complex",
        "[0:v][1:v]concat=n=2:v=1:a=0",
        "-pix_fmt",
        "yuv420p",
        str(directory / "silent.mp4"),
    )
    ffmpeg(
        "-i",
        str(directory / "silent.mp4"),
        "-f",
        "lavfi",
        "-i",
        "sine=f=660:r=16000:d=3",
        "-af",
        "adelay=3000",
        "-c:v",
        "copy",
        "-shortest",
        str(directory / "sound.mp4"),
    )


def _resample(wav: bytes, output: Path) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            "pipe:0",
            "-ar",
            "16000",
            "-ac",
            "1",
            str(output),
        ],
        input=wav,
        check=True,
        timeout=60,
    )
