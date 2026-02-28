from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

SCRIPT_PATH = Path("scripts/check_architecture_contracts.py")


def _write_contract(path: Path) -> None:
    payload = {
        "version": 1,
        "rules": [
            {
                "id": "no_api_routes_outside_api",
                "description": "Only API modules may import api.routes.",
                "from_prefixes": ["venom_core"],
                "except_from_prefixes": ["venom_core.api"],
                "forbidden_import_prefixes": ["venom_core.api.routes"],
            }
        ],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_architecture_contracts_pass_when_no_violation(tmp_path: Path) -> None:
    source_root = tmp_path / "venom_core"
    (source_root / "core").mkdir(parents=True)
    (source_root / "core" / "scheduler.py").write_text(
        "from venom_core.api.schemas.tasks import TaskRequest\n",
        encoding="utf-8",
    )

    contracts = tmp_path / "contracts.yaml"
    _write_contract(contracts)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--contracts",
            str(contracts),
            "--source-root",
            str(source_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "passed" in result.stdout.lower()


def test_architecture_contracts_fail_on_forbidden_import(tmp_path: Path) -> None:
    source_root = tmp_path / "venom_core"
    (source_root / "core").mkdir(parents=True)
    (source_root / "core" / "scheduler.py").write_text(
        "from venom_core.api.routes.tasks import router\n",
        encoding="utf-8",
    )

    contracts = tmp_path / "contracts.yaml"
    _write_contract(contracts)

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--contracts",
            str(contracts),
            "--source-root",
            str(source_root),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "no_api_routes_outside_api" in result.stdout
    assert "venom_core.api.routes.tasks" in result.stdout
