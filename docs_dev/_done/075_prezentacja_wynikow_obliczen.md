# 075: Prezentacja wyników obliczeń (formatowanie danych)
Status: zrobione

## Cel
Po wykonaniu obliczeń przez model, prezentować wynik w czytelnej formie
(np. tabela, lista, wykres tekstowy), zamiast surowych struktur danych.

## Problem
Niektóre modele potrafią rozwiązywać zadania obliczeniowe, ale zwracają kod lub
surowe struktury bez prezentacji. Przykład: tablica mnożenia wygenerowana jako
lista list, a następnie wypisana bez formatowania.

## Przykład (case study)
Wejście użytkownika:
```
def generate_multiplication_table(size=10):
  """
  Generuje tablicę mnożenia od 1 do podanego rozmiaru.

  Args:
    size: Rozmiar tablicy (domyślnie 10).

  Returns:
    Tablica mnożenia jako listę list.
  """
  table = []
  for i in range(1, size + 1):
    row = []
    for j in range(1, size + 1):
      row.append(i * j)
    table.append(row)
  return table

def print_table(table):
  """
  Wyświetla tablicę mnożenia na konsoli.
  """
  for row in table:
    print(row)

# Generowanie tablicy mnożenia
multiplication_table = generate_multiplication_table()

# Wyświetlanie tablicy
print_table(multiplication_table)
```

Oczekiwane wyjście:
- Czytelna tabela (kolumny wyrównane).
- Ewentualne formatowanie nagłówków (1..N).

## Zakres
- [x] **Detekcja typu wyniku**
  - Lista list (tabela), lista obiektów, słownik, liczby, tekst.
- [x] **Formatowanie wyników**
  - Tabela tekstowa (monospace, wyrównane kolumny).
  - Listy punktowane dla struktur 1‑wymiarowych.
- [x] **UI**
  - Sekcja “Wynik obliczeń” w czacie (jeśli rozpoznany format).
- [x] **Płynne dostarczanie odpowiedzi**
  - Strumieniowe wyświetlanie fragmentów odpowiedzi (efekt „pisania”).
  - Ograniczenie częstotliwości renderu, aby nie destabilizować pola input.
  - Buforowanie i batchowanie aktualizacji (np. co 100–200 ms).
  - Po zakończeniu strumienia wykryj pełne formuły i prze-renderuj wynik zgodnie z zasadami obsługi formuł.
- [x] **Fallback**
  - Jeśli nie da się zinterpretować, pokaż surowe dane.

## Kryteria akceptacji
- Dla tablic 2D wynik jest czytelny i wyrównany.
- Dla list i słowników wynik jest czytelniejszy niż surowy `repr`.
- Brak regresji w standardowych odpowiedziach tekstowych.

## Dodatkowe zapisy (PR 075)
- [x] W ramach tego PR dodano funkcje zasilające model w dodatkowe dane.
- [x] Przykłady: pliki, linki, wskazywanie ścieżek do plików.

## Proponowane miejsca zmian
- Warstwa odpowiedzi LLM (formatter/post‑processor).
- UI chat (render wyników obliczeń).
- Testy jednostkowe formatera.

## Scenariusze testowe
1. Tablica mnożenia 10x10 → tabela z wyrównaniem.
2. Lista liczb → lista punktowana.
3. Słownik → tabela klucz‑wartość.
4. Tekst naturalny → brak zmian.

## Przypadek testowy (UI: chat)
Cel: potwierdzić, że wynik obliczeń jest wykrywany i renderowany w sekcji
„Wynik obliczeń” w czacie, a nie jako surowy JSON/lista.

### Kroki
1) Otwórz Cockpit chat w `web-next`.
2) Wyślij prompt:
```
Wygeneruj tablicę mnożenia 1..5 jako listę list, a potem pokaż wynik.
```
3) Poczekaj na zakończenie strumieniowania odpowiedzi.

### Oczekiwany rezultat (na ekranie chat)
- W treści odpowiedzi pojawia się sekcja „Wynik obliczeń”.
- W sekcji widać tabelę tekstową z wyrównanymi kolumnami 1..5.
- Brak surowego `[[1,2,3...]]` w miejscu prezentacji (może być w treści odpowiedzi,
  ale nie zamiast tabeli).
