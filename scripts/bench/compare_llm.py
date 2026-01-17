#!/usr/bin/env python
# compare_llm.py
"""
Porównanie czasu odpowiedzi dwóch lokalnych serwerów LLM (vLLM i Ollama) na tych samych promptach.
**Uwaga:** test obciąża GPU/CPU – uruchamiaj na czystym środowisku, bez równoległego Venoma.

Użycie:
  source .venv/bin/activate
  python scripts/bench/compare_llm.py

Konfiguracja (zmienne środowiskowe):
  VLLM_ENDPOINT      - domyślnie http://localhost:8001/v1
  OLLAMA_ENDPOINT    - domyślnie http://localhost:11434/v1
  VLLM_MODEL         - domyślnie gemma-3-4b-it
  OLLAMA_MODEL       - domyślnie gemma3:4b
  OLLAMA_START_COMMAND- opcjonalnie; fallback do `ollama serve`
  VLLM_START_COMMAND - opcjonalnie; fallback do scripts/llm/vllm_service.sh start
  VLLM_STOP_COMMAND  - opcjonalnie; fallback do scripts/llm/vllm_service.sh stop
  OLLAMA_STOP_COMMAND- opcjonalnie; domyślnie użyjemy `ollama stop`
  BENCH_FORCE_CLEANUP- domyślnie 1; jeśli 1, po teście zatrzymujemy oba serwery (nawet jeśli działały przed testem)
"""

import json
import os
import shlex
import subprocess
import time

import requests

PROMPTS = [
    "Co to jest kwadrat?",
    "Wyjaśnij w 2 zdaniach zasadę działania silnika spalinowego.",
    "Napisz krótką (40 słów) odpowiedź: dlaczego testy jednostkowe są ważne?",
    (
        "Streszcz i podsumuj w ~200 słowach (po polsku) znaczenie testów automatycznych "
        "w projektach produkcyjnych, uwzględniając różne poziomy testów (unit/integration/e2e), "
        "wpływ na regresje oraz tempo dostarczania. Dodaj krótką, wypunktowaną listę dobrych praktyk."
    ),
]


def call_chat(endpoint: str, model: str, prompt: str, use_chat: bool = True) -> dict:
    """
    Wysyła pojedynczy prompt i mierzy TTFT oraz całkowity czas.
    Dla vLLM bez chat template używamy /completions z polem prompt.
    """
    if use_chat:
        url = f"{endpoint.rstrip('/')}/chat/completions"
        payload = {
            "model": model,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 400,
        }
    else:
        url = f"{endpoint.rstrip('/')}/completions"
        payload = {
            "model": model,
            "stream": True,
            "prompt": prompt,
            "max_tokens": 400,
        }
    headers = {"Content-Type": "application/json"}

    start = time.time()
    ttft = None
    tokens = 0
    try:
        with requests.post(
            url, headers=headers, data=json.dumps(payload), stream=True, timeout=120
        ) as resp:
            try:
                resp.raise_for_status()
            except requests.HTTPError as exc:
                # Zwróć treść błędu z serwera (np. max_tokens/ctx)
                try:
                    detail = resp.json()
                except Exception:
                    detail = resp.text
                return {
                    "error": f"{exc}: {detail}",
                    "ttft_ms": None,
                    "duration_ms": None,
                    "tokens": 0,
                }
            for line in resp.iter_lines():
                if not line or not line.startswith(b"data: "):
                    continue
                tokens += 1  # przybliżenie liczby chunków ~ liczba tokenów
                if ttft is None:
                    ttft = (time.time() - start) * 1000.0
    except Exception as exc:
        return {
            "error": str(exc),
            "ttft_ms": None,
            "duration_ms": None,
            "tokens": tokens,
        }

    duration_ms = (time.time() - start) * 1000.0
    return {"ttft_ms": ttft, "duration_ms": duration_ms, "tokens": tokens}


