# Venom's Polish multimodal assistant — Omni and Gemma 4 E4B

[Wersja polska](../PL/POLISH_MULTIMODAL_ASSISTANT_EXPERIMENT.md)

On November 10, 2026, we compared two local profiles, **LiquidAI LFM3-Omni-2B** and **Gemma 4 E4B**, in Venom Studio and the full Venom application (Full). We measured conversation and document answer accuracy, speech and image understanding, tool selection, playback latency, and memory use. Separate experiments tested model switching, Polish speech output, and whether Omni adapters improved the targeted behaviors.

Gemma passed **254/280 (90.71%)** strict checks on the frozen benchmark, compared with **209/280 (74.64%)** for Omni. In the original application run, Omni started playback sooner and had lower peak memory use. A later repair to Gemma's native speech recognition brought its Chrome score in Full from **1/10 to 7/10**. These results come from three different protocols.

## Hardware, models, and scoring

- One Windows 11 host with Ubuntu under WSL2, an RTX 3060 with 12 GiB of VRAM, and local Ollama 0.40.14. Studio and Full shared a backend. Chrome replayed recorded inputs through a virtual microphone.
- The Ollama tags were `lfm3-omni:2b` and `gemma4:e4b`. Both packages were labelled GGUF Q4_K_M. Their recorded on-disk sizes were about 2.05 GB and 6.58 GB, respectively.
- `pl-assistant-v1` contains 48 validation scenarios and 200 final scenarios. The splits use separate scenario families, documents, and synthetic input voices. Some recordings have noise at 18 dB SNR. Manifest and media hashes were fixed before evaluation. The separate reserved set B for voice adapter evaluation stayed sealed.
- A strict pass requires the expected value and format after word normalization. An extra label or a different inflection can lose a pass. Word error rate (WER) measures transcription errors. We also checked whether transcripts preserved critical names, numbers, and relationships, where a single word can change the meaning.
- GPU figures are peaks for the whole device. WSL RAM use is `MemTotal − MemAvailable`. Both include other processes running on the host. Model runs and listening trials were conducted outside the code quality gates.

## Quality on the 200 frozen scenarios

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
| Time to text answer · conversation, median / p95 | 0.053 / 0.060 s | 0.095 / 0.122 s |
| Time to text answer · recorded instructions, median / p95 | 0.326 / 0.668 s | 0.654 / 1.085 s |
| Median time to WAV · instructions, 8 samples each | 0.511 s | 0.951 s |
| Median time to WAV · image and question, 8 samples each | 0.608 s | 0.821 s |
| Peak GPU memory | 7,962 MiB | 9,741 MiB |
| Peak WSL RAM | 5,081 MiB | 7,950 MiB |
| Execution errors / synthesis sample errors | 0 / 0 | 0 / 0 |

Time to WAV runs from the start of input processing until the script receives the audio file. Model loading was recorded separately. Omni was already resident, while Gemma took 16.99 s to load. The first turns therefore started from different conditions.

## Studio and Full — validation, playback, and memory

On revision `c7849e83`, each model–interface pair produced 68 outcomes through the application API (48 reference-text scenarios, 20 also run on recordings), for 272 results. Standalone spoken instructions in Full used the `/voice` WebSocket. Image and recording cases used an ASR → image and transcript → answer → synthesis pipeline. For tool cases, the script supplied a frozen result after the model selected the correct tool. Gemma used Whisper and Piper in Studio. In Full, the last turn's recorded metadata identified Gemma's native decoder and Piper. The later acceptance run verified the decoder on every turn.

| Profile | Interface | Strict API passes | Strict Chrome passes | Chrome playback start, median / p95 | Peak GPU memory | Peak WSL RAM |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Omni | Studio | 50/68 | 4/10 | 1.210 / 1.425 s | 7,235 MiB | 5,556 MiB |
| Omni | Full | 50/68 | 3/10 | 1.191 / 1.509 s | 7,498 MiB | 5,517 MiB |
| Gemma E4B | Studio | 51/68 | 4/10 | 2.641 / 5.576 s | 9,871 MiB | 9,570 MiB |
| Gemma E4B | Full | 48/68 | 1/10 | 4.532 / 10.276 s | 8,865 MiB | 9,439 MiB |

