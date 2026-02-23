"""Unit tests for CodeGraphStore."""

import tempfile
from pathlib import Path

import pytest

from venom_core.memory.graph_store import CodeGraphStore


@pytest.fixture
def temp_workspace():
    """Fixture for temporary workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def graph_store(temp_workspace):
    """Fixture for CodeGraphStore with temporary workspace."""
    graph_file = Path(temp_workspace) / "code_graph.json"
    return CodeGraphStore(workspace_root=temp_workspace, graph_file=str(graph_file))


@pytest.fixture
def sample_python_file(temp_workspace):
    """Fixture creating sample Python file."""
    file_path = Path(temp_workspace) / "sample.py"
    content = """
import os
from typing import List

class MyClass:
    def __init__(self):
        self.value = 0

    def increment(self):
        self.value += 1
        return self.value

def my_function(x: int) -> int:
    return x * 2

def caller():
    obj = MyClass()
    result = my_function(5)
    return obj.increment()
"""
    file_path.write_text(content, encoding="utf-8")
    return file_path


class TestCodeGraphStore:
    """Tests for CodeGraphStore."""

    def test_initialization(self, graph_store, temp_workspace):
        """Test CodeGraphStore initialization."""
        assert graph_store.workspace_root == Path(temp_workspace).resolve()
        assert graph_store.graph is not None
        assert graph_store.graph.number_of_nodes() == 0

    def test_scan_workspace_empty(self, graph_store):
        """Test scanning empty workspace."""
        stats = graph_store.scan_workspace()

        assert stats["total_files"] == 0
        assert stats["files_scanned"] == 0
        assert stats["nodes"] == 0
        assert stats["edges"] == 0

    def test_scan_workspace_with_file(self, graph_store, sample_python_file):
        """Test scanning workspace with file."""
        stats = graph_store.scan_workspace()

        assert stats["total_files"] == 1
        assert stats["files_scanned"] == 1
        assert stats["nodes"] > 0  # Should have nodes
        assert stats["edges"] > 0  # Should have edges

    def test_parse_file_creates_nodes(self, graph_store, sample_python_file):
        """Test if file parsing creates appropriate nodes."""
        graph_store.scan_workspace()

        # Check if file node exists
        file_nodes = [n for n in graph_store.graph.nodes() if n.startswith("file:")]
        assert len(file_nodes) > 0

        # Check if class nodes exist
        class_nodes = [
            n
            for n, data in graph_store.graph.nodes(data=True)
            if data.get("type") == "class"
        ]
        assert len(class_nodes) > 0

        # Check if function nodes exist
        function_nodes = [
            n
            for n, data in graph_store.graph.nodes(data=True)
            if data.get("type") == "function"
        ]
        assert len(function_nodes) > 0

    def test_get_file_info(self, graph_store, sample_python_file):
        """Test getting file information."""
        graph_store.scan_workspace()

        rel_path = sample_python_file.relative_to(graph_store.workspace_root)
        info = graph_store.get_file_info(str(rel_path))

        assert "file" in info
        assert "classes" in info
        assert "functions" in info
        assert "imports" in info

        # Check if class was found
        assert len(info["classes"]) > 0
        assert any(c["name"] == "MyClass" for c in info["classes"])

        # Check if functions were found
        assert len(info["functions"]) > 0

    def test_get_dependencies_empty(self, graph_store, sample_python_file):
        """Test getting dependencies for file without dependencies."""
        graph_store.scan_workspace()

        rel_path = sample_python_file.relative_to(graph_store.workspace_root)
        deps = graph_store.get_dependencies(str(rel_path))

        # Our sample file has no dependencies on other files in workspace
        assert isinstance(deps, list)

    def test_get_impact_analysis(self, graph_store, sample_python_file):
        """Test impact analysis."""
        graph_store.scan_workspace()

        rel_path = sample_python_file.relative_to(graph_store.workspace_root)
        impact = graph_store.get_impact_analysis(str(rel_path))

        assert "file" in impact
        assert "direct_importers" in impact
        assert "all_affected_files" in impact
        assert "impact_score" in impact

    def test_save_and_load_graph(self, graph_store, sample_python_file):
        """Test saving and loading graph."""
        # Scan and save
        graph_store.scan_workspace()
        nodes_before = graph_store.graph.number_of_nodes()
        edges_before = graph_store.graph.number_of_edges()

        # Create new instance and load
        new_store = CodeGraphStore(
            workspace_root=graph_store.workspace_root,
            graph_file=graph_store.graph_file,
        )
        loaded = new_store.load_graph()

        assert loaded is True
        assert new_store.graph.number_of_nodes() == nodes_before
        assert new_store.graph.number_of_edges() == edges_before

    def test_get_graph_summary(self, graph_store, sample_python_file):
        """Test getting graph summary."""
        graph_store.scan_workspace()

        summary = graph_store.get_graph_summary()

        assert "total_nodes" in summary
        assert "total_edges" in summary
        assert "node_types" in summary
        assert "edge_types" in summary

        assert summary["total_nodes"] > 0
        assert summary["total_edges"] > 0

    def test_parse_invalid_syntax(self, graph_store, temp_workspace):
        """Test parsing file with syntax error."""
        invalid_file = Path(temp_workspace) / "invalid.py"
        invalid_file.write_text("def invalid syntax here", encoding="utf-8")

        # Should not raise exception
        stats = graph_store.scan_workspace()

        # Should have error
        assert stats["errors"] > 0

    def test_multiple_files(self, graph_store, temp_workspace):
        """Test scanning multiple files."""
        # Create several files
        for i in range(3):
            file_path = Path(temp_workspace) / f"file{i}.py"
            file_path.write_text(f"def func{i}(): pass", encoding="utf-8")

        stats = graph_store.scan_workspace()

        assert stats["total_files"] == 3
        assert stats["files_scanned"] == 3

    def test_safe_log_value_sanitizes_control_chars(self):
        value = "abc\tdef\nxyz"
        out = CodeGraphStore._safe_log_value(value, max_len=50)
        assert "\n" not in out
        assert "\t" not in out

    def test_get_dependencies_returns_empty_for_missing_file(self, graph_store):
        deps = graph_store.get_dependencies("missing.py")
        assert deps == []

    def test_get_file_info_returns_empty_for_missing_file(self, graph_store):
        assert graph_store.get_file_info("missing.py") == {}

    def test_get_impact_analysis_returns_error_for_missing_file(self, graph_store):
        result = graph_store.get_impact_analysis("missing.py")
        assert "error" in result

    def test_load_graph_returns_false_when_file_missing(self, graph_store):
        assert graph_store.load_graph() is False

    def test_load_graph_returns_false_for_invalid_json(self, graph_store):
        graph_store.graph_file.write_text("{bad json", encoding="utf-8")
        assert graph_store.load_graph() is False

    def test_parse_file_outside_workspace_returns_false(self, graph_store, tmp_path):
        external_file = tmp_path / "external.py"
        external_file.write_text("def x():\n    return 1\n", encoding="utf-8")
        assert graph_store._parse_file(external_file) is False
