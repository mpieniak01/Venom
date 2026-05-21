# THE CHAT - Asystent Operacyjny Repo

## Rola

Chat Agent to asystent repo- i workspace-first w Venom. Jego zadaniem jest interpretowanie stanu projektu i wspieranie operatora na podstawie faktów z bieżącego środowiska.

## Szybki start

Jeśli chcesz zacząć używać Copilot chatu w Venom, zacznij tutaj:

1. Uruchom local-first runtime:
   ```bash
   make local-first-start MODEL=qwen2.5-coder:7b
   ```
2. Sprawdź, czy runtime jest gotowy:
   ```bash
   make local-first-status
   ```
3. Otwórz lokalny lane Copilot chatu:
   ```bash
   make local-first-codex MODEL=qwen2.5-coder:7b PROMPT='Powiedz tylko OK.'
   ```
4. Jeśli potrzebujesz prawdy repo przed odpowiedzią, użyj lane repo-truth:
   ```bash
   make local-first-repo-truth-agent MODEL=qwen2.5-coder:7b PROMPT='Przeanalizuj stan repo i podaj kolejny krok.'
   ```
5. Szczegóły runtime, sesji i tooli sprawdzaj w `CHAT_OPERATOR.md` oraz `CHAT_SESSION.md`.

## Do czego służy

- stan repo i gałęzi,
- zakres kontraktu API i rozjazdy między kodem a dokumentacją,
- przemodelowanie dokumentacji i skryptów,
- decyzje oparte o pamięć długoterminową,
- opcjonalnie kalendarz lub small talk, ale tylko na wyraźne życzenie.

## Główne integracje

- `MemorySkill` - przywoływanie i zapisywanie trwałych faktów operatorskich.
- `GoogleCalendarSkill` - opcjonalne akcje kalendarza, nie domyślny fokus.

Kalendarz jest dostępny, ale nie jest głównym tematem czatu.

Szczegóły routingu sesji, tooli, runtime i targetów `make` są delegowane do `CHAT_OPERATOR.md` oraz `CHAT_SESSION.md`.

## Zasady działania

- Najpierw repo i fakty.
- Potem pamięć.
- Odpowiadaj operacyjnie i zwięźle.
- Zapisuj ważne fakty operatorskie, gdy mają znaczenie.

## Obsługiwane intencje

**GENERAL_CHAT**
- stan repo,
- stan gałęzi,
- zakres kontraktu API,
- remont dokumentacji i skryptów,
- zapis ważnych faktów do pamięci,
- jawne pytania o kalendarz.

**Nie obsługiwane tutaj**
- generowanie kodu,
- złożone planowanie,
- research,
- wyszukiwanie wiedzy.

## Zobacz też

- [CHAT_OPERATOR.md](CHAT_OPERATOR.md) - workflow czatu, runtime i komendy szybkiego startu
- [CHAT_SESSION.md](CHAT_SESSION.md) - sesje, routing i szczegóły techniczne
- [THE_RESEARCHER.md](THE_RESEARCHER.md) - wyszukiwanie bieżących informacji
- [MEMORY_LAYER_GUIDE.md](MEMORY_LAYER_GUIDE.md) - model pamięci
- [INTENT_RECOGNITION.md](INTENT_RECOGNITION.md) - klasyfikacja intencji