def _read_env_var_from_dotenv(key: str) -> str | None:
    """Proste odczytanie wartości z lokalnego .env (bez eksportu)."""
    dotenv_path = os.path.join(os.getcwd(), ".env")
    if not os.path.exists(dotenv_path):
        return None
    try:
        with open(dotenv_path, "r") as f:
            for line in f:
                if not line or line.lstrip().startswith("#"):
                    continue
                if "=" not in line:
                    continue
                k, v = line.split("=", 1)
                if k.strip() == key:
                    return v.strip()
    except Exception:
        return None
    return None


def check_health(endpoint: str, timeout: int = 3) -> bool:
    url = f"{endpoint.rstrip('/')}/models"
    try:
        resp = requests.get(url, timeout=timeout)
        return resp.status_code == 200
    except Exception:
        return False


def ensure_vllm_running(endpoint: str, start_cmd: str) -> bool:
    """
    Jeśli vLLM nie odpowiada, spróbuj uruchomić go komendą z ENV.
    Zwraca True, jeśli serwer został uruchomiony przez skrypt (do późniejszego stop).
    """
    if check_health(endpoint):
        return False
    # Fallback do lokalnego skryptu jeśli brak zmiennej
    if not start_cmd:
        default_script = os.path.join(os.getcwd(), "scripts/llm/vllm_service.sh")
        if os.path.exists(default_script):
            start_cmd = f"bash {default_script} start"
    if not start_cmd:
        raise RuntimeError(
            "vLLM nie odpowiada, a VLLM_START_COMMAND nie jest ustawione."
        )
    print(f"[bench] vLLM offline, uruchamiam: {start_cmd}")
    proc = subprocess.run(shlex.split(start_cmd), capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            f"Nie udało się uruchomić vLLM: {proc.stderr or proc.stdout}"
        )
    # Odczekaj na health
    max_wait = int(
        os.getenv("VLLM_HEALTH_TIMEOUT", "90")
    )  # dłuższy limit dla wolnych startów/WSL
    interval = int(os.getenv("VLLM_HEALTH_INTERVAL", "3"))
    waited = 0
    while waited < max_wait:
        if check_health(endpoint):
            print("[bench] vLLM gotowy.")
            return True
        if waited % 10 == 0:
            print(f"[bench] czekam na vLLM... ({waited}/{max_wait}s)")
        time.sleep(interval)
        waited += interval
    # Przy timeout dołącz ostatnie linie z logs/vllm.log (jeśli istnieje)
    log_path = os.path.join(os.getcwd(), "logs", "vllm.log")
    tail = ""
    if os.path.exists(log_path):
        try:
            with open(log_path, "r") as f:
                lines = f.readlines()[-20:]
                tail = "".join(lines)
        except Exception:
            # Ignorowanie błędów odczytu logów - nie krytyczne dla diagnostyki
            pass
    raise RuntimeError(
        f"vLLM nie odpowiada po uruchomieniu (timeout {max_wait}s). "
        f"Ostatnie logi:\n{tail or 'brak logów/nie udało się odczytać.'}"
    )


def stop_vllm(stop_cmd: str, started_by_script: bool):
    """Zatrzymaj vLLM jeśli był uruchomiony przez skrypt (lub gdy jawnie podano stop_cmd)."""
    cmd = stop_cmd.strip()
    if not cmd:
        default_script = os.path.join(os.getcwd(), "scripts/llm/vllm_service.sh")
        if os.path.exists(default_script):
            cmd = f"bash {default_script} stop"
    if started_by_script or stop_cmd:
        print(f"[bench] zatrzymuję vLLM: {cmd}")
        subprocess.run(shlex.split(cmd), capture_output=True, text=True)


def stop_ollama(stop_cmd: str, started_by_script: bool):
    """Zatrzymaj Ollamę jeśli była uruchomiona przez skrypt (lub gdy jawnie podano stop_cmd)."""
    if not started_by_script and not stop_cmd:
        return
    cmd = stop_cmd.strip() if stop_cmd else "ollama stop"
    print(f"[bench] zatrzymuję Ollama: {cmd}")
    subprocess.run(shlex.split(cmd), capture_output=True, text=True)


