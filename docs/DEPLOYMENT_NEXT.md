# Deploy Venom 1.10.0 on Linux or WSL2

[Wersja polska](PL/DEPLOYMENT_NEXT.md) · [Project README](../README.md)

Use `dev` for single-operator use and development. Use `preprod` for isolated, read-only acceptance checks. The `prod` environment is reserved. If you already have an instance launcher, keep its repository path, environment files, data roots and ports. See the [environment support matrix](ENVIRONMENTS_SUPPORT.md).

## Install from source

On Linux x86-64, including an x86-64 WSL2 distribution, use the pinned Python **3.14.8**, Node.js **24.22.0**, and npm **11.19.1**. Install Git, GNU Make and curl. Full also needs a C compiler and Linux input headers to build `evdev`. On Debian or Ubuntu the system packages are `build-essential` and `linux-libc-dev`. Set up the exact Python and Node versions before running the commands below.

```bash
git clone https://github.com/mpieniak01/Venom.git
cd Venom
python3.14 --version
node --version
npm --version
python3.14 scripts/bootstrap_dependency_profile.py --profile full --venv "$PWD/.venv"
npm --prefix web-next ci
make ensure-env-file ENVIRONMENT=dev
```

The bootstrap uses the interpreter that invokes it and creates the new virtual environment from the Full lock. It checks available storage. The Full installation requires at least 16 GiB free at its installation location. Leave additional space for Ollama models, data and web build output. Both applications use the same `web-next/node_modules` installation. For an existing deployment, validate the new profile in a separate virtual environment before switching. See the [dependency profiles and qualification status](DEPENDENCY_PROFILES.md).

## Configure Ollama and the local model

Run Ollama on the Linux host, then prepare Gemma 4 E4B. Set `OLLAMA_HOST` for the Ollama CLI if your instance uses a custom address.

```bash
curl -fsS http://127.0.0.1:11434/api/version
ollama pull gemma4:e4b
ollama list
```

Edit `.env.dev` for the default Ollama listener. Keep credentials and machine-specific settings in your private environment file.

```dotenv
ACTIVE_LLM_SERVER=ollama
LLM_SERVICE_TYPE=local
LLM_LOCAL_ENDPOINT=http://127.0.0.1:11434/v1
LLM_MODEL_NAME=gemma4:e4b
```

## Start Studio or Venom Full

Studio runs a separate Next.js app (`web-studio`) and the Studio subset of the shared FastAPI API (`venom_core.studio_main:app`). Venom Full runs `web-next` and `venom_core.main:app`. Both use Turbopack in the default dev startup. For loopback-only access, export `HOST=127.0.0.1 WEB_HOST=127.0.0.1` in the shell used for start, status and stop.

Run the block for the application you want. The launcher prints the UI and API addresses. Repository defaults for dev are UI `3000` and API `8000`.

### Studio

```bash
make stack-plan VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=dev
make start-studio PROFILE=full ENVIRONMENT=dev
make status-studio PROFILE=full ENVIRONMENT=dev
curl -fsS http://127.0.0.1:8000/healthz
```

