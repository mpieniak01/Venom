# Status runtime voice i capability multimodalnych

Data statusu: 2026-05-10
Zakres: PR 205/205B voice loop, PR 207 runtime capability

## Podsumowanie

Venom ma już działającą lokalną pętlę głosową, ale lokalny stos multimodalny nie jest jeszcze wystarczająco dojrzały, żeby zastąpić stabilny pipeline STT/TTS natywnym audio w modelu.

Aktualna bezpieczna ścieżka produkcyjna:

1. przeglądarka `/voice` nagrywa mikrofon przez push-to-talk,
2. backend `/ws/audio` odbiera chunki audio i zapisuje ostatnie nagranie,
3. STT wykonuje `faster-whisper`,
4. rozumowanie LLM wykonuje aktywny lokalny runtime/model,
5. TTS wykonuje Piper, jeśli model głosu jest dostępny,
6. `/voice` pokazuje transkrypcję, odpowiedź, link do nagrania, czasy, metryki jakości i snapshot runtime.

Ta gałąź traktuje też orb voice jako osobny stos UI, a nie luźny widget:

1. `VoiceCommandCenter` zarządza stanem ekranu `/voice` i podpina orb do reszty strony,
2. `VoiceOrb3D` to ścieżka renderowania `react-three` dla orba, gdy włączone są wizualizacje 3D,
3. CSS orb pozostaje bezpiecznym fallbackiem, gdy WebGL jest niedostępny albo 3D jest wyłączone,
4. smoke coverage dla voice siedzi w `web-next/tests/voice-orb.spec.ts`.

### Aktualny baseline STT

Domyślny model speech-to-text to `medium`.

Dlaczego:

1. po dodatkowych testach po polsku na mowie potocznej daje wyraźnie lepszą jakość rozpoznawania niż `base`,
2. nadal mieści się w akceptowalnej latencji dla obecnej lokalnej pętli voice na CPU,
3. `large-v3` zostaje fallbackiem, gdy trzeba jeszcze podnieść jakość.

Rekomendacja modeli:

1. `medium` - obecny domyślny i rekomendowany baseline,
2. `base` - szybszy fallback, gdy kluczowa jest latencja i jakość pozostaje akceptowalna,
3. `large-v3` - jakościowy fallback, gdy warto zapłacić większą latencją za dodatkową próbę jakości,
4. `large-v3-turbo` - dostępny w nowszych wydaniach `faster-whisper`, ale traktujemy go jako osobny benchmark przed ewentualnym ustawieniem jako default.

### Dostępne polskie głosy TTS

Lokalne głosy Piper są trzymane w `data/models/piper` i można je przełączać przez `TTS_MODEL_PATH`.

| Głos | Plik | Uwagi |
| --- | --- | --- |
| `gosia` | `data/models/piper/pl_PL-gosia-medium.onnx` | domyślny medium, już używany |
| `darkman` | `data/models/piper/pl_PL-darkman-medium.onnx` | medium quality, już używany |
| `mc_speech` | `data/models/piper/pl_PL-mc_speech-medium.onnx` | medium quality, właśnie dodany do porównania |
| `mls_6892` | `data/models/piper/pl_PL-mls_6892-low.onnx` | low quality, tylko jako słaby baseline |

Przełączenie przykładowo:

```bash
TTS_MODEL_PATH=/home/ubuntu/venom/data/models/piper/pl_PL-mc_speech-medium.onnx
```

### Zmierzone próbki po polsku

Benchmarki CPU z cold startem zebrane 2026-05-10:

| Sesja | Prompt | Model | Czas | Wynik |
| --- | --- | ---: | ---: | --- |
| `20260510_135543_886758_125913349432592_57be75fe` | `Co to jest kwadrat?` | `base` | `2.509 s` | `Co to jest kwadrat?` |
| `20260510_135543_886758_125913349432592_57be75fe` | `Co to jest kwadrat?` | `medium` | `7.030 s` | `Co to jest kwadrat?` |
| `20260510_135543_886758_125913349432592_57be75fe` | `Co to jest kwadrat?` | `large-v3` | `11.318 s` | `Co to jest kwadrat?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `base` | `2.558 s` | `Jakie jest największy dzieło ulijama szekspira?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `medium` | `7.380 s` | `Jakie jest największe dzieło Williama Shakespeare'a?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `large-v3` | `12.095 s` | `Jakie jest największe dzieło Williama Szekspira?` |
| `20260510_140146_754253_125913368394688_6872f70f` | `Jakie jest największe dzieło Williama Shakespeare'a?` | `large-v3-turbo` | `34.875 s` | `Jakie jest największe dzieło Williama Szekspira?` |

