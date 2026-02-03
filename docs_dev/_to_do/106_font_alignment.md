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
