# Ghost Agent - Visual GUI Automation (Task 032)

## 🎯 Przegląd

Ghost Agent (Upiór) to rewolucyjna funkcja Venom umożliwiająca **fizyczną interakcję z interfejsem systemu operacyjnego**. Agent "opętuje" kursor myszy i klawiaturę, aby wykonywać zadania w aplikacjach, które nie posiadają API (np. Spotify, Excel, Photoshop, legacy software).

## 🏗️ Architektura

### Komponenty

1. **VisionGrounding** (`venom_core/perception/vision_grounding.py`)
   - Lokalizacja elementów UI na podstawie opisów wizualnych
   - Obsługa GPT-4o Vision (OpenAI) lub fallback do OCR
   - Zwraca współrzędne (x, y) znalezionego elementu

2. **InputSkill** (`venom_core/execution/skills/input_skill.py`)
   - Kontrola myszy (klikanie, podwójne kliknięcie, ruch)
   - Kontrola klawiatury (pisanie, skróty klawiszowe)
   - **Zabezpieczenia Fail-Safe** (PyAutoGUI)

3. **GhostAgent** (`venom_core/agents/ghost_agent.py`)
   - Agent RPA z pętlą OODA (Observe-Orient-Decide-Act)
   - Planowanie i wykonywanie sekwencji akcji
   - Generowanie raportów z wykonanych zadań

4. **DesktopSensor** (rozszerzony)
   - Tryb nagrywania akcji użytkownika
   - Replay/makra dla GhostAgent

## 🔐 Bezpieczeństwo

### PyAutoGUI Fail-Safe
**KRYTYCZNE:** Ghost Agent ma wbudowane zabezpieczenie:
- Ruch myszy do rogu ekranu **(0, 0)** NATYCHMIAST przerywa wszystkie operacje
- Fail-Safe jest **ZAWSZE AKTYWNY** i nie można go wyłączyć
- To mechanizm ochronny przed niekontrolowanym działaniem agenta

### Inne zabezpieczenia
- Walidacja współrzędnych (sprawdzanie czy nie wykraczają poza ekran)
- Opóźnienia między akcjami (domyślnie 0.5s)
- Logowanie wszystkich operacji
- Limit maksymalnej liczby kroków (domyślnie 20)
- Emergency Stop API

## 📝 Konfiguracja

W pliku `.env` lub `config.py`:

```python
# Ghost Agent (Visual GUI Automation)
ENABLE_GHOST_AGENT = False  # Włącz Ghost Agent
ENABLE_GHOST_API = False  # Włącz publiczne endpointy API /api/v1/ghost/*
GHOST_MAX_STEPS = 20  # Maksymalna liczba kroków
GHOST_STEP_DELAY = 1.0  # Opóźnienie między krokami (sekundy)
GHOST_VERIFICATION_ENABLED = True  # Weryfikacja po każdym kroku
GHOST_SAFETY_DELAY = 0.5  # Opóźnienie bezpieczeństwa
GHOST_VISION_CONFIDENCE = 0.7  # Próg pewności dla vision grounding
GHOST_RUNTIME_PROFILE = "desktop_safe"  # desktop_safe|desktop_power
GHOST_CRITICAL_FAIL_CLOSED = True  # Blokuj fallback kliknięć na ścieżkach krytycznych

# OpenAI API (opcjonalne, dla vision grounding)
OPENAI_API_KEY = "sk-..."  # Jeśli chcesz używać GPT-4o Vision
```

### Profile runtime

- `desktop_safe`:
  - konserwatywne limity,
  - włączona weryfikacja kroków,
  - fail-closed dla akcji krytycznych.
- `desktop_power`:
  - wyższa przepustowość domyślna,
  - szybsze tempo kroków,
  - możliwość użycia fallback przy braku trafienia vision.

### Governance i audit

