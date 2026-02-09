"""Testy jednostkowe dla CodeGraphStore."""

import tempfile
from pathlib import Path

import pytest

from venom_core.memory.graph_store import CodeGraphStore


@pytest.fixture
def temp_workspace():
    """Fixture dla tymczasowego workspace."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def graph_store(temp_workspace):
    """Fixture dla CodeGraphStore z tymczasowym workspace."""
    graph_file = Path(temp_workspace) / "code_graph.json"
    return CodeGraphStore(workspace_root=temp_workspace, graph_file=str(graph_file))


@pytest.fixture
def sample_python_file(temp_workspace):
    """Fixture tworzący przykładowy plik Python."""
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
    """Testy dla CodeGraphStore."""

    def test_initialization(self, graph_store, temp_workspace):
        """Test inicjalizacji CodeGraphStore."""
        assert graph_store.workspace_root == Path(temp_workspace).resolve()
        assert graph_store.graph is not None
        assert graph_store.graph.number_of_nodes() == 0

    def test_scan_workspace_empty(self, graph_store):
        """Test skanowania pustego workspace."""
        stats = graph_store.scan_workspace()

        assert stats["total_files"] == 0
        assert stats["files_scanned"] == 0
        assert stats["nodes"] == 0
        assert stats["edges"] == 0

    def test_scan_workspace_with_file(self, graph_store, sample_python_file):
        """Test skanowania workspace z plikiem."""
        stats = graph_store.scan_workspace()

        assert stats["total_files"] == 1
        assert stats["files_scanned"] == 1
        assert stats["nodes"] > 0  # Powinny być węzły
        assert stats["edges"] > 0  # Powinny być krawędzie

    def test_parse_file_creates_nodes(self, graph_store, sample_python_file):
        """Test czy parsowanie pliku tworzy odpowiednie węzły."""
        graph_store.scan_workspace()

        # Sprawdź czy istnieje węzeł pliku
        file_nodes = [n for n in graph_store.graph.nodes() if n.startswith("file:")]
        assert len(file_nodes) > 0

        # Sprawdź czy istnieją węzły klas
        class_nodes = [
            n
            for n, data in graph_store.graph.nodes(data=True)
            if data.get("type") == "class"
        ]
        assert len(class_nodes) > 0

        # Sprawdź czy istnieją węzły funkcji
        function_nodes = [
            n
            for n, data in graph_store.graph.nodes(data=True)
            if data.get("type") == "function"
        ]
        assert len(function_nodes) > 0

    def test_get_file_info(self, graph_store, sample_python_file):
        """Test pobierania informacji o pliku."""
        graph_store.scan_workspace()

        rel_path = sample_python_file.relative_to(graph_store.workspace_root)
        info = graph_store.get_file_info(str(rel_path))

        assert "file" in info
        assert "classes" in info
        assert "functions" in info
        assert "imports" in info

        # Sprawdź czy znaleziono klasę
        assert len(info["classes"]) > 0
        assert any(c["name"] == "MyClass" for c in info["classes"])

        # Sprawdź czy znaleziono funkcje
        assert len(info["functions"]) > 0

    def test_get_dependencies_empty(self, graph_store, sample_python_file):
        """Test pobierania zależności dla pliku bez zależności."""
        graph_store.scan_workspace()

        rel_path = sample_python_file.relative_to(graph_store.workspace_root)
        deps = graph_store.get_dependencies(str(rel_path))

        # Nasz przykładowy plik nie ma zależności od innych plików w workspace
        assert isinstance(deps, list)

    def test_get_impact_analysis(self, graph_store, sample_python_file):
        """Test analizy wpływu."""
        graph_store.scan_workspace()

        rel_path = sample_python_file.relative_to(graph_store.workspace_root)
        impact = graph_store.get_impact_analysis(str(rel_path))

        assert "file" in impact
        assert "direct_importers" in impact
        assert "all_affected_files" in impact
        assert "impact_score" in impact

    def test_save_and_load_graph(self, graph_store, sample_python_file):
        """Test zapisywania i ładowania grafu."""
        # Skanuj i zapisz
        graph_store.scan_workspace()
        nodes_before = graph_store.graph.number_of_nodes()
        edges_before = graph_store.graph.number_of_edges()

        # Utwórz nową instancję i załaduj
        new_store = CodeGraphStore(
            workspace_root=graph_store.workspace_root,
            graph_file=graph_store.graph_file,
        )
        loaded = new_store.load_graph()

        assert loaded is True
        assert new_store.graph.number_of_nodes() == nodes_before
        assert new_store.graph.number_of_edges() == edges_before

    def test_get_graph_summary(self, graph_store, sample_python_file):
        """Test pobierania podsumowania grafu."""
        graph_store.scan_workspace()

        summary = graph_store.get_graph_summary()

        assert "total_nodes" in summary
        assert "total_edges" in summary
        assert "node_types" in summary
        assert "edge_types" in summary

        assert summary["total_nodes"] > 0
        assert summary["total_edges"] > 0

    def test_parse_invalid_syntax(self, graph_store, temp_workspace):
        """Test parsowania pliku z błędem składni."""
        invalid_file = Path(temp_workspace) / "invalid.py"
        invalid_file.write_text("def invalid syntax here", encoding="utf-8")

        # Nie powinno wywołać wyjątku
        stats = graph_store.scan_workspace()

        # Powinien być błąd
        assert stats["errors"] > 0

    def test_multiple_files(self, graph_store, temp_workspace):
        """Test skanowania wielu plików."""
        # Utwórz kilka plików
        for i in range(3):
            file_path = Path(temp_workspace) / f"file{i}.py"
            file_path.write_text(f"def func{i}(): pass", encoding="utf-8")

        stats = graph_store.scan_workspace()

        assert stats["total_files"] == 3
        assert stats["files_scanned"] == 3
