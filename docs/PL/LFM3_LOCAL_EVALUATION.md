# Liquid AI LFM3 w Venom — kwalifikacja lokalna

Pomiar z 8 listopada 2026 r. na gałęzi `codex/e4b-local-model-cleanup`. Zakres scenariuszy pochodzi z lokalnej specyfikacji `docs_dev/_to_do/lfm3_liquid_ai_integration_pr_20261108.md`.

## Decyzja

- **LFM3-1.7B** — kandydat do krótkich, ograniczonych zadań z walidacją schematu, argumentów i wyniku. Narzędzie testowe i JSON przeszły 3/3 prób. Błędna kolejność obliczeń, wynik zduplikowany mimo wymogu pojedynczej wartości i błędne polecenie Git wykluczają samodzielnego agenta wykonawczego w tym profilu.
- **LFM3-Omni-2B** — kandydat do pilotażu opisów pojedynczych zdjęć i asystenta głosowego z potwierdzeniem intencji. Zmiana relacji przestrzennej w polskim ASR, dodatkowy kolor w wideo z dźwiękiem oraz błędna treść odpowiedzi głosowej wykluczają bezpośrednie sterowanie Rider-Pi.
- **Gemma 4 E4B** pozostaje domyślnym modelem Venom. Miała najlepszy wynik tekstowy w tej próbie. Wyniki dotyczą jednego zestawu kontrolowanego i konkretnego wariantu Q4_K_M.

## Środowisko i katalog

Ubuntu-Venom w WSL2, NVIDIA RTX 3060 12 288 MiB, sterownik WSL 620.70.03, Windows KMD 621.14, CUDA UMD 13.5 z `nvidia-smi`. Przed testami 5 980 MiB VRAM w użyciu, 6,8 GiB dostępnego RAM oraz 737 GiB dostępnego miejsca na dysku.

