# 085: PR – monitoring kosztów dysku (modele/logi/cache)
Status: w trakcie (backend + UI zaimplementowane, do weryfikacji).

## Cel
Wprowadzić kontrolkę na ekranie głównym (dashboard/kokpit) do monitorowania największych konsumentów dysku:
- modele LLM,
- logi,
- cache/buildy,
- dane historyczne (timelines, pamięć, audio).
Ma to pozwolić szybko diagnozować „co zjada miejsce” i zapobiegać cichym wyczerpaniom dysku.

## Stan obecny (z pomiaru w repo)
Największe katalogi w `/home/ubuntu/venom`:
- `models/` ~ **60G**
  - `models/blobs` ~ 52G
  - `models/gemma-3-4b-it` ~ 8.1G
- `data/` ~ **5.7G**
  - `data/timelines` ~ 5.6G (największy konsument w data/)
  - `data/memory` ~ 70M
  - `data/audio` ~ 61M
- `web-next/` ~ **1.5G**
  - `.next` ~ 760M (buildy/cache)
  - `node_modules` ~ 753M
- `logs/` ~ **77M**

## Problemy / luki
- Brak jednej kontrolki pokazującej „Top 5” konsumujących katalogów.
- Brak alertów/progów (np. >80% dysku).
- Brak informacji, czy dane są „odnawialne” (np. .next) vs „krytyczne” (modele/knowledge).

## Zakres PR (plan)
1) **Backend – endpoint metryk storage**
   - Nowy endpoint (np. `/api/v1/system/storage`) zwracający:
     - `disk_total`, `disk_used`, `disk_free` (psutil),
     - `paths`: lista top katalogów (models, data, logs, web-next/.next, web-next/node_modules, data/timelines, data/memory, data/audio),
     - rozróżnienie `kind`: `model`, `data`, `log`, `cache`, `build`, `deps`.
   - Dane tylko dla whitelisty bezpiecznych ścieżek (bez pełnego `du` po całym dysku).
2) **UI – kontrolka na ekranie głównym**
   - Nowy panel „Koszty dysku”:
     - pasek użycia całego dysku (used/total),
     - top 5 katalogów z rozmiarem i ikoną rodzaju,
     - oznaczenia „odnawialne” (cache/build) vs „trwałe” (modele, dane).
   - Progi ostrzegawcze (np. >75% = warning, >90% = danger).
3) **Dokumentacja**
   - Krótki opis w README/CONFIG_PANEL (gdzie sprawdzać zużycie, co jest bezpieczne do czyszczenia).

## Kryteria akceptacji
- Na głównym ekranie widać aktualny stan dysku i 5 największych źródeł użycia.
- Dane są spójne z realnym stanem systemu (zgodne z `du` i `df`).
- UI jasno wskazuje, które kategorie są „cache/build” (można czyścić) vs „trwałe”.

## Otwarte pytania
- Czy kontrolka ma być odświeżana automatycznie (np. co 5 min), czy tylko ręcznie?
- Czy dodać przycisk „czyść cache .next/logi” jako szybka akcja?

## Postęp realizacji
- [x] Backend: endpoint `/api/v1/system/storage` (snapshot dysku + lista kluczowych ścieżek).
- [x] UI: panel „Koszty dysku” na ekranie głównym z przyciskiem „Odśwież”.
- [ ] Weryfikacja w UI (czytelność nazw/ścieżek, potwierdzenie rozmiarów).
