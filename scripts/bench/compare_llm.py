#!/usr/bin/env python
# compare_llm.py
"""
Porównanie czasu odpowiedzi dwóch lokalnych serwerów LLM (vLLM i Ollama) na tych samych promptach.
**Uwaga:** test obciąża GPU/CPU – uruchamiaj na czystym środowisku, bez równoległego Venoma.

Użycie:
  source .venv/bin/activate
  python scripts/bench/compare_llm.py

Konfiguracja (zmienne środowiskowe):
  VLLM_ENDPOINT      - domyślnie localhost:8001/v1 (schemat wg polityki URL)
  OLLAMA_ENDPOINT    - domyślnie localhost:11434/v1 (schemat wg polityki URL)
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

from venom_core.utils.url_policy import build_http_url

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


def _resolve_vllm_start_command(start_cmd: str) -> str:
    if start_cmd:
        return start_cmd
    default_script = os.path.join(os.getcwd(), "scripts/llm/vllm_service.sh")
    if os.path.exists(default_script):
        return f"bash {default_script} start"
    return ""


def _wait_for_vllm_health(endpoint: str, max_wait: int, interval: int) -> bool:
    waited = 0
    while waited < max_wait:
        if check_health(endpoint):
            return True
        if waited % 10 == 0:
            print(f"[bench] czekam na vLLM... ({waited}/{max_wait}s)")
        time.sleep(interval)
        waited += interval
    return False


def _tail_vllm_log(lines_count: int = 20) -> str:
    log_path = os.path.join(os.getcwd(), "logs", "vllm.log")
    if not os.path.exists(log_path):
        return ""
    try:
        with open(log_path, "r") as f:
            return "".join(f.readlines()[-lines_count:])
    except (OSError, UnicodeError):
        # Ignorowanie błędów odczytu logów - nie krytyczne dla diagnostyki
        return ""


def ensure_vllm_running(endpoint: str, start_cmd: str) -> bool:
    """
    Jeśli vLLM nie odpowiada, spróbuj uruchomić go komendą z ENV.
    Zwraca True, jeśli serwer został uruchomiony przez skrypt (do późniejszego stop).
    """
    if check_health(endpoint):
        return False
    start_cmd = _resolve_vllm_start_command(start_cmd)
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
    if _wait_for_vllm_health(endpoint, max_wait, interval):
        print("[bench] vLLM gotowy.")
        return True
    tail = _tail_vllm_log(lines_count=20)
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


def _new_runtime_entry(runtime: str, model: str) -> dict:
    return {"runtime": runtime, "model": model, "prompts": []}


def _append_prompt_result(
    runtime_entry: dict,
    prompt: str,
    endpoint: str,
    model: str,
    *,
    use_chat: bool,
):
    runtime_entry["prompts"].append(
        {
            "prompt": prompt,
            "result": call_chat(endpoint, model, prompt, use_chat=use_chat),
        }
    )


def _append_runtime_error(runtime_entry: dict, prompts: list[str], exc: Exception):
    error_text = str(exc)
    for prompt in prompts:
        runtime_entry["prompts"].append(
            {"prompt": prompt, "result": {"error": error_text}}
        )


def _run_vllm_prompts(vllm_endpoint: str, vllm_model: str) -> dict:
    vllm_entry = _new_runtime_entry("vllm", vllm_model)
    for prompt in PROMPTS:
        _append_prompt_result(
            vllm_entry,
            prompt,
            vllm_endpoint,
            vllm_model,
            use_chat=False,
        )
    return vllm_entry


def _run_ollama_prompts(ollama_endpoint: str, ollama_model: str) -> dict:
    ollama_entry = _new_runtime_entry("ollama", ollama_model)
    for prompt in PROMPTS:
        _append_prompt_result(
            ollama_entry,
            prompt,
            ollama_endpoint,
            ollama_model,
            use_chat=True,
        )
    return ollama_entry


def _benchmark_vllm(
    vllm_endpoint: str,
    vllm_model: str,
    vllm_start_cmd: str,
    vllm_stop_cmd: str,
    force_cleanup: bool,
) -> dict:
    started_vllm = False
    try:
        started_vllm = ensure_vllm_running(vllm_endpoint, vllm_start_cmd)
        return _run_vllm_prompts(vllm_endpoint, vllm_model)
    except Exception as exc:
        print(f"[bench] vLLM nieosiągalny: {exc}")
        vllm_entry = _new_runtime_entry("vllm", vllm_model)
        _append_runtime_error(vllm_entry, PROMPTS, exc)
        return vllm_entry
    finally:
        if force_cleanup or started_vllm:
            stop_vllm(vllm_stop_cmd, started_vllm or force_cleanup)
            kill_leftovers()


def _benchmark_ollama(
    ollama_endpoint: str,
    ollama_model: str,
    ollama_stop_cmd: str,
    force_cleanup: bool,
) -> dict:
    ollama_was_running = check_health(ollama_endpoint)
    started_ollama, ollama_proc = False, None
    ollama_failed = False
    ollama_entry = _new_runtime_entry("ollama", ollama_model)
    try:
        if not ollama_was_running:
            try:
                started_ollama, ollama_proc = ensure_ollama_running(
                    ollama_endpoint, os.getenv("OLLAMA_START_COMMAND", "")
                )
            except Exception as exc:
                ollama_failed = True
                print(f"[bench] Ollama nieosiągalna: {exc}")
                _append_runtime_error(ollama_entry, PROMPTS, exc)
        if not ollama_failed:
            ollama_entry = _run_ollama_prompts(ollama_endpoint, ollama_model)
    finally:
        if started_ollama and ollama_proc:
            ollama_proc.terminate()
            try:
                ollama_proc.wait(timeout=10)
            except Exception:
                ollama_proc.kill()
        if force_cleanup or started_ollama or not ollama_was_running:
            stop_ollama(ollama_stop_cmd, started_by_script=True)
            kill_leftovers()
    return ollama_entry


def _format_prompt_cell(prompt: str, max_len: int = 40) -> str:
    return prompt[:max_len] + ("..." if len(prompt) > max_len else "")


def _build_table_rows(runtime_prompts: list[dict]) -> list[list[str]]:
    rows = [["Lp", "Prompt", "TTFT (ms)", "Czas (ms)", "Tok", "Err"]]
    for idx, entry in enumerate(runtime_prompts, start=1):
        result = entry["result"]
        rows.append(
            [
                str(idx),
                _format_prompt_cell(entry["prompt"]),
                f"{result.get('ttft_ms'):.0f}" if result.get("ttft_ms") else "-",
                f"{result.get('duration_ms'):.0f}"
                if result.get("duration_ms")
                else "-",
                str(result.get("tokens", "-")),
                result.get("error", "-"),
            ]
        )
    return rows


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
        + "|".join(f" {str(cell).ljust(widths[i])} " for i, cell in enumerate(header))
        + "|"
    )
    print(border(char="+", fill="="))
    # data rows
    for row in rows[1:]:
        print(
            "|"
            + "|".join(f" {str(cell).ljust(widths[i])} " for i, cell in enumerate(row))
            + "|"
        )
    print(border())


def run_benchmark():
    vllm_endpoint = os.getenv("VLLM_ENDPOINT", build_http_url("localhost", 8001, "/v1"))
    ollama_endpoint = os.getenv(
        "OLLAMA_ENDPOINT", build_http_url("localhost", 11434, "/v1")
    )
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
    results.append(
        _benchmark_vllm(
            vllm_endpoint=vllm_endpoint,
            vllm_model=vllm_model,
            vllm_start_cmd=vllm_start_cmd,
            vllm_stop_cmd=vllm_stop_cmd,
            force_cleanup=force_cleanup,
        )
    )

    # --- Test Ollama ---
    results.append(
        _benchmark_ollama(
            ollama_endpoint=ollama_endpoint,
            ollama_model=ollama_model,
            ollama_stop_cmd=ollama_stop_cmd,
            force_cleanup=force_cleanup,
        )
    )

    # Prezentacja tabelaryczna z ramkami
    print_box_table("vLLM", _build_table_rows(results[0]["prompts"]))
    print_box_table("Ollama", _build_table_rows(results[1]["prompts"]))

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