Kierunek docelowy:

1. zostawić stabilny fallback Whisper/Piper,
2. jawnie pokazywać capability runtime,
3. używać natywnych funkcji multimodalnych tylko po aktywnej weryfikacji probe,
4. utrzymać kompatybilność ze starszymi modelami text-only.

## Wnioski z ostatnich PR

### PR 205 / 205B - lokalna pętla voice

Stan dostarczony:

1. czat głosowy został wyniesiony z układu czatu pisanego do osobnego ekranu `/voice`,
2. push-to-talk działa przez przeglądarkę i kanał WebSocket audio,
3. backend zapisuje audio i wystawia link do ostatniego WAV,
4. STT wykonuje `faster-whisper`,
5. TTS wykonuje Piper,
6. UI udostępnia tryby voice: standard, głęboka analiza, podsumowanie, kroki do wykonania,
7. historia tekstowego cockpit nie jest już blokowana przez duży panel voice.

Wniosek operacyjny:

1. ta ścieżka działa i powinna pozostać domyślnym fallbackiem,
2. problemy jakości nagrania i wyboru mikrofonu zostały rozwiązane na poziomie browser/recording pipeline,
3. natywne audio modelu nie może zastąpić tej ścieżki bez pomiaru i bez odwracalnego fallbacku.

### PR 207 - kontrakt capability runtime multimodalnego

Stan dostarczony lub w trakcie:

1. metadata modeli Ollama jest normalizowana do snapshotu capability runtime,
2. `gemma4:latest` jest rozpoznawany jako model deklarujący `completion`, `vision`, `audio`, `tools`, `thinking`,
3. `GET /api/v1/models/{model_name}/runtime-capabilities` wystawia szczegóły capability,
4. `GET /api/v1/audio/status` zawiera `runtime_snapshot`,
5. `/voice` pokazuje aktywny snapshot runtime bardziej widocznie,
6. starsze modele nadal działają przez legacy flow: tekst + Whisper + Piper.

Aktualna decyzja:

1. `audio` w metadata Ollama nie jest dowodem używalnego raw audio input,
2. `gemma4:latest` może poprawić rozumowanie po transkrypcji, szczególnie dla głębokiej analizy, jeśli probe thinking jest zweryfikowane,
3. natywne audio zostaje za jawną probe i flagami eksperymentalnymi.

## Trzy lokalne stosy runtime

Venom ma trzy lokalne ścieżki runtime. Wykrywanie capability musi być neutralne względem runtime, a nie specyficzne tylko dla Ollama.

| Runtime | Aktualna rola w Venom | Najlepsze zastosowanie | Aktualny status native audio |
| --- | --- | --- | --- |
| `ollama` | Lokalny daemon, UX instalacji modeli, metadata `/api/show` | domyślny lokalny runtime i baseline kompatybilności | metadata może deklarować `audio`, ale transport REST audio nie jest wystarczająco stabilny do produkcji |
| `vllm` | Serwer OpenAI-compatible, lokalny stos benchmarkowany | pierwszy kandydat do eksperymentów native audio i wydajnego multimodal serving | lepszy kandydat, bo vLLM dokumentuje OpenAI-style `input_audio` |
| `onnx` | In-process adapter ONNX Runtime GenAI | edge/CPU/DirectML/mobile, kontrolowany footprint, możliwa ścieżka ONNX Whisper/ASR | przydatny dla badań ASR/edge, ale nie pierwszy kandydat dla Gemma4 native audio |

## Kontrakt capability runtime

Docelowy kontrakt powinien być niezależny od providera:

