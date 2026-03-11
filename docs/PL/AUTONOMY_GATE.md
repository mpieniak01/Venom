# AutonomyGate - System Kontroli Uprawnień

Bazowe wymagania polityki bezpieczeństwa dla egzekwowania autonomii są opisane w `docs/PL/SECURITY_POLICY.md`.

## 📋 Wprowadzenie

AutonomyGate to 5-stopniowy system kontroli uprawnień agenta, który zastępuje binarny "Cost Mode". System zarządza dostępem do sieci, budżetem oraz prawami do modyfikacji plików i systemu operacyjnego.

## 🚦 Poziomy Autonomii

System definiuje 5 poziomów zaufania, gdzie każdy wyższy poziom dziedziczy uprawnienia niższych:

### Poziom 0: ISOLATED (🟢 Zielony)
- **Zakres**: Lokalny Odczyt
- **Uprawnienia**:
  - ✅ Dostęp do lokalnych plików (read-only)
  - ✅ Modele lokalne (Ollama, vLLM, ONNX)
  - ✅ Pamięć RAG (lokalna)
  - ❌ Brak dostępu do sieci
  - ❌ Brak zapisu plików
- **Ryzyko**: Zerowe
- **Przykładowe Skille**: `FileRead`, `MemoryRecall`, `LocalLlm`

### Poziom 10: CONNECTED (🔵 Niebieski)
- **Zakres**: Internet (Free)
- **Uprawnienia**:
  - ✅ Wszystko z poziomu ISOLATED
  - ✅ Dostęp do publicznej sieci
  - ✅ Darmowe API (DuckDuckGo, Wikipedia)
  - ✅ Przeglądarka web
  - ❌ Nadal brak zapisu plików
- **Ryzyko**: Niskie (wyciek danych)
- **Przykładowe Skille**: `DuckDuckGo`, `BrowserVisit`, `WeatherApi`

### Poziom 20: FUNDED (🟡 Żółty)
- **Zakres**: Płatne API (Cloud)
- **Uprawnienia**:
  - ✅ Wszystko z poziomu CONNECTED
  - ✅ Płatne API chmurowe (GPT-4, Gemini)
  - ✅ Autoryzacja wydatków (Token Economist)
  - ✅ SOTA AI modele
  - ❌ Nadal brak zapisu plików
- **Ryzyko**: Średnie (koszty finansowe)
- **Przykładowe Skille**: `GPT-4o`, `Gemini Pro`, `DeepL`, `DALL-E`

### Poziom 30: BUILDER (🟠 Pomarańczowy)
- **Zakres**: Edycja Plików
- **Uprawnienia**:
  - ✅ Wszystko z poziomu FUNDED
  - ✅ Tworzenie i modyfikacja plików
  - ✅ Edycja kodu projektu
  - ✅ Git commit/push
  - ❌ Brak dostępu do terminala systemowego
- **Ryzyko**: Wysokie (błędy w kodzie)
- **Przykładowe Skille**: `FileWrite`, `FileEdit`, `GitCommit`

### Poziom 40: ROOT (🔴 Czerwony)
- **Zakres**: Pełna Władza
- **Uprawnienia**:
  - ✅ Wszystko z poziomu BUILDER
  - ✅ Dostęp do powłoki systemowej (Shell)
  - ✅ Docker, instalacja pakietów
  - ✅ Pełna kontrola systemu
- **Ryzyko**: Krytyczne (destrukcja systemu)
- **Przykładowe Skille**: `ShellExecute`, `DockerRun`, `PipInstall`

## 🛠️ Implementacja

### Backend

#### 1. PermissionGuard

Singleton zarządzający systemem uprawnień:

```python
from venom_core.core.permission_guard import permission_guard, AutonomyViolation

# Sprawdź uprawnienia
try:
    permission_guard.check_permission("ShellSkill")
    # Jeśli uprawnienia wystarczające, wykonaj akcję
except AutonomyViolation as e:
    # Brak uprawnień - zwróć błąd 403 do frontendu
    print(f"Wymagany poziom: {e.required_level_name}")
```

