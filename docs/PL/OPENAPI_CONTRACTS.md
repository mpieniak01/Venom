# Utrzymanie kontraktów OpenAPI

Plik `openapi/openapi.json` opisuje HTTP API rdzenia Full. Studio korzysta ze
wspólnych handlerów i typów TypeScript. Moduły opcjonalne mają osobne kontrakty.

## Aktualizacja i kontrola

```bash
source .venv/bin/activate
npm --prefix web-next ci
make openapi-codegen-types
make openapi-check
```

Zapisz w commicie oba pliki: `openapi/openapi.json` oraz
`web-next/lib/generated/api-types.d.ts`. Generator i jego zależności są
przypięte w `web-next/package-lock.json`. Samo `make openapi-export` aktualizuje
tylko JSON.

Bramka generuje artefakty w `test-results/openapi/` i porównuje JSON z kodem,
typy z wynikiem generatora oraz wspólne operacje i komponenty Studio z Full.
Nie zmienia plików śledzonych. Brak pliku, rozbieżność lub błąd generowania
zatrzymują kontrolę. Tego samego polecenia używają CI i `make pr-fast`,
uruchamiane także przez pre-push dla zmian dotyczących kontraktu.

Eksport odbywa się w osobnym interpreterze i katalogu tymczasowym. Nie dziedziczy
lokalnego `.env`, flag ani listy modułów operatora. Nie uruchamia cyklu startowego
ASGI, endpointów, modeli ani testów sprzętowych. Konfiguracja działającej aplikacji
pozostaje niezależna. OpenAPI opisuje HTTP; WebSocket ma osobne testy protokołu.

## Moduły opcjonalne i Studio

```bash
python scripts/export_openapi.py --profile module \
  --module-manifest /absolutna/sciezka/modulu/module.json \
  --output test-results/openapi/modules/przyklad.json

python scripts/export_openapi.py --profile studio \
  --output test-results/openapi/studio.json
```

Eksport modułu wymaga poprawnego manifestu i routera. Włącza flagę wskazanego
modułu wyłącznie w procesie eksportu. Importuje kod modułu, dlatego należy używać
zrecenzowanej rewizji. Kontrakt i klient modułu powinny być utrzymywane w jego
repozytorium, z ustaloną rewizją i zależnościami. Bramka rdzenia działa bez
zainstalowanych modułów. Eksport modułu lub Studio nie może nadpisać JSON rdzenia.

Pierwsza pełna synchronizacja dodaje 27 brakujących tras rdzenia, uzupełnia
parametr `runtime` możliwości modelu i aktualizuje wersję do `1.10.0`.
Dziewięć tras Google Home znika wyłącznie z kontraktu rdzenia, ponieważ należy
do modułu opcjonalnego. Nie usuwa to tras działającej aplikacji.
Kontrakt po synchronizacji zawiera 246 ścieżek.

[English instructions](../OPENAPI_CONTRACTS.md)
