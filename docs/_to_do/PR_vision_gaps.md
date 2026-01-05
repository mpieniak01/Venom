# PR: Odstępstwa od wizji (analiza stanu)

## Cel
Zebrać i doprecyzować kluczowe rozjazdy między wizją projektu a obecnym stanem, oraz przygotować decyzje/priorytety pod przyszłe PR-y.

## Kontekst
Źródła analizy:
- `README.md`
- `docs/VENOM_MASTER_VISION_V1.md`
- `docs/BACKEND_ARCHITECTURE.md`

## Odstępstwa wizja ↔ stan obecny
1. **Standard modeli ONNX**
   - Wizja: jeden standard runtime (ONNX) dla wszystkich modeli.
   - Stan: runtime LLM oparty o Ollama/vLLM + chmura; ONNX używany głównie w vision.

2. **Policy/ethics jako warstwa systemowa**
   - Wizja: Policy Engine jako globalny gate.
   - Stan: PolicyEngine używany głównie w `CriticAgent`, brak pełnego gate w Orchestratorze i UX.

3. **Rider‑Pi / integracja fizyczna**
   - Wizja: pełna warstwa „ciała” (telemetria, lifecycle, bezpieczeństwo).
   - Stan: moduły istnieją, ale brak spójnego pipeline’u operacyjnego i UI/ops.

4. **Samodoskonalenie jako zamknięta pętla**
   - Wizja: stały cykl task → kod → test → PR → memory → policy.
   - Stan: elementy są rozproszone (Forge/Healer/testy), brak domkniętego automatu.

## Luki funkcjonalne (meta‑inżynier)
1. **Jedno źródło prawdy dla wiedzy**
   - Brak zunifikowanego kontraktu: session history vs. lessons vs. vector store.

2. **Źródła i audyt zewnętrzny**
   - Brak wymuszonego policy/kontraktu na źródła (wymóg metadanych dla odpowiedzi).

3. **Feedback polityk w UX**
   - Brak jawnych komunikatów blokad/powodów w UI.

## Braki systemowe
1. **Policy Engine jako gate w Orchestratorze**
2. **Spójna definicja autonomii (backend‑enforced)**
3. **Kontrakt „organizm → organy → funkcje” (budżety, TTL, audyt)**

## Co jest potrzebne, aby domknąć wizję (high‑level)
1. **Decyzja strategiczna runtime** (ONNX‑first vs. LLM‑first z API‑abstrakcją).
2. **Globalny Policy Gate** (przed wykonaniem narzędzi i wyboru providerów).
3. **Knowledge contract** (jedna definicja wpisu, źródła, sesji, lessons).
4. **Self‑improvement pipeline** (automatyczny cykl test/PR/memory/policy).
5. **Rider‑Pi lifecycle** (telemetria, bezpieczeństwo, start/stop).

## Następne kroki (do doprecyzowania w kolejnych PR-ach)
- Zdefiniować kryteria wyboru runtime (LLM‑first vs. ONNX‑first).
- Opisać minimalny zakres Policy Gate w Orchestratorze.
- Spisać schemat „knowledge contract” i mapę migracji.
- Określić MVP dla pętli samodoskonalenia.
- Spisać wymagania operacyjne dla Rider‑Pi (telemetria, bezpieczeństwo, kontrola).
