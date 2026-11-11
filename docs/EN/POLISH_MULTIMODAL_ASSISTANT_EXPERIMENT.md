# Venom's Polish multimodal assistant — Omni and Gemma 4 E4B

[Wersja polska](../PL/POLISH_MULTIMODAL_ASSISTANT_EXPERIMENT.md)

This report compares the local **LiquidAI LFM3-Omni-2B** and **Gemma 4 E4B** profiles in Venom Studio and the full Venom application (Full). It covers the paired November 11, 2026 measurement, earlier quality tests, and the close of the Omni training pilot.

Both models started without resident weights in the Ollama rerun. Median time to first content was **2.882 s for Omni and 11.532 s for Gemma** when cold, and **0.032 s and 0.105 s** once resident. In the separate, larger quality benchmark, Gemma passed **254/280 (90.71%)** and Omni **209/280 (74.64%)**. Results are reported by protocol.

## Hardware, models, and scoring

- One Windows 11 host with Ubuntu under WSL2, an RTX 3060 with 12 GiB of VRAM, and local Ollama 0.40.14. Chrome replayed the same recordings through a virtual microphone. Configurations ran one at a time.
- The Ollama tags were `lfm3-omni:2b` and `gemma4:e4b`. Both packages were labelled GGUF Q4_K_M. Their recorded on-disk sizes were about 2.05 GB and 6.58 GB, respectively.
- `pl-assistant-v1` contains 48 validation scenarios and 200 final scenarios. The splits use separate scenario families, documents, and synthetic input voices. Some recordings have noise at 18 dB SNR. Manifest and media hashes were fixed before evaluation. The separate reserved set B for voice adapter evaluation stayed sealed.
- A strict pass requires the expected value and format after word normalization. An extra label or a different inflection can lose a pass. Word error rate (WER) measures transcription errors. We also checked whether transcripts preserved critical names, numbers, and relationships, where a single word can change the meaning.
- GPU figures are peaks for the whole device. WSL RAM use is `MemTotal − MemAvailable`. Both include other processes running on the host. Model runs and listening trials were conducted outside the code quality gates.

## Paired Ollama measurement — from an empty runner to model unload

The November 11, 2026 run used Venom revision `4b57d8c3`, Ubuntu-Venom under WSL2, an RTX 3060 with 12 GiB VRAM (driver 621.14), and local Ollama 0.40.14. An isolated Ollama instance used the same two pinned packages. The running Venom instance had no active turns and did not take part in the run. Its idle model was unloaded for the test and restored afterward.

1. Both packages were loaded and unloaded once before sampling. The operating system file cache stayed enabled. A cold turn means no resident model in `/api/ps`; it does not measure system startup or first disk access.
2. Six pairs alternated Omni → Gemma and Gemma → Omni. Each arm started with an empty `/api/ps`. Both models got the same short request for a Polish definition of a square: one turn at a time, temperature 0, seed 42, context length 4096, a 128-token cap, and thinking disabled. Each package kept its own template and settings, including Gemma's bundled decoding variant.
3. After the first turn, each model ran the same eight validation cases from the block and answered the square question again. Before the next arm, the runner requested unload and waited for an empty `/api/ps`. Runner logs confirmed all language model layers on CUDA (Omni 25/25, Gemma 43/43). Both profiles also use host memory buffers.

| Metric (6 repeats per model) | Omni | Gemma E4B |
| --- | ---: | ---: |
| Cold · Ollama-reported load, median (min–max) | 2.787 s (1.721–6.291) | 11.146 s (8.735–18.283) |
| Cold · time to first content, median (min–max) | 2.882 s (1.815–6.429) | 11.532 s (8.946–18.686) |
| Cold · complete answer, median (min–max) | 2.998 s (1.927–6.592) | 12.113 s (9.514–19.439) |
| Resident · first content, median (min–max) | 0.032 s (0.030–0.037) | 0.105 s (0.055–0.127) |
| Resident · complete answer, median (min–max) | 0.146 s (0.139–0.155) | 0.637 s (0.587–0.696) |
| Resident · decode throughput, median | 214.2 tokens/s | 71.3 tokens/s |
| Unload · request → empty `/api/ps`, median (min–max) | 0.070 s (0.065–0.134) | 0.383 s (0.377–0.406) |

