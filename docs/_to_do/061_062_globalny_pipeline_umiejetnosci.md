# 061/062: Globalny pipeline umiejętności + naprawa „podaj godzinę”

## Problem
Obecne rozpoznawanie umiejętności/intencji jest rozproszone i oparte głównie na prostych słowach kluczowych. To powoduje:
- brak odporności na literówki i warianty zapytań,
- słabą obsługę wielojęzyczności (PL/EN/DE),
- niestabilność w trybie offline lub przy błędach LLM,
- trudność w rozbudowie o nowe umiejętności.

Dodatkowo „podaj godzinę” nie działało stabilnie z lokalnymi modelami (brak SYSTEM role / brak tool calling / błędy połączeń), a odpowiedź była opóźniona przez kosztowne etapy pamięci.

## Cel
Wprowadzić jednolity, globalny pipeline NLU dla wszystkich umiejętności (obecnych i przyszłych), który:
- działa bez LLM jako minimum,
- jest odporny na warianty i literówki,
- obsługuje PL/EN/DE,
- pozwala łatwo dopinać nowe umiejętności przez konfigurację.

Równolegle doprowadzić „podaj godzinę” do szybkiej, deterministycznej odpowiedzi bez LLM i bez zapisu lekcji.

## Globalne rozwiązanie (pipeline)
1. **Normalizacja wejścia**
   - lowercasing, trim, redukcja wielokrotnych spacji
   - transliteracja diakrytyków (PL/DE)
   - usuwanie znaków niealfanumerycznych
   - rozwijanie skrótów/skrótowców

2. **Lexicon per język**
   - słowniki wzorców dla PL/EN/DE
   - synonimy i warianty fraz dla każdej umiejętności
   - regexy dla typowych zapytań

3. **Fuzzy matching (literówki)**
   - dopasowanie oparte o podobieństwo (np. Levenshtein)
   - progi per umiejętność
   - mechanizm rozstrzygania remisów

4. **Embedding fallback (offline)**
   - lokalne wektory „anchorów” umiejętności
   - przypisanie intencji na podstawie podobieństwa semantycznego

5. **LLM fallback (ostatnia warstwa)**
   - wywoływany tylko gdy poprzednie warstwy nie zwróciły pewnego wyniku

## Struktura danych (propozycja)
- `intent_lexicon_pl.json`
- `intent_lexicon_en.json`
- `intent_lexicon_de.json`
  - `intents.{intent_id}.phrases[]`
  - `intents.{intent_id}.regex[]`
  - `intents.{intent_id}.threshold`

## Integracja
- `IntentManager` powinien korzystać z pipeline zamiast gołych keywordów.
- „Bypass” dla krytycznych umiejętności (np. czas, status usług) przed LLM.
- Jedna wspólna warstwa normalizacji i dopasowania dla całego systemu.
 - Dobór języka przez lekką heurystykę + fallback na wszystkie słowniki.

## Kompatybilność
- Zachować dotychczasowe klasyfikacje jako fallback w okresie przejściowym.
- Dodać telemetry/metryki jakości rozpoznania intencji.

## Testy
- Testy jednostkowe dla każdej umiejętności w PL/EN/DE.
- Testy na literówki (min. 2-3 warianty na intent).
- Scenariusze bez LLM (symulacja błędów połączenia).

## Adaptacja stylu użytkownika (kolejny etap)
- Prywatny user‑lexicon poza repo: `data/user_lexicon/intent_lexicon_user_{lang}.json` (patrz zadanie 063).
- Merge bazowego lexiconu + user‑lexicon w runtime.
- Uczenie tylko wtedy, gdy lexicon+fuzzy nie daje pewnego wyniku.
- Dane użytkownika nie trafiają do gita.

## Efekt końcowy
- Spójne, odporne rozpoznawanie umiejętności dla wszystkich obecnych i przyszłych funkcji.
- Mniej błędów w UI i mniej zależności od stabilności LLM.

---

## Plan naprawy „podaj godzinę” + kontrola innych skills

### Co było do naprawy
1. **Klasyfikacja intencji** – lokalny model nie wspiera roli SYSTEM, co powodowało błąd 400 i fallback do `GENERAL_CHAT`.
2. **Rejestracja `AssistantSkill`** – skill nie był wpinany do kernela.
3. **Function calling dla lokalnego modelu** – lokalny backend był blokowany.
4. **Weryfikacja innych skills** – sprawdzić rejestrację pluginów i blokady narzędzi.

### Plan naprawy
1. **Naprawa `IntentManager`**: retry z połączonym promptem (bez roli SYSTEM) po błędzie „System role not supported”.
2. **Rejestracja `AssistantSkill` w kernelu**: plugin przy starcie `TaskDispatcher`.
3. **Włączenie function calling dla lokalnych modeli**: próbuj tool‑call i fallbackuj, jeśli backend nie wspiera narzędzi.
4. **Kontrola innych skills**: mapowanie pluginów i braków.
5. **Globalna naprawa LLM**: wspólny fallback (SYSTEM → USER, tools → no‑tools).
6. **Weryfikacja manualna**: przeniesione do zadania 063.
7. **Bypass LLM dla czasu**: TIME_REQUEST obsługiwany bez LLM.
8. **Wyłącz lekcje dla narzędzi**: nie zapisuj lekcji dla deterministycznych tools.
9. **Globalna normalizacja + fuzzy**: lexicon+fuzzy (PL/EN/DE) przed LLM.

### Status
- [x] 1. IntentManager retry bez SYSTEM
- [x] 2. Rejestracja AssistantSkill
- [x] 3. Function calling dla local
- [x] 4. Przegląd innych skills
- [x] 5. Globalna naprawa LLM (fallback SYSTEM + tools)
- [x] 6. Weryfikacja manualna (przeniesione do 063)
- [x] 7. Bypass LLM dla czasu
- [x] 8. Wyłącz lekcje dla narzędzi
- [x] 9. Globalna normalizacja + fuzzy

### Weryfikacja manualna (uwagi)
- Weryfikacja przeniesiona do zadania 063.

### Przegląd innych skills (wyniki)
- **Globalnie (dispatcher)**: `AssistantSkill` (wbudowany), `SkillManager` ładuje custom skills z `workspace/custom`.
- **Agent‑local**: większość agentów rejestruje własne pluginy (np. `FileSkill`, `ShellSkill`, `ComposeSkill`, `WebSearchSkill`, `GitSkill`, `BrowserSkill`, `DocsSkill`, `MemorySkill`).

### Ryzyka/uwagi
1. **Brak fallbacku SYSTEM role**: historycznie część agentów używała SYSTEM prompt bez fallbacku (naprawione globalnie).
2. **Function calling bez fallbacku**: część agentów nie obsługiwała błędu “tools not supported” (naprawione globalnie).
3. **SystemStatusAgent**: nie używa LLM, więc nie jest narażony na problem roli SYSTEM ani tools.
4. **Spójność intencji**: uzupełniono `TIME_REQUEST` i `UNSUPPORTED_TASK` w promptach LLM oraz poprawiono fallback na user‑lexicon.

### Globalna naprawa LLM (wdrożone)
- Wspólny fallback w `BaseAgent`: retry bez SYSTEM oraz retry bez tools.
- Podpięte agenty: Architect, Toolmaker, CreativeDirector, SystemEngineer, Shadow, ReleaseManager, Critic, Designer, Operator, Executive, Publisher, DevOps, Librarian, Ghost, SimulatedUser, Guardian, Tester, UXAnalyst, Researcher, Coder, Oracle, Integrator.
