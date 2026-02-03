# Zadanie 103: Dokończenie i Weryfikacja Tłumaczeń (i18n)

**Status:** Planowanie / Review
**Priorytet:** Średni

## 1. Analiza Ilościowa
Stan na dzień: 2026-02-01

- **Baza (PL):** 370 kluczy
- **Angielski (EN):** 370 kluczy (100% pokrycia)
- **Niemiecki (DE):** 370 kluczy (100% pokrycia)

## 2. Zidentyfikowane Problemy
Mimo 100% pokrycia kluczy, analiza skryptowa wykazała ~30 potencjalnych "anglicyzmów" w języku niemieckim (wartości identyczne jak w EN).

**Lista do weryfikacji (DE):**
- `Queue` -> Sugerowane: *Warteschlange* (lub zostawić jako tech-term)
- `Shortcuts` -> Sugerowane: *Tastenkürzel*
- `Palette ⌘K` -> Sugerowane: *Befehlspalette*
- `Repository` -> Sugerowane: *Repository* (akceptowalne) lub *Projektarchiv*
- `LessonsStore` -> Tech-term (zostawić)
- `Models` / `Model Control Center` -> Weryfikacja spójności
- `Run` -> *Starten* / *Ausführen* (już jest 'Starten' w action, ale sprawdzić kontekst)
- `Limit` -> *Limit* (akceptowalne) lub *Begrenzung*

## 3. Plan Realizacji

### Etap 1: Decyzje Terminologiczne [ZAKOŃCZONE]
Ustalenie słownika dla terminów technicznych w DE:
- [x] Czy "Queue" tłumaczymy na "Warteschlange"? (Decyzja: Tak)
- [x] Czy "Repository" zostaje jako anglicyzm? (Decyzja: Tak)
- [x] Czy "Cockpit" zostaje? (Decyzja: Tak, nazwa własna modułu)

### Etap 2: Korekta `de.ts` [ZAKOŃCZONE]
- [x] Poprawić ewidentne braki (np. "Shortcuts" -> "Tastenkürzel")
- [x] Ujednolicić "Run" / "Start" (Run=Starten dla modeli, Ausführen dla komend)
- [x] Sprawdzić "Offline cache" -> "Offline-Speicher"? (OK)

### Etap 3: Testy
- [x] Przeklikać UI w trybie DE i sprawdzić czy długość słów nie łamie layoutu.
- [x] Sprawdzić tooltipy i placeholdery.

## 4. Pliki powiązane
- `web-next/lib/i18n/locales/pl.ts`
- `web-next/lib/i18n/locales/en.ts`
- `web-next/lib/i18n/locales/de.ts`

## 5. Analiza Podstron (Hardcoded Strings)
Stan na dzień: 2026-02-01
Analiza plików w `web-next/app/` wykazała liczne hardcodowane stringi w języku polskim, które nie korzystają z systemu i18n (`useTranslation` / `t()`).

### Krytyczne (Całe strony hardcoded)
Te strony wymagają pełnej refaktoryzacji pod i18n (teksty w UI, nagłówki, opisy, buttony, alerty).

1.  **`app/benchmark/page.tsx`**
    - Nagłówki: "Panel Benchmarkingu", "Testuj wydajność..."
    - Panele: "Krok 1", "Konfiguracja testu", "Wyniki porównawcze"
    - Loading states: "Ładowanie modeli..."
2.  **`app/inspector/page.tsx`** (Bardzo duży plik)
    - SectionHeading: "Inspector / Diagnostyka"
    - Statystyki: "Skuteczność", "Aktywne zadania"
    - Panele: "Kolejka requestów", "Diagnoza przepływu", "Kroki RequestTracer"
    - Diagramy Mermaid (Default diagram: "Wybierz request z listy")
    - Logika błędów i pustych stanów ("Brak historii", "Nie udało się pobrać...")
3.  **`app/strategy/page.tsx`** (Bardzo duży plik)
    - SectionHeading: "Strategia i roadmapa"
    - Buttony i akcje: "Odśwież Roadmapę", "Uruchom Kampanię", "Raport Statusu"
    - Alerty i Toasty: "Roadmapa utworzona", "Nie udało się..."
    - Logika biznesowa w UI: "Postęp wizji", "Milestones"

