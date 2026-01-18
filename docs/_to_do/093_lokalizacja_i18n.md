# Zadanie 093: Lokalizacja Aplikacji (i18n)

**Cel:** Pełna obsługa wielojęzyczności (PL, EN, DE) w całym interfejsie użytkownika.
Obecnie tłumaczenia są częściowe - niektóre elementy są "hardcoded" po polsku lub angielsku.

## Status Obecny
- [x] Podstawowa struktura `lib/i18n` (useTranslation hook).
- [x] Pliki językowe `pl.ts`, `en.ts`, `de.ts`.
- [x] Sekcja AuthorSignature (zrobiona w ramach wstępnego etapu 093).
- [ ] Większość podstron (Brain, Cockpit, Settings) ma braki w kluczach tłumaczeń.

## Zakres Prac

### 1. Przegląd i Ekstrakcja Tekstów (Hardcoded Strings)
Przejść przez główne ekrany i zamienić stringi na klucze `t("...")`:
- **Layout**: Sidebar, TopBar, SystemStatusBar (częściowo jest).
- **Brain**: Graph Overlay, HygienePanel, CacheManagement.
- **Cockpit**: Chat Interface, Input placeholders.
- **Settings**: Config Panel, Service Status.

### 2. Uzupełnienie Słowników (PL, EN, DE)
Dla każdego nowego klucza dodać tłumaczenia w 3 plikach:
- `locales/pl.ts`
- `locales/en.ts`
- `locales/de.ts`

### 3. Weryfikacja UX
- Sprawdzenie czy przełączanie języka (jeśli dostępne w UI, np. automatyczne) działa poprawnie.
- (Opcjonalnie) Dodanie przełącznika języka w Settings jeśli go brakuje (obecnie jest wykrywanie z przeglądarki).

## Kryteria Akceptacji
- Brak "hardcoded" tekstów w głównych ścieżkach użytkownika.
- Aplikacja wyświetla się poprawnie w języku angielskim i niemieckim (zmieniając locale w przeglądarce lub kodzie).
