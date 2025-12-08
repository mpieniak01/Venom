"""
Moduł: demonstration_analyzer - Analizator Behawioralny (Behavioral Analyzer).

Odpowiedzialny za analizę nagranych demonstracji i transformację
surowych danych (piksele, kliki) na semantyczne kroki akcji.
"""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from PIL import Image

from venom_core.perception.recorder import DemonstrationSession, InputEvent
from venom_core.perception.vision_grounding import VisionGrounding
from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class ActionIntent:
    """Reprezentacja intencji akcji (semantyczny krok)."""

    action_type: str  # 'click', 'type', 'hotkey', 'wait'
    description: str  # Opis semantyczny (np. "Click blue Submit button")
    timestamp: float
    params: Dict[str, Any]
    confidence: float = 1.0


class DemonstrationAnalyzer:
    """
    Analizator Behawioralny - zamienia "piksele i kliki" na "intencje".

    Funkcjonalność:
    - Analiza sekwencji zdarzeń z sesji demonstracyjnej
    - Rozpoznawanie elementów UI na zrzutach ekranu
    - Transformacja współrzędnych na opisy semantyczne
    - Generowanie sekwencji kroków logicznych
    """

    def __init__(self):
        """Inicjalizacja DemonstrationAnalyzer."""
        self.vision_grounding = VisionGrounding()
        self.crop_size = 512  # Rozmiar crop'a wokół kursora

    async def analyze_session(
        self, session: DemonstrationSession
    ) -> List[ActionIntent]:
        """
        Analizuje sesję demonstracyjną i wyodrębnia intencje akcji.

        Args:
            session: Sesja demonstracyjna do analizy

        Returns:
            Lista ActionIntent (semantyczne kroki)
        """
        logger.info(f"Rozpoczynam analizę sesji: {session.session_id}")

        actions = []
        screenshots_dir = Path(session.screenshots_dir)

        # Filtruj tylko istotne zdarzenia (kliknięcia, wpisywanie tekstu)
        click_events = [
            e for e in session.events if e.event_type == "mouse_click" and e.data.get("pressed")
        ]

        key_sequences = self._extract_key_sequences(session.events)

        # Analizuj każde kliknięcie
        for event in click_events:
            intent = await self._analyze_click_event(event, screenshots_dir)
            if intent:
                actions.append(intent)

        # Analizuj sekwencje klawiszy
        for key_seq in key_sequences:
            intent = self._analyze_key_sequence(key_seq)
            if intent:
                actions.append(intent)

        # Sortuj według czasu
        actions.sort(key=lambda a: a.timestamp)

        logger.info(
            f"Analiza zakończona: {len(actions)} akcji z {len(session.events)} zdarzeń"
        )
        return actions

    async def _analyze_click_event(
        self, event: InputEvent, screenshots_dir: Path
    ) -> Optional[ActionIntent]:
        """
        Analizuje zdarzenie kliknięcia i rozpoznaje element UI.

        Args:
            event: Zdarzenie kliknięcia
            screenshots_dir: Katalog ze zrzutami ekranu

        Returns:
            ActionIntent lub None jeśli nie udało się rozpoznać
        """
        x = event.data["x"]
        y = event.data["y"]
        button = event.data.get("button", "left")

        # Znajdź najbliższy zrzut ekranu (przed kliknięciem)
        screenshot_path = self._find_nearest_screenshot(
            event.timestamp, screenshots_dir, before=True
        )

        if not screenshot_path:
            logger.warning(
                f"Brak zrzutu ekranu dla kliknięcia w czasie {event.timestamp}"
            )
            # Fallback do współrzędnych
            return ActionIntent(
                action_type="click",
                description=f"Click at ({x}, {y})",
                timestamp=event.timestamp,
                params={"x": x, "y": y, "button": button},
                confidence=0.3,
            )

        # Załaduj zrzut
        try:
            screenshot = Image.open(screenshot_path)
        except Exception as e:
            logger.error(f"Błąd ładowania zrzutu {screenshot_path}: {e}")
            return None

        # Wytnij fragment wokół kursora
        crop = self._crop_around_point(screenshot, x, y, self.crop_size)

        # Użyj VLM do rozpoznania elementu
        element_description = await self._describe_ui_element(crop, x, y)

        # Jeśli nie udało się rozpoznać, użyj współrzędnych
        if not element_description or element_description == "unknown":
            element_description = f"element at ({x}, {y})"
            confidence = 0.3
        else:
            confidence = 0.8

        return ActionIntent(
            action_type="click",
            description=f"Click {element_description}",
            timestamp=event.timestamp,
            params={
                "element_description": element_description,
                "fallback_coords": {"x": x, "y": y},
                "button": button,
            },
            confidence=confidence,
        )

    def _extract_key_sequences(self, events: List[InputEvent]) -> List[List[InputEvent]]:
        """
        Wyodrębnia sekwencje wpisywanych klawiszy.

        Args:
            events: Lista zdarzeń

        Returns:
            Lista sekwencji klawiszy (grupowanie po czasie)
        """
        key_events = [e for e in events if e.event_type == "key_press"]

        sequences = []
        current_seq = []
        last_time = 0.0
        max_gap = 2.0  # Maksymalna przerwa między klawiszami w sekwencji

        for event in key_events:
            if current_seq and (event.timestamp - last_time) > max_gap:
                # Nowa sekwencja
                if current_seq:
                    sequences.append(current_seq)
                current_seq = []

            current_seq.append(event)
            last_time = event.timestamp

        if current_seq:
            sequences.append(current_seq)

        return sequences

    def _analyze_key_sequence(
        self, key_sequence: List[InputEvent]
    ) -> Optional[ActionIntent]:
        """
        Analizuje sekwencję klawiszy.

        Args:
            key_sequence: Sekwencja zdarzeń klawiatury

        Returns:
            ActionIntent lub None
        """
        if not key_sequence:
            return None

        # Wyodrębnij klawisze
        keys = [e.data["key"] for e in key_sequence]

        # Sprawdź czy to skrót klawiszowy (np. Ctrl+S)
        if self._is_hotkey_sequence(keys):
            hotkey = "+".join(keys)
            return ActionIntent(
                action_type="hotkey",
                description=f"Press hotkey {hotkey}",
                timestamp=key_sequence[0].timestamp,
                params={"keys": keys},
                confidence=0.9,
            )

        # Jeśli to tekst, złącz klawisze
        text = self._keys_to_text(keys)

        if text:
            # Sprawdź czy to może być hasło (heurystyka)
            is_password = self._is_likely_password(text)

            return ActionIntent(
                action_type="type",
                description=f"Type text: {'***' if is_password else text[:50]}",
                timestamp=key_sequence[0].timestamp,
                params={"text": text, "is_sensitive": is_password},
                confidence=0.9,
            )

        return None

    def _is_hotkey_sequence(self, keys: List[str]) -> bool:
        """
        Sprawdza czy sekwencja klawiszy to skrót klawiszowy.

        Args:
            keys: Lista klawiszy

        Returns:
            True jeśli to skrót
        """
        modifier_keys = {"ctrl", "alt", "shift", "cmd", "win"}
        has_modifier = any(k.lower() in modifier_keys for k in keys)
        return has_modifier and len(keys) <= 3

    def _keys_to_text(self, keys: List[str]) -> str:
        """
        Konwertuje sekwencję klawiszy na tekst.

        Args:
            keys: Lista klawiszy

        Returns:
            Tekst
        """
        text = ""
        for key in keys:
            if len(key) == 1:
                text += key
            elif key == "space":
                text += " "
            elif key == "enter":
                text += "\n"
            # Inne specjalne klawisze możemy ignorować

        return text

    def _is_likely_password(self, text: str) -> bool:
        """
        Heurystyka: czy tekst wygląda na hasło.

        Args:
            text: Tekst do sprawdzenia

        Returns:
            True jeśli prawdopodobnie hasło
        """
        # Prosta heurystyka: brak spacji, zawiera cyfry i znaki specjalne
        has_no_spaces = " " not in text
        has_digits = any(c.isdigit() for c in text)
        has_special = any(not c.isalnum() for c in text)
        is_short = len(text) < 20

        return has_no_spaces and has_digits and has_special and is_short

    async def _describe_ui_element(
        self, crop: Image.Image, x: int, y: int
    ) -> Optional[str]:
        """
        Używa VLM do opisania elementu UI.

        Args:
            crop: Wycięty fragment obrazu
            x: Współrzędna X (dla kontekstu)
            y: Współrzędna Y (dla kontekstu)

        Returns:
            Opis elementu lub None
        """
        try:
            # Użyj VisionGrounding do analizy
            # Tutaj możemy użyć bardziej zaawansowanego promptu
            # np. "What UI element is in the center of this image?"

            # Prosty placeholder - w przyszłości można użyć Florence-2 lub LLaVA
            # do generowania opisów
            description = await self._simple_element_detection(crop)

            return description

        except Exception as e:
            logger.error(f"Błąd podczas opisywania elementu UI: {e}")
            return None

    async def _simple_element_detection(self, crop: Image.Image) -> str:
        """
        Prosta detekcja elementu (placeholder).

        W przyszłości: integracja z Florence-2, LLaVA itp.

        Args:
            crop: Fragment obrazu

        Returns:
            Opis elementu
        """
        # Placeholder - można rozbudować o:
        # 1. OCR do wykrywania tekstu na przyciskach
        # 2. Detekcja koloru dominującego
        # 3. Rozpoznawanie kształtów (przycisk vs pole tekstowe)

        # Na razie zwracamy generyczny opis
        return "UI element"

    def _crop_around_point(
        self, image: Image.Image, x: int, y: int, size: int
    ) -> Image.Image:
        """
        Wycina fragment obrazu wokół punktu.

        Args:
            image: Obraz źródłowy
            x: Współrzędna X środka
            y: Współrzędna Y środka
            size: Rozmiar crop'a (kwadrat)

        Returns:
            Wycięty fragment
        """
        half_size = size // 2
        left = max(0, x - half_size)
        top = max(0, y - half_size)
        right = min(image.width, x + half_size)
        bottom = min(image.height, y + half_size)

        return image.crop((left, top, right, bottom))

    def _find_nearest_screenshot(
        self, timestamp: float, screenshots_dir: Path, before: bool = True
    ) -> Optional[Path]:
        """
        Znajduje najbliższy zrzut ekranu do danego czasu.

        Args:
            timestamp: Czas zdarzenia
            screenshots_dir: Katalog ze zrzutami
            before: True - szukaj przed zdarzeniem, False - po

        Returns:
            Ścieżka do zrzutu lub None
        """
        if not screenshots_dir.exists():
            return None

        # Parsuj nazwy plików (screenshot_<timestamp>.png)
        screenshots = []
        for file in screenshots_dir.glob("screenshot_*.png"):
            try:
                # Wyodrębnij timestamp z nazwy
                match = re.search(r"screenshot_([\d.]+)\.png", file.name)
                if match:
                    ss_timestamp = float(match.group(1))
                    screenshots.append((ss_timestamp, file))
            except ValueError:
                continue

        if not screenshots:
            return None

        # Sortuj
        screenshots.sort(key=lambda x: x[0])

        # Znajdź najbliższy
        if before:
            # Szukaj ostatniego przed timestamp
            candidates = [s for s in screenshots if s[0] <= timestamp]
            if candidates:
                return candidates[-1][1]
        else:
            # Szukaj pierwszego po timestamp
            candidates = [s for s in screenshots if s[0] >= timestamp]
            if candidates:
                return candidates[0][1]

        # Jeśli nie znaleziono, zwróć najbliższy w ogóle
        if screenshots:
            closest = min(screenshots, key=lambda s: abs(s[0] - timestamp))
            return closest[1]

        return None

    def generate_workflow_summary(self, actions: List[ActionIntent]) -> str:
        """
        Generuje tekstowy opis workflow.

        Args:
            actions: Lista akcji

        Returns:
            Opis workflow
        """
        summary = f"Workflow składa się z {len(actions)} kroków:\n\n"

        for i, action in enumerate(actions, 1):
            summary += f"{i}. {action.description}\n"

        return summary
