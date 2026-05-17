# Introspekcja modelu - przewodnik operacyjny

Dokument opisuje ekran `Inspector / Model Introspection` w `web-next` oraz to, jak czytac sygnaly po ostatnich wdrozeniach 223D/223E.

Flow Inspector nadal zyje pod `/inspector`. Introspekcja modelu jest osobnym ekranem pod `/inspector/model-introspection`.

---

## 1. Cel

- pokazac odpowiedz modelu, przebieg analizy i sygnaly mechanistyczne w jednym miejscu,
- oddzielic jakosc odpowiedzi od jakosci internals,
- pokazac jawnie, kiedy introspekcja jest pelna, a kiedy pozostaje w fallbacku,
- utrzymac UI stabilne nawet wtedy, gdy probe sa niedostepne albo czesciowe.

## 2. Stan aktualny vs stan docelowy

| Stan | Co widzisz | Jak to czytac |
|---|---|---|
| przejsciowy / degraded | `internals fallback`, `attention_unavailable`, `saliency_unavailable`, `probe_failed` | UI dziala, ale probe nie dostarczyly pelnych danych internals dla tego runu |
| docelowy / ready | osobne `answer verdict` i `internals verdict`, dane dla `attention`, `saliency`, `logit lens` | analiza jest pelna i nie opiera sie na fallbacku |

## 3. Kontrakt danych

Widok opiera sie na polu `analysis_capabilities`.

### 3.1 Gotowosc runtime / probe

- `probe_profile`
- `probe_enabled`
- `probe_healthy`
- `runtime_supported`
- `endpoint_configured`
- `model_whitelisted`
- `limits.*`:
  - `timeout_seconds`
  - `max_attempts`
  - `max_top_k`
  - `max_layer_count`
  - `max_head_count`
  - `max_prompt_tokens`

### 3.2 Stan mechanizmow

Kazdy mechanizm zwraca jawny status i powod:

- `attention`
- `saliency`
- `logit_lens`

W praktyce UI rozroznia:

- `available`
- `unavailable`
- `probe_failed`
- `probe_unavailable`

## 4. Jak czytac ekran

### 4.1 Answer verdict

To sygnal jakosci odpowiedzi i grounding:

- czy odpowiedz jest spoista,
- czy jest grounded,
- czy coverage evidence jest wystarczajace.

### 4.2 Internals verdict

To osobny sygnal dla mechanizmow introspekcji:

- czy runtime i endpoint sa gotowe,
- czy model jest whitelisted,
- czy probe zwrocily dane,
- czy awaria jest tylko fallbackiem, czy prawdziwym brakiem danych.

### 4.3 Odczyt timeline

Timeline rozdziela teraz dwie sciezki:

- `answer_path`
- `internals_path`

To pomaga odczytac, czy opoznienie dotyczy samej odpowiedzi, czy dodatkowych probe.

## 5. Kiedy stan jest przejsciowy

Stan jest przejsciowy, jesli:

- runtime pokazuje `supported`, `configured`, `whitelisted`, `enabled`,
- ale internals nadal zwracaja `fallback` albo `unavailable`,
- albo `logit lens` konczy sie na `probe_failed`.

To nie oznacza awarii calego UI. Oznacza, ze warstwa sterowania dziala, ale probe dla danego runu nie dostarczyly pelnych danych.

## 6. Kryteria gotowosci

Faza jest uznana za gotowa dopiero wtedy, gdy spelnione sa wszystkie warunki:

- `probe success rate >= 90%` w oknie 20 runow,
- `first chunk p95 <= 2500 ms`,
- 3 kolejne okna walidacyjne przechodza gate,
- `answer verdict` i `internals verdict` sa rozdzielone i czytelne,
- `analysis_capabilities` pokazuje pelna gotowosc runtime/probe albo jawny powod braku gotowosci,
- pre-commit, lint, typecheck i testy komponentowe sa zielone.

## 7. Typowe scenariusze

### 7.1 `probe budget unknown`

UI nie ma jeszcze pelnego snapshotu budzetu probe. To sygnal informacyjny, nie koniecznie blad.

### 7.2 `attention_unavailable` / `saliency_unavailable`

Mechanizm jest w stanie fallback albo nie dostal danych dla tego runu. Sprawdz probe readiness i logi runtime.

### 7.3 `probe_failed`

Logit lens lub inny probe nie zakonczyl sie sukcesem. Jesli problem sie powtarza, to nie jest juz tylko pojedynczy transient.

### 7.4 `internals fallback` mimo dobrego answer verdict

To oczekiwany stan przejsciowy. Odpowiedz moze byc poprawna, ale internals sa jeszcze niepelne.

## 8. Powiazane dokumenty

- [Plan realizacji 223DA](../../docs_dev/_to_do/223DA_pr_plan_realizacji_attention_saliency_dev.md)
- [Analiza gap / live analysis 223E](../../docs_dev/_to_do/223E_pr_analiza_gap_live_analysis_dev.md)
- [Kierunek docelowy 225](../../docs_dev/_to_do/225_pr_docelowy_kierunek_introspection_dev.md)
- [README](../../README_PL.md)
- [Frontend Next.js](./FRONTEND_NEXT_GUIDE.md)
- [Dashboard Guide](./DASHBOARD_GUIDE.md)
