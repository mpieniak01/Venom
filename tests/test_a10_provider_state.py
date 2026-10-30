"""Provider state belongs to one environment, independent of Full/Light."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from venom_core.utils.runtime_state import resolve_runtime_state_root


def test_existing_dev_path_is_preserved_without_copying(tmp_path):
    legacy = tmp_path / ".venom_runtime"
    legacy.mkdir()
    selection = legacy / "existing.json"
    selection.write_text('{"selected":"operator"}')
    assert resolve_runtime_state_root(tmp_path) == legacy
    assert (
        resolve_runtime_state_root(
            tmp_path, environment_role="dev", storage_prefix="custom"
        )
        == legacy
    )
    assert selection.read_text() == '{"selected":"operator"}'


@pytest.mark.parametrize("role", ["preprod", "prod"])
def test_non_dev_defaults_are_separate(tmp_path, role):
    selected = resolve_runtime_state_root(tmp_path, environment_role=role)
    assert selected == tmp_path / ".venom_runtime" / role
    assert not selected.exists()


def test_explicit_namespace_and_override(tmp_path):
    assert (
        resolve_runtime_state_root(
            tmp_path, environment_role="preprod", storage_prefix="uat"
        )
        == tmp_path / ".venom_runtime/uat"
    )
    assert (
        resolve_runtime_state_root(
            tmp_path, environment_role="preprod", override="isolated"
        )
        == tmp_path / "isolated"
    )


@pytest.mark.parametrize("prefix", ["..", ".", "nested/path", "../dev", "a\\b"])
def test_namespace_traversal_is_rejected(tmp_path, prefix):
    with pytest.raises(ValueError, match="namespace"):
        resolve_runtime_state_root(
            tmp_path, environment_role="preprod", storage_prefix=prefix
        )


def test_non_dev_override_cannot_use_dev_root_or_its_parent(tmp_path):
    for path in (".venom_runtime", "."):
        with pytest.raises(ValueError, match="overlaps"):
            resolve_runtime_state_root(
                tmp_path, environment_role="preprod", override=path
            )


SCRIPT = r"""
import json, socket, sys
from pathlib import Path
socket.socket.connect = lambda *args: (_ for _ in ()).throw(AssertionError("network forbidden"))
from venom_core.utils.runtime_state import runtime_state_root
from venom_core.services import openrouter_runtime as rt
from venom_core.services import openrouter_model_catalog as catalog
from venom_core.services import remote_provider_control as remote
from venom_core.services import vast_chat_runtime as vast
from venom_core.services import vast_chat_connection as connection
from venom_core.services import vast_management_config as config
from venom_core.services.vast_environments import cli
from venom_core.services.openrouter_billing import OpenRouterBilling, Cache
name, action = sys.argv[1:]
if action == "write":
    rt.save_selection({"model": name, "config_hash": name + "-hash"})
    rt.save_request_receipt("a" * 32, {"provider": name})
    rt._STATE.joinpath("connected-models.json").write_text(json.dumps({"models": [name]}))
    remote.set_enabled("openrouter", name == "dev")
    vast._save({"target_id": "ollama@vast:" + "a" * 32 + ":1", "model": name, "digest": "b" * 64})
    billing = OpenRouterBilling(credential="fake", management="fake")
    owner = billing.store.claim(1)
    assert owner
    billing.store.save(Cache(source=name), owner)
    manager = connection.VastChatConnection(object())
    manager.journal.write(manager.journal.root / "chat-target.json", {"target": None})
else:
    billing = OpenRouterBilling(credential="fake", management="fake")
print(json.dumps({
    "root": str(runtime_state_root()), "model": rt.selection()["model"],
    "vast": vast.selection()["model"], "enabled": remote.enabled("openrouter"),
    "billing": billing.store.load().source,
    "catalog": str(catalog._path()),
    "connection": str(connection.ROOT),
    "prepared": str(config.DEFAULT_PROFILE), "cli": cli.DEFAULT_STATE,
    "receipt": json.loads((rt._STATE / "requests" / ("a" * 32 + ".json")).read_text())["provider"]
}))
"""


def run_state(root, role, profile, name, action):
    env = dict(
        os.environ,
        ENVIRONMENT_ROLE=role,
        STORAGE_PREFIX="" if role == "dev" else role,
        VENOM_RUNTIME_PROFILE=profile,
        VENOM_RUNTIME_STATE_ROOT=str(root),
        VENOM_LOG_DIR=str(root / "logs"),
        ENV_FILE=str(root / "missing.env"),
    )
    result = subprocess.run(
        [sys.executable, "-c", SCRIPT, name, action],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_actual_consumers_keep_two_models_and_ledgers_isolated_across_restart(tmp_path):
    roots = {role: tmp_path / role for role in ("dev", "preprod")}
    before = run_state(roots["dev"], "dev", "full", "dev", "write")
    preprod = run_state(roots["preprod"], "preprod", "light", "preprod", "write")
    after = run_state(roots["dev"], "dev", "light", "dev", "read")
    restarted = run_state(roots["preprod"], "preprod", "full", "preprod", "read")
    assert before == after
    assert preprod == restarted
    for role, result in (("dev", after), ("preprod", restarted)):
        assert (
            result["model"]
            == result["vast"]
            == result["billing"]
            == result["receipt"]
            == role
        )
        assert result["enabled"] is (role == "dev")
        for key in ("root", "catalog", "connection", "prepared", "cli"):
            assert Path(result[key]).is_relative_to(roots[role])


def test_namespace_symlink_cannot_resolve_to_dev(tmp_path):
    legacy = tmp_path / ".venom_runtime"
    legacy.mkdir()
    (legacy / "preprod").symlink_to(legacy)
    with pytest.raises(ValueError, match="overlaps"):
        resolve_runtime_state_root(tmp_path, environment_role="preprod")
