"""Moduł: graph_store - Magazyn Grafu Wiedzy o Kodzie (GraphRAG)."""

import ast
import json
from pathlib import Path
from typing import Any, Dict, List

import networkx as nx

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CodeGraphStore:
    """
    Graf wiedzy o strukturze kodu projektu.
    Używa AST (Abstract Syntax Tree) do analizy zależności między plikami, klasami i funkcjami.
    """

    def __init__(self, workspace_root: str = None, graph_file: str = None):
        """
        Inicjalizacja CodeGraphStore.

        Args:
            workspace_root: Katalog roboczy do skanowania (domyślnie WORKSPACE_ROOT)
            graph_file: Ścieżka do pliku z serializowanym grafem (domyślnie data/memory/code_graph.json)
        """
        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT).resolve()
        self.graph_file = Path(graph_file or f"{SETTINGS.MEMORY_ROOT}/code_graph.json")
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)

        # Graf zależności (DiGraph = Directed Graph)
        self.graph = nx.DiGraph()

        logger.info(f"CodeGraphStore zainicjalizowany: workspace={self.workspace_root}")

    def scan_workspace(self, force_rescan: bool = False) -> Dict[str, Any]:
        """
        Skanuje workspace i buduje graf zależności.

        Args:
            force_rescan: Jeśli True, przebudowuje graf od zera

        Returns:
            Statystyki skanowania (liczba plików, węzłów, krawędzi)
        """
        if force_rescan:
            self.graph.clear()
            logger.info("Czyszczenie grafu przed reskanem")

        logger.info(f"Rozpoczynam skanowanie workspace: {self.workspace_root}")

        # Znajdź wszystkie pliki Python
        python_files = list(self.workspace_root.rglob("*.py"))
        logger.info(f"Znaleziono {len(python_files)} plików Python")

        scanned_files = 0
        errors = []

        for file_path in python_files:
            result = self._parse_file(file_path)
            if result is False:
                # Plik miał błąd
                errors.append({"file": str(file_path), "error": "Parse error"})
            else:
                scanned_files += 1

        # Zapisz graf
        self.save_graph()

        stats = {
            "files_scanned": scanned_files,
            "total_files": len(python_files),
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "errors": len(errors),
        }

        logger.info(f"Skanowanie zakończone: {stats}")
        return stats

    def _parse_file(self, file_path: Path) -> bool:
        """
        Parsuje pojedynczy plik Python i dodaje jego elementy do grafu.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            True jeśli parsowanie się powiodło, False w przeciwnym razie
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                source_code = f.read()
        except Exception as e:
            logger.warning(f"Nie można odczytać pliku {file_path}: {e}")
            return False

        try:
            tree = ast.parse(source_code, filename=str(file_path))
        except SyntaxError as e:
            logger.warning(f"Błąd składni w pliku {file_path}: {e}")
            return False

        # Dodaj węzeł pliku
        rel_path = file_path.relative_to(self.workspace_root)
        file_node = f"file:{rel_path}"
        self.graph.add_node(
            file_node, type="file", path=str(rel_path), full_path=str(file_path)
        )

        # Visitor do ekstrakcji informacji
        visitor = CodeVisitor(file_node, self.graph, str(rel_path))
        visitor.visit(tree)

        return True

    def get_dependencies(self, file_path: str) -> List[str]:
        """
        Zwraca listę plików, które zależą od danego pliku.

        Args:
            file_path: Ścieżka do pliku (relatywna do workspace)

        Returns:
            Lista ścieżek plików zależnych
        """
        file_node = f"file:{file_path}"

        if file_node not in self.graph:
            logger.warning(f"Plik {file_path} nie istnieje w grafie")
            return []

        # Znajdź wszystkie węzły, które mają krawędź DO tego pliku
        dependents = []
        for node in self.graph.nodes():
            if node == file_node:
                continue

            # Sprawdź czy istnieje ścieżka od tego węzła do pliku
            if nx.has_path(self.graph, node, file_node):
                # Wyciągnij tylko węzły typu "file"
                if node.startswith("file:"):
                    dependents.append(node.replace("file:", ""))

        logger.info(f"Plik {file_path} ma {len(dependents)} zależnych plików")
        return dependents

    def get_file_info(self, file_path: str) -> Dict[str, Any]:
        """
        Zwraca informacje o pliku z grafu.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Słownik z informacjami (klasy, funkcje, importy)
        """
        file_node = f"file:{file_path}"

        if file_node not in self.graph:
            return {}

        # Zbierz wszystkie dzieci tego pliku
        children = list(self.graph.successors(file_node))

        classes = []
        functions = []
        imports = []

        for child in children:
            node_data = self.graph.nodes[child]
            node_type = node_data.get("type")

            if node_type == "class":
                classes.append(
                    {"name": node_data.get("name"), "node": child, "data": node_data}
                )
            elif node_type == "function":
                functions.append(
                    {"name": node_data.get("name"), "node": child, "data": node_data}
                )

        # Znajdź importy (krawędzie typu IMPORTS)
        for _, target, edge_data in self.graph.edges(file_node, data=True):
            if edge_data.get("type") == "IMPORTS":
                imports.append(target)

        return {
            "file": file_path,
            "classes": classes,
            "functions": functions,
            "imports": imports,
            "dependents": self.get_dependencies(file_path),
        }

    def get_impact_analysis(self, file_path: str) -> Dict[str, Any]:
        """
        Analizuje wpływ usunięcia/modyfikacji pliku.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Raport wpływu na inne pliki
        """
        file_node = f"file:{file_path}"

        if file_node not in self.graph:
            return {"error": f"Plik {file_path} nie istnieje w grafie"}

        # Znajdź wszystkie pliki, które importują ten plik
        importers = []
        for source, target, edge_data in self.graph.edges(data=True):
            if target == file_node and edge_data.get("type") == "IMPORTS":
                if source.startswith("file:"):
                    importers.append(source.replace("file:", ""))

        # Znajdź wszystkie pliki w downstream (zależne pośrednio)
        all_dependents = set()
        for node in self.graph.nodes():
            if node.startswith("file:") and node != file_node:
                if nx.has_path(self.graph, node, file_node):
                    all_dependents.add(node.replace("file:", ""))

        return {
            "file": file_path,
            "direct_importers": importers,
            "all_affected_files": list(all_dependents),
            "impact_score": len(all_dependents),
            "warning": (
                f"Usunięcie lub modyfikacja tego pliku wpłynie na {len(all_dependents)} plików"
                if all_dependents
                else "Ten plik nie ma zależności downstream"
            ),
        }

    def save_graph(self) -> None:
        """Zapisuje graf do pliku JSON."""
        try:
            # Konwertuj graf do JSON
            data = nx.node_link_data(self.graph)

            with open(self.graph_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"Graf zapisany do {self.graph_file}")
        except Exception as e:
            logger.error(f"Błąd podczas zapisywania grafu: {e}")

    def load_graph(self) -> bool:
        """
        Ładuje graf z pliku JSON.

        Returns:
            True jeśli udało się załadować, False w przeciwnym razie
        """
        if not self.graph_file.exists():
            logger.info("Plik grafu nie istnieje, rozpoczynam od pustego grafu")
            return False

        try:
            with open(self.graph_file, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.graph = nx.node_link_graph(data, directed=True)
            logger.info(
                f"Graf załadowany: {self.graph.number_of_nodes()} węzłów, {self.graph.number_of_edges()} krawędzi"
            )
            return True
        except Exception as e:
            logger.error(f"Błąd podczas ładowania grafu: {e}")
            return False

    def get_graph_summary(self) -> Dict[str, Any]:
        """
        Zwraca podsumowanie grafu.

        Returns:
            Statystyki grafu
        """
        node_types = {}
        edge_types = {}

        for node, data in self.graph.nodes(data=True):
            node_type = data.get("type", "unknown")
            node_types[node_type] = node_types.get(node_type, 0) + 1

        for _, _, data in self.graph.edges(data=True):
            edge_type = data.get("type", "unknown")
            edge_types[edge_type] = edge_types.get(edge_type, 0) + 1

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "node_types": node_types,
            "edge_types": edge_types,
        }


class CodeVisitor(ast.NodeVisitor):
    """AST Visitor do ekstrakcji informacji o kodzie."""

    def __init__(self, file_node: str, graph: nx.DiGraph, file_path: str):
        """
        Inicjalizacja CodeVisitor.

        Args:
            file_node: Identyfikator węzła pliku w grafie
            graph: Graf do wypełnienia
            file_path: Ścieżka do pliku (do logowania)
        """
        self.file_node = file_node
        self.graph = graph
        self.file_path = file_path
        self.current_class = None  # Śledzimy aktualną klasę

    def visit_Import(self, node: ast.Import) -> None:
        """Odwiedza instrukcję import."""
        for alias in node.names:
            module_name = alias.name
            self._add_import(module_name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Odwiedza instrukcję from...import."""
        if node.module:
            self._add_import(node.module)
        self.generic_visit(node)

    def _add_import(self, module_name: str) -> None:
        """Dodaje krawędź importu."""
        # Uproszczona logika - dodaj krawędź do modułu
        import_node = f"module:{module_name}"
        self.graph.add_node(import_node, type="module", name=module_name)
        self.graph.add_edge(self.file_node, import_node, type="IMPORTS")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Odwiedza definicję klasy."""
        class_node = f"{self.file_node}::class:{node.name}"
        self.graph.add_node(
            class_node, type="class", name=node.name, file=self.file_path
        )
        self.graph.add_edge(self.file_node, class_node, type="CONTAINS")

        # Dodaj dziedziczenie
        for base in node.bases:
            if isinstance(base, ast.Name):
                base_class = f"class:{base.id}"
                self.graph.add_node(base_class, type="class_ref", name=base.id)
                self.graph.add_edge(class_node, base_class, type="INHERITS_FROM")

        # Zanurz się w klasę
        old_class = self.current_class
        self.current_class = class_node
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Odwiedza definicję funkcji."""
        if self.current_class:
            # Metoda w klasie
            func_node = f"{self.current_class}::method:{node.name}"
            self.graph.add_node(
                func_node,
                type="method",
                name=node.name,
                class_name=self.current_class,
                file=self.file_path,
            )
            self.graph.add_edge(self.current_class, func_node, type="CONTAINS")
        else:
            # Funkcja na poziomie modułu
            func_node = f"{self.file_node}::function:{node.name}"
            self.graph.add_node(
                func_node, type="function", name=node.name, file=self.file_path
            )
            self.graph.add_edge(self.file_node, func_node, type="CONTAINS")

        # Analizuj wywołania funkcji w ciele
        self._analyze_function_calls(node, func_node)

        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Odwiedza definicję funkcji asynchronicznej."""
        # Traktuj podobnie jak zwykłą funkcję
        self.visit_FunctionDef(node)

    def _analyze_function_calls(self, func_node: ast.FunctionDef, node_id: str) -> None:
        """
        Analizuje wywołania funkcji wewnątrz funkcji.

        Args:
            func_node: Węzeł AST funkcji
            node_id: ID węzła funkcji w grafie
        """
        for child in ast.walk(func_node):
            if isinstance(child, ast.Call):
                if isinstance(child.func, ast.Name):
                    # Proste wywołanie funkcji: foo()
                    called_func = f"function:{child.func.id}"
                    self.graph.add_node(
                        called_func, type="function_ref", name=child.func.id
                    )
                    self.graph.add_edge(node_id, called_func, type="CALLS")
                elif isinstance(child.func, ast.Attribute):
                    # Wywołanie metody: obj.method()
                    method_name = child.func.attr
                    called_method = f"method:{method_name}"
                    self.graph.add_node(
                        called_method, type="method_ref", name=method_name
                    )
                    self.graph.add_edge(node_id, called_method, type="CALLS")
