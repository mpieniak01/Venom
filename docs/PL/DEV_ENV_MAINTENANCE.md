# Konserwacja Środowiska Developerskiego (Repo + Docker)

Ten dokument opisuje praktyczny workflow utrzymania środowiska w projekcie Venom:
1. audyt zajętości i zależności,
2. bezpieczne czyszczenie artefaktów odtwarzalnych,
3. kontrola duplikatów wersji pakietów,
4. kontrola, czy host Linux nie puchnie przez nieplanowane pakiety.

Zakres: `Repo + Docker`.
Poza zakresem: globalny hard cleanup hosta bez decyzji operatora.

## Szybki workflow (zalecany)

1. Audyt:
```bash
make env-audit
```
2. Bezpieczny cleanup repo:
```bash
make env-clean-safe
```
3. Bezpieczny cleanup Docker:
```bash
make env-clean-docker-safe
```
4. Audyt po cleanup:
```bash
make env-audit
make env-report-diff
```

## Komendy Make i do czego służą

1. `make env-audit`
- generuje raporty:
  - `logs/diag-env-<timestamp>.json`
  - `logs/diag-env-<timestamp>.md`
- raport obejmuje: footprint katalogów, różnice dependency Python/Node, duplikaty transitives Node, status Docker.

2. `make env-clean-safe`
- czyści tylko artefakty odtwarzalne w repo (`.next`, cache test/lint/type-check itp.),
- nie usuwa `models`, `data/*`, `.venv`.

3. `make env-clean-docker-safe`
- czyści tylko bezpieczne artefakty Docker (np. dangling),
- nie usuwa aktywnych usług.

4. `make env-clean-deep`
- głębsze czyszczenie (np. cięższe cache rebuildowalne),
- wymaga flagi:
```bash
CONFIRM_DEEP_CLEAN=1 make env-clean-deep
```

5. `make env-report-diff`
- porównuje dwa ostatnie raporty `diag-env-*.json`,
- tworzy markdown z różnicą zużycia miejsca.

## Skrypty `scripts/dev/*`

1. `scripts/dev/env_audit.py`
- główny audyt środowiska,
- wykrywa:
  - top kosztów dyskowych,
  - konflikty pinów między `requirements.txt` i `requirements-ci-lite.txt`,
  - duplikaty wersji transitive w `web-next/package-lock.json`,
  - heurystycznie nieużywane zależności direct w Node,
  - stan zasobów Docker.
- tryb CI:
```bash
python3 scripts/dev/env_audit.py --ci-check
```

2. `scripts/dev/env_cleanup.sh`
- cleanup repo w trybach `safe` i `deep`,
- `deep` wyłącznie z `CONFIRM_DEEP_CLEAN=1`.

3. `scripts/dev/docker_cleanup.sh`
- cleanup Docker w trybach `safe` i `deep`,
- `deep` również wymaga `CONFIRM_DEEP_CLEAN=1`.

4. `scripts/dev/env_report_diff.py`
- porównanie raportów przed/po cleanup i podsumowanie odzyskanego miejsca.

## Kontrola duplikatów i konfliktów pakietów

### Python (`.venv`)

1. Spójność zależności runtime:
```bash
. .venv/bin/activate
pip check
```

2. Konflikty i drzewo zależności:
```bash
pip install -q pipdeptree
pipdeptree --warn fail
pipdeptree -r -p <nazwa_paczki>
```

3. Potencjalne duplikaty dystrybucji w środowisku:
```bash
python - <<'PY'
import importlib.metadata as m
from collections import Counter
names=[d.metadata.get("Name","").lower() for d in m.distributions()]
for n,c in sorted(Counter(names).items()):
    if n and c>1:
        print(c, n)
PY
```

### Node (`web-next`)

1. Wersje wielokrotne i drzewo:
```bash
npm --prefix web-next ls --all
npm --prefix web-next ls <pakiet>
```

2. Potencjalna deduplikacja:
```bash
npm --prefix web-next dedupe --dry-run
```

3. Szybki przegląd przez raport projektu:
```bash
python3 scripts/dev/env_audit.py
```

## Kontrola hosta Linux (czy system nie puchnie)

1. Liczba pakietów manualnie instalowanych:
```bash
apt-mark showmanual | wc -l
```

2. Ostatnie operacje APT:
```bash
tail -n 80 /var/log/apt/history.log
```

3. Ostatnie operacje DPKG:
```bash
tail -n 80 /var/log/dpkg.log
```

4. Największe pakiety systemowe:
```bash
dpkg-query -Wf='${Installed-Size}\t${Package}\n' | sort -nr | head -n 20
```

## Co wolno usuwać, a czego nie

Bezpieczne do regularnego cleanup:
1. `web-next/.next`
2. `.pytest_cache`
3. `.mypy_cache`
4. `.ruff_cache`
5. tymczasowe artefakty build/logi diagnostyczne

Chronione domyślnie:
1. `models/`
2. `data/*`
3. `.venv/` (chyba że świadomie robisz pełną rekreację środowiska)

## Częstotliwość

1. Co tydzień:
- `make env-audit`
- `make env-clean-safe`
- `make env-clean-docker-safe`

2. Po większym refaktorze/dependency bump:
- `make env-audit`
- kontrola `pip check`, `pipdeptree --warn fail`, `npm ls`, `npm dedupe --dry-run`

3. Gdy kończy się miejsce:
- snapshot `make env-audit`,
- ostrożnie `CONFIRM_DEEP_CLEAN=1 make env-clean-deep`,
- ponownie `make env-audit && make env-report-diff`.

## Powiązane bramki jakości

Po zmianach w dependency/cleanup scripts wykonaj:
```bash
make pr-fast
make check-new-code-coverage
```

To utrzymuje zgodność z polityką repo i chroni przed regresjami.
