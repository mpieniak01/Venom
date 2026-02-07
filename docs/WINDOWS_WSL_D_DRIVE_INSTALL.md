# Windows + WSL Install on D: (Docker Release)

This guide is for users who want to run Venom Docker release from a WSL distro stored on `D:` (not on system drive `C:`).

It is based on a real end-to-end setup flow and includes common pitfalls.

## Goal

- Keep Docker/WSL work data on `D:\docker-data`
- Run Venom from prebuilt images (`compose/compose.release.yml`)
- Avoid mixing PowerShell commands with Linux commands

## Prerequisites (before you start)

- Windows 10/11 with WSL2 support.
- **Docker Desktop for Windows** installed and running.
- Docker Desktop option enabled: `Use the WSL 2 based engine`.
- Virtualization enabled in BIOS/UEFI if Docker/WSL fails to start.
- `Git` installed on Windows (for repository clone).
- Stable internet connection (first run pulls images and Ollama model).
- Free space on `D:`: real post-install footprint can reach about `36 GB`; recommended minimum is `45 GB` (safe target `50 GB`).

## Windows installer (one-click)

If you want a no-terminal setup, use installer assets from GitHub Releases:

- Venom Releases: `https://github.com/mpieniak01/Venom/releases`
- Latest release page: `https://github.com/mpieniak01/Venom/releases/latest`

If a Windows installer is attached to a release, download it from `Assets` and run it.

## 1. Host layout (Windows)

Create a clear structure once:

```powershell
mkdir D:\docker-data\wsl -Force
mkdir D:\docker-data\venom -Force
```

Recommended:
- `D:\docker-data\wsl` for imported distro files
- `D:\docker-data\venom` for repository checkout

## 2. Create dedicated WSL distro on D:

In PowerShell:

```powershell
wsl --list --verbose
wsl --export Ubuntu-24.04 D:\docker-data\wsl\ubuntu-base.tar
wsl --import venom-build D:\docker-data\wsl\venom-build D:\docker-data\wsl\ubuntu-base.tar --version 2
del D:\docker-data\wsl\ubuntu-base.tar
```

Notes:
- If you see warning about invalid key in `C:\Users\<you>\.wslconfig`, fix that file before proceeding.
- Imported distro may keep original user (for example `pi`). This is normal for exported/imported images.

## 3. Enable Docker Desktop integration for this distro

In Docker Desktop:
1. `Settings` -> `Resources` -> `WSL Integration`
2. Enable integration for `venom-build`
3. Apply and restart Docker Desktop

Verify inside WSL later:
- `docker version`
- `docker compose version`

If `docker compose` is missing, integration is not correctly enabled.

## 4. Clone Venom into D:

In PowerShell:

```powershell
git clone https://github.com/mpieniak01/Venom.git D:\docker-data\venom
```

If folder exists and is not empty, either remove it first or use `git -C D:\docker-data\venom pull`.

## 5. Enter WSL and run Linux commands

Start shell:

```powershell
wsl -d venom-build -u root
```

Then in Linux shell:

```bash
cd /mnt/d/docker-data/venom
apt update
apt install -y dos2unix git make
```

Important:
- `/mnt/d/...` paths are Linux paths.
- Do not run `apt`, `export`, `find`, `xargs` in PowerShell.

## 6. Fix CRLF once (Windows checkout issue)

If you get:
- `/usr/bin/env: 'bash\r': No such file or directory`

run in WSL:

```bash
find scripts -type f -name "*.sh" -print0 | xargs -0 dos2unix
dos2unix Makefile
```

Optional Git setting to prevent future CRLF issues in this repo:

```bash
git config core.autocrlf input
```

## 7. Start release stack

In WSL (Linux shell):

```bash
cd /mnt/d/docker-data/venom
export VENOM_ENABLE_GPU=auto
bash scripts/docker/run-release.sh start
```

First run can take longer (image pulls + model pull).

## 8. Verify healthy state

```bash
docker compose -f compose/compose.release.yml ps
docker exec -it venom-ollama-release ollama list
curl -fsS http://localhost:8000/healthz
```

Expected:
- backend: `healthy`
- ollama: `healthy`
- frontend: `up` (or shortly `health: starting` during warmup)
- `ollama list` shows `gemma3:4b` (or your selected model)
- health endpoint returns JSON with `status":"ok"`

## 9. Daily operations

```bash
cd /mnt/d/docker-data/venom
scripts/docker/run-release.sh status
scripts/docker/run-release.sh logs
scripts/docker/run-release.sh restart
scripts/docker/run-release.sh stop
```

## 10. Common mistakes (quick mapping)

- `export is not recognized`:
  You are in PowerShell. Switch to WSL shell.
- `apt not recognized`:
  You are in PowerShell. Switch to WSL shell.
- `docker compose plugin is not available`:
  Docker Desktop WSL integration for this distro is disabled.
- `scripts/docker/run-release.sh: No such file or directory`:
  Wrong directory; use `/mnt/d/docker-data/venom`.
- `bash\r` error:
  Convert line endings using `dos2unix` as shown above.

## 11. Full cleanup (back to initial state)

Use this when you want to remove Venom code + Venom WSL distro and return to clean baseline.

### Step A - stop and remove Venom stack

In WSL:

```bash
cd /mnt/d/docker-data/venom
scripts/docker/run-release.sh stop || true
docker compose -f compose/compose.release.yml down -v --remove-orphans || true
```

### Step B - remove Venom code folder

In PowerShell:

```powershell
Remove-Item -Recurse -Force D:\docker-data\venom
```

### Step C - remove dedicated Venom WSL distro

In PowerShell:

```powershell
wsl --terminate venom-build
wsl --unregister venom-build
```

### Step D - optional Docker cleanup (global, destructive)

Use only if you want to wipe Docker data for all projects:

```powershell
wsl --shutdown
wsl --unregister docker-desktop
wsl --unregister docker-desktop-data
```

Then you can uninstall Docker Desktop from Windows Apps.

### Step E - remove leftover folders on D:

In PowerShell:

```powershell
Remove-Item -Recurse -Force D:\docker-data\wsl\venom-build
```

Verification:

```powershell
wsl -l -v
```

`venom-build` should no longer be listed.
