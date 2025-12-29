# 080: Slash commands do wymuszania narzedzi (/gem, /gpt, /<tool>)
Status: zrobione

## Cel
Dodac dyrektywy w zapytaniu uzytkownika, ktore wymuszaja uruchomienie
konkretnego narzedzia/modelu poprzez prefiks ze znakiem ukosnika.
Przyklad: `/gem` (Gemini), `/gpt` (GPT). Analogicznie dla pozostalych tools.

## Zakres
- Parser polecen w warstwie wejscia (chat input / request parser).
- Auto-podpowiedz dostepnych narzedzi, nalezy przygotowac specjalny komponent
  serwujacy 3 podpowiedzi i filtrujacy je po wpisywanym tekscie uzytkownika.
- Routing do konkretnego narzedzia/modelu.
- Informacja zwrotna w UI (np. badge lub short text).
- Testy jednostkowe i integracyjne bez E2E.

## Zasady
- Prefiks `/gem` wymusza uzycie API Gemini.
- Prefiks `/gpt` wymusza uzycie API GPT.
- Prefiks `/<tool>` wymusza uzycie wskazanego toola.
- Prefiks musi byc pierwszy w linii (po ewentualnych bialych znakach).
- Po rozpoznaniu prefiksu, jest on usuwany z tresci promptu przekazywanej dalej.
- Gdy narzedzie nie istnieje -> czytelny komunikat bledu + fallback bez wymuszenia.
- Gdy wymuszony provider nie jest aktywny, zwracamy blad routingu (bez wykonania).
- Dla `/gem` i `/gpt` UI pyta o potwierdzenie globalnego przelaczenia runtime.

## Format polecen
Przyklady:
- `/gem Policz srednia z [1,2,3]`
- `/gpt Podsumuj ten tekst: ...`
- `/git Sprawdz status repo`

## Lista tooli i aliasow slash (propozycja)
Modele:
- `/gem` -> Gemini (LLM API: generowanie odpowiedzi)
- `/gpt` -> GPT (LLM API: generowanie odpowiedzi)

Tools (na podstawie `venom_core/execution/skills`):
- `assistant_skill` -> `/assistant` (operacje asystenta, pomocnicze akcje)
- `browser_skill` -> `/browser` (akcje w przegladarce)
- `chrono_skill` -> `/chrono` (czas, daty, pomiary)
- `complexity_skill` -> `/complexity` (estymacje zlozonosci/czasu)
- `compose_skill` -> `/compose` (skladanie/transformacje tresci)
- `core_skill` -> `/core` (operacje systemowe/core Venom)
- `docs_skill` -> `/docs` (generowanie dokumentacji/stron z markdown)
- `file_skill` -> `/file` (operacje na plikach)
- `git_skill` -> `/git` (operacje git w repo)
- `github_skill` -> `/github` (operacje GitHub API)
- `google_calendar_skill` -> `/gcal` (Google Calendar API)
- `huggingface_skill` -> `/hf` (HuggingFace API)
- `input_skill` -> `/input` (symulacja wejscia: mysz/klawiatura)
- `media_skill` -> `/media` (media: obraz/audio, generowanie)
- `parallel_skill` -> `/parallel` (uruchamianie wielu akcji rownolegle)
- `platform_skill` -> `/platform` (integracje platformowe, np. issues/PR)
- `render_skill` -> `/render` (renderowanie tabel/markdown/widgetow)
- `research_skill` -> `/research` (research, zrodla, podsumowania)
- `shell_skill` -> `/shell` (polecenia shell)
- `test_skill` -> `/test` (testy, raporty testowe/lint)
- `web_skill` -> `/web` (wyszukiwanie web)

Uwagi:
- Dla aliasow krotkich (np. `/gcal`, `/hf`) zachowujemy jednoznacznosc.
- Dodatkowe custom skills z katalogu `venom_core/execution/skills/custom` moga
  byc mapowane 1:1 na `/<skill_name>`.
- Wymuszenie toola mapuje sie na intencje/agenta (np. `/git` -> VERSION_CONTROL).

## Auto-uzupelnianie (doprecyzowanie)
- Aktywacja po wpisaniu `/` na poczatku pola (po opcjonalnych bialych znakach).
- Lista podpowiedzi pokazuje maks. 3 pozycje (priorytet: dopasowania prefix).
- Wpisywany tekst po `/` filtruje liste w czasie rzeczywistym.
- Klawiatura: strzalki gora/dol, Enter potwierdza wybor, Esc zamyka liste.
- Klik w podpowiedz wstawia pelny prefiks (`/gpt`, `/git`, itp.).
- Gdy brak dopasowan: pokaz "Brak dopasowan" i nie blokuj wpisywania.

## Kryteria akceptacji
- Dyrektywy `/gem` i `/gpt` zawsze wymuszaja odpowiedni routing.
- Dyrektywy `/<tool>` dzialaja dla wszystkich naszych tooli.
- UI pokazuje, ze uzyto wymuszonej sciezki.
- Brak regresji w standardowym flow bez prefiksu.

## Proponowane miejsca zmian
- Parser requestu / router intencji.
- Mapowanie tool-name -> executor.
- UI chat: etykieta przy odpowiedzi (np. "Forced: /gem").

## Scenariusze testowe
1. `/gem` + zwykle pytanie -> routing do Gemini.
2. `/gpt` + zwykle pytanie -> routing do GPT.
3. `/git status` -> uruchamia tool git.
4. Nieznany `/<tool>` -> komunikat bledu + fallback do standardowego flow.
5. Brak prefiksu -> zachowanie bez zmian.

## Realizacja
1) Logika rozpoznania dyrektyw
   - Dodano parser prefiksu w warstwie wejscia.
   - Zwrot: forced_tool / forced_provider / cleaned_prompt.
2) Routing i egzekucja
   - Mapowanie `/gem` -> provider Gemini, `/gpt` -> provider GPT.
   - Mapowanie `/<tool>` -> konkretna intencja/agent.
   - Obsluga bledu: brak toola => komunikat bledu i zatrzymanie zadania.
3) UI
   - Autouzuplenianie slash w cockpicie (3 podpowiedzi).
   - Badge/etykieta "Forced" przy odpowiedzi.
   - Potwierdzenie globalnego przelaczenia runtime dla `/gpt` i `/gem`.
4) Testy
   - Unit testy parsera slash.
   - Test API przełączania runtime.
   - UI smoke test `/gpt` (Playwright).
5) Docs
   - Uzupełniono dokumentacje w README (sekcja Cockpit).

## Notatki
- Wymuszenie `/gem` i `/gpt` działa przez globalny switch runtime.
- Informacja o wymuszeniu trafia do logow i jest widoczna w UI.
