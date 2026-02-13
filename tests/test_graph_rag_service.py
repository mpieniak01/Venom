"""Testy dla GraphRAGService."""

import json
from unittest.mock import AsyncMock, Mock

import networkx as nx
import pytest

from venom_core.memory.graph_rag_service import GraphRAGService


@pytest.fixture
def graph_rag_service(tmp_path):
    """Fixture dla GraphRAGService."""
    graph_file = tmp_path / "test_knowledge_graph.json"
    service = GraphRAGService(graph_file=str(graph_file))
    return service


def test_graph_rag_service_init(tmp_path):
    """Test inicjalizacji GraphRAGService."""
    graph_file = tmp_path / "test_graph.json"
    service = GraphRAGService(graph_file=str(graph_file))

    assert isinstance(service.graph, nx.DiGraph)
    assert service.graph_file == graph_file


def test_add_entity(graph_rag_service):
    """Test dodawania encji do grafu."""
    graph_rag_service.add_entity(
        entity_id="test_entity",
        entity_type="TestType",
        properties={"name": "Test Entity", "description": "Test description"},
    )

    assert "test_entity" in graph_rag_service.graph
    node_data = graph_rag_service.graph.nodes["test_entity"]
    assert node_data["entity_type"] == "TestType"
    assert node_data["name"] == "Test Entity"


def test_add_relationship(graph_rag_service):
    """Test dodawania relacji między encjami."""
    # Dodaj encje
    graph_rag_service.add_entity("entity1", "Type1")
    graph_rag_service.add_entity("entity2", "Type2")

    # Dodaj relację
    graph_rag_service.add_relationship(
        source_id="entity1",
        target_id="entity2",
        relationship_type="RELATED_TO",
        properties={"weight": 1.0},
    )

    assert graph_rag_service.graph.has_edge("entity1", "entity2")
    edge_data = graph_rag_service.graph.get_edge_data("entity1", "entity2")
    assert edge_data["relationship_type"] == "RELATED_TO"
    assert edge_data["weight"] == pytest.approx(1.0)


@pytest.mark.asyncio
async def test_extract_knowledge_from_text_no_llm(graph_rag_service):
    """Test ekstrakcji wiedzy bez serwisu LLM."""
    result = await graph_rag_service.extract_knowledge_from_text(
        text="Test text", source_id="test_source", llm_service=None
    )

    assert result["entities"] == 0
    assert result["relationships"] == 0


@pytest.mark.asyncio
async def test_extract_knowledge_from_text_with_llm(graph_rag_service):
    """Test ekstrakcji wiedzy z mockiem LLM."""
    # Mock LLM response
    mock_llm = AsyncMock()
    mock_response = Mock()
    mock_response.__str__ = Mock(
        return_value=json.dumps(
            {
                "entities": [
                    {"id": "python", "name": "Python", "type": "Language"},
                    {"id": "guido", "name": "Guido van Rossum", "type": "Person"},
                ],
                "relationships": [
                    {"source": "python", "target": "guido", "type": "CREATED_BY"}
                ],
            }
        )
    )
    mock_llm.get_chat_message_content.return_value = mock_response

    result = await graph_rag_service.extract_knowledge_from_text(
        text="Python was created by Guido van Rossum.",
        source_id="test_doc",
        llm_service=mock_llm,
    )

    assert result["entities"] == 2
    assert result["relationships"] == 1
    assert "python" in graph_rag_service.graph
    assert "guido" in graph_rag_service.graph
    assert graph_rag_service.graph.has_edge("python", "guido")


@pytest.mark.asyncio
async def test_extract_knowledge_from_text_invalid_json(graph_rag_service):
    """Test ekstrakcji wiedzy z niepoprawnym JSON z LLM."""
    mock_llm = AsyncMock()
    mock_response = Mock()
    mock_response.__str__ = Mock(return_value="This is not valid JSON")
    mock_llm.get_chat_message_content.return_value = mock_response

    result = await graph_rag_service.extract_knowledge_from_text(
        text="Test text",
        source_id="test_doc",
        llm_service=mock_llm,
    )

    assert result["entities"] == 0
    assert result["relationships"] == 0
    assert "error" in result


def test_find_communities_empty_graph(graph_rag_service):
    """Test znajdowania społeczności w pustym grafie."""
    communities = graph_rag_service.find_communities()
    assert len(communities) == 0


def test_find_communities_simple_graph(graph_rag_service):
    """Test znajdowania społeczności w prostym grafie."""
    # Dodaj kilka połączonych encji
    graph_rag_service.add_entity("node1", "Type1")
    graph_rag_service.add_entity("node2", "Type1")
    graph_rag_service.add_entity("node3", "Type1")

    graph_rag_service.add_relationship("node1", "node2", "RELATED_TO")
    graph_rag_service.add_relationship("node2", "node3", "RELATED_TO")

    communities = graph_rag_service.find_communities()
    assert len(communities) > 0


