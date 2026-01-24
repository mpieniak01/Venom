"""
Moduł: input_skill - Umiejętność motoryczna (kontrola myszy i klawiatury).

Ten skill pozwala na fizyczną interakcję z interfejsem systemu operacyjnego.
"""

import platform
import sys
import time
from typing import Annotated, Optional

from semantic_kernel.functions import kernel_function

from venom_core.utils.logger import get_logger

try:  # pragma: no cover - zależne od środowiska testowego
    import pyautogui  # type: ignore[import-untyped]
except Exception:  # pragma: no cover
    pyautogui = None

logger = get_logger(__name__)


class InputSkill:
    """
    Skill do sterowania myszą i klawiaturą.

    UWAGA BEZPIECZEŃSTWA:
    - PyAutoGUI Fail-Safe jest ZAWSZE aktywny (ruch myszy do (0,0) przerywa)
    - Wszystkie operacje są logowane
    - Zalecane jest ustawienie opóźnień między akcjami
    """

    def __init__(self, safety_delay: float = 0.5):
        """
        Inicjalizacja InputSkill.

        Args:
            safety_delay: Opóźnienie między akcjami (sekundy) dla bezpieczeństwa
        """
        resolved_pg = sys.modules.get("pyautogui", pyautogui)
        if resolved_pg is None:  # pragma: no cover - informacyjnie
            raise RuntimeError(
                "PyAutoGUI nie jest dostępne w tym środowisku. "
                "Zainstaluj pakiet lub uruchom w trybie z interfejsem graficznym."
            )

        self.pg = resolved_pg
        self.safety_delay = safety_delay
        self.system = platform.system()

        # Aktywuj PyAutoGUI Fail-Safe (ruch do rogu (0,0) przerywa)
        self.pg.FAILSAFE = True

        # Ustaw minimalne opóźnienie
        self.pg.PAUSE = max(0.1, safety_delay)

        # Pobierz rozdzielczość ekranu z tolerancją dla mocków/testów
        self.screen_width, self.screen_height = self._resolve_screen_size()

        logger.info(
            f"InputSkill zainicjalizowany (System: {self.system}, "
            f"Ekran: {self.screen_width}x{self.screen_height}, "
            f"Delay: {safety_delay}s, FailSafe: AKTYWNY)"
        )

    @kernel_function(
        name="mouse_click",
        description="Wykonuje kliknięcie myszą w określonych współrzędnych. UWAGA: To fizycznie porusza kursorem!",
    )
    async def mouse_click(
        self,
        x: Annotated[int, "Współrzędna X na ekranie"],
        y: Annotated[int, "Współrzędna Y na ekranie"],
        button: Annotated[str, "Przycisk myszy: 'left', 'right', 'middle'"] = "left",
        double: Annotated[bool, "Czy wykonać podwójne kliknięcie"] = False,
        move_duration: Annotated[
            float, "Czas ruchu kursora w sekundach (0 = natychmiast)"
        ] = 0.3,
    ) -> str:
        """
        Wykonuje kliknięcie myszą.

        Args:
            x: Współrzędna X
            y: Współrzędna Y
            button: Przycisk myszy ('left', 'right', 'middle')
            double: Czy podwójne kliknięcie
            move_duration: Czas ruchu kursora

        Returns:
            Komunikat o wyniku operacji

        Raises:
            pyautogui.FailSafeException: Jeśli mysz zostanie przesunięta do (0,0)
        """
        try:
            # Walidacja współrzędnych
            if not self._validate_coordinates(x, y):
                return f"❌ Nieprawidłowe współrzędne: ({x}, {y})"

            # Walidacja przycisku
            if button not in ["left", "right", "middle"]:
                return f"❌ Nieprawidłowy przycisk: {button}"

            logger.info(
                f"Klikanie myszą: ({x}, {y}), przycisk={button}, double={double}"
            )

            # Przesuń mysz
            self.pg.moveTo(x, y, duration=move_duration)

            # Czekaj chwilę
            time.sleep(0.1)

            # Kliknij
            if double:
                self.pg.doubleClick(button=button)
            else:
                self.pg.click(button=button)

            # Czekaj safety delay
            time.sleep(self.safety_delay)

            return f"✅ Kliknięto w ({x}, {y}) przyciskiem {button}"

        except self.pg.FailSafeException:
            error_msg = "🛑 FAIL-SAFE AKTYWOWANY! Mysz przesunięta do (0,0) - operacja przerwana"
            logger.warning(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas klikania: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    def _resolve_screen_size(self) -> tuple[int, int]:
        """Zwraca rozmiar ekranu tolerując różne typy odpowiedzi pyautogui."""

        size = self.pg.size()

        # Standardowy przypadek: tuple/list
        if isinstance(size, (tuple, list)) and len(size) >= 2:
            return int(size[0]), int(size[1])

        # Obiekt z atrybutami width/height (np. pyautogui.Size)
        if hasattr(size, "width") and hasattr(size, "height"):
            return int(size.width), int(size.height)

        # Spróbuj wymusić iterowalność (np. MagicMock może zachowywać się niestandardowo)
        try:
            seq = list(size)
            if len(seq) >= 2:
                return int(seq[0]), int(seq[1])
        except TypeError:
            # size might not be iterable in some edge cases
            logger.debug(f"Could not convert screen size to tuple: {size}")

        raise RuntimeError("PyAutoGUI zwróciło nieprawidłowy rozmiar ekranu")

    @kernel_function(
        name="keyboard_type",
        description="Wpisuje tekst używając klawiatury. UWAGA: Wpisuje w aktywnym oknie!",
    )
    async def keyboard_type(
        self,
        text: Annotated[str, "Tekst do wpisania"],
        interval: Annotated[float, "Opóźnienie między literami (sekundy)"] = 0.05,
    ) -> str:
        """
        Wpisuje tekst używając klawiatury.

        Args:
            text: Tekst do wpisania
            interval: Opóźnienie między literami (symuluje ludzkie pisanie)

        Returns:
            Komunikat o wyniku operacji

        Raises:
            pyautogui.FailSafeException: Jeśli mysz zostanie przesunięta do (0,0)
        """
        try:
            if not text:
                return "❌ Brak tekstu do wpisania"

            logger.info(f"Wpisywanie tekstu: '{text[:50]}...' (długość: {len(text)})")

            # Wpisz tekst
            self.pg.write(text, interval=interval)

            # Czekaj safety delay
            time.sleep(self.safety_delay)

            return f"✅ Wpisano tekst ({len(text)} znaków)"

        except self.pg.FailSafeException:
            error_msg = "🛑 FAIL-SAFE AKTYWOWANY! Mysz przesunięta do (0,0) - operacja przerwana"
            logger.warning(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas pisania: {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @kernel_function(
        name="keyboard_hotkey",
        description="Wykonuje skrót klawiszowy (np. 'ctrl+s', 'alt+tab'). UWAGA: Działa w aktywnym oknie!",
    )
    async def keyboard_hotkey(
        self,
        keys: Annotated[
            str,
            "Skrót klawiszowy rozdzielony '+' (np. 'ctrl+s', 'win+r', 'alt+f4')",
        ],
    ) -> str:
        """
        Wykonuje skrót klawiszowy.

        Args:
            keys: Skrót klawiszowy (np. 'ctrl+s', 'alt+tab', 'win+r')

        Returns:
            Komunikat o wyniku operacji

        Raises:
            pyautogui.FailSafeException: Jeśli mysz zostanie przesunięta do (0,0)
        """
        try:
            if not keys:
                return "❌ Brak klawiszy do naciśnięcia"

            # Parsuj klawisze
            key_list = [k.strip().lower() for k in keys.split("+")]

            logger.info(f"Wykonywanie skrótu: {keys}")

            # Wykonaj hotkey
            self.pg.hotkey(*key_list)

            # Czekaj safety delay
            time.sleep(self.safety_delay)

            return f"✅ Wykonano skrót: {keys}"

        except self.pg.FailSafeException:
            error_msg = "🛑 FAIL-SAFE AKTYWOWANY! Mysz przesunięta do (0,0) - operacja przerwana"
            logger.warning(error_msg)
            return error_msg
        except Exception as e:
            error_msg = f"❌ Błąd podczas wykonywania skrótu '{keys}': {e}"
            logger.error(error_msg, exc_info=True)
            return error_msg

    @kernel_function(
        name="get_mouse_position",
        description="Zwraca aktualną pozycję kursora myszy.",
    )
    async def get_mouse_position(self) -> str:
        """
        Zwraca aktualną pozycję kursora myszy.

        Returns:
            Pozycja kursora w formacie "X,Y"
        """
        try:
            x, y = self.pg.position()
            return f"Pozycja myszy: ({x}, {y})"
        except Exception as e:
            error_msg = f"❌ Błąd podczas pobierania pozycji myszy: {e}"
            logger.error(error_msg)
            return error_msg

    @kernel_function(
        name="take_screenshot",
        description="Robi zrzut ekranu i zwraca jego wymiary.",
    )
    async def take_screenshot(
        self,
        region: Annotated[
            Optional[str],
            "Opcjonalny region w formacie 'x,y,width,height' lub None dla całego ekranu",
        ] = None,
    ) -> str:
        """
        Robi zrzut ekranu.

        Args:
            region: Opcjonalny region (x,y,width,height) lub None

        Returns:
            Komunikat z informacją o zrzucie
        """
        try:
            if region:
                # Parsuj region
                parts = [int(p.strip()) for p in region.split(",")]
                if len(parts) != 4:
                    return "❌ Region musi być w formacie: x,y,width,height"

                screenshot = self.pg.screenshot(region=tuple(parts))
            else:
                screenshot = self.pg.screenshot()

            width, height = screenshot.size
            logger.info(f"Zrobiono zrzut ekranu: {width}x{height}")

            return f"✅ Zrzut ekranu: {width}x{height} pikseli"

        except Exception as e:
            error_msg = f"❌ Błąd podczas robienia zrzutu: {e}"
            logger.error(error_msg)
            return error_msg

    def _validate_coordinates(self, x: int, y: int) -> bool:
        """
        Waliduje współrzędne.

        Args:
            x: Współrzędna X
            y: Współrzędna Y

        Returns:
            True jeśli współrzędne są prawidłowe
        """
        # Współrzędne ekranu są 0-based: (0,0) do (width-1, height-1)
        # Używamy >= dla górnej granicy aby wykluczyć wartości równe width/height
        if x < 0 or x >= self.screen_width:
            logger.warning(f"X poza zakresem: {x} (zakres: 0-{self.screen_width - 1})")
            return False

        if y < 0 or y >= self.screen_height:
            logger.warning(f"Y poza zakresem: {y} (zakres: 0-{self.screen_height - 1})")
            return False

        return True

    def get_screen_size(self) -> tuple[int, int]:
        """
        Zwraca rozmiar ekranu.

        Returns:
            Tuple (width, height)
        """
        return (self.screen_width, self.screen_height)