#### 2. StateManager

Persystencja poziomu autonomii:

```python
from venom_core.core.state_manager import StateManager

state_manager = StateManager()
print(f"Aktualny poziom: {state_manager.autonomy_level}")
```

#### 3. API Endpoints

```bash
# Pobierz aktualny poziom
GET /api/v1/system/autonomy

# Ustaw nowy poziom
POST /api/v1/system/autonomy
{
  "level": 20
}

# Lista wszystkich poziomów
GET /api/v1/system/autonomy/levels
```

> **Ostrzeżenie dotyczące bezpieczeństwa:** Endpointy kontroli autonomii powinny być chronione autentykacją i ograniczone do localhost lub zaufanych sieci. Nieograniczony dostęp pozwala dowolnemu wywołującemu na podniesienie poziomu autonomii do ROOT, co omija wszystkie kontrole uprawnień dotyczące dostępu do sieci, zapisu plików i wykonywania komend shell.

#### 4. Kanoniczny payload blokady (policy/autonomy)

Mutujące trasy i guardowane ścieżki runtime używają jednego kontraktu blokady `HTTP 403`:

```json
{
  "decision": "block",
  "reason_code": "PERMISSION_DENIED",
  "user_message": "Access denied",
  "technical_context": {
    "operation": "system.config.localhost_guard"
  },
  "tags": ["permission", "blocked"]
}
```

Uwagi:
- Dla blokad autonomii `reason_code` ma wartość `AUTONOMY_PERMISSION_DENIED`.
- Helper blokad route-level publikuje kanoniczne eventy audytu:
  - `source=api.permission`
  - `action=policy.blocked.route` lub `action=autonomy.blocked`
  - `status=blocked`
  - `details` zgodne z payloadem blokady.
- Tryb egzekwowania autonomii steruje backend (`AUTONOMY_ENFORCEMENT_MODE=hard|soft`):
  - `hard` (domyślnie): `decision=block`, operacja jest terminalnie blokowana, `technical_context.terminal=true`, `technical_context.retryable=false`.
  - `soft`: `decision=degraded_allow`, operacja przechodzi z ostrzeżeniem, audyt: `action=autonomy.degraded_allow`, `status=degraded`.
- UI nie jest warstwą egzekucji autonomii. UI tylko prezentuje decyzję backendu (`decision`, `reason_code`, `user_message`, `technical_context`).

### Frontend

#### 1. Selektor Autonomii

W UI Next.js (cockpit/layout):

- Selektor autonomii w sidebar (`web-next/components/layout/sidebar-sections.tsx`)
- Selektor autonomii w widoku mobile (`web-next/components/layout/mobile-nav.tsx`)
- Wspólna logika stanu autonomii (`web-next/components/layout/use-sidebar-logic.ts`)

#### 2. Dynamiczne Tematowanie

Stan autonomii jest prezentowany przez stan UI i etykiety i18n w cockpit/layout.
UI pokazuje poziom i ryzyko z backendu, ale nie egzekwuje lokalnie decyzji policy/autonomy.

#### 3. Obsługa Błędów

Gdy backend zwróci `403 Autonomy Violation`:

1. Frontend wyświetla modal z informacją o wymaganym poziomie
2. Selektor autonomii pulsuje odpowiednim kolorem
3. Użytkownik może zwiększyć poziom lub anulować

## 📊 Scenariusz Użycia

### Przykład: Sprawdzanie Pogody i Zapis do Pliku