Time to first content covers request submission through the first content in the stream. The responses contained 24 and 38 tokens, respectively. Decode throughput comes from the runner and depends on the tokenizer. The min–max range shows the spread across six repeats.

| Memory · whole GPU / WSL, median over 6 cycles | Omni | Gemma E4B |
| --- | ---: | ---: |
| GPU before the cold turn · median (min–max) | 2,039 MiB (2,033–2,163) | 2,090 MiB (2,038–2,163) |
| GPU · cold-turn peak / increase from pre-turn baseline | 5,036 / +2,996 MiB | 6,722 / +4,633 MiB |
| GPU · peak while resident, validation block | 5,076 MiB | 6,766 MiB |
| WSL RAM before the cold turn | 1,250 MiB | 1,246 MiB |
| WSL RAM · cold-turn peak / increase from pre-turn baseline | 1,757 / +506 MiB | 4,733 / +3,424 MiB |
| WSL RAM · peak while resident, validation block | 1,951 MiB | 4,730 MiB |

GPU and RAM were sampled about every 100 ms. Increases were calculated per cycle and then aggregated, so they can differ from subtracting the rounded medians. Every unload produced an empty `/api/ps`; GPU memory returned to 2,033–2,163 MiB. Samples include background use and may miss short peaks between readings. These are Ollama measurements; application and speech component memory was measured separately.

The same cycles replayed 48 locked validation cases per model with reference text and, where applicable, identical PNGs, documents, and history. Tool results came from frozen fixtures. No recordings were used in this part.

| Task · reference input | Omni | Gemma E4B |
| --- | ---: | ---: |
| Conversation | 10/10 | 10/10 |
| Documents | 7/8 | 8/8 |
| Spoken instructions as text | 7/10 | 6/10 |
| Image and question as text | 9/10 | 8/10 |
| Tool choice and answer | 10/10 | 10/10 |
| **Total** | **43/48** | **42/48** |

These scores describe this validation matrix and the Ollama profiles. The larger set below covers a different workload, including voice input.

## Studio and Full — paired recording replay on the measured revision

The same revision replayed 68 turns in Google Chrome 146.0.7680.80 under WSL2. Each interface used four pairs in Omni → Gemma, Gemma → Omni, Omni → Gemma, Gemma → Omni order. Arms used separate API processes, fresh conversations, and the same recordings supplied through a virtual microphone. Each cold cycle started with an empty `/api/ps` after the backend was ready. With the model resident, we replayed the same `V-S01-1` file and ran 10 shared validation cases per configuration. One resident replay of `V-S01-1` belongs to both summaries. We verified unload after each cycle. File cache preparation followed the same procedure as the Ollama run.

Studio used Chat 2.0 (PCM over HTTP); Full used the Voice view in Direct mode (WebM/Opus over `/ws/audio`). Input was matched **within each interface**. Studio with Omni used native ASR and speech (24 kHz); Studio with Gemma used CUDA Whisper medium and Piper (22.05 kHz). Full confirmed native Ollama ASR on every accepted turn: Omni with native speech (24 kHz), Gemma with Piper (22.05 kHz). In Studio, Gemma's first turn includes on-demand initialization of Whisper and Piper. Before each Full run, its normal host Whisper and Piper warmup completed for both profiles. Any Ollama weights loaded during startup were unloaded before measurement. This measures a cold Ollama model in an already running application. Studio and Full ran in separate batches; their startup states are reported independently. Packages and speech components follow the application profiles, so timings include ASR, text generation, and synthesis.

We timed from turn submission after recording to `playing` in Studio or scheduled source start in a running `AudioContext` in Full. We also measured delivery of the complete HTTP WAV in Studio and the first audio frame in Full. These are browser events; no physical speaker was timed. The table uses only cases with verified playback in both arms of a pair; the number of pairs is in parentheses. With 10 pairs, nearest-rank p95 is the slowest pair member for each profile.

