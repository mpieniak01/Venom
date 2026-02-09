"""Testy dla OracleAgent."""

from unittest.mock import AsyncMock, Mock, patch

import pytest
from semantic_kernel import Kernel

from venom_core.agents.oracle import OracleAgent
from venom_core.memory.graph_rag_service import GraphRAGService


@pytest.fixture
def mock_kernel():
    """Fixture dla mocka Kernel."""
    kernel = Mock(spec=Kernel)
    kernel.get_service = Mock(return_value=Mock())
    kernel.add_plugin = Mock()
    return kernel


@pytest.fixture
def mock_graph_rag_service(tmp_path):
    """Fixture dla mocka GraphRAGService."""
    graph_file = tmp_path / "test_graph.json"
    service = GraphRAGService(graph_file=str(graph_file))
    return service


def test_oracle_agent_init(mock_kernel, mock_graph_rag_service):
    """Test inicjalizacji OracleAgent."""
    agent = OracleAgent(mock_kernel, mock_graph_rag_service)

    assert agent.kernel is mock_kernel
    assert agent.graph_rag is mock_graph_rag_service
    assert agent.ingestion_engine is not None

    # Sprawdź czy plugin został zarejestrowany
    mock_kernel.add_plugin.assert_called_once()


def test_oracle_agent_init_without_graph_rag(mock_kernel):
    """Test inicjalizacji OracleAgent bez podanego GraphRAGService."""
    with patch("venom_core.agents.oracle.GraphRAGService") as MockGraphRAG:
        mock_service = Mock()
        MockGraphRAG.return_value = mock_service

        agent = OracleAgent(mock_kernel)

        assert agent.graph_rag is mock_service
        MockGraphRAG.assert_called_once()


@pytest.mark.asyncio
async def test_oracle_agent_process(mock_kernel, mock_graph_rag_service):
    """Test przetwarzania zapytania przez OracleAgent."""
    # Mock chat service
    mock_chat_service = AsyncMock()
    mock_response = Mock()
    mock_response.__str__ = Mock(return_value="Generated response from Oracle")
    mock_chat_service.get_chat_message_content.return_value = mock_response
    mock_kernel.get_service.return_value = mock_chat_service

    agent = OracleAgent(mock_kernel, mock_graph_rag_service)

    result = await agent.process("What is the relationship between X and Y?")

    assert "Generated response from Oracle" in result
    mock_chat_service.get_chat_message_content.assert_called_once()


@pytest.mark.asyncio
async def test_oracle_agent_process_error(mock_kernel, mock_graph_rag_service):
    """Test obsługi błędów podczas przetwarzania."""
    # Mock chat service z błędem
    mock_chat_service = AsyncMock()
    mock_chat_service.get_chat_message_content.side_effect = Exception("Test error")
    mock_kernel.get_service.return_value = mock_chat_service

    agent = OracleAgent(mock_kernel, mock_graph_rag_service)

    result = await agent.process("Test query")

    assert "błąd" in result.lower()
    assert "Test error" in result


def test_oracle_plugin_functions(mock_kernel, mock_graph_rag_service):
    """Test czy funkcje Oracle są poprawnie zarejestrowane."""
    OracleAgent(mock_kernel, mock_graph_rag_service)

    # Sprawdź czy plugin został dodany
    assert mock_kernel.add_plugin.called

    # Pobierz plugin
    call_args = mock_kernel.add_plugin.call_args
    plugin = call_args[0][0]

    # Sprawdź czy ma wymagane metody
    assert hasattr(plugin, "global_search")
    assert hasattr(plugin, "local_search")
    assert hasattr(plugin, "ingest_file")
    assert hasattr(plugin, "ingest_url")
    assert hasattr(plugin, "get_graph_stats")


@pytest.mark.asyncio
async def test_oracle_plugin_global_search(mock_kernel, mock_graph_rag_service):
    """Test funkcji global_search w pluginie."""
    OracleAgent(mock_kernel, mock_graph_rag_service)

    # Pobierz plugin
    plugin = mock_kernel.add_plugin.call_args[0][0]

    # Mock GraphRAG global_search
    mock_graph_rag_service.global_search = AsyncMock(
        return_value="Global search result"
    )

    result = await plugin.global_search("test query")

    assert result == "Global search result"
    mock_graph_rag_service.global_search.assert_called_once()


@pytest.mark.asyncio
async def test_oracle_plugin_local_search(mock_kernel, mock_graph_rag_service):
    """Test funkcji local_search w pluginie."""
    OracleAgent(mock_kernel, mock_graph_rag_service)

    # Pobierz plugin
    plugin = mock_kernel.add_plugin.call_args[0][0]

    # Mock GraphRAG local_search
    mock_graph_rag_service.local_search = AsyncMock(return_value="Local search result")

    result = await plugin.local_search("test query", max_hops=2)

    assert result == "Local search result"
    mock_graph_rag_service.local_search.assert_called_once()