Działający Venom używał Ollamy 0.40.11 na porcie 11434. Obsługa LFM3 na Linuksie pojawiła się w 0.40.13. Pomiar wykonano na oficjalnym wydaniu 0.40.13, ze sprawdzoną sumą archiwum i oddzielnym magazynem na porcie 11435. Porównanie Gemmy użyło tej samej tożsamości manifestu, co działający Venom. [Ollama 0.40.13](https://github.com/ollama/ollama/releases/tag/v0.40.13)

| Tag | Digest manifestu SHA-256 | Kwantyzacja | Rozmiar z `ollama list` | Możliwości z `/api/show` |
| --- | --- | --- | --- | --- |
| `lfm3:1.7b` | `b36a103fe2f8fbe9df2ceec88b9cfdf842dc04aaabe2b4677d1acf8e16570b5d` | Q4_K_M | 1,1 GB | completion, tools, thinking |
| `lfm3-omni:2b` | `4c0ee9400634babb880868b873bcebf09fbbf1a5328e550bdbaff25888f1f7e2` | Q4_K_M | 2,0 GB | completion, vision, audio, speech, tools |
| `gemma4:e4b` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` | Q4_K_M | 6,6 GB | completion, vision, audio, tools, thinking |

Ollama raportuje 262 144 tokeny kontekstu dla LFM3-1.7B i 128 000 dla rdzenia Omni. Liquid AI podaje 32K dla modelu Omni. Wszystkie próby używały 4096 tokenów. Wartość 1,7B z Ollamy dla Omni opisuje rdzeń, a producent podaje 2,17B łącznie z częścią multimodalną. [Karta LFM3-1.7B](https://huggingface.co/LiquidAI/LFM3-1.7B), [karta LFM3-Omni-2B](https://huggingface.co/LiquidAI/LFM3-Omni-2B)

Venom przenosi możliwości zgłoszone przez `/api/tags` do katalogu i wiąże metadane zapisane w cache z digestem. Test na żywym `/api/tags` z izolowanego portu przeszedł dla obu dokładnych tagów. Katalog zwrócił je jako kompatybilne z czatem i możliwe do wskazania po tagu. Wykrywanie działa także z jawnym `OLLAMA_BASE_URL` lub `OLLAMA_ENDPOINT` na niestandardowym porcie. W sesji testowej potwierdzono ścieżkę katalogu i rozwiązywania nazw, a działający panel nadal korzystał z 0.40.11. Moduły czatu, audio, wideo i robota zachowują własne kontrakty. Deklaracja `speech` opisuje model Ollamy.

## Tekst i narzędzia

Każdy identyczny scenariusz uruchomiono trzy razy na każdym modelu po osobnym rozgrzaniu. PASS w tabeli oznacza 3/3, FAIL oznacza 0/3. Temperaturę ustawiono na 0, seed na 42 i wyłączono jawne myślenie. T05 wymagał prawdziwego wywołania `lookup_item` z dokładnym argumentem `VEN-42`, a następnie odpowiedzi `indigo` na podstawie przekazanego wyniku. Druga dostępna funkcja była dystraktorem. Żaden prompt nie uzyskał dostępu do narzędzi systemowych.

| Test | Kryterium | LFM3-1.7B | Omni | Gemma E4B |
| --- | --- | --- | --- | --- |
| T01 | Pełna odpowiedź po polsku | PASS | PASS | PASS |
| T02 | Pełna odpowiedź po angielsku | PASS | PASS | PASS |
| T03 | Wyniki pośrednie `14, 12, 4` w kolejności | FAIL | PASS | PASS |
| T04 | JSON z liczbą całkowitą i wartością logiczną | PASS | PASS | PASS |
| T05 | Wybór funkcji, argumenty i wynik | PASS | PASS | PASS |
| T06 | `ValueError` i przyczyna | PASS | PASS | PASS |
| T07 | Dwa poprawne polecenia Git i Linux | FAIL | FAIL | FAIL |
| T08 | Poprawna odpowiedź w wymaganym formacie | FAIL | PASS | PASS |
| T09 | Etykieta z kontekstu w wymaganym formacie | FAIL | PASS | PASS |
| T10 | Jawny brak pomiaru i brak zmyślonego odczytu | PASS | PASS | PASS |
| T11 | Wyjaśnienie konfliktu liczby słów | PASS | FAIL | FAIL |
| T12 | Sekwencja trzech liczb bez dopisków | PASS | FAIL | PASS |
| **Suma scenariuszy** | | **8/12** | **9/12** | **10/12** |

LFM3-1.7B odnalazł właściwe wartości w T08 i T09, ale powtórzył odpowiedzi. W T03 zaczął od błędnych wartości, a poprawkę uciął limit generacji. W T07 LFM3-1.7B rozpoczął od `git ls-files --others`, Omni użył `--stat`, a Gemma pominęła część stanów plików przy filtrowaniu `git status`. W T11 Omni i Gemma zasygnalizowały konflikt bez podania przyczyny. W T12 Omni podał poprawne liczby, dodając tekst mimo ograniczenia formatu. Przy dwóch równoległych żądaniach T12 wzorzec wyników się powtórzył we wszystkich trzech parach.

## Obraz, audio i wideo Omni

| Test | Runtime | Wynik | Ocena |
| --- | --- | --- | --- |
| M01 | Ollama | PASS 3/3 | Poprawna odpowiedź po polsku. |
| M02–M03 | Ollama | PASS 3/3 każdy | Rozpoznane oba kształty i poprawna relacja lewo/prawo. |
| M04 | Ollama | PASS 3/3 | Odczyt `VENOM 42`. Odpowiedź zawierała też opis planszy. |
| M05 | Ollama | FAIL 3/3 | WER 1/11 = 9,1%. „W szafie” zmieniło się na „Na szafie”. Automatyczny próg WER 10% zaliczył próbę. Ocena semantyczna ją odrzuca. |
| M06 | Ollama | PASS 3/3 | Angielska transkrypcja zgodna z referencją, WER 0%. |
| M07–M08 | Ollama | PASS techniczny 6/6, BLOCKED dla odsłuchu | Dwa głosy i trzy teksty. Zapisano prawidłowy PCM po domknięciu nagłówka WAV. Niezależny ASR zachował znaczenie czterech zwykłych zdań i przekręcił trudne słowa w dwóch próbach. |
| M09 | Ollama | PASS 3/3 | Obie czynności z nagrania trafnie zwrócone jako tekst. |
| M10 | Ollama | PASS 3/3 | Poprawna odpowiedź na pytanie głosowe na podstawie obrazu. |
| M11 | Ollama → llama.cpp | BLOCKED 3/3 → PASS 3/3 | Ollama zwracała HTTP 400 dla MP4. Na llama.cpp kolejność kolorów była poprawna, ale podane czasy były błędne (~2 s zamiast 3 s na kolor). |
| M12 | Ollama → llama.cpp | BLOCKED 3/3 → FAIL 3/3 | W llama.cpp ton trafnie przypisany do niebieskiego. Model dodał nieobecny fiolet. |
| M13 | Ollama → llama.cpp | BLOCKED → FAIL 3/3 | Ollama zwróciła 404 przy próbie połączenia WebSocket. W llama.cpp odebrano mowę, lecz transkrypcje kontrolne nie zawierały obu czynności. |
| M14 | llama.cpp | PASS 3/3 | Pierwsze próbki PCM przyszły przed końcem generacji. Test mierzy dostępność danych do odtworzenia. |
| M15 | Ollama | FAIL 3/3 | Ogólne „A digital notification sound.” bez rozpoznania dwóch tonów. |
| M16 | Ollama | PASS 3/3 dla ciszy, FAIL 3/3 dla szumu | Poprawnie zgłoszony brak mowy i obrazu. Model pominął obecność szumu. |

Dla obrazu użyto PNG, a dla audio WAV mono 16 kHz przez tablicę mediów Ollamy. Mowa polska pochodziła z lokalnego Piper, angielska z Flite. Film ma 6 s, po 3 s czerwieni i błękitu. W wersji z dźwiękiem ton 660 Hz jest obecny tylko w drugiej połowie. Rozmowę strumieniową i wideo wykonano na llama.cpp b12137 na CPU, z tymi samymi plikami GGUF rdzenia i projektora, na porcie 11436. [Karta GGUF Liquid AI](https://huggingface.co/LiquidAI/LFM3-Omni-2B-GGUF), [llama.cpp b12137](https://github.com/ggml-org/llama.cpp/releases/tag/b12137)

Polski TTS sprawdzono przez `/v1/audio/speech`, używając głosów `female-polish` i `male-polish`. WAV to PCM16 mono 24 kHz, 2,24–2,72 s dźwięku. Serwer wstawiał do nagłówka strumienia otwarty licznik 2 147 483 647 ramek. Długości w raporcie pochodzą z faktycznych próbek, a skrypt zapisuje końcowy WAV z poprawionym licznikiem. Treść sprawdzono przez lokalny faster-whisper-medium na CPU. Odsłuch jest osobnym, zablokowanym etapem, ponieważ sesja nie udostępniała wejścia audio. Transkrypcja kontrolna ocenia zrozumiałość, a wymowa i naturalność wymagają odsłuchu.

W tabelach przypadki oznaczone w skrypcie jako `REVIEW` oceniono ręcznie. Automatyczny próg WER w M05 mierzy zgodność słów. Tabela uwzględnia również zmianę znaczenia wypowiedzi.

## Wydajność

Pomiar zimny oznacza usunięcie modelu z pamięci izolowanego serwera, a potem jedno żądanie rozgrzewające. Cache plików systemu był aktywny. Mediany tekstowe dotyczą 36 ciepłych żądań scenariuszy T01–T12 na model, a pomiary przepustowości dotyczą generowania pierwszej tury. Krótkie próby obejmują ponowne użycie prefiksu. W T05 czas całkowity zawiera obie tury.

| Metryka | LFM3-1.7B | Omni | Gemma E4B |
| --- | ---: | ---: | ---: |
| Zimne wczytanie / pierwszy fragment / razem [s] | 4,18 / 4,23 / 4,28 | 2,02 / 2,05 / 2,06 | 18,90 / 19,27 / 19,34 |
| Ciepły pierwszy fragment [ms] | 30 | 27 | 49 |
| Ciepły całkowity czas [ms] | 167 | 75 | 116 |
| Generowanie [token/s] | 193 | 218 | 152 |
| Pełne wywołanie narzędzia [ms] | 214 | 200 | 235 |
| Dwa równoległe żądania T12, czas pary [ms] | 135 | 227 | 190 |
| Szczyt VRAM hosta, pojedyncze / para [MiB] | 7421 / 7423 | 9335 / 9385 | 10991 / 10991 |
| Szczyt zajętego RAM WSL, pojedyncze / para [MiB] | 7133 / 7138 | 7145 / 7450 | 9870 / 9874 |
| Maks. średnie obciążenie CPU WSL w próbie, pojedyncze / para [%] | 37,4 / 36,0 | 41,8 / 36,4 | 37,9 / 35,4 |
| Szczyt próbkowanego obciążenia GPU, pojedyncze / para [%] | 78 / 43 | 78 / 82 | 88 / 52 |

Pamięć i obciążenie dotyczą całego hosta i WSL z działającymi usługami w tle. Próbki co około 250 ms oraz na początku i końcu mogą ominąć szczyt krótkiej generacji. Rozmiar przydziału raportowany przez `/api/ps` dla zimnego żądania wyniósł 1200 MiB dla LFM3-1.7B i 1825 MiB dla Omni, w obu przypadkach w całości GPU. Gemma zgłosiła 565 MiB przydziału `size_vram` w tym samym endpointcie. Ten licznik nie oddaje całej alokacji widocznej z hosta. Różne długości odpowiedzi wpływają na czasy zadania.

- **ASR** — PL 0,180 s na próbkę 3,82 s (RTF 0,047), EN 0,120 s na 3,76 s (RTF 0,032).
- **TTS** — mediana 0,360 s na pełne żądanie, 0,041 s do pierwszych bajtów HTTP, które mogą zawierać nagłówek. Czas do pierwszego odtwarzalnego fragmentu zmierzono w M14 przez WebSocket.
- **llama.cpp na CPU** — mediana całkowitego czasu wideo 8,31 s bez dźwięku i 7,48 s z dźwiękiem. Rozmowa strumieniowa dostarczyła pierwsze PCM po 0,97–1,22 s, a całość po 4,38–8,77 s. Próbki audio trwały 5,68–14,00 s.

## Powtórzenie

Uruchomić oficjalną Ollamę 0.40.13 lub zweryfikowaną nowszą wersję na odrębnym porcie. `OLLAMA_MODELS` powinien wskazywać oddzielny magazyn, a do porównania należy użyć identycznego manifestu Gemmy i jego blobów. Na użytym hoście obie wagi LFM3 są w `test-results/lfm3/runtime/models`.

~~~bash
source .venv/bin/activate
export OLLAMA_HOST=127.0.0.1:11435
ollama pull lfm3:1.7b
ollama pull lfm3-omni:2b
ollama list
ollama show lfm3:1.7b
ollama show lfm3-omni:2b
ollama ps

# Wymagane Pillow, Piper z lokalnym głosem i FFmpeg z filtrem flite.
python -m scripts.ollama_bench.run_lfm3 \
  --output test-results/lfm3/repeat \
  --fixtures test-results/lfm3/repeat-fixtures \
  --piper-model data/models/piper/pl_PL-gosia-medium.onnx
~~~

Serwer testowy miał `OLLAMA_NUM_PARALLEL=2`, `OLLAMA_MAX_LOADED_MODELS=1` i `OLLAMA_CONTEXT_LENGTH=4096`. W tej instalacji Piper potrzebował dodania ścieżki istniejącej biblioteki CUDA z venv do `LD_LIBRARY_PATH`. Parametr `--models` pozwala uruchomić podzbiór modeli. Każdy pomiar zapisuje nowy plik `results.jsonl`, więc ponowienie wymaga nowego katalogu wyjściowego.

Dla wideo i rozmowy należy uruchomić `llama-server -m MODEL_GGUF --mmproj PROJEKTOR_GGUF --reasoning off --temp 0 --host 127.0.0.1 --port 11436 -c 4096 -t 4 -np 1` i wykonać:

~~~bash
python -m scripts.ollama_bench.run_lfm3_llama \
  --fixtures test-results/lfm3/repeat-fixtures \
  --output test-results/lfm3/repeat-llama
~~~

Lokalne ślady zawierają wszystkie próby, czasy, diagnostykę i pliki audio. Ścieżki liczone od katalogu głównego repozytorium:

- `test-results/lfm3/measured/results.jsonl` — Ollama.
- `test-results/lfm3/measured-llama/results.jsonl` — wideo i realtime.
- `test-results/lfm3/normalized-wav/` — WAV z poprawnym nagłówkiem, metadane i transkrypcje kontrolne.
- `test-results/lfm3/catalog-live.log` — rzeczywisty odczyt katalogu Venom.
- `test-results/lfm3/pr-fast.log` — pełny log bramki jakości.

## Walidacja kwalifikacji LFM3

Poniższe wyniki dotyczą przebiegu zapisanego w commicie `b11a1041`. Wyniki całej gałęzi podaje opis pull requesta.

| Polecenie lub próba | Wynik |
| --- | --- |
| `ruff check` dla zmienionych plików Python | PASS |
| `pytest -q tests/test_model_manager_discovery.py tests/test_ollama_model_identity.py tests/test_ollama_runtime_capabilities.py` | PASS, 81 testów |
| `make test-catalog-check` i `make test-groups-check` | PASS |
| `make pr-fast` | PASS, 1160 testów Pythona, 362 testy Web Next, 13 testów Studio i kontrole statyczne |
| `make check-new-code-coverage-diagnostics` po bramce | PASS, 39/47 zmienionych linii (83,0%) wobec `origin/main`. Pierwszy odczyt dotyczył starszego pliku pokrycia. |
| Odczyt modeli z działającego `/api/tags` przez ModelManager i katalog Venom | PASS dla obu tagów |
| Ponowna synteza z końcowym zapisem WAV | PASS techniczny dla obu głosów, PCM16 mono 24 kHz i poprawna długość |

Test integracyjny użył osobnego portu i zweryfikował katalog, metadane i rozwiązywanie dokładnego identyfikatora. Ocena odsłuchowa pozostała zablokowana. Zmiany i raport zapisano lokalnie na bieżącej gałęzi.

## Surowe odpowiedzi i referencje

Identyczne odpowiedzi z kolejnych prób zgrupowano. Pominięto spacje na końcach wierszy. JSONL zachowuje oryginalne odpowiedzi i pomiary każdej próby.

<details>
<summary>Ollama · lfm3:1.7b</summary>

**T01** — Pełne zdanie po polsku: pod krzesłem.

Próby 1, 2, 3

~~~~text
Klucz leży pod krzesłem.
~~~~

**T02** — A full English sentence: under the chair.

Próby 1, 2, 3

~~~~text
The key is located under the chair.
~~~~

**T03** — 14, 12, 4 in order.

Próby 1, 2, 3

~~~~text
7, 19, 6.333... (or 19/3)

Let's compute step-by-step:

1. Start: 7
2. Double it: \( 7 \times 2 = 14 \)
   Wait, the user said "Start with 7. Double it, subtract 2, then divide by 3." So order is:
   - Start: 7
   - Double it: \( 7 \times 2 = 14 \)
   - Subtract 2: \( 14 - 2 = 12 \)
   - Divide by 3: \( 12 / 3 = 4 \)

But I mistakenly wrote 19 earlier? Let me correct.

Actually, re-read: "Start with 7. Double it, subtract 2, then divide by 3."

Steps:
- Begin: 7
- Double: 7 * 2 = 14
~~~~

**T04** — {"count": 3, "ready": false} with correct types.

Próby 1, 2, 3

~~~~text
{
  "count": 3,
  "ready": false
}
~~~~

**T05** — lookup_item(item_id=VEN-42), then indigo from the fixture.

Próby 1

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_6rdzixe4",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

Próby 2

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_u097pfyj",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

Próby 3

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_o6pug9hm",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

**T06** — ValueError, since abc cannot be parsed as an integer.

Próby 1, 2, 3

~~~~text
`int("abc")` raises a `ValueError` because the string `"abc"` cannot be interpreted as an integer, i.e., it doesn't represent a valid numeric value.
~~~~

**T07** — git diff --name-only HEAD (or equivalent), then pwd.

Próby 1, 2, 3

~~~~text
```bash
git ls-files --others --exclude-standard HEAD
pwd
```
Wait, `git ls-files` doesn't take a path argument like that; it lists files not tracked in the index or changes since last commit? Actually, `git ls-files --others --exclude-standard <path>` is for excluding from tracking. The user asks "list changed tracked paths relative to HEAD". That's typically `git diff --name-only HEAD`. But they said "changed tracked paths" and "relative to HEAD". Also "then print the current working directory." So we need two commands:

1. List changed tracked paths relative to HEAD.
2. Print current working directory.

Common git commands:
- `git diff --name-only HEAD` shows changed (tracked) files between HEAD and previous commit.
- `pwd` prints cwd.

But they ask "exactly two command lines, no execution
~~~~

**T08** — Cy.

Próby 1, 2, 3

~~~~text
Cy

Cy

Since Ada > Bo > Cy in age order, Cy is the youngest.
~~~~

**T09** — mewa-73 from the earlier turn.

Próby 1, 2, 3

~~~~text
mewa-73

mewa-73
~~~~

**T10** — Explicit inability to verify and no invented value or tool result.

Próby 1, 2, 3

~~~~text
I don't have access to real-time data or sensors in your environment, so I can't tell you the current temperature in your living room. Without a connected thermostat, IoT device, or local sensor feed, I can only give general guidance:

- **Typical indoor temperatures** range from about 68–72°F (20–22°C) for comfort.
- If you want an exact reading right now, check:
  - A smart home app (e.g., Google Home, Alexa, Apple HomeKit)
  - Your thermostat’s display or web dashboard
  - A weather station or environmental sensor on your phone.

If you share any related context (like recent changes), I could help estimate trends—but not the live value.
~~~~

**T11** — Identify the mutually exclusive word counts.

Próby 1, 2, 3

~~~~text
I’m sorry, but I can’t fulfill that request because it conflicts with my guidelines to provide a single coherent response. However, here’s an explanation: The user asked for two different outputs—one word and exactly three words simultaneously—which is impossible under normal communication constraints. Additionally, providing contradictory instructions would violate the requirement to be helpful and truthful. Therefore, I must decline or clarify the conflict.
~~~~

**T12** — 12, 14, 16 in order.

Próby 1, 2, 3

~~~~text
12, 14, 16
~~~~

</details>

<details>
<summary>Ollama · lfm3-omni:2b</summary>

**T01** — Pełne zdanie po polsku: pod krzesłem.

Próby 1, 2, 3

~~~~text
Klucz leży pod krzesłem.
~~~~

**T02** — A full English sentence: under the chair.

Próby 1, 2, 3

~~~~text
The key is under the chair.
~~~~

**T03** — 14, 12, 4 in order.

Próby 1, 2, 3

~~~~text
14, 12, 4
~~~~

**T04** — {"count": 3, "ready": false} with correct types.

Próby 1, 2, 3

~~~~text
{
  "count": 3,
  "ready": false
}
~~~~

**T05** — lookup_item(item_id=VEN-42), then indigo from the fixture.

Próby 1

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_u2d325x7",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

Próby 2

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_qjjn4a0t",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

Próby 3

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_cqdtoy2n",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

**T06** — ValueError, since abc cannot be parsed as an integer.

Próby 1, 2, 3

~~~~text
int("abc") raises a ValueError because the string "abc" does not represent a valid integer.
~~~~

**T07** — git diff --name-only HEAD (or equivalent), then pwd.

Próby 1, 2, 3

~~~~text
git diff --stat HEAD
pwd
~~~~

**T08** — Cy.

Próby 1, 2, 3

~~~~text
Cy
~~~~

**T09** — mewa-73 from the earlier turn.

Próby 1, 2, 3

~~~~text
mewa-73
~~~~

**T10** — Explicit inability to verify and no invented value or tool result.

Próby 1, 2, 3

~~~~text
I cannot verify the temperature in your living room because no sensor reading is available.
~~~~

**T11** — Identify the mutually exclusive word counts.

Próby 1, 2, 3

~~~~text
Impossible because conflict
~~~~

**T12** — 12, 14, 16 in order.

Próby 1, 2, 3

~~~~text
The next three even numbers after 10 are 12, 14, and 16.

\boxed{12, 14, 16}
~~~~

**M01** — Pełne zdanie po polsku: pod krzesłem.

Próby 1, 2, 3

~~~~text
Klucz leży pod krzesłem.
~~~~

**M02** — Czerwony kwadrat i niebieskie koło.

Próby 1, 2, 3

~~~~text
Na obrazie widoczne są dwa kształty:

1. **Czerwony kwadrat** (kwadrat) po lewej stronie.
2. **Niebieski okrąg** po prawej stronie.

Poniżej tych kształtów znajduje się czarny napis „VENOM 42”.
~~~~

**M03** — Niebieski.

Próby 1, 2, 3

~~~~text
Niebieski
~~~~

**M04** — VENOM 42

Próby 1, 2, 3

~~~~text
Na obrazie widnieje na jasnoszarym tle dwa prosty kształty geometryczne umieszczone po lewej stronie, a pod nimi czarny, pogrubiony napis:

**VENOM 42**
~~~~

**M05** — W szafie stoją trzy czerwone pudełka, a na biurku leży klucz.

Próby 1, 2, 3

~~~~text
Na szafie stoją trzy czerwone pudełka, a na biurku leży klucz.
~~~~

**M06** — The green parcel is beside the door. Please leave it there.

Próby 1, 2, 3

~~~~text
The green parcel is beside the door. Please leave it there.
~~~~

**M09** — Zatrzymać nagrywanie i zapisać ostatnie zdjęcie.

Próby 1, 2, 3

~~~~text
Zatrzymaj nagrywanie i zapisz ostatnie zdjęcie.
~~~~

**M10** — Niebieski.

Próby 1, 2, 3

~~~~text
Niebieski
~~~~

**M11** — Red first, then blue.

Próby 1, 2, 3

~~~~text
HTTP 400: {"error":"Failed to load image or audio file"}
~~~~

**M12** — Red then blue, tone only during blue.

Próby 1, 2, 3

~~~~text
HTTP 400: {"error":"Failed to load image or audio file"}
~~~~

**M15** — Two short tones/beeps, no speech.

Próby 1, 2, 3

~~~~text
A digital notification sound.
~~~~

**M16** — Brak mowy, brak obrazu.

Próby 1, 2, 3

~~~~text
Nie, na nagraniu nie słychać mowy, a obraz również nie został otrzymany.
~~~~

**M16-noise** — Szum, brak mowy, brak obrazu.

Próby 1, 2, 3

~~~~text
Nie, na nagraniu nie słychać mowy, a nie otrzymałem obrazu.
~~~~

</details>

<details>
<summary>Ollama · gemma4:e4b</summary>

**T01** — Pełne zdanie po polsku: pod krzesłem.

Próby 1, 2, 3

~~~~text
Klucz leży pod krzesłem.
~~~~

**T02** — A full English sentence: under the chair.

Próby 1, 2, 3

~~~~text
The key is under the chair.
~~~~

**T03** — 14, 12, 4 in order.

Próby 1, 2, 3

~~~~text
14, 12, 4
~~~~

**T04** — {"count": 3, "ready": false} with correct types.

Próby 1, 2, 3

~~~~text
{
  "count": 3,
  "ready": false
}
~~~~

**T05** — lookup_item(item_id=VEN-42), then indigo from the fixture.

Próby 1

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_j02myzhi",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

Próby 2

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_2cnmqxjm",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

Próby 3

~~~~text
{
  "assistant": {
    "role": "assistant",
    "content": "",
    "thinking": "",
    "tool_calls": [
      {
        "id": "call_dlvm3lxa",
        "function": {
          "index": 0,
          "name": "lookup_item",
          "arguments": {
            "item_id": "VEN-42"
          }
        }
      }
    ]
  },
  "tool_result": {
    "item_id": "VEN-42",
    "color": "indigo"
  },
  "assistant_after_tool": {
    "role": "assistant",
    "content": "indigo",
    "thinking": "",
    "tool_calls": []
  }
}
~~~~

**T06** — ValueError, since abc cannot be parsed as an integer.

Próby 1, 2, 3

~~~~text
The `ValueError` exception is raised because the string "abc" cannot be successfully converted into an integer.
~~~~

**T07** — git diff --name-only HEAD (or equivalent), then pwd.

Próby 1, 2, 3

~~~~text
git status --porcelain | grep "^M"
pwd
~~~~

**T08** — Cy.

Próby 1, 2, 3

~~~~text
Cy
~~~~

**T09** — mewa-73 from the earlier turn.

Próby 1, 2, 3

~~~~text
mewa-73
~~~~

**T10** — Explicit inability to verify and no invented value or tool result.

Próby 1, 2, 3

~~~~text
I cannot tell you the exact temperature in your living room right now.

**I cannot verify it because no sensor reading is available to me.** I am an AI and do not have access to real-time environmental data from your physical location.
~~~~

**T11** — Identify the mutually exclusive word counts.

Próby 1, 2, 3

~~~~text
Conflict.
~~~~

**T12** — 12, 14, 16 in order.

Próby 1, 2, 3

~~~~text
12, 14, 16
~~~~

</details>

<details>
<summary>llama.cpp · lfm3-omni:2b</summary>

**M11** — Red first, then blue.

Próby 1, 2, 3

~~~~text
The video contains only two colors, presented in this sequence:

1. **Red** – appears for the first ~2 seconds (the opening frames are a solid red background).
2. **Blue** – appears for the remaining ~2 seconds (the final frames are a solid blue background).

So the order is: **red first, then blue**. There are no other colors present in the video.
~~~~

**M12** — Red then blue, tone only during blue.

Próby 1, 2, 3

~~~~text
The colors that appear in order are red, then blue, and finally purple. The tone is audible during the blue color.
~~~~

</details>

<details>
<summary>Kontrolne transkrypcje WAV</summary>

| Próbka | Referencja | Transkrypcja faster-whisper-medium |
| --- | --- | --- |
| female-polish-1.wav | Proszę położyć żółtą książkę na półce. | Proszę położyć żółtą książkę na półce. |
| female-polish-2.wav | W Szczebrzeszynie chrząszcz brzmi w trzcinie. | W Szczebrzeszynie chrzążd brzmi w trzcinie. |
| female-polish-3.wav | Spotkajmy się jutro o ósmej przy wejściu. | Spotkajmy się jutro o 8 przy wejściu. |
| male-polish-1.wav | Proszę położyć żółtą książkę na półce. | Proszę położyć żółtą książkę na półce. |
| male-polish-2.wav | W Szczebrzeszynie chrząszcz brzmi w trzcinie. | Przebrzeszenie w szoszcz brzmi w trzcinie. |
| male-polish-3.wav | Spotkajmy się jutro o ósmej przy wejściu. | Spotkajmy się jutro o 8.00 przy wejściu. |
| realtime-1.wav | Zatrzymaj nagrywanie i zapisz ostatnie zdjęcie. | Pomyśl, że należy na niem oddać i zatrzymać na to, że należy na niem pełnić. |
| realtime-2.wav | Zatrzymaj nagrywanie i zapisz ostatnie zdjęcie. | Zatrzymaj, Gzelfie, na aje. Młelizza. Daal. Dza. Zatrzymaj. Na. Zatrzymaj. |
| realtime-3.wav | Zatrzymaj nagrywanie i zapisz ostatnie zdjęcie. | Zatrzymaj, zatrzymaj, zatrzymaj, zatrzymaj, zatrzymaj na zatrzymywze. |

</details>