- Mutacje desktop w `InputSkill` (`mouse_click`, `keyboard_type`, `keyboard_hotkey`) są chronione gate policy autonomii.
- Runtime Ghost i API publikują kanoniczne wpisy audytu:
  - akcje desktop: `source=core.ghost`,
  - kontrola API: `source=api.ghost`.

## 🚀 Przykłady Użycia

### Przykład 1: Otwórz Notatnik i napisz tekst

```python
from venom_core.agents.ghost_agent import GhostAgent
from venom_core.execution.kernel_builder import KernelBuilder

# Zbuduj kernel
kernel = KernelBuilder().build()

# Utwórz Ghost Agent
ghost = GhostAgent(
    kernel=kernel,
    max_steps=20,
    step_delay=1.0,
)

# Wykonaj zadanie
result = await ghost.process("Otwórz notatnik i napisz 'Hello Venom'")
print(result)
```

**Wyjście:**
```
📊 RAPORT GHOST AGENT
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Wykonane kroki: 7
Udane: 7 ✅
Nieudane: 0 ❌

SZCZEGÓŁY:
1. ✅ Otwórz dialog Run
   → ✅ Wykonano skrót: win+r
2. ✅ Czekaj na otwarcie
   → Oczekiwano 1.0s
3. ✅ Wpisz 'notepad'
   → ✅ Wpisano tekst (7 znaków)
4. ✅ Naciśnij Enter
   → ✅ Wykonano skrót: enter
5. ✅ Czekaj na notatnik
   → Oczekiwano 2.0s
6. ✅ Wpisz tekst: Hello Venom
   → ✅ Wpisano tekst (12 znaków)
```

### Przykład 2: Włącz następną piosenkę w Spotify

```python
result = await ghost.process("Włącz następną piosenkę w Spotify")
```

**Jak to działa:**
1. Ghost robi screenshot ekranu
2. VisionGrounding lokalizuje przycisk "Next" w Spotify
3. InputSkill klika w znaleziony przycisk
4. Muzyka się zmienia ✅

### Przykład 3: Użycie InputSkill bezpośrednio

```python
from venom_core.execution.skills.input_skill import InputSkill

input_skill = InputSkill(safety_delay=0.5)

# Kliknij w punkt (500, 300)
await input_skill.mouse_click(x=500, y=300)

# Wpisz tekst
await input_skill.keyboard_type("Hello World", interval=0.1)

# Wykonaj skrót Ctrl+S
await input_skill.keyboard_hotkey("ctrl+s")

# Pobierz pozycję myszy
position = await input_skill.get_mouse_position()
print(position)  # "Pozycja myszy: (500, 300)"
```

### Przykład 4: Vision Grounding

```python
from venom_core.perception.vision_grounding import VisionGrounding
from PIL import ImageGrab

vision = VisionGrounding()

# Zrób screenshot
screenshot = ImageGrab.grab()

# Znajdź element
coords = await vision.locate_element(
    screenshot,
    description="zielony przycisk Zapisz"
)

if coords:
    x, y = coords
    print(f"Element znaleziony: ({x}, {y})")
else:
    print("Element nie znaleziony")
```

### Przykład 5: `vision_click` i polityka fallback

```python
# Tryb safe: fail-closed gdy description nie zostanie znaleziony
ghost.apply_runtime_profile("desktop_safe")
await ghost.vision_click(
    description="niebieski przycisk Submit",
    fallback_coords=(500, 300),
)

# Tryb power: fallback może zostać użyty przy braku locate
ghost.apply_runtime_profile("desktop_power")
await ghost.vision_click(
    description="niebieski przycisk Submit",
    fallback_coords=(500, 300),
    require_visual_confirmation=False,
)
```

### Kontrakt API Ghost (feature-flagged)

Gdy `ENABLE_GHOST_API=True` i `ENABLE_GHOST_AGENT=True`:

- `GET /api/v1/ghost/status` - status runtime i wykonania
- `POST /api/v1/ghost/start` - start zadania Ghost w tle
- `POST /api/v1/ghost/cancel` - anulowanie aktywnego zadania (emergency stop)

## 🧪 Testowanie

