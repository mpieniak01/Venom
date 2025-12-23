# 075: Prezentacja wyników obliczeń (formatowanie danych)
Status: do zrobienia

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
1. **Detekcja typu wyniku**
   - Lista list (tabela), lista obiektów, słownik, liczby, tekst.
2. **Formatowanie wyników**
   - Tabela tekstowa (monospace, wyrównane kolumny).
   - Listy punktowane dla struktur 1‑wymiarowych.
3. **UI**
   - Sekcja “Wynik obliczeń” w czacie (jeśli rozpoznany format).
4. **Płynne dostarczanie odpowiedzi**
   - Strumieniowe wyświetlanie fragmentów odpowiedzi (efekt „pisania”).
   - Ograniczenie częstotliwości renderu, aby nie destabilizować pola input.
   - Buforowanie i batchowanie aktualizacji (np. co 100–200 ms).
   - Po zakończeniu strumienia wykryj pełne formuły i prze-renderuj wynik zgodnie z zasadami obsługi formuł.
4. **Fallback**
   - Jeśli nie da się zinterpretować, pokaż surowe dane.

## Kryteria akceptacji
- Dla tablic 2D wynik jest czytelny i wyrównany.
- Dla list i słowników wynik jest czytelniejszy niż surowy `repr`.
- Brak regresji w standardowych odpowiedziach tekstowych.

## Dodatkowe zapisy (PR 075)
- W ramach tego PR należy dodać funkcje zasilające model w dodatkowe dane.
- Przykłady: pliki, linki, wskazywanie ścieżek do plików.

## Proponowane miejsca zmian
- Warstwa odpowiedzi LLM (formatter/post‑processor).
- UI chat (render wyników obliczeń).
- Testy jednostkowe formatera.

## Scenariusze testowe
1. Tablica mnożenia 10x10 → tabela z wyrównaniem.
2. Lista liczb → lista punktowana.
3. Słownik → tabela klucz‑wartość.
4. Tekst naturalny → brak zmian.
