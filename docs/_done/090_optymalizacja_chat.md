# 090: Optymalizacja chat (zadanie)


## Cel
Poprawa jakosci i przewidywalnosci rozmowy w trybie NORMAL i DIRECT: mniej "zaciec", brak wyciekow promptow kontekstowych do czatu, szybszy feedback dla uzytkownika, spojnosc historii sesji po restarcie serwera.
**Uwaga:** Zmiany obejmują wyłącznie tryby **DIRECT** i **NORMAL**. Tryb **COMPLEX** (Architect/High-Level Planning) nie był objęty zakresem tych prac i funkcjonuje na dotychczasowych zasadach.

Zalozenie: okno chat pokazuje tylko pytanie uzytkownika i odpowiedz. Wszystkie dodatkowe informacje (kontekst, hidden prompts, parametry, routing) sa ujawniane dopiero po kliknieciu "Szczegoly".


## Zakres
- UI: zachowanie stanu generowania, fallback gdy SSE/polling nie dowozi odpowiedzi.
- Backend: spojnosc session_id i czyszczenie kontekstu po restarcie.
- Hidden prompts: polityka wiedzy i kuratorstwo.
- Observability: jasny sygnal co jest zrodlem odpowiedzi (history/session/hidden).

## Obserwacje (problem)
- Tryb NORMAL nie pokazuje stalego stanu generowania i potrafi utknac bez finalnej odpowiedzi.
- W czacie potrafia pojawiac sie bloki [KONTEKST SESJI] / [HISTORIA SESJI] (ukryte prompty).
- Po restarcie serwera uzytkownik widzi hidden prompts sprzed restartu, co jest mylone z historia sesji.
- Rozpoznanie: hidden prompts sa trwale i globalne, ale brak polityki kwalifikacji prowadzi do "bledow wiedzy".

## Zadania do wykonania (plan)
### A) UX i frontend chat
- [x] Stabilny ekran generowania dla NORMAL (takze bez danych SSE).
- [x] Wyeliminowanie "utknietych" odpowiedzi (fallback na session history).
- [x] Czytelny sygnal skad pochodzi odpowiedz: live/ history/ hidden.
- [x] Zabezpieczenie przed wyswietleniem hidden promptow w czacie (tylko w szczegolach).
- [x] W "Szczegoly" pokazac pelny payload przekazany do modelu (kontekst, hidden prompts, parametry generacji, runtime).
- [x] Tryb DIRECT: zachowac maszynopisanie (streaming znak po znaku).
- [x] Tryb NORMAL: zweryfikowac czy mozna pokazac maszynopisanie bez naruszenia weryfikacji odpowiedzi
      (albo potwierdzic, ze odpowiedz jest weryfikowana i musi pojawic sie dopiero po walidacji).

### B) Backend i sesje
- [x] Weryfikacja ze session_id resetuje sie po zmianie boot_id.
- [x] Jasna semantyka /clear: czy czysci tylko StateManager czy tez SessionStore.
- [x] Walidacja ze sesja czatu nie miesza sie z per-prompt contextem.

Ustalenia walidacyjne:
- Kontekst sesji jest budowany z SessionStore po session_id i dolaczany jako osobny blok.
- Per-prompt context bazuje na request.content i nie jest zapisywany do SessionStore bez session_id.
- Ryzyko "mieszania" wystepuje tylko gdy ten sam session_id jest swiadomie utrzymywany miedzy promptami.

### C) Hidden prompts - polityka wiedzy (do zrobienia)
Problem: aktualnie kazdy kciuk w gore moze zapisac prompt -> odpowiedz jako hidden prompt i wracac w kontekscie LLM-only. To prowadzi do "bledow wiedzy" (odpowiedzi jednorazowo poprawne, ale slabe, stylowe lub kontekstowe). Trzeba rozdzielic "pomoglo w tej sesji" od "wiedza do reuse".

Zasady kwalifikacji (propozycja):
- Tylko pytania o definicje/fakty/reguly o charakterze ogolnym.
- Brak kontekstu osobistego/projektowego i brak stylu (wiersze, humor, slang).
- Odpowiedz krotka, neutralna i wzorcowa (definicja + 1 przyklad).
- Aktywacja dopiero po powtorzeniu pytania (np. 2-3 razy) albo recznej akceptacji.
- Hidden prompts nie powinny byc zrodlem, gdy pytanie jest inne (tylko podobne do oryginalnego promptu).
- Gdy istnieje kciuk w gore dla identycznego promptu, odpowiedz powinna byc zwrocona z cache bez wywolywania LLM
- Wykorzystanie wiedzy analogicznie do rynkowych systemow opartych o LLM.

