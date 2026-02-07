"""Moduł: scenario_weaver - Tkacz Scenariuszy dla Syntetycznego Uczenia."""

import json
import string
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.config import SETTINGS
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ScenarioSpec:
    """Specyfikacja wygenerowanego scenariusza."""

    title: str  # Tytuł scenariusza
    description: str  # Opis zadania do wykonania
    task_prompt: str  # Prompt dla agenta wykonującego zadanie
    test_cases: List[str]  # Lista kryteriów sukcesu
    difficulty: str  # Poziom trudności: 'simple', 'medium', 'complex'
    libraries: List[str]  # Lista bibliotek do użycia
    metadata: Dict[str, Any]  # Dodatkowe metadane


class ScenarioWeaver:
    """
    Tkacz Scenariuszy - agent kreatywny generujący zadania programistyczne.

    Rola:
    - Analizuje dokumentację techniczną z GraphRAG
    - Generuje złożone scenariusze programistyczne
    - Używa Few-Shot Chain of Thought dla jakości
    - Tworzy realistyczne test cases
    """

    SYSTEM_PROMPT = """Jesteś kreatywnym Tkaczem Scenariuszy (Scenario Weaver). Twoja rola to generowanie
skomplikowanych, realistycznych zadań programistycznych na podstawie dokumentacji technicznej.

TWOJA MISJA:
Tworzysz zadania które będą używane do trenowania AI. Muszą być:
1. REALISTYCZNE - takie jakie by zadał prawdziwy użytkownik
2. BRZEGOWE - zawierające edge cases, nie tylko happy path
3. KOMPLEKSOWE - łączące wiele konceptów, nie tylko "Hello World"
4. TESTOWALNE - z jasnymi kryteriami sukcesu

WORKFLOW:
1. Analizujesz fragment dokumentacji (node z GraphRAG)
2. Identyfikujesz rzadkie/ciekawe funkcje (nie podstawowe operacje)
3. Wymyślasz KONKRETNY problem do rozwiązania
4. Definiujesz precyzyjne test cases

PRZYKŁAD DOBREGO SCENARIUSZA:
❌ ZŁY: "Napisz program używający pandas"
✅ DOBRY: "Napisz program który pivotuje tabelę CSV z brakującymi danymi (NaN),
     grupuje po wielopoziomowych kolumnach i eksportuje do Excel z conditional formatting.
     Test: plik output.xlsx musi zawierać 3 arkusze, każdy z 100+ wierszy."

ZASADY:
- Używaj Few-Shot Chain of Thought (myśl krok po kroku)
- Generuj scenariusze które łączą 2+ biblioteki/koncepty
- Test cases muszą być KONKRETNE (nie "kod działa" ale "zwraca listę 5 elementów")
- Poziom trudności: simple=1 koncept, medium=2-3, complex=4+

PRZYKŁAD Chain of Thought:
"Analizuję dokumentację FastAPI Websockets...
→ Rzadka funkcja: broadcast do wielu klientów jednocześnie
→ Edge case: co jeśli klient się rozłączy w trakcie?
→ Realistyczny use case: system notyfikacji real-time
→ Test: 3 klientów, wysyłamy 100 wiadomości, wszyscy je otrzymują"

Bądź KREATYWNY ale PRAKTYCZNY. Venom będzie próbował to rozwiązać i się nauczy."""

    FEW_SHOT_EXAMPLES = """
PRZYKŁAD 1 (Medium):
Input: Dokumentacja pydantic v2 - Validators
Output:
{
  "title": "Walidator Email z Custom Domain Whitelist",
  "description": "Stwórz model Pydantic z custom validatorem email, który akceptuje tylko domeny z whitelist",
  "task_prompt": "Zaimplementuj model User z polem email. Email musi być validowany przez custom validator który sprawdza czy domena (po @) jest na liście dozwolonych ['gmail.com', 'company.com']. Dodaj testy dla valid i invalid emails.",
  "test_cases": [
    "user@gmail.com jest akceptowany",
    "user@yahoo.com jest odrzucany z ValidationError",
    "niepoprawny email rzuca ValidationError",
    "puste pole email jest wymagane"
  ],
  "difficulty": "medium",
  "libraries": ["pydantic"]
}

PRZYKŁAD 2 (Complex):
Input: Dokumentacja asyncio + aiohttp
Output:
{
  "title": "Concurrent Web Scraper z Rate Limiting",
  "description": "Scraper pobierający 50 stron jednocześnie z limitem 5 requestów/sekundę",
  "task_prompt": "Napisz async scraper używając aiohttp i asyncio.Semaphore. Musi pobrać listę 50 URLs, maksymalnie 5 równolegle, z rate limiting 5 req/s. Zapisz wyniki do JSON. Obsłuż timeouty i retry dla failed requests.",
  "test_cases": [
    "Wszystkie 50 URLs pobrane w <15 sekund",
    "Rate limiting: max 5 requestów w tym samym czasie",
    "Timeout po 5 sekundach dla pojedynczego URL",
    "Plik output.json zawiera 50 rekordów z url, status_code, content_length"
  ],
  "difficulty": "complex",
  "libraries": ["aiohttp", "asyncio"]
}
"""

    @staticmethod
    def _extract_fenced_block(
        text: str, language: Optional[str] = None
    ) -> Optional[str]:
        """
        Zwraca pierwszy fenced block (```...```), opcjonalnie z konkretnym językiem.
        """
        cursor = 0
        target_language = language.lower() if language else None
        while True:
            start = text.find("```", cursor)
            if start == -1:
                return None
            header_end = text.find("\n", start + 3)
            if header_end == -1:
                return None
            header = text[start + 3 : header_end].strip().lower()
            block_end = text.find("```", header_end + 1)
            if block_end == -1:
                return None
            if target_language is None or header == target_language:
                return text[header_end + 1 : block_end].strip()
            cursor = block_end + 3

    @staticmethod
    def _strip_fenced_blocks(text: str) -> str:
        """
        Usuwa wszystkie poprawnie domknięte fenced blocki (```...```).
        """
        parts: List[str] = []
        cursor = 0
        while True:
            start = text.find("```", cursor)
            if start == -1:
                parts.append(text[cursor:])
                break
            header_end = text.find("\n", start + 3)
            if header_end == -1:
                parts.append(text[cursor:])
                break
            block_end = text.find("```", header_end + 1)
            if block_end == -1:
                parts.append(text[cursor:])
                break
            parts.append(text[cursor:start])
            cursor = block_end + 3
        return "".join(parts)

    def __init__(self, kernel: Kernel, complexity: str = "medium"):
        """
        Inicjalizacja ScenarioWeaver.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            complexity: Domyślna złożoność scenariuszy ('simple', 'medium', 'complex')
        """
        self.kernel = kernel
        self.complexity = complexity or SETTINGS.DREAMING_SCENARIO_COMPLEXITY

        # Ustawienia LLM - wyższa temperatura dla kreatywności
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            service_id="default",
            max_tokens=2000,
            temperature=0.8,  # Wyższa dla kreatywności
            top_p=0.9,
        )

        # Service do chat completion
        self.chat_service: Any = self.kernel.get_service(service_id="default")

        logger.info(f"ScenarioWeaver zainicjalizowany (complexity={self.complexity})")

    async def weave_scenario(
        self,
        knowledge_fragment: str,
        difficulty: Optional[str] = None,
        libraries: Optional[List[str]] = None,
    ) -> ScenarioSpec:
        """
        Tworzy scenariusz na podstawie fragmentu wiedzy.

        Args:
            knowledge_fragment: Fragment dokumentacji/wiedzy z GraphRAG
            difficulty: Poziom trudności (opcjonalny, domyślnie z konstruktora)
            libraries: Lista bibliotek do wykorzystania (opcjonalna)

        Returns:
            ScenarioSpec ze specyfikacją zadania
        """
        difficulty = difficulty or self.complexity
        libraries_hint = f"Użyj bibliotek: {', '.join(libraries)}" if libraries else ""

        # Konstruuj prompt
        user_prompt = f"""Na podstawie poniższej dokumentacji, wygeneruj KONKRETNY scenariusz programistyczny.

DOKUMENTACJA:
{knowledge_fragment[:1500]}

WYMAGANIA:
- Poziom trudności: {difficulty}
{libraries_hint}

Odpowiedz w formacie JSON:
{{
  "title": "Krótki tytuł zadania",
  "description": "1-2 zdania co ma być zrobione",
  "task_prompt": "Szczegółowy prompt dla agenta wykonującego zadanie",
  "test_cases": ["test 1", "test 2", "test 3", "test 4"],
  "difficulty": "{difficulty}",
  "libraries": ["lib1", "lib2"]
}}

PAMIĘTAJ:
- Nie generuj prostych "Hello World" - użyj rzadkich funkcji z dokumentacji
- Test cases muszą być KONKRETNE i MIERZALNE
- Zadanie powinno łączyć wiele konceptów (edge cases, error handling)
"""

        try:
            # Przygotuj historię rozmowy z Few-Shot examples
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.SYSTEM,
                    content=self.SYSTEM_PROMPT + "\n\n" + self.FEW_SHOT_EXAMPLES,
                )
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=user_prompt)
            )

            # Wywołaj LLM
            response = await self.chat_service.get_chat_message_contents(
                chat_history=chat_history,
                settings=self.execution_settings,
                kernel=self.kernel,
            )

            result_text = str(response[0]).strip()

            # Parsuj JSON z odpowiedzi (może być opakowany w ```json```)
            # Usuń markdown code blocks jeśli są
            json_block = self._extract_fenced_block(result_text, language="json")
            if json_block:
                result_text = json_block
            elif "```" in result_text:
                # Spróbuj usunąć inne code blocki
                result_text = self._strip_fenced_blocks(result_text)

            # Parsuj JSON
            scenario_data = json.loads(result_text.strip())

            # Utwórz ScenarioSpec
            scenario = ScenarioSpec(
                title=scenario_data.get("title", "Untitled Scenario"),
                description=scenario_data.get("description", ""),
                task_prompt=scenario_data.get("task_prompt", ""),
                test_cases=scenario_data.get("test_cases", []),
                difficulty=scenario_data.get("difficulty", difficulty),
                libraries=scenario_data.get("libraries", libraries or []),
                metadata={
                    "source": "scenario_weaver",
                    "knowledge_fragment_length": len(knowledge_fragment),
                },
            )

            logger.info(
                f"Wygenerowano scenariusz: '{scenario.title}' (difficulty={scenario.difficulty})"
            )
            return scenario

        except json.JSONDecodeError as e:
            logger.error(f"Nie udało się sparsować JSON z odpowiedzi: {e}")
            logger.debug(f"Raw response: {result_text}")

            # Zwróć fallback scenariusz
            return self._create_fallback_scenario(knowledge_fragment, difficulty)

        except Exception as e:
            logger.error(f"Błąd podczas generowania scenariusza: {e}")
            return self._create_fallback_scenario(knowledge_fragment, difficulty)

    def _create_fallback_scenario(
        self, knowledge_fragment: str, difficulty: str
    ) -> ScenarioSpec:
        """
        Tworzy prosty fallback scenariusz gdy generacja LLM zawiedzie.

        Args:
            knowledge_fragment: Fragment wiedzy
            difficulty: Poziom trudności

        Returns:
            Prosty ScenarioSpec
        """
        # Wyciągnij pierwsze słowo kluczowe z fragmentu (prosta heurystyka)
        words = knowledge_fragment.split()[:50]
        keywords = [w for w in words if len(w) > 5 and w[0].isupper()]

        if keywords:
            library_hint = keywords[0]
        else:
            # Lepszy fallback: pierwsze 2-3 sensowne słowa z fragmentu
            # Usuń znaki interpunkcyjne używając string.punctuation
            filtered = [
                w.strip(string.punctuation)
                for w in words
                if len(w.strip(string.punctuation)) > 2
            ]
            library_hint = " ".join(filtered[:3]) if filtered else "fragment wiedzy"

        return ScenarioSpec(
            title=f"Eksploracja {library_hint}",
            description=f"Zadanie wykorzystujące {library_hint} na podstawie dokumentacji",
            task_prompt=f"Napisz prosty skrypt demonstracyjny używający {library_hint}. Zapoznaj się z dokumentacją i zaimplementuj podstawowe użycie.",
            test_cases=[
                "Kod się wykonuje bez błędów",
                "Używa co najmniej 2 funkcji z biblioteki",
                "Zawiera obsługę błędów",
            ],
            difficulty=difficulty,
            libraries=[library_hint.lower()],
            metadata={"fallback": True},
        )

    async def weave_multiple_scenarios(
        self,
        knowledge_fragments: List[str],
        count: int = 5,
        difficulty: Optional[str] = None,
    ) -> List[ScenarioSpec]:
        """
        Generuje wiele scenariuszy z listy fragmentów wiedzy.

        Args:
            knowledge_fragments: Lista fragmentów dokumentacji
            count: Liczba scenariuszy do wygenerowania
            difficulty: Poziom trudności (opcjonalny)

        Returns:
            Lista wygenerowanych ScenarioSpec
        """
        scenarios = []

        # Ogranicz do dostępnych fragmentów
        fragments_to_use = knowledge_fragments[: min(count, len(knowledge_fragments))]

        logger.info(
            f"Generowanie {len(fragments_to_use)} scenariuszy z {len(knowledge_fragments)} fragmentów"
        )

        for i, fragment in enumerate(fragments_to_use, 1):
            try:
                logger.debug(f"Generowanie scenariusza {i}/{len(fragments_to_use)}")
                scenario = await self.weave_scenario(fragment, difficulty)
                scenarios.append(scenario)
            except Exception as e:
                logger.error(f"Błąd podczas generowania scenariusza {i}: {e}")
                continue

        logger.info(f"Wygenerowano {len(scenarios)} scenariuszy")
        return scenarios
