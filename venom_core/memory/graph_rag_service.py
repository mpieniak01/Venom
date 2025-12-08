"""Moduł: graph_rag_service - GraphRAG z ekstrakcją wiedzy i multi-hop reasoning."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import networkx as nx

from venom_core.config import SETTINGS
from venom_core.memory.embedding_service import EmbeddingService
from venom_core.memory.vector_store import VectorStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class GraphRAGService:
    """
    Zaawansowany silnik GraphRAG z ekstrakcją wiedzy i multi-hop reasoning.
    Rozbudowa istniejącego CodeGraphStore dla ogólnych danych (nie tylko kodu).
    """

    def __init__(
        self,
        graph_file: str = None,
        vector_store: VectorStore = None,
        embedding_service: EmbeddingService = None,
    ):
        """
        Inicjalizacja GraphRAGService.

        Args:
            graph_file: Ścieżka do pliku z grafem (domyślnie data/memory/knowledge_graph.json)
            vector_store: VectorStore dla hybrydowego wyszukiwania
            embedding_service: Serwis embeddingów
        """
        self.graph_file = Path(
            graph_file or f"{SETTINGS.MEMORY_ROOT}/knowledge_graph.json"
        )
        self.graph_file.parent.mkdir(parents=True, exist_ok=True)

        # Graf wiedzy (DiGraph = Directed Graph)
        self.graph = nx.DiGraph()

        # VectorStore i EmbeddingService dla hybrydowego wyszukiwania
        self.vector_store = vector_store or VectorStore(
            collection_name="knowledge_graph"
        )
        self.embedding_service = embedding_service or EmbeddingService()

        # Cache dla społeczności (communities)
        self._communities_cache: Optional[List[Set[str]]] = None

        logger.info(f"GraphRAGService zainicjalizowany: graph_file={self.graph_file}")

    def add_entity(
        self,
        entity_id: str,
        entity_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Dodaje encję (węzeł) do grafu wiedzy.

        Args:
            entity_id: Unikalny identyfikator encji
            entity_type: Typ encji (np. 'Person', 'Document', 'Concept')
            properties: Opcjonalne właściwości encji
        """
        properties = properties or {}
        self.graph.add_node(entity_id, entity_type=entity_type, **properties)
        logger.debug(f"Dodano encję: {entity_id} (typ: {entity_type})")

    def add_relationship(
        self,
        source_id: str,
        target_id: str,
        relationship_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Dodaje relację (krawędź) między encjami.

        Args:
            source_id: ID encji źródłowej
            target_id: ID encji docelowej
            relationship_type: Typ relacji (np. 'RELATED_TO', 'AUTHORED_BY')
            properties: Opcjonalne właściwości relacji
        """
        properties = properties or {}
        self.graph.add_edge(
            source_id, target_id, relationship_type=relationship_type, **properties
        )
        logger.debug(f"Dodano relację: {source_id} -{relationship_type}-> {target_id}")

    async def extract_knowledge_from_text(
        self, text: str, source_id: str, llm_service=None
    ) -> Dict[str, Any]:
        """
        Ekstrahuje wiedzę z tekstu używając LLM (trójki: podmiot-relacja-dopełnienie).

        Args:
            text: Tekst do analizy
            source_id: ID źródła (dokumentu)
            llm_service: Serwis LLM do ekstrakcji

        Returns:
            Dict ze statystykami ekstrakcji
        """
        if not llm_service:
            logger.warning("Brak serwisu LLM, pomijam ekstrakcję wiedzy")
            return {"entities": 0, "relationships": 0}

        try:
            # Prompt dla ekstrakcji wiedzy
            extraction_prompt = f"""Przeanalizuj poniższy tekst i wyekstrahuj kluczowe fakty w formie trójek (podmiot, relacja, dopełnienie).

Format odpowiedzi (JSON):
{{
  "entities": [
    {{"id": "unique_id", "name": "nazwa", "type": "typ"}},
    ...
  ],
  "relationships": [
    {{"source": "id_podmiotu", "target": "id_dopełnienia", "type": "typ_relacji"}},
    ...
  ]
}}

Przykład:
Tekst: "Python jest językiem programowania stworzonym przez Guido van Rossum w 1991 roku."

Odpowiedź:
{{
  "entities": [
    {{"id": "python", "name": "Python", "type": "ProgrammingLanguage"}},
    {{"id": "guido_van_rossum", "name": "Guido van Rossum", "type": "Person"}},
    {{"id": "1991", "name": "1991", "type": "Year"}}
  ],
  "relationships": [
    {{"source": "python", "target": "guido_van_rossum", "type": "CREATED_BY"}},
    {{"source": "python", "target": "1991", "type": "CREATED_IN"}}
  ]
}}

Tekst do analizy:
{text[:2000]}

Odpowiedź (JSON):"""

            # Wywołaj LLM
            from semantic_kernel.contents import ChatHistory
            from semantic_kernel.contents.chat_message_content import ChatMessageContent
            from semantic_kernel.contents.utils.author_role import AuthorRole

            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=extraction_prompt)
            )

            response = await llm_service.get_chat_message_content(
                chat_history=chat_history
            )
            result_text = str(response).strip()

            # Parsuj JSON (szukaj między ``` jeśli są)
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0].strip()

            data = json.loads(result_text)

            # Dodaj encje do grafu
            entities_count = 0
            for entity in data.get("entities", []):
                entity_id = entity.get("id")
                if not entity_id:
                    continue

                self.add_entity(
                    entity_id=entity_id,
                    entity_type=entity.get("type", "Unknown"),
                    properties={
                        "name": entity.get("name", entity_id),
                        "source": source_id,
                    },
                )
                entities_count += 1

            # Dodaj relacje do grafu
            relationships_count = 0
            for rel in data.get("relationships", []):
                source = rel.get("source")
                target = rel.get("target")
                rel_type = rel.get("type", "RELATED_TO")

                if source and target:
                    self.add_relationship(
                        source_id=source,
                        target_id=target,
                        relationship_type=rel_type,
                        properties={"source": source_id},
                    )
                    relationships_count += 1

            # Dodaj dokument jako encję
            self.add_entity(
                entity_id=source_id,
                entity_type="Document",
                properties={"text": text[:500]},
            )

            logger.info(
                f"Wyekstrahowano {entities_count} encji i {relationships_count} relacji z {source_id}"
            )

            return {"entities": entities_count, "relationships": relationships_count}

        except Exception as e:
            logger.error(f"Błąd podczas ekstrakcji wiedzy: {e}")
            return {"entities": 0, "relationships": 0, "error": str(e)}

    def find_communities(self, force_recompute: bool = False) -> List[Set[str]]:
        """
        Znajduje społeczności (communities) w grafie używając algorytmu Louvain.

        Args:
            force_recompute: Czy wymusić przeliczenie (ignoruj cache)

        Returns:
            Lista zbiorów węzłów (każdy zbiór to społeczność)
        """
        if self._communities_cache and not force_recompute:
            return self._communities_cache

        try:
            # Konwertuj na graf nieskierowany dla algorytmu community detection
            undirected = self.graph.to_undirected()

            # Użyj algorytmu Louvain
            import networkx.algorithms.community as nx_community

            communities = list(nx_community.greedy_modularity_communities(undirected))

            self._communities_cache = communities
            logger.info(f"Znaleziono {len(communities)} społeczności w grafie")

            return communities

        except Exception as e:
            logger.error(f"Błąd podczas znajdowania społeczności: {e}")
            return []

    def get_community_summary(self, community: Set[str]) -> str:
        """
        Tworzy podsumowanie społeczności (używane w global_search).

        Args:
            community: Zbiór ID węzłów w społeczności

        Returns:
            Tekstowe podsumowanie społeczności
        """
        if not community:
            return ""

        # Zbierz informacje o węzłach
        entities = []
        for node_id in community:
            if node_id not in self.graph:
                continue
            node_data = self.graph.nodes[node_id]
            entities.append(
                f"{node_data.get('name', node_id)} ({node_data.get('entity_type', 'Unknown')})"
            )

        # Zbierz relacje wewnątrz społeczności
        relationships = []
        for source in community:
            if source not in self.graph:
                continue
            for target in self.graph.successors(source):
                if target in community:
                    edge_data = self.graph.get_edge_data(source, target)
                    rel_type = edge_data.get("relationship_type", "RELATED_TO")
                    relationships.append(f"{source} -{rel_type}-> {target}")

        summary = f"Społeczność zawiera {len(entities)} encji:\n"
        summary += ", ".join(entities[:10])  # Ogranicz do 10
        if len(entities) > 10:
            summary += f" ... (i {len(entities) - 10} więcej)"

        if relationships:
            summary += f"\n\nKluczowe relacje ({len(relationships)}):\n"
            summary += "\n".join(relationships[:5])  # Ogranicz do 5
            if len(relationships) > 5:
                summary += f"\n... (i {len(relationships) - 5} więcej)"

        return summary

    async def global_search(self, query: str, llm_service=None) -> str:
        """
        Wyszukiwanie globalne oparte na podsumowaniach społeczności.
        Dobre do pytań typu "O czym jest ten projekt?".

        Args:
            query: Zapytanie użytkownika
            llm_service: Serwis LLM do syntezy odpowiedzi

        Returns:
            Odpowiedź na zapytanie
        """
        logger.info(f"Global search: {query[:100]}...")

        # Znajdź społeczności
        communities = self.find_communities()

        if not communities:
            return "Graf wiedzy jest pusty lub nie zawiera społeczności."

        # Stwórz podsumowania społeczności
        summaries = []
        for i, community in enumerate(communities, 1):
            summary = self.get_community_summary(community)
            summaries.append(f"## Społeczność {i}\n{summary}")

        context = "\n\n".join(summaries)

        # Użyj LLM do syntezy odpowiedzi
        if not llm_service:
            return f"Znaleziono {len(communities)} społeczności w grafie wiedzy.\n\n{context}"

        try:
            from semantic_kernel.contents import ChatHistory
            from semantic_kernel.contents.chat_message_content import ChatMessageContent
            from semantic_kernel.contents.utils.author_role import AuthorRole

            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.SYSTEM,
                    content="Jesteś analitykiem wiedzy. Na podstawie podsumowań społeczności odpowiedz na pytanie użytkownika.",
                )
            )
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER,
                    content=f"Kontekst:\n{context}\n\nPytanie: {query}\n\nOdpowiedź:",
                )
            )

            response = await llm_service.get_chat_message_content(
                chat_history=chat_history
            )
            return str(response).strip()

        except Exception as e:
            logger.error(f"Błąd podczas global_search: {e}")
            return f"Wystąpił błąd: {str(e)}\n\nDostępny kontekst:\n{context}"

    async def local_search(
        self, query: str, max_hops: int = 2, llm_service=None
    ) -> str:
        """
        Wyszukiwanie lokalne oparte na sąsiedztwie węzłów (multi-hop reasoning).
        Dobre do pytań typu "Jaki jest związek między X a Y?".

        Args:
            query: Zapytanie użytkownika
            max_hops: Maksymalna liczba "skoków" w grafie
            llm_service: Serwis LLM do syntezy odpowiedzi

        Returns:
            Odpowiedź na zapytanie
        """
        logger.info(f"Local search: {query[:100]}... (max_hops={max_hops})")

        # Najpierw użyj wyszukiwania wektorowego, aby znaleźć najbardziej relevantne węzły
        try:
            search_results = self.vector_store.search(query, limit=5)
            if not search_results:
                return "Nie znaleziono relewanatnych informacji w grafie wiedzy."

            # Zbierz ID węzłów z metadanych
            starting_nodes = []
            for result in search_results:
                node_id = result.get("metadata", {}).get("entity_id")
                if node_id and node_id in self.graph:
                    starting_nodes.append(node_id)

            if not starting_nodes:
                return "Nie znaleziono węzłów w grafie pasujących do zapytania."

            # Eksploruj sąsiedztwo (multi-hop)
            explored_nodes = set()
            explored_edges = []

            for start_node in starting_nodes[:3]:  # Ogranicz do 3 węzłów startowych
                # BFS do max_hops kroków
                visited = {start_node}
                queue = [(start_node, 0)]

                while queue:
                    current_node, depth = queue.pop(0)

                    if depth >= max_hops:
                        continue

                    explored_nodes.add(current_node)

                    # Eksploruj sąsiadów (zarówno następniki jak i poprzedniki)
                    for neighbor in list(self.graph.successors(current_node)) + list(
                        self.graph.predecessors(current_node)
                    ):
                        if neighbor not in visited:
                            visited.add(neighbor)
                            queue.append((neighbor, depth + 1))
                            explored_nodes.add(neighbor)

                            # Zapisz krawędź
                            if self.graph.has_edge(current_node, neighbor):
                                edge_data = self.graph.get_edge_data(
                                    current_node, neighbor
                                )
                                explored_edges.append(
                                    (
                                        current_node,
                                        neighbor,
                                        edge_data.get(
                                            "relationship_type", "RELATED_TO"
                                        ),
                                    )
                                )
                            elif self.graph.has_edge(neighbor, current_node):
                                edge_data = self.graph.get_edge_data(
                                    neighbor, current_node
                                )
                                explored_edges.append(
                                    (
                                        neighbor,
                                        current_node,
                                        edge_data.get(
                                            "relationship_type", "RELATED_TO"
                                        ),
                                    )
                                )

            # Zbuduj kontekst z eksplorowanego podgrafu
            context_parts = []

            # Encje
            context_parts.append(f"Znalezione encje ({len(explored_nodes)}):")
            for node_id in list(explored_nodes)[:20]:  # Ogranicz do 20
                node_data = self.graph.nodes[node_id]
                context_parts.append(
                    f"- {node_data.get('name', node_id)} ({node_data.get('entity_type', 'Unknown')})"
                )

            # Relacje
            if explored_edges:
                context_parts.append(f"\nZnalezione relacje ({len(explored_edges)}):")
                for source, target, rel_type in explored_edges[:20]:  # Ogranicz do 20
                    source_name = self.graph.nodes[source].get("name", source)
                    target_name = self.graph.nodes[target].get("name", target)
                    context_parts.append(f"- {source_name} -{rel_type}-> {target_name}")

            context = "\n".join(context_parts)

            # Użyj LLM do syntezy odpowiedzi
            if not llm_service:
                return context

            from semantic_kernel.contents import ChatHistory
            from semantic_kernel.contents.chat_message_content import ChatMessageContent
            from semantic_kernel.contents.utils.author_role import AuthorRole

            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.SYSTEM,
                    content="Jesteś analitykiem wiedzy. Na podstawie eksploracji grafu wiedzy odpowiedz na pytanie użytkownika. Wyjaśnij połączenia między encjami.",
                )
            )
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER,
                    content=f"Kontekst z grafu wiedzy:\n{context}\n\nPytanie: {query}\n\nOdpowiedź:",
                )
            )

            response = await llm_service.get_chat_message_content(
                chat_history=chat_history
            )
            return str(response).strip()

        except Exception as e:
            logger.error(f"Błąd podczas local_search: {e}")
            return f"Wystąpił błąd podczas wyszukiwania: {str(e)}"

    def save_graph(self) -> None:
        """Zapisuje graf do pliku JSON."""
        try:
            data = nx.node_link_data(self.graph)
            with open(self.graph_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Graf wiedzy zapisany do {self.graph_file}")
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
            self._communities_cache = None  # Wyczyść cache
            logger.info(
                f"Graf wiedzy załadowany: {self.graph.number_of_nodes()} węzłów, {self.graph.number_of_edges()} krawędzi"
            )
            return True
        except Exception as e:
            logger.error(f"Błąd podczas ładowania grafu: {e}")
            return False

    def get_stats(self) -> Dict[str, Any]:
        """
        Zwraca statystyki grafu wiedzy.

        Returns:
            Dict ze statystykami
        """
        entity_types = {}
        relationship_types = {}

        for node, data in self.graph.nodes(data=True):
            entity_type = data.get("entity_type", "Unknown")
            entity_types[entity_type] = entity_types.get(entity_type, 0) + 1

        for _, _, data in self.graph.edges(data=True):
            rel_type = data.get("relationship_type", "Unknown")
            relationship_types[rel_type] = relationship_types.get(rel_type, 0) + 1

        communities = self.find_communities()

        return {
            "total_nodes": self.graph.number_of_nodes(),
            "total_edges": self.graph.number_of_edges(),
            "entity_types": entity_types,
            "relationship_types": relationship_types,
            "communities_count": len(communities),
            "largest_community_size": (
                max([len(c) for c in communities]) if communities else 0
            ),
        }