| Interface | Profile | Cold control WAV · playback, s: median (min–max; n) | Same WAV while resident · playback, s: median (min–max; n) | Resident validation · playback, s: median / p95 (n) | Resident validation · audio delivery, s: median / p95 (n) |
| --- | --- | ---: | ---: | ---: | ---: |
| Studio | Omni | 6.248 (3.488–8.586; 4) | 0.867 (0.739–1.466; 4) | 0.921 / 1.701 (10) | 0.916 / 1.696 (10) |
| Studio | Gemma E4B | 28.632 (26.649–29.005; 4) | 1.030 (0.976–1.164; 4) | 1.107 / 1.246 (10) | 1.103 / 1.240 (10) |
| Full | Omni | 1.931 (1.501–2.075; 4) | 0.782 (0.716–0.823; 4) | 0.856 / 1.323 (10) | 0.853 / 1.312 (10) |
| Full | Gemma E4B | 6.122 (5.156–6.560; 4) | 0.876 (0.783–3.396; 4) | 1.022 / 3.008 (10) | 1.018 / 2.961 (10) |

Strict answers and WER refer to the ten resident recordings. WER is averaged over available transcripts; critical content counts all attempts. Playback alone does not establish a correct answer. Response length also affects latency.

| Interface | Profile | Played · cold / resident validation / resident control | Strict answer · validation | Mean WER · validation (n) | Critical transcript content preserved · validation |
| --- | --- | ---: | ---: | ---: | ---: |
| Studio | Omni | 4/4 / 10/10 / 4/4 | 5/10 | 5.0% (10) | 8/10 |
| Studio | Gemma E4B | 4/4 / 10/10 / 4/4 | 6/10 | 2.0% (10) | 9/10 |
| Full | Omni | 4/4 / 10/10 / 4/4 | 5/10 | 5.0% (10) | 8/10 |
| Full | Gemma E4B | 4/4 / 10/10 / 4/4 | 7/10 | 9.0% (10) | 8/10 |

Memory includes Chrome, the backend, speech components, and host background use. Each cell reports medians across four cycles. The peak covers the recording block after app startup and before model unload. Baseline and increase use the sample taken after Chrome opened and before the first recording. Cold and resident turn peaks use samples from submission through the end of each turn measurement. Subtracting medians can differ from the median increase.

| Interface | Profile | GPU · baseline / block peak / increase (MiB) | GPU · cold / resident peak (MiB) | WSL RAM · baseline / block peak / increase (MiB) | WSL RAM · cold / resident peak (MiB) |
| --- | --- | ---: | ---: | ---: | ---: |
| Studio | Omni | 2,025 / 5,082 / +3,057 | 5,068 / 5,082 | 1,444 / 2,587 / +1,129 | 2,477 / 2,587 |
| Studio | Gemma E4B | 2,025 / 8,115 / +6,090 | 7,931 / 8,115 | 1,506 / 7,190 / +5,745 | 7,031 / 7,190 |
| Full | Omni | 3,247 / 6,339 / +3,085 | 6,314 / 6,332 | 2,774 / 4,159 / +1,205 | 3,845 / 4,078 |
| Full | Gemma E4B | 3,208 / 8,211 / +5,000 | 8,122 / 8,204 | 2,853 / 7,644 / +4,745 | 7,331 / 7,627 |

Playback started in all 68 turns. On this host, Omni had lower median playback latency and a smaller increase in memory use in both interfaces. The latency gap was largest before model load. Across the ten resident recordings, Gemma had more strict passes in Studio and Full. In Full it did so with a higher WER, so transcript accuracy and answer accuracy are worth tracking separately.

## Quality on the 200 frozen scenarios (historical run)

Revision `c7849e83` used temperature 0, seed 42, a 4,096-token context, a 128-token generation limit, and reasoning disabled. Each model received 200 reference-text inputs and 80 additional runs of scenarios with recordings, for 560 scored outcomes in total. The same image was supplied to both input variants of an image question. The backend used Omni's native ASR and speech synthesis, and CUDA Whisper medium and Piper for Gemma.

| Task and input | Omni | Gemma E4B |
| --- | ---: | ---: |
| Conversation · reference text | 40/40 | 40/40 |
| Documents · reference text | 33/40 | 40/40 |
| Spoken instructions · reference text | 16/40 | 31/40 |
| Spoken instructions · recording | 7/40 | 23/40 |
| Image and question · reference text | 37/40 | 40/40 |
| Image and question · recording | 40/40 | 40/40 |
| Tools and final answer · reference text | 36/40 | 40/40 |
| **Total** | **209/280** | **254/280** |

