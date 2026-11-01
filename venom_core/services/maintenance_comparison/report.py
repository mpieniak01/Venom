"""Role aggregates preserve blocked rows and unavailable measurements."""

import statistics
from pathlib import Path

ROLES = ["operator", "repair", "localization"]
DIAGNOSTICS = {"repair-08", "repair-10"}


def _ratio(rows: list[dict]) -> str:
    """Format passed/count and percentage, keeping an empty denominator explicit."""
    correct, count = sum(bool(row["passed"]) for row in rows), len(rows)
    return (
        f"{correct}/{count} ({100 * correct / count:.1f}%)"
        if count
        else "0/0 (brak danych)"
    )


def _median(rows: list[dict], key: str) -> str:
    """Format the median of measured values, preserving missing data as unavailable."""
    values = [row[key] for row in rows if row.get(key) is not None]
    return f"{statistics.median(values):.2f}" if values else "brak danych"


def _group(rows: list[dict], model: str, role: str) -> list[dict]:
    """Select attempts for exactly one model and role."""
    return [r for r in rows if r["model"] == model and r["role"] == role]


def _primary(rows: list[dict]) -> list[dict]:
    """Exclude the two diagnostic escalation cases from repair effectiveness."""
    return [r for r in rows if r["scenario"] not in DIAGNOSTICS]


def _scored(rows: list[dict]) -> list[dict]:
    """Exclude blocked attempts from scored outcomes without deleting their records."""
    return [r for r in rows if r["status"] != "blocked"]


def _role_row(model: dict, role: str, rows: list[dict]) -> list[str]:
    """Render role outcomes with separate baseline, repeats, blockers and diagnostics."""
    name = model["id"]
    if role not in model["roles"]:
        return [f"| {name} | {role} | N/A | N/A | N/A | N/A |"]
    group = _group(rows, name, role)
    base = [r for r in _primary(group) if r["repetition"] == 0]
    extra = [r for r in _primary(group) if r["repetition"] > 0]
    lines = [
        f"| {name} | {role} | {_ratio(_scored(base))} | {len(base) - len(_scored(base))} | {_ratio(_scored(extra))} | {_median(group, 'seconds')} |"
    ]
    if role == "repair":
        diagnostics = [
            r
            for r in _scored(group)
            if r["scenario"] in DIAGNOSTICS and r["repetition"] == 0
        ]
        lines.append(
            f"| {name} | diagnoza/eskalacja | {_ratio(diagnostics)} | — | — | — |"
        )
    return lines


