# Polski czat: próbka jakości v1

Zestaw zawiera **32 scenariusze napisane przez zespół** na podstawie rozkładu potrzeb opisanego w `test-results/polski-czat-zrodla/ANALIZA.md`. Nie są to cytaty z WildChat ani reprezentatywna próbka rzeczywistych rozmów. Kategorie mają wagi 10 porad praktycznych, 8 pytań informacyjnych, 6 zadań tekstowych, 4 rozmowy codzienne i 4 zadania techniczne. Co najmniej 12 przypadków zawiera historię 2–5 tur użytkownika. Źródłowe rozmowy WildChat mogą być później użyte po selekcji, anonimizacji, kontroli licencji i niezależnej ocenie odpowiedzi. Nie wolno oznaczać tych przykładów jako `real_user`.

`cases.jsonl` jest rozłącznym zestawem rozwojowym `dev`. Każdy przypadek ma rubrykę ustaloną przed generowaniem, budżet odpowiedzi i wskazanie `capability`. 23 przypadki `model` mają limit 512 tokenów zgodny z istniejącym izolowanym ewaluatorem Omni. Pozostałe 9 przypadków `web`, `wiki` i `weather` mają limit 384 i wymagają pełnej ścieżki czatu z narzędziami; odpowiedź modelu bez narzędzia nie jest porównywalnym wynikiem. Historia to stały kontekst, a nie pełny odtworzony dialog. Próba z własnymi odpowiedziami modelu powinna zostać dodana później jako osobna ocena.

Uruchomienie walidacji i eksportu:

```bash
python -m scripts.academy.polish_chat_quality validate
python -m scripts.academy.polish_chat_quality export-model /tmp/polish-chat-model-dev.jsonl
```

## Zamrożona ocena 32 przypadków

Modelowe 23 przypadki i dziewięć przypadków ze źródłami oceniamy oddzielnie,
z tym samym przypiętym modelem bazowym i checkpointem. `capture-tools` wywołuje
przygotowanie kontekstu Studio Normal dla dziewięciu scenariuszy, pobiera
bezpłatne źródła publiczne i zapisuje ich stan oraz sumy kontrolne. Przed
porównaniem modeli pobranie odbywa się tylko raz, więc obydwa warianty dostają
identyczny kontekst. Występujące braki routingu i źródeł pozostają w ocenie.

```bash
root=test-results/polish-chat-quality-baseline
mkdir -p "$root"
python -m scripts.academy.polish_chat_quality export-model "$root/model-dev.jsonl"
python -m scripts.academy.polish_chat_quality capture-tools "$root/tool-capture"
bash scripts/academy/omni_pl_chat_evaluate.sh "$snapshot" \
  "$root/model-dev.jsonl" "$root/model-eval" "$training_venv" \
  base "checkpoint-7=$adapter"
bash scripts/academy/omni_pl_chat_evaluate.sh "$snapshot" \
  "$root/tool-capture/tool-dev.jsonl" "$root/tool-eval" "$training_venv" \
  base "checkpoint-7=$adapter"
python -m scripts.academy.polish_chat_quality_report "$root" "$root/report"
```

Ustaw `snapshot`, `training_venv` i `adapter` na zweryfikowane lokalne ścieżki.
Ewaluator wymaga CUDA/BF16; nie ma zastępczego uruchomienia na CPU.
Scenariusze ze źródłami korzystają z przygotowania kontekstu Studio Normal,
ale samą generację wykonuje izolowany ewaluator Omni na GPU. Nie należy
oznaczać tego wyniku jako testu streamingu Ollama. Raport techniczny pokazuje
przyczynę zakończenia, tokeny, czas, stan źródeł i zgodność cytowanych adresów
z pobranymi. `model-eval/blind.jsonl` i `tool-eval/blind.jsonl` wymagają
niezależnego przeglądu treści według zamrożonych rubryk. Sam raport techniczny
nie kwalifikuje adaptera do wydania ani do kolejnego treningu.

W ocenie zapisuj obok odpowiedzi `record_id`, wariant/checkpoint, wersję aplikacji, datę, budżet tokenów, czas i przyczynę zakończenia, ślad użycia narzędzia oraz źródła z czasem publikacji/odczytu. Kryteria oceniać na ślepo względem wariantu. Osobno policzyć wykonanie prośby, użycie historii, naturalną polszczyznę, istotny błąd, kończenie i koszt czasu. Dla pytań bieżących brak pobranego źródła oznacza brak weryfikacji, nawet jeśli odpowiedź brzmi wiarygodnie.

