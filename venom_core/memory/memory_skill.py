"""Moduł: memory_skill - Plugin Semantic Kernel do obsługi pamięci wektorowej."""

from typing import Annotated

from semantic_kernel.functions import kernel_function

from venom_core.memory.vector_store import VectorStore
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class MemorySkill:
    """
    Skill do zarządzania pamięcią długoterminową Venoma.
    Pozwala agentom zapisywać i przypominać sobie informacje.
    """

    def __init__(self, vector_store: VectorStore = None):
        """
        Inicjalizacja MemorySkill.

        Args:
            vector_store: Instancja VectorStore (domyślnie nowa)
        """
        self.vector_store = vector_store or VectorStore()
        logger.info("MemorySkill zainicjalizowany")

    @kernel_function(
        name="recall",
        description="Przeszukuje pamięć długoterminową w poszukiwaniu informacji związanych z zapytaniem. Użyj tej funkcji, aby znaleźć wcześniej zapamiętane fakty, dokumentację lub kontekst.",
    )
    def recall(
        self,
        query: Annotated[
            str, "Zapytanie lub temat, o którym chcesz przypomnieć sobie informacje"
        ],
    ) -> str:
        """
        Przywołuje informacje z pamięci długoterminowej.

        Args:
            query: Zapytanie tekstowe

        Returns:
            Znalezione informacje lub komunikat o braku wyników
        """
        logger.info(f"Recall: szukanie informacji dla zapytania '{query[:100]}...'")

        try:
            results = self.vector_store.search(query, limit=3)

            if not results:
                return "Nie znalazłem żadnych informacji w pamięci na ten temat."

            # Formatuj wyniki
            output = "Znalazłem następujące informacje w pamięci:\n\n"
            for i, result in enumerate(results, 1):
                output += f"{i}. {result['text']}\n"
                if result.get("metadata"):
                    meta = result["metadata"]
                    if meta.get("category"):
                        output += f"   (Kategoria: {meta['category']})\n"
                output += "\n"

            logger.info(f"Recall: znaleziono {len(results)} wyników")
            return output.strip()

        except Exception as e:
            logger.error(f"Błąd podczas recall: {e}")
            return f"Wystąpił błąd podczas przeszukiwania pamięci: {str(e)}"

    @kernel_function(
        name="memorize",
        description="Zapisuje informację do pamięci długoterminowej. Użyj tej funkcji, aby zapamiętać ważne fakty, zasady, fragmenty dokumentacji lub kontekst, który może być przydatny w przyszłości.",
    )
    def memorize(
        self,
        content: Annotated[str, "Treść do zapamiętania"],
        category: Annotated[
            str, "Kategoria informacji (np. 'documentation', 'code_snippet', 'rule')"
        ] = "general",
    ) -> str:
        """
        Zapisuje informację do pamięci długoterminowej.

        Args:
            content: Treść do zapamiętania
            category: Kategoria informacji

        Returns:
            Potwierdzenie zapisu lub komunikat o błędzie
        """
        logger.info(
            f"Memorize: zapisywanie informacji (kategoria: {category}, długość: {len(content)})"
        )

        try:
            metadata = {"category": category}
            result = self.vector_store.upsert(
                text=content, metadata=metadata, chunk_text=True
            )

            logger.info(f"Memorize: {result['message']}")
            return f"Informacja została zapisana w pamięci ({result['message']})"

        except Exception as e:
            logger.error(f"Błąd podczas memorize: {e}")
            return f"Wystąpił błąd podczas zapisywania do pamięci: {str(e)}"

    @kernel_function(
        name="memory_search",
        description="Wyszukuje informacje w pamięci i zwraca surowe wyniki. Podobne do recall, ale zwraca więcej szczegółów technicznych.",
    )
    def memory_search(
        self,
        query: Annotated[str, "Zapytanie do wyszukania"],
        limit: Annotated[int, "Maksymalna liczba wyników (domyślnie 3)"] = 3,
    ) -> str:
        """
        Wyszukuje informacje w pamięci (wersja techniczna).

        Args:
            query: Zapytanie
            limit: Limit wyników

        Returns:
            Sformatowane wyniki wyszukiwania
        """
        logger.info(f"Memory search: '{query[:100]}...' (limit: {limit})")

        try:
            results = self.vector_store.search(query, limit=limit)

            if not results:
                return "Brak wyników w pamięci."

            output = f"Znaleziono {len(results)} wyników:\n\n"
            for i, result in enumerate(results, 1):
                output += f"[Wynik {i}] (score: {result['score']:.4f})\n"
                output += f"Tekst: {result['text']}\n"
                output += f"Metadata: {result.get('metadata', {})}\n\n"

            return output.strip()

        except Exception as e:
            logger.error(f"Błąd podczas memory_search: {e}")
            return f"Błąd: {str(e)}"
