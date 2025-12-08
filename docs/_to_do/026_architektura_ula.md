# ZADANIE: 026_THE_HIVE (Grid Computing, Task Queue & Swarm Synchronization)

**Priorytet:** Strategiczny (Performance & Scalability)
**Kontekst:** Warstwa Rozproszonego Przetwarzania
**Cel:** Przekształcenie luźno połączonych Zarodników (Spores) w jeden, zsynchronizowany superkomputer. Wdrożenie kolejki zadań (Redis), mechanizmu równoległego wykonywania (Parallel Execution) oraz zdalnych aktualizacji kodu (OTA Updates) dla węzłów.

---

## 1. Kontekst Biznesowy
**Problem:** Venom posiada wiele zasobów (Nexus + Spores), ale używa ich pojedynczo. Zadania długotrwałe (np. "przeskanuj całe repozytorium") blokują głównego agenta.
**Rozwiązanie:**
1.  **Rozdzielanie:** Architekt dzieli zadanie na 10 podzadań.
2.  **Dystrybucja:** Foreman (nowy agent) rozsyła je do wolnych Zarodników.
3.  **Agregacja:** Wyniki spływają do Nexusa i są scalane (MapReduce).
4.  **Utrzymanie:** Gdy Venom (Nexus) ewoluuje (PR 021), automatycznie aktualizuje kod wszystkich Zarodników (Over-The-Air Update).

---

## 2. Zakres Prac (Scope)

### A. Infrastruktura Kolejkowa (`venom_core/infrastructure/message_broker.py`)
*Wdrożenie `Redis`.*
* Zaktualizuj `StackManager` (PR 016), aby domyślny stack zawierał kontener `redis:alpine`.
* Zaimplementuj wrapper na kolejkę zadań (użyj lekkiej biblioteki `arq` lub `celery` dla async).
* **Kanały:**
    - `tasks_high_priority` (dla interakcji z userem).
    - `tasks_background` (dla scrapingu, treningu).
    - `broadcast_control` (dla komend systemowych do wszystkich węzłów).

### B. Agent Majster (`venom_core/agents/foreman.py`)
*Nowy agent.* Zarządca zasobów klastra.
* **Rola:** Load Balancer & Watchdog.
* **Zadania:**
    - Monitoruje obciążenie każdego Zarodnika (CPU/RAM).
    - Decyduje, gdzie wysłać zadanie (np. "Zarodnik #3 ma GPU, wyślij tam zadanie transkrypcji Whisper").
    - Wykrywa "zombie tasks" (zadania, które utknęły) i zleca je ponownie.

### C. Skill Równoległy (`venom_core/execution/skills/parallel_skill.py`)
*Narzędzie dla Architekta.*
* **Metoda `@kernel_function` `map_reduce(task_description: str, items: List[str])`**:
    1. **Map:** Tworzy N promtów/zadań dla każdego elementu z listy `items` (np. lista URLi).
    2. **Execute:** Wrzuca zadania do kolejki Redis.
    3. **Wait:** Czeka (asynchronicznie) na wyniki od Zarodników.
    4. **Reduce:** Przekazuje listę wyników do `ResearcherAgenta` w celu syntezy jednej odpowiedzi.

### D. System Aktualizacji OTA (`venom_core/core/ota_manager.py`)
*Propagacja Ewolucji (z PR 021).*
* **Mechanizm:**
    - Nexus wystawia endpoint HTTP z paczką kodu (zip) lub udostępnia serwer Git.
    - Na sygnał `UPDATE_SYSTEM` (przez Redis Pub/Sub), Zarodniki:
        1. Pobierają nowy kod.
        2. Instalują nowe zależności (`pip install`).
        3. Wykonują bezpieczny restart procesu (`venom-spore`).

### E. Dashboard Update: "Hive Monitor"
* Wizualizacja przepływu zadań (Task Queue length).
* Wykres "Cluster Throughput" (zadania na minutę).
* Matryca statusu (który węzeł co teraz robi).

---

## 3. Kryteria Akceptacji (DoD)

1.  ✅ **Masowe Przetwarzanie:**
    * Zadanie: *"Pobierz i stresuść te 20 artykułów"*.
    * Obserwacja: W logach widać, że 5 Zarodników pracuje jednocześnie, każdy przetwarza po 4 artykuły. Czas wykonania jest ~5x krótszy niż sekwencyjnie.
2.  ✅ **Globalna Pamięć Podręczna:**
    * Wynik pracy Zarodnika #1 (np. pobrany plik) jest dostępny dla Zarodnika #2 (poprzez współdzielony Redis Cache lub przesłanie wyniku).
3.  ✅ **Odporność na Awarię:**
    * Jeśli w trakcie pracy jeden Zarodnik zostanie wyłączony ("zabity"), Majster (Foreman) wykrywa timeout i przekazuje jego zadania innemu węzłowi.
4.  ✅ **Synchronizacja Wersji:**
    * Zmiana w `utils/helpers.py` na Nexusie po kliknięciu "Deploy to Hive" pojawia się na wszystkich podłączonych Zarodnikach w ciągu 30 sekund.

---

## 4. Wskazówki Techniczne
* **ARQ (Async Redis Queue):** Jest idealne dla FastAPI. Pozwala na łatwe definiowanie workerów.
* **Shared Storage:** Pamiętaj, że Zarodniki mogą nie mieć wspólnego systemu plików (mogą być w innej sieci). Dane wejściowe/wyjściowe zadań muszą być przesyłane w payloadzie zadania (JSON/Base64) lub linkowane (URL), a nie przez ścieżki lokalne (chyba że używasz NFS/S3, ale na start JSON wystarczy).
* **Idempotentność:** Zarodniki powinny być przygotowane na otrzymanie tego samego zadania dwa razy (w przypadku błędu sieci).
