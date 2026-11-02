# Katalog danych treningowych Venoma

Stan opisu i audytu: **2026-11-02**. Zakres: cztery wersje materiału operatora
repozytorium G01–G04 oraz zachowany podzbiór HF. To opis danych i ich ograniczeń,
nie raport skuteczności wytrenowanych modeli.

## Od czego zacząć

Kanoniczny lokalny katalog to `data/training/README.md`, a karty wersji znajdują
się w `data/training/catalog/G01.md`–`G04.md`. Korpusy, receptury, szczegółowe
manifesty i dowody pozostają lokalne, ignorowane przez Git. Ten dokument zawiera
wyłącznie podsumowanie; nie zawiera próbek rozmów, wyników narzędzi ani sekretów.
Na innym checkoutcie brak prywatnego katalogu nie oznacza, że dane nie istnieją.

Pierwotne opisy już istnieją:

| Wersja | Lokalny opis | Manifest tożsamości |
|---|---|---|
| G01 | `data/training/granite-g01-20261101/README.md` | `pilot-manifest.json` w tym katalogu |
| G02 | `data/training/granite-g02-material-20261101/README_PL.md` | `pilot-manifest.json` w tym katalogu |
| G03 | `data/training/granite-g03-material-20261102/README_PL.md` | `pilot-manifest.json` w tym katalogu |
| G04 | `data/training/granite-g04-material-20261102/README_PL.md` | `pilot-manifest.json` w tym katalogu |

Opis przygotowania danych może historycznie mówić „nie trenowano”. Aktualnego
stanu modelu szukaj w potwierdzeniach uruchomień, `selected-adapter.json` i
`current-experiment.json`; nie wyprowadzaj go z historycznego README materiału.
Procedura wykonania: [Zdalny trening](ZDALNY_TRENING.md).

## Co oznacza rekord

Jeden rekord domenowy to rozmowa `messages` z deklaracjami `tools`, metadanymi
pochodzenia, `record_id`, `problem_group`, podziałem, językiem i uprawnieniem
`training_allowed`. Zawiera propozycje asystenta, odpowiedzi narzędzi i zakończenie.
Jeden rekord nie jest jednym wywołaniem ani niezależnym problemem. Pary PL/EN i
warianty tego samego fixture'a zachowujemy w jednym podziale.

W domenie każde zadanie oferuje tylko:

- `Terminal(command)` — polecenie Bash w izolowanym repozytorium;
- `Finish(status, summary)` — wynik, pytanie o brak danych lub eskalację.

Materiał uczy generowania poleceń, interpretacji obserwacji i krótkich procedur.
Nie kwalifikuje całego produkcyjnego katalogu narzędzi Venoma ani dowolnego API.

## Wersje i zawartość

Liczby dotyczą rozmów domenowych; HF jest odrębnym podzbiorem.

| Wersja | Train | Validation | Rezerwa holdout | Zawartość |
|---|---:|---:|---:|---|
| G01 | 192 | 48 | brak osobnego holdout w manifeście danych | Git, wyszukiwanie, pliki, logi, testy, małe zmiany, wybór działania i brakujące argumenty |
| G02 | 256 | 64 | brak osobnego holdout w manifeście danych | Dokładny zakres zmian, odzyskiwanie po błędach narzędzi, weryfikacja po zmianie, błędy kolekcji testów, odczyt konfiguracji |
| G03 | 320 | 96 | 32 | Cały G02 oraz doprecyzowanie i kontynuacja, bezpośrednie wykonanie, odkrywanie testów, Git i filtrowanie logów |
| G04 | 640 | 176 | 112 | Cały G03 oraz wiązanie parametrów i usług, dwa zestawy testów, integralność, runtime/interpreter, importy, naprawa, logi zadań, GPU/kolejka i SSH |

G04 to 320 fixture'ów treningowych w parach PL/EN (320 + 320 rozmów), 88
walidacyjnych i 56 w rezerwie. To nie 640 niezależnych zadań treningowych.

