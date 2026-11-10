# Polski benchmark asystenta Venoma

Zestaw `pl-assistant-v1` zawiera 200 końcowych scenariuszy i 48
walidacyjnych z odrębnymi rodzinami scen, dokumentami i głosami
wejściowymi. Definicje są w `scripts/ollama_bench/polish_cases.py`.
Plik `scripts/ollama_bench/polish_v1.lock.json` ustala sumy obu manifestów.
Manifesty zawierają sumy obrazów i WAV. Używaj walidacji do strojenia
i wyboru checkpointu. Zachowaj zamrożony zbiór końcowy do porównań.

## Uruchomienie

Poniższe polecenia wymagają lokalnego Ollamy, modelu Omni i bazowej
Gemmy E4B, środowiska Venoma z CUDA, fontu DejaVu Sans Bold oraz
lokalnych głosów Piper. Przy ponownym pomiarze użyj istniejącego
katalogu zamrożonych wejść. Polecenie prepare wymaga nowego katalogu
i podanych wersji głosów. Rozbieżność sum wymaga odtworzenia
oryginalnego artefaktu albo jawnego wersjonowania nowego zestawu.

```bash
source .venv/bin/activate
export HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1
python scripts/llm/with_gpu_libraries.py python -m scripts.ollama_bench.polish_benchmark prepare \
  --output test-results/polish-v1/fixtures \
  --final-voice data/models/piper/pl_PL-darkman-medium.onnx \
  --validation-voice data/models/piper/pl_PL-gosia-medium.onnx \
  --font /usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf
python scripts/llm/with_gpu_libraries.py python -m scripts.ollama_bench.polish_benchmark run \
  --fixtures test-results/polish-v1/fixtures/final \
  --output test-results/polish-v1/omni-final \
  --model lfm3-omni:2b --piper data/models/piper/pl_PL-mc_speech-medium.onnx
```

Powtórz dla `gemma4:e4b` z oddzielnym katalogiem wyników. Podaj
`fixtures/validation` do osobnego pomiaru walidacyjnego. Narzędzie
ogranicza model dodatkowy do zadań rozmowy i dokumentów. Uruchamiaj
profile kolejno na lokalnym GPU poza bramkami kodu.

## Wyniki

`rows.jsonl` zapisuje ocenę odpowiedzi znormalizowanej do słów, WER,
zachowanie krytycznych liczb, nazw i relacji oraz wynik wywołania narzędzia.
Narzędzia odczytują wyłącznie przygotowane wyniki testowe po poprawnym
wyborze funkcji i argumentu. `summary.json` porównuje odpowiedź na
wzorcowym tekście z odpowiedzią na natywnej transkrypcji tego samego
nagrania. Dla wyniku na obrazie oba warianty dostają ten sam obraz.
Nagrania wejściowe są syntetyczne, a wybrane z nich mają szum 18 dB SNR.

`identity.json` zapisuje wersje i tożsamość modeli oraz ustawienia.
`warmup.json` oddziela pierwszy przebieg od pomiaru serii.
W katalogu `audio` są odpowiedzi wybranych tur i trzy identyczne teksty
do odsłuchu w obu profilach. Opóźnienie audio mierzy gotowy WAV.
Zwięzłość i poprawność automatyczna dotyczą formatu odpowiedzi w tych
zadaniach. Akcent, prozodia i naturalność wymagają odsłuchu. Kaskadę
ASR, odpowiedź i syntezę oceniaj osobno od generacji audio → audio.
