"""Testy integracyjne RAG - pełny workflow zapisywania i przywoływania informacji."""

import tempfile

import pytest

# Testy będą działać tylko jeśli dependencies są zainstalowane
pytest.importorskip("lancedb")
pytest.importorskip("sentence_transformers", exc_type=ImportError)

from venom_core.memory.embedding_service import EmbeddingService
from venom_core.memory.memory_skill import MemorySkill
from venom_core.memory.vector_store import VectorStore


@pytest.fixture
def temp_db_path():
    """Fixture dla tymczasowej bazy danych."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def memory_skill(temp_db_path):
    """Fixture dla MemorySkill z tymczasową bazą."""
    embedding_service = EmbeddingService(service_type="local")
    vector_store = VectorStore(
        db_path=temp_db_path,
        embedding_service=embedding_service,
    )
    return MemorySkill(vector_store=vector_store)


class TestRAGWorkflow:
    """Testy integracyjne RAG workflow."""

    def test_memorize_and_recall_basic(self, memory_skill):
        """Test podstawowy: zapisz informację i przypomniej ją."""
        # Zapisz informację
        content = "Zasady projektu Venom: Kod musi być po polsku"
        result = memory_skill.memorize(content, category="rules")

        assert "zapisana" in result.lower()

        # Przypomnij informację
        recall_result = memory_skill.recall("Jakim językiem piszemy kod?")

        assert recall_result is not None
        assert "polski" in recall_result.lower() or "polsku" in recall_result.lower()

    def test_memorize_and_recall_complex(self, memory_skill):
        """Test złożony: zapisz wiele informacji i wyszukaj właściwą."""
        # Zapisz kilka różnych informacji
        memory_skill.memorize(
            "Python jest głównym językiem programowania w projekcie Venom",
            category="technical",
        )
        memory_skill.memorize(
            "Testy piszemy używając pytest i pytest-asyncio", category="technical"
        )
        memory_skill.memorize(
            "Venom używa FastAPI do budowy REST API", category="technical"
        )
        memory_skill.memorize(
            "Spotkania zespołu odbywają się w środy o 10:00", category="organizational"
        )

        # Wyszukaj informację o testach
        result = memory_skill.recall("Jak piszemy testy?")

        assert "pytest" in result.lower()

        # Wyszukaj informację o API
        result = memory_skill.recall("Jaki framework używamy do API?")

        assert "fastapi" in result.lower()

        # Wyszukaj informację organizacyjną
        result = memory_skill.recall("Kiedy są spotkania?")

        assert "środy" in result.lower() or "10:00" in result.lower()

    def test_recall_no_results(self, memory_skill):
        """Test recall gdy nie ma wyników."""
        result = memory_skill.recall("Pytanie o coś czego nie ma w pamięci xyz123")

        assert "nie znalazłem" in result.lower() or "brak" in result.lower()

    def test_memorize_long_text(self, memory_skill):
        """Test zapamiętywania długiego tekstu (z automatycznym chunkingiem)."""
        # Utwórz długi tekst dokumentacji
        long_text = (
            """
        Venom to zaawansowany system agentów AI.

        Architektura składa się z kilku warstw:
        1. Warstwa percepcji - odpowiedzialna za wejście (tekst, obraz, dźwięk)
        2. Warstwa przetwarzania - jądro z agentami
        3. Warstwa wykonawcza - skills i narzędzia
        4. Warstwa pamięci - długoterminowe przechowywanie wiedzy

        Główne agenty to:
        - ChatAgent: rozmowy ogólne
        - CoderAgent: pisanie kodu
        - CriticAgent: review kodu
        - LibrarianAgent: zarządzanie plikami

        System używa Semantic Kernel od Microsoft jako framework orkiestracji.
        """
            * 5
        )  # Powielamy aby tekst był długi

        result = memory_skill.memorize(long_text, category="documentation")

        assert "zapisana" in result.lower()
        # Powinno być kilka fragmentów
        assert any(char.isdigit() for char in result)

        # Sprawdź czy możemy znaleźć informacje z różnych części tekstu
        result1 = memory_skill.recall("Co to jest ChatAgent?")
        assert "chat" in result1.lower()

        result2 = memory_skill.recall("Jakie są warstwy w architekturze?")
        assert (
            "warstwa" in result2.lower()
            or "percepcji" in result2.lower()
            or "pamięci" in result2.lower()
        )

    def test_memory_search_function(self, memory_skill):
        """Test funkcji memory_search (technicznej)."""
        # Zapisz dane
        memory_skill.memorize("Test informacja 1", category="test")
        memory_skill.memorize("Test informacja 2", category="test")

        # Wyszukaj używając memory_search
        result = memory_skill.memory_search("test informacja", limit=2)

        assert "wynik" in result.lower()
        assert "informacja" in result.lower()

    def test_category_metadata(self, memory_skill):
        """Test czy kategorie są prawidłowo zapisywane i zwracane."""
        # Zapisz z różnymi kategoriami
        memory_skill.memorize("Informacja techniczna", category="technical")
        memory_skill.memorize("Informacja biznesowa", category="business")

        # Wyszukaj i sprawdź czy kategoria jest w wyniku
        result = memory_skill.recall("informacja techniczna")

        assert "kategoria" in result.lower() or "technical" in result.lower()

    def test_persistence_across_instances(self, temp_db_path):
        """Test persystencji danych między różnymi instancjami."""
        # Pierwsza instancja - zapisz dane
        embedding_service1 = EmbeddingService(service_type="local")
        vector_store1 = VectorStore(
            db_path=temp_db_path, embedding_service=embedding_service1
        )
        skill1 = MemorySkill(vector_store=vector_store1)

        skill1.memorize("Dane do persystencji", category="test")

        # Druga instancja - odczytaj dane
        embedding_service2 = EmbeddingService(service_type="local")
        vector_store2 = VectorStore(
            db_path=temp_db_path, embedding_service=embedding_service2
        )
        skill2 = MemorySkill(vector_store=vector_store2)

        result = skill2.recall("persystencji")

        assert "dane" in result.lower() or "persystencji" in result.lower()

    def test_empty_content_memorize(self, memory_skill):
        """Test próby zapamiętania pustej treści."""
        result = memory_skill.memorize("", category="test")

        assert "błąd" in result.lower() or "error" in result.lower()

    def test_semantic_search_accuracy(self, memory_skill):
        """Test dokładności wyszukiwania semantycznego."""
        # Zapisz informacje używając różnych sformułowań
        memory_skill.memorize(
            "Framework FastAPI jest używany do budowy REST API", category="tech"
        )
        memory_skill.memorize("Python jest językiem programowania", category="tech")
        memory_skill.memorize(
            "Venom ma architekturę opartą na agentach", category="arch"
        )

        # Wyszukaj używając synonimów/podobnych pojęć
        result = memory_skill.recall("jaki framework do API?")

        # Powinien znaleźć FastAPI mimo że pytanie jest sformułowane inaczej
        assert "fastapi" in result.lower()

        # Wyszukaj o architekturze
        result = memory_skill.recall("struktura systemu")

        # Powinien znaleźć informację o architekturze
        assert "agent" in result.lower() or "architektur" in result.lower()


class TestAcceptanceCriteria:
    """Testy kryteriów akceptacji z dokumentacji zadania."""

    def test_criterion_1_save_knowledge(self, memory_skill):
        """
        Kryterium 1: Zapis Wiedzy
        Wysłanie tekstu zapisuje wektor w LanceDB.
        """
        text = "Zasady projektu Venom: Kod musi być po polsku"
        result = memory_skill.memorize(text, category="rules")

        # Sprawdź czy zapis się powiódł
        assert "zapisana" in result.lower()

        # Sprawdź czy dane są w bazie (przez wyszukiwanie)
        search_result = memory_skill.vector_store.search("Zasady Venom")
        assert len(search_result) > 0

    def test_criterion_2_recall(self, memory_skill):
        """
        Kryterium 2: Przywoływanie
        Zadanie pytania powoduje przeszukanie pamięci i odpowiedź na podstawie zapisanych danych.
        """
        # Zapisz zasadę
        memory_skill.memorize("Zasady projektu Venom: Kod musi być po polsku")

        # Zadaj pytanie
        answer = memory_skill.recall("Jakim językiem piszemy w projekcie?")

        # Sprawdź czy odpowiedź zawiera informację o języku polskim
        assert (
            "polski" in answer.lower()
            or "polsku" in answer.lower()
            or "po polsku" in answer.lower()
        )

    def test_criterion_3_local_mode(self, temp_db_path):
        """
        Kryterium 3: Lokalność
        Cały proces działa offline w trybie local.
        """
        # Utwórz system w trybie lokalnym
        embedding_service = EmbeddingService(service_type="local")
        assert embedding_service.service_type == "local"

        vector_store = VectorStore(
            db_path=temp_db_path, embedding_service=embedding_service
        )
        skill = MemorySkill(vector_store=vector_store)

        # Test pełnego workflow bez połączenia zewnętrznego
        skill.memorize("Test lokalności", category="test")
        result = skill.recall("lokalność")

        assert "test" in result.lower() or "lokalność" in result.lower()

    def test_criterion_4_persistence(self, temp_db_path):
        """
        Kryterium 4: Persystencja
        Po restarcie aplikacji dane są nadal dostępne.
        """
        # Symulacja pierwszego uruchomienia
        embedding_service1 = EmbeddingService(service_type="local")
        vector_store1 = VectorStore(
            db_path=temp_db_path, embedding_service=embedding_service1
        )
        skill1 = MemorySkill(vector_store=vector_store1)

        # Zapisz informację
        skill1.memorize("Dane które muszą przetrwać restart", category="persistent")

        # Symulacja restartu - nowe instancje
        embedding_service2 = EmbeddingService(service_type="local")
        vector_store2 = VectorStore(
            db_path=temp_db_path, embedding_service=embedding_service2
        )
        skill2 = MemorySkill(vector_store=vector_store2)

        # Sprawdź czy dane są dostępne
        result = skill2.recall("restart")
        assert "przetrwać" in result.lower() or "restart" in result.lower()
