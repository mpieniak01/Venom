import pytest

import venom_core.execution.skills.research_skill as research_skill_mod


class DummyVectorStore:
    def __init__(self) -> None:
        self.upserts = []

    def upsert(self, text, metadata, chunk_text) -> None:
        self.upserts.append(
            {"text": text, "metadata": metadata, "chunk_text": chunk_text}
        )


class DummyGraphRag:
    def __init__(self, stats=None) -> None:
        self.loaded = False
        self.saved = False
        self.vector_store = DummyVectorStore()
        self._stats = stats

    def load_graph(self) -> None:
        self.loaded = True

    def save_graph(self) -> None:
        self.saved = True

    def get_stats(self):
        if isinstance(self._stats, Exception):
            raise self._stats
        return self._stats


class FakeIngestionEngine:
    def __init__(self) -> None:
        self.next_url_result = None
        self.next_file_results = []

    async def ingest_url(self, _url: str):
        return self.next_url_result

    async def ingest_file(self, _path: str):
        if self.next_file_results:
            return self.next_file_results.pop(0)
        return {
            "text": "",
            "chunks": [],
            "metadata": {},
            "file_type": "text",
        }


@pytest.mark.asyncio
async def test_digest_file_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(research_skill_mod, "IngestionEngine", FakeIngestionEngine)
    skill = research_skill_mod.ResearchSkill(graph_rag_service=DummyGraphRag())

    missing_path = tmp_path / "missing.txt"
    result = await skill.digest_file(str(missing_path))

    assert "Plik nie istnieje" in result


@pytest.mark.asyncio
async def test_digest_url_success(monkeypatch):
    monkeypatch.setattr(research_skill_mod, "IngestionEngine", FakeIngestionEngine)
    graph_rag = DummyGraphRag()
    skill = research_skill_mod.ResearchSkill(graph_rag_service=graph_rag)
    skill.ingestion_engine.next_url_result = {
        "text": "hello world",
        "chunks": ["hello", "world"],
        "metadata": {"source": "unit-test"},
    }

    result = await skill.digest_url("https://example.com")

    assert "URL przetworzony" in result
    assert graph_rag.saved is True
    assert graph_rag.vector_store.upserts
    assert (
        graph_rag.vector_store.upserts[0]["metadata"]["entity_id"]
        == "url_https://example.com"
    )


@pytest.mark.asyncio
async def test_digest_directory_rejects_outside_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(research_skill_mod, "IngestionEngine", FakeIngestionEngine)
    graph_rag = DummyGraphRag()
    skill = research_skill_mod.ResearchSkill(graph_rag_service=graph_rag)

    monkeypatch.chdir(tmp_path)
    forbidden = tmp_path / "outside"
    forbidden.mkdir()

    result = await skill.digest_directory(str(forbidden))

    assert "zabroniony" in result


@pytest.mark.asyncio
async def test_digest_directory_processes_files(tmp_path, monkeypatch):
    monkeypatch.setattr(research_skill_mod, "IngestionEngine", FakeIngestionEngine)
    graph_rag = DummyGraphRag()
    skill = research_skill_mod.ResearchSkill(graph_rag_service=graph_rag)
    skill.ingestion_engine.next_file_results = [
        {
            "text": "alpha",
            "chunks": ["alpha"],
            "metadata": {"source": "a"},
            "file_type": "txt",
        },
        {
            "text": "beta",
            "chunks": ["beta"],
            "metadata": {"source": "b"},
            "file_type": "txt",
        },
    ]

    monkeypatch.chdir(tmp_path)
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "a.txt").write_text("alpha", encoding="utf-8")
    (workspace / "b.md").write_text("beta", encoding="utf-8")

    result = await skill.digest_directory(str(workspace))

    assert "Katalog przetworzony" in result
    assert "Przetworzone pliki: 2/2" in result
    assert graph_rag.saved is True
    assert len(graph_rag.vector_store.upserts) == 2


def test_get_knowledge_stats_success(monkeypatch):
    monkeypatch.setattr(research_skill_mod, "IngestionEngine", FakeIngestionEngine)
    stats = {
        "total_nodes": 3,
        "total_edges": 2,
        "communities_count": 1,
        "largest_community_size": 3,
        "entity_types": {"Doc": 3},
        "relationship_types": {"related_to": 2},
    }
    skill = research_skill_mod.ResearchSkill(
        graph_rag_service=DummyGraphRag(stats=stats)
    )

    result = skill.get_knowledge_stats()

    assert "Statystyki Grafu Wiedzy" in result
    assert "Encje: 3" in result


def test_get_knowledge_stats_failure(monkeypatch):
    monkeypatch.setattr(research_skill_mod, "IngestionEngine", FakeIngestionEngine)
    skill = research_skill_mod.ResearchSkill(
        graph_rag_service=DummyGraphRag(stats=ValueError("boom"))
    )

    result = skill.get_knowledge_stats()

    assert "❌ Błąd" in result
