from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_module():
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "update_sonar_new_code_group.py"
    )
    spec = importlib.util.spec_from_file_location(
        "update_sonar_new_code_group", script_path
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_append_auto_items_keeps_entries_in_auto_section(tmp_path):
    module = _load_module()
    group_path = tmp_path / "sonar-new-code.txt"
    group_path.write_text(
        "\n".join(
            [
                "# AUTO-ADDED by pre-commit (staged backend/test changes)",
                "tests/test_auto1.py",
                "",
                "# Manual section",
                "tests/test_manual.py",
                "",
            ]
        ),
        encoding="utf-8",
    )

    module._append_auto_items(group_path, ["tests/test_auto2.py"])
    lines = group_path.read_text(encoding="utf-8").splitlines()

    auto_header_idx = lines.index(module.AUTO_SECTION_HEADER)
    manual_header_idx = lines.index("# Manual section")
    assert lines[auto_header_idx + 1 : manual_header_idx] == [
        "tests/test_auto1.py",
        "",
        "tests/test_auto2.py",
    ]


def test_main_handles_nested_tests_and_uses_public_resolver_api(
    monkeypatch, tmp_path, capsys
):
    module = _load_module()
    group_path = tmp_path / "sonar-new-code.txt"
    group_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(module, "GROUP_PATH", group_path)
    monkeypatch.setattr(
        module,
        "_git_staged_files",
        lambda: ["tests/api/test_nested.py", "venom_core/core/x.py"],
    )

    class Resolver:
        def resolve_candidates_from_changed_files(self, staged):
            assert "tests/api/test_nested.py" in staged
            return ["tests/api/test_nested.py"]

    monkeypatch.setattr(module, "_load_resolver_module", lambda: Resolver())

    assert module.main() == 0
    output = capsys.readouterr().out
    assert "Added 1 test(s)" in output
    assert "tests/api/test_nested.py" in group_path.read_text(encoding="utf-8")


def test_main_dedupes_candidates_from_public_resolver(monkeypatch, tmp_path):
    module = _load_module()
    group_path = tmp_path / "sonar-new-code.txt"
    group_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(module, "GROUP_PATH", group_path)
    monkeypatch.setattr(
        module,
        "_git_staged_files",
        lambda: ["tests/api/test_nested.py"],
    )

    class Resolver:
        def resolve_candidates_from_changed_files(self, staged):
            return [
                "tests/api/test_nested.py",
                "tests/api/test_nested.py",
            ]

    monkeypatch.setattr(module, "_load_resolver_module", lambda: Resolver())
    assert module.main() == 0
    lines = group_path.read_text(encoding="utf-8").splitlines()
    assert lines.count("tests/api/test_nested.py") == 1


def test_main_skips_when_no_relevant_changes(monkeypatch, capsys):
    module = _load_module()
    monkeypatch.setattr(module, "_git_staged_files", lambda: ["README.md"])

    assert module.main() == 0
    assert "skip Sonar group update" in capsys.readouterr().out
