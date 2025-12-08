"""Moduł: research_skill - Skill badawczy z ingestią danych."""

from pathlib import Path
from typing import Annotated

from semantic_kernel.functions import kernel_function

from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.ingestion_engine import IngestionEngine
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ResearchSkill:
    """
    Skill badawczy rozszerzony o możliwość ingestii danych do grafu wiedzy.
    Współpracuje z WebSearchSkill i MemorySkill.
    """

    def __init__(self, graph_rag_service: GraphRAGService = None):
        """
        Inicjalizacja ResearchSkill.

        Args:
            graph_rag_service: Serwis GraphRAG (opcjonalny)
        """
        self.graph_rag = graph_rag_service or GraphRAGService()
        self.graph_rag.load_graph()
        self.ingestion_engine = IngestionEngine()

        logger.info("ResearchSkill zainicjalizowany")

    @kernel_function(
        name="digest_url",
        description="Pobiera stronę WWW, oczyszcza, przetwarza i dodaje do grafu wiedzy. Używaj gdy użytkownik chce 'przeczytać' lub 'przeanalizować' konkretny URL.",
    )
    async def digest_url(
        self,
        url: Annotated[str, "URL strony do pobrania i przetworzenia"],
    ) -> str:
        """
        Pobiera i przetwarza treść ze strony WWW, dodaje do grafu wiedzy.

        Args:
            url: URL do pobrania

        Returns:
            Potwierdzenie przetworzenia ze statystykami
        """
        logger.info(f"ResearchSkill: digest_url dla {url}")

        try:
            # Ingestia URL
            result = await self.ingestion_engine.ingest_url(url)
            text = result["text"]
            chunks = result["chunks"]
            metadata = result["metadata"]

            # Dodaj do VectorStore
            self.graph_rag.vector_store.upsert(
                text=text,
                metadata={**metadata, "entity_id": f"url_{url}"},
                chunk_text=False,  # Już podzielone
            )

            # Ekstrahuj wiedzę (wymaga LLM, więc zwracamy info że to async)
            # W praktyce będzie wywoływane przez agenta z dostępem do LLM

            # Zapisz graf
            self.graph_rag.save_graph()

            return f"""✅ URL przetworzony: {url}

📊 Statystyki:
- Ekstrahowane znaki: {len(text)}
- Fragmenty (chunks): {len(chunks)}
- Dodane do bazy wektorowej: ✓

💡 Informacja: Pełna ekstrakcja wiedzy (encje, relacje) będzie wykonana przy następnym zapytaniu do grafu."""

        except Exception as e:
            logger.error(f"Błąd podczas digest_url: {e}")
            return f"❌ Błąd podczas przetwarzania URL {url}: {str(e)}"

    @kernel_function(
        name="digest_file",
        description="Przetwarza plik lokalny (PDF, DOCX, obraz, audio, video, tekst) i dodaje do grafu wiedzy. Używaj gdy użytkownik chce 'przeczytać' lub 'przeanalizować' plik.",
    )
    async def digest_file(
        self,
        file_path: Annotated[str, "Ścieżka do pliku lokalnego"],
    ) -> str:
        """
        Przetwarza plik lokalny i dodaje do grafu wiedzy.

        Args:
            file_path: Ścieżka do pliku

        Returns:
            Potwierdzenie przetworzenia ze statystykami
        """
        logger.info(f"ResearchSkill: digest_file dla {file_path}")

        path = Path(file_path)

        if not path.exists():
            return f"❌ Plik nie istnieje: {file_path}"

        try:
            # Ingestia pliku
            result = await self.ingestion_engine.ingest_file(str(path))
            text = result["text"]
            chunks = result["chunks"]
            metadata = result.get("metadata", {})
            file_type = result["file_type"]

            # Dodaj do VectorStore
            self.graph_rag.vector_store.upsert(
                text=text,
                metadata={**metadata, "entity_id": f"file_{path.name}"},
                chunk_text=False,
            )

            # Zapisz graf
            self.graph_rag.save_graph()

            return f"""✅ Plik przetworzony: {path.name}

📋 Typ: {file_type}
📊 Statystyki:
- Ekstrahowane znaki: {len(text)}
- Fragmenty (chunks): {len(chunks)}
- Dodane do bazy wektorowej: ✓

💡 Informacja: Pełna ekstrakcja wiedzy (encje, relacje) będzie wykonana przy następnym zapytaniu do grafu."""

        except Exception as e:
            logger.error(f"Błąd podczas digest_file: {e}")
            return f"❌ Błąd podczas przetwarzania pliku {file_path}: {str(e)}"

    @kernel_function(
        name="digest_directory",
        description="Przetwarza wszystkie obsługiwane pliki w katalogu i dodaje do grafu wiedzy. Używaj gdy użytkownik chce przeanalizować folder z dokumentacją.",
    )
    async def digest_directory(
        self,
        directory_path: Annotated[str, "Ścieżka do katalogu"],
        recursive: Annotated[
            bool, "Czy przetwarzać podkatalogi rekurencyjnie (domyślnie False)"
        ] = False,
    ) -> str:
        """
        Przetwarza wszystkie pliki w katalogu.

        Args:
            directory_path: Ścieżka do katalogu
            recursive: Czy przetwarzać rekurencyjnie

        Returns:
            Podsumowanie przetworzenia
        """
        logger.info(
            f"ResearchSkill: digest_directory dla {directory_path} (recursive={recursive})"
        )

        # Walidacja ścieżki - tylko katalogi w ./workspace są dozwolone
        path = Path(directory_path).resolve()
        allowed_base = Path("./workspace").resolve()
        try:
            path.relative_to(allowed_base)
        except ValueError:
            return f"❌ Dostęp do katalogu {directory_path} jest zabroniony. Używaj tylko katalogów w workspace."

        if not path.exists() or not path.is_dir():
            return f"❌ Katalog nie istnieje: {directory_path}"

        # Obsługiwane rozszerzenia
        supported_extensions = {
            ".pdf",
            ".docx",
            ".doc",
            ".txt",
            ".md",
            ".rst",
            ".py",
            ".js",
            ".java",
            ".png",
            ".jpg",
            ".jpeg",
        }

        # Znajdź pliki
        if recursive:
            files = [
                f
                for f in path.rglob("*")
                if f.is_file() and f.suffix in supported_extensions
            ]
        else:
            files = [
                f
                for f in path.glob("*")
                if f.is_file() and f.suffix in supported_extensions
            ]

        if not files:
            return f"❌ Nie znaleziono obsługiwanych plików w {directory_path}"

        logger.info(f"Znaleziono {len(files)} plików do przetworzenia")

        # Przetwórz każdy plik
        processed = 0
        failed = 0
        total_chars = 0
        total_chunks = 0

        for file in files:
            try:
                result = await self.ingestion_engine.ingest_file(str(file))
                text = result["text"]
                chunks = result["chunks"]

                # Dodaj do VectorStore
                self.graph_rag.vector_store.upsert(
                    text=text,
                    metadata={**result["metadata"], "entity_id": f"file_{file.name}"},
                    chunk_text=False,
                )

                processed += 1
                total_chars += len(text)
                total_chunks += len(chunks)

            except Exception as e:
                logger.error(f"Błąd przetwarzania {file}: {e}")
                failed += 1

        # Zapisz graf
        self.graph_rag.save_graph()

        return f"""✅ Katalog przetworzony: {directory_path}

📊 Statystyki:
- Przetworzone pliki: {processed}/{len(files)}
- Błędy: {failed}
- Łącznie znaków: {total_chars}
- Łącznie fragmentów: {total_chunks}
- Dodane do bazy wektorowej: ✓

💡 Informacja: Pełna ekstrakcja wiedzy zostanie wykonana przy zapytaniach do grafu."""

    @kernel_function(
        name="get_knowledge_stats",
        description="Zwraca statystyki grafu wiedzy (encje, relacje, społeczności).",
    )
    def get_knowledge_stats(self) -> str:
        """
        Zwraca statystyki grafu wiedzy.

        Returns:
            Sformatowane statystyki
        """
        try:
            stats = self.graph_rag.get_stats()

            return f"""📊 Statystyki Grafu Wiedzy:

🔹 Encje: {stats['total_nodes']}
🔹 Relacje: {stats['total_edges']}
🔹 Społeczności: {stats['communities_count']}
🔹 Największa społeczność: {stats['largest_community_size']} encji

📋 Typy encji:
{chr(10).join([f'  - {k}: {v}' for k, v in stats['entity_types'].items()])}

🔗 Typy relacji:
{chr(10).join([f'  - {k}: {v}' for k, v in stats['relationship_types'].items()])}"""

        except Exception as e:
            logger.error(f"Błąd podczas pobierania statystyk: {e}")
            return f"❌ Błąd: {str(e)}"
