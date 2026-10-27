from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.test_execution_inventory import build_inventory, main


def _repo(tmp_path: Path, entries: list[dict], files: dict[str, str]) -> Path:
    catalog = tmp_path / "config/testing/test_catalog.json"
    catalog.parent.mkdir(parents=True)
    catalog.write_text(json.dumps({"tests": entries}), encoding="utf-8")
    for name, contents in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(contents, encoding="utf-8")
    return tmp_path


def _entry(path: str, test_type: str = "unit") -> dict:
    return {
        "path": path,
        "domain": "runtime",
        "test_type": test_type,
        "primary_lane": "new-code",
        "allowed_lanes": ["new-code", "release"],
    }


def test_network_signal_is_only_a_candidate_and_no_signal_is_still_unknown(tmp_path):
    repo = _repo(
        tmp_path,
        [_entry("tests/test_mock.py"), _entry("tests/test_plain.py")],
        {
            "tests/test_mock.py": "import httpx\ndef test_a(monkeypatch):\n    monkeypatch.setattr(httpx, 'get', lambda *a: None)\n    httpx.get('http://example.invalid')\n",
            "tests/test_plain.py": "def test_plain():\n    assert True\n",
        },
    )
    report = build_inventory(repo)
    rows = {row["path"]: row for row in report["tests"]}
    assert rows["tests/test_mock.py"]["environment"] == "unknown"
    assert rows["tests/test_mock.py"]["signals"][0]["kind"] == "network_candidate"
    assert rows["tests/test_plain.py"]["environment"] == "unknown"
    assert rows["tests/test_plain.py"]["signals"] == []
    assert all(row["manual_review_required"] for row in rows.values())


def test_module_marker_and_partial_class_marker_are_distinct(tmp_path):
    repo = _repo(
        tmp_path,
        [_entry("tests/test_live.py"), _entry("tests/test_mixed.py")],
        {
            "tests/test_live.py": "import pytest\npytestmark = [pytest.mark.live_venom]\ndef test_live(): pass\n",
            "tests/test_mixed.py": "import pytest\n@pytest.mark.live_model\nclass TestLive:\n    def test_a(self): pass\ndef test_b(): pass\n",
        },
    )
    rows = {row["path"]: row for row in build_inventory(repo)["tests"]}
    assert rows["tests/test_live.py"]["environment"] == "declared_live"
    assert rows["tests/test_mixed.py"]["environment"] == "partly_declared_live"
    assert rows["tests/test_mixed.py"]["declared_live_nodes"] == ["TestLive::test_a"]


def test_ast_scan_does_not_execute_imports_and_marks_collection_calls(tmp_path):
    path = "tests/test_import_probe.py"
    repo = _repo(
        tmp_path,
        [_entry(path)],
        {
            path: "from urllib.request import urlopen as fetch\nfetch('http://example.invalid')\nraise AssertionError('must never execute')\n"
        },
    )
    row = build_inventory(repo)["tests"][0]
    assert row["signals"] == [
        {
            "kind": "network_candidate",
            "call": "urllib.request.urlopen",
            "line": 2,
            "phase": "collection",
        }
    ]


def test_cost_and_e2e_are_reported_as_hints_not_measured_results(tmp_path):
    path = "tests/perf/test_flow_e2e.py"
    repo = _repo(tmp_path, [_entry(path, "perf")], {path: "def test_it(): pass\n"})
    group = repo / "config/pytest-groups/heavy.txt"
    group.parent.mkdir(parents=True)
    group.write_text(f"# generated\n{path}\n", encoding="utf-8")
    row = build_inventory(repo)["tests"][0]
    assert row["layer_hint"] == "e2e_candidate"
    assert row["layer_basis"] == "path_name_only"
    assert row["cost_groups"] == ["heavy"]
    assert row["environment"] == "unknown"


def test_new_unregistered_test_remains_visible_and_strict_check_fails(tmp_path, capsys):
    repo = _repo(tmp_path, [], {"tests/test_new.py": "def test_it(): pass\n"})
    assert main(["--root", str(repo), "--summary", "--fail-on-unregistered"]) == 1
    report = json.loads(capsys.readouterr().out)
    assert report["unregistered_files"] == 1
    row = build_inventory(repo)["tests"][0]
    assert row["catalogued"] is False
    assert row["environment"] == "unknown"
    assert row["cost_groups"] == []


def test_duplicate_and_outside_catalog_paths_fail_closed(tmp_path):
    path = "tests/test_a.py"
    repo = _repo(tmp_path, [_entry(path), _entry(path)], {path: "pass\n"})
    with pytest.raises(ValueError, match="duplicate"):
        build_inventory(repo)
    catalog = repo / "config/testing/test_catalog.json"
    catalog.write_text(
        json.dumps({"tests": [_entry("../test_outside.py")]}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="invalid test path"):
        build_inventory(repo)


def test_alias_marker_is_not_assumed_safe_or_live(tmp_path):
    path = "tests/test_dynamic.py"
    repo = _repo(
        tmp_path,
        [_entry(path)],
        {path: "from pytest import mark as m\n@m.live_venom\ndef test_it(): pass\n"},
    )
    row = build_inventory(repo)["tests"][0]
    assert row["environment"] == "unknown"
    assert row["manual_review_required"] is True


def test_missing_catalog_file_fails_instead_of_silent_omission(tmp_path):
    repo = _repo(tmp_path, [_entry("tests/test_missing.py")], {})
    with pytest.raises(ValueError, match="does not exist"):
        build_inventory(repo)


def test_review_filter_selects_candidate_rows_and_keeps_full_summary(tmp_path, capsys):
    repo = _repo(
        tmp_path,
        [_entry("tests/test_plain.py"), _entry("tests/test_candidate.py")],
        {
            "tests/test_plain.py": "def test_plain(): pass\n",
            "tests/test_candidate.py": "import requests\ndef test_candidate(): requests.get('http://example.invalid')\n",
        },
    )
    assert main(["--root", str(repo), "--review", "signals"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["review_filter"] == "signals"
    assert report["summary"]["discovered_files"] == 2
    assert [row["path"] for row in report["tests"]] == ["tests/test_candidate.py"]


def test_argument_defaults_follow_enclosing_execution_phase(tmp_path):
    path = "tests/test_defaults.py"
    source = """\
import requests

def test_defaults(value=requests.get('http://example.invalid'), *, second=requests.get('http://example.invalid')):
    def nested(value=requests.get('http://example.invalid')):
        pass
    callback = lambda value=requests.get('http://example.invalid'): requests.get('http://example.invalid')

callback = lambda value=requests.get('http://example.invalid'): requests.get('http://example.invalid')

async def test_async(value=requests.get('http://example.invalid')):
    pass
"""
    repo = _repo(tmp_path, [_entry(path)], {path: source})
    signals = build_inventory(repo)["tests"][0]["signals"]
    assert [(item["line"], item["phase"]) for item in signals] == [
        (3, "collection"),
        (3, "collection"),
        (4, "execution"),
        (6, "execution"),
        (6, "execution"),
        (8, "collection"),
        (8, "execution"),
        (10, "collection"),
    ]


@pytest.mark.parametrize("payload", [None, [], "catalog", 42])
def test_non_object_catalog_root_fails_with_cli_exit_2(tmp_path, capsys, payload):
    repo = _repo(tmp_path, [], {})
    catalog = repo / "config/testing/test_catalog.json"
    catalog.write_text(json.dumps(payload), encoding="utf-8")
    assert main(["--root", str(repo)]) == 2
    assert "catalog root must be a JSON object" in capsys.readouterr().err
