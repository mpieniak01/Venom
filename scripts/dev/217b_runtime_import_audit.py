#!/usr/bin/env python3
"""217B: Audit importów pakietu gemma4_audio_runtime w repozytoryrium.

Raportuje wszystkie miejsca, gdzie kod nadal importuje lub patchuje
stary pakiet services.gemma4_audio_runtime zamiast services.multi_runtime.

Uruchomienie:
  python scripts/dev/217b_runtime_import_audit.py
  python scripts/dev/217b_runtime_import_audit.py --strict  # exit 1 jeśli błędy
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

SCAN_DIRS = [
    "venom_core",
    "tests",
    "scripts",
    "services/multi_runtime",
]

# Patterns that indicate old-package usage (excluding the shim files themselves)
OLD_IMPORT_PATTERN = re.compile(
    r'(?:import|from|patch|")\s*services[.\s]*gemma4_audio_runtime'
)

# Files allowed to reference old package (the shim files themselves)
ALLOWED_FILES = {
    "services/gemma4_audio_runtime/engine.py",
    "services/gemma4_audio_runtime/main.py",
    "services/gemma4_audio_runtime/schemas.py",
    "services/gemma4_audio_runtime/audio.py",
    "services/gemma4_audio_runtime/__init__.py",
}


def scan() -> list[dict]:
    hits = []
    for scan_dir in SCAN_DIRS:
        base = REPO_ROOT / scan_dir
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            rel = str(path.relative_to(REPO_ROOT))
            if rel in ALLOWED_FILES:
                continue
            if "__pycache__" in rel:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for lineno, line in enumerate(lines, 1):
                if OLD_IMPORT_PATTERN.search(line):
                    hits.append({"file": rel, "line": lineno, "content": line.strip()})
    return hits


def main() -> None:
    parser = argparse.ArgumentParser(
        description="217B: audit importów gemma4_audio_runtime"
    )
    parser.add_argument("--strict", action="store_true", help="Exit 1 jeśli znaleziono")
    args = parser.parse_args()

    hits = scan()
    if not hits:
        print(
            "✅ 217B import audit: brak importów services.gemma4_audio_runtime poza shim."
        )
        sys.exit(0)

    print(f"⚠️  217B import audit: znaleziono {len(hits)} importów do przepisania:\n")
    for h in hits:
        print(f"  {h['file']}:{h['line']}: {h['content']}")

    if args.strict:
        sys.exit(1)


if __name__ == "__main__":
    main()
