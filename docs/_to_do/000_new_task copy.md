# ZADANIE: 006_PERCEPTION_AND_QUALITY (Oczy i Krytyk)

**Kontekst:** Warstwa Percepcji (Perception Layer) i Agentów (Agents Layer)
**Cel:** Przekształcenie Venoma z systemu tekstowego w system multimodalny (widzący) oraz wdrożenie pętli samokorekty kodu (Code Review).

---

## 1. Kontekst Biznesowy
Obecnie Venom jest "ślepy" – jeśli użytkownik ma błąd w GUI, musi go opisać słowami. Dodatkowo, Venom jest "bezkrytyczny" – kod wygenerowany przez Codera trafia od razu do użytkownika, często z błędami, które łatwo wyłapać w review.
Celem tego zadania jest:
1. Danie Venomowi "Oczu" (obsługa obrazów/screenshotów).
2. Uruchomienie "Sumienia" (Policy Engine) i "Krytyka" (Critic Agent), aby kod był bezpieczny i wysokiej jakości.

---

## 2. Zakres Prac (Scope)

### A. Warstwa Percepcji (`venom_core/perception/eyes.py`)
Zaimplementuj klasę `Eyes` obsługującą analizę obrazu.
* **Integracja Hybrydowa:**
  - **Local:** Jeśli dostępny jest lokalny model Vision (np. LLaVA przez Ollama/ONNX), użyj go do opisu obrazu.
  - **Cloud:** Jeśli skonfigurowano OpenAI, użyj modelu `gpt-4o` do analizy wizualnej.
* **Funkcjonalność:**
  - Metoda `analyze_image(image_path_or_base64: str, prompt: str) -> str`.
  - Powinna potrafić odczytać kod ze zrzutu ekranu lub zidentyfikować błąd na screenie terminala.

### B. Agent Krytyk (`venom_core/agents/critic.py`)
Ożyw pusty plik agenta.
* **Rola:** Senior Developer / QA. Nie pisze kodu, tylko go ocenia.
* **Narzędzia:** Dostęp do `PolicyEngine` (sprawdzanie bezpieczeństwa).
* **Prompt Systemowy:** Skoncentrowany na wykrywaniu błędów logicznych, luk bezpieczeństwa (hardcoded credentials) i braku typowania.
* **Input:** Kod wygenerowany przez CoderAgenta + wymagania użytkownika.
* **Output:** Lista poprawek lub "APPROVED".

### C. Silnik Polityk (`venom_core/core/policy_engine.py`)
Zaimplementuj logikę weryfikacji zgodności (Compliance).
* Metoda `check_safety(content: str) -> List[Violation]`.
* **Reguły (Regex/Logic):**
  - Blokuj klucze API w kodzie (np. `sk-proj-...`).
  - Blokuj niebezpieczne komendy shell (np. `rm -rf /`).
  - Wymuszaj obecność Docstringów.

### D. Aktualizacja Orchestratora (Pętla Refleksji)
To największa zmiana w logice (`venom_core/core/orchestrator.py`).
* Zmień przepływ z liniowego na pętlę:
  1. `Dispatcher` wybiera `CoderAgent`.
  2. `CoderAgent` generuje kod.
  3. **NOWOŚĆ:** Orchestrator przekazuje wynik do `CriticAgent`.
  4. Jeśli Krytyk zgłasza uwagi -> Orchestrator wraca do `CoderAgent` z feedbackiem (maksymalnie 2 pętle naprawcze).
  5. Dopiero po akceptacji (lub wyczerpaniu limitu) wynik trafia do użytkownika.

### E. Obsługa Multimodalna w API (`venom_core/main.py`)
* Zaktualizuj endpoint `POST /api/v1/tasks`.
* Dodaj obsługę pola `images` (lista base64 lub URL) w `TaskRequest`.
* Przekaż obrazy do kontekstu Orchestratora.

---

## 3. Kryteria Akceptacji (Definition of Done)

1.  ✅ **Wizja:**
    * Przesłanie zrzutu ekranu z błędem w konsoli wraz z pytaniem "Jak to naprawić?" skutkuje poprawną diagnozą problemu widocznego na obrazku.
2.  ✅ **Code Review:**
    * Próba wygenerowania kodu z "hardcodowanym hasłem" zostaje zatrzymana przez `PolicyEngine` lub `CriticAgent`, a finalny kod używa zmiennych środowiskowych.
3.  ✅ **Samonaprawa:**
    * W logach widać, że Coder wygenerował kod, Krytyk go odrzucił, Coder poprawił, i dopiero wersja v2 trafiła do użytkownika.
4.  ✅ **Bezpieczeństwo:**
    * System wykrywa próby ataku (np. Prompt Injection w obrazku) dzięki warstwie Policy.
5.  ✅ **Testy:**
    * Test integracyjny pętli Coder-Critic (z mockowaniem odpowiedzi LLM, aby symulować błąd i poprawkę).

---

## 4. Wskazówki Techniczne
* **Obsługa Obrazów:** W Semantic Kernel dla Python obsługa obrazów w `ChatCompletion` wymaga odpowiedniego formatowania `ChatMessageContent` (z elementami `ImageContent`).
* **Vision Model:** Jeśli działasz lokalnie i nie masz mocnego GPU, możesz użyć mniejszego modelu (np. `moondream` lub `llava-phi3`) tylko do opisu obrazu (Image-to-Text), a tekst przekazać do głównego LLM. To oszczędza VRAM.
* **Pętla:** Uważaj na nieskończone pętle kłótni między Coderem a Krytykiem. Ustaw twardy limit iteracji (np. `MAX_REPAIR_ATTEMPTS = 2`).
