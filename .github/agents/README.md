# Custom Agents (Repository)

To repo zawiera profile custom agents dla GitHub Coding Agent:

1. `venom-hard-gate-engineer.md`
2. `venom-release-guard.md`

## Przeznaczenie

- Standaryzacja zachowania agentów względem bramek jakości.
- Powtarzalny workflow bez czerwonych gate'ów na końcu sesji.

## Uwaga

Niezależnie od profilu, obowiązuje polityka Hard Gate z:

- `AGENTS.md`
- `docs/AGENTS.md`
- `.github/copilot-instructions.md`

## Szybki start (dla agenta kodowania)

Minimalna sekwencja przed pierwszym testem:

```bash
test -f .venv/bin/activate || python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install -r requirements.txt
python -m pip install -r requirements-ci-lite.txt
```

Jeśli pracujesz nad ONNX/runtime:

```bash
python -m pip install -r requirements-extras-onnx.txt
```

## Najczęstsze problemy i szybkie rozwiązanie

1. `ModuleNotFoundError` podczas `pytest`/`mypy`:
   - najpierw sprawdź aktywację `.venv`,
   - potem doinstaluj brakujące pakiety z odpowiedniego `requirements-*.txt`,
   - nie kończ zadania z "lokalnie działa tylko po ręcznym ad-hoc pip install bez update instrukcji".
2. Zmienne środowiskowe nie są widoczne w testach:
   - ładuj je jawnie:
   ```bash
   set -a
   source .env.dev
   set +a
   ```
3. Testy przeszły, ale gate coverage nadal czerwony:
   - `make pr-fast` ocenia changed-lines coverage względem `origin/main`,
   - nowe testy muszą być widoczne dla lane (`test_catalog` + grupy pytest),
   - użyj diagnostyki:
   ```bash
   make check-new-code-coverage-diagnostics
   ```

## Krytyczne zasady uruchamiania gate (anti-confusion)

1. Nie używaj `&` między `cd` i `make` (to nie jest bezpieczne łączenie komend). Używaj `&&`.
2. Nie oceniaj wyniku gate po obciętym logu (`tail`) bez `pipefail`.
3. Jeśli używasz pipeline (`... | tail -n ...`), sprawdzaj kod wyjścia `make`, a nie ostatniej komendy.

Bezpieczny wzorzec:

```bash
set -euo pipefail
cd /home/runner/work/Venom/Venom
make pr-fast
```

Wzorzec z podglądem końcówki logu (bez maskowania błędu):

```bash
set -euo pipefail
cd /home/runner/work/Venom/Venom
make pr-fast 2>&1 | tail -n 200
test ${PIPESTATUS[0]} -eq 0
```

## Gdy padnie coverage floor

Nie zakładaj automatycznie, że to „stary problem”.

Minimalna procedura:
1. potraktuj fail jako blokujący,
2. sprawdź próg w `config/coverage-file-floor.txt`,
3. dołóż testy/pokrycie lub udowodnij reprodukcję na czystym `origin/main`,
4. dopiero wtedy oznacz jako blocker środowiskowy/repozytoryjny.

### Coverage floor — decyzje w 5 krokach (bez błądzenia)

1. Uruchom pełny gate i zachowaj pełny log (`make pr-fast`), bez `grep/head` jako źródła prawdy.
2. Potwierdź próg w `config/coverage-file-floor.txt`.
3. Jeśli fail dotyczy pliku niezmienionego, uruchom reprodukcję na czystym `origin/main`:
   - bez lokalnych zmian i bez dodatkowych "pomocniczych" filtrów loga.
4. Jeśli `origin/main` jest zielone, traktuj problem jako regresję aktualnego diffa (nawet jeśli nie dotknąłeś tego pliku bezpośrednio).
5. Napraw przez testy albo zmianę selekcji testów zgodnie z katalogiem/grupami; nie oznaczaj jako pre-existing.

Antywzorce (zakazane):

1. `git stash && make pr-fast ... | grep ... | head ...` jako dowód.
2. Wniosek „to stary problem” bez pełnego uruchomienia na czystym `origin/main`.
3. Decyzja na podstawie pojedynczej linii z procentem pokrycia bez wyniku `check-file-coverage-floor`.