def ensure_ollama_running(endpoint: str, start_cmd: str):
    """
    Jeśli Ollama nie odpowiada, spróbuj ją uruchomić.
    Zwraca (started_by_script, proc) gdzie proc to Popen gdy uruchomiono lokalnie.
    """
    if check_health(endpoint):
        return False, None
    cmd = start_cmd.strip() if start_cmd else "ollama serve"
    print(f"[bench] Ollama offline, uruchamiam: {cmd}")
    proc = subprocess.Popen(
        shlex.split(cmd), stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )
    max_wait = int(os.getenv("OLLAMA_HEALTH_TIMEOUT", "60"))
    interval = int(os.getenv("OLLAMA_HEALTH_INTERVAL", "2"))
    waited = 0
    while waited < max_wait:
        if check_health(endpoint):
            print("[bench] Ollama gotowa.")
            return True, proc
        if waited % 10 == 0:
            print(f"[bench] czekam na Ollama... ({waited}/{max_wait}s)")
        time.sleep(interval)
        waited += interval
    proc.terminate()
    raise RuntimeError(f"Ollama nie odpowiada po uruchomieniu (timeout {max_wait}s).")


def _gpu_processes():
    """Zwraca listę procesów GPU z nvidia-smi (pid, name, mem)."""
    try:
        out = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-compute-apps=pid,process_name,used_memory",
                "--format=csv,noheader",
            ],
            text=True,
        )
        rows = []
        for line in out.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3:
                rows.append({"pid": parts[0], "name": parts[1], "mem": parts[2]})
        return rows
    except Exception:
        return []


def kill_leftovers():
    """Spróbuj ubić typowe procesy LLM na GPU i zweryfikować zwolnienie."""
    patterns = ["vllm serve", "VLLM::EngineCore", "ollama runner"]
    for pat in patterns:
        subprocess.run(["pkill", "-f", pat], capture_output=True)
    time.sleep(2)
    leftovers = _gpu_processes()
    if leftovers:
        print("[bench] Ostrzeżenie: GPU nadal zajęty przez:")
        for p in leftovers:
            print(f" - PID {p['pid']}: {p['name']} ({p['mem']})")
    else:
        print("[bench] GPU czyste (brak procesów nvidia-smi).")


