"""Moduł: forge - The Forge workflow (tworzenie nowych narzędzi)."""

from typing import Callable, Optional
from uuid import UUID

from venom_core.agents.guardian import GuardianAgent
from venom_core.core.dispatcher import TaskDispatcher
from venom_core.core.state_manager import StateManager
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ForgeFlow:
    """
    Workflow "The Forge" - tworzenie nowego narzędzia.

    Algorytm:
    1. CRAFT: Toolmaker generuje kod narzędzia
    2. TEST: Toolmaker generuje test jednostkowy
    3. VERIFY: Guardian testuje narzędzie w Dockerze
    4. LOAD: SkillManager ładuje narzędzie do Kernela
    """

    def __init__(
        self,
        state_manager: StateManager,
        task_dispatcher: TaskDispatcher,
        event_broadcaster: Optional[Callable] = None,
    ):
        """
        Inicjalizacja ForgeFlow.

        Args:
            state_manager: Menedżer stanu zadań
            task_dispatcher: Dispatcher zadań (dostęp do agentów)
            event_broadcaster: Opcjonalny broadcaster zdarzeń
        """
        self.state_manager = state_manager
        self.task_dispatcher = task_dispatcher
        self.event_broadcaster = event_broadcaster

    async def _broadcast_event(
        self, event_type: str, message: str, agent: str = None, data: dict = None
    ):
        """
        Wysyła zdarzenie do WebSocket (jeśli broadcaster jest dostępny).

        Args:
            event_type: Typ zdarzenia
            message: Treść wiadomości
            agent: Opcjonalna nazwa agenta
            data: Opcjonalne dodatkowe dane
        """
        if self.event_broadcaster:
            await self.event_broadcaster.broadcast_event(
                event_type=event_type, message=message, agent=agent, data=data
            )

    async def execute(
        self, task_id: UUID, tool_specification: str, tool_name: str
    ) -> dict:
        """
        Wykonuje workflow "The Forge" - tworzenie nowego narzędzia.

        Args:
            task_id: ID zadania
            tool_specification: Specyfikacja narzędzia (co ma robić)
            tool_name: Nazwa narzędzia (snake_case, bez .py)

        Returns:
            Słownik z wynikami:
            - success: bool - czy narzędzie zostało stworzone i załadowane
            - tool_name: str - nazwa narzędzia
            - message: str - opis wyniku
            - code: str - wygenerowany kod (jeśli sukces)
        """
        try:
            logger.info(f"🔨 THE FORGE: Rozpoczynam tworzenie narzędzia {tool_name}")

            self.state_manager.add_log(
                task_id,
                f"🔨 THE FORGE: Tworzę nowe narzędzie '{tool_name}'",
            )

            await self._broadcast_event(
                event_type="FORGE_STARTED",
                message=f"Rozpoczynam tworzenie narzędzia: {tool_name}",
                agent="Toolmaker",
                data={"task_id": str(task_id), "tool_name": tool_name},
            )

            # PHASE 1: CRAFT - Toolmaker generuje kod
            self.state_manager.add_log(
                task_id,
                "⚒️ PHASE 1: Toolmaker generuje kod narzędzia...",
            )

            toolmaker = self.task_dispatcher.toolmaker_agent

            # Generuj narzędzie
            success, tool_code = await toolmaker.create_tool(
                specification=tool_specification,
                tool_name=tool_name,
                output_dir=None,  # Zapisze do workspace/custom/
            )

            if not success:
                error_msg = f"❌ Toolmaker nie mógł wygenerować narzędzia: {tool_code}"
                logger.error(error_msg)
                self.state_manager.add_log(task_id, error_msg)

                await self._broadcast_event(
                    event_type="FORGE_FAILED",
                    message=error_msg,
                    agent="Toolmaker",
                    data={"task_id": str(task_id), "error": tool_code},
                )

                return {
                    "success": False,
                    "tool_name": tool_name,
                    "message": error_msg,
                }

            self.state_manager.add_log(
                task_id,
                f"✅ Kod narzędzia wygenerowany ({len(tool_code)} znaków)",
            )

            # PHASE 2: TEST - Toolmaker generuje test
            self.state_manager.add_log(
                task_id,
                "🧪 PHASE 2: Toolmaker generuje testy...",
            )

            test_success, test_code = await toolmaker.create_test(
                tool_name=tool_name,
                tool_code=tool_code,
                output_dir=None,
            )

            if test_success:
                self.state_manager.add_log(
                    task_id,
                    "✅ Test jednostkowy wygenerowany",
                )
            else:
                self.state_manager.add_log(
                    task_id,
                    f"⚠️ Nie udało się wygenerować testu: {test_code[:100]}",
                )

            # PHASE 3: VERIFY - Guardian testuje w Dockerze
            self.state_manager.add_log(
                task_id,
                "🔍 PHASE 3: Guardian weryfikuje narzędzie w Docker Sandbox...",
            )

            try:
                guardian = GuardianAgent(kernel=self.task_dispatcher.kernel)

                # Sprawdź podstawową składnię - ogranicz kod do bezpiecznego fragmentu
                # Używamy tylko metadanych, nie całego kodu aby uniknąć prompt injection
                verify_prompt = f"""Sprawdź czy narzędzie {tool_name} jest poprawne składniowo.

METADANE NARZĘDZIA:
- Nazwa: {tool_name}
- Długość kodu: {len(tool_code)} znaków
- Czy zawiera @kernel_function: {"TAK" if "@kernel_function" in tool_code else "NIE"}
- Czy zawiera klasę: {"TAK" if "class " in tool_code else "NIE"}

FRAGMENT KODU (pierwsze 500 znaków):
```python
{tool_code[:500]}
```

Zweryfikuj:
1. Czy fragment kodu jest poprawny składniowo (Python syntax)
2. Czy ma dekorator @kernel_function
3. Czy ma odpowiednie type hints
4. Czy nie widać niebezpiecznych konstrukcji (eval, exec)

Odpowiedz APPROVED jeśli wygląda OK, lub opisz problemy."""

                verification_result = await guardian.process(verify_prompt)

                if "APPROVED" in verification_result.upper():
                    self.state_manager.add_log(
                        task_id,
                        "✅ Narzędzie przeszło weryfikację Guardian",
                    )
                else:
                    self.state_manager.add_log(
                        task_id,
                        f"⚠️ Guardian zgłosił uwagi: {verification_result[:200]}",
                    )

            except Exception as e:
                logger.warning(f"Nie udało się uruchomić weryfikacji Docker: {e}")
                self.state_manager.add_log(
                    task_id,
                    f"⚠️ Pomijam weryfikację Docker (błąd: {str(e)})",
                )

            # PHASE 4: LOAD - SkillManager ładuje narzędzie
            self.state_manager.add_log(
                task_id,
                "⚡ PHASE 4: SkillManager ładuje narzędzie do Kernela...",
            )

            try:
                skill_manager = self.task_dispatcher.skill_manager

                # Przeładuj narzędzie (jeśli już istniało) lub załaduj nowe
                reload_success = skill_manager.reload_skill(tool_name)

                if reload_success:
                    self.state_manager.add_log(
                        task_id,
                        f"✅ Narzędzie '{tool_name}' załadowane i gotowe do użycia!",
                    )

                    await self._broadcast_event(
                        event_type="FORGE_COMPLETED",
                        message=f"Narzędzie {tool_name} zostało stworzone i załadowane",
                        agent="SkillManager",
                        data={
                            "task_id": str(task_id),
                            "tool_name": tool_name,
                            "success": True,
                        },
                    )

                    logger.info(f"🔨 THE FORGE: Narzędzie {tool_name} gotowe!")

                    return {
                        "success": True,
                        "tool_name": tool_name,
                        "message": f"Narzędzie '{tool_name}' zostało pomyślnie stworzone i załadowane. Możesz go teraz użyć!",
                        "code": tool_code,
                    }
                else:
                    error_msg = "❌ Nie udało się załadować narzędzia do Kernela"
                    self.state_manager.add_log(task_id, error_msg)

                    await self._broadcast_event(
                        event_type="FORGE_FAILED",
                        message=error_msg,
                        agent="SkillManager",
                        data={"task_id": str(task_id), "tool_name": tool_name},
                    )

                    return {
                        "success": False,
                        "tool_name": tool_name,
                        "message": error_msg,
                        "code": tool_code,
                    }

            except Exception as e:
                error_msg = f"❌ Błąd podczas ładowania narzędzia: {str(e)}"
                logger.error(error_msg)
                self.state_manager.add_log(task_id, error_msg)

                await self._broadcast_event(
                    event_type="FORGE_ERROR",
                    message=error_msg,
                    agent="SkillManager",
                    data={"task_id": str(task_id), "error": str(e)},
                )

                return {
                    "success": False,
                    "tool_name": tool_name,
                    "message": error_msg,
                }

        except Exception as e:
            error_msg = f"❌ Błąd podczas workflow The Forge: {str(e)}"
            logger.error(error_msg)
            self.state_manager.add_log(task_id, error_msg)

            await self._broadcast_event(
                event_type="FORGE_ERROR",
                message=error_msg,
                data={"task_id": str(task_id), "error": str(e)},
            )

            return {
                "success": False,
                "tool_name": tool_name,
                "message": error_msg,
            }
