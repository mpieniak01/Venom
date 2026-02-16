# THE WORKFLOW CONTROL - Kompozytor Wizualny i Bezpieczny Przepływ Zmian

## Przegląd

THE WORKFLOW CONTROL to operatorski interfejs Venom do bezpiecznego komponowania i wdrażania konfiguracji stosu.
Łączy:
1. Wizualny kompozytor grafu (węzły, połączenia, swimlane).
2. Inspektor właściwości zaznaczonego elementu.
3. Wykonanie plan/apply z walidacją kompatybilności i audytem.

Ten dokument jest przewodnikiem operatorskim.
Szczegóły payloadów API: `docs/PL/WORKFLOW_CONTROL_PLANE_API.md`.

## Co robi ekran Workflow

Ekran Workflow nie jest wyłącznie mapą stanu. To interaktywna płaszczyzna sterowania:
1. Operator wybiera i edytuje węzły w kompozytorze.
2. Zmiany są odzwierciedlane w panelu właściwości (jedno źródło prawdy).
3. System buduje plan, waliduje kompatybilność i bezpiecznie aplikuje zmiany.

## Model kompozytora

### Swimlane (sekcje domenowe)

Graf jest podzielony domenowo:
1. **Decision / Intent**
2. **Kernel / Embedding**
3. **Runtime / Provider**
4. **Execution / Workflow Ops** (opcjonalnie, zależnie od funkcji)

Podział eliminuje chaos "all-to-all" i wymusza jawne ścieżki.

### Semantyka węzłów

Typowe grupy węzłów:
1. Strategia decyzji / tryb intencji.
2. Kernel i usługi runtime.
3. Embedding oraz wybór dostawcy.

Węzły mogą prezentować statusy:
1. Dirty (lokalna zmiana przed apply).
2. Conflict / blocked.
3. Wymagany restart.
4. Tag źródła (np. lokalne vs chmura tam, gdzie dotyczy).

### Reguły połączeń

Połączenia są sterowane polityką, nie są dowolne.
Jeśli połączenie jest zabronione, UI powinno zwrócić kod przyczyny.

Przykłady:
1. `decision_strategy -> intent_mode` dozwolone.
2. `runtime -> provider` dozwolone z walidacją kompatybilności.
3. Niewspierane kombinacje blokowane z jasnym feedbackiem.

## Świadomość źródła: lokalne vs chmura

Tam, gdzie istnieje wybór źródła (np. embedding/provider), operator zawsze powinien widzieć, czy aktywny wybór jest lokalny czy chmurowy:
1. W polach formularza inspektora.
2. Na odpowiednich węzłach "bieżących" jako mały badge/tag.
3. W komunikatach walidacyjnych, gdy dla wybranego źródła brak opcji zgodnych.

Jeśli domena jest dobierana automatycznie (np. część usług runtime), unikaj mylącego "brak". Lepszy jest jawny stan `auto`, gdy użytkownik nie wybiera ręcznie.

## Bezpieczny przepływ wykonania (Plan -> Apply)

Rekomendowany przepływ:
1. Edycja wartości na węźle lub w inspektorze.
2. Uruchomienie **Plan**.
3. Przegląd compatibility report i reason code.
4. Apply tylko dla poprawnych zmian.
5. Potwierdzenie operacji wymagających restartu.

Kluczowe wyniki:
1. `hot_swap` - zmiana natychmiastowa.
2. `restart_required` - zmiana przyjęta, wymaga restartu.
3. `rejected` - zmiana zablokowana przez politykę/kompatybilność.

## Dobre praktyki operatora

1. Wprowadzaj zmiany iteracyjnie, nie masowo przez wiele domen naraz.
2. Rozwiązuj konflikty w inspektorze przed apply.
3. Traktuj etykiety źródła (lokalne/chmura/auto) jako informację operacyjną.
4. Korzystaj z audytu po większych apply.
5. Utrzymuj parity i18n (PL/EN/DE) dla komunikatów workflow.

## Troubleshooting

### "Zmieniłem źródło na lokalne/chmura, ale lista opcji jest zła"
1. Odśwież stan workflow.
2. Otwórz ponownie inspektor węzła.
3. Sprawdź compatibility report (powód filtrowania).
4. Zweryfikuj, czy backend zwrócił opcje dla wybranego źródła.

### "Węzeł pokazuje klucz tłumaczenia zamiast tekstu"
1. Brakuje klucza i18n dla modelu/dostawcy.
2. Dodaj klucz do słowników tłumaczeń.
3. Fallback ma być czytelny (nie surowy klucz w finalnym UX).

### "Plan przeszedł, ale Apply wymaga restartu"
To normalne przy `restart_required`.
Zmiana jest poprawna, ale efekt będzie widoczny po pełnym cyklu usługi.

## Powiązane dokumenty

1. `docs/PL/WORKFLOW_CONTROL_PLANE_API.md` - kontrakt endpointów i schematów.
2. `docs/PL/OPERATOR_MANUAL.md` - szersze operacje dzienne.
3. `docs/PL/FRONTEND_NEXT_GUIDE.md` - kontekst UI i frontend.
