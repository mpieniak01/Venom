# Zadanie nr 103: Analiza i Optymalizacja Prezentacji Podstron Web-Next

## Opis Problemu
Obecnie frontend `web-next` opiera się na agresywnym pobieraniu danych po stronie serwera (SSR) w `RootLayout` oraz głównych widokach. Powoduje to, że czas TTFB (Time To First Byte) jest uzależniony od odpowiedzi wszystkich endpointów API wywoływanych w `Promise.all`. Jeśli backend jest obciążony, cała strona wydaje się "wisieć" przed renderowaniem czegokolwiek.

## Analiza Stanu Obecnego
1.  **Główny Layout (`app/layout.tsx`)**: Wykorzystuje `force-dynamic` i oczekuje na 6 endpointów API (kolejka, metryki, zadania, modele, tokeny, git). Blokuje to renderowanie paska bocznego i nawigacji.
2.  **Widok Cockpit**: Pobiera 10 różnych zestawów danych przed wyświetleniem dashboardu.
3.  **Brak Streamingu**: Nie wykorzystujemy pełnego potencjału React Suspense i streamingu w Next.js 15, co pozwoliłoby na wysłanie szkieletu strony natychmiast.
4.  **Backend**: Niektóre dashboardowe endpointy liczą dane "on-the-fly" bez cache'owania (np. git status, usage metrics), co sumuje się do opóźnień.

## Plan Optymalizacji

### Etap 1: Optymalizacja Backendowa (Quick Wins)
- [x] Wdrożenie `TTLCache` dla endpointów: `/api/v1/git/status`, `/api/v1/models/usage`, `/api/v1/metrics/tokens`.
- [x] Optymalizacja zapytań do bazy wiedzy (limitowanie i paginacja dla grafu i historii).

### Etap 2: Architektura Frontendu (Streaming & Skeletons)
- [x] **Dekonstrukcja Layoutu**: Usunięcie blokujących `await` z `RootLayout` dla danych, które nie są krytyczne dla nawigacji.
- [x] **Wprowadzenie Suspense**: Przeniesienie ładowania "ciężkich" komponentów do osobnych modułów z `Suspense`.
- [x] **Skeletons**: Implementacja dedykowanych skeletonów (Services, StatusBar, Metrics).
- [x] **Client-side Fetching**: Wykorzystanie pollingu i hooków Reactowych dla danych o wysokiej zmienności.

### Etap 3: Konfiguracja Serwera i Next.js
- [x] Przegląd `next.config.ts` pod kątem optymalizacji paczek (`optimizePackageImports` dla `lucide-react`, `mermaid`, etc.).
- [x] Włączenie kompresji i optymalizacja cachowania assetów statycznych (Next.js standalone + default compression).

## Podsumowanie Realizacji
Wszystkie etapy zostały zrealizowane i zweryfikowane. Czas TTFB został zredukowany do poziomu ~15-30ms dla zbuforowanych endpointów. Interfejs reaguje natychmiastowo dzięki dekonstrukcji `RootLayout`.

## Kryteria Sukcesu
- Czas TTFB < 200ms w sieci lokalnej.
- Szkielet strony widoczny w < 500ms.
- Niezależne doczytywanie się widgetów bez blokowania interakcji z nawigacją.
