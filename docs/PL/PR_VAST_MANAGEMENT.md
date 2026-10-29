# VAST: wybór środowiska, zamówienie i gotowość czatu

Zakres na istniejącej gałęzi `codex/openrouter-chat-mvp`.

- Zakładka Modele → VAST: oferty, wymagania domyślnego profilu, wybór hosta,
  wycena i jawne zamówienie z limitami godzinowym i szacunkowym.
- Wspólny z CLI dziennik, ocena ofert, kontrola obrazu/modelu i kosztu przed zakupem.
- Proces w tle: pojedynczy create, oczekiwanie, inspekcja pojemności, instalacja,
  tunel SSH i kontrola modelu/digestu bez generowania odpowiedzi.
- Podpięty VAST w Modelach zdalnych i model dostępny w istniejącym selektorze czatu.
  Operator sam wybiera dostawcę i model.
- Jawne zatrzymanie/usunięcie, eksport przed usunięciem i potwierdzenie od dostawcy.
- Odtworzenie po restarcie bez ponownego najmu; serializacja odświeżania i cleanup.
- Lokalizacje pl/en/de, testy z atrapami bez prawdziwego VAST ani Test Zero.

Przygotowany lokalnie profil: `gemma4:26b-a4b-it-q4_K_M`. Inne instalacje wskazują
własny zweryfikowany profil ustawieniem `VAST_CHAT_PROFILE_FILE`; nie przesyłamy
prywatnych profili i kluczy do repozytorium.

Limity kontrolują wycenę przed zamówieniem. Czas służy oszacowaniu kosztu i nie
niszczy instancji automatycznie. Niepowodzenie instalacji może pozostawić płatny
host do jawnego sprzątnięcia. Test Zero wykonuje operator na osobne żądanie.

Weryfikacja lokalna zakończona:

- `npm --prefix web-next ci --offline`: PASS.
- `pytest -q tests/test_vast*.py tests/test_remote_provider_control.py`: 512 PASS;
  wyłącznie atrapy dostawcy, HTTP i SSH.
- Regresja komponentów VAST/OpenRouter/selektorów: 31 PASS.
- `mypy` czterech modułów, TypeScript `--noEmit`, ESLint i `lint:locales`: PASS.
- `make test-web-unit`, `make test-ci-lite`, `make test-catalog-check`,
  `make test-groups-check`, `make check-new-code-coverage-diagnostics`: PASS.
- Końcowe `make pr-fast`: PASS, 176.95 s, 1408 testów backendu
  oraz 239 testów komponentów frontendu; pokrycie zmienionych linii 95.25%,
  wszystkie 14 progów plikowych spełnione. Sieć testów była izolowana.
- Rzeczywisty panel `/models?tab=vast`: DOM i odczyt ofert VAST PASS;
  API konfiguracji, `/rider` i `/cooperation-lab`: HTTP 200.

Odbiór środowiska wykrył jeden stary wpis z nieprawidłowym formatem stanu.
Panel pokazuje go jako ostrzeżenie bez blokowania prawidłowego profilu i ofert;
historycznych danych nie przepisano. Nie wykonano rzeczywistego zamówienia,
instalacji na płatnym hoście, generacji, Test Zero ani pełnego regresu E2E.
Ta część przyjęcia wymaga jawnego zamówienia operatora.
