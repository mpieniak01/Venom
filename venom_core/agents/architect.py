"""Moduł: architect - agent architekta, planowanie złożonych projektów."""

from typing import TYPE_CHECKING

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.core.models import ExecutionPlan, ExecutionStep
from venom_core.utils.logger import get_logger

if TYPE_CHECKING:
    from venom_core.core.dispatcher import TaskDispatcher

logger = get_logger(__name__)


class ArchitectAgent(BaseAgent):
    """Agent architekta - kierownik projektu, planuje i zarządza złożonymi zadaniami."""

    PLANNING_PROMPT = """Jesteś głównym architektem projektu (Strategic Architect). Twoim zadaniem jest rozłożenie złożonego celu użytkownika na konkretne kroki wykonawcze.

DOSTĘPNI AGENCI (WYKONAWCY):
1. RESEARCHER - Zbiera wiedzę z Internetu, czyta dokumentację, znajduje przykłady
   Używaj gdy: trzeba znaleźć informacje o bibliotekach, API, najlepsze praktyki, aktualne wersje
   
2. CODER - Pisze kod, tworzy pliki, implementuje funkcjonalność
   Używaj gdy: trzeba napisać konkretny kod, stworzyć pliki, zaimplementować logikę
   
3. LIBRARIAN - Zarządza plikami, czyta istniejący kod, organizuje strukturę
   Używaj gdy: trzeba sprawdzić co już istnieje, odczytać konfigurację, przejrzeć strukturę

ZASADY PLANOWANIA:
1. Rozbij cel na MAŁE, KONKRETNE kroki (3-7 kroków optymalnie)
2. Każdy krok powinien mieć JEDNEGO wykonawcę
3. Kroki powinny być w LOGICZNEJ KOLEJNOŚCI
4. Jeśli zadanie wymaga wiedzy o technologii/bibliotece - ZACZNIJ od RESEARCHER
5. Każda instrukcja powinna być JASNA i KONKRETNA

FORMAT ODPOWIEDZI (TYLKO JSON, NIC WIĘCEJ):
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "RESEARCHER",
      "instruction": "Znajdź aktualną dokumentację PyGame dot. obsługi kolizji i renderowania",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Stwórz plik game.py z podstawową strukturą gry Snake bazując na wynikach z kroku 1",
      "depends_on": 1
    }
  ]
}

PRZYKŁADY DOBRYCH PLANÓW:

Zadanie: "Stwórz prostą stronę HTML z zegarem cyfrowym i stylem CSS"
Plan:
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "CODER",
      "instruction": "Stwórz plik index.html z podstawową strukturą HTML5 i elementem do wyświetlania zegara",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Stwórz plik style.css z nowoczesnym stylem dla zegara cyfrowego (duża czcionka, centrowanie)",
      "depends_on": 1
    },
    {
      "step_number": 3,
      "agent_type": "CODER",
      "instruction": "Stwórz plik script.js z logiką aktualizacji zegara co sekundę",
      "depends_on": 2
    }
  ]
}

Zadanie: "Napisz grę Snake używając PyGame"
Plan:
{
  "steps": [
    {
      "step_number": 1,
      "agent_type": "RESEARCHER",
      "instruction": "Znajdź aktualną dokumentację PyGame - główne moduły, obsługa inputu, kolizje, rendering",
      "depends_on": null
    },
    {
      "step_number": 2,
      "agent_type": "CODER",
      "instruction": "Stwórz plik snake.py z podstawową strukturą gry: okno, pętla gry, bazując na dokumentacji z kroku 1",
      "depends_on": 1
    },
    {
      "step_number": 3,
      "agent_type": "CODER",
      "instruction": "Dodaj do snake.py logikę węża: ruch, wzrost, kolizje ze ścianami i sobą, używając najlepszych praktyk z kroku 1",
      "depends_on": 2
    },
    {
      "step_number": 4,
      "agent_type": "CODER",
      "instruction": "Dodaj do snake.py system punktacji i jedzenie, finalizuj grę",
      "depends_on": 3
    }
  ]
}

WAŻNE: 
- Odpowiedz TYLKO kodem JSON, bez ```json ani innych znaczników
- NIE dodawaj komentarzy ani wyjaśnień poza JSONem
- Upewnij się że JSON jest poprawny syntaktycznie"""

    def __init__(self, kernel: Kernel, task_dispatcher: "TaskDispatcher" = None):
        """
        Inicjalizacja ArchitectAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            task_dispatcher: Dispatcher do wykonywania kroków planu (będzie ustawiony później)
        """
        super().__init__(kernel)
        self.task_dispatcher = task_dispatcher
        logger.info("ArchitectAgent zainicjalizowany")

    def set_dispatcher(self, dispatcher: "TaskDispatcher"):
        """
        Ustawia dispatcher dla wykonywania planu.

        Args:
            dispatcher: TaskDispatcher do wykonywania kroków
        """
        self.task_dispatcher = dispatcher

    async def create_plan(self, user_goal: str) -> ExecutionPlan:
        """
        Tworzy plan wykonania dla złożonego zadania.

        Args:
            user_goal: Cel użytkownika

        Returns:
            Plan wykonania ze zdefiniowanymi krokami
        """
        logger.info(f"ArchitectAgent tworzy plan dla: {user_goal[:100]}...")

        # Przygotuj historię rozmowy
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.PLANNING_PROMPT)
        )
        chat_history.add_message(
            ChatMessageContent(
                role=AuthorRole.USER,
                content=f"Stwórz plan wykonania dla następującego celu:\n\n{user_goal}",
            )
        )

        try:
            # Pobierz serwis chat completion
            chat_service = self.kernel.get_service()

            # Ustawienia dla LLM
            settings = OpenAIChatPromptExecutionSettings(
                max_tokens=1500, temperature=0.3  # Niższa temperatura dla bardziej deterministycznych planów
            )

            # Wywołaj model
            response = await chat_service.get_chat_message_content(
                chat_history=chat_history, settings=settings
            )

            plan_json = str(response).strip()
            logger.info(f"ArchitectAgent otrzymał plan: {plan_json[:200]}...")

            # Parsuj JSON
            import json

            # Usuń potencjalne znaczniki markdown
            if plan_json.startswith("```"):
                lines = plan_json.split("\n")
                plan_json = "\n".join(
                    [line for line in lines if not line.strip().startswith("```")]
                )

            plan_data = json.loads(plan_json)

            # Stwórz ExecutionPlan
            steps = [
                ExecutionStep(
                    step_number=step["step_number"],
                    agent_type=step["agent_type"],
                    instruction=step["instruction"],
                    depends_on=step.get("depends_on"),
                )
                for step in plan_data["steps"]
            ]

            plan = ExecutionPlan(goal=user_goal, steps=steps, current_step=0)

            logger.info(f"ArchitectAgent stworzył plan z {len(steps)} krokami")
            return plan

        except json.JSONDecodeError as e:
            logger.error(f"Błąd parsowania JSON planu: {e}")
            logger.error(f"Otrzymany tekst: {plan_json}")
            # Fallback - prosty plan z tylko Coderem
            return ExecutionPlan(
                goal=user_goal,
                steps=[
                    ExecutionStep(
                        step_number=1,
                        agent_type="CODER",
                        instruction=user_goal,
                        depends_on=None,
                    )
                ],
                current_step=0,
            )
        except Exception as e:
            logger.error(f"Błąd podczas tworzenia planu: {e}")
            # Fallback
            return ExecutionPlan(
                goal=user_goal,
                steps=[
                    ExecutionStep(
                        step_number=1,
                        agent_type="CODER",
                        instruction=user_goal,
                        depends_on=None,
                    )
                ],
                current_step=0,
            )

    async def execute_plan(self, plan: ExecutionPlan) -> str:
        """
        Wykonuje plan krok po kroku.

        Args:
            plan: Plan wykonania

        Returns:
            Skonsolidowany wynik wykonania wszystkich kroków
        """
        if not self.task_dispatcher:
            logger.error("TaskDispatcher nie został ustawiony dla ArchitectAgent")
            return "Błąd: Brak dispatchera do wykonania planu"

        logger.info(f"ArchitectAgent wykonuje plan z {len(plan.steps)} krokami")

        context_history = {}
        final_result = f"=== WYKONANIE PLANU ===\nCel: {plan.goal}\n\n"

        for step in plan.steps:
            logger.info(
                f"Wykonywanie kroku {step.step_number}: {step.agent_type} - {step.instruction[:50]}..."
            )

            # Przygotuj kontekst dla kroku (wyniki poprzednich kroków)
            step_context = step.instruction

            if step.depends_on and step.depends_on in context_history:
                dependent_result = context_history[step.depends_on]
                step_context = f"""KONTEKST Z POPRZEDNIEGO KROKU ({step.depends_on}):
{dependent_result[:1000]}...

AKTUALNE ZADANIE:
{step.instruction}"""

            # Wykonaj krok przez dispatcher
            try:
                # Mapowanie typu agenta na intencję
                agent_type_to_intent = {
                    "RESEARCHER": "RESEARCH",
                    "CODER": "CODE_GENERATION",
                    "LIBRARIAN": "KNOWLEDGE_SEARCH",
                }

                intent = agent_type_to_intent.get(
                    step.agent_type, "CODE_GENERATION"
                )
                result = await self.task_dispatcher.dispatch(intent, step_context)

                # Zapisz wynik
                step.result = result
                context_history[step.step_number] = result

                final_result += f"\n--- Krok {step.step_number}: {step.agent_type} ---\n"
                final_result += f"Zadanie: {step.instruction}\n"
                final_result += f"Wynik: {result[:500]}...\n\n"

                logger.info(f"Krok {step.step_number} zakończony sukcesem")

            except Exception as e:
                logger.error(f"Błąd podczas wykonywania kroku {step.step_number}: {e}")
                final_result += f"\n--- Krok {step.step_number}: BŁĄD ---\n"
                final_result += f"Zadanie: {step.instruction}\n"
                final_result += f"Błąd: {str(e)}\n\n"

        final_result += "\n=== PLAN ZAKOŃCZONY ==="
        logger.info("ArchitectAgent zakończył wykonywanie planu")
        return final_result

    async def process(self, input_text: str) -> str:
        """
        Przetwarza złożone zadanie - tworzy plan i go wykonuje.

        Args:
            input_text: Opis złożonego zadania

        Returns:
            Wynik wykonania planu
        """
        logger.info(f"ArchitectAgent przetwarza zadanie: {input_text[:100]}...")

        # Stwórz plan
        plan = await self.create_plan(input_text)

        # Wykonaj plan
        result = await self.execute_plan(plan)

        return result