### Pomniejsze (Metadata i Fallbacki)
Te strony są głównie wrapperami, ale posiadają hardcodowane metadane lub stany ładowania.

4.  **`app/calendar/page.tsx`**
    - Metadata: `title` ("Kalendarz - Venom Cockpit"), `description`
    - Fallback: "Ładowanie kalendarza..."
5.  **`app/config/page.tsx`**
    - Metadata: `title`, `description`
    - Fallback: "Ładowanie konfiguracji..."
6.  **`app/layout.tsx`**
    - Metadata globalne: `title`, `description` ("Next.js frontend dla Venom...")

### Czyste (Wrappery)
Te strony wydają się korzystać z komponentów, które (prawdopodobnie) mają już i18n lub będą poprawiane osobno.
- `app/page.tsx` (CockpitWrapper)
- `app/brain/page.tsx` (BrainWrapper)
- `app/models/page.tsx` (ModelsViewer)
- `app/chat/page.tsx` (CockpitHome)


## 6. Master Plan Realizacji (Zaktualizowany)
Zgodnie z optymalną logiką wykonania:


### Faza 1: Instrumentacja i Ekstrakcja (PL) [ZAKOŃCZONE]
Celem jest usunięcie wszystkich hardcodowanych stringów z kodu `web-next` i zastąpienie ich funkcjami tłumaczącymi, początkowo tylko dla języka bazowego (PL).
- [x] **Instrumentacja**: W identified plikach (`benchmark`, `inspector`, `strategy`, `calendar`, `config`) dodać hook `useTranslation`.
- [x] **Ekstrakcja Local**: Zamienić hardcodowane stringi na klucze np. `strategy.vision.title` i dodać je TYLKO do `pl.ts`.

### Faza 2: Kolekcja i Standaryzacja (Common) [ZAKOŃCZONE]
Gdy cały kod korzysta już z kluczy, należy uporządkować słownik `pl.ts`.
- [x] **Analiza Powtórzeń**: Przeskanować `pl.ts` w poszukiwaniu powtarzających się wartości ("Zapisz", "Anuluj", "minuty", "Sukces").
- [x] **Wydzielenie `common`**: Przenieść te wartości do przestrzeni `common` (np. `common.actions.save`, `common.time.minutes`).
- [x] **Refaktor Kluczy**: Zaktualizować odwołania w kodzie (np. z `strategy.actions.save` na `common.actions.save`).

### Faza 2.5: Smoke Test (Punkt Kontrolny) [ZAKOŃCZONE]
- [x] **Weryfikacja**: Uruchomić aplikację w trybie PL i sprawdzić, czy wszystkie klucze (szczególnie `common`) ładują się poprawnie.

### Faza 3: Propagacja i Tłumaczenie (EN/DE) [ZAKOŃCZONE]
Dopiero na ustandaryzowanej strukturze wykonujemy tłumaczenia.
- [x] **Synchronizacja Struktur**: Skopiować strukturę JSON z `pl.ts` do `en.ts` i `de.ts` (jako puste/todo).
- [x] **Tłumaczenie**: Uzupełnić tłumaczenia EN i DE, zweryfikować "anglicyzmy" w DE.
- [x] **Formatowanie Danych**: Wdrożyć dynamiczne formatowanie dat/liczb (zamiast hardcoded `pl-PL`).

### Faza 4: API Status Mapping (NOWE) [ZAKOŃCZONE]
Obsługa dynamicznych statusów i błędów z backendu.
- [x] **Helper Statusów**: Stworzyć funkcję mapującą angielskie Enums (PENDING, COMPLETED) na klucze i18n.
- [x] **Implementacja UI**: Wdrożyć helper w `InspectorPage` (Badge) oraz `SystemStatusPanel`.
- [x] **Uzupełnienie Kluczy**: Dodać brakujące statusy do `pl.ts`, `en.ts`, `de.ts`.

### Faza 5: Weryfikacja Finalna
- [x] **Testy manualne**: Sprawdzenie UI w każdym języku (Static Audit).
- [x] **Audyt**: Sprawdzenie czy żaden hardcoded string nie pozostał na ekranach krytycznych (Grep Audit).
