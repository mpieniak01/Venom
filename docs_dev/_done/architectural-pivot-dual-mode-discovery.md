# Architectural Pivot: Dual-Mode Discovery (mDNS + Hive Registration)

**Data:** 2025-12-09
**Context:** Odpowiedź na komentarz PR #6 od @mpieniak01
**Zmiana:** Rozszerzenie architektury o Client-Side Registration Pattern

---

## Problem: Agent za NAT/Firewallem

### Ograniczenia mDNS (Zeroconf)
- ✅ Działa **tylko w sieci lokalnej (LAN)**
- ❌ Nie działa przez Internet
- ❌ Nie działa przez NAT/Firewall
- ❌ Ul musi być w tej samej sieci co Agent

### Nowe wymaganie
Agent może znajdować się za NAT/Firewallem, a centralny "Ul" (Hive Server) może być w Internecie.

---

## Rozwiązanie: Dual-Mode Discovery

### 1. mDNS (Zeroconf) - ZACHOWANE
**Cel:** Lokalne wykrywanie przez administratora
**Użycie:** `ping venom.local` w sieci LAN
**Status:** Pomocniczy, nie główny kanał komunikacji

### 2. Hive Registration - NOWE
**Cel:** Aktywna rejestracja w zdalnym Ulu
**Model:** Client-Side Registration (Agent dzwoni do Ula)
**Protokół:** HTTP POST do `{HIVE_URL}/api/agents/register`

---

## Implementacja

### 1. Nowa konfiguracja (`venom_core/config.py`)

```python
# Konfiguracja THE_HIVE
HIVE_URL: str = ""  # URL centralnego Ula (np. https://hive.example.com:8080)
HIVE_REGISTRATION_TOKEN: SecretStr = SecretStr("")  # Token autoryzacji
```

### 2. Rozszerzona klasa `CloudProvisioner`

#### Nowe pola:
```python
self.agent_id: str             # UUID agenta (automatycznie generowany)
self.hive_url: str             # URL Ula z konfiguracji
self.hive_registered: bool     # Status rejestracji
```

#### Nowa metoda: `register_in_hive()`
```python
async def register_in_hive(
    self,
    hive_url: Optional[str] = None,
    metadata: Optional[dict] = None
) -> dict[str, Any]:
    """
    Rejestruje agenta w centralnym Ulu (Hive Server).

    Agent inicjuje połączenie wychodzące do Ula,
    dzięki czemu działa za NAT/Firewallem.
    """
```

**Payload rejestracji:**
```json
{
  "agent_id": "uuid-agenta",
  "hostname": "agent-machine",
  "service_port": 8000,
  "status": "online",
  "capabilities": ["ssh_deployment", "mdns_discovery"],
  "version": "1.0"
}
```

**Autoryzacja:**
```http
Authorization: Bearer {HIVE_REGISTRATION_TOKEN}
```

---

## Przykład użycia

### Konfiguracja (`.env` lub `config.py`):
```bash
HIVE_URL=https://hive.example.com:8080
HIVE_REGISTRATION_TOKEN=secret_token_abc123
```

### Kod agenta:
```python
from venom_core.infrastructure.cloud_provisioner import CloudProvisioner

# Inicjalizacja
provisioner = CloudProvisioner(service_port=8000)

# 1. Start mDNS (lokalne wykrywanie)
provisioner.start_broadcasting("my-agent")

# 2. Rejestracja w Ulu (zdalne połączenie)
result = await provisioner.register_in_hive()

if result["status"] == "registered":
    print(f"✓ Agent zarejestrowany: {result['agent_id']}")
```

### Metadane niestandardowe:
```python
custom_metadata = {
    "location": "datacenter-1",
    "environment": "production",
    "gpu_available": True,
}

await provisioner.register_in_hive(metadata=custom_metadata)
```

---

## Diagram architektury

```
┌─────────────────────────────────────────────────────────────┐
│                     AGENT (za NAT)                          │
│                                                             │
│  ┌────────────────┐         ┌─────────────────┐           │
│  │ mDNS Broadcast │         │ Hive Registration│           │
│  │  (Zeroconf)    │         │  (HTTP POST)     │           │
│  └────────┬───────┘         └────────┬─────────┘           │
│           │                          │                      │
└───────────┼──────────────────────────┼──────────────────────┘
            │                          │
            │ LAN only                 │ Internet OK
            │ Passive                  │ Active (outbound)
            ▼                          ▼
    ┌───────────────┐          ┌─────────────────┐
    │  Local Admin  │          │  Hive Server    │
    │  (ping)       │          │  (Internet)     │
    └───────────────┘          └─────────────────┘
```

