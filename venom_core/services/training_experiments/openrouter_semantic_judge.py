"""Qualified OpenRouter field reviewer; no local model or GPU access.

Audit v7 checks candidate evidence before accepting a remote decision. Earlier audit results keep their own identity.
All verification/replay functions are offline. Real requests occur only in
review_bundle, after qualification, configuration and budget checks.
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from collections import Counter
from collections.abc import Callable
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Annotated, Literal, cast
from uuid import uuid4

import httpx
from pydantic import Field

from venom_core.config import SETTINGS
from venom_core.services import openrouter_runtime as runtime
from venom_core.services.remote_training.lifecycle import atomic_json, file_lock
from venom_core.services.remote_training.paths import operator_path

from . import local_semantic_judge as local
from . import semantic_judge_v4 as controls
from . import semantic_judge_v5 as fields
from .profiles import digest, read_json, stable_hash

JUDGE = "semantic-openrouter-luna-field-v7"
JUDGES = frozenset({JUDGE})
PROMPT = (
    fields.PROMPT
    + """

Doprecyzowanie kontraktu v3: odróżniaj potrzebę, zamówienie i stan wykonania.
Zdanie, że dostawa nie wymaga chłodzenia, nie dowodzi, że chłodzenia nie zamówiono.
Jeżeli kryterium wymaga zakomunikowania braku danych w źródle, a kandydat zamiast
tego podaje definitywną wartość, relation=omitted (nie zakomunikował braku),
a tę konkretną nieudowodnioną wartość zapisz w additional_claims jako unsupported.
Nie stwierdzaj, że nieznana wartość jest faktycznie fałszywa. Gdy źródło jawnie
mówi, że nie zamówiono chłodzenia, odpowiedź, że je zamówiono, jest contradicted.
Parafraza osoby jest dopuszczalna, gdy zachowuje rolę podaną jawnie w materiale.
Sama lokalizacja odbioru nie dowodzi, że właściciel miejsca osobiście wydaje rzeczy.
"""
    + (
        "\n\nReguły rozstrzygania dla recenzenta pól\n\n1. Przy ocenie dodatkowych "
        "twierdzeń najpierw sprawdź, czy fragment należy znaczeniowo do kryterium już"
        " ocenionego. Równoważny opis położenia zawierający zwykły czasownik "
        "oznaczający obecność obiektu zachowuje informację o miejscu. Sformułowania "
        "„wpis nie wskazuje, kto…” i „nie wpisano nazwiska” przekazują ten sam brak "
        "danych o osobie w danym wpisie. Oceniaj każdą z tych informacji w jej "
        "właściwym kryterium. W additional_claims zachowaj nowe, niepoparte "
        "twierdzenia, takie jak przypisanie osobie czynności, której materiał jej nie"
        " przypisuje.\n\n2. Gdy użytkownik żąda osobno wyniku i zachowanej zasady, "
        "znajdź osobny dowód treściowy dla obu kryteriów w odpowiedzi. Lista osób w "
        "prawidłowej kolejności nadal pozostawia omitted dla osobno żądanej zasady o "
        "tym, ile razy każda osoba zabiera głos. Jednokrotne wymienienie osoby "
        "opisuje listę. Jawne „każdy raz” przy jasnym kontekście wypowiedzi "
        "wystarcza, by uznać zasadę za supported.\n\n3. Dla polish_ok oceń język "
        "rozpoznawalnej wypowiedzi niosącej odpowiedź. Jeśli istnieje zrozumiałe "
        "polskie zdanie, a reszta jest bełkotliwą doklejką bez rozpoznawalnego zdania"
        " w innym języku, wybierz polish_ok=true oraz natural_ok=false. Sam bełkot "
        "bez odpowiedzi ani użytecznej samodzielnej wartości ma polish_ok=false i "
        "natural_ok=false. Naturalna odpowiedź w pełnych zdaniach obcojęzycznych ma "
        "polish_ok=false, nawet gdy fakty są poprawne. Oczekiwany samodzielny kod, "
        "liczba lub nazwa mogą mieć polish_ok=true i natural_ok=true. Sprawdź oba "
        "pola osobno przed zwróceniem JSON.\n\n4. Zmniejsz objętość odpowiedzi JSON. W "
        "required i observed zapisz krótkie frazy zachowujące rozstrzygające fakty i "
        "pełny sens pola. Każde additional_claims.text przytocz jako krótki, dosłowny"
        " i ciągły fragment kandydata. W reason napisz jedno krótkie zdanie. Zachowaj"
        " wszystkie pola schematu.\n\n5. Rozwiąż odsyłacze miejsca typu „tam” do "
        "wskazanego przed chwilą położenia lub obiektu. Gdy opis lokalizacji i zdanie"
        " z odsyłaczem wspólnie podają wymagane miejsce zdarzenia, pole miejsca jest "
        "supported. Ustal relation przed oceną additional_claims i zachowaj supported"
        " dla pola, które zostało podane prawidłowo. Osobny niepoparty szczegół "
        "należy do additional_claims i sam nie zmienia podanego już pola na omitted."
    )
    + (
        "\n\nRozstrzyganie ról przy przekazaniu i odbiorze\n\n1. Oceniając osobę, użyj "
        "obowiązujących ustaleń użytkownika i źródeł. „Odbierzesz u tej osoby” "
        "wystarcza dla pola osoby obsługującej odbiór, jeśli materiał jawnie "
        "przypisał jej tę rolę, późniejsza korekta jej nie zmieniła, a kryterium "
        "wymaga jej identyfikacji w kontekście odbioru. Nazwa punktu, adres, szyld "
        "ani samo powiązanie osoby z miejscem nie potwierdzają roli. Gdy materiał "
        "podaje tylko lokalizację, a kandydat powtarza tylko lokalizację, oznacz pole"
        " osoby jako omitted. Jawne przypisanie tej roli bez dowodu w materiale jest "
        "niepopartym twierdzeniem.\n\n2. „Osoba X wydaje przedmiot” i „przedmiot "
        "odbierzesz od osoby X” mogą opisywać to samo ustalone przekazanie. Gdy "
        "przedmiot, termin i osoba są zgodne, sformułowanie od strony odbioru "
        "potwierdza rolę osoby X. Zwykłe zwrócenie się do adresata w tej parafrazie "
        "nie stanowi osobnej gwarancji, ustalenia tożsamości odbiorcy ani "
        "potwierdzenia wykonanego odbioru. Zmienioną rolę, innego odbiorcę "
        "określonego niezależnym twierdzeniem oraz inne fakty oceniaj zgodnie ze "
        "źródłem.\n\n3. Jeśli nazwa miejsca i imię osoby są takie same, rozróżnij "
        "konstrukcje odpowiedzi. „W punkcie o nazwie X” identyfikuje miejsce. Zwykłe "
        "„odbierzesz u X”, z odmienionym imieniem jawnie ustalonej osoby wydającej, "
        "identyfikuje tę osobę w kontekście odbioru. Wpisz takie wskazanie w checks. "
        "Przed zwróceniem additional_claims sprawdź, czy każde text jest dosłownym "
        "fragmentem samej odpowiedzi kandydata.\n\n„Stoi” to część parafrazy opisu "
        "położenia znanego obiektu, także gdy źródło pomija ten czasownik.\n\n4. "
        "Pominięcie roli i oparcie twierdzenia o miejscu oceniaj osobno. Gdy "
        "odpowiedź podaje tylko nazwę punktu ustaloną w materiale, w checks ustaw "
        "omitted dla osoby. Podaną nazwę punktu potraktuj jako dodatkowe twierdzenie "
        "o lokalizacji z grounding=supported, również wtedy, gdy pytanie dotyczy "
        "tylko osoby. Opisuje ona miejsce, nie osobę. Brak odpowiedzi na pytanie o "
        "osobę nie zmienia oparcia nazwy punktu w materiale. Dla nazwy miejsca "
        "podmienionej względem aktualnego ustalenia oznacz dodatkowe twierdzenie jako"
        " unsupported. Użyj krótkiego dosłownego fragmentu odpowiedzi."
    )
    + (
        "\n\nRozstrzyganie parafrazy, braku danych i dowodu z odpowiedzi\n\n1. Oceniaj "
        "znaczenie połączenia czynności z miejscem. „Podejdź po przedmiot pod schody”"
        " i „odbierz przedmiot spod schodów” mogą wskazywać to samo miejsce odbioru. "
        "Sprawdź przedmiot, faktyczne położenie i właściwy termin. „Obok schodów” i "
        "„pod schodami” to różne położenia.\n2. Gdy wymagany fakt mówi, że status jest"
        " nieznany, jawne „nie ma ustalonego statusu” spełnia ten warunek. Zakaz "
        "wnioskowania z kodu jest ograniczeniem oceny i treści. Kandydat nie musi go "
        "powtarzać, chyba że użytkownik osobno prosi o podanie tej zasady.\n3. Dla "
        "każdego pola oddziel required z polecenia lub źródeł od observed z samej "
        "odpowiedzi. W observed przytocz krótki dosłowny fragment odpowiedzi "
        "kandydata. Jeśli kandydat nie podał treści danego pola, wpisz „brak w "
        "odpowiedzi” oraz relation=omitted. Imię lub wartość widoczne tylko w "
        "pytaniu, karcie albo w required nigdy nie potwierdzają pola odpowiedzi. "
        "Przed zwróceniem wyniku sprawdź, że każdy cytat observed pochodzi z "
        "odpowiedzi."
    )
    + (
        "\n\nKontrola cytatu w observed\n\nDla supported i contradicted wpisz w observed "
        "jeden ciągły dosłowny fragment odpowiedzi, bez komentarza, etykiety z "
        "polecenia, nawiasów ani wielokropka. Dla omitted bez fragmentu danego pola "
        "wpisz dokładnie: brak w odpowiedzi. Jeśli odpowiedź zawiera część wymaganego"
        " pola, możesz przytoczyć tę część przy omitted. Wartość podaną tylko w "
        "źródle zapisz w required.\n\n„Status nieznany” oznacza brak podstaw do "
        "ustalenia wartości. Jeśli kandydat dopisuje pewny status bez źródła, pole "
        "jawnego braku statusu ma omitted, a dosłowny fragment z dopisanym statusem "
        "dodaj do additional_claims z grounding=unsupported. Dopisanie wartości nie "
        "jest zaprzeczeniem konkretnej wartości źródłowej. Użyj contradicted, gdy "
        "odpowiedź zaprzecza wartości, którą materiał podaje wprost."
    )
)
MODEL = "openai/gpt-6-luna"
PROVIDER = "Azure"
ROUTE = "azure"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
OUTPUT = 900
_TRANSACTION_FILE = ".pending-transaction.json"
_STAGED_RECEIPT_FILE = ".pending-receipt.json"
_STAGED_LEDGER_FILE = ".pending-ledger.json"

_JSON_SUFFIX = ".json"
_LEDGER_FILE = "ledger.json"
INPUT_PRICE = Decimal("0.10")
OUTPUT_PRICE = Decimal("0.50")
PHASE1 = {"legacy": 60, "development": 48, "extra": 32, "contrasts": 16}
Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
ERROR = "experiment_remote_judge_invalid"
DECISION_FIELDS = controls.DECISION_FIELDS


class QualificationRemote(local._Strict):
    schema_version: Literal[1]
    judge: Literal["semantic-openrouter-luna-field-v7"]
    audit_root: str = Field(min_length=1)
    model: Literal["openai/gpt-6-luna"]
    provider: Literal["Azure"]
    endpoint: Literal["https://openrouter.ai/api/v1/chat/completions"]
    protocol_sha256: Digest
    result_sha256: Digest
    controls_manifest_sha256: Digest
    prompt_sha256: Digest
    request_contract_sha256: Digest
    implementation_sha256: Digest


def _require(value: bool) -> None:
    if not value:
        raise ValueError(ERROR)


def _money(value: object) -> Decimal:
    if not isinstance(value, str):
        raise ValueError("experiment_remote_judge_cost_invalid")
    try:
        result = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError("experiment_remote_judge_cost_invalid") from exc
    if not result.is_finite() or result < 0:
        raise ValueError("experiment_remote_judge_cost_invalid")
    return result


def _time(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError(ERROR)
    result = datetime.fromisoformat(value)
    _require(result.tzinfo is not None)
    return result


def _root(path: str) -> Path:
    result = operator_path(Path(path))
    _require(result.is_absolute())
    return result


def _bound(root: Path, name: str, sha: str) -> dict:
    # All callers supply fixed names, never paths from result/HTTP data.
    path = root / name
    _require(digest(path) == sha)
    value = read_json(path)
    _require(isinstance(value, dict) and digest(path) == sha)
    return value


def _contract() -> dict:
    return {
        "judge": JUDGE,
        "model": MODEL,
        "provider": PROVIDER,
        "endpoint": ENDPOINT,
        "route": ROUTE,
        "max_completion_tokens": OUTPUT,
        "reasoning": {"effort": "low", "exclude": True},
        "input_per_m_usd": str(INPUT_PRICE),
        "output_per_m_usd": str(OUTPUT_PRICE),
        "zdr_required": False,
        "automatic_retry": False,
        "response_format": "strict_field_schema",
        "prompt_sha256": hashlib.sha256(PROMPT.encode()).hexdigest(),
    }


def implementation_identity() -> str:
    directory = Path(__file__).parent
    paths = [
        directory / name
        for name in (
            "openrouter_semantic_judge.py",
            "semantic_judge_v5.py",
            "local_semantic_judge.py",
            "semantic_judge_v4.py",
            "semantic_judge_controls.py",
            "semantic_openrouter_audit.py",
            "profiles.py",
            "grounded_claims.py",
        )
    ]
    paths.append(directory.parents[2] / "scripts/academy/omni_pl_chat_dialogue.py")
    return stable_hash({path.name: digest(path) for path in paths})


def reported_cost(body: dict) -> str | None:
    # Keep calibration -> dispatch imports independent of ExperimentService.
    from .dialogue_judge import reported_cost as cost

    return cost(body)


def claim_rubric(spec: dict) -> dict:
    return local.claim_rubric(spec)


def request_payload(spec: dict, case: dict, answer: dict) -> dict:
    _require(
        answer.get("finish") == "stop"
        and answer.get("error") is None
        and isinstance(answer.get("text"), str)
    )
    material = local._material(spec, case, answer)
    _require(len(json.dumps(material, ensure_ascii=False).encode()) <= 16_000)
    ids = [item["id"] for item in material["criteria"]]
    _require(bool(ids) and len(ids) == len(set(ids)))
    body = fields.request(MODEL, material, ids)
    body["messages"][0]["content"] = PROMPT
    # Persisted packet dictionaries may be key-sorted by atomic_json.
    body["messages"][1]["content"] = json.dumps(
        json.loads(body["messages"][1]["content"]),
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )
    return {
        "model": MODEL,
        "messages": body["messages"],
        "max_completion_tokens": OUTPUT,
        "reasoning": {"effort": "low", "exclude": True},
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "factual_field_review",
                "strict": True,
                "schema": body["format"],
            },
        },
        "provider": {
            "only": [ROUTE],
            "allow_fallbacks": False,
            "require_parameters": True,
            "max_price": {
                "prompt": float(INPUT_PRICE),
                "completion": float(OUTPUT_PRICE),
                "request": 0,
            },
        },
    }


def _control_request(case: dict, answer: dict) -> dict:
    # Audit cases have no runtime wrapper; use the same material/prompt/schema.
    normalized = {
        **case,
        "criteria": [{**c, "kind": "content"} for c in case["criteria"]],
    }
    normalized["record_id"] = case["id"]
    return request_payload(
        {"evidence": case.get("evidence", [])},
        normalized,
        {"text": answer["text"], "finish": "stop", "error": None},
    )


def reserve(body: dict) -> Decimal:
    tokens = sum(len(item["content"].encode()) + 128 for item in body["messages"])
    tokens += len(json.dumps(body["response_format"]).encode()) + 1024
    return (INPUT_PRICE * tokens + OUTPUT_PRICE * OUTPUT) / Decimal(1_000_000)


def decode(response: dict, body: dict, candidate: str) -> local._Decision:
    _require(response.get("model") == MODEL and response.get("provider") == PROVIDER)
    _require(isinstance(response.get("id"), str) and bool(response["id"].strip()))
    choices = response.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise ValueError(ERROR)
    choice = choices[0]
    _require(isinstance(choice, dict))
    _require(choice.get("finish_reason") == "stop")
    message = choice.get("message")
    _require(isinstance(message, dict))
    content = message.get("content")
    _require(isinstance(content, str))
    ids = list(
        body["response_format"]["json_schema"]["schema"]["properties"]["checks"][
            "properties"
        ]
    )
    result = fields.decode(
        {
            "model": MODEL,
            "done": True,
            "done_reason": "stop",
            "message": {"content": content},
        },
        ids,
        MODEL,
        candidate=candidate,
        require_observed_quotes=True,
    )
    _require(result is not None)
    assert result is not None
    return result


def _jobs(root: Path, manifest: dict, split: str) -> tuple[dict, dict]:
    if split == "contrasts":
        from .semantic_judge_controls import jobs_for_contrasts

        return jobs_for_contrasts(root, manifest)
    return controls.jobs_for(root, manifest, split)


def _audit_order(root: Path, manifest: dict, *, phase1: bool = False) -> list[dict]:
    entry = "phase1-order.json"
    order = _bound(root / "controls", entry, manifest["files"][entry])["jobs"]
    expected = {
        (split, ident) for split in PHASE1 for ident in _jobs(root, manifest, split)[0]
    }
    _require(len(order) == 156 and len(expected) == 156)
    _require(Counter(row["split"] for row in order) == PHASE1)
    _require(
        all(type(row.get("repeat")) is int and row["repeat"] == 1 for row in order)
    )
    _require({(row["split"], row["answer_id"]) for row in order} == expected)
    if phase1:
        return order
    held, _ = _jobs(root, manifest, "holdout")
    _require(len(held) == 24)
    return order + [
        {"split": "holdout", "answer_id": ident, "repeat": repeat}
        for repeat in (1, 2, 3)
        for ident in held
    ]


def _audit_metrics(
    root: Path, manifest: dict, rows: list[dict], *, phase1: bool = False
) -> dict:
    splits = (*PHASE1,) if phase1 else (*PHASE1, "holdout")
    decisions: dict[str, dict] = {split: {} for split in splits}
    for row in rows:
        decisions[row["split"]].setdefault(row["answer_id"], []).append(
            local._Decision.model_validate(row["decision"])
        )
    _, gold = _jobs(root, manifest, "legacy")
    actual = {key: arr[0] for key, arr in decisions["legacy"].items()}
    positives = set(gold["accepted"])
    accepted = {key for key, decision in actual.items() if local._supported(decision)}
    styles = local._style_checks(gold, positives, set(gold["rejected"]))
    _require(len(styles) == 24 and len(gold["expected_semantics"]) == 6)
    metrics = {
        "legacy_positive": len(accepted & positives),
        "legacy_negative": len(set(gold["rejected"]) - accepted),
        "legacy_style": sum(
            (actual[key].polish_ok, actual[key].natural_ok) == expected
            for key, expected in styles.items()
        ),
        "legacy_semantics": sum(
            local._semantic_check(actual[key], expected)
            for key, expected in gold["expected_semantics"].items()
        ),
    }
    for split in splits[1:]:
        _, gold = _jobs(root, manifest, split)
        metrics[split + "_full"] = sum(
            {key: getattr(decision, key) for key in DECISION_FIELDS}
            == gold["answers"][ident]["decision"]
            for ident, arr in decisions[split].items()
            for decision in arr
        )
    if not phase1:
        metrics["holdout_stable_groups"] = sum(
            len(arr) == 3
            and all(
                {k: getattr(d, k) for k in DECISION_FIELDS}
                == {k: getattr(arr[0], k) for k in DECISION_FIELDS}
                for d in arr
            )
            for arr in decisions["holdout"].values()
        )
    return metrics


def _verify_call(
    row: dict, body: dict, candidate: str, protocol_sha: str
) -> local._Decision:
    _require(
        row.get("status") == "completed" and row.get("protocol_sha256") == protocol_sha
    )
    request_sha = stable_hash(body)
    _require(
        row.get("request_sha256") == request_sha
        and stable_hash(row.get("request")) == request_sha
    )
    response = row.get("response")
    _require(
        isinstance(response, dict)
        and row.get("response_sha256") == stable_hash(response)
    )
    assert isinstance(response, dict)
    result = decode(response, body, candidate)
    _require(row.get("decision") == result.model_dump())
    cost = reported_cost(response)
    _require(cost is not None and row.get("cost_usd") == cost)
    _require(_money(cost) <= _money(row["reserved_usd"]))
    _require(_money(row["reserved_usd"]) == reserve(body))
    _require(_time(row["started_at"]) <= _time(row["finished_at"]))
    return result


def verify_audit(pin: QualificationRemote) -> None:
    from .semantic_openrouter_audit import _RATE_LIMIT_POLICY, _REQUEST_TIMEOUT_SECONDS

    root = _root(pin.audit_root)
    protocol = _bound(root, "protocol.json", pin.protocol_sha256)
    _require(
        protocol.get("rate_limit") == _RATE_LIMIT_POLICY
        and protocol.get("automatic_retry") == "http_429_only"
        and protocol.get("request_timeout_seconds") == _REQUEST_TIMEOUT_SECONDS
    )
    result = _bound(root, "result.json", pin.result_sha256)
    manifest = _bound(
        root / "controls", "frozen-manifest.json", pin.controls_manifest_sha256
    )
    thresholds = {
        "legacy_positive": 24,
        "legacy_negative": 36,
        "legacy_style": 24,
        "legacy_semantics": 6,
        "development_full": 48,
        "extra_full": 32,
        "contrasts_full": 16,
        "holdout_full": 72,
        "holdout_stable_groups": 24,
    }
    _require(
        manifest.get("control_version") == "luna-controls-v3"
        and manifest.get("status") == "frozen_before_any_inference"
        and manifest.get("thresholds") == thresholds
    )
    _require(
        protocol.get("judge") == JUDGE
        and protocol.get("request_contract") == _contract()
    )
    _require(protocol.get("controls_manifest_sha256") == pin.controls_manifest_sha256)
    _require(
        pin.prompt_sha256 == _contract()["prompt_sha256"]
        and pin.request_contract_sha256 == stable_hash(_contract())
        and pin.implementation_sha256 == implementation_identity()
    )
    _require(protocol.get("implementation_sha256") == pin.implementation_sha256)
    _require(
        result.get("status") == "passed"
        and result.get("protocol_sha256") == pin.protocol_sha256
    )
    hashes = result["receipt_hashes"]
    _require(set(hashes) == {f"{i:03d}.json" for i in range(1, 229)})
    phase1_hashes = {f"{i:03d}.json": hashes[f"{i:03d}.json"] for i in range(1, 157)}
    rows, phase1_metrics, (phase1_known, phase1_reserved) = _replay_phase1(
        root, protocol, pin.protocol_sha256, manifest, phase1_hashes
    )
    _require(
        phase1_metrics
        == {k: v for k, v in thresholds.items() if not k.startswith("holdout")}
    )
    phase1 = _bound(root, "phase1-result.json", result["phase1_result_sha256"])
    _require(
        phase1.get("status") == "passed"
        and type(phase1.get("rows")) is int
        and phase1["rows"] == 156
    )
    _require(phase1.get("metrics") == phase1_metrics)
    _require(phase1.get("receipt_hashes") == phase1_hashes)
    phase1_finished = _time(phase1["finished_at"])
    _require(_time(rows[-1]["finished_at"]) <= phase1_finished)
    initial = _money(protocol["initial_accounted_usd"])
    initial_unknown = _money(protocol["initial_unknown_reserved_usd"])
    budget = _money(protocol["budget_usd"])
    _require(initial_unknown <= initial and budget > 0)
    limit = _verify_holdout_capacity(
        protocol, rows, initial + phase1_known + phase1_reserved, phase1_finished
    )
    # No held-out content, including its receipts, is read until G1 replay passed.
    held = manifest["holdout"]
    _require(set(held["files"]) == {"panel.json", "gold.json"})
    for name in ("panel.json", "gold.json"):
        _require(digest(root / "controls" / "holdout" / name) == held["files"][name])
    combined = {
        **manifest,
        "files": {
            **manifest["files"],
            **{"holdout/" + n: h for n, h in held["files"].items()},
        },
    }
    rows = _audit_rows(
        root,
        pin.protocol_sha256,
        combined,
        hashes,
        _audit_order(root, combined)[156:],
        rows,
        phase1_finished,
    )
    holdout_cap = _money(protocol["holdout_max_request_usd"])
    _require(all(_money(row["reserved_usd"]) <= holdout_cap for row in rows[156:]))
    metrics = _audit_metrics(root, combined, rows)
    _require(metrics == thresholds and result.get("metrics") == metrics)
    known, reserved = _audit_costs(rows, protocol)
    _require(_money(result["actual_known_cost_usd"]) == known)
    _require(_money(result["unknown_reserved_usd"]) == reserved)
    _require(_money(result["carried_unknown_reserved_usd"]) == initial_unknown)
    _require(_money(result["accounted_usd"]) == initial + known + reserved <= budget)
    elapsed = (
        _time(rows[-1]["finished_at"]) - _first_attempt_started(rows[0])
    ).total_seconds()
    _require(elapsed <= limit)


def _replay_phase1(
    root: Path, protocol: dict, protocol_sha: str, manifest: dict, hashes: dict
) -> tuple[list[dict], dict, tuple[Decimal, Decimal]]:
    review = _bound(root, "data-review.json", protocol["data_review_sha256"])
    _require(
        review.get("status") == "passed"
        and review.get("controls_manifest_sha256")
        == protocol["controls_manifest_sha256"]
        and isinstance(review.get("reviewer"), str)
        and bool(review["reviewer"].strip())
    )
    _require(set(hashes) == {f"{i:03d}.json" for i in range(1, 157)})
    rows = _audit_rows(
        root,
        protocol_sha,
        manifest,
        hashes,
        _audit_order(root, manifest, phase1=True),
        [],
        _time(review["created_at"]),
    )
    costs = _audit_costs(rows, protocol)
    return rows, _audit_metrics(root, manifest, rows, phase1=True), costs


def _verify_holdout_capacity(
    protocol: dict, rows: list[dict], accounted: Decimal, phase1_finished: datetime
) -> float:
    from .semantic_openrouter_audit import (
        _HOLDOUT_CALLS,
        _capacity,
        _holdout_required_seconds,
    )

    budget = _money(protocol["budget_usd"])
    per_request = _money(protocol["max_request_usd"])
    cap = _money(protocol["holdout_max_request_usd"])
    quotes = [_money(row["reserved_usd"]) for row in rows]
    _require(
        0 < cap <= per_request <= budget
        and max(quotes) <= per_request
        and max(quotes) == _money(protocol["phase1_max_request_usd"])
        and sum(quotes, Decimal(0)) == _money(protocol["phase1_reservation_usd"])
    )
    _require(_money(_capacity(protocol, budget)["planned_budget_usd"]) <= budget)
    policy = protocol["rate_limit"]
    max_retries = policy["max_retries_per_audit"]
    retries_left = max_retries - sum(len(_rate_limit_attempts(row)) for row in rows)
    _require(accounted + (_HOLDOUT_CALLS + retries_left) * cap <= budget)
    limit = protocol["max_seconds"]
    cleanup = protocol["holdout_cleanup_seconds"]
    _require(
        type(limit) in (int, float)
        and math.isfinite(limit)
        and 0 < limit <= 86400
        and type(cleanup) is int
        and cleanup >= 0
    )
    phase1_spacing = (len(rows) - 1) * policy["interval_seconds"]
    _require(phase1_spacing + _holdout_required_seconds(protocol, max_retries) < limit)
    elapsed = (phase1_finished - _first_attempt_started(rows[0])).total_seconds()
    _require(elapsed + _holdout_required_seconds(protocol, retries_left) <= limit)
    return limit


def _first_attempt_started(row: dict) -> datetime:
    attempts = _rate_limit_attempts(row)
    return _time((attempts[0] if attempts else row)["started_at"])


def _rate_limit_attempts(row: dict) -> list[dict]:
    attempts = row.get("rate_limit_attempts", [])
    if not isinstance(attempts, list) or not all(
        isinstance(attempt, dict) for attempt in attempts
    ):
        raise ValueError(ERROR)
    return attempts


def _audit_costs(rows: list[dict], protocol: dict) -> tuple[Decimal, Decimal]:
    known = sum((_money(row["cost_usd"]) for row in rows), Decimal(0))
    unknown = Decimal(0)
    retry_count = 0
    call_ids = {row["call_id"] for row in rows}
    policy = protocol["rate_limit"]
    for row in rows:
        attempts = _rate_limit_attempts(row)
        _require(len(attempts) <= len(policy["backoff_seconds"]))
        retry_count += len(attempts)
        _require(retry_count <= policy["max_retries_per_audit"])
        for attempt in attempts:
            _require(
                attempt.get("status") == "failed"
                and attempt.get("http_status") == 429
                and all(
                    attempt.get(k) == row.get(k)
                    for k in (
                        "index",
                        "case_id",
                        "answer_id",
                        "split",
                        "repeat",
                        "request_sha256",
                        "reserved_usd",
                        "protocol_sha256",
                    )
                )
                and stable_hash(attempt.get("request")) == row["request_sha256"]
            )
            _require(
                isinstance(attempt.get("call_id"), str)
                and bool(attempt["call_id"].strip())
                and attempt["call_id"] not in call_ids
                and "response" in attempt
                and stable_hash(attempt["response"]) == attempt["response_sha256"]
            )
            call_ids.add(attempt["call_id"])
            reserved = _money(attempt["reserved_usd"])
            response = attempt["response"]
            reported = reported_cost(response) if isinstance(response, dict) else None
            _require(reported == attempt.get("cost_usd"))
            if reported is None:
                unknown += reserved
            else:
                cost = _money(reported)
                _require(cost <= reserved)
                known += cost
    return known, unknown


def _retry_wait_seconds(attempt: dict, index: int, finished: datetime) -> float:
    from .semantic_openrouter_audit import _RATE_LIMIT_POLICY, _retry_delay

    policy: dict = _RATE_LIMIT_POLICY
    backoff = policy["backoff_seconds"]
    _require(index < len(backoff))
    header = attempt.get("retry_after")
    if not isinstance(header, str) or len(header) > 128:
        raise ValueError(ERROR)
    delay = _retry_delay(header, backoff[index], finished)
    _require(delay <= policy["max_retry_after_seconds"])
    return max(policy["interval_seconds"], delay)


def _audit_rows(
    root: Path,
    protocol_sha: str,
    manifest: dict,
    hashes: dict,
    order: list[dict],
    prior: list[dict],
    phase_opened_at: datetime,
) -> list[dict]:
    from .semantic_openrouter_audit import _RATE_LIMIT_POLICY

    interval = cast(int, _RATE_LIMIT_POLICY["interval_seconds"])
    previous_end = _time(prior[-1]["finished_at"]) if prior else phase_opened_at
    rows = list(prior)
    calls = {row["call_id"] for row in prior}
    generations = {row["response"]["id"] for row in prior}
    for index, expected in enumerate(order, len(prior) + 1):
        row = _bound(
            root / "receipts", f"{index:03d}.json", hashes[f"{index:03d}.json"]
        )
        _require(type(row.get("index")) is int and row["index"] == index)
        _require(type(row.get("repeat")) is int)
        _require(all(row.get(k) == v for k, v in expected.items()))
        _require(
            isinstance(row.get("call_id"), str)
            and bool(row["call_id"].strip())
            and row["call_id"] not in calls
        )
        wait_seconds = max(
            interval if rows else 0.0,
            (phase_opened_at - previous_end).total_seconds(),
        )
        for retry_index, attempt in enumerate(_rate_limit_attempts(row)):
            started = _time(attempt["started_at"])
            finished = _time(attempt["finished_at"])
            _require(
                (started - previous_end).total_seconds() >= wait_seconds
                and started <= finished
            )
            wait_seconds = _retry_wait_seconds(attempt, retry_index, finished)
            previous_end = finished
        _require(
            (_time(row["started_at"]) - previous_end).total_seconds() >= wait_seconds
        )
        previous_end = _time(row["finished_at"])
        case, answer = _jobs(root, manifest, row["split"])[0][row["answer_id"]]
        decision = _verify_call(
            row, _control_request(case, answer), answer["text"], protocol_sha
        )
        _require(
            decision.unsupported != "unclear"
            and "unclear" not in decision.atoms.values()
        )
        generation = row["response"]["id"]
        _require(generation not in generations)
        _require(_money(row["cost_usd"]) <= _money(row["reserved_usd"]))
        generations.add(generation)
        calls.add(row["call_id"])
        rows.append(row)
    return rows


def qualification(calibration: dict) -> QualificationRemote:
    _require(calibration.get("judge") == JUDGE)
    pin = QualificationRemote.model_validate(calibration.get("judge_qualification"))
    verify_audit(pin)
    return pin


def scorer_protocol(calibration: dict) -> str:
    pin = qualification(calibration)
    return JUDGE + ":" + stable_hash(pin.model_dump())


def preflight(calibration: dict) -> None:
    qualification(calibration)
    _review_settings(calibration)
    if (
        not runtime.is_enabled()
        or not runtime.cloud_allowed()
        or not runtime.credential()
    ):
        raise ValueError("experiment_remote_judge_unavailable")


def _review_settings(calibration: dict) -> tuple[Path, Decimal, Decimal]:
    config = calibration.get("remote_review", {})
    _require(set(config) == {"ledger_root", "budget_usd", "max_request_usd"})
    root = _root(config["ledger_root"])
    budget = min(
        _money(config["budget_usd"]), Decimal(str(SETTINGS.OPENROUTER_DAILY_LIMIT_USD))
    )
    per_request = min(
        _money(config["max_request_usd"]),
        Decimal(str(SETTINGS.OPENROUTER_MESSAGE_LIMIT_USD)),
    )
    _require(budget > 0 and per_request > 0 and per_request <= budget)
    return root, budget, per_request


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_review_receipt(
    pin: QualificationRemote, spec: dict, case: dict, answer: dict, grade: dict
) -> None:
    body = request_payload(spec, case, answer)
    raw = grade.get("model_review_call")
    if not isinstance(raw, dict):
        raise ValueError(ERROR)
    _receipt_name(raw.get("receipt_name"))
    # Validate before constructing a path or opening any receipt.
    _require(
        len(raw["receipt_name"]) == 37
        and raw["receipt_name"].endswith(_JSON_SUFFIX)
        and all(c in "0123456789abcdef" for c in raw["receipt_name"][:-5])
    )
    row = _bound(
        _root(raw["ledger_root"]) / "receipts",
        raw["receipt_name"],
        raw["receipt_sha256"],
    )
    _require(row.get("qualification_sha256") == stable_hash(pin.model_dump()))
    decision = _verify_call(row, body, answer["text"], pin.protocol_sha256)
    expected = local._grade(decision, claim_rubric(spec), case, answer, judge=JUDGE)
    _require(all(grade.get(key) == value for key, value in expected.items()))


def _receipt_name(name: object) -> str:
    _require(isinstance(name, str))
    assert isinstance(name, str)
    _require(
        len(name) == 37
        and name.endswith(_JSON_SUFFIX)
        and all(c in "0123456789abcdef" for c in name[:-5])
    )
    return name


def _ledger_charge(row: dict, pin: QualificationRemote) -> Decimal:
    _require(row["qualification_sha256"] == stable_hash(pin.model_dump()))
    _require(row["protocol_sha256"] == pin.protocol_sha256)
    _require(row["status"] in {"attempted", "failed", "completed"})
    body = request_payload(row["spec"], row["case"], row["answer"])
    _require(row["request"] == body and row["request_sha256"] == stable_hash(body))
    reservation = _money(row["reserved_usd"])
    _require(reservation == reserve(body))
    cost = row.get("cost_usd")
    if cost is not None:
        _require(reported_cost(row["response"]) == cost)
    if row["status"] == "attempted":
        _require(cost is None and row["response"] == {})
    else:
        _require(row["response_sha256"] == stable_hash(row["response"]))
        _require(_time(row["started_at"]) <= _time(row["finished_at"]))
    if row["status"] == "completed":
        _verify_call(row, body, row["answer"]["text"], pin.protocol_sha256)
    return reservation if cost is None else _money(cost)


def _ledger_rows(root: Path, ledger: dict) -> list[dict]:
    existing = {path.name for path in (root / "receipts").glob("*.json")}
    _require(existing == set(ledger["receipts"]))
    rows = []
    calls: set[str] = set()
    for name, checksum in ledger["receipts"].items():
        row = _bound(root / "receipts", _receipt_name(name), checksum)
        _require(row["call_id"] + _JSON_SUFFIX == name and row["call_id"] not in calls)
        calls.add(row["call_id"])
        rows.append(row)
    return sorted(rows, key=lambda row: _time(row["started_at"]))


def _ledger_snapshot(root: Path, pin: QualificationRemote) -> tuple[dict, set[str]]:
    _recover_transaction(root)
    identity = stable_hash(pin.model_dump())
    base = _money(
        _bound(_root(pin.audit_root), "result.json", pin.result_sha256)["accounted_usd"]
    )
    path = root / _LEDGER_FILE
    if not path.exists():
        _require(not list((root / "receipts").glob("*.json")))
        return {
            "qualification_sha256": identity,
            "accounted_usd": str(base),
            "receipts": {},
        }, set()
    ledger = read_json(path)
    _require(
        isinstance(ledger, dict)
        and set(ledger) == {"qualification_sha256", "accounted_usd", "receipts"}
    )
    _require(
        ledger["qualification_sha256"] == identity
        and isinstance(ledger["receipts"], dict)
    )
    total = base
    generations: set[str] = set()
    for row in _ledger_rows(root, ledger):
        total += _ledger_charge(row, pin)
        generation = row["response"].get("id")
        if isinstance(generation, str) and generation.strip():
            # Failed duplicates remain chargeable observations, not accepted calls.
            if row["status"] == "completed":
                _require(generation not in generations)
            generations.add(generation)
    _require(_money(ledger["accounted_usd"]) == total)
    return ledger, generations


def _current_version(path: Path, before: str | None, after: str) -> None:
    current = digest(path) if path.exists() else None
    _require(current in {before, after})


def _recover_transaction(root: Path) -> None:
    journal_path = root / _TRANSACTION_FILE
    if not journal_path.exists():
        return
    journal = read_json(journal_path)
    _require(journal["schema_version"] == 1)
    name = _receipt_name(journal["receipt_name"])
    row = _bound(root, _STAGED_RECEIPT_FILE, journal["receipt_sha256"])
    ledger = _bound(root, _STAGED_LEDGER_FILE, journal["ledger_sha256"])
    _require(ledger["receipts"].get(name) == journal["receipt_sha256"])
    target = root / "receipts" / name
    _current_version(
        target, journal["previous_receipt_sha256"], journal["receipt_sha256"]
    )
    _current_version(
        root / _LEDGER_FILE, journal["previous_ledger_sha256"], journal["ledger_sha256"]
    )
    # Repeating either idempotent write after a crash cannot cause another POST.
    atomic_json(target, row)
    atomic_json(root / _LEDGER_FILE, ledger)
    journal_path.unlink()
    (root / _STAGED_RECEIPT_FILE).unlink()
    (root / _STAGED_LEDGER_FILE).unlink()


def _save_call(root: Path, path: Path, row: dict, ledger: dict) -> None:
    _require(path.parent == root / "receipts")
    _receipt_name(path.name)
    _require(not (root / _TRANSACTION_FILE).exists())
    previous_receipt = digest(path) if path.exists() else None
    ledger_path = root / _LEDGER_FILE
    previous_ledger = digest(ledger_path) if ledger_path.exists() else None
    atomic_json(root / _STAGED_RECEIPT_FILE, row)
    row_sha = digest(root / _STAGED_RECEIPT_FILE)
    ledger["receipts"][path.name] = row_sha
    atomic_json(root / _STAGED_LEDGER_FILE, ledger)
    atomic_json(
        root / _TRANSACTION_FILE,
        {
            "schema_version": 1,
            "receipt_name": path.name,
            "previous_receipt_sha256": previous_receipt,
            "previous_ledger_sha256": previous_ledger,
            "receipt_sha256": row_sha,
            "ledger_sha256": digest(root / _STAGED_LEDGER_FILE),
        },
    )
    _recover_transaction(root)


def _cached_observations(
    marker_path: Path,
    plan_sha: str,
    calibration: dict,
    cases: dict,
    plan: list,
    pin: QualificationRemote,
) -> list[dict] | None:
    if not marker_path.exists():
        return None
    marker = read_json(marker_path)
    _require(marker["plan_sha256"] == plan_sha)
    if marker.get("status") != "completed":
        raise ValueError("experiment_remote_judge_attempt_already_started")
    cached = marker["observations"]
    _require(len(cached) == len(plan))
    for (ident, label, answer), grade in zip(plan, cached):
        _require(grade["record_id"] == ident and grade["label"] == label)
        verify_review_receipt(
            pin, calibration["cases"][ident], cases[ident], answer, grade
        )
    return cached


def _post_call(
    client: httpx.Client,
    root: Path,
    pin: QualificationRemote,
    ledger: dict,
    body: dict,
    spec: dict,
    case: dict,
    answer: dict,
    run_id: str,
    label: str,
    remaining: float,
    generations: set[str],
) -> tuple[dict, dict]:
    reservation = reserve(body)
    accounted = _money(ledger["accounted_usd"])
    ident = uuid4().hex
    row = {
        "status": "attempted",
        "run_id": run_id,
        "call_id": ident,
        "record_id": case["record_id"],
        "label": label,
        "qualification_sha256": stable_hash(pin.model_dump()),
        "protocol_sha256": pin.protocol_sha256,
        "request": body,
        "spec": spec,
        "case": case,
        "answer": answer,
        "request_sha256": stable_hash(body),
        "reserved_usd": str(reservation),
        "started_at": _utc(),
        "response": {},
        "cost_usd": None,
    }
    path = root / "receipts" / (ident + _JSON_SUFFIX)
    ledger["accounted_usd"] = str(accounted + reservation)
    _save_call(root, path, row, ledger)
    try:
        response = client.post(ENDPOINT, json=body, timeout=min(75.0, remaining))
        row["http_status"] = response.status_code
        try:
            raw = response.json()
        except ValueError:
            row["response"] = {"non_json_body": response.text[:16000]}
            raise
        _require(isinstance(raw, dict))
        row["response"] = raw
        row["cost_usd"] = reported_cost(raw)
        response.raise_for_status()
        decision = decode(raw, body, answer["text"])
        _require(row["cost_usd"] is not None and raw["id"] not in generations)
        _require(_money(row["cost_usd"]) <= reservation)
        row["decision"] = decision.model_dump()
        row["status"] = "completed"
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        row["status"] = "failed"
        row["error_type"] = type(exc).__name__
        raise
    finally:
        row["finished_at"] = _utc()
        row["response_sha256"] = stable_hash(row["response"])
        if row["cost_usd"] is not None:
            ledger["accounted_usd"] = str(accounted + _money(row["cost_usd"]))
        _save_call(root, path, row, ledger)
    _require(_money(row["cost_usd"]) <= reservation)
    generations.add(row["response"]["id"])
    return local._grade(decision, claim_rubric(spec), case, answer, judge=JUDGE), {
        "ledger_root": str(root),
        "receipt_name": path.name,
        "receipt_sha256": digest(path),
    }


def review_bundle(
    calibration: dict,
    bundle: dict,
    run_id: str,
    seconds: float,
    *,
    check: Callable[[], None] = lambda: None,
) -> list[dict]:
    """A locked budget ledger, one attempt per exact plan, no model retries."""
    from venom_core.core.environment_policy import ensure_data_mutation_allowed

    pin = qualification(calibration)
    root, budget, per_request = _review_settings(calibration)
    _require(math.isfinite(seconds) and seconds > 0)
    if (
        not runtime.is_enabled()
        or not runtime.cloud_allowed()
        or not runtime.credential()
    ):
        raise ValueError("experiment_remote_judge_unavailable")
    ensure_data_mutation_allowed("academy_remote_judge")
    cases = {c["record_id"]: c for c in bundle["cases"]}
    _require(len(cases) == len(bundle["cases"]))
    plan = [
        (row["case"]["record_id"], label, answer)
        for row in bundle["answers"]
        for label, answer in row["answers"].items()
    ]
    _require(
        bool(plan) and len({(ident, label) for ident, label, _ in plan}) == len(plan)
    )
    payloads = [
        request_payload(calibration["cases"][ident], cases[ident], answer)
        for ident, _, answer in plan
    ]
    plan_sha = stable_hash(
        {"run_id": run_id, "bundle": bundle, "qualification": pin.model_dump()}
    )
    root.mkdir(parents=True, exist_ok=True)
    (root / "receipts").mkdir(exist_ok=True)
    marker_path = root / ("attempt-" + plan_sha + _JSON_SUFFIX)
    deadline = time.monotonic() + seconds
    observations = []
    with file_lock(root / "ledger.lock", blocking=False):
        ledger, generations = _ledger_snapshot(root, pin)
        cached = _cached_observations(
            marker_path, plan_sha, calibration, cases, plan, pin
        )
        if cached is not None:
            return cached
        atomic_json(
            marker_path,
            {"status": "started", "plan_sha256": plan_sha, "created_at": _utc()},
        )
        with httpx.Client(
            trust_env=False,
            follow_redirects=False,
            headers={"Authorization": "Bearer " + runtime.credential()},
        ) as client:
            for (ident, label, answer), body in zip(plan, payloads):
                check()
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("experiment_judge_time_limit")
                reservation = reserve(body)
                if (
                    reservation > per_request
                    or _money(ledger["accounted_usd"]) + reservation > budget
                ):
                    raise ValueError("experiment_remote_judge_budget_exhausted")
                grade, raw = _post_call(
                    client,
                    root,
                    pin,
                    ledger,
                    body,
                    calibration["cases"][ident],
                    cases[ident],
                    answer,
                    run_id,
                    label,
                    remaining,
                    generations,
                )
                if time.monotonic() > deadline:
                    raise TimeoutError("experiment_judge_time_limit")
                observations.append(
                    {
                        **grade,
                        "record_id": ident,
                        "label": label,
                        "model_review_call": raw,
                    }
                )
        atomic_json(
            marker_path,
            {
                "status": "completed",
                "plan_sha256": plan_sha,
                "finished_at": _utc(),
                "observations": observations,
            },
        )
    return observations