Uruchom testy:

```bash
# Wszystkie testy Ghost Agent
pytest tests/test_ghost_agent.py -v

# Testy InputSkill
pytest tests/test_input_skill.py -v

# Testy VisionGrounding
pytest tests/test_vision_grounding.py -v

# Wszystkie testy razem
pytest tests/test_ghost_agent.py tests/test_input_skill.py tests/test_vision_grounding.py -v
```

**Wyniki:**
- 42 testy jednostkowe i integracyjne
- 100% passing rate ✅

## ⚠️ Ograniczenia i Znane Problemy

1. **Wymaga GUI Environment:**
   - Ghost Agent nie działa w środowiskach headless (bez X11/Wayland)
   - Testy używają mocków aby działać w CI/CD

2. **Vision Grounding:**
   - Wymaga OpenAI API key dla najlepszych rezultatów
   - Fallback OCR (pytesseract) ma ograniczoną dokładność
   - Florence-2 nie jest jeszcze zaimplementowane (TODO)

3. **DPI Scaling:**
   - Na systemach z skalowaniem DPI mogą wystąpić przesunięcia współrzędnych
   - TODO: Automatyczne wykrywanie i kompensacja DPI

4. **Wydajność:**
   - Analiza obrazu przez GPT-4o Vision trwa 2-5 sekund
   - Ghost Agent jest wolniejszy niż człowiek (celowo, dla bezpieczeństwa)

## 🔮 Przyszłe Usprawnienia

### Planowane na kolejne iteracje:

1. **Florence-2 Integration**
   - Lokalny model vision dla offline action
   - Szybsza lokalizacja elementów (< 1s)

2. **DPI Auto-Compensation**
   - Automatyczne wykrywanie i kompensacja skalowania

3. **Recording & Replay**
   - Nagrywanie sekwencji akcji użytkownika
   - Generalizacja do procedur/makr

4. **Dashboard Update**
   - Remote Control UI w przeglądarce
   - Live streaming pulpitu (MJPEG)
   - Emergency Stop button

5. **Advanced Planning**
   - LLM-based action planning
   - Multi-step reasoning dla złożonych zadań

## 📚 API Reference

### GhostAgent

```python
class GhostAgent(BaseAgent):
    def __init__(
        kernel: Kernel,
        max_steps: int = 20,
        step_delay: float = 1.0,
        verification_enabled: bool = True
    )

    async def process(input_text: str) -> str
    async def vision_click(
        description: str,
        fallback_coords: tuple[int, int] | None = None
    ) -> Dict[str, Any]
    def apply_runtime_profile(profile: str) -> Dict[str, Any]
    def emergency_stop_trigger() -> None
    def get_status() -> Dict[str, Any]
```

### InputSkill

```python
class InputSkill:
    @kernel_function
    async def mouse_click(x: int, y: int, button: str = "left", double: bool = False) -> str

    @kernel_function
    async def keyboard_type(text: str, interval: float = 0.05) -> str

    @kernel_function
    async def keyboard_hotkey(keys: str) -> str

    @kernel_function
    async def get_mouse_position() -> str

    @kernel_function
    async def take_screenshot(region: Optional[str] = None) -> str
```

### VisionGrounding

```python
class VisionGrounding:
    async def locate_element(
        screenshot: Image.Image,
        description: str,
        confidence_threshold: float = 0.7
    ) -> Optional[Tuple[int, int]]

    def load_screenshot(path_or_bytes) -> Image.Image
```

## 🤝 Współtworzenie

Ghost Agent jest częścią projektu Venom. Zachęcamy do:
- Zgłaszania Issues z problemami/propozycjami
- Pull Requests z usprawnieniami
- Testowania i raportowania błędów

## 📄 Licencja

Zobacz główny plik LICENSE projektu Venom.

---

**Uwaga:** Ghost Agent to potężne narzędzie. Używaj odpowiedzialnie i zawsze testuj w bezpiecznym środowisku przed uruchomieniem na produkcji.
