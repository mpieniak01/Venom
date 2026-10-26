# Głos i możliwości multimodalne silników

Aktualizacja: 2026-10-26.

## Chat głosowy

Ekran /voice nagrywa dźwięk w przeglądarce i przesyła go przez /ws/audio.
Wybór ścieżki wynika z aktywnego silnika i możliwości wybranego modelu:

- Modele Ollama deklarujące audio korzystają z ollama_audio_llm_piper, chyba że operator jawnie wybierze faster_whisper.
- Modele tekstowe korzystają z whisper_llm_piper.
- Osobny silnik multi_runtime zachowuje własną ścieżkę audio.

Ollama otrzymuje pełny kontener WAV zakodowany base64 w messages[].images. Tekst użytkownika jest pusty, a instrukcja transkrypcji trafia do osobnej wiadomości systemowej. Dane to mono PCM16, 16 kHz; inne częstotliwości nagrania są przeliczane. Nie zastępuj nagrania nazwą pliku, surowym PCM ani oczekiwaną transkrypcją.

Transkrypcja Ollama trafia do wspólnego mechanizmu rozmowy i autoryzacji dostawców, tak samo jak tekst z Whisper. Piper generuje odpowiedź głosową. Obsługa wejścia audio nie oznacza generowania audio przez model ani zgody na wykonanie polecenia. Wspólna kontrola dostępu do silnika pozostaje aktywna; zajęta generacja pozwala użyć Whisper do odczytania pilnego polecenia.

Status rozróżnia deklarację z metadanych od wykonanego przetwarzania nagrania. Zapytanie tekstowe nie potwierdza obsługi audio. Metadane sesji zapisują ścieżkę, transkrypcję, odpowiedź i czasy etapów. Błąd lub cisza kończą stan oczekiwania interfejsu bez wymyślania wypowiedzi.

Jakość rozpoznawania polskiego zależy od nagrania i wag. Po aktualizacji sprawdź prawdziwe próbki; samo przyjęcie żądania przez API nie potwierdza jakości transkrypcji.

## Role modeli i pamięć

Model codzienny pozostaje lekki, aby zachować VRAM na wizję. Lokalny profil zachowuje Gemma2:2b i adapter, większą Gemma4 do zadań multimodalnych oraz chińskie alternatywy eksperymentalne. Jednocześnie pracuje jeden silnik i jedna generacja LLM.

Neutralna rola code_generation domyślnie używa qwen2.5-coder:3b. FEEDBACK_LOOP_PRIMARY_MODEL i lista FEEDBACK_LOOP_FALLBACK_MODELS pozwalają zmieniać modele bez przypinania funkcji do ich rodzin. Budżety określają FEEDBACK_LOOP_MIN_RAM_GB, FEEDBACK_LOOP_MIN_VRAM_MB i FEEDBACK_LOOP_MAX_CONTEXT. Historyczny alias OpenCodeInterpreter-Qwen2.5-7B pozostaje odczytywany dla zgodności, bez wymagania instalacji modelu 7B.

Lokalny katalog wycofuje Codestral, tagi Ollama Gemma3 oraz Qwen2.5-Coder 7B. Wagi innych silników i adaptery treningowe pozostają zachowane.

## Weryfikacja

tests/test_ollama_voice_input.py sprawdza WAV, żądania i wybór ścieżki; testy czasów sesji w interfejsie sprawdzają raportowanie etapów. Odbiór działającego stosu wymaga dodatkowo rzeczywistego nagrania przez /ws/audio, sensownej transkrypcji i odpowiedzi oraz pliku audio Piper. Prywatne nagrania i surowe dowody sesji nie trafiają do Git.
