## Copilot Coding Agent — Hard Gate Operating Rules

Ten plik definiuje minimalny kontrakt wykonania dla GitHub Coding Agent w tym repo.

### 1) Sekwencja obowiązkowa (nie pomijaj)

Po zmianach w kodzie agent zawsze wykonuje:

1. `make pr-fast`
2. `make check-new-code-coverage`

Wyjątek: jeśli zmiana jest **doc-only** (wszystkie zmienione pliki w `docs/**`, `docs_dev/**`, `README*.md` lub innych root `*.md`), ciężkie gate'y można pominąć.

### 2) Pętla naprawcza (obowiązkowa)

Jeśli którykolwiek gate zakończy się błędem:

1. agent nie kończy zadania,
2. naprawia problem,
3. ponownie uruchamia oba gate'y,
4. powtarza pętlę do uzyskania zielonego wyniku lub potwierdzonego blokera środowiskowego.

Tryb "partial done" przy czerwonych gate'ach jest zabroniony.

Ścieżka blokera środowiskowego:

1. ustaw `HARD_GATE_ENV_BLOCKER=1` dla hooka,
2. obowiązkowo opisz bloker i impact w sekcji ryzyk PR.

### 3) Kontrakt raportu końcowego (PR/summary)

Raport musi zawierać:

1. listę wykonanych komend walidacyjnych,
2. wynik pass/fail dla każdej komendy,
3. changed-lines coverage z `make check-new-code-coverage`,
4. znane ryzyka/skipy wraz z uzasadnieniem.

Dla zmian doc-only raport musi zawierać jasną adnotację: "doc-only change, hard gates skipped by policy".

Format sekcji raportowych: `.github/pull_request_template.md`.

### 4) Zasady jakości i CI-lite

1. Pilnuj zgodności z `docs/TESTING_POLICY.md` i `docs/AGENTS.md`.
2. Dla testów optional dependency stosuj `pytest.importorskip(...)`, gdy dependency nie jest gwarantowane w CI-lite.
3. Nie zgłaszaj zadania jako ukończonego, jeśli wymagane status checks pozostają czerwone.

### 5) i18n komunikatów użytkownika (obowiązkowe)

1. Komunikaty dla użytkownika nie mogą być hardkodowane w komponentach/handlerach; używaj kluczy tłumaczeń.
2. Każdy nowy/zmieniony komunikat musi mieć wpisy w `pl`, `en`, `de`.
3. Zachowaj spójność kluczy między locale i nie dopuszczaj do mieszania języków w UI.
