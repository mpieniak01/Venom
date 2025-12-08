"""Moduł: oracle - Agent Wyrocznia (Deep Research & Multi-Hop Reasoning)."""

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.memory.graph_rag_service import GraphRAGService
from venom_core.memory.ingestion_engine import IngestionEngine
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class OracleAgent(BaseAgent):
    """
    Agent Wyrocznia - zaawansowany analityk wiedzy z multi-hop reasoning.
    Wykorzystuje GraphRAG do odpowiadania na trudne pytania wymagające
    połączenia faktów z wielu źródeł.
    """

    SYSTEM_PROMPT = """Jesteś Wyrocznią (Oracle) - zaawansowanym analitykiem wiedzy i badaczem.

TWOJA ROLA:
Odpowiadasz na trudne pytania wymagające głębokiej analizy i połączenia faktów z wielu źródeł.
Wykorzystujesz graf wiedzy (Knowledge Graph) do multi-hop reasoning.

DOSTĘPNE NARZĘDZIA:
- global_search: Wyszukiwanie globalne w grafie (pytania o ogólny obraz, kontekst)
- local_search: Wyszukiwanie lokalne z multi-hop reasoning (pytania o konkretne związki)
- ingest_file: Przetwarzanie i dodawanie plików do grafu wiedzy
- ingest_url: Pobieranie i dodawanie treści ze stron WWW do grafu wiedzy

WORKFLOW "REASONING LOOP":
1. **Analiza pytania**: Zrozum co użytkownik naprawdę chce wiedzieć
2. **Wybór strategii**:
   - Pytanie o ogólny obraz? → użyj global_search
   - Pytanie o konkretne związki między X a Y? → użyj local_search
   - Brak wiedzy w grafie? → najpierw użyj ingest_file/ingest_url
3. **Eksploracja**: Zbierz fakty z grafu wiedzy
4. **Synteza**: Połącz fakty w spójną odpowiedź z cytatami
5. **Weryfikacja**: Upewnij się, że odpowiedź jest poparta faktami

ZASADY:
1. **Zawsze cytuj źródła**: Każdy fakt powinien mieć źródło
2. **Multi-hop reasoning**: Jeśli pytanie wymaga połączenia 2+ faktów, jasno wyjaśnij łańcuch logiczny
3. **Przejrzystość**: Jeśli nie masz pewności, powiedz to wprost
4. **Hierarchiczna analiza**: Najpierw ogólny obraz (global), potem szczegóły (local)

PRZYKŁAD DOBREJ ODPOWIEDZI:
Pytanie: "Jaki jest związek między agentem Ghost a modułem Florence-2?"

Odpowiedź:
"Na podstawie analizy grafu wiedzy znalazłem następujący łańcuch połączeń:

1. Agent Ghost (typ: Agent) → USES → Input Skill (typ: Skill)
   [Źródło: venom_core/agents/ghost_agent.py]

2. Input Skill (typ: Skill) → DEPENDS_ON → Vision Grounding (typ: Module)
   [Źródło: venom_core/execution/skills/input_skill.py]

3. Vision Grounding (typ: Module) → POWERED_BY → Florence-2 (typ: Model)
   [Źródło: venom_core/perception/vision_grounding.py]

**Wniosek**: Agent Ghost używa modelu Florence-2 pośrednio poprzez Input Skill i Vision Grounding.
Florence-2 służy do rozpoznawania elementów GUI na ekranie, co pozwala Ghost na automatyzację
interakcji z interfejsami graficznymi."

PAMIĘTAJ: Jesteś WYROCZNIĄ - dostarczasz głębokiej analizy opartej na faktach z grafu wiedzy."""

    def __init__(self, kernel: Kernel, graph_rag_service: GraphRAGService = None):
        """
        Inicjalizacja OracleAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            graph_rag_service: Serwis GraphRAG (opcjonalny, utworzy nowy jeśli None)
        """
        super().__init__(kernel)

        # GraphRAG Service
        self.graph_rag = graph_rag_service or GraphRAGService()
        self.graph_rag.load_graph()

        # Ingestion Engine
        self.ingestion_engine = IngestionEngine()

        # Zarejestruj funkcje jako plugin
        self._register_oracle_functions()

        logger.info("OracleAgent zainicjalizowany z GraphRAG i IngestionEngine")

    def _register_oracle_functions(self):
        """Rejestruje funkcje Oracle jako plugin dla Semantic Kernel."""
        from semantic_kernel.functions import kernel_function
        from typing import Annotated

        class OraclePlugin:
            """Plugin Oracle z funkcjami do reasoning."""

            def __init__(self, oracle_agent):
                self.oracle = oracle_agent

            @kernel_function(
                name="global_search",
                description="Wyszukiwanie globalne w grafie wiedzy. Używaj dla pytań o ogólny obraz, kontekst, podsumowanie. Analizuje społeczności w grafie.",
            )
            async def global_search(
                self, query: Annotated[str, "Zapytanie użytkownika"]
            ) -> str:
                """Wyszukiwanie globalne."""
                try:
                    llm_service = self.oracle.kernel.get_service()
                    result = await self.oracle.graph_rag.global_search(query, llm_service)
                    return result
                except Exception as e:
                    logger.error(f"Błąd w global_search: {e}")
                    return f"Błąd: {str(e)}"

            @kernel_function(
                name="local_search",
                description="Wyszukiwanie lokalne z multi-hop reasoning. Używaj dla pytań o konkretne związki między encjami, łańcuchy przyczynowo-skutkowe.",
            )
            async def local_search(
                self,
                query: Annotated[str, "Zapytanie użytkownika"],
                max_hops: Annotated[int, "Maksymalna liczba skoków w grafie (domyślnie 2)"] = 2,
            ) -> str:
                """Wyszukiwanie lokalne."""
                try:
                    llm_service = self.oracle.kernel.get_service()
                    result = await self.oracle.graph_rag.local_search(
                        query, max_hops, llm_service
                    )
                    return result
                except Exception as e:
                    logger.error(f"Błąd w local_search: {e}")
                    return f"Błąd: {str(e)}"

            @kernel_function(
                name="ingest_file",
                description="Przetwarza i dodaje plik do grafu wiedzy. Obsługuje: PDF, DOCX, obrazy, audio, video, tekst.",
            )
            async def ingest_file(
                self, file_path: Annotated[str, "Ścieżka do pliku"]
            ) -> str:
                """Przetwarzanie pliku."""
                try:
                    result = await self.oracle.ingestion_engine.ingest_file(file_path)
                    text = result["text"]
                    chunks = result["chunks"]

                    # Dodaj do VectorStore
                    self.oracle.graph_rag.vector_store.upsert(
                        text=text,
                        metadata={
                            **result["metadata"],
                            "entity_id": f"doc_{file_path}",
                        },
                        chunk_text=False,  # Już podzielone
                    )

                    # Ekstrahuj wiedzę (tylko dla tekstów, nie dla obrazów/audio)
                    if result["file_type"] in ["pdf", "docx", "text", "web"]:
                        llm_service = self.oracle.kernel.get_service()
                        extraction_result = await self.oracle.graph_rag.extract_knowledge_from_text(
                            text[:3000],  # Ogranicz dla LLM
                            f"doc_{file_path}",
                            llm_service,
                        )

                        return f"Plik przetworzony: {file_path}\nChunks: {len(chunks)}\nEncje: {extraction_result.get('entities', 0)}\nRelacje: {extraction_result.get('relationships', 0)}"
                    else:
                        return f"Plik przetworzony: {file_path}\nChunks: {len(chunks)}\n(ekstrakcja wiedzy niedostępna dla tego typu pliku)"

                except Exception as e:
                    logger.error(f"Błąd w ingest_file: {e}")
                    return f"Błąd podczas przetwarzania pliku: {str(e)}"

            @kernel_function(
                name="ingest_url",
                description="Pobiera treść ze strony WWW i dodaje do grafu wiedzy.",
            )
            async def ingest_url(
                self, url: Annotated[str, "URL strony do pobrania"]
            ) -> str:
                """Pobieranie URL."""
                try:
                    result = await self.oracle.ingestion_engine.ingest_url(url)
                    text = result["text"]
                    chunks = result["chunks"]

                    # Dodaj do VectorStore
                    self.oracle.graph_rag.vector_store.upsert(
                        text=text,
                        metadata={**result["metadata"], "entity_id": f"url_{url}"},
                        chunk_text=False,
                    )

                    # Ekstrahuj wiedzę
                    llm_service = self.oracle.kernel.get_service()
                    extraction_result = await self.oracle.graph_rag.extract_knowledge_from_text(
                        text[:3000], f"url_{url}", llm_service
                    )

                    return f"URL przetworzony: {url}\nChunks: {len(chunks)}\nEncje: {extraction_result.get('entities', 0)}\nRelacje: {extraction_result.get('relationships', 0)}"

                except Exception as e:
                    logger.error(f"Błąd w ingest_url: {e}")
                    return f"Błąd podczas przetwarzania URL: {str(e)}"

            @kernel_function(
                name="get_graph_stats",
                description="Zwraca statystyki grafu wiedzy (liczba encji, relacji, społeczności).",
            )
            def get_graph_stats(self) -> str:
                """Statystyki grafu."""
                try:
                    stats = self.oracle.graph_rag.get_stats()
                    return f"""Statystyki grafu wiedzy:
- Encje: {stats['total_nodes']}
- Relacje: {stats['total_edges']}
- Społeczności: {stats['communities_count']}
- Największa społeczność: {stats['largest_community_size']} encji
- Typy encji: {stats['entity_types']}
- Typy relacji: {stats['relationship_types']}"""
                except Exception as e:
                    return f"Błąd: {str(e)}"

        plugin = OraclePlugin(self)
        self.kernel.add_plugin(plugin, plugin_name="OraclePlugin")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza trudne pytanie używając Reasoning Loop.

        Args:
            input_text: Pytanie użytkownika

        Returns:
            Odpowiedź z głęboką analizą i cytatami
        """
        logger.info(f"OracleAgent przetwarza zapytanie: {input_text[:100]}...")

        # Przygotuj historię rozmowy
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=input_text)
        )

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()

            # Włącz automatyczne wywoływanie funkcji
            settings = OpenAIChatPromptExecutionSettings(
                function_choice_behavior=FunctionChoiceBehavior.Auto(),
                max_tokens=3000,
            )

            # Wywołaj model z reasoning loop
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings
            )

            result = str(response).strip()

            # Zapisz graf po każdej operacji
            self.graph_rag.save_graph()

            logger.info(f"OracleAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas przetwarzania przez OracleAgent: {e}")
            return f"Wystąpił błąd podczas analizy: {str(e)}. Sprawdź czy graf wiedzy zawiera odpowiednie dane."
