# Publiczne źródła w zwykłym czacie

Studio Normal korzysta z umiejętności `AssistantSkill` (pogoda),
`WebSearchSkill` (wyszukiwanie) i `RSSReaderSkill` (kanały RSS).
Wybór regionu, domen wyszukiwania, kanałów RSS i odmian nazw miast
jest w [konfiguracji](../../config/chat_public_sources.json).

Zmień `CHAT_PUBLIC_SOURCES_CONFIG` w środowisku procesu backendu, aby wskazać
inny plik JSON. Ścieżka względna jest liczona od katalogu repozytorium.
Konfiguracja jest odczytywana przy każdym zapytaniu, więc zmiana pliku
nie wymaga zmiany kodu. Każdy region ma:

- `match_terms`: początek słów rozpoznawanych w pytaniu; region domyślny
  służy jako fallback;
- `search_domains`: domeny używane w zapytaniach `site:`;
- `article_hosts`: domeny, z których wolno czytać datowane artykuły;
- `feeds`: uporządkowane źródła RSS z nazwą, adresem HTTPS, dopuszczalnymi
  domenami i prefiksem ścieżki artykułu.

`weather.city_aliases` normalizuje odmienione nazwy lokalizacji do nazw
rozumianych przez dostawcę pogody. Brak lokalizacji w pytaniu nadal wymaga
dopytania użytkownika. Wadliwa konfiguracja lub niedostępny dostawca
zatrzymuje pozyskanie danych; czat nie powinien dopowiadać aktualnych faktów.
Pobrania RSS i artykułów są ograniczone do publicznych adresów HTTPS,
bez przekierowań, z limitem rozmiaru i świeżości publikacji.
