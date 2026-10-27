# Strategia testów — wdrożenie i pomiary

Gałąź robocza: codex/single-host-test-strategy. Wyniki dotyczą testów lokalnych wykonanych w osobnym checkoutcie, z izolacją sieci i wybranych zasobów hosta. Nie uruchamiano drugiej instancji Venoma ani modeli na potrzeby pomiarów.

## Czas grup

Przy rewizji 27a941e2 wykonano grupy symulowane kolejno:

| Grupa | Workery | Czas | Zaliczone | Pominięte |
| --- | ---: | ---: | ---: | ---: |
| Lekka (fast) | 4 | 161 s | 7254 | 10 |
| Średnia (long) | 2 | 79 s | 824 | 37 |
| Ciężka (heavy) | 1 | 5 s | 4 | 0 |
| **Razem** | — | **245 s (4 min 5 s)** | **8082** | **47** |

To czas wybranego zakresu symulowanego, a nie wszystkich testów repozytorium ani pełnego odbioru fizycznego. Przypadki oznaczone jako fizyczne, bezpośrednie modele, Docker i ręczne były wykluczone; część testów integracyjnych pozostaje pomijana. W obecnym raporcie JUnit liczba przypadków wykluczonych na etapie selekcji nie jest mierzona.

Lokalna bramka make pr-fast przeszła na późniejszej rewizji 5fafbdfa w **173,9 s (2 min 54 s)**. To osobny, mieszany zakres backendu i frontendu, nie suma trzech grup. Przy tym zestawie zmian nie było podlegających pomiarowi zmienionych linii kodu produkcyjnego po wyłączeniach Sonara; nie jest to dowód 100% pokrycia.

## Porównanie workerów dla grupy lekkiej

Trzy próby dla 2, 4 i 6 workerów oraz jedna próba bazowa dla 1 workera przy rewizji 5fafbdfa:

| Workery | Czas prób (s) | Mediana (s) | Maksymalna próbka RSS procesu i potomków |
| ---: | --- | ---: | ---: |
| 1 | 546,49 (jedna próba) | 546,49 | ok. 1,8 GiB |
| 2 | 287,88 / 287,66 / 287,64 | 287,66 | ok. 3,1 GiB |
| 4 | 160,51 / 161,35 / 161,31 | 161,31 | ok. 5,7 GiB |
| 6 | 125,90 / 123,38 / 124,50 | 124,50 | ok. 8,4 GiB |

Pamięć jest przybliżeniem z próbek co 2 sekundy: suma RSS procesów może liczyć wspólne strony wielokrotnie i pomijać krótkotrwałe szczyty. Czasy nie obejmują przygotowania zależności. Różnice obciążenia komputera mogą wpływać na wynik.

Domyślnie wybrano **4 workery** dla grupy lekkiej, aby ograniczyć obciążenie współdzielonego komputera. **6 workerów** jest opcją dla sytuacji, w których dostępne zasoby uzasadniają większe zużycie pamięci.


## Zakres i pozostała weryfikacja

- Inwentarz obejmuje 520 plików testów; 500 nadal nie ma ręcznie potwierdzonej klasyfikacji. Automatyczne sygnały w inwentarzu nie zastępują audytu. Izolacja połączeń w procesie pytest nie obejmuje wszystkich procesów potomnych i dostępu do systemu plików.
- W pierwotnych pomiarach grup nie wykonywano testów fizycznych ani E2E z istniejącym modelem. Później, przy wyłączonym Venomie, potwierdzono pominięcie profilu i testu live z powodem `stack_not_started`; stos przywrócono. Ręczny przepływ czatu i pojedynczy test live API przeszły na działającej instancji. Automatyczny lokalny profil modelowy pozostaje zablokowany przez `proxy_identity_unverified` do czasu bezpiecznego potwierdzenia powiązania panelu z API.
- GitHub PR #563: test przeglądarka → proxy → rzeczywiste API → kontrolowany testowy LLM przeszedł; symulowane smoke i functional dały odpowiednio 29 i 8 testów. Nie jest to test fizycznego modelu. SonarCloud dla `34ca095b` przeszedł Quality Gate i wykazał zero otwartych zgłoszeń dla PR; nie wskazał linii nowego kodu do pomiaru, więc wynik nie dowodzi pokrycia frontendu.
- PR na GitHubie przy `34ca095b`: 91 plików i 1253 testy, 91 s pytesta; 14 progów plików spełniono. Pełna regresja symulowana na technicznej gałęzi [40570117886](https://github.com/mpieniak01/Venom/actions/runs/40570117886) przeszła przed końcowymi poprawkami frontendu i selektora: 7265 + 832 + 4 testy backendu, zadanie 11 min 27 s wraz z przygotowaniem; zadanie frontendu 6 min 12 s. Zadania działały równolegle.
- CodeRabbit wstrzymał automatyczną recenzję końcowego commita. W logu symulowanego smoke wystąpił błąd hydracji identyfikatora sesji; zielony przebieg nie oznacza czystej konsoli.
- Wyniki grup pochodzą z 27a941e2, a benchmark workerów i pr-fast z 5fafbdfa. Nie należy traktować ich jako pomiarów identycznej rewizji.