```json
{
  "runtime_id": "ollama|vllm|onnx",
  "model": "aktywny model",
  "metadata_source": "api_show|openai_models|onnx_manifest|config",
  "probe_status": "verified|metadata_only|failed|unsupported",
  "capabilities": {
    "text_completion": "verified|metadata_only|fallback|unsupported",
    "vision_input": "verified|metadata_only|fallback|unsupported",
    "audio_input": "verified|metadata_only|fallback|unsupported",
    "audio_transcription": "verified|metadata_only|fallback|unsupported",
    "tool_calling": "verified|metadata_only|fallback|unsupported",
    "thinking": "verified|metadata_only|fallback|unsupported"
  },
  "fallbacks": {
    "stt": "faster_whisper|vllm_whisper|onnx_whisper",
    "tts": "piper",
    "tools": "policy_gate_required"
  }
}
```

Zasady:

1. metadata jest sygnałem discovery, a nie dowodem wsparcia produkcyjnego,
2. aktywne probe decydują, czego router może użyć,
3. UI musi pokazywać wybraną ścieżkę i powód fallbacku,
4. stare modele text-only nie są błędem,
5. każda natywna funkcja musi mieć bezpieczny fallback.

## Decyzja dla native audio

Aktualny status produkcyjny: czekamy.

Uzasadnienie:

1. Ollama wystawia capability modeli przez `/api/show`, ale stabilne publiczne API nie ma dziś raw audio field równie jasnego jak `messages[].images` dla vision.
2. vLLM dokumentuje OpenAI-compatible `input_audio` oraz offline `multi_modal_data.audio`, więc jest lepszą ścieżką kolejnego eksperymentu.
3. ONNX Runtime GenAI jest wartościowy dla edge i eksperymentów ASR, ale Gemma4 audio-native przez ONNX nie jest najkrótszą ścieżką.
4. Jakość STT po polsku i opóźnienia muszą zostać porównane z aktualnym `faster-whisper`, zanim cokolwiek przełączymy.

Kryteria akceptacji dla native audio:

1. powtarzalny smoke test na fixture WAV,
2. stabilny kontrakt payload dla wybranego runtime,
3. akceptowalna jakość transkrypcji po polsku,
4. czasy nie gorsze od obecnego fallbacku dla typowych komend,
5. pełny fallback do `faster-whisper` bez błędu UI,
6. snapshot runtime jasno pokazuje, czy audio jest `verified`, `metadata_only`, `fallback` albo `failed`.

## Rekomendowane kolejne kroki

1. Utrzymać PR 207 jako neutralny kontrakt capability i adapter Ollama.
2. Przed dodaniem kolejnych providerów uogólnić typy backendu z `OllamaRuntimeCapabilities` do `RuntimeModelCapabilities`.
3. Dodać `VllmCapabilityProbe` jako pierwszą ścieżkę eksperymentu native audio.
4. Dodać smoke `RUN_VLLM_AUDIO_EXPERIMENT=1` z krótkim WAV i OpenAI-compatible `input_audio`.
5. Zostawić `RUN_OLLAMA_AUDIO_EXPERIMENT=1` tylko jako guarded experiment, dopóki Ollama nie wystawi stabilnego transportu audio.
6. Traktować ONNX jako osobne badanie edge/ASR, nie jako pierwszy kierunek Gemma4 audio-native.
7. Budować PR 206 voice orb dopiero na stabilnych stanach runtime emitowanych przez PR 207.

## Źródła

1. Ollama show model details: https://docs.ollama.com/api-reference/show-model-details
2. Ollama thinking: https://docs.ollama.com/capabilities/thinking
3. Ollama vision: https://docs.ollama.com/capabilities/vision
4. Ollama tool calling: https://docs.ollama.com/capabilities/tool-calling
5. Ollama audio input feature request: https://github.com/ollama/ollama/issues/11798
6. vLLM multimodal inputs: https://docs.vllm.ai/en/v0.20.0/features/multimodal_inputs/
7. vLLM tool calling: https://docs.vllm.ai/en/v0.14.0/features/tool_calling/
8. vLLM reasoning outputs: https://docs.vllm.ai/en/v0.8.2/features/reasoning_outputs.html
9. ONNX Runtime GenAI: https://github.com/microsoft/onnxruntime-genai
