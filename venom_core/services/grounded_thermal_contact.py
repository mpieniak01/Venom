"""Check a short-contact comparison against independently bound premises."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from venom_core.services.grounded_dialogue import EvidenceError, _normal

Temperature = Literal["colder", "warmer"]
Flow = Literal["hand_to_objects", "objects_to_hand"]

# Compare only opposite groups, for ordinary solid samples at equal temperature
# and comparable contact. This is not a conductivity ranking within a group.
_MATERIALS = {
    "stal": r"stal|stali|stalow\w*",
    "miedź": r"miedz|miedzi|miedzia|miedzian\w*",
    "mosiądz": r"mosiadz\w*|mosiez\w*",
    "aluminium": r"aluminium|aluminiow\w*",
    "filc": r"filc\w*",
    "korek": r"korek|korka|korkow\w*",
    "drewno": r"drewn\w*",
    "guma": r"guma|gumy|gumow\w*",
}
_FAST = frozenset(("stal", "miedź", "mosiądz", "aluminium"))
_CONTACT = re.compile(r"\b(?:dotyk\w*|w dotyku)\b")
_CHOICE = re.compile(
    r"\b(?:ktory|ktora|ktore)\b[^.!?]{0,120}"
    r"\b(?:chlodniejsz\w*|zimniejsz\w*|cieplejsz\w*|goretsz\w*)\b"
)
_EQUAL = re.compile(
    r"\b(?:(?:te sama|taka sama|jednakow\w*|rowna) temperature"
    r"|(?:obie|oba) (?:plytki |przedmioty )?sa jednakowo (?:cieple|zimne|chlodne|gorace)"
    r"|oba maja po \d{1,3} stopni)\b"
)
_RELATIVE_TO_HAND = (
    r"(?P<relative>chlodniejsz\w*|zimniejsz\w*|cieplejsz\w*|goretsz\w*)"
    r" (?:od|niz) (?:(?:mojej|mojego|temperatury|temp) )*(?:dlon\w*|palc\w*|palec)\b"
)
_RELATION = re.compile(
    rf"\b(?:oba|obie) (?:plytki |przedmioty |probki )?sa (?:jednakowo |tak samo )?{_RELATIVE_TO_HAND}"
)
_ANY_RELATION = re.compile(rf"\b{_RELATIVE_TO_HAND}")
_SEQUENCE = re.compile(r"\bnajpierw\b[^.]*\bpotem\b")
_UNSUPPORTED = re.compile(
    r"\b(?:powlok\w*|foli\w*|powlecz\w*|powlekan\w*|mok\w*|wilgot\w*|"
    r"nierown\w*|rozne temperatury|rozna grubosc|izolowan\w*|warstw\w*|"
    r"nie (?:maja|wiem|wiemy|wiadomo|ustalono))\b"
)
_QUESTION_START = re.compile(r"\b(?:ktory|ktora|ktore)\b[^.!?]{0,120}\?")
_DIRECTION: dict[Temperature, Flow] = {
    "colder": "hand_to_objects",
    "warmer": "objects_to_hand",
}


@dataclass(frozen=True)
class ThermalStep:
    condition: Temperature
    flow: Flow
    material: str


@dataclass(frozen=True)
class ThermalContact:
    faster: str
    slower: str
    conditions: tuple[Temperature, ...]

    def check(self, proposed: tuple[ThermalStep, ...]) -> None:
        conditions = tuple(step.condition for step in proposed)
        if conditions != self.conditions:
            raise EvidenceError("thermal_conditions_mismatch")
        errors = []
        if any(step.flow != _DIRECTION[step.condition] for step in proposed):
            errors.append("thermal_flow_mismatch")
        if any(step.material != self.faster for step in proposed):
            errors.append("thermal_material_mismatch")
        if errors:
            raise EvidenceError(",".join(errors))

    def render(self) -> str:
        def sentence(condition: Temperature) -> str:
            if condition == "colder":
                return (
                    f"Gdy oba materiały są chłodniejsze od dłoni, {self.faster} może dawać "
                    "silniejsze wrażenie chłodu, bo ciepło płynie z dłoni do przedmiotów "
                    f"i przy porównywalnym dotyku {self.faster} odbiera je szybciej niż {self.slower}."
                )
            return (
                f"Gdy oba materiały są cieplejsze od dłoni, {self.faster} może dawać "
                "silniejsze wrażenie ciepła, bo ciepło płynie z przedmiotów do dłoni "
                f"i przy porównywalnym dotyku {self.faster} oddaje je szybciej niż {self.slower}."
            )

        return " ".join(sentence(condition) for condition in self.conditions)


def thermal_contact(message: str) -> ThermalContact | None:
    """Bind an explicit tactile comparison. Refuse ambiguous or unsupported premises."""
    text = " ".join(_normal(message).split())
    if not (_CONTACT.search(text) and _CHOICE.search(text)):
        return None
    materials = tuple(
        material
        for material, forms in _MATERIALS.items()
        if re.search(rf"\b(?:{forms})\b", text)
    )
    question = _QUESTION_START.search(text)
    premises = text[: question.start()] if question is not None else text
    equal = _EQUAL.search(premises)
    if len(materials) < 2 and not (equal and _ANY_RELATION.search(text)):
        return None
    if len(materials) != 2 or not equal or _UNSUPPORTED.search(text):
        raise EvidenceError("thermal_contact_premises_unbound")
    high = tuple(material for material in materials if material in _FAST)
    low = tuple(material for material in materials if material not in _FAST)
    if len(high) != 1 or len(low) != 1:
        raise EvidenceError("thermal_contact_materials_unbound")
    conditions: list[Temperature] = [
        "colder" if m["relative"].startswith(("chlod", "zim")) else "warmer"
        for m in _RELATION.finditer(premises)
    ]
    if (
        not conditions
        or len(conditions) != len(set(conditions))
        or len(conditions) != sum(1 for _ in _ANY_RELATION.finditer(premises))
        or bool(_SEQUENCE.search(premises)) != (len(conditions) == 2)
    ):
        raise EvidenceError("thermal_contact_temperature_unbound")
    return ThermalContact(high[0], low[0], tuple(conditions))
