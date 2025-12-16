# Legacy Frontend (Jinja2)

Ten katalog zawiera pozostawiony interfejs (`web/templates`, `web/static`) i nie jest dalej rozwijany. Wszystkie nowe prace frontendowe prowadzone są w `web-next/` (Next.js). Wprowadzanie zmian tutaj grozi rozjazdem z docelowym dashboardem, dlatego:

- Nie dodawaj nowych funkcji ani stylów do bieżących szablonów.
- Jeśli potrzebujesz poprawki UX/UI, zaimplementuj ją w `web-next/` i tam testuj.
- Katalog służy wyłącznie jako punkt odniesienia lub fallback – traktuj go jako zamrożony stan.
