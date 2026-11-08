"""Read-only evidence for explicit Full operator diagnostics."""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import stat
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from venom_core.core.permission_guard import AutonomyViolation, permission_guard
from venom_core.core.slash_commands import parse_slash_command
from venom_core.utils.logger import LOG_DIR

DIAGNOSTICS_INTENT = "OPERATOR_DIAGNOSTICS"
RUNBOOK = "docs/PL/OPERATOR_MANUAL.md#4-diagnostyka-full"
HOST_CHECK = "make status-venom PROFILE=full ENVIRONMENT=dev"
_RIDER_PATH = "/api/v1/rider/status?section=overview"
_SERVICES_PATH = "/api/v1/system/services"
_COMMAND = re.compile(
    r"(?:(?P<guide>jak sprawdzić|how to check)|sprawdź|check) "
    r"(?:(?:stan|status(?: of)?) )?"
    r"(?P<target>venom(?:a)?|rider(?:-pi|a)?|venom(?:a)? (?:i|and) rider(?:-pi|a)?)"
    r"[?.]?",
    re.IGNORECASE,
)
_RIDER_SECTIONS = ("control", "settings", "telemetry", "health", "system")
_LOG_LEVEL = re.compile(
    rb"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+ \| (WARNING|ERROR|CRITICAL)\s+\|",
    re.MULTILINE,
)
_LOG_LIMIT = 16384
_BODY_LIMIT = 262144
_SERVICE_NAME = re.compile(r"[a-zA-Z0-9_. -]{1,48}")
_STALE_AFTER = 5.0


@dataclass(frozen=True)
class DiagnosticRequest:
    guide: bool
    venom: bool
    rider: bool


def parse_diagnostic_request(content: str) -> DiagnosticRequest | None:
    """Match a complete instruction with a fixed target and no command arguments."""
    match = _COMMAND.fullmatch(" ".join(content.strip().split()))
    if match is None:
        return None
    target = match["target"].casefold()
    return DiagnosticRequest(
        bool(match["guide"]), target.startswith("venom"), "rider" in target
    )


def parse_diagnostic_task(content: str) -> DiagnosticRequest | None:
    """Apply the same slash normalization used before task dispatch."""
    slash = parse_slash_command(content)
    return parse_diagnostic_request(slash.cleaned if slash else content)


@dataclass(frozen=True)
class Evidence:
    source: str
    status: str
    detail: str
    observed_at: datetime

    def render(self) -> str:
        return f"- {self.source} · **{self.status}** · {self.detail} · {self.observed_at.isoformat(timespec='seconds')}"


@dataclass(frozen=True)
class ProbeResult:
    payload: dict | None
    status: str
    detail: str


def _loopback_origin(endpoint: str) -> str | None:
    try:
        url = urlsplit(endpoint)
        if (
            url.scheme == "http"
            and url.hostname in {"127.0.0.1", "::1", "localhost"}
            and url.username is None
            and url.password is None
            and url.port is not None
        ):
            return f"http://{url.netloc}"
    except ValueError:
        pass
    return None


async def _read_json(client: httpx.AsyncClient, path: str) -> ProbeResult:
    try:
        async with asyncio.timeout(4), client.stream("GET", path) as response:
            if response.status_code in {401, 403}:
                return ProbeResult(None, "odmowa", f"HTTP {response.status_code}")
            if not response.is_success:
                return ProbeResult(None, "niedostępne", f"HTTP {response.status_code}")
            body = bytearray()
            async for chunk in response.aiter_bytes():
                if len(body) + len(chunk) > _BODY_LIMIT:
                    return ProbeResult(
                        None, "niepełne", "Przekroczono limit odpowiedzi"
                    )
                body.extend(chunk)
            payload = json.loads(body)
            if isinstance(payload, dict):
                return ProbeResult(payload, "odczytano", f"HTTP {response.status_code}")
    except (httpx.RequestError, TimeoutError):
        return ProbeResult(None, "niedostępne", "Brak odpowiedzi lokalnego API")
    except (ValueError, RecursionError):
        pass
    return ProbeResult(None, "niepełne", "Nieprawidłowa odpowiedź JSON")


