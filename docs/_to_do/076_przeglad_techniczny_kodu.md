# 76: Przeglad techniczny kodu + audyt CSS (frontend)

Uwaga: zlecenie zostalo rozbite na dwa osobne tematy.
- Backend: `docs/_to_do/077_przeglad_backend.md`
- Frontend (CSS/HTML): `docs/_to_do/078_audyt_frontend_css_html.md`

## Cel
- Znalezc nieoptymalny, nadmiernie skomplikowany lub niewydajny kod.
- Wykryc zbyt duze, monolityczne pliki oraz martwy kod.
- Przejrzec CSS pod katem pokrycia, duplikacji i braku standaryzacji (np. boxy, przyciski).

## Zakres
- Backend/serwisy: `venom_core`, `venom_spore`.
- Frontend: `web`, `web-next` (ze szczegolnym naciskiem na CSS i powtarzalne komponenty UI).

## Wstepna analiza (szybki rekonesans)
### Duze/monolityczne pliki (kandydaci do podzialu)
- `web-next/components/cockpit/cockpit-home.tsx` (~3422 linii).
- `web/static/js/app.js` (~3800 linii, potencjalnie zbudowany/bundlowany kod).
- `web/static/css/app.css` (~2523 linie).
- `web/static/css/app copy.css` (~2410 linii, mozliwy duplikat lub martwy kod).
- `venom_core/core/orchestrator.py` (~1846 linii).
- `venom_core/api/routes/models.py` (~1329 linii).
- `venom_core/core/model_registry.py` (~1114 linii).

### CSS (pokrycie i standaryzacja)
- W repo zyje tylko 5 plikow CSS:
  - `web/static/css/index.css`
  - `web/static/css/strategy.css`
  - `web/static/css/app.css`
  - `web/static/css/app copy.css`
  - `web-next/app/globals.css`
- Obecnosc `app copy.css` sugeruje potencjalna duplikacje lub relikt.
- Brak widocznych wydzielonych warstw komponentow (np. przyciski/boxy/typografia) w osobnych plikach.
- Uwaga: style dla strony modeli maja byc celowo odmienne (klimat mono/czytnik ebook) z uwagi na duzo tekstu; przy porownaniu CSS traktowac to jako strategia UX, nie blad.

### Wstepne hipotezy ryzyk
- `web/static/js/app.js` i `web/static/css/app.css` moga byc wynikami bundlingu, co utrudnia przeglad i moze zawierac martwy kod.
- `cockpit-home.tsx` i pliki w `venom_core` sa na tyle duze, ze moga mieszac odpowiedzialnosci.
- Duza liczba stylow w jednym pliku moze oznaczac niespojna architekture CSS i duplikacje reguł.

## Plan przegladu
1) Backend: identyfikacja powtarzajacych sie sciezek, warstw i niepotrzebnych abstrajkcji.
2) Frontend (JS/TS): wykrycie komponentow/stron o nadmiernym rozmiarze.
3) Frontend (CSS): mapa powtarzalnych wzorcow (boxy, przyciski, naglowki), duplikaty, brakujace standardy.
4) Lista rekomendacji: podzial plikow, standaryzacja stylow, usuniecie martwego kodu.

## Kryteria wyjscia
- Lista plikow o wysokim priorytecie refaktoru.
- Zidentyfikowane duplikaty i kandydaci do usuniecia.
- Propozycja standardow CSS (komponenty bazowe i zmienne/utility).
