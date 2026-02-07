# Instalacja Windows + WSL na D: (Docker Release)

Ten poradnik jest dla użytkownika, który chce uruchomić Venom Docker release z dystrybucji WSL trzymanej na `D:` (a nie na dysku systemowym `C:`).

Jest oparty o realny proces instalacji end-to-end i zawiera typowe pułapki.

## Cel

- Trzymać dane Docker/WSL na `D:\docker-data`
- Uruchomić Venom z gotowych obrazów (`compose/compose.release.yml`)
- Nie mieszać komend PowerShell z komendami Linux

## Wymagania (przed startem)

- Windows 10/11 z WSL2.
- Aplikacja **Docker Desktop for Windows** (zainstalowana i uruchomiona).
- W Docker Desktop włączone: `Use the WSL 2 based engine`.
- Włączona wirtualizacja (BIOS/UEFI), jeśli Docker/WSL zgłasza błąd startu.
- `Git` w Windows (do klonowania repo).
- Stabilne łącze internetowe (pierwszy start pobiera obrazy i model Ollama).
- Wolne miejsce na dysku `D:`: realnie po instalacji i pierwszym uruchomieniu może zająć ok. `36 GB`; rekomendowane minimum to `45 GB` (bezpiecznie `50 GB`).

## 1. Układ katalogów na hoście (Windows)

Utwórz raz czytelny układ:

```powershell
mkdir D:\docker-data\wsl -Force
mkdir D:\docker-data\venom -Force
```

Rekomendacja:
- `D:\docker-data\wsl` na pliki/import dystrybucji
- `D:\docker-data\venom` na repozytorium projektu

## 2. Utworzenie dedykowanej dystrybucji WSL na D:

W PowerShell:

```powershell
wsl --list --verbose
wsl --export Ubuntu-24.04 D:\docker-data\wsl\ubuntu-base.tar
wsl --import venom-build D:\docker-data\wsl\venom-build D:\docker-data\wsl\ubuntu-base.tar --version 2
del D:\docker-data\wsl\ubuntu-base.tar
```

Uwagi:
- Jeśli widzisz ostrzeżenie o błędnym kluczu w `C:\Users\<użytkownik>\.wslconfig`, popraw ten plik przed dalszą pracą.
- Importowana dystrybucja może odziedziczyć starego usera (np. `pi`). To normalne po `export/import`.

## 3. Włącz integrację Docker Desktop z tą dystrybucją

W Docker Desktop:
1. `Settings` -> `Resources` -> `WSL Integration`
2. Włącz integrację dla `venom-build`
3. Zastosuj i zrestartuj Docker Desktop

Potwierdzenie później w WSL:
- `docker version`
- `docker compose version`

Jeśli `docker compose` nie działa, integracja nie jest poprawnie włączona.

## 4. Klon repozytorium Venom do D:

W PowerShell:

```powershell
git clone https://github.com/mpieniak01/Venom.git D:\docker-data\venom
```

Jeśli katalog już istnieje i nie jest pusty, usuń go albo użyj `git -C D:\docker-data\venom pull`.

## 5. Wejdź do WSL i pracuj komendami Linux

Start shella:

```powershell
wsl -d venom-build -u root
```

Potem w Linux:

```bash
cd /mnt/d/docker-data/venom
apt update
apt install -y dos2unix git make
```

Ważne:
- Ścieżki `/mnt/d/...` to ścieżki Linux.
- `apt`, `export`, `find`, `xargs` uruchamiaj w WSL, nie w PowerShell.

## 6. Jednorazowa naprawa CRLF (problem checkoutu z Windows)

Jeśli widzisz:
- `/usr/bin/env: 'bash\r': No such file or directory`

uruchom w WSL:

```bash
find scripts -type f -name "*.sh" -print0 | xargs -0 dos2unix
dos2unix Makefile
```

Opcjonalnie ustawienie Git na przyszłość (dla tego repo):

```bash
git config core.autocrlf input
```

## 7. Start stosu release

W WSL (Linux shell):

```bash
cd /mnt/d/docker-data/venom
export VENOM_ENABLE_GPU=auto
bash scripts/docker/run-release.sh start
```

Pierwszy start trwa dłużej (pull obrazów + pull modelu).

## 8. Weryfikacja zdrowia usług

```bash
docker compose -f compose/compose.release.yml ps
docker exec -it venom-ollama-release ollama list
curl -fsS http://localhost:8000/healthz
```

Oczekiwany stan:
- backend: `healthy`
- ollama: `healthy`
- frontend: `up` (lub chwilowo `health: starting` podczas rozruchu)
- `ollama list` zawiera `gemma3:4b` (albo wybrany model)
- endpoint health zwraca JSON z `status":"ok"`

## 9. Codzienna obsługa

```bash
cd /mnt/d/docker-data/venom
scripts/docker/run-release.sh status
scripts/docker/run-release.sh logs
scripts/docker/run-release.sh restart
scripts/docker/run-release.sh stop
```

## 10. Najczęstsze pomyłki (mapa błędów)

- `export is not recognized`:
  Jesteś w PowerShell. Przejdź do WSL.
- `apt not recognized`:
  Jesteś w PowerShell. Przejdź do WSL.
- `docker compose plugin is not available`:
  Wyłączona integracja Docker Desktop dla tej dystrybucji.
- `scripts/docker/run-release.sh: No such file or directory`:
  Zły katalog; użyj `/mnt/d/docker-data/venom`.
- Błąd `bash\r`:
  Skonwertuj końce linii przez `dos2unix` jak wyżej.
