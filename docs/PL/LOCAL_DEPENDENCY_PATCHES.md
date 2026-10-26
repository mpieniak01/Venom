# Lokalne poprawki zależności

## Migawka zależności interfejsu llama.cpp

Ignorowany checkout `tools/llama.cpp` zawiera lokalny commit
`1dd8f7e3152c4efefe163f52cb4dee6bc4b15ed8` (`chore: remediate webui snyk findings`).
Łatka zachowuje tę istniejącą różnicę w opublikowanej historii Venoma, bez
tworzenia forka ani zmieniania repozytorium upstream.

- Baza upstream: `5f4cdac3857ec3915c069caf3dec4f35af1691a1`.
- Zakres: `tools/server/webui/package.json` i `package-lock.json` wewnątrz llama.cpp.
- Łatka: [llama-cpp-webui-dependencies.patch](../patches/llama-cpp-webui-dependencies.patch).
- SHA-256: `f6e8d2994bf2f5dd2c0a893747fddb046ac9b14ae35a3f23cca96871126d90e8`.

Migawka aktualizuje MCP SDK i przypina przechodnie zależności interfejsu. Jest
archiwalną lokalną poprawką, a nie bieżącym audytem podatności ani automatyczną
aktualizacją zainstalowanego silnika. Nie zmienia wykonawcy modeli C++.
Istniejący zmodyfikowany checkout pozostaje zachowany.

Na czystej kopii zapisanej wersji bazowej najpierw sprawdź możliwość zastosowania:

```bash
git -C tools/llama.cpp apply --check ../../docs/patches/llama-cpp-webui-dependencies.patch
git -C tools/llama.cpp apply ../../docs/patches/llama-cpp-webui-dependencies.patch
```

Nie nakładaj łatki dwukrotnie. Checkout już zawierający poprawkę można sprawdzić
przez `git apply --check --reverse` z tym samym plikiem. Nowsze wersje upstream
wymagają osobnego przeglądu zależności przed ponownym użyciem.

Weryfikacja: łatkę zastosowano do tymczasowych kopii obu plików bazowych; wynik
był bajtowo identyczny z lokalnym commitem. Sprawdzono również odwrócenie łatki
na zainstalowanym checkoutcie. Archiwizacja nie instalowała zależności, nie
restartowała silnika ani nie uruchamiała nowego skanu bezpieczeństwa.
