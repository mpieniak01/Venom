# Runbook Ollama Feedback-Loop

## Cel
Sterowanie rozwiązywaniem klasy modelu codingowego `OpenCodeInterpreter-Qwen2.5-7B`.

Polityka runtime:
- primary: `qwen2.5-coder:7b`
- fallbacks: `qwen2.5-coder:3b`, `codestral:latest`

## Sprawdź stan runtime
```bash
curl -s http://127.0.0.1:8000/api/v1/system/llm-runtime/options | jq '.feedback_loop, .active'
```

Kluczowe pola:
- `requested_model_alias`
- `resolved_model_id`
- `resolution_reason` (`exact` | `fallback` | `resource_guard`)

## Instalacja po aliasie (idempotent)
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/models/install \
  -H 'Content-Type: application/json' \
  -d '{"name":"OpenCodeInterpreter-Qwen2.5-7B"}'
```

Oczekiwane zachowanie:
- jeśli model już jest: `already_installed=true`
- jeśli primary jest zablokowany guardem zasobowym: instalator planuje fallback

## Aktywacja z fallbackiem
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active \
  -H 'Content-Type: application/json' \
  -d '{"server_name":"ollama","model_alias":"OpenCodeInterpreter-Qwen2.5-7B"}'
```

## Aktywacja exact-only (bez fallback)
```bash
curl -s -X POST http://127.0.0.1:8000/api/v1/system/llm-servers/active \
  -H 'Content-Type: application/json' \
  -d '{"server_name":"ollama","model_alias":"OpenCodeInterpreter-Qwen2.5-7B","exact_only":true}'
```

Oczekiwane zachowanie:
- zwraca 409, gdy primary jest niedostępny lub zablokowany guardem zasobowym
- błąd zawiera rekomendację fallbacku albo zmiany profilu/zasobów

## Typowe naprawy
1. Guard zasobowy na niskim profilu:
- ustaw `VENOM_OLLAMA_PROFILE=balanced-12-24gb`
2. Brak 7B w lokalnym katalogu:
- zainstaluj `qwen2.5-coder:7b`
3. Za słaby host dla 7B:
- użyj fallbacku `qwen2.5-coder:3b`