def run_benchmark():
    vllm_endpoint = os.getenv("VLLM_ENDPOINT", "http://localhost:8001/v1")
    ollama_endpoint = os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434/v1")
    vllm_model = os.getenv("VLLM_MODEL") or _read_env_var_from_dotenv("VLLM_MODEL")
    if not vllm_model:
        vllm_model = (
            os.getenv("VLLM_SERVED_MODEL_NAME")
            or _read_env_var_from_dotenv("VLLM_SERVED_MODEL_NAME")
            or os.path.basename(os.getenv("VLLM_MODEL_PATH", ""))
            or "gemma-3-4b-it"
        )
    ollama_model = os.getenv("OLLAMA_MODEL", "gemma3:4b")
    vllm_start_cmd = os.getenv("VLLM_START_COMMAND", "").strip()
    vllm_stop_cmd = os.getenv("VLLM_STOP_COMMAND", "").strip()
    ollama_stop_cmd = os.getenv("OLLAMA_STOP_COMMAND", "").strip()
    force_cleanup = os.getenv("BENCH_FORCE_CLEANUP", "1") == "1"

    results = []

    # --- Test vLLM ---
    vllm_entry = {"runtime": "vllm", "model": vllm_model, "prompts": []}

    started_vllm = False
    try:
        started_vllm = ensure_vllm_running(vllm_endpoint, vllm_start_cmd)
        for prompt in PROMPTS:
            vllm_entry["prompts"].append(
                {
                    "prompt": prompt,
                    "result": call_chat(
                        vllm_endpoint, vllm_model, prompt, use_chat=False
                    ),
                }
            )
    except Exception as exc:
        print(f"[bench] vLLM nieosiągalny: {exc}")
        for prompt in PROMPTS:
            vllm_entry["prompts"].append(
                {"prompt": prompt, "result": {"error": str(exc)}}
            )
    finally:
        if force_cleanup or started_vllm:
            stop_vllm(vllm_stop_cmd, started_vllm or force_cleanup)
            kill_leftovers()
    results.append(vllm_entry)

    # --- Test Ollama ---
    ollama_entry = {"runtime": "ollama", "model": ollama_model, "prompts": []}
    ollama_was_running = check_health(ollama_endpoint)
    started_ollama, ollama_proc = False, None
    ollama_failed = False
    try:
        if not ollama_was_running:
            try:
                started_ollama, ollama_proc = ensure_ollama_running(
                    ollama_endpoint, os.getenv("OLLAMA_START_COMMAND", "")
                )
            except Exception as exc:
                ollama_failed = True
                print(f"[bench] Ollama nieosiągalna: {exc}")
                for prompt in PROMPTS:
                    ollama_entry["prompts"].append(
                        {"prompt": prompt, "result": {"error": str(exc)}}
                    )
        if not ollama_failed:
            for prompt in PROMPTS:
                ollama_entry["prompts"].append(
                    {
                        "prompt": prompt,
                        "result": call_chat(ollama_endpoint, ollama_model, prompt),
                    }
                )
    finally:
        # jeśli startowaliśmy własny serwer, zamknijmy go grzecznie
        if started_ollama and ollama_proc:
            ollama_proc.terminate()
            try:
                ollama_proc.wait(timeout=10)
            except Exception:
                ollama_proc.kill()
        if force_cleanup or started_ollama or not ollama_was_running:
            stop_ollama(ollama_stop_cmd, started_by_script=True)
            kill_leftovers()
    results.append(ollama_entry)

    def print_box_table(title: str, rows: list[list[str]]):
        # oblicz szerokości kolumn
        widths = [max(len(str(cell)) for cell in col) for col in zip(*rows)]

        def border(char="+", fill="-"):
            return char + char.join(fill * (w + 2) for w in widths) + char

        print(f"\n=== {title} ===")
        print(border())
        # header
        header = rows[0]
        print(
            "|"
            + "|".join(
                f" {str(cell).ljust(widths[i])} " for i, cell in enumerate(header)
            )
            + "|"
        )
        print(border(char="+", fill="="))
        # data rows
        for row in rows[1:]:
            print(
                "|"
                + "|".join(
                    f" {str(cell).ljust(widths[i])} " for i, cell in enumerate(row)
                )
                + "|"
            )
        print(border())

    # Prezentacja tabelaryczna z ramkami
    v_rows = [["Lp", "Prompt", "TTFT (ms)", "Czas (ms)", "Tok", "Err"]]
    for i, entry in enumerate(results[0]["prompts"], start=1):
        v = entry["result"]
        v_rows.append(
            [
                str(i),
                entry["prompt"][:40] + ("..." if len(entry["prompt"]) > 40 else ""),
                f"{v.get('ttft_ms'):.0f}" if v.get("ttft_ms") else "-",
                f"{v.get('duration_ms'):.0f}" if v.get("duration_ms") else "-",
                str(v.get("tokens", "-")),
                v.get("error", "-"),
            ]
        )
    print_box_table("vLLM", v_rows)

    o_rows = [["Lp", "Prompt", "TTFT (ms)", "Czas (ms)", "Tok", "Err"]]
    for i, entry in enumerate(results[1]["prompts"], start=1):
        o = entry["result"]
        o_rows.append(
            [
                str(i),
                entry["prompt"][:40] + ("..." if len(entry["prompt"]) > 40 else ""),
                f"{o.get('ttft_ms'):.0f}" if o.get("ttft_ms") else "-",
                f"{o.get('duration_ms'):.0f}" if o.get("duration_ms") else "-",
                str(o.get("tokens", "-")),
                o.get("error", "-"),
            ]
        )
    print_box_table("Ollama", o_rows)

    # JSON do dalszego przetwarzania
    print("\n=== JSON ===")
    print(
        json.dumps(
            {"prompts": len(PROMPTS), "results": results}, indent=2, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    run_benchmark()
    # Przywróć środowisko do stanu sprzed testu:
    # - vLLM zatrzymany (obsługuje stop_vllm)
    # - Ollama zatrzymana tylko jeśli uruchamiana przez skrypt lub podano OLLAMA_STOP_COMMAND
    # - Jeśli wcześniej Venom backend/UI były wyłączone, uruchom je ręcznie (np. make start) dopiero po teście