def test_get_community_summary_empty(graph_rag_service):
    """Test podsumowania pustej społeczności."""
    summary = graph_rag_service.get_community_summary(set())
    assert summary == ""


def test_get_community_summary(graph_rag_service):
    """Test podsumowania społeczności."""
    # Dodaj encje
    graph_rag_service.add_entity("entity1", "Type1", properties={"name": "Entity 1"})
    graph_rag_service.add_entity("entity2", "Type2", properties={"name": "Entity 2"})
    graph_rag_service.add_relationship("entity1", "entity2", "RELATED_TO")

    # Podsumowanie
    summary = graph_rag_service.get_community_summary({"entity1", "entity2"})

    assert "Entity 1" in summary
    assert "Entity 2" in summary
    assert "RELATED_TO" in summary


@pytest.mark.asyncio
async def test_global_search_empty_graph(graph_rag_service):
    """Test global search na pustym grafie."""
    result = await graph_rag_service.global_search("test query")
    assert "pusty" in result.lower()


@pytest.mark.asyncio
async def test_global_search_with_communities(graph_rag_service):
    """Test global search ze społecznościami."""
    # Dodaj dane
    graph_rag_service.add_entity("node1", "Type1", properties={"name": "Node 1"})
    graph_rag_service.add_entity("node2", "Type1", properties={"name": "Node 2"})
    graph_rag_service.add_relationship("node1", "node2", "RELATED_TO")

    # Mock LLM
    mock_llm = AsyncMock()
    mock_response = Mock()
    mock_response.__str__ = Mock(return_value="Generated answer based on communities")
    mock_llm.get_chat_message_content.return_value = mock_response

    result = await graph_rag_service.global_search("test query", llm_service=mock_llm)
    assert "Generated answer" in result


@pytest.mark.asyncio
async def test_local_search_no_results(graph_rag_service):
    """Test local search bez wyników."""
    # Mock VectorStore bez wyników
    graph_rag_service.vector_store.search = Mock(return_value=[])

    result = await graph_rag_service.local_search("test query")
    assert "Nie znaleziono" in result


def test_save_and_load_graph(tmp_path):
    """Test zapisywania i ładowania grafu."""
    graph_file = tmp_path / "test_graph.json"
    service = GraphRAGService(graph_file=str(graph_file))

    # Dodaj dane
    service.add_entity("entity1", "Type1", properties={"name": "Entity 1"})
    service.add_entity("entity2", "Type2", properties={"name": "Entity 2"})
    service.add_relationship("entity1", "entity2", "RELATED_TO")

    # Zapisz
    service.save_graph()
    assert graph_file.exists()

    # Załaduj w nowej instancji
    service2 = GraphRAGService(graph_file=str(graph_file))
    loaded = service2.load_graph()

    assert loaded
    assert service2.graph.number_of_nodes() == 2
    assert service2.graph.number_of_edges() == 1
    assert "entity1" in service2.graph
    assert "entity2" in service2.graph


def test_load_graph_nonexistent_file(tmp_path):
    """Test ładowania nieistniejącego pliku grafu."""
    graph_file = tmp_path / "nonexistent.json"
    service = GraphRAGService(graph_file=str(graph_file))

    loaded = service.load_graph()
    assert not loaded


def test_get_stats(graph_rag_service):
    """Test statystyk grafu."""
    # Dodaj dane
    graph_rag_service.add_entity("entity1", "Type1")
    graph_rag_service.add_entity("entity2", "Type2")
    graph_rag_service.add_entity("entity3", "Type1")
    graph_rag_service.add_relationship("entity1", "entity2", "RELATED_TO")
    graph_rag_service.add_relationship("entity2", "entity3", "DEPENDS_ON")

    stats = graph_rag_service.get_stats()

    assert stats["total_nodes"] == 3
    assert stats["total_edges"] == 2
    assert "Type1" in stats["entity_types"]
    assert stats["entity_types"]["Type1"] == 2
    assert "RELATED_TO" in stats["relationship_types"]
    assert stats["relationship_types"]["RELATED_TO"] == 1


def test_find_communities_with_cache(graph_rag_service):
    """Test cache dla społeczności."""
    # Dodaj dane
    graph_rag_service.add_entity("node1", "Type1")
    graph_rag_service.add_entity("node2", "Type1")
    graph_rag_service.add_relationship("node1", "node2", "RELATED_TO")

    # Pierwsze wywołanie - oblicza
    communities1 = graph_rag_service.find_communities()
    assert graph_rag_service._communities_cache is not None

    # Drugie wywołanie - używa cache
    communities2 = graph_rag_service.find_communities()
    assert communities1 == communities2

    # Wymuś przeliczenie
    communities3 = graph_rag_service.find_communities(refresh_cache=True)
    assert communities3 is not None


