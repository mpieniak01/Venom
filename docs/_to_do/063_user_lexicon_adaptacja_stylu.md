# 063: Adaptacja stylu użytkownika przez prywatny lexicon

## Cel
Dodać prywatny (poza repozytorium) lexicon użytkownika, który umożliwia adaptację do stylu zapytań bez zapisywania poufnych danych w Git.

## Założenia
- Bazowy lexicon pozostaje w repo (`venom_core/data/intent_lexicon_{pl,en,de}.json`).
- Lexicon użytkownika jest poufny i **nie trafia do gita**.
- System łączy lexicon bazowy + user‑lexicon w runtime.
- Uczenie dotyczy tylko nowych wariantów zapytań, nie „lekcji” narzędziowych.

## Zakres
1. **Prywatny katalog lexiconu**
   - Lokalizacja: `data/user_lexicon/intent_lexicon_user_{lang}.json`.
   - Dodać `data/user_lexicon/` do `.gitignore`.

2. **Ładowanie i merge**
   - `IntentManager` ładuje lexicon bazowy + user‑lexicon.
   - Merge: user‑lexicon nadpisuje/dodaje `phrases[]` dla intencji.

3. **Uczenie wariantów (adaptacja stylu)**
   - Uruchamia się tylko, gdy lexicon+fuzzy nie zwróci pewnego wyniku.
   - LLM używany jednorazowo do przypisania intencji.
   - Zapis wyłącznie krótkich fraz (np. < 8 słów) i bez URL/liczb.
   - Dla narzędzi: dopisuj wariant do user‑lexicon, **nie zapisuj lekcji**.

4. **Bezpieczeństwo i prywatność**
   - User‑lexicon nigdy nie jest commitowany.
   - Opcjonalna konfiguracja wyłączająca auto‑uczenie.

5. **Krótkie testy manualne (przeniesione z 061/062)**
   - „która godzina?” → TIME_REQUEST (bez LLM)
   - „jaka pogoda w Warszawie?” → powinno iść do pogody, nie do czasu
   - „status usług” → INFRA_STATUS
   - uruchomić po restarcie backendu

## Status
- [x] Prywatny katalog + .gitignore
- [x] Merge lexiconu bazowego i user‑lexicon
- [x] Auto‑dopisywanie nowych wariantów po rozpoznaniu intencji
- [x] Testy manualne (patrz niżej)
- [x] Tie‑breaker i fallback językowy

## Uwaga
- Dla zapytań poza narzędziami dodano obsługę `UNSUPPORTED_TASK` (osobny agent).
- `UNSUPPORTED_TASK` nie zapisuje nowych fraz do user‑lexicon.

## Wyniki testów manualnych
- TIME: OK → TIME_REQUEST, odpowiedź czasu bez LLM
- INFRA: OK → INFRA_STATUS, raport infrastruktury
- WEATHER: FAIL → błąd połączenia LLM (APIConnectionError)

## Wyniki testów lexicon/fuzzy (bez LLM)
- TIME: OK
- INFRA: OK
- HELP: OK
- VERSION_CONTROL: OK
- DOCUMENTATION: OK
- RESEARCH: OK
- CODE_GENERATION: OK
- COMPLEX_PLANNING: OK
- GENERAL_CHAT: OK
- UNSUPPORTED_TASK: OK (i brak zapisu do user‑lexicon)

## Ryzyka spójności (do zaplanowania)
1. **Brak jawnego źródła klasyfikacji**: nie wiadomo, czy wynik pochodzi z lexicon, keywords, LLM czy fallbacku.
2. **Brak tie‑breakera**: przy podobnych wynikach decyzja zależy od kolejności w słownikach.
3. **Zbyt wczesne wiązanie języka**: jeśli język rozpoznany błędnie, nie ma fallbacku do innych lexiconów.
4. **Brak informacji o top‑2 wynikach**: utrudnia diagnozę „dlaczego ten wynik”.

## Plan (kolejne kroki w 63)
- Dodać `intent_debug` do kontekstu zadania: `source`, `language`, `score`, `top2`.
- Dodać tie‑breaker: preferencja narzędzi lub „ambiguous → dopytaj”.
- Fallback językowy: gdy score < próg, przeszukaj wszystkie lexicony.

## Wykonane (transparencja decyzji)
- `intent_debug` jest zapisywany do kontekstu zadania i dostępny przez API.
- Zawiera: `source` (lexicon/keyword/llm/fallback), `language`, `score`, `top2`.
- Dla intencji bez LLM (`TIME_REQUEST`, `INFRA_STATUS`, `UNSUPPORTED_TASK`) metadane LLM są czyszczone w historii.
- Tie‑breaker: przy zbliżonych wynikach preferowane są intencje narzędziowe.
- Fallback językowy: gdy wynik dla wykrytego języka jest słaby, sprawdzane są wszystkie lexicony.

## Kryteria akceptacji
- Nowy plik user‑lexicon działa lokalnie bez udziału gita.
- Nowe warianty pytań użytkownika są zapamiętywane i działają offline.
- Brak zapisów lekcji dla narzędzi i bezpiecznych intencji.
- Zwiekszenie pokrycia testami do 65%

## Stan końcowy
- Zadanie 063 uznane za zakończone.

## Dokumentacja końcowa
- Opisać w `docs/_to_do/061_062_globalny_pipeline_umiejetnosci.md` jako etap adaptacji stylu.
- Wskazać katalog i zasady prywatności.