def _object(value: object) -> dict:
    return value if isinstance(value, dict) else {}


def _finite(value: object) -> float | int | None:
    if (
        type(value) in {int, float}
        and isinstance(value, (int, float))
        and abs(value) <= 1e12
        and math.isfinite(value)
    ):
        return value
    return None


def _axis(value: object) -> str:
    number = _finite(value)
    return str(number) if number is not None and -1 <= number <= 1 else "brak danych"


def _control_detail(control: dict, now: datetime) -> str:
    safety = _object(control.get("safety")) or control
    if not safety:
        return "Stan sterowania niedostępny."
    observed_at = _finite(safety.get("observed_at"))
    age = now.timestamp() - observed_at if observed_at is not None else None
    if safety.get("stale") is True or age is not None and age > _STALE_AFTER:
        return (
            "Stan sterowania przeterminowany. Aktualne osie i ACK są niepotwierdzone."
        )
    if age is None or age < -1:
        return "Brak wiarygodnego czasu stanu sterowania."
    output = _object(safety.get("output"))
    axes = f"Odczyt osi lx (liniowa)={_axis(output.get('lx'))}, az (obrotowa)={_axis(output.get('az'))}."
    ack = _object(safety.get("last_ack"))
    if ack.get("accepted") is True:
        axes += (
            " Ostatnie ACK potwierdza przyjęcie komendy. Brak dowodu fizycznego skutku."
        )
    elif ack.get("accepted") is False:
        axes += " Ostatnie ACK zgłasza odmowę komendy."
    return f"Wiek stanu sterowania {max(0.0, age):.1f} s. {axes}"


def _rider_evidence(read: ProbeResult, now: datetime) -> Evidence:
    if read.payload is None:
        return Evidence(_RIDER_PATH, read.status, read.detail, now)
    connection = _object(read.payload.get("connection"))
    errors = _object(read.payload.get("errors"))
    available = [
        key
        for key in _RIDER_SECTIONS
        if key not in errors and read.payload.get(key) is not None
    ]
    denied = [
        key
        for key in _RIDER_SECTIONS
        if errors.get(key)
        in ("forbidden", "unauthorized", "operator_access_denied", "permission_denied")
    ]
    failed = [
        key for key in _RIDER_SECTIONS if key not in available and key not in denied
    ]
    if not available:
        status = (
            "odmowa"
            if denied
            else "brak transportu"
            if connection.get("status") in ("offline", "unconfigured")
            else "niepełne"
        )
    else:
        status = (
            "częściowy odczyt"
            if failed or denied or connection.get("status") != "online"
            else "odczytano"
        )
    parts = [f"Odczytano: {', '.join(available) or 'brak'}."]
    if failed:
        parts.append(f"Bez danych: {', '.join(failed)}.")
    if denied:
        parts.append(f"Odmowa: {', '.join(denied)}.")
    if "control" in available:
        parts.append(_control_detail(_object(read.payload["control"]), now))
    return Evidence(_RIDER_PATH, status, " ".join(parts), now)


def _services_evidence(read: ProbeResult, now: datetime) -> Evidence:
    if read.payload is None:
        return Evidence(_SERVICES_PATH, read.status, read.detail, now)
    rows = read.payload.get("services")
    if not isinstance(rows, list) or not rows:
        return Evidence(_SERVICES_PATH, "niepełne", "Brak listy usług w sondzie", now)
    states: Counter[str] = Counter()
    affected = []
    for row in map(_object, rows):
        state = row.get("status")
        if state not in ("online", "degraded", "offline"):
            state = "unknown"
        states[state] += 1
        name = row.get("name")
        if (
            state != "online"
            and isinstance(name, str)
            and _SERVICE_NAME.fullmatch(name)
        ):
            affected.append(f"{name}={state}")
    detail = ", ".join(
        f"{status}={states[status]}"
        for status in ("online", "degraded", "offline", "unknown")
    )
    if affected:
        detail += f" · usługi do sprawdzenia: {', '.join(affected[:8])}"
    status = "odczytano" if states["online"] == len(rows) else "częściowy odczyt"
    return Evidence(_SERVICES_PATH, status, detail, now)


