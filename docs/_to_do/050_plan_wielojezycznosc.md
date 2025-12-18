# ZADANIE 050: Wielojęzyczność i standard tłumaczeń

## Cel
- Ustalić jeden bazowy język interfejsu (`pl-PL`) oraz sposób rozszerzenia o `en-US` i `de-DE`.
- Zapewnić przełącznik językowy (flagi) widoczny w top barze i nawigacji mobilnej.
- Przygotować strukturę plików tłumaczeń oraz zasady wdrażania, aby kolejne moduły mogły korzystać z tych samych kluczy.

## Stan na dziś
- Warstwa layoutów (TopBar, Sidebar, Mobile Nav, overlaye) korzysta już z `LanguageProvider` i kluczy w `web-next/lib/i18n/locales/*.ts`. Przełącznik języka zapisuje wybór w `localStorage`.
- Widoki produktowe (Cockpit, Brain, Strategy, Inspector) oraz kontrolki autonomii i kosztów nadal zawierają twardo zakodowane teksty PL (`AUTONOMY_LABELS`, komunikaty w `cockpit-home.tsx`, `brain-home.tsx` ~2.7k linii). Te moduły nie używają `t(...)`, więc brak spójności językowej.
- Skrypt `npm --prefix web-next run lint:locales` jest dostępny i spinany w CI; brakuje natomiast smoke testu Playwright sprawdzającego zmianę języka.

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
1. **Warstwa kontekstowa** *(✅ zrealizowana)*
   `LanguageProvider` i `useTranslation` działają globalnie (patrz `web-next/lib/i18n/index.tsx`). Wymaga jedynie utrzymania dokumentacji.
2. **Słowniki** *(w toku)*
   - Layout jest w słownikach, ale całe widoki (`components/cockpit/*`, `components/brain/*`, `components/inspector/*`, `components/strategy/*`) muszą zostać wyczyszczone z tekstów PL i przełączone na `t(...)`.
   - Konfiguracje w sidebarze (AUTONOMY_LABELS/DETAILS, confirmy trybu kosztów) trzeba przenieść do sekcji `sidebar.controls.*`.
3. **Fallback + walidacja** *(częściowo)*
   - `scripts/check-locales.ts` + `npm run lint:locales` działa.
   - Do zrobienia smoke test Playwright (np. `language-switcher.spec.ts`) weryfikujący zmianę języka i fallback przy braku klucza.
4. **Wersjonowanie** *(niezrobione)*
   - Potrzebna konwencja w PR (`## i18n`) i checklist tłumaczeń.
   - Po ukończeniu migracji można rozważyć integrację (Crowdin/Lokalise), ale najpierw ustalić prosty changelog tłumaczeń.

## Otwarte tematy
- Integracja z backendem (czy API zwraca opisy w jednym języku? jeśli tak, trzeba dodać mapowanie po stronie frontu).
- Strategia dla dokumentacji (`docs/`): na razie pozostaje po polsku, ale można rozważyć analogiczną strukturę MD dla EN/DE.
- Automatyczne pobieranie języka z przeglądarki – planowo po wdrożeniu contextu.

## Status realizacji
- [x] `LanguageProvider`, hook `useTranslation`, layouty i overlaye działają w oparciu o słowniki (`web-next/lib/i18n`).
- [ ] Cockpit, Brain, Strategy, Inspector oraz kontrolki autonomii/kosztów korzystają z tekstów PL wpisanych w kodzie – wymagają migracji do słowników.
- [ ] Brak testu Playwright potwierdzającego zmianę języka.
- [ ] Brak procedury wersjonowania tłumaczeń w PR.

## Wykonane kroki
- Dodano `LanguageProvider` (`web-next/lib/i18n`) z kontekstem, który przechowuje wybór języka w `localStorage`, posiada fallback na polski oraz udostępnia hook `useTranslation`. Warstwa jest podpięta globalnie w `app/providers.tsx`, więc każdy komponent może korzystać z `t(...)`.
- Przygotowano pierwsze słowniki `pl/en/de` (top bar, sidebar, mobile nav, paleta poleceń) – wszystkie klucze dla wymienionych modułów znajdują się w `web-next/lib/i18n/locales/*.ts`.
- Przepisano komponenty `TopBar`, `Sidebar`, `MobileNav`, `LanguageSwitcher` i `CommandPalette`, aby korzystały z nowych tłumaczeń. Zmiany obejmują także nawigację (etykiety modułów, przyciski) oraz podstawowe komunikaty w palecie poleceń.
- Lokalne słowniki zostały rozszerzone o sekcje `CommandCenter`, `QuickActions`, `Alert/Notification drawer`, `Service status` oraz kartę kolejki; odpowiadające komponenty korzystają z `useTranslation`, dzięki czemu całe doświadczenie overlayów reaguje na zmianę języka (łącznie z fallbackami, komunikatami błędów i przyciskami).
- Dodano skrypt walidujący spójność kluczy (`npm run lint:locales` → `scripts/check-locales.ts`) z wykorzystaniem `tsx`, dzięki czemu PR-y z tłumaczeniami wymagają identycznego zestawu kluczy w `pl/en/de`.
