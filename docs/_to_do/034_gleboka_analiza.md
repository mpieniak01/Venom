# ZADANIE: 034_THE_ORACLE (Omni-Modal Ingestion & Deep Graph Reasoning)

**Priorytet:** Strategiczny (Advanced Intelligence & Knowledge Management)
**Kontekst:** Warstwa Pamięci i Analizy Danych
**Cel:** Przekształcenie systemu pamięci Venoma z prostego wyszukiwania wektorowego (VectorRAG) w zaawansowany silnik grafowy (GraphRAG). Dodanie obsługi "ciężkich" danych (PDF, DOCX, Video) oraz wdrożenie agenta "Wyroczni", który potrafi odpowiadać na pytania wymagające połączenia faktów z wielu źródeł.

---

## 1. Kontekst Biznesowy
**Problem:** Użytkownik wrzuca do folderu `./workspace` 100-stronicową dokumentację API w PDF i pyta: *"Jak zaimplementować autoryzację zgodnie z tą specyfikacją?"*. Obecny Venom (VectorRAG) znajdzie losowe fragmenty o "autoryzacji", ale zgubi kontekst struktury i zależności.
**Rozwiązanie:**
1.  **Omni-Ingest:** Venom OCR-uje PDFy, transkrybuje nagrania wideo i parsuje kod.
2.  **Knowledge Graph:** Buduje sieć pojęć (Entities) i relacji (Relationships).
3.  **Oracle Agent:** "Chodzi" po grafie, aby znaleźć odpowiedź, której nie ma wprost w żadnym pojedynczym akapicie.

---

## 2. Zakres Prac (Scope)

### A. Silnik Ingestii (`venom_core/memory/ingestion_engine.py`)
*Utwórz nowy moduł przetwarzania danych.*
* **Obsługa formatów:**
    - `PDF/DOCX`: Użyj `pypdf` lub `markitdown` (od Microsoft).
    - `Images`: Użyj `Florence-2` (z PR 032) do opisu obrazków/wykresów w dokumentach.
    - `Audio/Video`: Użyj `AudioEngine` (z PR 019) do transkrypcji.
* **Chunking Semantyczny:** Zamiast ciąć tekst co 500 znaków, dziel go logicznie (rozdziały, funkcje, klasy).

### B. Implementacja GraphRAG (`venom_core/memory/graph_rag_service.py`)
*Rozbudowa `GraphStore`.*
* **Ekstrakcja Wiedzy:**
    - Użyj LLM do wyciągnięcia trójek z tekstu: `(Podmiot, Relacja, Dopełnienie)`, np. `(Venom, JEST_TYPU, System AI)`.
* **Klastrowanie:**
    - Zgrupuj powiązane węzły w "Społeczności" (Communities), aby uzyskać hierarchiczny obraz wiedzy.
* **API:**
    - `global_search(query)`: Odpowiedź oparta na podsumowaniach klastrów (dobre do pytań "O czym jest ten projekt?").
    - `local_search(query)`: Odpowiedź oparta na sąsiedztwie węzłów (dobre do pytań "Kto stworzył moduł X?").

### C. Agent Wyrocznia (`venom_core/agents/oracle.py`)
*Nowy agent analityczny.*
* **Rola:** Deep Researcher & Analyst.
* **Workflow "Reasoning Loop":**
    1. Otrzymuje trudne pytanie.
    2. Generuje plan badawczy (jakie słowa kluczowe szukać w grafie).
    3. Eksploruje graf wiedzy (krok po kroku).
    4. Zbiera dowody (cytaty).
    5. Syntezuje odpowiedź z przypisami.

### D. Skill Badawczy (`venom_core/execution/skills/research_skill.py`)
*Update istniejącego skilla.*
* Dodaj metodę `digest_url(url: str)`: Pobiera stronę, czyści, przepuszcza przez Ingestię i dodaje do Grafu Wiedzy.
* Dodaj metodę `digest_file(path: str)`: To samo dla plików lokalnych.

### E. Dashboard Update: "Knowledge Explorer"
* Wizualizacja Grafu Wiedzy (użyj np. `vis.js` lub `cytoscape.js`).
* Interakcja: Kliknięcie w węzeł (np. "Docker") pokazuje wszystkie powiązane dokumenty i fakty, które Venom o nim wie.
* Dropzone: Przeciągnij i upuść plik PDF, aby Venom go "przeczytał".

---

## 3. Kryteria Akceptacji (DoD)

1.  ✅ **Analiza Dokumentacji:**
    * Wrzucasz plik PDF z instrukcją obsługi pralki.
    * Pytasz: *"Dlaczego miga czerwona dioda?"*.
    * Venom (Oracle) bezbłędnie wskazuje przyczynę na podstawie tabeli błędów w PDF.
2.  ✅ **Multi-hop Reasoning:**
    * Pytasz: *"Jaki jest związek między agentem `Ghost` a modułem `Florence-2`?"*.
    * Venom (korzystając z grafu) odpowiada: *"Agent Ghost używa Skill Input, który korzysta z Vision Grounding, który jest oparty na modelu Florence-2"*. (Mimo że te informacje są w 3 różnych plikach).
3.  ✅ **Persistent Knowledge:**
    * Wiedza z przetworzonych plików zostaje w bazie LanceDB/GraphStore po restarcie systemu.

---

## 4. Wskazówki Techniczne
* **Microsoft GraphRAG:** Projekt Microsoftu jest potężny, ale może być trudny do uruchomienia lokalnie w "lekkim" środowisku. Rozważ implementację uproszczoną: `Text -> LLM Extract (Nodes/Edges) -> NetworkX + VectorStore`.
* **Koszt Indeksowania:** Budowanie grafu zużywa dużo tokenów. Uruchamiaj proces indeksowania w tle (`Scheduler`) i używaj tańszego modelu (np. lokalny Mistral/Phi-3) do ekstrakcji trójek, a GPT-4o tylko do syntezy odpowiedzi.
* **LanceDB Hybrid Search:** LanceDB wspiera teraz wyszukiwanie hybrydowe (FTS + Vector). Wykorzystaj to w `GraphRagService`.