---

## Zalety rozwiązania

### ✅ Działa za NAT/Firewallem
- Agent inicjuje połączenie wychodzące (outbound)
- Ul nie potrzebuje dostępu do Agenta (inbound)
- Standardowe firewall rules pozwalają na outbound HTTP

### ✅ Dual-Mode Discovery
- **mDNS**: dla lokalnych administratorów (`ping venom.local`)
- **Hive**: dla zdalnego zarządzania (zadania, monitoring)

### ✅ Elastyczność
- Jeśli `HIVE_URL` nie jest skonfigurowany → tylko mDNS
- Jeśli `HIVE_URL` jest skonfigurowany → dual-mode
- Można dodać custom metadata przy rejestracji

### ✅ Bezpieczeństwo
- Autoryzacja przez token (`HIVE_REGISTRATION_TOKEN`)
- HTTPS dla połączeń do Ula
- Timeout dla wszystkich requestów

---

## Testy

### Nowe testy jednostkowe (5):
1. `test_register_in_hive_no_url` - brak HIVE_URL
2. `test_register_in_hive_success` - pomyślna rejestracja
3. `test_register_in_hive_error_status` - błąd HTTP (403, 500, etc.)
4. `test_register_in_hive_timeout` - timeout połączenia
5. `test_register_in_hive_with_metadata` - custom metadata

### Wyniki:
```
tests/test_cloud_provisioner.py::test_register_in_hive_no_url PASSED
tests/test_cloud_provisioner.py::test_register_in_hive_success PASSED
tests/test_cloud_provisioner.py::test_register_in_hive_error_status PASSED
tests/test_cloud_provisioner.py::test_register_in_hive_timeout PASSED
tests/test_cloud_provisioner.py::test_register_in_hive_with_metadata PASSED
```

### Testy istniejące (mDNS):
```
tests/test_cloud_provisioner.py::test_start_broadcasting PASSED
tests/test_cloud_provisioner.py::test_get_service_url PASSED
```

**Wszystkie testy przechodzą! ✅**

---

## API Endpoint Ula (Hive Server)

Ul powinien implementować endpoint:

```
POST /api/agents/register
```

**Request:**
```json
{
  "agent_id": "uuid",
  "hostname": "string",
  "service_port": 8000,
  "status": "online",
  "capabilities": ["string"],
  "version": "1.0",
  // ... custom metadata
}
```

**Response (200/201):**
```json
{
  "status": "registered",
  "agent_id": "uuid",
  "message": "Agent registered successfully",
  "assigned_tasks": []  // opcjonalne
}
```

**Response (403):**
```json
{
  "status": "error",
  "message": "Invalid token"
}
```

---

## Migracja

### Istniejący kod:
- ✅ **Zachowany** - mDNS (`start_broadcasting`, `stop_broadcasting`)
- ✅ **Zachowany** - wszystkie metody SSH deployment
- ✅ **Zachowany** - diagnostyka (energy_manager, tracer)

### Nowy kod:
- ➕ `register_in_hive()` - nowa metoda
- ➕ `HIVE_URL`, `HIVE_REGISTRATION_TOKEN` - nowa konfiguracja
- ➕ `agent_id`, `hive_registered` - nowe pola

### Backward compatibility:
- ✅ Jeśli `HIVE_URL` nie jest skonfigurowany → działa jak wcześniej (tylko mDNS)
- ✅ Existing tests nie są zepsute

---

## Wnioski

1. **Problem rozwiązany**: Agent może być za NAT/Firewallem
2. **Architektura rozszerzona**: Dual-Mode Discovery (mDNS + Hive)
3. **mDNS zachowany**: Nadal przydatny dla lokalnych administratorów
4. **Nowy pattern**: Client-Side Registration (Agent → Ul)
5. **Gotowe do integracji**: Ul może teraz śledzić i zarządzać agentami

---

## Następne kroki (opcjonalne)

1. **Heartbeat**: Okresowe pingowanie Ula (Agent → Ul)
2. **Task Polling**: Agent pobiera zadania z Ula
3. **Status Updates**: Agent raportuje postęp zadań
4. **Graceful Shutdown**: Agent wyrejestrowuje się przy zamykaniu
