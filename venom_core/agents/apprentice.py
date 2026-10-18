"""
Moduł: apprentice - Agent Czeladnik (Apprentice Agent).

Agent odpowiedzialny za uczenie się workflow poprzez obserwację
demonstracji użytkownika i generowanie skryptów automatyzacji.
"""

import re
from pathlib import Path
from typing import Any, List, Optional

from venom_core.agents.base import BaseAgent
from venom_core.config import SETTINGS
from venom_core.execution.agent_contracts import ConversationHistory as ChatHistory
from venom_core.execution.agent_contracts import (
    ConversationMessage as ChatMessageContent,
)
from venom_core.execution.agent_contracts import MessageRole as AuthorRole
from venom_core.execution.maf_runtime import AgentRuntime as Kernel
from venom_core.execution.model_router import HybridModelRouter, TaskType
from venom_core.learning.demonstration_analyzer import (
    ActionIntent,
    DemonstrationAnalyzer,
)
from venom_core.perception.recorder import DemonstrationRecorder
from venom_core.utils.code_generation_utils import escape_string_for_code
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ApprenticeAgent(BaseAgent):
    """
    Agent Czeladnik - uczy się workflow poprzez obserwację.

    Rola: Uczeń, który zamienia demonstracje na kod
    Odpowiedzialność:
    - Nagrywanie demonstracji użytkownika
    - Analiza nagranych akcji
    - Generowanie skryptów Python dla GhostAgent
    - Parametryzacja workflow (rozpoznawanie zmiennych)
    - Zapis umiejętności do custom_skills
    """

    SYSTEM_PROMPT = """Jesteś Apprentice Agent - uczeń, który uczy się poprzez obserwację.

TWOJA ROLA:
- Obserwujesz działania użytkownika i uczysz się nowych umiejętności
- Przekształcasz demonstracje na kod Python wykorzystujący GhostAgent
- Rozpoznajesz wzorce i parametryzujesz workflow
- Generujesz odporny kod, który działa niezależnie od pozycji okien

MOŻLIWOŚCI:
1. Nagrywanie demonstracji (REC/STOP)
2. Analiza nagranych akcji
3. Generowanie skryptów Python
4. Parametryzacja workflow
5. Zapis umiejętności

PRZYKŁADOWY WORKFLOW:
Użytkownik: "Patrz jak wysyłam raport"
Ty: [Rozpoczynasz nagrywanie]
Użytkownik: [Wykonuje akcje: otwiera Slack, wybiera kanał, załącza plik, wysyła]
Użytkownik: "Zrobione"
Ty: [Analizujesz demonstrację]
Ty: "Zrozumiałem. Kliknąłeś kanał #general, potem ikonę spinacza, wybrałeś plik.
     Zapisałem to jako umiejętność 'wyslij_raport_slack'."

GENERALIZACJA:
- Jeśli użytkownik wpisał wartość (np. "Jan Kowalski"), pytasz czy ma być parametrem
- Używasz opisów elementów UI, nie sztywnych współrzędnych
- Generujesz kod z fallbackami (jeśli element nie znaleziony, użyj koordynatów)

Pamiętaj: Generujesz kod PYTHON, nie pseudokod. Kod musi być gotowy do wykonania."""

    def __init__(
        self,
        kernel: Kernel,
        workspace_root: Optional[str] = None,
    ):
        """
        Inicjalizacja ApprenticeAgent.

        Args:
            kernel: Semantic Kernel
            workspace_root: Katalog główny workspace
        """
        super().__init__(kernel, role="Apprentice")

        self.workspace_root = Path(workspace_root or SETTINGS.WORKSPACE_ROOT)
        self.custom_skills_dir = self.workspace_root / "custom_skills"
        self.custom_skills_dir.mkdir(parents=True, exist_ok=True)

        self.recorder = DemonstrationRecorder(workspace_root=str(self.workspace_root))
        self.analyzer = DemonstrationAnalyzer()

        self.current_session_id: Optional[str] = None

        # Inicjalizuj hybrydowy router modeli
        self.hybrid_router = HybridModelRouter()

        logger.info(
            f"ApprenticeAgent zainicjalizowany (skills: {self.custom_skills_dir})"
        )

    async def process(self, request: str) -> str:
        """
        Przetwarza żądanie użytkownika.

        Args:
            request: Żądanie (np. "Rozpocznij nagrywanie", "Zakończ nagrywanie")

        Returns:
            Odpowiedź
        """
        request_lower = request.lower()

        # Rozpocznij nagrywanie
        if any(kw in request_lower for kw in ["rozpocznij", "start", "rec", "nagraj"]):
            return self._start_recording(request)

        # Zatrzymaj nagrywanie
        elif any(kw in request_lower for kw in ["zatrzymaj", "stop", "zakończ"]):
            return self._stop_recording()

        # Analiza sesji
        elif "analizuj" in request_lower:
            return await self._analyze_demonstration(request)

        # Generuj skill
        elif "generuj" in request_lower or "stwórz skill" in request_lower:
            return await self._generate_skill(request)

        # Inne - deleguj do LLM
        else:
            return await self._llm_response_async(request)

    def _start_recording(self, request: str) -> str:
        """
        Rozpoczyna nagrywanie demonstracji.

        Args:
            request: Żądanie użytkownika

        Returns:
            Odpowiedź
        """
        if self.recorder.is_recording:
            return "❌ Nagrywanie już trwa. Użyj 'stop' aby zakończyć."

        # Wyodrębnij nazwę sesji jeśli podana
        session_name = self._extract_session_name(request)

        self.current_session_id = self.recorder.start_recording(
            session_name=session_name,
            metadata={"request": request},
        )

        return (
            f"🔴 **Rozpoczęto nagrywanie demonstracji**\n\n"
            f"Sesja: `{self.current_session_id}`\n\n"
            f"Wykonaj zadanie, które chcesz nauczyć, a następnie powiedz 'stop'."
        )

    def _stop_recording(self) -> str:
        """
        Zatrzymuje nagrywanie demonstracji.

        Returns:
            Odpowiedź
        """
        if not self.recorder.is_recording:
            return "❌ Nagrywanie nie jest aktywne."

        session_path = self.recorder.stop_recording()

        if not session_path:
            return "❌ Błąd podczas zapisywania sesji."

        return (
            f"⬛ **Zakończono nagrywanie**\n\n"
            f"Sesja zapisana: `{session_path}`\n\n"
            f"Użyj 'analizuj sesję {self.current_session_id}' aby przeanalizować demonstrację."
        )

    async def _analyze_demonstration(self, request: str) -> str:
        """
        Analizuje nagraną demonstrację.

        Args:
            request: Żądanie użytkownika (z ID sesji)

        Returns:
            Opis analizy
        """
        # Wyodrębnij ID sesji z żądania
        session_id = self._extract_session_id(request) or self.current_session_id

        if not session_id:
            return "❌ Nie podano ID sesji. Użyj: 'analizuj sesję <session_id>'"

        # Załaduj sesję
        session = self.recorder.load_session(session_id)
        if not session:
            return f"❌ Nie znaleziono sesji: {session_id}"

        # Analizuj
        logger.info(f"Analizuję sesję: {session_id}")
        actions = await self.analyzer.analyze_session(session)

        # Generuj opis
        summary = self.analyzer.generate_workflow_summary(actions)

        return (
            f"✅ **Analiza zakończona**\n\n"
            f"Sesja: `{session_id}`\n"
            f"Liczba akcji: {len(actions)}\n\n"
            f"{summary}\n\n"
            f"Użyj 'generuj skill <nazwa>' aby utworzyć skrypt automatyzacji."
        )

    async def _generate_skill(self, request: str) -> str:
        """
        Generuje skill Python z analizy.

        Args:
            request: Żądanie użytkownika (z nazwą skill)

        Returns:
            Odpowiedź
        """
        # Wyodrębnij nazwę skill
        skill_name = self._extract_skill_name(request)
        if not skill_name:
            return "❌ Nie podano nazwy skill. Użyj: 'generuj skill <nazwa>'"

        # Wyodrębnij ID sesji
        session_id = self._extract_session_id(request) or self.current_session_id
        if not session_id:
            return "❌ Nie podano ID sesji."

        # Załaduj sesję
        session = self.recorder.load_session(session_id)
        if not session:
            return f"❌ Nie znaleziono sesji: {session_id}"

        # Analizuj
        actions = await self.analyzer.analyze_session(session)

        # Generuj kod Python
        skill_code = self._generate_skill_code(skill_name, actions)

        # Zapisz do pliku
        skill_file = self.custom_skills_dir / f"{skill_name}.py"
        skill_file.write_text(skill_code, encoding="utf-8")

        return (
            f"✅ **Skill wygenerowany**\n\n"
            f"Nazwa: `{skill_name}`\n"
            f"Plik: `{skill_file}`\n"
            f"Liczba kroków: {len(actions)}\n\n"
            f"Skill gotowy do użycia przez GhostAgent."
        )

    def _generate_skill_code(self, skill_name: str, actions: List[ActionIntent]) -> str:
        """
        Generuje kod Python dla skill.

        Args:
            skill_name: Nazwa skill
            actions: Lista akcji

        Returns:
            Kod Python
        """
        # Sanityzuj nazwę funkcji
        safe_function_name = self._sanitize_identifier(skill_name)

        # Bezpiecznie eskejpuj wartości dla generowanego kodu
        skill_name_repr = escape_string_for_code(skill_name)

        # Nagłówek
        code = f'''"""
Custom skill: {skill_name}
Wygenerowany automatycznie przez ApprenticeAgent.
"""

from venom_core.agents.ghost_agent import GhostAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


async def {safe_function_name}(ghost_agent: GhostAgent, **kwargs):
    """
    Wykonuje workflow: {skill_name}

    Args:
        ghost_agent: Instancja GhostAgent
        **kwargs: Parametry workflow
    """
    logger.info("Rozpoczynam workflow: %s", {skill_name_repr})

'''

        # Generuj kod dla każdej akcji
        for i, action in enumerate(actions, 1):
            desc_repr = escape_string_for_code(action.description)
            code += f"    # Krok {i}: {desc_repr}\n"

            if action.action_type == "click":
                element_desc = action.params.get("element_description", "unknown")
                element_desc_repr = escape_string_for_code(element_desc)
                fallback_x = action.params.get("fallback_coords", {}).get("x", 0)
                fallback_y = action.params.get("fallback_coords", {}).get("y", 0)

                code += "    await ghost_agent.vision_click(\n"
                code += f"        description={element_desc_repr},\n"
                code += f"        fallback_coords=({fallback_x}, {fallback_y})\n"
                code += "    )\n\n"

            elif action.action_type == "type":
                text = action.params.get("text", "")
                text_repr = escape_string_for_code(text)
                is_sensitive = action.params.get("is_sensitive", False)

                if is_sensitive:
                    # Użyj parametru
                    code += '    text = kwargs.get("password", "")\n'
                    code += (
                        "    await ghost_agent.input_skill.keyboard_type(text=text)\n\n"
                    )
                else:
                    # Hardcoded text lub parametr
                    # Generuj bezpieczną nazwę parametru (f-string z int jest zawsze bezpieczny)
                    param_name = f"text_{i}"
                    # Dodatkowe zabezpieczenie - sanityzuj na wypadek przyszłych zmian
                    param_name_safe = self._sanitize_identifier(param_name)
                    code += f'    text = kwargs.get("{param_name_safe}", {text_repr})\n'
                    code += (
                        "    await ghost_agent.input_skill.keyboard_type(text=text)\n\n"
                    )

            elif action.action_type == "hotkey":
                keys = action.params.get("keys", [])
                code += f"    await ghost_agent.input_skill.keyboard_hotkey({keys})\n\n"

            # Dodaj opóźnienie między krokami
            code += "    await ghost_agent._wait(1.0)\n\n"

        # Stopka
        code += f'    logger.info("Workflow zakończony: %s", {skill_name_repr})\n'
        # Użyj repr pojedynczo dla bezpieczeństwa, bez podwójnego eskejpowania
        return_msg = f"✅ Workflow {skill_name} wykonany pomyślnie"
        code += f"    return {repr(return_msg)}\n"

        return code

    def _extract_session_name(self, text: str) -> Optional[str]:
        """Wyodrębnia nazwę sesji z tekstu."""
        # Prosta heurystyka
        words = text.split()
        for i, word in enumerate(words):
            if word.lower() in ["nazwany", "jako", "name"] and i + 1 < len(words):
                return words[i + 1].strip("'\"")
        return None

    def _extract_session_id(self, text: str) -> Optional[str]:
        """Wyodrębnia ID sesji z tekstu."""
        pattern = re.compile(
            r"(?:sesj[aeę]|session)\s+(?:o\s+nazwie\s+)?['\"]?([a-z0-9_-]+)['\"]?",
            re.IGNORECASE,
        )
        match = pattern.search(text)
        if match:
            return match.group(1)

        words = text.split()
        for word in words:
            if word.startswith(("demo_", "session_", "sesja_")):
                return word.strip("'\"")
        return None

    def _extract_skill_name(self, text: str) -> Optional[str]:
        """Wyodrębnia nazwę skill z tekstu."""
        pattern = re.compile(r"skill\s+['\"]?([a-z0-9 _-]+)['\"]?", re.IGNORECASE)
        match = pattern.search(text)
        if not match:
            return None
        raw_name = match.group(1).strip()
        normalized = raw_name.lower().replace("-", " ").replace(" ", "_")
        normalized = self._sanitize_identifier(normalized)
        return normalized

    def _sanitize_identifier(self, identifier: str) -> str:
        """
        Sanitizuje identyfikator aby był bezpiecznym identyfikatorem Python.

        Args:
            identifier: Identyfikator do sanityzacji

        Returns:
            Bezpieczny identyfikator (tylko alfanumeryczne znaki i _)
        """
        # Specjalne zabezpieczenie przed ../ lub ..\ w ścieżkach
        identifier = identifier.replace("../", "____").replace("..\\", "____")

        # Usuń niedozwolone znaki, zostaw tylko alfanumeryczne i _
        sanitized = re.sub(r"\W", "_", identifier)

        # Upewnij się że zaczyna się od litery lub _
        if sanitized and sanitized[0].isdigit():
            sanitized = "_" + sanitized

        # Jeśli pusty, użyj domyślnej nazwy
        if not sanitized:
            sanitized = "skill"

        return sanitized

    async def _llm_response_async(self, request: str) -> str:
        """
        Asynchroniczne wywołanie LLM przez hybrydowy router.

        Args:
            request: Żądanie użytkownika

        Returns:
            Odpowiedź LLM
        """
        try:
            # Dodaj kontekst o dostępnych komendach
            context = """
Dostępne komendy:
- "Rozpocznij nagrywanie" / "REC" - rozpoczyna nagrywanie demonstracji
- "Zatrzymaj nagrywanie" / "STOP" - kończy nagrywanie
- "Analizuj sesję <session_id>" - analizuje nagraną demonstrację
- "Generuj skill <nazwa>" - tworzy skrypt automatyzacji

Obecnie:
"""
            if self.recorder.is_recording:
                context += (
                    f"- Nagrywanie w trakcie (sesja: {self.current_session_id})\n"
                )
            else:
                context += "- Nagrywanie nieaktywne\n"

            sessions = self.recorder.list_sessions()
            context += f"- Dostępne sesje: {', '.join(sessions)}\n"

            # Przygotuj pełny prompt
            full_prompt = f"{context}\n\nPytanie użytkownika: {request}"

            # Pobierz informacje o routingu (określamy typ zadania jako CHAT)
            routing_info = self.hybrid_router.get_routing_info_for_task(
                task_type=TaskType.CHAT, prompt=full_prompt
            )

            # Loguj użyty model
            logger.info(
                f"[ApprenticeAgent] Routing do modelu: {routing_info['provider']} "
                f"({routing_info['model_name']})"
            )

            # Faktyczne wywołanie LLM przez kernel
            chat_service: Any = self.kernel.get_service()
            chat_history = ChatHistory()

            # Dodaj system prompt
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )

            # Dodaj zapytanie użytkownika
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=full_prompt)
            )

            # Ustawienia wykonania
            settings = self._create_execution_settings(
                generation_params={"temperature": 0.7, "max_tokens": 1000}
            )

            # Wywołanie LLM z fallbackami
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=chat_history,
                settings=settings,
                enable_functions=False,
            )

            return str(response)

        except Exception as e:
            logger.warning(f"Błąd podczas wywołania LLM, używam fallback: {e}")
            # Kontrolowany fallback bez podnoszenia wyjątku
            return (
                "Jestem ApprenticeAgent. Mogę pomóc Ci nauczyć nowe umiejętności poprzez demonstrację.\n\n"
                "Dostępne komendy: REC (rozpocznij nagrywanie), STOP (zakończ), "
                "'analizuj sesję', 'generuj skill'.\n\n"
                "⚠️ LLM czasowo niedostępny, używam trybu podstawowego."
            )
