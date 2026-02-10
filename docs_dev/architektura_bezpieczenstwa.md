# Analiza Modelu Bezpieczeństwa: Podwójna Suwerenność

## Czy model "Agent Autonomy + User/Admin" jest optymalny?

**Zdecydowanie TAK.** Proponowany model jest bardzo zdrowy, ponieważ rozdziela dwa różne rodzaje ryzyka i odpowiada standardom systemów `Unix/Linux` ("sudo") oraz nowoczesnym podejściom do AI Safety.

### 1. Autonomia Agentów (Ochrona przed AI)
Agenci AI są **indeterministyczni**. Mogą popełniać błędy, halucynować lub źle zinterpretować polecenie.
- **Cel:** Ochrona użytkownika przed systemem.
- **Mechanizm:** `PermissionGuard` (Autonomy Levels).
- **Zasada:** Agent *zawsze* ma ograniczenia (np. nie może wyjść poza workspace, nie może dzwonić do API jeśli nie ma na to budżetu). To jest "klatka bezpieczeństwa".

### 2. Tryb Użytkownika vs Administratora (Ochrona przed Błędem Ludzkim)
Użytkownik jest **właścicielem** systemu.
- **Cel:** Ochrona systemu przed przypadkowym błędem użytkownika, przy zachowaniu pełnej kontroli.
- **Mechanizm:** Rozdzielenie konfiguracji (Admin) od używania (User).
- **Zasada (Sudo):** Na co dzień system nie pozwala na zmianę krytycznych ustawień (Tryb Użytkownika), aby nie zepsuć czegoś przypadkiem. Ale jeśli użytkownik *świadomie* chce wejść w tryb Administratora (np. w UI wchodzi w "Ustawienia Zaawansowane"), system mu na to pozwala.

### 3. Izolacja Przestrzeni Roboczej (Workspace & MCP)
Zgodnie z zasadą separacji eksperymentów od rdzenia systemu:

#### A. Core Isolation
-   **Katalog `venom_core/`:** Traktowany jako **Read-Only** dla Agentów. Agent nie powinien mieć możliwości modyfikacji własnego kodu źródłowego (zapobiega to trwałym uszkodzeniom lub wstrzyknięciu backdoora).
-   **Wyjątki:** Tylko autoryzowane aktualizacje (np. przez `git pull` uruchomione przez użytkownika).

#### B. Workspace Sandbox
-   **Katalog `workspace/`:** To jest "piaskownica". Agenci mają tu pełne prawa (zależnie od poziomu autonomii) do tworzenia, edycji i usuwania plików.
-   **Zasada:** To co dzieje się w `workspace`, zostaje w `workspace`.

#### C. MCP Scripts (Eksperymenty)
-   **Katalog `mcp/` (lub dedykowany):** Miejsce na skrypty Model Context Protocol oraz narzędzia tworzone przez agenta/użytkownika.
-   **Separacja:** Skrypty te są uruchamiane jako odrębne procesy. Nie mają bezpośredniego dostępu do pamięci procesu `venom_core`.

### 4. Automatyzacja Weryfikacji Bezpieczeństwa (Security Testing Policy)
Bezpieczeństwo nie jest stanem, lecz procesem. Aby utrzymać integralność systemu, testy bezpieczeństwa muszą być częścią CI/CD.

#### A. Testy Regresji (Pytest)
Każda zmiana w kodzie musi przechodzić automatyczne testy sprawdzające podstawowe założenia bezpieczeństwa:
1.  **Autonomy Enforecement:** Testy muszą próbować wykonać operacje plikowe/shellowe w trybie `ISOLATED` i oczekiwać błędu `AutonomyViolation`.
2.  **API Security:** Testy muszą sprawdzać, czy endpointy konfiguracyjne maskują sekrety.

#### B. Zasada "Fail Secure"
Jeśli testy bezpieczeństwa nie przechodzą, build musi zostać zatrzymany. Nie ma wyjątków dla "małych poprawek".

### Wnioski
Taki podział jest optymalny dla `Venom`:
1.  **Agent** nigdy nie może sam sobie nadać uprawnień Admina (blokuje go Autonomia).
2.  **Użytkownik** jest bezpieczny na co dzień, ale nie jest "ubezwłasnowolniony" – może naprawić system lub zmienić zasady gry, jeśli tego potrzebuje.
3.  **Rdzeń (Core)** jest odseparowany od **Eksperymentów (Workspace/MCP)**, co gwarantuje stabilność systemu nawet przy błędach w generowanych skryptach.
4.  **Automatyzacja (Pytest)** gwarantuje, że raz naprawiona dziura (np. Autonomy Bypass) nigdy nie wróci (Regression Testing).

To podejście "Defense in Depth" (Obrona w głąb), gdzie warstwa ludzka ma klucze do królestwa, a warstwa AI ma tylko klucze do piaskownicy.
