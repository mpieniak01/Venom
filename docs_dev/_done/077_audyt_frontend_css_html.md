# 77: Audyt frontend (CSS/HTML/JS)

## Cel
- Sprawdzic pokrycie CSS i wykryc duplikacje.
- Zidentyfikowac brak standaryzacji w powtarzajacych sie elementach (boxy, przyciski, typografia).
- Ocenic spojnosc struktury HTML/komponentow w kontekscie stylow.
- Przejrzec JS/TS pod katem nadmiernej zlozonosci, duplikacji logiki i brakow w separacji warstw.
- Zrealizowac refaktor w tym samym PR i udokumentowac zmiany.

## Zakres
- Frontend: `web`, `web-next` (CSS/HTML/JS/TS pod katem layoutu, stylow i logiki UI).

## Wstepna analiza (szybki rekonesans)
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

### HTML/komponenty
- Potencjalnie duze komponenty/strony do przegladu:
  - `web-next/components/cockpit/cockpit-home.tsx` (~3422 linii).
  - `web-next/components/models/models-viewer.tsx` (~1199 linii).
  - `web-next/app/inspector/page.tsx` (~1096 linii).

### JS/TS (logika UI)
- Najwieksze pliki legacy JS:
  - `web/static/js/app.js` (~3800 linii).
  - `web/static/js/brain.js`, `web/static/js/strategy.js`, `web/static/js/inspector.js`.
- Najwieksze komponenty klientowe w `web-next` lacza logike danych i UI:
  - `web-next/components/cockpit/cockpit-home.tsx`.
  - `web-next/components/models/models-viewer.tsx`.

### Dodatkowe obserwacje po spojrzeniu w kod
- Sa dwa fronty: legacy `web` (wlasne CSS, klasy w `web/templates/index.html`) i `web-next` (Tailwind + `web-next/app/globals.css`). Porownywanie CSS warto robic osobno dla kazdego frontu.
- `web/static/css/app.css` i `web/static/css/index.css` definiuja inne zestawy tokenow i motywow (rozne palety i fonty), co utrudnia standaryzacje.
- `web/static/css/strategy.css` wprowadza osobny, monospace'owy motyw (war-room) z dedykowanym body class.
- `web-next/app/globals.css` zawiera globalne selektory i duzo `!important`, co utrudnia nadpisywanie i moze prowadzic do kaskadowych regresji.
- Legacy HTML zawiera sporo inline styles (np. `web/templates/index.html` w sekcji modeli), co zmniejsza pokrycie CSS i komplikuje refaktor.
- Legacy JS ma silne powiazanie z DOM (manualne query/selectory, inline events) i powtarza logike fetch/obsługi bledow w wielu miejscach.
- W `web-next` czesc komponentow klientowych miesza logike pobierania danych, formatowanie i UI w jednym pliku, co utrudnia testy i reuse.
- Biblioteki zewnetrzne (CDN, legacy `web`): Chart.js, Mermaid, DOMPurify, Marked, Cytoscape, Alpine.js, svg-pan-zoom. Tych bibliotek nie refaktorujemy, jedynie kontrolujemy sposob uzycia.

## Plan przegladu
1) Mapowanie powtarzalnych wzorcow UI (boxy, przyciski, naglowki, listy).
2) Identyfikacja duplikacji klas i stylow oraz brakujacych standardow.
3) Weryfikacja spojnosc HTML/komponentow z architektura CSS.
4) Audyt JS/TS: duplikacje fetch/handlers, nadmiernie duze komponenty, brak separacji danych od widokow.
5) Lista rekomendacji: standaryzacja stylow, refaktor JS/TS, podzial CSS i ewentualne usuniecie reliktow.

## Kryteria wyjscia
- Lista powtarzalnych wzorcow i brakow standaryzacji.
- Kandydaci do wydzielenia wspolnych stylow.
- Wskazanie duplikatow CSS i plikow do uporzadkowania.
- Lista duplikacji i nadmiernej zlozonosci w JS/TS.

