# ZADANIE 057: Podstawowe umiejetnosci asystenta

## Cel
Dopisac bazowe umiejetnosci, ktore powinny byc zawsze dostepne w asystencie.

## Istniejace umiejetnosci (nie dublowac)
Wykaz z `venom_core/execution/skills/`:
- browser_skill.py – przegladarka do testow E2E.
- chrono_skill.py – umiejetnosci czasowe (timeline/state).
- complexity_skill.py – ocena zlozonosci zadan.
- compose_skill.py – orkiestracja Docker Compose.
- core_skill.py – bezpieczne operacje na kodzie zrodlowym.
- docs_skill.py – generowanie dokumentacji.
- file_skill.py – operacje plikowe (sandbox).
- git_skill.py – operacje Git.
- github_skill.py – wyszukiwanie/analiza repozytoriow GitHub.
- huggingface_skill.py – wyszukiwanie modeli/datasets na Hugging Face.
- input_skill.py – kontrola myszy i klawiatury.
- media_skill.py – generowanie i przetwarzanie obrazow.
- parallel_skill.py – rownolegle przetwarzanie (Map-Reduce).
- platform_skill.py – integracje z platformami (GitHub/Discord/Slack).
- render_skill.py – wizualizacja i renderowanie UI.
- research_skill.py – skill badawczy z ingescia danych.
- shell_skill.py – wykonywanie komend shell (Docker sandbox).
- test_skill.py – wrapper na narzedzia testowe (DockerHabitat).
- web_skill.py – wyszukiwanie w Internecie (Semantic Kernel).

## Zakres
- "Podaj godzine" - zwracanie aktualnego czasu lokalnego.
- "Podaj pogode" - zwracanie aktualnej pogody dla podanej lokalizacji.
- "Sprawdz uslugi" - podsumowanie statusu uruchomionych uslug (start/stop/bledy).

## Wymagania
- Umiejetnosci maja dzialac bez dodatkowej konfiguracji po instalacji.
- Wynik ma byc krotki i jednoznaczny, z opcja rozszerzenia szczegolow na zyczenie.


## Status realizacji
- [ ] Zdefiniowano kontrakty i format odpowiedzi dla 3 umiejetnosci.
- [ ] Zaimplementowano komendy i testy podstawowe.
- [ ] Dodano dokumentacje uzycia.
