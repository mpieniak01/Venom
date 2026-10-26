# Lokalne poprawki zależności

## Migawka zależności interfejsu llama.cpp

Ignorowany checkout `tools/llama.cpp` zawiera lokalny commit
`1dd8f7e3152c4efefe163f52cb4dee6bc4b15ed8` (`chore: remediate webui snyk findings`).
Łatka utrwala lokalną różnicę z poprawką zgodności po recenzji: Ajv 8 jest
przypisany tylko do MCP SDK zamiast globalnie, dzięki czemu ESLint zachowuje
zgodne Ajv 6. Nie wymaga to tworzenia forka ani zmiany repozytorium upstream.

- Baza upstream: `5f4cdac3857ec3915c069caf3dec4f35af1691a1`.
- Zakres: `tools/server/webui/package.json` i `package-lock.json` wewnątrz llama.cpp.
- Łatka: [llama-cpp-webui-dependencies.patch](../patches/llama-cpp-webui-dependencies.patch).
- SHA-256: `ee8b4deefe213a98053ebbc908ea5c545a21cd2d1b1462898bfa9c9333e1376a`.

Migawka aktualizuje MCP SDK i przypina przechodnie zależności interfejsu. Jest
archiwalną lokalną poprawką, a nie bieżącym audytem podatności ani automatyczną
aktualizacją zainstalowanego silnika. Nie zmienia wykonawcy modeli C++.
Istniejący checkout pozostaje zachowany; poprawiona receptura nie jest stosowana automatycznie.

Na czystej kopii zapisanej wersji bazowej najpierw sprawdź możliwość zastosowania:

```bash
git -C tools/llama.cpp apply --check ../../docs/patches/llama-cpp-webui-dependencies.patch
git -C tools/llama.cpp apply ../../docs/patches/llama-cpp-webui-dependencies.patch
```

Nie nakładaj łatki dwukrotnie. Checkout już zawierający poprawkę można sprawdzić
przez `git apply --check --reverse` z tym samym plikiem. Oryginalny lokalny
commit poprzedza poprawkę Ajv i nie jest bajtowo identyczny z tą recepturą. Nowsze wersje upstream
wymagają osobnego przeglądu zależności przed ponownym użyciem.

Weryfikacja: poprawiona łatka odtworzyła w tymczasowej kopii pliki zgodne bajtowo
z poprawionymi manifestami; sprawdzono także jej odwrócenie. Izolowane npm ci
z wyłączonymi skryptami instalacji rozwiązało zależności jako Ajv 6.15.0 dla
ESLinta i Ajv 8.18.0 dla SDK. Funkcjonalny test schematu konfiguracji ESLinta
przeszedł. Zainstalowany silnik i checkout nie były zmieniane; nie jest to nowy
skan podatności.
