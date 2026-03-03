# Web-Next Theming Guide (PL)

Ten dokument opisuje działanie globalnego systemu motywów w `web-next`, listę aktualnych motywów oraz sposób bezpiecznego dodawania i modyfikacji motywów.

## 1. Aktualne motywy

Zdefiniowane w `web-next/lib/theme-registry.ts`:

- `venom-dark` (domyślny)
- `venom-light`

Alias legacy (tylko migracyjnie, runtime):
- `venom-light-dev` -> `venom-light`

## 2. Przegląd architektury

Kluczowe pliki:

- `web-next/lib/theme-registry.ts`
  - identyfikatory motywów (`ThemeId`)
  - metadane motywów (`THEME_REGISTRY`)
  - mapa aliasów legacy (`LEGACY_THEME_ALIASES`)
  - fallback (`DEFAULT_THEME`)
- `web-next/lib/theme.tsx`
  - `ThemeProvider`, `useTheme`
  - priorytet źródeł:
    - `localStorage["venom-theme"]`
    - backend `UI_THEME_DEFAULT` z `/api/v1/config/runtime`
    - `DEFAULT_THEME`
  - normalizacja legacy:
    - `venom-light-dev` w localStorage jest przepisywany na `venom-light`
    - backendowe `UI_THEME_DEFAULT=venom-light-dev` jest mapowane na `venom-light`
  - best-effort sync do backendu po zmianie
- `web-next/app/layout.tsx`
  - bootstrap `html[data-theme]` przed hydratacją (ogranicza FOUC)
- `web-next/app/globals.css`
  - bazowe tokeny semantyczne w `:root`
  - nadpisania per-theme w `html[data-theme="<id>"]`
  - brak warstwy kompatybilności utility dla `venom-light-dev` (tylko canonical selector)
- `web-next/components/layout/theme-switcher.tsx`
  - globalny selektor motywu w TopBar
- `web-next/lib/i18n/locales/{pl,en,de}.ts`
  - etykiety i opisy motywów w UI

## 3. Jak dodać nowy motyw

1. Dodaj ID motywu do `web-next/lib/theme-registry.ts`:
   - dodaj `<id>` do `THEME_REGISTRY`
   - dodaj klucz tłumaczenia, np. `theme.options.<newTheme>`
2. Dodaj nadpisania tokenów CSS w `web-next/app/globals.css`:
   - utwórz blok: `html[data-theme="<id>"] { ... }`
   - nadpisuj tylko tokeny semantyczne (`--text-primary`, `--ui-border`, `--ui-surface` itd.)
3. Dodaj etykiety/opisy i18n we wszystkich locale:
   - `web-next/lib/i18n/locales/pl.ts`
   - `web-next/lib/i18n/locales/en.ts`
   - `web-next/lib/i18n/locales/de.ts`
4. Zweryfikuj testy:
   - `web-next/tests/theme-registry.test.ts`
   - `web-next/tests/theme-i18n-keys.test.ts`
   - `web-next/tests/theme-provider.component.test.tsx`
   - `web-next/tests/theme-switcher.component.test.tsx`
5. Uruchom walidacje frontendu:
   - `cd web-next && npm run lint`
   - `cd web-next && npm run test:unit:components`

## 4. Jak modyfikować istniejące motywy

Przy zmianach istniejącego motywu:

1. Zmieniaj przede wszystkim wartości tokenów w `web-next/app/globals.css`, chyba że trzeba zmienić logikę działania.
2. Unikaj hardcoded kolorów w komponentach. Preferuj zmienne semantyczne (`var(--...)`).
3. Pilnuj kontrastu (szczególnie tekst vs tło oraz stany przycisków).
4. Sprawdź oba motywy na kluczowych widokach:
   - Cockpit (`/`)
   - Models (`/models`)
   - Academy (`/academy`)
   - Config (`/config`)
5. Po zmianach tokenów uruchom testy unit/component.
6. Utrzymuj guardy stabilizacji:
   - brak `dark:` w `web-next/components` i `web-next/app`,
   - brak `venom-light-dev` w `web-next/app/globals.css`,
   - brak sekcji compatibility layer dla legacy utility klas.

## 5. Zalecany zakres tokenów

Preferowane tokeny semantyczne:

- Tekst: `--text-primary`, `--text-secondary`, `--text-heading`, `--ui-muted`
- Powierzchnie: `--bg-base`, `--bg-panel`, `--ui-surface`, `--surface-muted`, `--surface-overlay-*`
- Obrysy: `--ui-border`, `--ui-border-strong`, `--border-glass`
- Akcje: `--primary`, `--secondary`, zestaw tokenów przycisków
- Statusy: `--tone-success-*`, `--tone-warning-*`, `--tone-danger-*`, `--tone-info-*`, `--tone-neutral-*`
- Efekty: `--shadow-card`, `--app-shell-radial`, `--noise-image`

Unikaj dodawania osobnych, hardcoded palet per komponent, jeśli da się użyć istniejących tokenów.
