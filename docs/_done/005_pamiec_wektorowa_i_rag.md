# ZADANIE: 005_THE_HIPPOCAMPUS (Pamięć Wektorowa i RAG)

**Priorytet:** Krytyczny
**Kontekst:** Warstwa Pamięci (Memory Layer)
**Cel:** Implementacja pamięci długotrwałej opartej na wektorach (RAG). Venom ma zapamiętywać informacje (dokumentację, notatki, fragmenty kodu) i przywoływać je, gdy są potrzebne do zadania.

---

## 1. Kontekst Biznesowy
Obecnie Venom działa tylko w oparciu o "pamięć krótkotrwałą" (okno kontekstowe rozmowy). Jeśli rozmowa się kończy, wiedza przepada.
Celem tego zadania jest wdrożenie "Hipokampu" – systemu, który:
1. Zamienia tekst na liczby (Embeddingi).
2. Przechowuje je w lokalnej bazie wektorowej (LanceDB).
3. Pozwala agentom wyszukiwać informacje semantycznie (np. zapytanie "jak obsługujemy błędy?" znajdzie odpowiedni fragment w `CONTRIBUTING.md`, nawet jeśli słowa nie są identyczne).

---

## 2. Zakres Prac (Scope)

### A. Serwis Embeddingów (`venom_core/memory/embedding_service.py`)
*Utwórz nowy plik.* Klasa odpowiedzialna za zamianę tekstu na wektory.
* **Logika Hybrydowa (zgodna z configiem):**
  - Jeśli `LLM_SERVICE_TYPE == "openai"` → użyj `OpenAITextEmbeddingGeneration`.
  - Jeśli `LLM_SERVICE_TYPE == "local"` → użyj modelu lokalnego (np. `sentence-transformers/all-MiniLM-L6-v2`) lub endpointu Ollama `/api/embeddings`.
* **Cache:** Implementacja prostego cache'owania w pamięci, aby nie generować wektorów dla tego samego tekstu wielokrotnie.

### B. Baza Wektorowa (`venom_core/memory/vector_store.py`)
Zaimplementuj logikę w istniejącym pliku.
* Użyj biblioteki **LanceDB** (jest w `requirements.txt`).
* Klasa `VectorStore`:
  - `__init__`: Inicjalizacja bazy w katalogu `data/memory/lancedb`.
  - `upsert(text: str, metadata: dict)`: Zapisanie fragmentu tekstu.
  - `search(query: str, limit: int = 3)`: Wyszukiwanie najbardziej podobnych fragmentów.
  - `create_collection(name: str)`: Tworzenie tabel/kolekcji (np. "documentation", "code_snippets").

### C. Umiejętność Pamięci (`venom_core/memory/memory_skill.py`)
Stwórz plugin (Skill) dla Semantic Kernel, aby agenci mogli używać pamięci.
* Metody `@kernel_function`:
  - `recall(query: str)`: Przeszukuje bazę wiedzy i zwraca relewantne fragmenty.
  - `memorize(content: str, category: str)`: Zapisuje informację do pamięci.

### D. Integracja z Agentami
* **ChatAgent:** Wyposaż go w `MemorySkill`. Zaktualizuj prompt, aby przed odpowiedzią sprawdzał, czy w pamięci nie ma informacji na dany temat (RAG).
* **LibrarianAgent:** Dodaj mu funkcję "indeksowania" – gdy czyta plik (`read_file`), powinien mieć możliwość (lub automatycznie to robić) zapisania jego treści do wektorów, aby `CoderAgent` mógł go później znaleźć semantycznie.

### E. API Ingestion (`venom_core/main.py`)
* Dodaj endpoint `POST /api/v1/memory/ingest`:
  - Przyjmuje tekst lub plik.
  - Kroi go na kawałki (chunking).
  - Zapisuje w `VectorStore`.
  - To pozwoli "karmić" Venoma dokumentacją.

---

## 3. Kryteria Akceptacji (Definition of Done)

1.  ✅ **Zapis Wiedzy:**
    * Wysłanie tekstu "Zasady projektu Venom: Kod musi być po polsku" do endpointu ingestion lub przez funkcję `memorize` zapisuje wektor w LanceDB.
2.  ✅ **Przywoływanie (Recall):**
    * Zadanie *"Jakim językiem piszemy w projekcie?"* powoduje, że Venom najpierw przeszukuje pamięć, znajduje powyższą zasadę i odpowiada: *"W projekcie Venom piszemy po polsku"* (mimo że w prompcie systemowym mogło tego nie być).
3.  ✅ **Lokalność:**
    * Cały proces (embeddingi + baza) działa offline, jeśli w configu ustawiono tryb local.
4.  ✅ **Persystencja:**
    * Po restarcie aplikacji Venom nadal pamięta to, co zostało zapisane (baza LanceDB jest na dysku).
5.  ✅ **Testy:**
    * Testy jednostkowe dla `VectorStore` (zapis/odczyt).
    * Test integracyjny RAG: Zapisz fakt -> Zapytaj o fakt -> Sprawdź czy odpowiedź go zawiera.

---

## 4. Wskazówki Techniczne
* **Chunking:** Nie wrzucaj całych plików do bazy. Podziel tekst na fragmenty po np. 500 tokenów/znaków z lekkim zakładkami (overlap).
* **LanceDB:** Jest bardzo lekkie i nie wymaga osobnego procesu serwera (embedded DB).
* **Sentence Transformers:** Do testów lokalnych użyj `all-MiniLM-L6-v2` – jest mały, szybki i wystarczająco dobry do prostego RAG.
