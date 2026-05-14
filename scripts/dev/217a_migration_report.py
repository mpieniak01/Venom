#!/usr/bin/env python3
"""217A: Raport stanu migracji — agreguje wyniki scan + validate w jednym podsumowaniu.

python scripts/dev/217a_migration_report.py
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts/dev"


def run_script(name: str, extra: list[str] | None = None) -> tuple[int, str, str]:
    cmd = [sys.executable, str(SCRIPTS / name)] + (extra or [])
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    return result.returncode, result.stdout, result.stderr


def main() -> None:
    print("=" * 60)
    print("217A — Raport stanu migracji multi_runtime")
    print("=" * 60)

    # 1. Skan
    print("\n[1/2] Skan warstw publicznych (gemma4_audio):")
    rc_scan, out_scan, err_scan = run_script("217a_migration_scan.py")
    print(err_scan.strip() if err_scan.strip() else out_scan.strip())

    # 2. Walidacja kontraktów
    print("\n[2/2] Walidacja kontraktów runtime:")
    rc_val, out_val, err_val = run_script("217a_migration_validate.py")
    print(out_val.strip())

    print("\n" + "=" * 60)
    if rc_scan == 0 and rc_val == 0:
        print("✅ Migracja 217A — KOMPLETNA")
        print("   multi_runtime jest jedyną aktywną nazwą publiczną.")
    else:
        issues = []
        if rc_scan != 0:
            issues.append("pozostały publiczne wystąpienia gemma4_audio")
        if rc_val != 0:
            issues.append("kontrakty runtime niespełnione")
        print(f"⚠️  Migracja 217A — NIEKOMPLETNA: {', '.join(issues)}")
    print("=" * 60)

    sys.exit(0 if rc_scan == 0 and rc_val == 0 else 1)


if __name__ == "__main__":
    main()
