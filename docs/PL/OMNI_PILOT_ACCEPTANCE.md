# Odbiór pilotażu multimodalnego Omni w Studio i Full

Zestaw diagnostyczny zawiera 36 przypadków. Obejmuje odczyt kodu ze zrzutu ekranu, zmianę położenia i koloru, doprecyzowanie, brak wpisu w dokumentacji, błąd narzędzia i pytania uzupełniające. Zestaw służy do diagnozy i strojenia. Benchmark końcowy ma własne scenariusze.

Próby z rzeczywistym modelem wykonujemy osobno od testów kodu. Bramki Gita i CI sprawdzają kontrakty przy użyciu kontrolowanych danych oraz atrap. Zestaw z oznaczeniem `manual_llm` lub `live_model` uruchamia operator przez `make test-llm-manual` na zakwalifikowanym lokalnym środowisku. Odbiór Omni z poniższych kroków jest osobnym pomiarem.

## Przygotowanie

W aktywnym środowisku Venoma użyj lokalnego głosu Piper, Pillow z fontami DejaVu i FFmpeg. Jeżeli import Piper zgłosi brak biblioteki CUDA, sprawdź lokalną konfigurację hosta i zapisz rozwiązanie w prywatnym raporcie kwalifikacji.

```bash
source .venv/bin/activate
python -m scripts.ollama_bench.omni_pilot prepare \
  --output test-results/omni-pilot/acceptance-01 \
  --piper-model data/models/piper/pl_PL-gosia-medium.onnx
```

Polecenie tworzy w nowym katalogu PNG, syntetyczne nagrania WAV mono 16 kHz, kopię [zamrożonej dokumentacji](../../venom_core/services/omni_pilot_documentation.json), manifest z sumami SHA-256 oraz formularz pomiaru. Wspólne nagranie w sparowanych scenach pozwala sprawdzić, czy po zmianie obrazu zmienia się wybrany kod i wynik narzędzia.

## Pomiar

1. Użyj osobnych sesji testowych w Studio Chat 2.0 i Full `/voice`. Ustaw ten sam wariant Omni i tę samą wersję dokumentacji. Skopiuj `results-template.json` do `results.json` w tym samym katalogu. W `results.json` zapisz identyfikator buildu, wersję modelu i runtime oraz wyniki prób.
2. Dla każdego przypadku `paired` dołącz PNG i przekaż WAV przez kontrolowany mikrofon. Zastosuj te same pliki w obu interfejsach i potwierdź, że ścieżka z mikrofonu rzeczywiście zawiera nagranie. Każdy przypadek zacznij w nowej sesji. W przypadku wieloturowym pozostań w tej sesji także wtedy, gdy druga tura nie ma nowego PNG.
3. W `trace` podaj lokalny zapis próby zawierający tekst i źródło widoczne w interfejsie, kod i wynik narzędzia oraz odtworzone audio lub jego transkrypcję. Zaznacz kryteria jako `true` albo `false` na podstawie oczekiwanej intencji, kodu, instrukcji, zgodności audio i historii. Zanotuj błędy w `error`. Czas od końca wypowiedzi do pierwszego odtwarzalnego dźwięku wpisz do `latency_ms`; brak pomiaru zapisz jako `null`.
4. Przypadek `api_control` sprawdź przez jawne wywołanie ścieżki pilota bez obrazu. Przypadki `mock_transport` wykonaj z atrapą błędu odczytu i opisz osobno. Automatyczne podsumowanie obejmuje przypadki `paired`.
5. W obu interfejsach potwierdź także przerwanie odtwarzania, kontynuację rozmowy i powrót do poprzedniego modelu. Zapisz wyniki tych kroków w raporcie odbioru.

Wartość `null` oznacza kryterium bez oceny. Wynik przypadku jest pozytywny, gdy wszystkie kryteria każdej tury są zaliczone. Jeden błąd wystarcza do wyniku negatywnego. Słuchacz ocenia, czy odtworzone audio zawiera prawidłową instrukcję po polsku. Samo rozpoczęcie odtwarzania nie potwierdza zgodności treści.

```bash
python -m scripts.ollama_bench.omni_pilot summarize \
  test-results/omni-pilot/acceptance-01/manifest.json \
  test-results/omni-pilot/acceptance-01/results.json
```

Podsumowanie pokazuje wyniki według interfejsu i grupy, zgodność par oraz medianę i p95 dostępnych pomiarów opóźnienia. Wyniki dla nagrań syntetycznych i nagrań rzeczywistych zapisuj osobno.
