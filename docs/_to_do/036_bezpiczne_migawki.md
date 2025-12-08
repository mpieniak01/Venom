# ZADANIE: 036_THE_CHRONOMANCER (Universal State Management & Timeline Branching)

**Priorytet:** Strategiczny (Reliability & Experimentation)
**Kontekst:** Warstwa Meta-Zarządzania (nad Pamięcią i Infrastrukturą)
**Cel:** Wdrożenie systemu kompletnego zarządzania stanem projektu ("Time Travel"). Venom ma potrafić stworzyć migawkę (Snapshot) całego środowiska (Kod + Pamięć DB + Konfiguracja Docker), bezpiecznie eksperymentować na "alternatywnej linii czasu", a w razie porażki – błyskawicznie przywrócić stan sprzed błędu.

---

## 1. Kontekst Biznesowy
**Problem:** Gdy Venom ("The Executive") realizuje złożony plan, jedna pomyłka w kroku 10 może zniweczyć pracę z kroków 1-9. Git cofa tylko kod, ale nie cofa "wiedzy" zdobytej przez agentów ani danych w bazie PostgreSQL uruchomionej w Dockerze.
**Rozwiązanie:** Przed każdą ryzykowną akcją Venom tworzy "Punkt Kontrolny". Jeśli eksperyment (np. "Refaktoryzacja całego modułu Core") się nie uda, Venom wykonuje `timeline.rollback()` i system wraca do stanu idealnego.

---

## 2. Zakres Prac (Scope)

### A. Silnik Czasu (`venom_core/core/chronos.py`)
*Utwórz nowy moduł.* Zarządca migawek.
* **Struktura Snapshotu:** Katalog w `data/timelines/{id}/` zawierający:
    - `fs_diff.patch`: Różnice w plikach (bazując na Git).
    - `memory_dump.zip`: Kopia bazy LanceDB/GraphStore.
    - `agent_state.json`: Zrzut pamięci krótkotrwałej wszystkich agentów.
    - `env_config.json`: Stan zmiennych środowiskowych i aktywnych kontenerów.
* **API:**
    - `create_checkpoint(name: str) -> str`: Tworzy snapshot.
    - `restore_checkpoint(id: str)`: Przywraca system do stanu X (zatrzymuje kontenery, podmienia bazę, resetuje kontekst agentów).

### B. Agent Historyk (`venom_core/agents/historian.py`)
*Nowy agent.*
* **Rola:** Zarządzanie ryzykiem i przyczynowością.
* **Decyzje:**
    - Przed wykonaniem polecenia `CoreSkill.hot_patch` (PR 021) lub dużym `Migration`, Historyk nakazuje: *"Zalecam utworzenie punktu przywracania."*
* **Analiza:** Po błędzie analizuje różnicę między "Przed" a "Po" i aktualizuje `LessonsStore` (PR 009), aby uniknąć tego w przyszłości.

### C. Umiejętność Czasowa (`venom_core/execution/skills/chrono_skill.py`)
*Narzędzie dla Rady (Council).*
* **Metody (@kernel_function):**
    - `branch_timeline(name: str)`: Tworzy nową gałąź eksperymentalną (nie tylko Git branch, ale osobny namespace w bazie wiedzy!).
    - `merge_timeline(source: str, target: str)`: (Zaawansowane) Próbuje scalić wiedzę i kod z dwóch rzeczywistości.

### D. Integracja z "The Dreamer" (PR 035)
* Sny nie powinny zaśmiecać głównej pamięci.
* Zmodyfikuj `DreamEngine`, aby każdy sen odbywał się na **Tymczasowej Linii Czasu**.
* Tylko jeśli sen zakończy się sukcesem, wiedza jest "merge'owana" do głównego nurtu (Main Timeline).

### E. Dashboard Update: "Timeline Visualizer"
* Widok drzewa (jak w serialu *Loki* lub kliencie Git).
* Węzły to Checkpointy.
* Możliwość kliknięcia "Jump here" – system wykonuje restart i przywraca dany stan.

---

## 3. Kryteria Akceptacji (DoD)

1.  ✅ **Pełny Rollback:**
    * Stan początkowy: W bazie wiedzy jest wpis A, plik ma wersję v1.
    * Akcja: Venom tworzy checkpoint "Start".
    * Zmiana: Venom dodaje wpis B do bazy i zmienia plik na v2.
    * Rollback: Przywracamy "Start".
    * Wynik: Baza nie ma wpisu B, plik jest v1. Agenci nie pamiętają, że w ogóle robili zmianę.
2.  ✅ **Izolacja Eksperymentu:**
    * Użytkownik: *"Sprawdź na osobnej linii czasu, co się stanie, jak usunę wszystkie testy"*.
    * Venom tworzy timeline, usuwa testy, sprawdza (błąd), wraca do main. Główny projekt pozostaje nienaruszony.
3.  ✅ **Szybkość:**
    * Tworzenie snapshotu (przy wykorzystaniu hardlinków lub mechanizmów systemowych) trwa < 5 sekund.

---

## 4. Wskazówki Techniczne
* **LanceDB Backup:** To baza plikowa, więc wystarczy szybka kopia folderu (użyj `shutil.copytree` lub `rsync`).
* **Docker:** Nie snapshotoj całych obrazów Docker (za ciężkie). Zapisuj tylko konfigurację (`docker-compose.yml` + `.env`) i wolumeny (jeśli to możliwe, lub zrzuty SQL).
* **Git Worktree:** Do obsługi wielu linii czasu w systemie plików, rozważ użycie `git worktree` – pozwala to mieć fizycznie wycheckoutowane dwa branche w różnych folderach jednocześnie.
