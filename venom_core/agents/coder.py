"""Moduł: coder - agent generujący kod."""

from typing import Any, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.function_choice_behavior import (
    FunctionChoiceBehavior,
)
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.compose_skill import ComposeSkill
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.execution.skills.shell_skill import ShellSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class CoderAgent(BaseAgent):
    """Agent specjalizujący się w generowaniu kodu."""

    SYSTEM_PROMPT = """Jesteś ekspertem programowania (Senior Developer). Twoim zadaniem jest generować czysty, udokumentowany kod w odpowiedzi na żądanie użytkownika.

MASZ DOSTĘP DO SYSTEMU PLIKÓW:
- write_file: Zapisz kod do pliku w workspace
- read_file: Odczytaj istniejący kod
- list_files: Zobacz jakie pliki już istnieją
- file_exists: Sprawdź czy plik istnieje

MASZ DOSTĘP DO SHELL:
- run_shell: Wykonaj komendę shell w bezpiecznym środowisku

MASZ DOSTĘP DO ORKIESTRACJI DOCKER COMPOSE:
- create_environment: Stwórz środowisko wielokontenerowe (stack) z docker-compose.yml
- destroy_environment: Usuń środowisko i posprzątaj zasoby
- check_service_health: Sprawdź logi i status serwisu w środowisku
- list_environments: Zobacz aktywne środowiska
- get_environment_status: Pobierz szczegółowy status środowiska

ZASADY:
- Gdy użytkownik prosi o napisanie kodu DO PLIKU, UŻYJ funkcji write_file
- Nie tylko wypisuj kod w markdownie - zapisz go fizycznie używając write_file
- Kod powinien być kompletny i gotowy do użycia
- Dodaj komentarze wyjaśniające tylko wtedy, gdy logika jest złożona
- Używaj dobrych praktyk programistycznych i konwencji nazewnictwa
- Gdy zadanie wymaga bazy danych, cache lub innych serwisów - użyj create_environment z docker-compose.yml

Przykłady:
Żądanie: "Stwórz plik test.py z funkcją Hello World"
Akcja:
1. Wygeneruj kod funkcji
2. UŻYJ write_file("test.py", kod) aby zapisać go do pliku
3. Potwierdź zapis

Żądanie: "Co jest w pliku test.py?"
Akcja: Użyj read_file("test.py") i pokaż zawartość

Żądanie: "Stwórz API z bazą Redis"
Akcja:
1. Stwórz docker-compose.yml z serwisami (api, redis)
2. Użyj create_environment() aby uruchomić stack
3. Stwórz kod aplikacji używając nazw sieciowych serwisów (host='redis')
4. Zapisz kod używając write_file()

Żądanie: "Napisz funkcję Hello World w Python" (bez wskazania pliku)
Odpowiedź: Pokaż kod w bloku markdown:
```python
def hello_world():
    \"\"\"Wyświetla Hello World.\"\"\"
    print("Hello World")
```"""

    def __init__(self, kernel: Kernel, enable_self_repair: bool = True):
        """
        Inicjalizacja CoderAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            enable_self_repair: Czy włączyć pętlę samonaprawy (domyślnie True)
        """
        super().__init__(kernel)

        # Zarejestruj FileSkill
        self.file_skill = FileSkill()
        self.kernel.add_plugin(self.file_skill, plugin_name="FileSkill")

        # Zarejestruj ShellSkill
        self.shell_skill = ShellSkill(use_sandbox=True)
        self.kernel.add_plugin(self.shell_skill, plugin_name="ShellSkill")

        # Zarejestruj ComposeSkill
        self.compose_skill = ComposeSkill()
        self.kernel.add_plugin(self.compose_skill, plugin_name="ComposeSkill")

        self.enable_self_repair = enable_self_repair
        logger.info(
            f"CoderAgent zainicjalizowany z FileSkill, ShellSkill i ComposeSkill (self_repair={enable_self_repair})"
        )

    async def process_with_params(
        self, input_text: str, generation_params: dict[str, Any]
    ) -> str:
        """
        Generuje kod z niestandardowymi parametrami generacji.

        Args:
            input_text: Opis zadania programistycznego
            generation_params: Parametry generacji (temperature, max_tokens, etc.)

        Returns:
            Wygenerowany kod w bloku markdown lub potwierdzenie zapisu
        """
        logger.info(
            f"CoderAgent przetwarza żądanie z parametrami: {input_text[:100]}..."
        )
        if generation_params:
            safe_params = self._get_safe_params_for_logging(generation_params)
            logger.debug(f"Kluczowe parametry generacji: {safe_params}")
        return await self._process_internal(input_text, generation_params)

    async def process(self, input_text: str) -> str:
        """
        Generuje kod na podstawie żądania użytkownika.

        Args:
            input_text: Opis zadania programistycznego

        Returns:
            Wygenerowany kod w bloku markdown lub potwierdzenie zapisu

        """
        logger.info(f"CoderAgent przetwarza żądanie: {input_text[:100]}...")
        return await self._process_internal(input_text, None)

    async def _process_internal(
        self, input_text: str, generation_params: Optional[dict[str, Any]] = None
    ) -> str:
        """
        Wewnętrzna metoda generowania kodu z opcjonalnymi parametrami.

        Args:
            input_text: Opis zadania programistycznego
            generation_params: Opcjonalne parametry generacji

        Returns:
            Wygenerowany kod
        """
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
            chat_service: Any = self.kernel.get_service()

            # Włącz automatyczne wywoływanie funkcji i użyj parametrów generacji
            settings = self._create_execution_settings(
                generation_params=generation_params,
                function_choice_behavior=FunctionChoiceBehavior.Auto(),
            )

            # Wywołaj model z możliwością auto-wywołania funkcji
            response = await self._invoke_chat_with_fallbacks(
                chat_service=chat_service,
                chat_history=chat_history,
                settings=settings,
                enable_functions=True,
            )

            result = str(response).strip()
            logger.info(f"CoderAgent wygenerował odpowiedź ({len(result)} znaków)")
            return result

        except Exception as e:
            logger.error(f"Błąd podczas generowania kodu: {e}")
            raise

    async def process_with_verification(
        self, input_text: str, script_name: str = "script.py", max_retries: int = 3
    ) -> dict:
        """
        Generuje kod, zapisuje go i weryfikuje wykonanie z pętlą samonaprawy.

        Args:
            input_text: Opis zadania programistycznego
            script_name: Nazwa pliku do utworzenia (domyślnie "script.py")
            max_retries: Maksymalna liczba prób naprawy (domyślnie 3)

        Returns:
            Dict z kluczami:
            - success: bool - czy wykonanie się powiodło
            - output: str - output z wykonania lub błąd
            - attempts: int - liczba prób
            - final_code: str - ostateczna wersja kodu
        """
        if not self.enable_self_repair:
            # Bez weryfikacji - tylko generuj kod
            response = await self.process(input_text)
            return self._build_final_verification_result(
                success=True, output=response, attempts=1, final_code=None
            )

        logger.info(f"Rozpoczynam weryfikowane generowanie kodu: {script_name}")

        chat_history = self._build_verification_chat_history(input_text, script_name)

        for attempt in range(1, max_retries + 1):
            logger.info(f"Próba {attempt}/{max_retries}")

            try:
                attempt_result = await self._run_single_verification_attempt(
                    chat_history=chat_history,
                    script_name=script_name,
                )
                if attempt_result["retry"]:
                    continue

                if attempt_result["exit_code"] == 0:
                    logger.info(f"Kod działa poprawnie po {attempt} próbach")
                    return self._build_final_verification_result(
                        success=True,
                        output=attempt_result["shell_result"],
                        attempts=attempt,
                        final_code=attempt_result["code_content"],
                    )

                logger.warning(f"Kod zawiera błędy (próba {attempt})")
                if attempt < max_retries:
                    self._append_repair_feedback_to_history(
                        chat_history, attempt_result["shell_result"], script_name
                    )
                    continue

                logger.error(f"Nie udało się naprawić kodu po {max_retries} próbach")
                return self._build_final_verification_result(
                    success=False,
                    output=attempt_result["shell_result"],
                    attempts=attempt,
                    final_code=attempt_result["code_content"],
                )

            except Exception as e:
                logger.error(f"Błąd w próbie {attempt}: {e}")
                if attempt >= max_retries:
                    return self._build_final_verification_result(
                        success=False,
                        output=f"Błąd: {e}",
                        attempts=attempt,
                        final_code=None,
                    )

                # Poproś o naprawę
                chat_history.add_message(
                    ChatMessageContent(
                        role=AuthorRole.USER,
                        content=f"Wystąpił błąd: {e}. Proszę spróbować ponownie.",
                    )
                )

        # Nie powinniśmy tu dojść, ale dla bezpieczeństwa
        return {
            "success": False,
            "output": "Przekroczono maksymalną liczbę prób",
            "attempts": max_retries,
            "final_code": None,
        }

    def _build_verification_chat_history(
        self, input_text: str, script_name: str
    ) -> ChatHistory:
        chat_history = ChatHistory()
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
        )
        enhanced_input = (
            f"{input_text}\n\nZapisz wygenerowany kod do pliku '{script_name}'."
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=enhanced_input)
        )
        return chat_history

    async def _run_single_verification_attempt(
        self, *, chat_history: ChatHistory, script_name: str
    ) -> dict[str, Any]:
        chat_service: Any = self.kernel.get_service()
        settings = OpenAIChatPromptExecutionSettings(
            function_choice_behavior=FunctionChoiceBehavior.Auto()
        )
        response = await self._invoke_chat_with_fallbacks(
            chat_service=chat_service,
            chat_history=chat_history,
            settings=settings,
            enable_functions=True,
        )

        logger.info("Model wygenerował odpowiedź")
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.ASSISTANT, content=str(response))
        )

        try:
            code_content = await self.file_skill.read_file(script_name)
            logger.info(f"Kod zapisany do {script_name} ({len(code_content)} znaków)")
        except FileNotFoundError:
            logger.warning(
                f"Plik {script_name} nie został utworzony, generuję ponownie"
            )
            chat_history.add_message(
                ChatMessageContent(
                    role=AuthorRole.USER,
                    content=(
                        f"Plik {script_name} nie został utworzony. Proszę zapisać kod "
                        f"używając write_file('{script_name}', kod)."
                    ),
                )
            )
            return {
                "retry": True,
                "shell_result": "",
                "exit_code": 1,
                "code_content": None,
            }

        logger.info(f"Uruchamianie kodu: python {script_name}")
        shell_result = self.shell_skill.run_shell(f"python {script_name}", timeout=30)
        exit_code = self.shell_skill.get_exit_code_from_output(shell_result)
        logger.info(f"Wykonanie zakończone z exit_code={exit_code}")
        return {
            "retry": False,
            "shell_result": shell_result,
            "exit_code": exit_code,
            "code_content": code_content,
        }

    def _append_repair_feedback_to_history(
        self, chat_history: ChatHistory, shell_result: str, script_name: str
    ) -> None:
        feedback = (
            "Otrzymałem błąd podczas wykonywania kodu:\n\n"
            f"{shell_result}\n\n"
            "Proszę poprawić kod i zapisać go ponownie do pliku "
            f"'{script_name}'."
        )
        chat_history.add_message(
            ChatMessageContent(role=AuthorRole.USER, content=feedback)
        )

    @staticmethod
    def _build_final_verification_result(
        *, success: bool, output: str, attempts: int, final_code: Any
    ) -> dict[str, Any]:
        return {
            "success": success,
            "output": output,
            "attempts": attempts,
            "final_code": final_code,
        }