Gemma led by 16.07 percentage points. In the paired comparison, both models passed 208 outcomes, Gemma alone passed 46, Omni alone passed 1, and both failed 25. Text and audio variants of the same scenario are related observations. Both models scored 40/40 on the choice of tool and argument or request for clarification. The table also scores the final answer based on the frozen tool result. Tools returned prepared test responses.

| Metric | Omni | Gemma E4B |
| --- | ---: | ---: |
| Mean WER on 40 instruction recordings | 13.28% | 6.48% |
| Instruction transcripts preserving critical content | 28/40 | 30/40 |
| Mean WER on 40 recorded questions with an image | 16.94% | 1.11% |
| Image question transcripts preserving critical content | 30/40 | 36/40 |
| Execution errors / synthesis sample errors | 0 / 0 | 0 / 0 |

Omni was already resident in this run, while Gemma loaded in the first turn (16.99 s). The table preserves the quality and reliability results. Use the new paired measurements to compare loading, latency, and memory.

## Studio and Full — earlier validation and Full voice routing fix

On revision `c7849e83`, each model–interface pair produced 68 outcomes through the application API (48 reference-text scenarios, 20 also run on recordings), for 272 results. Standalone spoken instructions in Full used the `/voice` WebSocket. Image and recording cases used an ASR → image and transcript → answer → synthesis pipeline. For tool cases, the script supplied a frozen result after the model selected the correct tool. Gemma used Whisper and Piper in Studio. In Full, the last turn's recorded metadata identified Gemma's native decoder and Piper. The later acceptance run verified the decoder on every turn.

| Profile | Interface | Strict API passes | Strict Chrome passes |
| --- | --- | ---: | ---: |
| Omni | Studio | 50/68 | 4/10 |
| Omni | Full | 50/68 | 3/10 |
| Gemma E4B | Studio | 51/68 | 4/10 |
| Gemma E4B | Full | 48/68 | 1/10 |

The API matrix delivered 79/80 WAV files. The missing Studio Gemma response returned HTTP 503 `audio_invalid_output`. Chrome played all 40 turns in fixed Omni → Gemma order, without a controlled cold start. A separate Gemma → Omni → Gemma switching test played all six turns. Selection and unloading took 1.91–2.64 s in that test; loading started at first inference. We fixed lost recordings in Studio and the premature unload acknowledgement that caused HTTP 503 in Full.

### Gemma acceptance after the Full voice routing change

On revision `5cde42ef`, Full selected native ASR from the local Gemma model and used Gemma's audio instruction format. Every final Full voice turn confirmed `ollama_audio_llm_piper`. Direct in both interfaces prioritized the current question, user decisions, and requested format. A separate trial of native Gemma ASR in Studio scored 2/10 in Chrome against a 4/10 baseline, so Studio returned to CUDA Whisper medium. Both Gemma configurations used Piper for synthesis.

| Interface | API / WS, recordings | Chrome, strict passes | Chrome WER | Playback start after change, median / p95 |
| --- | ---: | ---: | ---: | ---: |
| Studio | 4/10 → 6/10 | 4/10 → 6/10 | 4% → 2% | 1.541 / 2.255 s |
| Full | 1/10 → 5/10 | 1/10 → 7/10 | 15% → 9% | 1.325 / 1.753 s |

Reference-text scores rose from 39/48 to 43/48 in both interfaces. Chrome played 10/10 responses in each, while the APIs delivered 9/10 in Studio and 10/10 in Full. Studio reproduced `audio_invalid_output`. This rerun covered Gemma alone. It verifies the routing fix; profile comparisons use the shared protocol.

## Omni diagnostic experiments

