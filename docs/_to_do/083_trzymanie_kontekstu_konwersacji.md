# 083: Trzymanie kontekstu konwersacji dla LLM
Status: do zrobienia

## Cel
Zapewnic ciaglosc rozmowy w czacie: model ma rozumiec, ze kolejne wiadomości to kontynuacja dialogu, mimo ograniczen okna kontekstu.

## Założenia
- Backend zarzadza stanem rozmowy; model nie ma wbudowanej pamieci miedzy wywolaniami.
- Wykorzystujemy trzy poziomy: okno ostatnich wiadomosci, streszczenia starszych fragmentow oraz pamiec dlugoterminowa (RAG/embeddings).
- Wsparcie dla wielu sesji czatu; kazda sesja ma wlasny identyfikator i bufor historii.

## Zakres
1. Okno kontekstu (short-term)
   - Ile ostatnich wiadomosci wysylamy do LLM (np. limit tokenow/wiadomosci).
   - Filtry: pomijanie logow systemowych/duzych plikow, odciete tresci powyzej limitu.
2. Streszczenia (mid-term)
   - Automatyczne skracanie starszych czesci rozmowy do krotkiego podsumowania.
   - Wstrzykiwanie streszczenia do promptu jako osobna sekcja.
3. Pamiec dlugoterminowa (long-term)
   - Zapisywanie kluczowych faktow/preferencji w wektorach (embeddings) + ewentualnie notatki strukturalne.
   - Retrieval przed zapytaniem i wstrzykniecie wynikow do promptu (RAG).
4. Persistencja
   - Gdzie zapisujemy historie/streszczenia/pamiec (np. pliki, DB, Redis, LanceDB).
   - Retencja i kasowanie starych danych.
5. API/UI
   - Identyfikator sesji w UI i backendzie.
   - Akcje: reset kontekstu, eksport, wlacz/ wylacz auto-streszczenia.
6. Bezpieczenstwo i limity
   - Maksymalna liczba tokenow wysylanych do LLM.
   - Maskowanie sekretow w historii.

## Proponowana realizacja (MVP)
- **Short-term**: trzymaj ostatnie N wiadomosci (np. 10-12) lub do limitu tokenow (np. 2k). Filtruj duze bloki kodu/JSON powyzej progu, zamieniajac je na placeholdery.
- **Mid-term**: po przekroczeniu 20-30 wiadomosci uruchamiaj streszczenie starszej czesci. Przechowuj jedno zbiorcze streszczenie + ewentualnie timestamp/wersje. Wstrzykuj do promptu jako blok "Summary".
- **Long-term**: kluczowe fakty i preferencje zapisuj jako embeddingi + notatki tekstowe. Przed kazdym zapytaniem wykonaj retrieval top-K (np. 3-5) i wstrzyknij sekcje "Relevant memory".
- **Sesje**: UI przesyla `session_id`, backend przechowuje historie w StateManager/DB. Reset/nowa sesja czysci okno i streszczenie, zostawia pamiec dlugoterminowa.
- **Limity**: buduj prompt w kolejnosci: system → summary → retrieved memory → historia (ostatnie wiadomosci) → biezace pytanie. Jesli prompt przekracza budzet tokenow, obcinaj najstarsze wiadomosci z okna.
- **Logi**: zapisuj streszczenia i decyzje trimowania w logach zadania (dla debugowania).

## Scenariusze testowe
1) Kontynuacja rozmowy z 15+ wiadomosciami: starsze czesci streszczone, nowe tresci nadal spiete.
2) Reset sesji: po resecie model nie widzi historii, ale preferencje z pamieci dlugoterminowej sa wstrzykiwane.
3) Limit tokenow: gdy prompt przekracza budzet, najstarsze wiadomosci sa obcinane, wynik nadal spójny.
4) Retrieval: pytanie o fakt zapisany w pamieci dlugoterminowej bez kontekstu bieżącego – model powinien odpowiedziec poprawnie.

## Otwarte pytania
- Jak przechowywac streszczenia i historie: w plikach, Redis czy DB? (decyzja zalezy od srodowiska)
- Kto wykonuje streszczenie: dedykowany prompt w backendzie czy agent? (koszt vs. latwosc)
- Jak dluga retencja pamieci dlugoterminowej? (per sesja, per uzytkownik)
- Czy dopuscic reczne pine-owanie faktow do pamieci, czy tylko automatycznie?
