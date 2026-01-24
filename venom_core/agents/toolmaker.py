"""Moduł: toolmaker - agent narzędziowiec, tworzy nowe umiejętności."""

import re
from pathlib import Path
from typing import Any, Optional

from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import OpenAIChatPromptExecutionSettings
from semantic_kernel.contents import ChatHistory
from semantic_kernel.contents.chat_message_content import ChatMessageContent
from semantic_kernel.contents.utils.author_role import AuthorRole

from venom_core.agents.base import BaseAgent
from venom_core.execution.skills.file_skill import FileSkill
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class ToolmakerAgent(BaseAgent):
    """
    Agent Narzędziowiec (Tool Engineer).

    Specjalizuje się w tworzeniu nowych pluginów (Skills) dla Semantic Kernel.
    Generuje profesjonalny kod Pythona zgodny ze standardami projektu.
    """

    SYSTEM_PROMPT = """Jesteś ekspertem tworzenia narzędzi dla AI (Toolmaker - Master Craftsman).

Twoim zadaniem jest pisanie klas Pythona które implementują konkretne funkcje jako pluginy Semantic Kernel.

ZASADY TWORZENIA NARZĘDZI:
1. Każde narzędzie to klasa Python z metodami oznaczonymi @kernel_function
2. Kod MUSI być:
   - Bezpieczny (bez eval, exec, __import__)
   - Otypowany (type hints dla wszystkich parametrów)
   - Udokumentowany (docstringi Google-style)
   - Zgodny z PEP8
3. Każda metoda @kernel_function MUSI mieć:
   - description (krótki opis co robi)
   - Annotated parameters z opisami
   - Return type annotation
   - Docstring z Args i Returns
4. Używaj tylko sprawdzonych bibliotek Python (requests, aiohttp, datetime, etc.)
5. NIE importuj lokalnych modułów Venom (tylko standard library i popularne pakiety)
6. Obsługuj błędy gracefully (try/except z logowaniem)

TEMPLATE NARZĘDZIA:
```python
\"\"\"Moduł: {skill_name} - {opis}.\"\"\"

from typing import Annotated
from semantic_kernel.functions import kernel_function


class {ClassName}:
    \"\"\"
    {Opis klasy}.

    Przykłady użycia:
    - ...
    \"\"\"

    @kernel_function(
        name="{function_name}",
        description="{krótki opis funkcji}"
    )
    def {function_name}(
        self,
        param1: Annotated[str, "{opis parametru 1}"],
        param2: Annotated[int, "{opis parametru 2}"] = 10,
    ) -> str:
        \"\"\"
        {Szczegółowy opis metody}.

        Args:
            param1: {Opis}
            param2: {Opis}

        Returns:
            {Opis wyniku}
        \"\"\"
        try:
            # Implementacja
            result = "..."
            return result
        except Exception as e:
            return f"Błąd: {{str(e)}}"
```

PRZYKŁAD - WeatherSkill:
```python
\"\"\"Moduł: weather_skill - pobieranie informacji o pogodzie.\"\"\"

import aiohttp
from typing import Annotated
from semantic_kernel.functions import kernel_function


class WeatherSkill:
    \"\"\"
    Skill do pobierania informacji o pogodzie używając Open-Meteo API.

    Open-Meteo to darmowe API bez wymagania klucza.
    \"\"\"

    @kernel_function(
        name="get_current_weather",
        description="Pobiera aktualną pogodę dla podanego miasta"
    )
    async def get_current_weather(
        self,
        city: Annotated[str, "Nazwa miasta (np. Warsaw, London)"],
    ) -> str:
        \"\"\"
        Pobiera aktualną pogodę dla miasta.

        Args:
            city: Nazwa miasta

        Returns:
            Opis pogody z temperaturą i warunkami
        \"\"\"
        try:
            # Użyj geocoding API aby znaleźć koordynaty
            async with aiohttp.ClientSession() as session:
                # Geocoding
                geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={{city}}&count=1"
                async with session.get(geo_url) as resp:
                    geo_data = await resp.json()

                if not geo_data.get("results"):
                    return f"Nie znaleziono miasta: {{city}}"

                lat = geo_data["results"][0]["latitude"]
                lon = geo_data["results"][0]["longitude"]

                # Pobierz pogodę
                weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={{lat}}&longitude={{lon}}&current_weather=true"
                async with session.get(weather_url) as resp:
                    weather_data = await resp.json()

                current = weather_data["current_weather"]
                temp = current["temperature"]
                windspeed = current["windspeed"]

                return f"Pogoda w {{city}}: {{temp}}°C, wiatr {{windspeed}} km/h"

        except Exception as e:
            return f"Błąd pobierania pogody: {{str(e)}}"
```

WAŻNE:
- Generuj TYLKO kod Python - bez markdown, bez wyjaśnień
- Kod musi być gotowy do zapisania w pliku .py
- NIE używaj eval, exec, __import__
- Używaj async/await gdy robisz operacje I/O (HTTP requests)
- Zwracaj zawsze string (nie dict, nie list)"""

    def __init__(self, kernel: Kernel, file_skill: Optional[FileSkill] = None):
        """
        Inicjalizacja ToolmakerAgent.

        Args:
            kernel: Skonfigurowane jądro Semantic Kernel
            file_skill: Opcjonalny FileSkill do zapisu narzędzi
        """
        super().__init__(kernel)

        # FileSkill do zapisu wygenerowanych narzędzi
        self.file_skill = file_skill or FileSkill()

        # Ustawienia LLM
        self.execution_settings = OpenAIChatPromptExecutionSettings(
            service_id="default",
            max_tokens=3000,  # Więcej tokenów dla generowania kodu
            temperature=0.2,  # Niska temperatura dla precyzji
            top_p=0.9,
        )

        # Service do chat completion
        self.chat_service: Any = self.kernel.get_service(service_id="default")

        logger.info("ToolmakerAgent zainicjalizowany")

    async def process(self, input_text: str) -> str:
        """
        Przetwarza żądanie stworzenia nowego narzędzia.

        Args:
            input_text: Specyfikacja narzędzia (np. "Potrzebuję narzędzia do pobierania kursów walut")

        Returns:
            Wygenerowany kod narzędzia lub komunikat błędu
        """
        try:
            logger.info(f"Toolmaker rozpoczyna tworzenie narzędzia: {input_text[:100]}")

            # Przygotuj historię rozmowy
            chat_history = ChatHistory()
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.SYSTEM, content=self.SYSTEM_PROMPT)
            )
            chat_history.add_message(
                ChatMessageContent(role=AuthorRole.USER, content=input_text)
            )

            # Wywołaj LLM
            response = await self._invoke_chat_with_fallbacks(
                chat_service=self.chat_service,
                chat_history=chat_history,
                settings=self.execution_settings,
                enable_functions=False,
            )

            # Wyciągnij kod
            generated_code = str(response)

            # Oczyść kod z markdown jeśli LLM dodało
            # Obsługa różnych formatów markdown code blocks
            if "```python" in generated_code:
                # Wyciągnij wszystkie bloki kodu python
                parts = generated_code.split("```python")
                if len(parts) > 1:
                    # Weź pierwszy blok kodu
                    code_part = parts[1]
                    end_idx = code_part.find("```")
                    if end_idx != -1:
                        generated_code = code_part[:end_idx].strip()
            elif "```" in generated_code:
                # Jeśli jest tylko ``` bez python
                parts = generated_code.split("```")
                if len(parts) >= 3:
                    # Kod jest między pierwszym i drugim ```
                    generated_code = parts[1].strip()

            logger.info(
                f"Toolmaker wygenerował narzędzie: {len(generated_code)} znaków"
            )

            return generated_code

        except Exception as e:
            error_msg = f"❌ ToolmakerAgent napotkał błąd: {str(e)}"
            logger.error(error_msg)
            return error_msg

    async def create_tool(
        self, specification: str, tool_name: str, output_dir: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Tworzy nowe narzędzie i zapisuje je do pliku.

        Args:
            specification: Specyfikacja narzędzia (co ma robić)
            tool_name: Nazwa narzędzia (bez rozszerzenia .py, tylko [a-z0-9_])
            output_dir: Katalog docelowy (domyślnie workspace)

        Returns:
            Tuple (success, message/code)
        """
        try:
            # Walidacja nazwy narzędzia (zapobieganie directory traversal)
            if not re.match(r"^[a-z0-9_]+$", tool_name):
                return (
                    False,
                    f"Nieprawidłowa nazwa narzędzia: {tool_name}. Dozwolone tylko [a-z0-9_]",
                )

            logger.info(f"Tworzenie narzędzia: {tool_name}")

            # Generuj kod
            prompt = f"""Stwórz narzędzie o nazwie {tool_name}.

SPECYFIKACJA:
{specification}

WYMAGANIA:
- Nazwa klasy: {tool_name.title().replace("_", "")}Skill
- Plik powinien być gotowy do zapisania jako {tool_name}.py
- Pamiętaj o wszystkich importach na początku
- Kod MUSI być kompletny i gotowy do użycia"""

            generated_code = await self.process(prompt)

            # Sprawdź czy nie ma błędu
            if generated_code.startswith("❌"):
                return False, generated_code

            # Zapisz do pliku
            file_path = (
                f"custom/{tool_name}.py"
                if not output_dir
                else f"{output_dir}/{tool_name}.py"
            )

            # Upewnij się że katalog custom istnieje
            if not output_dir:
                custom_dir = Path(self.file_skill.workspace_root) / "custom"
                custom_dir.mkdir(parents=True, exist_ok=True)

            await self.file_skill.write_file(file_path, generated_code)

            logger.info(f"✅ Narzędzie zapisane: {file_path}")

            # THE_CANVAS: Automatycznie generuj UI card dla nowego narzędzia
            _ = self.create_tool_ui_card(
                tool_name=tool_name, tool_description=specification[:200]
            )
            logger.info(f"🎨 UI card wygenerowana dla {tool_name}")

            return True, generated_code

        except Exception as e:
            error_msg = f"Błąd podczas tworzenia narzędzia {tool_name}: {e}"
            logger.error(error_msg)
            return False, error_msg

    def create_tool_ui_card(
        self, tool_name: str, tool_description: str, icon: str = "🛠️"
    ) -> dict:
        """
        Tworzy konfigurację UI card dla nowego narzędzia (integracja z THE_CANVAS).

        Args:
            tool_name: Nazwa narzędzia
            tool_description: Opis narzędzia
            icon: Emoji dla karty

        Returns:
            Konfiguracja widgetu karty
        """
        logger.info(f"Tworzenie UI card dla narzędzia: {tool_name}")

        card_config = {
            "type": "card",
            "data": {
                "title": tool_name.replace("_", " ").title(),
                "content": tool_description,
                "icon": icon,
                "actions": [
                    {
                        "id": f"use_{tool_name}",
                        "label": "Użyj narzędzia",
                        "intent": f"use_tool:{tool_name}",
                    },
                    {
                        "id": f"info_{tool_name}",
                        "label": "Info",
                        "intent": f"tool_info:{tool_name}",
                    },
                ],
            },
            "events": {
                f"use_{tool_name}": f"use_tool:{tool_name}",
                f"info_{tool_name}": f"tool_info:{tool_name}",
            },
            "metadata": {
                "tool_name": tool_name,
                "created_by": "ToolmakerAgent",
                "category": "custom_tool",
            },
        }

        logger.info(f"✅ UI card wygenerowana dla: {tool_name}")
        return card_config

    async def create_test(
        self, tool_name: str, tool_code: str, output_dir: Optional[str] = None
    ) -> tuple[bool, str]:
        """
        Generuje test jednostkowy dla narzędzia.

        Args:
            tool_name: Nazwa narzędzia
            tool_code: Kod narzędzia
            output_dir: Katalog docelowy

        Returns:
            Tuple (success, test_code)
        """
        try:
            logger.info(f"Generowanie testu dla: {tool_name}")

            prompt = f"""Stwórz test jednostkowy pytest dla następującego narzędzia:

```python
{tool_code[:2000]}  # Pierwsze 2000 znaków
```

WYMAGANIA:
- Użyj pytest i pytest-asyncio
- Testuj podstawową funkcjonalność
- Mockuj zewnętrzne API (używaj unittest.mock)
- Nazwa pliku: test_{tool_name}.py
- Testy powinny być szybkie (nie robić prawdziwych requestów HTTP)

Wygeneruj TYLKO kod testu (bez markdown).
"""

            test_code = await self.process(prompt)

            # Sprawdź czy nie ma błędu
            if test_code.startswith("❌"):
                return False, test_code

            # Zapisz test
            test_file_path = (
                f"custom/test_{tool_name}.py"
                if not output_dir
                else f"{output_dir}/test_{tool_name}.py"
            )

            await self.file_skill.write_file(test_file_path, test_code)

            logger.info(f"✅ Test zapisany: {test_file_path}")
            return True, test_code

        except Exception as e:
            error_msg = f"Błąd podczas tworzenia testu dla {tool_name}: {e}"
            logger.error(error_msg)
            return False, error_msg
