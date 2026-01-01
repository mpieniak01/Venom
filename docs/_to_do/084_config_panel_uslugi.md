# 084: Panel konfiguracji – usługi (status + sterowanie)
Status: do zrobienia (PR plan + analiza stanu obecnego).

## Cel
Ujednolicić panel usług na `/config`, tak aby:
- jasno rozróżniał **usługi sterowalne** od **tylko informacyjnych**,
- nie pokazywał akcji tam, gdzie backend zwraca tylko placeholder,
- prezentował spójny i prawdziwy obraz stosu Venom (runtime + monitor).

## Kontekst (co jest zaimplementowane vs. placeholder)
### Zaimplementowane (działa realnie)
- **API /api/v1/runtime/status** zwraca statusy usług z `RuntimeController` + (opcjonalnie) `ServiceMonitor`.
- **RuntimeController**:
  - Backend/UI: status na podstawie PID + logów; start/stop przez `make start-dev` / `make stop`.
  - Ollama/vLLM: status przez porty (11434/8001); start przez komendy env (`OLLAMA_START_COMMAND`, `VLLM_START_COMMAND`).
  - Historia akcji (`/api/v1/runtime/history`) – zapisywana lokalnie w kontrolerze.
  - Profile (`/api/v1/runtime/profile/{full|light|llm_off}`) – uruchamianie zestawów usług.
- **UI ServicesPanel**: pobiera status + historię, renderuje karty usług i przyciski Start/Stop/Restart.

### Placeholder / ograniczenia (nie steruje realnie)
- **Hive / Nexus / Background Tasks**:
  - status oparty wyłącznie o flagi konfiguracyjne (`ENABLE_HIVE`, `ENABLE_NEXUS`, `VENOM_PAUSE_BACKGROUND_TASKS`),
  - `start/stop/restart` zwracają komunikat „kontrolowane przez konfigurację” (brak realnego procesu).
- **UI stop**: `stop_ui` zwraca komunikat, ale nie steruje bezpośrednio procesem (pośrednio przez `make stop`).
- **ServiceMonitor** (jeśli aktywny) dodaje byty typu Redis, Docker, Local LLM, itd.:
  - to **health-checki**, nie procesy runtime; nie powinny mieć akcji Start/Stop.
  - `service_type` może nie mapować się na `ServiceType`, więc akcje z UI i tak nie zadziałają.
- **Duplikaty/overlap**: część usług (LLM) jest już w runtime i jest filtrowana w system endpoint, ale UI dalej pokazuje wszystko bez jasnego rozróżnienia.

## Zakres PR (plan)
1) **Rozróżnienie usług sterowalnych vs monitorowanych**
   - backend: w `/api/v1/runtime/status` dodać pole `actionable: bool` albo `source: runtime|monitor`.
   - UI: ukrywać przyciski start/stop/restart dla `actionable=false`.
2) **Spójny model nazw + ikon**
   - Ujednolicić nazwy na poziomie `service_type`/`service.name` (uniknąć duplikatów i różnych etykiet).
3) **Obsługa placeholderów w UI**
   - Jeśli usługa jest konfigurowana flagą (Hive/Nexus/Background Tasks), pokazać status, ale zamiast akcji wyświetlić info „kontrolowane przez konfigurację”.
4) **Dokumentacja w CONFIG_PANEL.md**
   - Zwięzłe wyjaśnienie: co jest procesem runtime, co jest tylko health-checkiem, a co placeholderem.

## Kryteria akceptacji
- Panel usług nie pokazuje „akcji” dla bytów, które nie mają realnego start/stop.
- Hive/Nexus/Background Tasks prezentowane jako konfigurowalne flagą, bez mylących przycisków.
- Usługi z ServiceMonitor są czytelnie oznaczone jako „monitorowane” (read-only).
- Brak duplikatów nazw i spójna nomenklatura.

## Otwarte pytania
- Czy UI ma też pozwalać na zmianę flag (ENABLE_HIVE/ENABLE_NEXUS) z poziomu panelu?
- Czy ServiceMonitor powinien zwracać osobne pole `actionable`, czy wystarczy `source`?
- Czy `stop_ui` ma rzeczywiście zatrzymywać proces UI, czy tylko informować użytkownika?
