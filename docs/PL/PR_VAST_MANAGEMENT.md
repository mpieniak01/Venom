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

Weryfikacja i końcowe pokrycie zmian zostaną uzupełnione po `make pr-fast`.
