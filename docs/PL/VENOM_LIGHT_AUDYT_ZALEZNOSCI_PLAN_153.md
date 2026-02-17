# 153. Venom Light: audyt ciężkich zależności i plan wdrożenia (API + Next + Gemma3)

Status: TO DO (analityczno-planistyczne, bez implementacji kodu)

## 1. Cel i decyzje docelowe

Ten dokument definiuje decyzjo-kompletny plan dla wariantu **Venom Light**.

Decyzje:
1. `venom light` = **FastAPI + Next.js + Ollama + Gemma3**.
2. `venom light` nie uruchamia i nie wymaga vLLM.
3. ONNX (`onnxruntime*`, `onnx`, `optimum`, `accelerate`) ma status **optional extra** poza domyślnym light.
4. `docker` SDK dla Pythona jest klasyfikowany funkcjonalnie (core vs optional) na podstawie audytu importów.
5. Model dystrybucji: **jedna paczka**, wybór wariantu instalacji/uruchomienia (`light`, `llm_off`, `full`).

## 2. As-Is (potwierdzenie stanu)

1. Istnieją profile zależności (`requirements.txt`, `requirements-docker-minimal.txt`, `requirements-ci-lite.txt`), ale semantyka runtime nie jest spójna z nazwami.
2. `compose/compose.minimal.yml` i Dockerfile backendu wspierają ścieżkę Ollama + Gemma3.
3. Profil runtime `light` jest obecnie semantycznie zbliżony do `llm_off` (niespójność względem docelowego onboardingu light).
4. ONNX i `docker` SDK mają różny profil kosztu i użycia, więc wymagają niezależnej decyzji.

## 3. Kontrakt To-Be profili runtime

1. `light`: backend + UI + Ollama (Gemma3), bez vLLM.
2. `llm_off`: backend + UI, bez LLM.
3. `full`: rozszerzony stack (w tym opcjonalnie vLLM i ścieżki heavy ML).

Wymagania semantyczne:
- jednoznaczne mapowanie profil -> usługi,
- jawne defaulty env (`OLLAMA_MODEL=gemma3:*`),
- zgodność kontraktu API runtime z dokumentacją i panelem konfiguracyjnym.

## 4. Macierz zależności (kierunkowa)

Klasy:
1. `core-light` – wymagane dla `light`.
2. `ml-heavy` – ciężkie ML poza default light.
3. `academy/habitat` – funkcje specjalistyczne.
4. `voice/onnx` – opcjonalne rozszerzenia inferencji.
5. `dev/test` – zależności developerskie i walidacyjne.

Statusy decyzyjne pakietów:
- `required` – konieczne dla startupu i działania core profile.
- `optional` – aktywowane tylko dla rozszerzeń.
- `excluded-from-light` – poza domyślnym light.

Kryteria decyzji:
- rozmiar obrazu,
- cold start,
- zużycie RAM,
- ryzyko operacyjne / utrzymaniowe,
- krytyczność dla ścieżki demo (chat + UI + Gemma przez Ollama).

## 5. Plan realizacji (fale/etapy, bez implementacji w tym issue)

### Faza 1 — audyt importów i ścieżek runtime
Deliverable:
- tabela `pakiet -> moduł -> ścieżka użycia -> krytyczność -> startup-critical (tak/nie)`.

Zakres:
1. mapowanie ciężkich pakietów z `requirements.txt` do modułów,
2. rozdzielenie importów startup-critical i lazy/optional,
3. weryfikacja, czy `docker` SDK jest wymagany w startupie `light`,
4. potwierdzenie braku wymogu DinD dla kontenera backendu light.

### Faza 2 — macierz `core-light` vs `optional-extras`
Deliverable:
- macierz decyzyjna z uzasadnieniem dla `onnx*` i `docker`.

Zakres:
1. przypisanie pakietów do klastrów,
2. status `required/optional/excluded-from-light`,
3. uzasadnienie kosztowe i operacyjne.

### Faza 3 — projekt podziału artefaktów (jedna paczka, wiele wariantów)
Deliverable:
- spec implementacyjny do osobnego PR.

Zakres:
1. projekt docelowych plików zależności (bez edycji w tej fali),
2. warianty obrazów:
   - `venom-backend-light` (core-light),
   - `venom-backend-onnx` (light + ONNX extras),
   - opcjonalnie wariant academy/habitat,
3. zasady kompatybilności wstecznej i fallbacków,
4. jeden kanał instalacyjny i wybór profilu: `light` / `llm_off` / `full`.

### Faza 4 — migracja semantyki runtime profiles
Deliverable:
- plan migracji bez breaking changes.

Zakres:
1. uporządkowanie semantyki `light` vs `llm_off` vs `full`,
2. synchronizacja API runtime, panelu config i dokumentacji,
3. rollout z feature flagami i rollbackiem.

### Faza 5 — walidacja i metryki sukcesu
Deliverable:
- acceptance checklist + target metryk.

Metryki:
1. startup time,
2. RAM,
3. rozmiar obrazu,
4. czas gotowości usług.

Scenariusze:
1. smoke `compose.minimal` (backend/UI/ollama readiness),
2. demo chat na Gemma3 bez ONNX,
3. brak regresji `llm_off`,
4. potwierdzenie braku wymogu Docker Engine/CLI w kontenerze backendu light,
5. potwierdzenie wyboru profilu bez zmiany pakietu dystrybucyjnego.

## 6. Kryteria akceptacji

1. Jednoznaczna definicja `venom light` jako API + Next + Ollama + Gemma3 bez vLLM.
2. ONNX zdefiniowany jako optional extra poza default light.
3. `docker` SDK sklasyfikowany na podstawie realnych ścieżek użycia.
4. Plan wdrożenia decyzjo-kompletny i gotowy do realizacji w kolejnych PR.
5. Uwzględnione ryzyka, mitigacje i metryki sukcesu.
6. Potwierdzony model: jedna paczka, wiele profili instalacji/uruchomienia.

## 7. Ryzyka i mitigacje

1. Niejednoznaczność definicji `light`.
   - Mitigacja: jawny kontrakt profili i mapowanie usług.
2. Ukryte importy heavy deps w startup path.
   - Mitigacja: audyt importów + lazy loading + smoke testy.
3. Regresja runtime profile API/UI.
   - Mitigacja: testy kontraktowe + walidacja panelu konfiguracyjnego.
4. Rozjazd dokumentacji i implementacji.
   - Mitigacja: checklista synchronizacji docs i evidences w PR.

## 8. Kontrakt wykonawczy fal (Wave 0-5)

1. Wave 0: baseline i potwierdzenie niespójności `light` vs `llm_off`.
2. Wave 1: semantyka profili runtime.
3. Wave 2: zależności light bez psucia full-dev.
4. Wave 3: jedna paczka, wiele profili uruchomienia.
5. Wave 4: spójność dokumentacji operacyjnej EN/PL.
6. Wave 5: walidacja końcowa (build + smoke + profile).

Zasady:
1. Jeden PR = jedna fala.
2. Każdy PR opisuje IN/OUT, walidację i ryzyka.
3. PR kodowy uruchamia hard gates.
4. PR doc-only zawiera adnotację: **"doc-only change, hard gates skipped by policy"**.