def _measurements(models: list[dict], rows: list[dict]) -> list[str]:
    """Render per-role measurements and keep loading time distinct from task time."""
    lines = [
        "",
        "## Pomiary",
        "",
        "Rezerwacja alokatora CUDA i RSS w bajtach; rezerwacja nie jest pomiarem fizycznego VRAM. Tokeny wejściowe obejmują ponowne przekazanie kontekstu. Mediana zadania obejmuje przygotowanie kopii, pracę modelu i niezależną weryfikację; ładowanie modelu jest oddzielne.",
        "",
        "| Model | Rola | Ładowanie [s] | Kroki | CUDA rezerwacja | RSS | Tokeny wejścia / wyjścia | Zbędne powtórzenia |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for model in models:
        for role in model["roles"]:
            group = _scored(_group(rows, model["id"], role))
            lines.append(
                f"| {model['id']} | {role} | {_median(group, 'load_seconds')} | {_median(group, 'tool_call_count')} | {_median(group, 'peak_vram_bytes')} | {_median(group, 'peak_ram_bytes')} | {_median(group, 'input_tokens')} / {_median(group, 'output_tokens')} | {sum(r.get('redundant_repetitions', 0) for r in group)} |"
            )
    return lines


def _recommendation(models: list[dict], rows: list[dict], role: str) -> str:
    """Recommend only from complete, scored finalists with all three executions."""
    candidates = []
    for model in models:
        primary = _primary(_group(rows, model["id"], role))
        expected = 24 if role == "repair" else 30
        if len(primary) == expected and len(_scored(primary)) == expected:
            candidates.append(
                (sum(bool(r["passed"]) for r in primary) / expected, model["id"])
            )
    if not candidates:
        return f"- **{role}:** brak podstaw do pilotażu; brak kompletnego, ocenionego finalisty. Blokady i brak sukcesów pozostają wynikami tej konfiguracji."
    rate, model = max(candidates)
    recommendation = (
        "zastosować pilotażowo pod nadzorem operatora"
        if rate >= 0.8
        else "skierować do dostrajania lub ograniczyć do węższej roli"
    )
    return f"- **{role}: {model}** — {recommendation}; {100 * rate:.1f}% z trzech wykonań. Nie potwierdza to konfiguracji szkolenia."


def _blockers(rows: list[dict]) -> list[str]:
    """Group recorded blocking reasons and list the affected models."""
    lines = []
    for reason in sorted(
        {r["blocked_reason"] for r in rows if r["status"] == "blocked"}
    ):
        affected = sorted(
            {r["model"] for r in rows if r.get("blocked_reason") == reason}
        )
        lines.append("- " + ", ".join(affected) + ": `" + reason + "`.")
    return lines


def _example(rows: list[dict], role: str, success: bool) -> list[str]:
    """Render one observed success or failure with its real terminal result."""
    example = next(
        (
            r
            for r in _scored(rows)
            if r["role"] == role and bool(r["passed"]) == success
        ),
        None,
    )
    if example is None:
        return []
    outcome = "poprawny" if success else "błędny"
    lines = [
        f"- Przykład {outcome}, {role}: `{example['model']}/{example['scenario']}`, status `{example['status']}`, weryfikacja `{example['verification']['reason']}`; artefakt `{example['id']}.json`."
    ]
    action = next(
        (c for c in example.get("calls", []) if c["name"] == "Terminal"), None
    )
    if action:
        command = (
            action["arguments"]
            .get("command", "")[:180]
            .replace("`", "'")
            .replace("\n", " ")
        )
        lines.append(
            f"  Działanie: `{command}`; rzeczywisty exit_code={action['result'].get('exit_code')}."
        )
    return lines


def render(
    models: list[dict],
    rows: list[dict],
    output: Path,
    roles: list[str] | None = None,
    *,
    phase: str = "comparison",
) -> str:
    """Write a role-separated Markdown report with denominators and measurement limitations."""
    selected_roles = roles if roles is not None else ROLES
    lines = [
        "# Porównanie lokalnych modeli utrzymania Venoma",
        "",
        "Profil RTX 3060 12 GB; wyniki odnoszą się do zapisanej konfiguracji. Osiem napraw to kontrolowane syntetyczne usterki w kopii repozytorium; lokalizacja korzysta z kodu Venoma. To nie są wyniki SWE-bench ani dowód skuteczności dla dowolnej usterki produkcyjnej.",
        "",
        "| Model | Rola | Baseline poprawne / ocenione | Blokady | Powtórzenia poprawne / ocenione | Mediana zadania [s] |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for model in models:
        for role in ROLES:
            if role not in selected_roles and role in model["roles"]:
                lines.append(f"| {model['id']} | {role} | nie wybrano | — | — | — |")
            else:
                lines.extend(_role_row(model, role, rows))
    lines.extend(_measurements(models, rows))
    planned = sum(len(set(m["roles"]) & set(selected_roles)) * 10 for m in models)
    base_count = sum(r["repetition"] == 0 for r in rows)
    maximum = planned
    if phase == "comparison":
        maximum += sum(
            20 * min(2, sum(role in model["roles"] for model in models))
            for role in selected_roles
        )
    lines += [
        "",
        "## Pokrycie planu i rekomendacje",
        "",
        f"Baseline: {base_count}/{planned} pozycji; wszystkie wykonania: {len(rows)} (limit {maximum}).",
    ]
    lines.extend(_recommendation(models, rows, role) for role in selected_roles)
    if phase == "baseline":
        lines.append(
            "Tryb baseline: po jednym wykonaniu przypadku; powtórzenia finalistów nie są uruchamiane. Wyniki pozostają wstępne."
        )
    if phase == "comparison":
        lines += [
            "",
            "Powtórzenia otrzymuje do dwóch finalistów roli z kompletnym baseline bez blokad i co najmniej jednym sukcesem. Pozostałe wyniki są wstępne. Seed=17 pozostaje identyczny w powtórzeniach; to nie jest pomiar wariancji między seedami.",
        ]
    lines += ["", "## Blokady i przykłady", ""]
    lines.extend(_blockers(rows))
    for role in ROLES:
        for success in [True, False]:
            lines.extend(_example(rows, role, success))
    lines += [
        "",
        "## Pomiary i dane szkoleniowe",
        "",
        "Czas ładowania jest oddzielny od zadania. VRAM: szczyt rezerwacji alokatora Torch, bez pozostałych procesów i narzutu sterownika. RAM: RSS procesu modelu próbkowany co 50 ms, bez pamięci kontenera i pozostałych procesów. Brak danych nie oznacza zera.",
        "Wszystkie przypadki są held-out test. Eksport zawiera rzeczywiste wiadomości, wyniki narzędzi, rewizje i weryfikację, z training_allowed=false. Trening wymaga odrębnych problemów/commitów train i validation oraz kwalifikacji sprzętu, backendu i licencji.",
        "",
    ]
    text = "\n".join(lines)
    (output / "REPORT.md").write_text(text)
    return text
