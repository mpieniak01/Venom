"""The real Make/Python/Node bridge belongs to the stack lane, not Node-only CI."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def available_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def test_make_build_start_relative_web_dir_without_implicit_rebuild(tmp_path):
    node = shutil.which("node")
    assert node, "Stack tests require the pinned Node from web-next/.nvmrc"
    app = tmp_path / "web-next"
    app.mkdir()
    (app / "page.tsx").write_text("fixture page")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "web-next/page.tsx"], cwd=tmp_path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-qm",
            "fixture",
        ],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    npm = tmp_path / "fake-npm"
    npm.write_text(
        f"#!{node}\n"
        + """
const fs = require('node:fs'); const path = require('node:path'); const http = require('node:http');
if (process.argv[3] === 'build') {
  if (process.env.FAKE_BUILD_FAIL) process.exit(7);
  const dist = process.env.NEXT_DIST_DIR;
  fs.mkdirSync(path.join(dist, 'standalone'), {recursive:true});
  fs.writeFileSync(path.join(dist, 'BUILD_ID'), 'test');
  fs.writeFileSync(path.join(dist, 'standalone/server.js'), '// test');
  process.exit(0);
}
const port = Number(process.argv[process.argv.indexOf('--port')+1]);
const server = http.createServer((req,res) => {
  if (req.url === '/_venom/ready' && req.headers['x-venom-start-token'] === process.env.VENOM_UI_START_TOKEN) res.end(process.env.VENOM_UI_START_TOKEN);
  else { res.statusCode=503; res.end('not ready'); }
});
server.listen(port, '127.0.0.1');
process.on('SIGTERM', () => server.close(() => process.exit(0)));
"""
    )
    npm.chmod(0o700)
    env_file = tmp_path / "test.env"
    env_file.write_text("ENVIRONMENT_ROLE=dev\n")
    pid = tmp_path / "run/ui.pid"
    args = [
        "make",
        "--no-print-directory",
        "ENVIRONMENT=dev",
        "PROFILE=full",
        f"PYTHON_BIN={sys.executable}",
        f"ENV_FILE={env_file}",
        f"WEB_DIR={os.path.relpath(app, ROOT)}",
        f"WEB_PID_FILE={pid}",
        f"WEB_LOG={tmp_path}/logs/ui.log",
        f"NPM={npm}",
        f"WEB_PORT={available_port()}",
        f"PORT={available_port()}",
        "WEB_HOST=127.0.0.1",
    ]
    env = {**os.environ, "WEB_READY_TIMEOUT_SEC": "10"}
    # Preserve the caller's tools; isolate profile/provider configuration from local fixtures.
    for key in (
        "ENV_FILE",
        "PROFILE",
        "ENVIRONMENT",
        "ENVIRONMENT_ROLE",
        "API_PROXY_TARGET",
        "NEXT_DIST_DIR",
        "VENOM_RUNTIME_PROFILE",
        "VENOM_STACK_RESOLVED",
    ):
        env.pop(key, None)
    try:
        build = subprocess.run(
            [*args, "web-build"],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert build.returncode == 0, build.stderr
        # If start attempts another build, the fake fails. Only a prepared artifact is allowed.
        start = subprocess.run(
            [*args, "web"],
            cwd=ROOT,
            env={**env, "FAKE_BUILD_FAIL": "1"},
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert start.returncode == 0, start.stderr
        assert int(pid.read_text()) > 1
        assert json.loads(Path(str(pid) + ".identity.json").read_text())["pid"] == int(
            pid.read_text()
        )
    finally:
        stop = subprocess.run(
            [*args, "web-stop"],
            cwd=ROOT,
            env=env,
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert stop.returncode == 0, stop.stderr
    assert not pid.exists()
    assert not Path(str(pid) + ".identity.json").exists()
