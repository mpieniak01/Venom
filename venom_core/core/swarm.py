"""Moduł: swarm - AutoGen Bridge dla Venom Agents.

Ten moduł stanowi most między światem Semantic Kernel (nasze Skille)
a światem AutoGen (Swarm Intelligence / Group Chat).
"""

from typing import Any, Callable, Dict, List, Optional

from autogen import ConversableAgent

from venom_core.agents.base import BaseAgent
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class VenomAgent(ConversableAgent):
    """
    Wrapper AutoGen na istniejące agenty Venom.

    Łączy funkcjonalność BaseAgent (Semantic Kernel) z ConversableAgent (AutoGen),
    pozwalając naszym agentom uczestniczyć w Group Chat.
    """

    def __init__(
        self,
        name: str,
        venom_agent: BaseAgent,
        system_message: str,
        llm_config: Optional[Dict] = None,
        **kwargs,
    ):
        """
        Inicjalizacja VenomAgent.

        Args:
            name: Nazwa agenta w Group Chat
            venom_agent: Instancja oryginalnego agenta Venom (CoderAgent, CriticAgent, etc.)
            system_message: System prompt dla agenta (pobierany z SYSTEM_PROMPT agenta)
            llm_config: Konfiguracja LLM dla AutoGen
            **kwargs: Dodatkowe parametry dla ConversableAgent
        """
        # Inicjalizuj ConversableAgent z AutoGen
        super().__init__(
            name=name,
            system_message=system_message,
            llm_config=llm_config,
            **kwargs,
        )

        # Przechowuj referencję do oryginalnego agenta Venom
        self.venom_agent = venom_agent

        # Zarejestruj funkcje z Semantic Kernel jako AutoGen tools
        self._register_venom_functions()

        logger.info(
            f"VenomAgent '{name}' zainicjalizowany jako wrapper dla {type(venom_agent).__name__}"
        )

    def _register_venom_functions(self):
        """
        Rejestruje funkcje z Semantic Kernel jako AutoGen function calling tools.

        Mapuje skille dostępne w venom_agent.kernel jako funkcje callable przez AutoGen.
        """
        if not hasattr(self.venom_agent, "kernel"):
            logger.warning(
                f"Agent {self.name} nie ma kernela - brak funkcji do zarejestrowania"
            )
            return

        kernel = self.venom_agent.kernel

        # Pobierz wszystkie pluginy z kernela
        try:
            plugins = kernel.plugins
            if not plugins:
                logger.debug(f"Brak pluginów w kernelu dla agenta {self.name}")
                return

            # Dla każdego pluginu, zarejestruj jego funkcje
            for plugin_name, plugin in plugins.items():
                logger.debug(f"Przetwarzam plugin: {plugin_name}")

                # Pobierz wszystkie funkcje z pluginu
                for func_name in dir(plugin):
                    # Pomiń prywatne i magiczne metody
                    if func_name.startswith("_"):
                        continue

                    func = getattr(plugin, func_name)

                    # Sprawdź czy to callable
                    if not callable(func):
                        continue

                    # Zarejestruj funkcję w AutoGen
                    self._register_function(plugin_name, func_name, func)

        except Exception as e:
            logger.error(f"Błąd podczas rejestracji funkcji z kernela: {e}")

    def _register_function(self, plugin_name: str, func_name: str, func: Callable):
        """
        Rejestruje pojedynczą funkcję jako AutoGen tool.

        Args:
            plugin_name: Nazwa pluginu (np. "FileSkill")
            func_name: Nazwa funkcji (np. "write_file")
            func: Funkcja do zarejestrowania
        """
        try:
            # Stwórz nazwę funkcji dla AutoGen
            autogen_func_name = f"{plugin_name}_{func_name}"

            # Zarejestruj funkcję używając AutoGen API
            self.register_function(function_map={autogen_func_name: func})

            logger.debug(f"Zarejestrowano funkcję: {autogen_func_name}")

        except Exception as e:
            logger.warning(f"Nie udało się zarejestrować funkcji {func_name}: {e}")

    async def a_process_venom(self, message: str) -> str:
        """
        Przetwarza wiadomość przez oryginalny agent Venom.

        Ta metoda pozwala na bezpośrednie wywołanie procesu agenta Venom
        bez przechodzenia przez AutoGen chat.

        Args:
            message: Wiadomość do przetworzenia

        Returns:
            Odpowiedź od agenta Venom
        """
        try:
            result = await self.venom_agent.process(message)
            return result
        except Exception as e:
            error_msg = f"Błąd podczas przetwarzania przez {self.name}: {e}"
            logger.error(error_msg)
            return error_msg


def create_venom_agent_wrapper(
    agent: BaseAgent,
    name: str,
    system_message: Optional[str] = None,
    llm_config: Optional[Dict] = None,
) -> VenomAgent:
    """
    Factory function do tworzenia VenomAgent wrapperów.

    Args:
        agent: Instancja BaseAgent (CoderAgent, CriticAgent, etc.)
        name: Nazwa agenta w Group Chat
        system_message: Opcjonalny system prompt (jeśli None, próbuje pobrać z agent.SYSTEM_PROMPT)
        llm_config: Konfiguracja LLM dla AutoGen

    Returns:
        VenomAgent wrapper gotowy do użycia w Group Chat
    """
    # Pobierz system prompt z agenta jeśli nie podano
    if system_message is None:
        system_message = getattr(agent, "SYSTEM_PROMPT", f"Jesteś agentem {name}")

    # Stwórz wrapper
    venom_agent = VenomAgent(
        name=name,
        venom_agent=agent,
        system_message=system_message,
        llm_config=llm_config,
    )

    logger.info(f"Utworzono VenomAgent wrapper: {name}")
    return venom_agent


def extract_venom_tools(agent: BaseAgent) -> List[Dict[str, Any]]:
    """
    Ekstrahuje definicje narzędzi z agenta Venom w formacie AutoGen.

    Args:
        agent: Agent Venom z załadowanymi skills

    Returns:
        Lista definicji narzędzi w formacie JSON Schema dla AutoGen function calling
    """
    tools = []

    if not hasattr(agent, "kernel"):
        return tools

    kernel = agent.kernel

    try:
        plugins = kernel.plugins
        if not plugins:
            return tools

        for plugin_name, plugin in plugins.items():
            for func_name in dir(plugin):
                if func_name.startswith("_"):
                    continue

                func = getattr(plugin, func_name)
                if not callable(func):
                    continue

                # Stwórz definicję narzędzia
                tool_def = {
                    "type": "function",
                    "function": {
                        "name": f"{plugin_name}_{func_name}",
                        "description": func.__doc__
                        or f"Funkcja {func_name} z {plugin_name}",
                        "parameters": {
                            "type": "object",
                            "properties": {},
                            "required": [],
                        },
                    },
                }

                tools.append(tool_def)

    except Exception as e:
        logger.error(f"Błąd podczas ekstrakcji narzędzi: {e}")

    return tools
