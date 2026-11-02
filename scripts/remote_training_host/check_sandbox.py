"""Explicit CPU-only sandbox qualification before remote model evaluation."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import uuid
from pathlib import Path

from scripts.granite_operator.comparison_support import (
    DockerTool,
    cleanup_owned,
    load_frozen,
)


def check(manifest_path: Path) -> dict:
    manifest, _ = load_frozen(manifest_path)
    run_id = uuid.uuid4().hex
    checks = {}
    try:
        with tempfile.TemporaryDirectory(prefix="venom-sandbox-check-") as temporary:
            workspace = Path(temporary) / "workspace"
            workspace.mkdir(mode=0o755)
            workspace.chmod(0o755)
            (workspace / "probe.txt").write_text("sandbox qualification\n")
            (workspace / "probe.txt").chmod(0o644)
            for phase, readonly, command in (
                (
                    "writable",
                    False,
                    "git init -q && git --no-optional-locks status --porcelain=v1",
                ),
                ("readonly", True, "git --no-optional-locks status --porcelain=v1"),
            ):
                tool = DockerTool(
                    workspace, manifest["sandbox_image"], run_id, readonly=readonly
                )
                try:
                    result = tool.execute(command, 10)
                    passed = (
                        result["exit_code"] == 0
                        and not result["workspace_error"]
                        and not result["execution_timed_out"]
                        and not result["execution_killed"]
                        and not result["output_truncated"]
                        and result["stdout"].strip() == "?? probe.txt"
                    )
                    if not passed:
                        raise RuntimeError("sandbox_check_failed:" + phase)
                    checks[phase] = "PASS"
                finally:
                    tool.close()
    finally:
        if not cleanup_owned(run_id):
            raise RuntimeError("sandbox_check_cleanup_failed")
    return {
        "status": "PASS",
        "checks": checks,
        "sandbox_image": manifest["sandbox_image"],
        "gpu_used": False,
        "model_loaded": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = check(args.cases)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        # Docker/provider stderr may contain sensitive configuration.
        print(json.dumps({"status": "FAIL", "error_type": type(error).__name__}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