| Experiment | Observation |
| --- | --- |
| Polish system prompt | On the same 48 reference texts and 20 shared transcripts, adding a Polish instruction reduced the reference score from 43/48 to 38/48. Recorded inputs stayed at 14/20. We kept the baseline prompt. |
| Switching models and conversation history | After switching, a correctly recognized question about tulips inherited Gemma's earlier wrong answer. Changing the context for a repeated question restored the expected answer in fresh and switched conversations in both interfaces. The original recordings in a wider paraphrase, correction, and follow-up sequence improved from 0/8 to 2/8. Additional controls scored 6/8. |
| “Roses instead of tulips” | We compared the source WAV with the audio captured by both interfaces. One native ASR retry at low confidence improved preservation of “instead of” from 5/6 to 6/6 in Chrome. The exact phrase scored 3/6 due to inflection. On 20 validation recordings, WER was 3.125% and 18/20 preserved the critical detail. |
| Image-based source selection and follow-ups | The matrix improved from 26/36 to 36/36 in Studio and from 24/36 to 36/36 in Full. In each interface, 31 cases used the model. The others covered missing images or controlled failures. In Chrome, a follow-up changed the selected source without attaching the image again. |
| Camera, live state, and silence | Studio HTTP and Full WS each passed 9/9 cases. We tested a single JPEG from a virtual camera, corrections, runtime state reads, controlled failures, missing images, and silence. Median time to a complete WAV was 1.205 s in Studio and 0.990 s in Full. |

### Polish speech quality

- In a listening comparison of one sentence about a square, recording quality was comparable. The operator judged the Polish accent of Piper `pl_PL-mc_speech-medium` more natural than Omni `female-polish`. Broader listener assessment of accent, prosody, and naturalness remains open.
- We generated 99 synthetic WAV files for speech input evaluation, 33 each from Piper, Omni, and Microsoft Paulina Desktop. Initial ASR diagnosis on the open subset plus a control recording scored 8/17, 14/17, and 13/17, respectively. The recordings were reserved for evaluation.
- In controlled Omni synthesis, manually spelling out numbers, dates, times, and abbreviations improved automated critical-content scores from 6/12 to 12/12 in BF16. A repeat through the application improved from 1/12 to 11/12 in Studio and from 1/12 to 12/12 in Full. Ordinary Direct turns in the same experiment scored 2/6 for text and 0/6 for audio content in both interfaces.
- In a separate “The temperature is 24°C” experiment, each of two Polish Omni voices scored 0/3 with digits and 0/3 with the number spelled out. Omni ASR transcribed the resulting audio to check the number. The result calls for listening and motivates future voice output training. The manual text preparation was a test condition, and reading numbers aloud still needs qualification.

## What the Omni training experiments showed

We ran local BF16 SFT LoRA on the same RTX 3060 with Transformers 5.22.2. The rank-4 Q/V adapter has 292,864 parameters. The fact verifier's weight file was 1.12 MiB. Peak reserved VRAM across the reported runs ranged from 4,588 to 6,048 MiB. We verified checkpoint saving and resumption in a separate process. Reserved memory during training uses a different measurement from the whole-device peaks in the application tests.

| Experiment | Diagnostic result |
| --- | --- |
| Text behavior and tools | The pilot improved from 6/12 to 7/12. Later iterations on their own validation sets improved over the base from 10/32 to 22/32, 21/48 to 34/48, 40/64 to 52/64, and 36/57 to 44/57. Conversation regressions, quoted text triggering actions, and evidence errors remained. The datasets and protocols differed. |
| Ranking a quote or choosing no evidence | At calibrated thresholds, pointwise returned 5/64 correct quotes and listwise returned 10/64. After filtering, both declined all 64/64 questions with no evidence. Listwise ran 192 steps in 169.8 s against 362.4 s for pointwise. Both fell below the 52/64 target. |
| Source filtering and fact matching | Filtering before ranking removed suggestions from unselected documents in a new trial. Misleading quotes from the selected document still passed. On held-out cases about the entity, condition, unit, or ordering, the LoRA verifier returned 3/32 correct quotes with four errors against a target of 26/32 with zero errors. |
| Native audio and image input | Audio and image encoders and the speech decoder stayed frozen. After 80 steps, strict scores rose from 8/32 to 15/32. Ignoring argument letter case gave 21/32 for the base and 22/32 for the adapter. Most of the strict gain came from formatting. |

None of the adapters met the deployment criteria. The main comparison uses the base profiles.

### LoRA pilot results

The native audio understanding pilot compared the BF16 base with checkpoints 12, 24, 36, and 48. LoRA r4 updated only the language model's Q/V projections. The target was a text answer to a recording. The encoders and speech decoder stayed frozen. The pilot used 96 training pairs and 24 validation pairs.