@pytest.mark.asyncio
async def test_oracle_plugin_local_search_error(mock_kernel, mock_graph_rag_service):
    """Test błędu w local_search pluginu."""
    OracleAgent(mock_kernel, mock_graph_rag_service)
    plugin = mock_kernel.add_plugin.call_args[0][0]
    mock_graph_rag_service.local_search = AsyncMock(side_effect=RuntimeError("boom"))

    result = await plugin.local_search("test query", max_hops=3)

    assert "Błąd" in result
    assert "boom" in result


@pytest.mark.asyncio
async def test_oracle_plugin_ingest_file(mock_kernel, mock_graph_rag_service, tmp_path):
    """Test funkcji ingest_file w pluginie."""
    agent = OracleAgent(mock_kernel, mock_graph_rag_service)

    # Utwórz testowy plik
    test_file = tmp_path / "test.txt"
    test_file.write_text("Test content")

    # Pobierz plugin
    plugin = mock_kernel.add_plugin.call_args[0][0]

    # Mock ingestion_engine
    agent.ingestion_engine.ingest_file = AsyncMock(
        return_value={
            "text": "Test content",
            "chunks": ["Test content"],
            "metadata": {"file_name": "test.txt"},
            "file_type": "text",
        }
    )

    # Mock graph_rag methods
    mock_graph_rag_service.vector_store.upsert = Mock()
    mock_graph_rag_service.extract_knowledge_from_text = AsyncMock(
        return_value={"entities": 2, "relationships": 1}
    )

    result = await plugin.ingest_file(str(test_file))

    assert "Plik przetworzony" in result
    assert "test.txt" in result


@pytest.mark.asyncio
async def test_oracle_plugin_ingest_url(mock_kernel, mock_graph_rag_service):
    """Test funkcji ingest_url w pluginie."""
    agent = OracleAgent(mock_kernel, mock_graph_rag_service)
    plugin = mock_kernel.add_plugin.call_args[0][0]

    agent.ingestion_engine.ingest_url = AsyncMock(
        return_value={
            "text": "URL content",
            "chunks": ["URL content"],
            "metadata": {"url": "https://example.com"},
            "file_type": "web",
        }
    )
    mock_graph_rag_service.vector_store.upsert = Mock()
    mock_graph_rag_service.extract_knowledge_from_text = AsyncMock(
        return_value={"entities": 1, "relationships": 1}
    )

    result = await plugin.ingest_url("https://example.com")

    assert "URL przetworzony" in result
    assert "Encje: 1" in result
    mock_graph_rag_service.extract_knowledge_from_text.assert_called_once()


@pytest.mark.asyncio
async def test_oracle_plugin_ingest_url_error(mock_kernel, mock_graph_rag_service):
    """Test błędu w ingest_url pluginu."""
    agent = OracleAgent(mock_kernel, mock_graph_rag_service)
    plugin = mock_kernel.add_plugin.call_args[0][0]
    agent.ingestion_engine.ingest_url = AsyncMock(side_effect=RuntimeError("network"))

    result = await plugin.ingest_url("https://example.com")

    assert "Błąd podczas przetwarzania URL" in result
    assert "network" in result


def test_oracle_plugin_get_graph_stats(mock_kernel, mock_graph_rag_service):
    """Test funkcji get_graph_stats w pluginie."""
    OracleAgent(mock_kernel, mock_graph_rag_service)

    # Pobierz plugin
    plugin = mock_kernel.add_plugin.call_args[0][0]

    # Mock stats
    mock_graph_rag_service.get_stats = Mock(
        return_value={
            "total_nodes": 10,
            "total_edges": 15,
            "communities_count": 2,
            "largest_community_size": 5,
            "entity_types": {"Type1": 5, "Type2": 5},
            "relationship_types": {"RELATED_TO": 10, "DEPENDS_ON": 5},
        }
    )

    result = plugin.get_graph_stats()

    assert "Statystyki grafu wiedzy" in result
    assert "Encje: 10" in result
    assert "Relacje: 15" in result


def test_oracle_plugin_get_graph_stats_error(mock_kernel, mock_graph_rag_service):
    """Test błędu w get_graph_stats pluginu."""
    OracleAgent(mock_kernel, mock_graph_rag_service)
    plugin = mock_kernel.add_plugin.call_args[0][0]
    mock_graph_rag_service.get_stats = Mock(side_effect=RuntimeError("stats-fail"))

    result = plugin.get_graph_stats()

    assert "Błąd:" in result
    assert "stats-fail" in result


def test_oracle_system_prompt():
    """Test czy system prompt jest poprawnie zdefiniowany."""
    assert OracleAgent.SYSTEM_PROMPT is not None
    assert (
        "Wyrocznia" in OracleAgent.SYSTEM_PROMPT
        or "Oracle" in OracleAgent.SYSTEM_PROMPT
    )
    assert "global_search" in OracleAgent.SYSTEM_PROMPT
    assert "local_search" in OracleAgent.SYSTEM_PROMPT