```
1. START: System w poziomie ISOLATED (0)

2. Użytkownik: "Sprawdź pogodę w Warszawie"
   - Backend: PermissionGuard.check_permission("WebSkill")
   - Wynik: AutonomyViolation (wymagany poziom 10)
   - Frontend: Modal + pulsacja na niebiesko

3. Użytkownik zwiększa poziom do CONNECTED (10)
   - Backend: permission_guard.set_level(10)
   - Frontend: Theme zmienia się na niebieski

4. Użytkownik ponownie: "Sprawdź pogodę w Warszawie"
   - Backend: Uprawnienia OK, wykonuje WebSkill
   - Wynik: Pobrano dane o pogodzie

5. Użytkownik: "Zapisz to do pliku pogoda.txt"
   - Backend: PermissionGuard.check_permission("FileWriteSkill")
   - Wynik: AutonomyViolation (wymagany poziom 30)
   - Frontend: Modal + pulsacja na pomarańczowo

6. Użytkownik zwiększa poziom do BUILDER (30)
   - Backend: permission_guard.set_level(30)
   - Frontend: Theme zmienia się na pomarańczowy

7. Użytkownik ponownie: "Zapisz to do pliku pogoda.txt"
   - Backend: Uprawnienia OK, wykonuje FileWriteSkill
   - Wynik: Plik zapisany
```

## 🔒 Zasady Bezpieczeństwa

### 1. Domyślny Poziom: ISOLATED

System zawsze startuje w poziomie ISOLATED (0) dla maksymalnego bezpieczeństwa.

### 2. Nowe Narzędzia = ROOT

Nowe, nieskategoryzowane skille domyślnie wymagają poziomu ROOT (40):

```python
# W skill_permissions.yaml brak UnknownSkill
# PermissionGuard domyślnie wymaga poziomu 40
permission_guard.check_permission("UnknownSkill")  # Wymaga ROOT
```

### 3. Explicit > Implicit

Lepiej jawnie ustawić niższy poziom dla bezpiecznego skilla niż polegać na domyślnym ROOT:

```yaml
# skill_permissions.yaml
SafeReadOnlySkill: 0  # Explicit - bezpieczne
```

### 4. Audyt i Monitoring

- Każda zmiana poziomu jest logowana
- StateManager persystuje poziom między sesjami
- TokenEconomist automatycznie włącza/wyłącza paid mode na poziomie 20+

## 📁 Pliki Konfiguracyjne

### autonomy_matrix.yaml

Definicja poziomów autonomii:

```yaml
levels:
  - id: 0
    name: "ISOLATED"
    description: "Lokalny Odczyt"
    color: "#22c55e"
    permissions:
      network_enabled: false
      paid_api_enabled: false
      filesystem_mode: "read_only"
      shell_enabled: false
```

### skill_permissions.yaml

Mapowanie skillów na poziomy:

```yaml
FileReadSkill: 0
WebSearchSkill: 10
GeminiSkill: 20
FileWriteSkill: 30
ShellSkill: 40
```

## 🧪 Testowanie

Uruchom testy:

```bash
pytest tests/test_permission_guard.py -v
```

Kluczowe testy:
- ✅ Singleton pattern
- ✅ Ustawianie poziomów
- ✅ Sprawdzanie uprawnień
- ✅ Dziedziczenie uprawnień
- ✅ Blokowanie niedozwolonych akcji
- ✅ Domyślne wymaganie ROOT dla nieznanych skillów

## 🎯 Best Practices

1. **Start Safe**: Zawsze rozpoczynaj sesję w poziomie ISOLATED
2. **Incremental Elevation**: Zwiększaj poziom tylko gdy potrzeba
3. **Explicit Permissions**: Definiuj uprawnienia dla nowych skillów w `skill_permissions.yaml`
4. **User Confirmation**: Frontend wymaga świadomej zgody użytkownika na zmianę poziomu
5. **Audit Trail**: Monitoruj zmiany poziomów w logach

## 📚 Referencje

- **Kod Backend**: `venom_core/core/permission_guard.py`
- **Kod Frontend**:
  - `web-next/components/layout/sidebar-sections.tsx`
  - `web-next/components/layout/mobile-nav.tsx`
  - `web-next/components/layout/use-sidebar-logic.ts`
- **Konfiguracja**: `config/autonomy_matrix.yaml`, `config/skill_permissions.yaml`
- **Testy**: `tests/test_permission_guard.py`
- **API**: `venom_core/api/routes/system_governance.py` (endpointy `/api/v1/system/autonomy`)
- **Runbook**: `docs/PL/runbooks/policy-autonomy-deny-triage.md`
