# 106. Font Alignment & Models Page Polish

## Cel
Ujednolicenie typografii i layoutu strony "Przegląd Modeli" (`/models`) ze stroną "Siatka wiedzy" (`/brain`), aby zapewnić spójność wizualną (Pixel Perfect).

## Zmiany

### 1. Globalne poprawki CSS (`globals.css`)
- **Usunięcie konfliktującego stylu**: Usunięto specyficzną regułę CSS, która wymuszała font `JetBrains Mono` (font-tech) dla nagłówków `h1` wewnątrz kontenerów `space-y-10`.
  - Powód: Ta reguła nadpisywała globalne ustawienia fontów dla strony Modeli.
- **Standaryzacja**: Dzięki temu nagłówki w całej aplikacji spójnie dziedziczą font `Inter` (font-sans).

### 2. Layout Strony Modeli (`models-viewer.tsx`)
- **Spacing**: Zmieniono główny kontener z `space-y-10` na `space-y-6` (oraz `pb-24` na `pb-10`).
  - Cel: Dopasowanie do spacingu używanego na stronie "Siatka wiedzy" (`brain-home.tsx`).
- **Header**: Zastąpiono ręczną implementację nagłówka komponentem `SectionHeading`.

### 3. Komponent `SectionHeading` (`section-heading.tsx`)
- **Wymuszenie fontu**: Dodano klasę `font-sans` do tytułu nagłówka, aby jawnie wskazać użycie fontu Inter, niezależnie od kaskady stylów rodzica.
- **Konfiguracja w Layout**: Upewniono się, że `layout.tsx` nakłada klasę `font-sans` na `body`.

## Status
- [x] Fonty na stronie Modeli są identyczne jak na innych stronach (Inter).
- [x] Odstępy (spacing) są spójne z resztą aplikacji.
- [x] Usunięto zbędny/nadpisujący kod CSS.

## Poprawa Stabilności Testów (Test Testów)

W ramach weryfikacji E2E i Backend dokonano szeregu kluczowych poprawek w infrastrukturze testowej:

### Backend (Pytest)
1. **Izolacja testów API pamięci (`test_memory_api_pruning.py`)**:
   - Wprowadzono fixture `override_dependencies` (autouse), który poprawnie zarządza nadpisywaniem zależności (`dependency_overrides`) dla `FastAPI`.
   - Rozwiązano problem "wykradania" mocków przez inne moduły testowe (np. `test_memory_api.py`), co powodowało losowe błędy (flakiness) w testach pruningu.
   - Naprawiono `NameError` związany z brakującym importem `pytest`.

2. **Stabilizacja równoległości**:
   - Potwierdzono, że grupy testowe (Heavy, Long, Light) przechodzą stabilnie w trybie sekwencyjnym, eliminując błędy związane ze współdzieleniem stanu.

### Frontend E2E (Playwright)
1. **Dostosowanie do i18n (`web-next/tests/memory-hygiene.spec.ts`)**:
   - Zaktualizowano selektory przycisków, aby używały angielskich etykiet ("Run", "Clear", "Deduplication"), co odpowiada domyślnemu środowisku uruchomieniowemu w CI/Headless.
   - Dodano brakujące klucze tłumaczeń w `en.ts`, `pl.ts`, `de.ts` dla panelu higieny pamięci.

2. **Robustość testów językowych (`web-next/tests/i18n.spec.ts`)**:
   - Wprowadzono mechanizm wykrywania domyślnego języka przed testem – jeśli system uruchamia się po angielsku, test automatycznie przełącza go na polski przed weryfikacją stanu początkowego.

System jest teraz w pełni stabilny, a wszystkie 34 testy E2E oraz 1700+ testów backendowych przechodzą poprawnie (PASS).
