"""Presentation policy and real-input distinctions at the pilot release boundary."""

import pytest

from venom_core.services.grounded_dialogue import EvidenceError, Requirements
from venom_core.services.grounded_pilot import (
    SemanticVerdict,
    material_hash,
    run_pilot_turn,
)
from venom_core.services.grounded_presentation import (
    normalize_claim,
    requested_precision,
    rounded_value,
)
from venom_core.services.grounded_review import compact_packet


class EmptySources:
    def search(self, _query):
        return []


class Model:
    def __init__(
        self,
        expression="12/21*100",
        claim="57,14%",
        prose="Wynik to 57,14%.",
        missing=(),
        unit="%",
    ):
        self.expression, self.claim, self.prose, self.missing = (
            expression,
            claim,
            prose,
            list(missing),
        )
        self.unit = unit
        self.calls = []

    def __call__(self, phase, data, schema):
        self.calls.append((phase, data))
        if phase == "input_roles":
            return {
                "items": [
                    {"label": label, "role": "input", "requested_output_quote": ""}
                    for label in data["reported_missing"]
                ]
            }
        if phase == "assess":
            return {
                "current_state": "Składniki podano wcześniej.",
                "missing": self.missing,
            }
        if phase == "plan":
            return {
                "calculations": [
                    {
                        "calculation_id": "total",
                        "expression": self.expression,
                        "unit": self.unit,
                    }
                ]
            }
        assert phase == "draft"
        clarify = data["plan"]["mode"] == "clarify"
        return {
            "prose": self.prose,
            "sources": [],
            "calculations": []
            if clarify
            else [{"calculation_id": "total", "value": self.claim, "unit": self.unit}],
        }


class Reviewer:
    qualification_id = "test-boundary-only"

    def __init__(self):
        self.materials = []

    def review(self, material):
        self.materials.append(material)
        return SemanticVerdict(
            material_hash(material),
            self.qualification_id,
            True,
            "Fixture boundary check.",
        )


def invoke(message, model, reviewer=None):
    reviewer = reviewer or Reviewer()
    result = run_pilot_turn(
        message,
        "presentation-test",
        EmptySources(),
        model,
        reviewer,
        required=Requirements(calculation=True),
    )
    return result, reviewer


@pytest.mark.parametrize(
    "expression,claim,prose,places",
    [
        ("12/21*100", "57,14%", "Wynik to 57,14%.", "dwóch"),
        ("14/22*100", "63.64 %", "Odpowiedź: 63,64%.", "2"),
        ("1/6*100", "16,7", "Udział to 16,7%.", "jednego"),
        ("1.25", "1,3%", "Udział to 1,3%.", "1"),
        ("-1.25", "−1,3%", "Udział to −1,3%.", "1"),
        ("12.5", "13%", "Udział to 13%.", "0"),
    ],
)
def test_requested_rounding_reaches_review_with_exact_evidence(
    expression, claim, prose, places
):
    model = Model(expression, claim, prose)
    result, reviewer = invoke(f"Podaj procent do {places} miejsc po przecinku.", model)
    assert result.text == prose
    material = reviewer.materials[0]
    assert material["draft"]["calculations"][0]["value"] == claim
    assert material["evidence"]["calculations"][0]["value"] != claim
    assert compact_packet(material)["result_precision"] == material["result_precision"]
    assert material["result_precision"]["rounding"] == "ROUND_HALF_UP"


@pytest.mark.parametrize(
    "claim,prose",
    [
        ("57,13%", "Wynik to 57,13%."),
        ("57,14 zł", "Wynik to 57,14%."),
        ("57.14%%", "Wynik to 57,14%."),
        ("57.14", "Wynik to 57,15%."),
        ("57.14", "Wynik to 57,142%."),
        ("57.14", "Wynik to 57,14 zł."),
        ("57.14", "Po drodze 57,14%, ale ostatecznie 58%."),
    ],
)
def test_rounding_does_not_allow_wrong_claim_unit_precision_or_visible_result(
    claim, prose
):
    reviewer = Reviewer()
    with pytest.raises(
        EvidenceError, match="answer_calculation_mismatch|answer_result_unbound"
    ):
        invoke(
            "Podaj procent do dwóch miejsc po przecinku.",
            Model(claim=claim, prose=prose),
            reviewer,
        )
    assert not reviewer.materials


