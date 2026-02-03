# 081: Zlozona intencja uzytkownika wymagajaca wielu narzedzi
Status: do zrobienia

## Cel
System ma rozpoznawac zlozone intencje, ktore wymagaja uzycia kilku narzedzi
w jednym przebiegu (np. research + analiza danych + generowanie raportu),
a nastepnie wykonac je w logicznej sekwencji i zwrocic wynik analizy.

## Zakres
- Rozpoznawanie zlozonych intencji w warstwie klasyfikacji (multi-intent).
- Planowanie sekwencji narzedzi (kolejnosc, dane wejsciowe/wyjsciowe).
- Egzekucja wielu narzedzi w jednym zadaniu oraz przekazywanie kontekstu.
- Finalne podsumowanie/analiza w formie jednej odpowiedzi.
- Logowanie krokow w historii zadania.

## Zasady
- Zlozona intencja to taka, ktora wymaga >1 narzedzia, aby spelnic cel.
- Plan wykonania musi byc deterministyczny i jawny w logach.
- Dane wyjsciowe jednego narzedzia sa przekazywane do kolejnego.
- Jesli jedno narzedzie zawiedzie, system probuje fallback lub konczy z
  czytelnym bledem i stanem czesciowym.
- Uzytkownik widzi finalny wynik + streszczenie krokow.

## Przyklady zapytan
- "Znajdz najnowsze info o firmie X, porownaj z raportem Y i wypisz roznice."
- "Pobierz dane z URL, policz srednia i opisz trend."
- "Sprawdz status repo, pobierz logi testow i podsumuj regresje."

## Kryteria akceptacji
- System wykrywa zlozona intencje i uruchamia >=2 narzedzia.
- Logi zadania pokazuja plan oraz wyniki krokow.
- Wynik koncowy zawiera syntetyczna analize z uzasadnieniem.
- Brak regresji w standardowych (prosty) zapytaniach.

## Scenariusze testowe
1. Zapytanie research + summary -> WebSearch + Browser + podsumowanie.
2. Zapytanie repo + testy -> GitSkill + TestSkill + analiza wynikow.
3. Zapytanie o dane + analiza -> FileSkill + ComposeSkill + podsumowanie.
4. Blad w jednym kroku -> komunikat bledu + kontekst wykonanych krokow.

## PR plan
1) Rozpoznanie zlozonej intencji
   - Dodac heurystyki/klasyfikacje multi-tool w IntentManager.
   - Oznaczyc typ intencji jako "multi_tool".
2) Planowanie i routing
   - Zbudowac plan krokow (lista narzedzi, kolejnosc, wejscia/wyjscia).
   - Zintegrowac z Orchestrator/TaskDispatcher.
3) Egzekucja
   - Wykonac kroki sekwencyjnie, zapisac wyniki czastkowe w kontekcie.
   - Wprowadzic fallback dla krytycznych bledow.
4) UI/Logi
   - Pokazac plan i kroki w historii zadania.
5) Testy
   - Testy integracyjne multi-tool (bez E2E).

## Otwarte pytania
- Czy plan ma byc deterministyczny czy generowany przez LLM?
- Jakie narzedzia sa dozwolone w multi-tool na start (lista whitelist)?
- Czy wymagamy uzycia modelu do streszczenia na koncu?
