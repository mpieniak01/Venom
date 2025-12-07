# ZADANIE: 019_THE_AVATAR (Local Voice Interface & IoT Bridge)

**Priorytet:** Strategiczny (Human-Machine Interaction & IoT)
**Kontekst:** Warstwa Percepcji i Infrastruktury Fizycznej
**Cel:** Przekształcenie Venoma w asystenta głosowego (jak Jarvis), który działa w pełni lokalnie (STT/TTS na ONNX) i potrafi sterować urządzeniami zewnętrznymi (Rider-Pi / IoT) poprzez dedykowany most.

---

## 1. Kontekst Biznesowy
Do tej pory komunikacja z Venomem odbywała się przez klawiaturę. Jest to nieefektywne przy pracy warsztatowej lub gdy operator jest z dala od ekranu. Ponadto Venom jest odcięty od "ciała" (Rider-Pi).
Celem tego PR jest:
1.  **Voice Ops:** Możliwość wydawania komend głosowych ("Venom, zrób deploy na produkcji").
2.  **Voice Response:** Venom odpowiada syntezowanym głosem (szybka informacja zwrotna).
3.  **Physical Control:** Venom może włączyć/wyłączyć piny GPIO na zdalnym Raspberry Pi (np. zresetować router, zapalić diodę statusu).

---

## 2. Zakres Prac (Scope)

### A. Silnik Audio (Local-First)
*Utwórz moduł `venom_core/perception/audio_engine.py`.*
* **Słuch (STT):** Implementacja `WhisperSkill` przy użyciu `faster-whisper` (działa na CPU/GPU lokalnie).
    - Metoda `transcribe(audio_buffer) -> str`.
* **Mowa (TTS):** Implementacja `VoiceSkill` przy użyciu `piper-tts` (bardzo szybki, działa na ONNX) lub `coqui-tts`.
    - Metoda `speak(text: str) -> audio_stream`.
    - Obsługa kolejkowania (żeby Venom nie przerywał sam sobie).

### B. Most Sprzętowy (`venom_core/infrastructure/hardware_pi.py`)
Zastąp pusty plik pełną implementacją.
* **Protokół:** Komunikacja z fizycznym Raspberry Pi (Rider-Pi) poprzez SSH (`paramiko`) lub lekki agent HTTP (np. `pigpio`).
* **Klasa `HardwareBridge`:**
    - `connect(host: str)`: Nawiązuje połączenie.
    - `read_sensor(sensor_id: str)`: Pobiera dane (np. temperatura CPU Pi).
    - `set_gpio(pin: int, state: bool)`: Sterowanie fizyczne.

### C. Agent Operator (`venom_core/agents/operator.py`)
*Nowy agent specjalny.*
* **Rola:** Interfejs głosowo-sprzętowy.
* **Prompt Systemowy:** *"Jesteś interfejsem głosowym. Twoje odpowiedzi muszą być krótkie, treściwe i naturalne do wymówienia. Nie używaj markdowna ani bloków kodu w odpowiedziach głosowych."*
* **Logika:** Działa jako "filtr" dla innych agentów. Kiedy użytkownik pyta głosowo, Operator streszcza odpowiedź CoderAgenta do 2 zdań syntezy mowy.

### D. WebSocket Audio Stream (`venom_core/api/audio_stream.py`)
*Rozbudowa API.*
* Endpoint WebSocket `/ws/audio`:
    - Przyjmuje strumień audio (blob) z przeglądarki.
    - Odsyła strumień audio (syntezę) do odtworzenia.
    - Implementuje VAD (Voice Activity Detection), aby wiedzieć, kiedy użytkownik przestał mówić.

### E. Dashboard Update (`web/`)
* Dodaj tryb **"Voice Command Center"**:
    - Duży przycisk mikrofonu (Push-to-Talk lub Always-on).
    - Wizualizacja fali dźwiękowej (Audio Visualizer).
    - Panel statusu IoT (np. wskaźniki temperatury z Rider-Pi).

---

## 3. Kryteria Akceptacji (Definition of Done)

1.  ✅ **Rozmowa Głosowa:**
    * Mówisz do mikrofonu: *"Venom, jaki jest status repozytorium?"*.
    * Venom (STT) transkrybuje tekst.
    * Integrator sprawdza git.
    * Operator generuje skrót.
    * Venom (TTS) odpowiada głosem: *"Jesteśmy na branchu dev. Dwa pliki są zmodyfikowane."*
2.  ✅ **Sterowanie Sprzętem:**
    * Komenda: *"Uruchom procedurę awaryjną na Rider-Pi"*.
    * Venom przez `HardwareBridge` wysyła sygnał GPIO lub komendę SSH do Raspberry Pi.
3.  ✅ **Wydajność:**
    * Opóźnienie (Latency) od końca wypowiedzi użytkownika do początku odpowiedzi głosowej < 2 sekundy (na lokalnym GPU/dobrym CPU).
4.  ✅ **Bezpieczeństwo:**
    * Komendy sprzętowe są chronione (wymagane potwierdzenie lub whitelist).

---

## 4. Wskazówki Techniczne
* **Zależności:** `faster-whisper`, `sounddevice`, `numpy`. Upewnij się, że biblioteki systemowe (np. `libsndfile`) są dostępne w `Dockerfile`.
* **VAD (Voice Activity Detection):** Użyj `webrtcvad` lub `silero-vad`, aby nie wysyłać ciszy do Whispera.
* **Model ONNX:** Dla TTS użyj modeli `en_US-lessac-medium.onnx` (lub polskiego odpowiednika, jeśli dostępny w Piper), są lekkie i nie wymagają internetu.
* **Integracja z Council:** `OperatorAgent` powinien być częścią roju, ale mieć priorytet w obsłudze wejść audio.