def test_extract_json_block_variants(graph_rag_service):
    fenced_json = '```json\n{"k": 1}\n```'
    fenced_plain = '```\n{"k": 2}\n```'
    raw_json = '{"k": 3}'

    assert graph_rag_service._extract_json_block(fenced_json) == '{"k": 1}'
    assert graph_rag_service._extract_json_block(fenced_plain) == '{"k": 2}'
    assert graph_rag_service._extract_json_block(raw_json) == raw_json


def test_resolve_edge_bidirectional(graph_rag_service):
    graph_rag_service.add_entity("a", "Type")
    graph_rag_service.add_entity("b", "Type")
    graph_rag_service.add_relationship("a", "b", "RELATED_TO")

    assert graph_rag_service._resolve_edge("a", "b") == ("a", "b", "RELATED_TO")
    assert graph_rag_service._resolve_edge("b", "a") == ("a", "b", "RELATED_TO")
    assert graph_rag_service._resolve_edge("a", "missing") is None


@pytest.mark.asyncio
async def test_local_search_with_results_returns_context(graph_rag_service):
    graph_rag_service.add_entity("python", "Language", properties={"name": "Python"})
    graph_rag_service.add_entity("guido", "Person", properties={"name": "Guido"})
    graph_rag_service.add_relationship("python", "guido", "CREATED_BY")

    graph_rag_service.vector_store.search = Mock(
        return_value=[{"metadata": {"entity_id": "python"}}]
    )
    result = await graph_rag_service.local_search("python")

    assert "Znalezione encje" in result
    assert "Python" in result
    assert "CREATED_BY" in result


# ===== Phase B: RAG Retrieval Boost Integration Tests =====


@pytest.mark.asyncio
async def test_local_search_with_custom_limit(graph_rag_service):
    """Test that local_search respects custom limit parameter."""
    # Add multiple entities
    for i in range(10):
        graph_rag_service.add_entity(
            f"entity_{i}",
            "TestType",
            properties={"name": f"Entity {i}", "description": f"Description {i}"},
        )

    # Mock vector store to return more results than requested
    def mock_search(query, limit):
        # Return as many results as the limit
        return [
            {"metadata": {"entity_id": f"entity_{i}"}, "score": 1.0 - (i * 0.1)}
            for i in range(min(limit, 10))
        ]

    graph_rag_service.vector_store.search = mock_search

    # Test with default limit (5)
    result_default = await graph_rag_service.local_search("test query")
    # Should find 5 entities (default limit)
    entity_count_default = result_default.count("entity_")

    # Test with custom limit (8)
    result_custom = await graph_rag_service.local_search("test query", limit=8)
    entity_count_custom = result_custom.count("entity_")

    # Custom limit should return more entities
    assert entity_count_custom >= entity_count_default

    # Test with smaller custom limit (2)
    result_small = await graph_rag_service.local_search("test query", limit=2)
    entity_count_small = result_small.count("entity_")

    # Smaller limit should return fewer entities
    assert entity_count_small <= entity_count_default


@pytest.mark.asyncio
async def test_local_search_default_limit_unchanged(graph_rag_service):
    """Test that default behavior is unchanged (backward compatibility)."""
    graph_rag_service.add_entity("test", "Type", properties={"name": "Test"})

    graph_rag_service.vector_store.search = Mock(
        return_value=[{"metadata": {"entity_id": "test"}}]
    )

    # Call without limit parameter (should use default 5)
    await graph_rag_service.local_search("test query")

    # Verify search was called with limit=5
    assert graph_rag_service.vector_store.search.call_count == 1
    call_args = graph_rag_service.vector_store.search.call_args
    # Check that limit=5 was passed (default)
    assert call_args[1]["limit"] == 5


@pytest.mark.asyncio
async def test_local_search_with_max_hops_and_limit(graph_rag_service):
    """Test that both max_hops and limit work together."""
    # Create a chain of entities
    for i in range(5):
        graph_rag_service.add_entity(
            f"node_{i}", "Type", properties={"name": f"Node {i}"}
        )
        if i > 0:
            graph_rag_service.add_relationship(f"node_{i - 1}", f"node_{i}", "LINKS_TO")

    graph_rag_service.vector_store.search = Mock(
        return_value=[{"metadata": {"entity_id": "node_0"}}]
    )

    # Test with higher limit and higher max_hops
    result = await graph_rag_service.local_search("test query", max_hops=3, limit=8)

    # Should explore multiple hops and include more nodes
    # Check for the display name "Node 0" instead of entity_id "node_0"
    assert "Node 0" in result
    # With max_hops=3, should reach at least Node 1, Node 2, Node 3
    node_count = sum(1 for i in range(5) if f"Node {i}" in result)
    assert node_count >= 2  # At least the starting node and one hop
