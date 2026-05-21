"""Testy jednostkowe dla CodeIndexSkill."""

import textwrap
from unittest.mock import patch

import pytest

from venom_core.execution.skills.code_index_skill import (
    CodeIndexSkill,
    CodeMatch,
    FileSymbols,
)


@pytest.fixture
def skill(tmp_path):
    return CodeIndexSkill(workspace_root=str(tmp_path))


@pytest.fixture
def py_file(tmp_path):
    content = textwrap.dedent("""\
        import os
        from pathlib import Path

        class MyClass:
            def method_one(self):
                pass

            async def async_method(self):
                pass

        def standalone_func():
            return 42
    """)
    f = tmp_path / "sample.py"
    f.write_text(content, encoding="utf-8")
    return f


class TestCodeMatch:
    def test_to_dict_roundtrip(self):
        m = CodeMatch(
            file="a.py",
            line=5,
            text="def foo():",
            context_before=["# comment"],
            context_after=["    pass"],
        )
        d = m.to_dict()
        assert d["file"] == "a.py"
        assert d["line"] == 5
        assert d["text"] == "def foo():"

    def test_format_snippet_includes_arrow(self):
        m = CodeMatch(
            file="a.py",
            line=3,
            text="target line",
            context_before=["before"],
            context_after=["after"],
        )
        snippet = m.format_snippet()
        assert "→" in snippet
        assert "target line" in snippet
        assert "before" in snippet
        assert "after" in snippet


class TestFileSymbols:
    def test_format_summary_all_sections(self):
        fs = FileSymbols(
            file="x.py",
            classes=["Foo", "Bar"],
            functions=["do_thing"],
            imports=["os", "pathlib"],
        )
        summary = fs.format_summary()
        assert "Foo" in summary
        assert "Bar" in summary
        assert "do_thing" in summary
        assert "os" in summary

    def test_format_summary_empty(self):
        fs = FileSymbols(file="empty.py", classes=[], functions=[], imports=[])
        summary = fs.format_summary()
        assert "empty.py" in summary


class TestCodeIndexSkillGetFileSymbols:
    def test_extracts_classes_and_functions(self, skill, py_file):
        symbols = skill.get_file_symbols(str(py_file))
        assert "MyClass" in symbols.classes
        assert "method_one" in symbols.functions
        assert "async_method" in symbols.functions
        assert "standalone_func" in symbols.functions

    def test_extracts_imports(self, skill, py_file):
        symbols = skill.get_file_symbols(str(py_file))
        assert "os" in symbols.imports
        assert "pathlib" in symbols.imports

    def test_nonexistent_file(self, skill):
        symbols = skill.get_file_symbols("/tmp/does_not_exist_xyz.py")
        assert symbols.classes == []
        assert symbols.functions == []

    def test_non_py_file(self, skill, tmp_path):
        f = tmp_path / "script.sh"
        f.write_text("echo hello")
        symbols = skill.get_file_symbols(str(f))
        assert symbols.classes == []
        assert symbols.functions == []

    def test_syntax_error_file(self, skill, tmp_path):
        f = tmp_path / "broken.py"
        f.write_text("def (broken syntax!!!")
        symbols = skill.get_file_symbols(str(f))
        assert isinstance(symbols, FileSymbols)

    def test_deduplicates_symbols(self, skill, tmp_path):
        f = tmp_path / "dup.py"
        f.write_text("import os\nimport os\ndef foo(): pass\ndef foo(): pass\n")
        symbols = skill.get_file_symbols(str(f))
        assert symbols.imports.count("os") == 1
        assert symbols.functions.count("foo") == 1


class TestReadContext:
    def test_returns_surrounding_lines(self, skill, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("\n".join(f"line {i}" for i in range(1, 21)))
        ctx = skill.read_context(str(f), line=10, context_lines=2)
        assert "→" in ctx
        assert "line 10" in ctx
        assert "line 8" in ctx
        assert "line 12" in ctx

    def test_nonexistent_file(self, skill):
        result = skill.read_context("/nonexistent/file.py", line=1)
        assert "❌" in result

    def test_line_at_start(self, skill, tmp_path):
        f = tmp_path / "t.py"
        f.write_text("a\nb\nc\n")
        ctx = skill.read_context(str(f), line=1, context_lines=5)
        assert "→" in ctx
        assert "a" in ctx

    def test_line_at_end(self, skill, tmp_path):
        f = tmp_path / "t.py"
        f.write_text("a\nb\nc\n")
        ctx = skill.read_context(str(f), line=3, context_lines=5)
        assert "→" in ctx
        assert "c" in ctx


class TestSearchCode:
    def test_returns_empty_when_rg_unavailable(self, skill):
        skill._rg_available = False
        matches = skill.search_code("anything")
        assert matches == []

    def test_search_finds_pattern(self, skill, tmp_path):
        if not skill._rg_available:
            pytest.skip("ripgrep niedostępny w środowisku testowym")
        f = tmp_path / "code.py"
        f.write_text("def hello_world():\n    return 'hello'\n")
        matches = skill.search_code("hello_world", max_results=5)
        assert any(m.text.strip().startswith("def hello_world") for m in matches)

    def test_respects_max_results(self, skill, tmp_path):
        for i in range(20):
            (tmp_path / f"f{i}.py").write_text(f"# target_{i}\n")
        matches = skill.search_code("target_", max_results=3)
        assert len(matches) <= 3

    def test_case_insensitive_default(self, skill, tmp_path):
        f = tmp_path / "c.py"
        f.write_text("class FooBar:\n    pass\n")
        matches = skill.search_code("foobar")
        assert len(matches) >= 1

    def test_glob_filter(self, skill, tmp_path):
        (tmp_path / "a.py").write_text("# unique_marker_xyz\n")
        (tmp_path / "b.md").write_text("unique_marker_xyz\n")
        py_matches = skill.search_code("unique_marker_xyz", path_glob="*.py")
        assert all(m.file.endswith(".py") for m in py_matches)

    def test_format_matches_empty(self, skill):
        result = skill.format_matches_for_llm([])
        assert result == "Brak wyników."

    def test_format_matches_truncation(self, skill):
        matches = [
            CodeMatch(
                file=f"f{i}.py",
                line=1,
                text="x" * 200,
                context_before=[],
                context_after=[],
            )
            for i in range(50)
        ]
        result = skill.format_matches_for_llm(matches, max_chars=500)
        assert len(result) <= 700


class TestSearchCodeRipgrepTimeout:
    def test_timeout_returns_empty(self, skill, tmp_path):
        import subprocess

        skill._rg_available = True
        with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("rg", 15)):
            matches = skill.search_code("anything")
        assert matches == []


@pytest.mark.asyncio
class TestKernelFunctionWrappers:
    async def test_search_code_tool_no_results(self, skill):
        skill._rg_available = False
        result = await skill.search_code_tool(query="xyz")
        assert result == "Brak wyników."

    async def test_get_file_symbols_tool(self, skill, py_file):
        result = await skill.get_file_symbols_tool(file_path=str(py_file))
        assert "MyClass" in result

    async def test_read_context_tool(self, skill, tmp_path):
        f = tmp_path / "t.py"
        f.write_text("line1\nline2\nline3\n")
        result = await skill.read_context_tool(file_path=str(f), line=2)
        assert "line2" in result
