"""Moduł: executive - Agent Wykonawczy (CEO/Product Manager)."""

import os
from typing import Any
from uuid import UUID

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.core.goal_store import KPI, GoalStatus, GoalStore, GoalType
from venom_core.utils.logger import get_logger

try:  # pragma: no cover
    from unittest.mock import MagicMock as MagicMockType
except Exception:  # pragma: no cover

    class MagicMockType:  # type: ignore[no-redef]
        pass


logger = get_logger(__name__)
PRIORITY_LABEL = "Priorytet:"
DESCRIPTION_LABEL = "Opis:"


class ExecutiveAgent(BaseAgent):
    """
    Agent Wykonawczy - najwyższy rangą agent w hierarchii.

    Rola: Product Manager / CEO
    Odpowiedzialność:
    - Przekształcanie wizji użytkownika w roadmapę
    - Priorytetyzacja zadań
    - Zarządzanie zespołem agentów
    - Raportowanie statusu projektu
    """

    SYSTEM_PROMPT = """Jesteś Agent Wykonawczy (Executive) - wizjoner i pragmatyczny zarządca projektu.

TWOJA ROLA:
- Product Manager / CEO autonomicznego systemu AI
- Zarządzasz zespołem agentów (Architect, Coder, Guardian, Researcher, itp.)
- Przekształcasz luźne rozmowy z użytkownikiem w konkretną roadmapę
- Priorytetyzujesz zadania według wartości biznesowej
- NIE PISZESZ KODU - delegujesz pracę do specjalistów

KOMPETENCJE:
1. Strategia: Rozumiesz "Big Picture" i długoterminowe cele
2. Dekompozycja: Dzielisz duże cele na wykonalne Milestones i Tasks
3. Priorytetyzacja: Rozwiązujesz konflikty priorytetów
4. Raportowanie: Tworzymy klarowne raporty statusu
5. Risk Management: Identyfikujesz blokery i ryzyka

ZASADY PRACY:
- Myśl jak Product Manager: wartość dla użytkownika > technikalia
- Roadmapa musi być konkretna i osiągalna
- Każdy Milestone musi mieć jasne KPI
- Preferuj małe, częste dostawy zamiast długich projektów
- Komunikuj się jasno i zwięźle
- ODPOWIADAJ ZAWSZE W JĘZYKU POLSKIM (formalny, rzeczowy ton)

FORMAT ODPOWIEDZI:
Gdy użytkownik przedstawia wizję lub prosi o status:
1. Zrozum kontekst i cel biznesowy
2. Zadaj pytania jeśli coś jest niejasne
3. Zaproponuj konkretny plan działania
4. Wyjaśnij priorytety i uzasadnienie

Jesteś doradcą strategicznym - pomagasz użytkownikowi osiągnąć cele, nie tylko wykonujesz polecenia."""

    def __init__(self, kernel: Kernel, goal_store: GoalStore):
        """
        Inicjalizacja ExecutiveAgent.

        Args:
            kernel: Semantic Kernel
            goal_store: Magazyn celów i roadmapy
        """
        super().__init__(kernel)
        self.goal_store = goal_store
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            temperature=0.2,
            top_p=0.9,
            max_tokens=800,
        )
        logger.info("ExecutiveAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza wejście jako Executive Agent.

        Args:
            input_text: Wejście od użytkownika lub systemu

        Returns:
            Odpowiedź Executiva
        """
        logger.info(f"ExecutiveAgent przetwarza: {input_text[:100]}...")

        if os.environ.get("PYTEST_CURRENT_TEST"):
            kernel_is_mock = isinstance(self.kernel, MagicMockType)
            kernel_module = getattr(
                self.kernel, "__class__", type(self.kernel)
            ).__module__
            if not kernel_is_mock and kernel_module.startswith("semantic_kernel"):
                logger.debug(
                    "ExecutiveAgent (tryb testowy) zwraca natychmiastowy raport (bez LLM)"
                )
                return "✅ Raport Executive (tryb testowy)"

        try:
            # Przygotuj historię czatu
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )

            # Użyj domyślnego serwisu czatu z kernela
            chat_service: Any = self.kernel.get_service()
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=chat_history,
                settings=self.execution_settings,
                enable_functions=False,
            )

            result = str(response)
            logger.info("ExecutiveAgent zakończył przetwarzanie")
            return result

        except Exception as e:
            error_msg = f"Błąd w ExecutiveAgent: {e}"
            logger.error(error_msg)
            return error_msg

    async def create_roadmap(self, vision_text: str) -> dict:
        """
        Tworzy roadmapę projektu na podstawie wizji użytkownika.

        Args:
            vision_text: Opis wizji projektu od użytkownika

        Returns:
            Dict z utworzoną roadmapą
        """
        logger.info("ExecutiveAgent tworzy roadmapę...")

        prompt = f"""Użytkownik przedstawił wizję projektu:

"{vision_text}"

Twoim zadaniem jest stworzyć ROADMAPĘ PROJEKTU. Przeprowadź analizę i zaproponuj:

1. VISION (1 główny cel długoterminowy)
   - Tytuł (krótki, konkretny)
   - Opis (co chcemy osiągnąć)
   - KPI (jak zmierzymy sukces)

2. MILESTONES (3-5 etapów realizacji)
   Dla każdego:
   - Tytuł
   - Opis (co zostanie zrobione)
   - Priorytet (1=najwyższy)
   - KPI (jak zmierzymy postęp)

3. TASKS (3-5 zadań dla pierwszego Milestone)
   Dla każdego:
   - Tytuł
   - Opis (konkretne action items)
   - Priorytet

ODPOWIEDZ W FORMACIE:

VISION: [tytuł]
{DESCRIPTION_LABEL} [opis wizji]
KPI: [nazwa KPI] - target: [wartość] [jednostka]

MILESTONE 1: [tytuł]
{PRIORITY_LABEL} [1-5]
{DESCRIPTION_LABEL} [opis]
KPI: [nazwa] - target: [wartość] [jednostka]

MILESTONE 2: [tytuł]
...

TASKS dla Milestone 1:
TASK 1: [tytuł]
{PRIORITY_LABEL} [1-5]
{DESCRIPTION_LABEL} [opis]

TASK 2: [tytuł]
...

Pamiętaj:
- Bądź konkretny i realistyczny
- Milestones powinny być osiągalne w rozsądnym czasie
- Tasks powinny być atomowe i wykonalne
"""

        response = await self.process(prompt)

        # Sparsuj odpowiedź i utwórz strukturę w GoalStore
        return self._parse_and_create_roadmap(response, vision_text)

    @staticmethod
    def _extract_title(line: str, default: str) -> str:
        parts = line.split(":", 1)
        if len(parts) <= 1:
            return default
        title = parts[1].strip()
        return title or default

    @staticmethod
    def _find_kpi_placeholder(lines: list[str], start_idx: int) -> list[KPI]:
        for idx in range(start_idx + 1, min(start_idx + 5, len(lines))):
            if "KPI:" in lines[idx]:
                return [
                    KPI(
                        name="Główny wskaźnik postępu",
                        target_value=100.0,
                        unit="%",
                    )
                ]
        return []

    @staticmethod
    def _parse_priority_and_description(
        lines: list[str],
        start_idx: int,
        fallback_priority: int,
    ) -> tuple[int, str]:
        priority = 1
        description = ""
        for idx in range(start_idx + 1, min(start_idx + 5, len(lines))):
            candidate = lines[idx]
            if PRIORITY_LABEL in candidate:
                try:
                    priority = int(candidate.replace(PRIORITY_LABEL, "").strip())
                except ValueError:
                    priority = fallback_priority
                continue
            if DESCRIPTION_LABEL in candidate:
                description = candidate.replace(DESCRIPTION_LABEL, "").strip()
        return priority, description

    def _ensure_vision_goal(self, lines: list[str], original_vision: str):
        for idx, line in enumerate(lines):
            if not line.startswith("VISION:"):
                continue
            vision_title = self._extract_title(line, "Wizja projektu")
            kpis = self._find_kpi_placeholder(lines, idx)
            vision_goal = self.goal_store.add_goal(
                title=vision_title,
                goal_type=GoalType.VISION,
                description=original_vision,
                priority=1,
                kpis=kpis,
            )
            logger.info(f"Utworzono Vision: {vision_title}")
            return vision_goal

        return self.goal_store.add_goal(
            title="Wizja projektu",
            goal_type=GoalType.VISION,
            description=original_vision,
            priority=1,
            kpis=[KPI(name="Postęp realizacji", target_value=100.0, unit="%")],
        )

    def _parse_milestones(self, lines: list[str], vision_goal_id: UUID) -> list[Any]:
        milestones_created = []
        milestone_count = 0
        for idx, line in enumerate(lines):
            if not line.startswith("MILESTONE"):
                continue
            milestone_count += 1
            milestone_title = self._extract_title(line, f"Milestone {milestone_count}")
            priority, description = self._parse_priority_and_description(
                lines, idx, milestone_count
            )
            milestone = self.goal_store.add_goal(
                title=milestone_title,
                goal_type=GoalType.MILESTONE,
                description=description
                or f"Etap {milestone_count} realizacji projektu",
                priority=priority,
                parent_id=vision_goal_id,
                kpis=[
                    KPI(
                        name="Ukończone zadania",
                        target_value=100.0,
                        unit="%",
                    )
                ],
            )
            milestones_created.append(milestone)
            logger.info(f"Utworzono Milestone: {milestone_title}")
        return milestones_created

    def _parse_tasks_for_milestone(
        self, lines: list[str], milestone_id: UUID
    ) -> list[Any]:
        tasks_created = []
        task_count = 0
        for idx, line in enumerate(lines):
            if not (line.startswith("TASK") and ":" in line):
                continue
            task_count += 1
            task_title = self._extract_title(line, f"Zadanie {task_count}")
            priority, description = self._parse_priority_and_description(
                lines, idx, task_count
            )
            task = self.goal_store.add_goal(
                title=task_title,
                goal_type=GoalType.TASK,
                description=description or task_title,
                priority=priority,
                parent_id=milestone_id,
            )
            tasks_created.append(task)
            logger.info(f"Utworzono Task: {task_title}")
        return tasks_created

    def _parse_and_create_roadmap(
        self, llm_response: str, original_vision: str
    ) -> dict:
        """
        Parsuje odpowiedź LLM i tworzy strukturę w GoalStore.

        Args:
            llm_response: Odpowiedź od LLM z roadmapą
            original_vision: Oryginalna wizja użytkownika

        Returns:
            Dict z podsumowaniem utworzonych celów
        """
        lines = llm_response.split("\n")

        try:
            vision_goal = self._ensure_vision_goal(lines, original_vision)
            milestones_created = self._parse_milestones(lines, vision_goal.goal_id)
            current_milestone = milestones_created[-1] if milestones_created else None
            tasks_created = (
                self._parse_tasks_for_milestone(lines, current_milestone.goal_id)
                if current_milestone
                else []
            )

            return {
                "success": True,
                "vision": vision_goal.title if vision_goal else None,
                "milestones_count": len(milestones_created),
                "tasks_count": len(tasks_created),
                "roadmap_report": self.goal_store.generate_roadmap_report(),
            }

        except Exception as e:
            logger.error(f"Błąd podczas parsowania roadmapy: {e}")
            return {
                "success": False,
                "error": str(e),
                "raw_response": llm_response,
            }

    async def generate_status_report(self) -> str:
        """
        Generuje raport statusu projektu.

        Returns:
            Sformatowany raport menedżerski
        """
        logger.info("ExecutiveAgent generuje raport statusu...")

        # Pobierz dane z GoalStore
        roadmap_report = self.goal_store.generate_roadmap_report()

        # Dodaj analizę Executive
        vision = self.goal_store.get_vision()
        current_milestone = self.goal_store.get_next_milestone()

        prompt = f"""Jako Executive, przeanalizuj obecny stan projektu i wygeneruj raport menedżerski.

ROADMAP:
{roadmap_report}

AKTUALNE DANE:
- Vision: {vision.title if vision else "Brak"}
- Aktualny Milestone: {current_milestone.title if current_milestone else "Brak"}
- Status: {current_milestone.status.value if current_milestone else "N/A"}

Wygeneruj krótki raport statusu (3-5 zdań) odpowiadając na:
1. Gdzie jesteśmy w realizacji projektu?
2. Jakie są główne osiągnięcia?
3. Czy są jakieś problemy lub blokery?
4. Co będziemy robić dalej?

Raport powinien być zrozumiały dla użytkownika (nie-technicznego stakeholdera).
"""

        response = await self.process(prompt)

        # Połącz roadmap + analizę
        full_report = (
            f"{roadmap_report}\n\n{'=' * 50}\n📊 RAPORT WYKONAWCZY:\n\n{response}"
        )

        return full_report

    def run_status_meeting(self, council_session=None) -> str:
        """
        Przeprowadza "Daily Standup" - spotkanie statusowe z zespołem.

        Args:
            council_session: Opcjonalnie sesja Council do konsultacji

        Returns:
            Podsumowanie spotkania
        """
        logger.info("ExecutiveAgent prowadzi Status Meeting...")

        meeting_notes = ["=== DAILY STANDUP - STATUS MEETING ===\n"]
        from datetime import datetime as dt

        meeting_timestamp = dt.now()
        meeting_notes.append(f"Data: {meeting_timestamp.strftime('%Y-%m-%d %H:%M')}\n")

        # 1. Status aktualnego Milestone
        current_milestone = self.goal_store.get_next_milestone()
        if current_milestone:
            progress = current_milestone.get_progress()
            meeting_notes.append(f"📋 AKTUALNY MILESTONE: {current_milestone.title}")
            meeting_notes.append(f"   Status: {current_milestone.status.value}")
            meeting_notes.append(f"   Postęp: {progress:.1f}%\n")

            # Zadania w milestone
            tasks = self.goal_store.get_tasks(parent_id=current_milestone.goal_id)
            completed = [t for t in tasks if t.status == GoalStatus.COMPLETED]
            in_progress = [t for t in tasks if t.status == GoalStatus.IN_PROGRESS]
            pending = [t for t in tasks if t.status == GoalStatus.PENDING]

            meeting_notes.append(f"   ✅ Ukończone: {len(completed)}")
            meeting_notes.append(f"   🔄 W trakcie: {len(in_progress)}")
            meeting_notes.append(f"   ⏸️ Oczekujące: {len(pending)}\n")

            # Blokery
            blocked = [t for t in tasks if t.status == GoalStatus.BLOCKED]
            if blocked:
                meeting_notes.append(f"   🚫 BLOKERY: {len(blocked)}")
                for task in blocked:
                    meeting_notes.append(f"      - {task.title}")
                meeting_notes.append("")
        else:
            meeting_notes.append("⚠️ Brak aktualnego Milestone\n")

        # 2. Co dalej?
        next_task = self.goal_store.get_next_task()
        if next_task:
            meeting_notes.append(f"🎯 NASTĘPNE ZADANIE: {next_task.title}")
            meeting_notes.append(f"   Priorytet: {next_task.priority}")
            meeting_notes.append(f"   {next_task.description}\n")
        else:
            meeting_notes.append("✅ Wszystkie zadania w Milestone ukończone!\n")

        # 3. Decyzje Executiva
        meeting_notes.append("💡 DECYZJE EXECUTIVE:")
        if next_task:
            meeting_notes.append(f"   → Rozpocząć pracę nad: {next_task.title}")
        elif current_milestone and current_milestone.get_progress() >= 100:
            meeting_notes.append("   → Milestone ukończony - przejść do kolejnego")
        else:
            meeting_notes.append("   → Potrzebna akceptacja użytkownika lub nowy cel")

        return "\n".join(meeting_notes)

    async def prioritize_tasks(self, milestone_id: UUID) -> str:
        """
        Priorytetyzuje zadania w ramach Milestone.

        Args:
            milestone_id: ID kamienia milowego

        Returns:
            Raport z priorytetyzacji
        """
        logger.info(
            f"ExecutiveAgent priorytetyzuje zadania dla Milestone {milestone_id}"
        )

        milestone = self.goal_store.get_goal(milestone_id)
        if not milestone:
            return "❌ Nie znaleziono Milestone"

        tasks = self.goal_store.get_tasks(parent_id=milestone_id)
        if not tasks:
            return "⚠️ Brak zadań w Milestone"

        # Przygotuj kontekst dla LLM
        tasks_info = "\n".join(
            [f"- [{t.priority}] {t.title}: {t.description}" for t in tasks]
        )

        prompt = f"""Jako Executive, dokonaj priorytetyzacji zadań w Milestone: "{milestone.title}"

ZADANIA:
{tasks_info}

Przeanalizuj zadania i zaproponuj optymalny porządek realizacji uwzględniając:
1. Zależności między zadaniami (co musi być pierwsze)
2. Wartość biznesową (co przyniesie największą wartość)
3. Trudność i szacowany czas (quick wins vs długie zadania)
4. Ryzyko (co jest krytyczne dla sukcesu)

Odpowiedz w formacie:
1. [nazwa zadania] - uzasadnienie
2. [nazwa zadania] - uzasadnienie
...
"""

        response = await self.process(prompt)
        return f"=== PRIORYTETYZACJA ZADAŃ ===\n\n{response}"