Open [Chat 2.0](http://localhost:3000/chat2) and send a short Direct message. When finished, stop Studio from the same checkout and configuration.

```bash
make stop-studio PROFILE=full ENVIRONMENT=dev
```

### Venom Full

```bash
make stack-plan VENOM_VARIANT=venom PROFILE=full ENVIRONMENT=dev
make start-venom PROFILE=full ENVIRONMENT=dev
make status-venom PROFILE=full ENVIRONMENT=dev
curl -fsS http://127.0.0.1:8000/healthz
```

Open [chat](http://localhost:3000/chat) or [voice](http://localhost:3000/voice). When finished, stop Venom Full.

```bash
make stop-venom PROFILE=full ENVIRONMENT=dev
```

Stop the active variant before starting the other. The launchers preserve server-side history, materials and notes in the same environment. Browser drafts depend on the UI origin. The variant-specific stop targets also stop a local engine when that launcher owns it and can verify its identity. A separately managed Ollama service keeps running under its own lifecycle. For custom ports, paths or bind addresses, use the same overrides on status and stop. [Runtime ownership and switching](STUDIO.md)

## Configure voice

With the Full dependencies, set `ENABLE_AUDIO_INTERFACE=true` in `.env.dev`. For speech output on the Gemma path, set `TTS_MODEL_PATH` to the absolute path of an installed Piper `.onnx` voice and keep its `.onnx.json` alongside it. Choose the Whisper size with `WHISPER_MODEL_SIZE`. For CPU audio, set both `AUDIO_DEVICE=cpu` and `TTS_USE_CUDA=false`. For GPU audio, install the required CUDA libraries for the selected dependencies. [Audio dependencies](DEPENDENCY_PROFILES.md)

To try Omni, run `ollama pull lfm3-omni:2b` against a loopback Ollama endpoint on the Venom host. Use an Ollama build with native audio input and output support for that model. Select it in Chat 2.0 or the Full voice screen. Keep automatic voice routing for the native path (`VOICE_ROUTE_PROFILE=auto`, `AUDIO_DECODER_PROFILE=auto` and an empty `AUDIO_DECODER_CHAIN`). Apply startup settings by restarting the active variant, allow microphone access in the browser, and confirm both transcription and playback. Keep host-specific measurements in the private local report.

## Runtime profiles and isolated verification

`PROFILE=light` pauses background work and skips model warmup. It can use the already installed Full dependencies. Use the Light dependency lock only for the API and basic chat use case. Install it into a separate virtual environment if you need both dependency sets, and pass the same `VENV` override to start, status and stop. For Studio with the Light dependency set, stop any running variant and prepare `.env.dev` and the shared web dependencies before running these commands.

```bash
python3.14 scripts/bootstrap_dependency_profile.py --profile light --venv "$PWD/.venv-light"
make start-studio PROFILE=light ENVIRONMENT=dev VENV=.venv-light
make status-studio PROFILE=light ENVIRONMENT=dev VENV=.venv-light
```

```bash
make stop-studio PROFILE=light ENVIRONMENT=dev VENV=.venv-light
```

[Stack profiles](STACK_PROFILES.md) · [Dependency profiles](DEPENDENCY_PROFILES.md)

For read-only checks, stop the running variant first and create `.env.preprod` from its own template.

```bash
make ensure-env-file ENVIRONMENT=preprod
```

Configure the provider in `.env.preprod` if the check requires inference. Preprod keeps separate data, cache, queues, logs and build output. The default UI/API ports are `3100`/`8100`.

```bash
make stack-plan VENOM_VARIANT=venom PROFILE=full ENVIRONMENT=preprod
make start-venom PROFILE=full ENVIRONMENT=preprod
make status-venom PROFILE=full ENVIRONMENT=preprod
curl -fsS http://127.0.0.1:8100/healthz
make stop-venom PROFILE=full ENVIRONMENT=preprod
```

For Studio preprod, use `VENOM_VARIANT=studio` in the plan and the `*-studio` targets with `ENVIRONMENT=preprod`. Use the addresses from the launcher for custom ports. [Preprod rules](ENVIRONMENTS_SUPPORT.md)

## Build Studio for standalone startup

Stop the UI before building. Keep the same profile, environment and public configuration between build and startup. Rebuild after changes to source, public settings or Node.js.

```bash
make web-build VENOM_VARIANT=studio PROFILE=full ENVIRONMENT=dev
make start-studio PROFILE=full ENVIRONMENT=dev START_WEB_MODE=standalone
```

[Web build and artifact lifecycle](PL/WEB_LIFECYCLE.md)

## Verify and operate

- Use the matching `status` target and check `/healthz`. Send a Direct message to verify the selected provider and model. Health checks report process liveness.
- If audio is enabled, record a short question and confirm the answer plays in the browser.
- Use `make stack-plan` for effective ports, data and log paths. Inspect backend and web logs if a start fails. Repository defaults are under `logs/` in dev and `logs/preprod/` in preprod.
- Use `make runtime-log-policy-audit` to review the local retention and rotation settings. [Backup and environment isolation](ENVIRONMENTS_SUPPORT.md)
- For containers, the current images use the Light dependency set. Follow the [Docker stack profile guide](PL/DOCKER_PROFILES.md) for local builds and the [Docker release guide](DOCKER_RELEASE_GUIDE.md) for tagged images.
