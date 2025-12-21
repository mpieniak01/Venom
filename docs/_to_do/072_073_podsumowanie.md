# Podsumowanie: 072 i 073

## 072
- Sterowanie parametrami generacji z Cockpitu (schema + walidacja + zapis override).
- Endpointy konfiguracji modelu oraz mapowanie parametrów per runtime (ollama/vLLM).
- UI panel strojenia + hook `updateModelConfig`.
- UX: streaming/first chunk, log pierwszego fragmentu oraz metryka time‑to‑first‑token.

Źródło: `docs/_done/072_strojenie_modelu_llm_ui.md`.

## 073
- Dedykowany ekran zarządzania modelami (Ollama + HuggingFace) z trendami i operacjami.
- Backend: integracje list/trendów, cache, kontrakt danych, operacje install/activate/remove.
- UI: `/models` z sekcjami Trendy/Zainstalowane/Dostępne, statusy operacji i cache.
- Dodatkowo: news/papers + tłumaczenia przez `/api/v1/translate`.

Źródło: `docs/_done/073_ekran_zarzadzania_modelami.md`.

## Kolejne rzeczy do zrobienia
- Tryb pełnoekranowego czatu: zostaje tylko lewy sidebar i górny pasek, a cała
  powierzchnia treści to chatbox; przełącznik względem obecnego widoku czatu.
- Podpięcie wyboru serwera i modelu na dole okna czatu jako selekty dopasowane
  do szerokości okna.
- Przewijana historia czatu (scroll z zachowaniem kontekstu).

## Dla przeglądu kodu (ważne uwagi)
- Streaming first‑chunk opiera się o SSE `/api/v1/tasks/{id}/stream` i aktualizuje `task.result`.
- Wprowadzono metrykę TTFT (first‑token) w metrykach backendu.
- Zredukowano migotanie w UI poprzez wyciszenie loaderów i spokojne odświeżanie.
- Model management opiera się o `ModelRegistry` i zapis manifestu.
- Tłumaczenia news/papers idą przez `/api/v1/translate` z cache per język.

## Stan jakości
- Testy: zielone.
- Pokrycie: 65%.
- Dokumentacja: uzupełniona.