## Kryteria akceptacji
- Raport refaktoryzacji z opisem zmian i uzasadnieniem decyzji.
- Brak regresow w testach po wprowadzeniu zmian.
- Ewentualne dostosowanie testow do nowej logiki plikow lub zoptymalizowanej funkcjonalnosci.
- Aktualizacja dokumentacji projektu (funkcjonalnej i architektury), jesli zmiany tego wymagaja.
- Zmiany w kodzie zostaly wprowadzone (nie tylko raport).

## Format raportu (frontend CSS/HTML/JS)
Plik raportu: `docs/_done/077_audyt_frontend_css_html_js_report.md`
- `Cel i zakres` (zawiera widoki i warstwy objete przegladem).
- `Najwazniejsze ryzyka` (duplikacje, brak standaryzacji, ryzyko regresji).
- `Znaleziska CSS` (problem -> selektor/plik -> uzasadnienie -> rekomendacja).
- `Znaleziska HTML/komponenty` (problem -> komponent/plik -> uzasadnienie -> rekomendacja).
- `Znaleziska JS/TS` (problem -> plik/obszar -> uzasadnienie -> rekomendacja).
- `Propozycje standaryzacji` (tokeny, klasy bazowe, minimalny podzial, podzial logiki JS).
- `Wpływ na testy` (co uruchomic, co dostosowac).
- `Zmiany w dokumentacji` (jezeli wymagane, z wskazaniem plikow).

## Wskazowki dla wykonawcy
- Zweryfikuj, ktore pliki CSS sa realnie zaladowane na stronach (`web/templates/index.html`, `web/templates/index_.html`, `web-next/app/layout.tsx`).
- Traktuj odmienny styl strony modeli (mono/czytnik ebook) jako celowy wariant i utrzymuj go w osobnym scope (np. body class lub dedykowany wrapper).
- Zidentyfikuj duplikacje przyciskow/paneli w `web/static/css/app.css` vs `web/static/css/index.css` i zdecyduj, co jest standardem, a co reliktem.
- Zminimalizuj inline styles w legacy HTML lub przenies je do klas, aby poprawic pokrycie CSS.
- W `web-next/app/globals.css` ogranicz globalne selektory i `!important`, przenoszac style do komponentow/utility lub tokenow.
- W legacy JS wydziel wspolne utilsy (API client, error handling, DOM helpers), aby ograniczyc powtorzenia w `app.js`, `brain.js`, `strategy.js`, `inspector.js`.
- W `web-next` rozdziel logike danych od widokow (np. wydzielenie hookow lub helperow formatowania z najwiekszych komponentow).

## Co nie jest celem
- Nie robic redesignu UI ani zmiany look-and-feel.
- Nie wymuszac unifikacji stylow miedzy `web/` i `web-next` poza konieczna standaryzacja wspolnych wzorcow.
- Nie zmieniac stosu technologicznego (np. rezygnacja z Tailwind w `web-next`).
- Nie przepisywac legacy JS na nowy framework bez uzasadnienia w raporcie.

## Odniesienia do dokumentacji i ograniczenia
- `docs/FRONTEND_NEXT_GUIDE.md` opisuje zasady SCC, podzial na `web-next` i konwencje stylow (tokeny i wspolne komponenty). Nie wprowadzac nowych konwencji bez uzasadnienia zgodnego z tym dokumentem.
- `docs/DASHBOARD_GUIDE.md` potwierdza istnienie dwoch frontendow (Next i legacy). Audyt CSS prowadz osobno dla `web/` i `web-next`, bez narzucania jednego stylu na oba.
- Zmiany stylistyczne maja zachowac obecna architekture UI (brak redesignu); celem jest standaryzacja i redukcja duplikacji, nie zmiana look-and-feel.
- Nie jest intencja tworzenie rozbudowanej siatki nowych plikow i nadmiernie skomplikowanej architektury; porzadkowanie CSS/HTML ma zwiekszac czytelnosc i latwosc utrzymania bez mnozenia bytow.
