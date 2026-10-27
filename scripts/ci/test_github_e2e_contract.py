"""Check the isolated E2E contract without opening sockets or running Venom."""

import io
import json
import os
import runpy
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.ci import verify_github_e2e_namespace as namespaces

ROOT = Path(__file__).resolve().parents[2]
FAKE = ROOT / "scripts/ci/github_e2e_fake_llm.py"


class E2EContractTest(unittest.TestCase):
    def test_consistent_ports_and_endpoints(self):
        with patch("http.server.ThreadingHTTPServer") as server:
            runpy.run_path(str(FAKE), run_name="__main__")
        self.assertEqual(server.call_args.args[0], ("127.0.0.1", 11434))
        harness = (ROOT / "scripts/ci/run-github-api-e2e.sh").read_text()
        setup = (ROOT / "web-next/scripts/github-api-e2e-setup.mjs").read_text()
        spec = (ROOT / "web-next/tests/github-real-api/chat.e2e.ts").read_text()
        self.assertIn("(13300, 18800, 11434)", harness)
        self.assertIn("LLM_LOCAL_ENDPOINT=http://127.0.0.1:11434/v1", harness)
        self.assertIn("OLLAMA_BASE_URL=http://127.0.0.1:11434", harness)
        self.assertIn("http://127.0.0.1:11434/v1", setup)
        self.assertIn("http://127.0.0.1:11434/__ci_e2e__/calls", spec)
        self.assertIn(
            "http://127.0.0.1:13300/api/v1/system/llm-servers/active", harness
        )
        self.assertIn("/api/v1/system/llm-servers/active", setup)
        self.assertIn("http://127.0.0.1:13300/api/v1/llm/simple/stream", spec)

    def test_namespace_check_rejects_shared_or_changed_namespace(self):
        for kind in ("net", "mnt"):
            current = os.readlink(f"/proc/self/ns/{kind}")
            with (
                self.subTest(kind=kind),
                patch.object(
                    namespaces, "read_proof_identities", return_value=(current, current)
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, f"private {kind}"):
                    namespaces.check_private_namespace(Path("/proof"), kind)
            with (
                self.subTest(kind=kind),
                patch.object(
                    namespaces,
                    "read_proof_identities",
                    return_value=(current, f"{kind}:[1]"),
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, f"private {kind}"):
                    namespaces.check_private_namespace(Path("/proof"), kind)

    def test_namespace_check_accepts_distinct_attested_handles(self):
        current = os.readlink("/proc/self/ns/net")
        with patch.object(
            namespaces, "read_proof_identities", return_value=("net:[1]", current)
        ):
            namespaces.check_private_namespace(Path("/proof/net"), "net")

    def test_namespace_proof_fails_closed_for_invalid_or_inaccessible_files(self):
        with self.assertRaises((OSError, RuntimeError, UnicodeError)):
            namespaces.read_proof_identities(FAKE, "net")
        with patch.object(
            namespaces, "read_proof_identities", side_effect=PermissionError("denied")
        ):
            with self.assertRaises(PermissionError):
                namespaces.check_private_namespace(Path("/missing"), "net")

    def test_namespace_proof_directory_rejects_untrusted_paths(self):
        if os.geteuid() == 0:
            self.skipTest("Requires a non-root test user")
        with tempfile.TemporaryDirectory(
            prefix="venom-github-e2e-ns.", dir="/tmp"
        ) as path:
            with self.assertRaisesRegex(RuntimeError, "root-owned and non-writable"):
                namespaces.verify_proof_directory(path)
        with tempfile.TemporaryDirectory(dir="/tmp") as path:
            with self.assertRaisesRegex(RuntimeError, "expected root-owned /tmp"):
                namespaces.verify_proof_directory(path)

    def test_namespace_verifier_rejects_missing_proof_before_services(self):
        env = os.environ.copy()
        env.pop("VENOM_E2E_NS_PROOF_DIR", None)
        result = subprocess.run(
            ["python3", str(ROOT / "scripts/ci/verify_github_e2e_namespace.py")],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Missing namespace proof location", result.stderr)

    def test_fake_tags_and_stream_without_network(self):
        module = runpy.run_path(str(FAKE))
        handler = module["Handler"].__new__(module["Handler"])
        handler.path = "/api/tags"
        handler.send_json = Mock()
        handler.do_GET()
        self.assertEqual(
            handler.send_json.call_args.args[0]["models"][0]["name"], "ci-fake-llm"
        )
        payload = {
            "model": "ci-fake-llm",
            "messages": [{"role": "user", "content": "probe"}],
            "stream": True,
        }
        body = json.dumps(payload).encode()
        handler.path = "/v1/chat/completions"
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = io.BytesIO(body)
        handler.wfile = io.BytesIO()
        handler.send_response = Mock()
        handler.send_header = Mock()
        handler.end_headers = Mock()
        handler.do_POST()
        self.assertIn(b"VENOM_E2E_OK_42", handler.wfile.getvalue())
        self.assertIn(b"data: [DONE]", handler.wfile.getvalue())
        self.assertEqual(module["calls"][-1], payload)

    def test_harness_refuses_non_github_environment(self):
        env = os.environ.copy()
        env.update(CI="false", GITHUB_ACTIONS="false", RUNNER_ENVIRONMENT="self-hosted")
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/ci/run-github-api-e2e.sh")],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires an unprivileged GitHub-hosted runner", result.stderr)


if __name__ == "__main__":
    unittest.main()