The separate Chrome run used the same 10 recordings for each configuration. Playback started in all 40 turns. We measured from the end of recording to the `playing` event in Studio or source start in a running `AudioContext` in Full. Both models were warm, the order was fixed (Omni → Gemma), and long answers affected latency. The median interval between the 2,233 memory samples was 289 ms. The API matrix delivered 79/80 WAV files. The missing Studio Gemma response returned HTTP 503 `audio_invalid_output`.

In an earlier short run, all 16 turns played back. Median playback start for the three subsequent turns was **1.258 / 1.330 s** in Studio and Full for Omni, and **4.128 / 1.473 s** for Gemma. Gemma's first cold turn in Full took **13.206 s**. In a separate Gemma → Omni → Gemma switching test, all six turns played back. Model selection and unloading took 1.91 to 2.64 s, with loading deferred to the first inference. We fixed a recording loss in Studio and an HTTP 503 in Full caused by an unload acknowledgement arriving before the model had left memory.

### Gemma acceptance after the Full voice routing change

On revision `5cde42ef`, Full selected native ASR from the local Gemma model and used Gemma's audio instruction format. Every final Full voice turn confirmed `ollama_audio_llm_piper`. Direct in both interfaces prioritized the current question, user decisions, and requested format. A separate trial of native Gemma ASR in Studio scored 2/10 in Chrome against a 4/10 baseline, so Studio returned to CUDA Whisper medium. Both Gemma configurations used Piper for synthesis.

| Interface | API / WS, recordings | Chrome, strict passes | Chrome WER | Playback start after change, median / p95 |
| --- | ---: | ---: | ---: | ---: |
| Studio | 4/10 → 6/10 | 4/10 → 6/10 | 4% → 2% | 1.541 / 2.255 s |
| Full | 1/10 → 5/10 | 1/10 → 7/10 | 15% → 9% | 1.325 / 1.753 s |

Reference-text scores rose from 39/48 to 43/48 in both interfaces. Chrome played 10/10 responses in each, while the APIs delivered 9/10 in Studio and 10/10 in Full. Studio reproduced `audio_invalid_output`. This run measured latency and quality again on the same recordings. The memory tables and the frozen 200-scenario scores come from earlier configurations.

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

## Choosing a profile and reproducing the benchmark

**Gemma 4 E4B** is the quality recommendation for tasks in the frozen benchmark, including document questions and answers with strict formatting. **Base Omni** is the experimental profile for Polish voice conversation with native input and output, with lower latency and memory use in the original application run. The later Full test verified Gemma's native input with Piper playback. Profile choice depends on the relative importance of answer quality, latency, memory, and speech naturalness. The runs used one host and mainly synthetic input. Physical camera acceptance and broader listening tests remain separate.

The [Polish assistant benchmark guide](../PL/POLSKI_BENCHMARK_ASYSTENTA.md) describes the commands, result formats, and requirements for frozen inputs. The versioned sources are the [benchmark runner](../../scripts/ollama_bench/polish_benchmark.py), [case definitions](../../scripts/ollama_bench/polish_cases.py), and [manifest lockfile](../../scripts/ollama_bench/polish_v1.lock.json). These tables summarize the recorded runs. Raw audio, host logs, and checkpoints remain in local artifacts.

Model identities for the frozen comparison:

| Tag | Ollama digest |
| --- | --- |
| `lfm3-omni:2b` | `4c0ee9400634babb880868b873bcebf09fbbf1a5328e550bdbaff25888f1f7e2` |
| `gemma4:e4b` | `dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c` |

See also the [Venom voice runtime guide](../VOICE_RUNTIME_CAPABILITIES.md) and the [local LFM3 evaluation (Polish)](../PL/LFM3_LOCAL_EVALUATION.md).