Weryfikacja (zrodla z internetu):
- OpenAI Cookbook opisuje "Search-Ask" (RAG): najpierw wyszukiwanie w bibliotece wiedzy, potem podanie znalezionych fragmentow do modelu. To potwierdza, ze wiedza jest zarzadzana przez warstwe wyszukiwania i reuse kontekstu, a nie tylko przez "ponowne pytanie" do LLM. Zrodlo: https://raw.githubusercontent.com/openai/openai-cookbook/main/examples/Question_answering_using_embeddings.ipynb
- LangChain (RedisCache / RedisSemanticCache) pokazuje praktyke cachowania odpowiedzi LLM i "semantic cache" dla podobnych zapytan, z naciskiem na ograniczenie powtorzonych wywolan i wykorzystanie podobienstwa semantycznego. To wspiera teze, ze odpowiedzi zaakceptowane (np. kciuk w gore) moga byc serwowane z cache dla identycznych/podobnych pytan. Zrodlo: https://raw.githubusercontent.com/langchain-ai/docs/main/src/oss/python/integrations/caches/redis_llm_caching.mdx


Oczekiwany efekt:
- Hidden prompts staja sie zaufana baza wiedzy, a nie "historia losowych lajkow".
- Mniej ryzyka wstrzykiwania blednych/nieadekwatnych odpowiedzi do kontekstu.

## Plan implementacji (z testami)

1) Zrodlo odpowiedzi (live/history/hidden)
- Ujednolicic pole `source` w API/front: live (SSE/response), history (SessionStore), hidden (cache/hidden prompt).
- Testy jednostkowe: mapowanie source dla kazdego typu eventu, blokada hidden w widoku czatu. **(zrealizowane: SessionStore utrzymuje `source`)**

2) Szczegoly: pelny payload do modelu
- Backend: zwracac w odpowiedzi: kontekst (session + per-prompt), hidden prompts (liczba + skrót), parametry generacji, runtime trace.
- Front: render w panelu Szczegoly (skroty, paginacja), ukrycie danych wrazliwych.
- Testy jednostkowe: serializacja payloadu i poprawne maskowanie/skrót dla hidden/context. **(zrealizowane: context_preview, generation_params, llm_runtime w HistoryRequestDetail + testy)**

3) Typing i weryfikacja odpowiedzi
- DIRECT: utrzymac stream znak-po-znaku.
- NORMAL: sprawdzic, czy mozna pokazac typing w trakcie walidacji; jesli nie, zostaje ekran generowania + publikacja po walidacji.
- Testy jednostkowe: stan frontu dla NORMAL bez SSE i z SSE; asercja, ze brak surowej odpowiedzi przed walidacja.

4) Baza wiedzy / cache (thumbs-up reuse)
- Polityka: kciuk w gore dla identycznego promptu => cache hit bez LLM; podobne promptu => semantic cache (prog podobienstwa, np. cos>0.85), TTL i wersjonowanie modelu.
- Integracja: warstwa retrieval (Search-Ask) przed LLM; cache RedisCache/RedisSemanticCache lub lokalny store.
- Testy jednostkowe: hit/miss dla identycznych promptow; hit/miss przy podobienstwie powyzej/pnizej progu; inwalidacja po zmianie model_version. **(zrealizowane: get_cached_hidden_response – priorytet aktywnych, min_score)**

5) Sesje i czyszczenie
- Potwierdzic reset session_id po zmianie boot_id; /clear czysci StateManager + SessionStore dla biezacego session_id.
- Testy jednostkowe: restart symulowany (boot_id zmiana) => nowe session_id; /clear nie usuwa innych sesji.

6) Hidden prompts – kontrola jakosci
- Kryteria: definicje/fakty, brak stylu/slangu, krotka odpowiedz; aktywacja po powtorzeniu lub recznej akceptacji.
- Testy jednostkowe: filtracja promptow stylizowanych; aktywacja dopiero po n-tej obserwacji lub explicite approve; brak wstrzykiwania hidden do czatu.

7) Monitoring i walidacja
- Logi: source, cache hit/miss, time-to-first-token, liczba hidden w kontekscie.
- Testy jednostkowe: poprawne logowanie eventow (mock logger), brak PII w logach.

## Stan wdrożenia 090 (co działa, co zostaje)
- Zaimplementowane: stabilny stan generowania NORMAL, fallback ze session history, label źródła odpowiedzi, blokada hidden w czacie, pełny payload w „Szczegóły” (context_preview, generation_params, llm_runtime, hidden count), testy utrzymania `source` w SessionStore, testy payloadu, cache hidden (get_cached_hidden_response) z priorytetem aktywnych wpisów i min_score, semantic cache (VectorStore/LanceDB + sentence-transformers).
- Do domknięcia: logi cache hit/miss + telemetry TTFB, e2e walidacja UI Szczegóły.

## Uwagi dot. modeli (jeden model produkcyjny)
- Aktualnie obowiązuje paradygmat jednego modelu generacyjnego; do semantic cache wykorzystano lokalny model embeddingów `sentence-transformers/all-MiniLM-L6-v2` oraz wbudowany `VectorStore` (LanceDB), minimalizując narzut infrastrukturalny. Zrealizowano "One runtime" w oparciu o istniejące komponenty.
## Kryteria akceptacji
- Uzytkownik widzi spójny stan generowania w NORMAL i DIRECT.
- Brak wyciekow promptow kontekstowych do czatu.
- Po restarcie serwera sesje sa resetowane lub jednoznacznie oznaczone.
- Hidden prompts sa kontrolowane i nie psuja jakosci odpowiedzi.
