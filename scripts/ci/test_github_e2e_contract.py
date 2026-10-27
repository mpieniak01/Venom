"""Check the isolated E2E contract without opening sockets or running Venom."""

import io
import json
import os
import runpy
import subprocess
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

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