**Nie sumować wersji jako niezależnych korpusów:**

- G03 zachowuje dokładnie wszystkie 256/64 rozmów G02 i dodaje 64/32.
- G04 zachowuje wszystkie 320/96 rozmów G03 i dodaje 320/80.
- G01 jest wcześniejszym materiałem; audyt nie znalazł identycznych rozmów
  `messages + tools` między G01 i G02. Nie jest on dokładną retencją w G02.
- Retencja poprzedniej wersji i pochodzenie dodatku są zapisane w manifestach.

## Podzbiór HF

W każdej wersji są te same **61 train / 14 validation**, z `nvidia/When2Call`
i `Team-ACE/ToolACE`; nie są automatycznie domieszane do `domain`.

W train jest 46 rozmów doprecyzowujących i 15 pojedynczych rund narzędziowych.
Pierwsza odpowiedź wybiera narzędzie tylko w 15/61 rozmów. Pozostałe 46 to tekstowe
pytania o brakujące dane. Deklaracje oferują od jednego do sześciu narzędzi.
Zachowujemy źródła, rewizje, licencje i mapowania nazw z lokalnych metadanych.
Są to etykiety źródłowe sprawdzone strukturalnie, bez niezależnego ponownego
wykonania narzędzi. Nie przedstawiać ich jako wykonanych demonstracji.

## Znane właściwości jakości

Audyt z 2026-11-02 potwierdził zgodność hashy i liczebności wszystkich 16 plików
train/validation z manifestami, poprawny kontrakt rozmów oraz schematy argumentów
nadzorowanych wywołań. Nie uruchamiał poleceń z rekordów ani modeli.

- G01: po porównaniu `messages + tools`, z pominięciem metadanych, pozostało
  166 unikalnych rozmów train i 28 validation; odpowiednio 26 i 20 nadmiarowych
  kopii. Nie mylić duplikatu treści z duplikatem `record_id` — tych nie wykryto.
- G02–G04: brak dokładnych duplikatów rozmów wewnątrz poszczególnych podziałów.
- Nie wykryto przecięcia `problem_group`, identyfikatorów fixture'ów ani dokładnych
  promptów użytkownika po normalizacji cyfr, odstępów i wielkości liter między
  train i validation. Porównano łączny tekst tur użytkownika w rozmowie, nie
  wszystkie możliwe prefiksy. To nie jest gwarancja niezależności semantycznej.
- Rezerwy G03/G04 mają `training_allowed=false` i pozostają poza manifestem
  treningowym. Współdzielą jednak rodziny autorskich szablonów z treningiem;
  są diagnostyczne, nie stanowią niezależnego końcowego benchmarku.
- Brak niezależnego przeglądu człowieka. Audyt danych nie dowodzi jakości modelu.

G02–G04 mają `supervised_assistant_indices` i `context_only_assistant_indices`.
Błędne wcześniejsze demonstracje pozostają kontekstem. Nie wolno po konwersji
uczyć wszystkich tur asystenta bez odtworzenia tego wyboru. W G04 zachowane jest
32 takich wyłączonych tur train i 16 validation; audyt nie znalazł przecięcia
wyłączonych tur z celami nadzorowanymi. System, użytkownik i wyniki narzędzi
pozostają poza funkcją straty. G01/HF bez selektora nadzorują wszystkie tury
asystenta zgodnie z kontraktem encodera.

## Dopasowanie do modeli

Dane kanoniczne nie są gotowym, uniwersalnym eksportem dla każdego tokenizera.

| Model / rola | Ustalenie i potrzebne dostosowanie |
|---|---|
| Granite 4.2 3B — operator | Obecny trener, encoder i parser są przypięte do tej bazy oraz rewizji; profile QLoRA/LoRA nie kwalifikują innych checkpointów. |
| FunctionGemma 270M — interpreter funkcji | Materiał nadaje się na źródło krótkich decyzji. Potrzebne są natywny format FunctionGemma, rola developer, obsługa wyników funkcji i zachowanie masek. Parser eksperymentalny już istnieje; dostrajanie pozostaje niezakwalifikowane. |
| Granite Nano 350M — krótkie procedury | Ustalić konkretny `ibm-granite/granite-4.0-350m` lub `granite-4.0-h-350m`, nowy profil i natywny renderer/parser 4.0. Udokumentowane wywołanie JSON Nano jest odrzucane przez parser 4.2 (`invalid_granite_function`). |

