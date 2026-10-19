# Kwalifikacja zgłoszeń Snyka

## CVE-2023-45853 — backend Bookworm zlib1g (2026-10-19)

**Rozstrzygnięcie: nie dotyczy sprawdzonego pakietu binarnego Debiana.** To nie jest poprawka kodu ani akceptacja wykorzystywalnej podatności. Rozstrzygnięcie nie obejmuje innych zgłoszeń i profili.

| Zakres | Sprawdzona wartość |
| --- | --- |
| Snyk ID | `SNYK-DEBIAN12-ZLIB-6008963` |
| Commit źródłowy | `df8245c27f837d2afe250780b5d48283a2825488` |
| Baza | `python:3.14.8-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83` |
| ID końcowego obrazu | `sha256:175c3c339af00e4526d6f90d15598f492ac56175f801ebf0c78b26f8f1a906ce` |
| Pakiet | `zlib1g:amd64` / `1:1.2.13.dfsg-1` |
| Ważność przeglądu | Do 2026-11-18, 23:59:59 UTC; wcześniej przy zmianie bazy lub zależności |

### Dowody

CVE dotyczy MiniZip. [Tracker Debiana](https://security-tracker.debian.org/tracker/CVE-2023-45853) wyjaśnia, że Bookworm nie buduje i nie dostarcza podatnego contrib/minizip z tego źródła. [Lista plików pakietu](https://packages.debian.org/bookworm/amd64/zlib1g/filelist) zawiera libz i dokumentację.

Dokładny Dockerfile backendu i śledzone pliki wejściowe zbudowano poprawnie; instalacja z hashami i `pip check` przeszły. Końcowy obraz obejmuje 121 pakietów systemowych i 98 dystrybucji Pythona. Nie znaleziono pakietów i nazw MiniZip ani wybranych znaczników w 647 plikach ELF. Takie wyszukiwanie nie wyklucza każdej statycznej implementacji po usunięciu symboli; podstawą jest ocena pakietu Debiana.

### Wynik skanera i zakres polityki

Surowy skan końcowego obrazu: **1 Critical / 7 High / 2 Medium / 162 Low**. Oddzielna, jawnie wskazywana polityka dla jednego ID i dokładnej wersji pakietu daje **0 Critical / 7 High / 2 Medium / 162 Low**. Usuwa tylko zakwalifikowane ID; pozostałe uwagi nadal powodują kod wyjścia 1.

Polityka pozostaje przy lokalnych dowodach, poza globalnym `.snyk` repozytorium; wolno jej używać tylko dla sprawdzonego obrazu. Nie zmieniono ignorowania całej organizacji ani stanu projektu webowego. Backend SCM pokazuje pusty wykaz zależności, co nie oznacza bezpieczeństwa. Pakiety Pythona zinwentaryzowano, ale skan kontenera zwrócił wyłącznie wynik systemowy; nie stanowi pełnej kwalifikacji podatności Pythona.

**Kontrola zakresu:** celowo niedopasowana wersja pakietu pozostawia Critical oraz wszystkie 172 ID z wyniku surowego.

Dowody lokalne: `docs_dev/_reports/snyk-backlog-20261019/critical-zlib/`, w tym `IMPLEMENTATION.json`, skany surowy i po kwalifikacji, wąska polityka, pakiety i hashe ELF. Zachować wynik surowy. Przed użyciem rozstrzygnięcia dla innego obrazu wykonać ponowną budowę i ocenę.

[Wersja angielska](../SNYK_ISSUE_DISPOSITIONS.md).