def test_unrequested_rounding_cannot_be_authorized_by_model_claim():
    with pytest.raises(EvidenceError, match="answer_calculation_mismatch"):
        invoke("Podaj procent.", Model())


@pytest.mark.parametrize(
    "message,error",
    [
        ("Podaj procent do 2 miejsc po przecinku. Nie zaokrąglaj.", "ambiguous"),
        (
            "Podaj procent do 1 miejsca po przecinku i do 2 miejsc po przecinku.",
            "ambiguous",
        ),
        ("Podaj procent do 99 miejsc po przecinku.", "unsupported"),
        ("Oblicz 1/3 do 2 miejsc po przecinku.", "unit_required"),
    ],
)
def test_ambiguous_or_unsupported_precision_fails_closed(message, error):
    with pytest.raises(EvidenceError, match="answer_precision_" + error):
        invoke(message, Model())


@pytest.mark.parametrize(
    "missing,remaining",
    [
        (["całkowity koszt"], []),
        (["koszt całkowity", "cena dojazdu"], ["cena dojazdu"]),
        (["łączny koszt", "liczba pojemników"], ["liczba pojemników"]),
        (["koszt ubezpieczenia"], ["koszt ubezpieczenia"]),
    ],
)
def test_requested_total_is_not_an_input_but_real_missing_fields_remain(
    missing, remaining
):
    model = Model(
        "18+5*7+5",
        "58",
        "Ile kosztuje dojazd?" if remaining else "58 zł.",
        missing,
        unit="zł",
    )
    _, reviewer = invoke(
        "Policz kalkulatorem pełen koszt po korekcie i podaj kwotę.", model
    )
    assert reviewer.materials[0]["plan"]["missing"] == remaining
    assert ("plan" in [phase for phase, _ in model.calls]) == (not remaining)


def test_cost_as_input_to_tax_is_not_discarded():
    model = Model(prose="Jaki jest całkowity koszt?", missing=["całkowity koszt"])
    _, reviewer = invoke("Oblicz podatek od zamówienia.", model)
    assert reviewer.materials[0]["plan"]["missing"] == ["całkowity koszt"]


@pytest.mark.parametrize(
    "value,unit,wanted",
    [
        ("12,50 zł", "zł", "12.50"),
        ("12.50 zł", "%", "12.50 zł"),
        ("12,5", "", "12.5"),
        ("−12,5%", "%", "-12.5"),
        ("12,5%%", "%", "12,5%%"),
    ],
)
def test_decimal_spelling_preserves_mismatched_units(value, unit, wanted):
    assert normalize_claim(value, unit) == wanted


@pytest.mark.parametrize("value", ["NaN", "Infinity", "1e999999999"])
def test_rounding_rejects_nonfinite_and_unbounded_numbers(value):
    with pytest.raises(ValueError, match="answer_precision_unsupported"):
        rounded_value(value, 2)


def test_no_implicit_rounding_policy():
    assert requested_precision("Oblicz 12/7.") is None


@pytest.mark.parametrize(
    "message,label",
    [
        (
            "Policz kalkulatorem udział żółtych po zmianie. Podaj procent zaokrąglony do jednego miejsca po przecinku.",
            "procent żółtych",
        ),
        (
            "Policz kalkulatorem dokładny procent błękitnych wśród wszystkich. Podaj wynik bez zaokrąglania.",
            "procent błękitnych wśród wszystkich",
        ),
        ("Policz kalkulatorem procent porysowanych.", "procent porysowanych"),
    ],
)
def test_requested_percentage_is_output_not_a_missing_operand(message, label):
    model = Model("12.5", "12,5%", "Udział wynosi 12,5%.", [label])
    _, reviewer = invoke(message, model)
    assert reviewer.materials[0]["plan"]["mode"] == "answer"
    assert reviewer.materials[0]["plan"]["missing"] == []
    assert dict(model.calls)["plan"]["calculation_contract"]["input_unit"]


def test_real_unknown_percentage_rate_still_requires_clarification():
    model = Model(
        prose="Jaką część czerwonych usunięto?",
        missing=["procent usuniętych czerwonych"],
    )
    _, reviewer = invoke("Podaj procent czerwonych w pozostałej grupie.", model)
    assert reviewer.materials[0]["plan"]["missing"] == ["procent usuniętych czerwonych"]
    assert "plan" not in dict(model.calls)