| Test | Base Omni | LoRA, checkpoint 48 |
| --- | ---: | ---: |
| Validation · text answer to recording | 36/48 | 43/48 |
| Earlier held-out test · text | 18/24 | 16/24 |
| Fresh pairs with different synthetic voices · text | 13/32 | 20/32 |
| Fresh pairs · incorrect approvals (lower is better) | 6/12 | 1/12 |
| Same fresh pairs · reference text as input | 25/32 | 25/32 |
| Same fresh pairs · matching text and speech in `interleaved` | 13/32 | 13/32 |

In the separate checkpoint selection matrix, the base and checkpoints 12, 24, 36, and 48 passed 14, 16, 19, 19, and 20 of 24 complete pairs, respectively. Vosk checked 72 WAVs. Of 14 disputed responses, two short affirmative answers were corroborated automatically, four were rejected based on text, and eight await human listening. Automatic recognition helps assess content; pronunciation and prosody need a separate evaluation. Numbers and units had their own tests: spelling them out passed 8/8 in the first separate synthesis trial and 2/5 on fresh values. In a fresh `interleaved` trial, digits passed 6/10 versus 0/10 when spelled out. This evidence does not support a general rewrite of digits into words.

The pilot closed without deploying an adapter. We archived 1,331 files locally with a SHA-256 manifest. The primary execution model and Venom policy own tool selection and execution; Omni can explain, ask follow-up questions, and pass along the understood intent.


## Native Omni dialogue in the BF16 prototype

This trial ran on a separate experimental branch of Venom. In the trial, LFM3‑Omni‑2B received a recording and an image in one turn. Studio and Full played speech from that same generation. The existing Omni pipeline serves as the reference. Warm BF16 inference produced valid WAV files in 96/96 turns. In `interleaved` mode, strict text passed 4/48 cases and spoken content passed 1/48. In `audio` mode, spoken content passed 0/36. Median and p95 time to WAV on the warm model were 5.181 / 7.532 s for interleaved output and 5.992 / 7.911 s for audio output. Peak whole-device GPU memory was 10,878 MiB. Chrome trials included model loading and used a separate timing protocol. Speech scores use an independent offline transcription, and some synthetic inputs also had recognition errors. Both modes remain experimental. On the same 48 scenarios, the reference cascade scored 19/48 for text and 12/48 for spoken content.

In a control with the same BF16 weights, image, and recordings, the cascade passed 7/12 strict text answers and 2/12 spoken answers. Interleaved generation passed 3/12 and 1/12. With reference text substituted for the recording, both routes passed 6/12 in text and 2/12 in speech. On eight single turns, median time to WAV was 1.677 s for the cascade and 1.871 s for interleaved generation. This compares two ways of running the same Omni model and is separate from the Omni–Gemma tables.

## Choosing a profile and reproducing the benchmark

**Gemma 4 E4B** remains the recommended profile for document questions and strict-format answers on the larger frozen set. **Base Omni** is the candidate for natural Polish multimodal conversation. It loads faster and uses less memory on this host in the Ollama comparison. Results from one host and mainly synthetic inputs need separate confirmation on natural speakers and a physical camera. The closed LoRA pilot and single-generation BF16 dialogue remain research results.

The [Polish assistant benchmark guide](../PL/POLSKI_BENCHMARK_ASYSTENTA.md) describes the commands, result formats, and requirements for frozen inputs. The versioned sources are the [benchmark runner](../../scripts/ollama_bench/polish_benchmark.py), [case definitions](../../scripts/ollama_bench/polish_cases.py), and [manifest lockfile](../../scripts/ollama_bench/polish_v1.lock.json). These tables summarize the recorded runs. Raw audio, host logs, and checkpoints remain in local artifacts.

The local replay index, scripts, and checksums are recorded in `test-results/omni-gemma-matched/README.md`.

Package identities for the paired and historical comparisons:

| Tag | Ollama digest |
| --- | --- |
| `lfm3-omni:2b` | `4c0ee9400634babb880868b873bcebf09fbbf1a5328e550bdbaff25888f1f7e2` |
| `gemma4:e4b` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |

See also the [Venom voice runtime guide](../VOICE_RUNTIME_CAPABILITIES.md) and the [local LFM3 evaluation (Polish)](../PL/LFM3_LOCAL_EVALUATION.md).
