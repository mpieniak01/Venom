# Budowanie i uruchamianie interfejsu

Codzienny stos używa Turbopacka. Wybór środowiska i profilu aplikacji należy do wspólnego launchera; bundler jest opcją techniczną. Komponentowe cele Make i pełny stos korzystają z tego samego `web-next/scripts/web-lifecycle.mjs`.

- `make web-build` buduje artefakt dla wybranej konfiguracji.
- `make web` uruchamia wyłącznie gotowy, zgodny artefakt. Nie wykonuje ukrytego rebuilda.
- `make web-dev-turbo` uruchamia frontend developerski. Webpack/debug pozostają technicznymi wejściami do tego samego mechanizmu.

Prod pozostaje nieużywany operacyjnie. Istnienie powyższych celów nie potwierdza odbioru produkcyjnego.

## Zgodność i izolacja

`NEXT_DIST_DIR` wybiera `.next` albo nazwany katalog `.next-<środowisko>`. Next, kopiowanie standalone i start serwera korzystają z tej samej walidacji. Nie przyjmują ścieżek poza workspace.

Po udanym buildzie powstaje `venom-build.json` ze skrótem zgodności: rewizja core, zmiany robocze core, źródła web, mirror modułów, publiczna konfiguracja i wersja Node. Stamp nie przechowuje wartości konfiguracji ani sekretów. Zmiana źródeł, rewizji, modułów lub konfiguracji wymaga ponownego `web-build`. Niepowodzenie budowania usuwa wcześniejszy stamp. Nie przebudowujemy artefaktu działającego UI.

Ścieżki logów i PID są rozwiązywane względem repozytorium przed wejściem do katalogu web. Log jest dopisywany. Zajęty port albo niezweryfikowany PID powoduje błąd, bez zabijania właściciela. Przy pierwszym przejściu ze starego launchera potrzebne jest jawne zatrzymanie starego UI zgodnie z procedurą instancji.

Gotowość wymaga odpowiedzi konkretnego procesu proxy i jego dziecka Next. Sam otwarty port ani wpis w logu nie oznacza sukcesu. Tożsamość gotowego procesu obejmuje środowisko, katalog, tryb, port i skrót konfiguracji. Ponowne użycie jest dozwolone tylko dla zgodnej, gotowej instancji. Nieudany start sprząta wyłącznie własną grupę procesów.

`/meta.json` jest utrwalane w pamięci procesu proxy z jego rolą środowiska. Przy równoległym dev/preprod przygotowanie pliku public/meta.json przez drugi proces nie zmienia roli wyświetlanej przez pierwsze UI. Kopiowanie standalone obejmuje zasoby statyczne i publiczne wybranego artefaktu.
