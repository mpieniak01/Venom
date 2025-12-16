# ZADANIE 050: Wielojęzyczność i standard tłumaczeń

## Cel
- Ustalić jeden bazowy język interfejsu (`pl-PL`) oraz sposób rozszerzenia o `en-US` i `de-DE`.
- Zapewnić przełącznik językowy (flagi) widoczny w top barze i nawigacji mobilnej.
- Przygotować strukturę plików tłumaczeń oraz zasady wdrażania, aby kolejne moduły mogły korzystać z tych samych kluczy.

## Stan na dziś
- Większość widoków `web-next` została przetłumaczona na polski (Cockpit, TopBar, Sidebar, Quick Actions, Command Center, Alert/Notification drawers, Service status, Mobile nav).
- Do top barów dodano `LanguageSwitcher`, który zapamiętuje wybór (`pl/en/de`) w `localStorage` i komunikuje docelowy kierunek zmian (flagi + skrót języka).
- Tłumaczenia nadal są osadzone jako stringi w komponentach – potrzebny jest wspólny magazyn tekstów.

## Standard tłumaczeń
1. **Struktura katalogów**
   - `web-next/locales/pl.ts`, `en.ts`, `de.ts` – eksport obiektu `{ common: { ... }, cockpit: { ... } }`.
   - Używać krótkich kluczy `module.section.key`, np. `cockpit.topBar.alerts`.
2. **Dostęp z komponentów**
   - W `web-next` tworzymy `LanguageProvider` (Context API) z hookiem `useTranslation()`:
     ```ts
     const translations = { pl, en, de };
     const LanguageContext = createContext({ lang: "pl", setLang: () => {}, t: (path) => string });
     ```
   - Hook zwraca `t("common.alertCenter")`, fallback do `pl` jeśli brakuje klucza.
3. **Konwencje**
   - Język bazowy: polski. Przy dodawaniu nowych tekstów najpierw aktualizujemy `pl.ts`, a następnie zadania na tłumaczenie `en/de`.
   - Nazwy modułów (Cockpit, Brain itd.) mogą pozostać brandowe, ale opisy/hinty koniecznie w słownikach.
   - Teksty techniczne (`/api/v1/...`, `AutonomyGate`) zostają w oryginalnej formie, ale otaczający opis polski.

## Plan wdrożenia
1. **Warstwa kontekstowa**
   - Utworzyć `LanguageProvider` w `web-next/app/layout.tsx`, czytający wybór z `localStorage` i obsługujący `LanguageSwitcher`.
   - Udostępniać `setLanguage` do istniejącego przycisku (aktualnie tylko cyklicznie zmienia stan lokalny – docelowo ma ustawiać kontekst).
2. **Słowniki**
   - Wyekstrahować wszystkie teksty z layoutu (`top-bar`, `sidebar`, `mobile-nav`, `command-center`, `quick-actions`, `alert-center`, `history`, `brain`, `inspector`, `strategy`) do kluczy.
   - Uzupełnić angielski i niemiecki plik, zachowując krótkie zdania, bez skrótów.
3. **Fallback + walidacja**
   - Dodać test typu `npm run lint:locales`, który sprawdza spójność kluczy (`Object.keys(pl) === Object.keys(en)`).
   - W Playwright dodać smoke test, który klika flagę i oczekuje zmiany etykiety (np. `data-testid="topbar-alerts"`).
4. **Wersjonowanie**
   - Każdą zmianę tekstu opisujemy w PR w sekcji `i18n`, aby tłumacze EN/DE wiedzieli co aktualizować.
   - Docelowo można spiąć to z Crowdin/Lokalise, ale na start wystarczy ręczna aktualizacja plików.

## Otwarte tematy
- Integracja z backendem (czy API zwraca opisy w jednym języku? jeśli tak, trzeba dodać mapowanie po stronie frontu).
- Strategia dla dokumentacji (`docs/`): na razie pozostaje po polsku, ale można rozważyć analogiczną strukturę MD dla EN/DE.
- Automatyczne pobieranie języka z przeglądarki – planowo po wdrożeniu contextu.

## Status realizacji
- Całość wdrożenia i18n zostanie domknięta dopiero po zakończeniu porządkowania struktury serwisu/UI (zadanie 051). Do tego czasu utrzymujemy istniejący `LanguageProvider` i słowniki, ale nie rozszerzamy tłumaczeń na kolejne moduły.

## Wykonane kroki
- Dodano `LanguageProvider` (`web-next/lib/i18n`) z kontekstem, który przechowuje wybór języka w `localStorage`, posiada fallback na polski oraz udostępnia hook `useTranslation`. Warstwa jest podpięta globalnie w `app/providers.tsx`, więc każdy komponent może korzystać z `t(...)`.
- Przygotowano pierwsze słowniki `pl/en/de` (top bar, sidebar, mobile nav, paleta poleceń) – wszystkie klucze dla wymienionych modułów znajdują się w `web-next/lib/i18n/locales/*.ts`.
- Przepisano komponenty `TopBar`, `Sidebar`, `MobileNav`, `LanguageSwitcher` i `CommandPalette`, aby korzystały z nowych tłumaczeń. Zmiany obejmują także nawigację (etykiety modułów, przyciski) oraz podstawowe komunikaty w palecie poleceń.
- Lokalne słowniki zostały rozszerzone o sekcje `CommandCenter`, `QuickActions`, `Alert/Notification drawer`, `Service status` oraz kartę kolejki; odpowiadające komponenty korzystają z `useTranslation`, dzięki czemu całe doświadczenie overlayów reaguje na zmianę języka (łącznie z fallbackami, komunikatami błędów i przyciskami).
- Dodano skrypt walidujący spójność kluczy (`npm run lint:locales` → `scripts/check-locales.ts`) z wykorzystaniem `tsx`, dzięki czemu PR-y z tłumaczeniami wymagają identycznego zestawu kluczy w `pl/en/de`.
