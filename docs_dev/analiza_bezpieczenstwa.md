# Raport z Analizy Bezpieczeństwa Venom

## Przegląd
W ramach audytu bezpieczeństwa zidentyfikowano i naprawiono trzy krytyczne podatności w systemie Venom. Poniższy dokument opisuje wykryte zagrożenia oraz zastosowane poprawki.

## 1. Obejście Systemu Autonomii (Autonomy Bypass)

### Problem
System `PermissionGuard` definiujący poziomy autonomii (np. `ISOLATED`, `BUILDER`) nie był zintegrowany z warstwą wykonawczą.
- **Ryzyko:** Agenci mogli wykonywać operacje na plikach i komendy systemowe niezależnie od ustawionego poziomu bezpieczeństwa.
- **Status:** KRYTYCZNY (Naprawiono)

### Naprawa
Wdrożono bezpośrednie sprawdzenia uprawnień w kluczowych umiejętnościach (Skills):
- **FileSkill (`venom_core/execution/skills/file_skill.py`):** Dodano sprawdzenie `permission_guard.can_write_files()` przed każdą operacją zapisu.
- **ShellSkill (`venom_core/execution/skills/shell_skill.py`):** Dodano sprawdzenie `permission_guard.can_execute_shell()` przed wykonaniem jakiejkolwiek komendy.

## 2. Wyciek Sekretów przez API (Config Secrets Exposure)

### Problem
Endpoint `GET /api/v1/config/runtime` pozwalał na pobranie pełnej konfiguracji środowiska, w tym kluczy API, bez uwierzytelniania.
- **Ryzyko:** Wyciek kluczy API (OpenAI, GitHub, etc.) do każdego podmiotu mającego dostęp do portu API.
- **Status:** KRYTYCZNY (Naprawiono)

### Naprawa
- Wymuszono parametr `mask_secrets=True` wewnątrz endpointu (`venom_core/api/routes/system_config.py`).
- API teraz zawsze zwraca maskowane wartości sekretów (np. `sk-****`), niezależnie od parametrów żądania.

## 3. Nieautoryzowana Zmiana Konfiguracji (Env Injection)

### Problem
Endpoint `POST /api/v1/config/runtime` pozwalał na modyfikację dowolnych zmiennych środowiskowych `.env` bez uwierzytelniania.
- **Ryzyko:** Możliwość wyłączenia zabezpieczeń przez zewnętrzne skrypty (CSRF).
- **Status:** KRYTYCZNY (Naprawiono)

### Naprawa (Podejście User-Centric)
Zgodnie z filozofią "Użytkownik jest Administratorem", system blokuje tylko **zewnętrzne** ataki, dając użytkownikowi pełną kontrolę:
- **Host Validation:** API akceptuje zmiany konfiguracji **wyłącznie z localhosta** (`127.0.0.1`). To chroni przed atakami sieciowymi, ale pozwala użytkownikowi (poprzez UI) na pełną konfigurację systemu.
- **Brak Sztucznych Ograniczeń:** Usunięto "czarną listę" parametrów. Użytkownik ma prawo wyłączyć Sandbox lub zmienić klucze API, jeśli taka jest jego wola, pod warunkiem że robi to lokalnie.

## Podsumowanie Filozofii Bezpieczeństwa
System Venom jest projektowany jako narzędzie dla **pojedynczego użytkownika w bezpiecznej sieci**.
1.  **Suwerenność Użytkownika:** System nie narzuca administratorowi (użytkownikowi) ograniczeń, których nie może zdjąć.
2.  **Ochrona przed Przypadkiem:** Poziomy Autonomii chronią przed błędami agenta, nie przed "złym administratorem".
3.  **Ochrona przed Zewnątrz:** Blokady sieciowe (localhost binding) chronią przed nieautoryzowanym dostępem z sieci lokalnej/internetu.

## Weryfikacja
Wdrożone poprawki zostały zweryfikowane testami:
- Próby obejścia autonomii przez agenta są blokowane (`AutonomyViolation`).
- Próby wyciągnięcia sekretów przez API zwracają maskowane dane.
- Konfiguracja systemu jest dostępna dla użytkownika lokalnego, ale zablokowana dla połączeń zewnętrznych.

## 4. Plan Dalszych Działań: Automatyzacja Testów Bezpieczeństwa
Aby zapobiec regresji (ponownemu wystąpieniu błędów), konieczne jest wdrożenie dedykowanych testów `pytest` w obszarze bezpieczeństwa:
- **Testy Autonomii:** Automatyczne scenariusze sprawdzające, czy zmiana poziomu na `ISOLATED` faktycznie blokuje operacje `ShellSkill` i `FileSkill`.
- **Testy API:** Weryfikacja endpointów pod kątem wycieku sekretów (czy maskowanie działa) oraz walidacja hosta (czy odrzuca połączenia spoofowane).
- **Zasada CI/CD:** Testy te powinny być uruchamiane przy każdym Pull Request, a ich niepowodzenie musi blokować wdrożenie.

#### Nowy Pakiet: `tests/security/`
Należy utworzyć dedykowany pakiet testów (`pytest`), który będzie rutynowo weryfikował bezpieczeństwo warstwy Web i API:
- **API Security:** Automatyczne skany endpointów sprawdzające autoryzację (BOLA/IDOR) i walidację danych wejściowych (Injection).
- **Web Security:** Testy nagłówków bezpieczeństwa (CSP, CORS) oraz podstawowe sprawdzenia podatności frontendowych (XSS w renderowaniu Markdown).
- **Cel:** Ten pakiet ma działać jako "lekki skaner podatności" uruchamiany przed każdym release'm.