def _read_log(log_dir: Path, now: datetime) -> Evidence:
    source = "venom.log · końcówka"
    try:
        permission_guard.check_permission("FileReadSkill")
    except AutonomyViolation:
        return Evidence(source, "odmowa", "Polityka FileReadSkill", now)
    try:
        flags = (
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
        )
        path = log_dir / "venom.log"
        if path.is_symlink():
            return Evidence(source, "odmowa", "Log jest dowiązaniem", now)
        with os.fdopen(os.open(path, flags), "rb") as file:
            info = os.fstat(file.fileno())
            if not stat.S_ISREG(info.st_mode):
                return Evidence(
                    source, "odmowa", "Źródło logu nie jest zwykłym plikiem", now
                )
            file.seek(max(0, info.st_size - _LOG_LIMIT))
            data = file.read(_LOG_LIMIT)
    except PermissionError:
        return Evidence(source, "odmowa", "Brak dostępu do logu", now)
    except OSError:
        return Evidence(source, "niedostępne", "Odczyt logu nie powiódł się", now)
    levels = Counter(_LOG_LEVEL.findall(data))
    detail = f"{len(data)} B · WARNING={levels[b'WARNING']}, ERROR={levels[b'ERROR']}, CRITICAL={levels[b'CRITICAL']}"
    modified = datetime.fromtimestamp(info.st_mtime, UTC).isoformat(timespec="seconds")
    return Evidence(source, "odczytano", f"{detail} · mtime logu {modified}", now)


def _commands(request: DiagnosticRequest, origin: str | None) -> list[str]:
    base = origin or "http://127.0.0.1:8000"
    commands = [HOST_CHECK] if request.venom else []
    if request.venom:
        commands.append(f"curl --fail --max-time 5 '{base}{_SERVICES_PATH}'")
    if request.rider:
        commands.append(f"curl --fail --max-time 5 '{base}{_RIDER_PATH}'")
    return commands


async def run_operator_diagnostics(
    request: DiagnosticRequest, status_endpoint: str, *, log_dir: Path = LOG_DIR
) -> str:
    """Dispatch fixed GET probes and render only verified, allowlisted fields."""
    origin = _loopback_origin(status_endpoint)
    commands = _commands(request, origin)
    source = f"Źródło procedury · {RUNBOOK}"
    if request.guide:
        return "\n".join(
            [
                "**Instrukcja diagnostyki**",
                *[f"- `{cmd}`" for cmd in commands],
                source,
            ]
        )
    if origin is None:
        return f"**Odmowa diagnostyki** · Sondy wymagają skonfigurowanego lokalnego API.\nNastępny krok · `{HOST_CHECK}`\n{source}"
    evidence = []
    async with httpx.AsyncClient(
        base_url=origin, timeout=3.0, follow_redirects=False, trust_env=False
    ) as client:
        if request.venom:
            read = await _read_json(client, _SERVICES_PATH)
            now = datetime.now(UTC)
            evidence.append(_services_evidence(read, now))
            evidence.append(await asyncio.to_thread(_read_log, log_dir, now))
        if request.rider:
            read = await _read_json(client, _RIDER_PATH)
            evidence.append(_rider_evidence(read, datetime.now(UTC)))
    statuses = {item.status for item in evidence}
    if "odmowa" in statuses:
        next_step = "Sprawdź uprawnienia operatora do wskazanego odczytu."
    elif "brak transportu" in statuses:
        next_step = "Sprawdź wybór urządzenia i stan transportu w panelu Rider."
    elif evidence[0].status == "niedostępne":
        next_step = f"`{HOST_CHECK}`"
    else:
        next_step = f"`{commands[-1]}`"
    return "\n".join(
        [
            "**Diagnostyka Full · dowody**",
            *[item.render() for item in evidence],
            f"Następny krok · {next_step}",
            source,
        ]
    )
