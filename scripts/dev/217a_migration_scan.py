#!/usr/bin/env python3
"""217A: Skan repo pod pozostałe twarde wystąpienia 'gemma4_audio' w warstwach publicznych.

Uruchamiaj przed i po przepisaniu nazwy:
  python scripts/dev/217a_migration_scan.py
  python scripts/dev/217a_migration_scan.py --strict   # exit 1 jeśli zostały publiczne

Zwraca raport JSON do stdout i raport tekstowy na stderr.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

# Warstwy publiczne — pliki, w których 'gemma4_audio' nie powinno już wystąpić
# jako kontrakt publiczny po zakończeniu fazy I.
PUBLIC_LAYERS = [
    "venom_core/utils/llm_runtime.py",
    "venom_core/core/model_registry_runtime.py",
    "venom_core/core/llm_server_controller.py",
    "venom_core/services/system_llm_service.py",
    "venom_core/api/routes/system_llm.py",
    "venom_core/api/audio_stream.py",
    "venom_core/main.py",
    "web-next/components/models/hooks/use-runtime.ts",
    "web-next/components/voice/voice-status-sidebar.tsx",
    "web-next/components/cockpit/cockpit-models.tsx",
    "web-next/components/cockpit/cockpit-section-props.ts",
    "web-next/components/voice/dev-diagnostics-drawer.tsx",
]

# Wzorzec — twarde porównanie lub publiczny string (nie komentarz, nie zmienna wewnętrzna)
PATTERN = "gemma4_audio"

# Ignorowane konteksty wewnętrzne — OK żeby zostały
ALLOWED_INTERNAL = [
    "GEMMA4_AUDIO_",  # config keys (wewnętrzne env vars)
    "_gemma4_audio_",  # prywatne metody/funkcje
    "gemma4_audio_models",  # serwis modeli (plik wewnętrzny)
    "gemma4_audio_service",  # skrypt systemu
    "gemma4_audio_available_models",
    "# gemma4_audio",  # komentarze
    '"gemma4_audio_service',  # skrypty powłoki
]


def grep_file(path: Path) -> list[dict]:
    hits = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return hits
    for lineno, line in enumerate(lines, 1):
        if PATTERN not in line:
            continue
        stripped = line.strip()
        if any(allowed in line for allowed in ALLOWED_INTERNAL):
            continue
        hits.append(
            {
                "file": str(path.relative_to(REPO_ROOT)),
                "line": lineno,
                "content": stripped,
            }
        )
    return hits


def run_scan() -> dict:
    results: dict[str, list[dict]] = {}
    for rel in PUBLIC_LAYERS:
        path = REPO_ROOT / rel
        if not path.exists():
            continue
        hits = grep_file(path)
        if hits:
            results[rel] = hits
    return results


def main() -> None:
    parser = argparse.ArgumentParser(
        description="217A: skan publicznych warstw pod gemma4_audio"
    )
    parser.add_argument(
        "--strict", action="store_true", help="Exit 1 jeśli znaleziono wystąpienia"
    )
    parser.add_argument("--json-output", help="Zapisz raport do pliku JSON")
    args = parser.parse_args()

    hits = run_scan()
    total = sum(len(v) for v in hits.values())

    report = {"total_hits": total, "files": hits}
    if args.json_output:
        Path(args.json_output).write_text(
            json.dumps(report, indent=2, ensure_ascii=False)
        )

    json.dump(report, sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")

    if total == 0:
        print(
            "\n✅ 217A scan: brak publicznych wystąpień 'gemma4_audio' — migracja zakończona.",
            file=sys.stderr,
        )
        sys.exit(0)
    else:
        print(
            f"\n⚠️  217A scan: znaleziono {total} publicznych wystąpień 'gemma4_audio' do przepisania:",
            file=sys.stderr,
        )
        for f, lines in hits.items():
            for hit in lines:
                print(
                    f"  {hit['file']}:{hit['line']}: {hit['content']}", file=sys.stderr
                )
        if args.strict:
            sys.exit(1)


if __name__ == "__main__":
    main()