def test_ratio_unit_contract_never_invents_a_count_to_percentage_conversion():
    from venom_core.services.grounded_pilot import Calculation, _compile_calculation

    with pytest.raises(EvidenceError, match="pilot_conversion_unsupported"):
        _compile_calculation(
            Calculation(
                calculation_id="ratio",
                expression="12/21*100",
                unit="%",
                input_unit="punktów",
            )
        )


def test_output_paraphrase_is_rechecked_against_current_request_before_clarification():
    message = "Policz kalkulatorem, jaki procent wszystkich modeli stanowią gliniane. Podaj procent do trzech miejsc po przecinku."

    class RolesModel(Model):
        def __call__(self, phase, data, schema):
            if phase == "input_roles":
                self.calls.append((phase, data))
                assert "Nie zakładaj wartości wejścia" in data["instruction"]
                return {
                    "items": [
                        {
                            "label": "procent glinianych modeli",
                            "role": "output",
                            "requested_output_quote": "jaki procent wszystkich modeli stanowią gliniane",
                        }
                    ]
                }
            return super().__call__(phase, data, schema)

    model = RolesModel(
        "1/6*100", "16.667", "Udział wynosi 16,667%.", ["procent glinianych modeli"]
    )
    _, reviewer = invoke(message, model)
    material = reviewer.materials[0]
    assert material["plan"]["mode"] == "answer"
    assert material["input_roles"]["items"][0]["role"] == "output"
    assert compact_packet(material)["input_roles"] == material["input_roles"]
    assert dict(model.calls)["input_roles"]["prior_users"] == ()


@pytest.mark.parametrize(
    "items,error",
    [
        (
            [
                {
                    "label": "procent modeli",
                    "role": "output",
                    "requested_output_quote": "nie ma tego w prośbie",
                }
            ],
            "unbound",
        ),
        (
            [
                {
                    "label": "inne pole",
                    "role": "output",
                    "requested_output_quote": "Podaj procent",
                }
            ],
            "coverage_invalid",
        ),
        (
            [
                {
                    "label": "procent modeli",
                    "role": "output",
                    "requested_output_quote": "",
                }
            ],
            "unbound",
        ),
    ],
)
def test_input_recheck_cannot_remove_an_unbound_or_different_input(items, error):
    class RolesModel(Model):
        def __call__(self, phase, data, schema):
            return (
                {"items": items}
                if phase == "input_roles"
                else super().__call__(phase, data, schema)
            )

    reviewer = Reviewer()
    with pytest.raises(EvidenceError, match="pilot_input_role_" + error):
        invoke(
            "Podaj procent tych egzemplarzy.",
            RolesModel(missing=["procent modeli"]),
            reviewer,
        )
    assert not reviewer.materials


def test_uncertain_role_preserves_real_input_instead_of_guessing_it():
    class RolesModel(Model):
        def __call__(self, phase, data, schema):
            if phase == "input_roles":
                return {
                    "items": [
                        {
                            "label": "stawka ubytku",
                            "role": "uncertain",
                            "requested_output_quote": "",
                        }
                    ]
                }
            return super().__call__(phase, data, schema)

    _, reviewer = invoke(
        "Podaj procent pozostałych modeli.",
        RolesModel(prose="Jaka jest stawka ubytku?", missing=["stawka ubytku"]),
    )
    assert reviewer.materials[0]["plan"]["mode"] == "clarify"
    assert reviewer.materials[0]["plan"]["missing"] == ["stawka ubytku"]


def test_named_operands_never_enter_the_model_output_reclassification():
    class GuardedModel(Model):
        def __call__(self, phase, data, schema):
            assert phase != "input_roles", (
                "A quoted request is not proof an operand is a result."
            )
            return super().__call__(phase, data, schema)

    _, reviewer = invoke(
        "Policz kalkulatorem pełną kwotę po zmianie, łącznie z dojazdem.",
        GuardedModel(prose="Jaka jest cena dojazdu?", missing=["dojazd"], unit="zł"),
    )
    assert reviewer.materials[0]["plan"]["missing"] == ["dojazd"]
    assert not reviewer.materials[0]["evidence"]["calculations"]


def test_percentage_unit_can_follow_the_rounding_instruction():
    result, _ = invoke(
        "Wynik zaokrąglij do trzech miejsc po przecinku i zapisz jako procent.",
        Model("1/6*100", "16,667%", "Udział wynosi 16,667%."),
    )
    assert result.text == "Udział wynosi 16,667%."