## Kontrakt następnych danych treningowych

Przyjmowane są tylko rekordy JSONL ze schematem Academy `train`, z polami `record_id`, `group_id`, `language: pl`, `messages` zakończonymi odpowiedzią asystenta, `supervision` indeksów odpowiedzi, `quality_status: accepted`, `source_repo`, `source_revision`, `source_record_id`, `license`, `review_note` i `reviewer_id`. Przy źródłach rozmów zachować identyfikator całej rodziny konwersacji w `group_id`; oddzielać rodziny i parafrazy między treningiem i oceną. Surowych identyfikatorów użytkownika, IP, nagłówków ani danych osobowych nie przenosić. Weryfikować każdy cel pod kątem faktów, polszczyzny, zgodności z intencją i licencji. Odpowiedzi z WildChat same nie są wzorcami.

Eksport gotowych, **już zrecenzowanych** rekordów:

```bash
python -m scripts.academy.polish_chat_quality export-reviewed-train reviewed.jsonl academy-train.jsonl
```

Eksport sprawdza schemat Academy i wyklucza dokładne przecięcia z tym zestawem. Wykrywanie parafraz, danych wrażliwych i jakości merytorycznej nadal wymaga przeglądu człowieka przed `accepted`. Zbiór dev i jeszcze nieotwarty holdout nie trafiają do treningu.

## Kolejka rzeczywistych pytań WildChat

`scripts/academy/wildchat_polish_candidates.py` czyta wybrane grupy z przypiętej rewizji [WildChat-4.8M](https://huggingface.co/datasets/allenai/WildChat-4.8M) przez żądania HTTP Range. Domyślna próba obejmuje trzy shardy. Dla szerszej, nadal ograniczonej próby można podać rozproszone indeksy shardów. Wynik wolno zapisać tylko pod ignorowanym `test-results/polish-chat-candidates/`.

```bash
python -m scripts.academy.wildchat_polish_candidates \
  --shards 0,8,16,24,32,40,48,56,64,72,80,85 --groups-per-shard 4 \
  --limit 60 --output test-results/polish-chat-candidates/review.jsonl
```

Kolejka zawiera wyłącznie wiadomości użytkowników, bez odpowiedzi źródłowego modelu, IP i identyfikatorów użytkownika. Odrzuca oczywiste adresy e-mail, telefony i linki. To tylko pierwszy filtr: ręczny przegląd musi usunąć pozostałe dane wrażliwe, odrzucić błędną polszczyznę i przypadki nieprzydatne. Każdy wpis ma `pending_review` i `training_eligible: false`. Wieloturowe prompty nie zawierają historycznych odpowiedzi asystenta; trzeba przygotować niezależnie oceniony kontekst i wzorzec odpowiedzi. Sam eksport kolejki nie zamienia jej w dane treningowe.

## Kolejka pełnych dialogów OASST2

`scripts/academy/oasst2_polish_candidates.py` wybiera z przypiętego pliku
`OpenAssistant/oasst2` jeden polski dialog na drzewo, zakończony odpowiedzią
asystenta z `rank=0`. Wszystkie tury mają pozytywny wynik źródłowego przeglądu;
wcześniejsze odpowiedzi w historii mogą mieć inną rangę i są oznaczone flagą
`non_top_rank_context`. Rewizja źródła to
`179dd21fc55192153d94adb0e0ce8f69e222bf75`, a SHA-256 pliku train to
`9638227b41b0a4fb69afa5d5c4b52e3fb6abfd56c9870d81bae32c9981e769b1`.
Źródło ma licencję Apache-2.0. Surowy Parquet i kolejka są ignorowane przez Git.

```bash
python -m scripts.academy.oasst2_polish_candidates \
  --source test-results/polish-chat-candidates/oasst2-train.parquet \
  --output test-results/polish-chat-candidates/oasst2-polish-review.jsonl
```

To są kandydaci `pending_review`, `training_eligible: false`. Przed użyciem
trzeba sprawdzić prywatność, fakty, naturalność polszczyzny, całą historię
i rozłączność rodzin z oceną. Samo źródłowe `rank=0` nie stanowi akceptacji
Academy. Zbiór validation OASST2 pozostaje poza tą kolejką.