FunctionGemma ma bazowy trening single-turn/parallel; dłuższe zależne procedury
wymagają osobnego dostrojenia i oceny. Nie oznacza to, że są niemożliwe.
[Format i ograniczenia Google](https://ai.google.dev/gemma/docs/functiongemma/formatting-and-best-practices),
[karta FunctionGemma](https://huggingface.co/google/functiongemma-270m-it).
Granite Nano ma własny format wywołań:
[karta 350M](https://huggingface.co/ibm-granite/granite-4.0-350m),
[karta H-350M](https://huggingface.co/ibm-granite/granite-4.0-h-350m).

Dla wąskiego interpretera przygotować osobny eksport wyboru funkcji i argumentów,
z przypadkami braku danych, niedostępnej operacji i mylących narzędzi. Przykładowe
nowe funkcje `git_status` czy `run_tests` są propozycją takiego kontraktu, a nie
nazwami już zakwalifikowanego zestawu w tych danych. Dłuższe naprawy i dowolny Bash
oceniać osobno. Tokeny i granice masek trzeba przeliczyć natywnie dla nowego modelu;
liczby tokenów z Granite 4.2 nie są pomiarem dla Gemmy lub Nano.

## Jak używać zapisanej analizy zamiast zaczynać od nowa

1. Przeczytać ten katalog i lokalną kartę wersji. Porównać pliki wskazane przez
   `pilot-manifest.json` z `catalog/analyses/2026-11-02/provenance.json`.
2. Przy identycznych hashach i niezmienionym schemacie wykorzystać dotychczasowe
   liczebności, deduplikację, pochodzenie i sprawdzenia podziału. Nie powtarzać
   pełnego profilowania tylko dlatego, że zmienił się model lub numer commita.
3. Zmiana checkpointu/tokenizera wymaga nowych sprawdzeń serializacji, masek,
   protokołu, limitów i zachowania modelu; nie unieważnia sama w sobie audytu
   niezmienionego źródłowego JSONL.
4. Nowe wiersze lub inny schemat wymagają nowej wersji i audytu zmienionego zakresu,
   z porównaniem względem zachowanego rodzica. Nie edytować zamrożonych wersji
   ani historycznych dowodów w celu uzyskania lepszego wyniku.
5. Brak lokalnych dowodów oznaczyć jako brak weryfikacji. Sam status PASS w
   manifeście nie zastępuje wyników kontroli. Nie promować diagnostycznej oceny
   do niezależnego dowodu skuteczności.

Trwały zapis audytu: `data/training/catalog/analyses/2026-11-02/`:
`audit.py`, `audit.json`, `additional.json`, `integration-checks.json`,
`assessment.json`, `provenance.json`. Pierwotne kopie w `test-results` mogą zostać
usunięte jako cache; kopia w katalogu danych pozostaje źródłem do ponownego użycia.
Skrypt audytu wymaga lokalnego venv z `jsonschema` i kodu Venoma; po przeniesieniu
hosta należy świadomie zmienić zapisany katalog źródłowy. Ponowne wykonanie skryptu
jest opcjonalne i uruchamia wyłącznie kontrole CPU, nigdy polecenia z rekordów.
Skrypt zapisuje wyniki obok własnego pliku: przed ponownym wykonaniem skopiować go
do nowego katalogu audytu, aby nie nadpisać zachowanych wyników i ich hashy.

Status uruchomień, wybór adaptera i wyniki modeli opisuje odrębny
[proces treningu](ZDALNY_TRENING.md), nie niniejszy katalog danych.
