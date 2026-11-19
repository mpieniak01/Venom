"""Keep user corrections and explicit arithmetic distinct from conversion steps."""

import pytest

from venom_core.services.grounded_calculator import calculate
from venom_core.services.grounded_explicit_totals import GroupTotal, bind_explicit_total
from venom_core.services.grounded_handoff_sms import handoff_sms_recap
from venom_core.services.grounded_speed_measurement import has_repeated_speed_scale


@pytest.mark.parametrize(
    ("withdrawn", "children"), [("trojga", 7), ("3", 7), ("dwojga", 10), ("2", 10)]
)
def test_group_withdrawal_binds_the_matching_growth(withdrawn, children):
    users = (
        "W grupie wycieczkowej jest 16 dorosłych, 7 dzieci. "
        "Jedna opiekunka wlicza się już do dorosłych.",
        "Dołącza 3 dzieci, dorośli bez zmian. Kalkulatorem policz całą grupę.",
        "Dwóch dorosłych odwołało obecność. "
        f"Próba dopisania {withdrawn} dzieci nieaktualna. Użyj kalkulatora ponownie.",
    )
    state = bind_explicit_total(users)
    assert state == GroupTotal(14, children)
    assert calculate(state.expression) == str(14 + children)


@pytest.mark.parametrize(
    ("original", "current", "accepted"),
    [
        ("statywu", "statyw", True),
        ("pompy", "pompę", True),
        ("STATYWU", "STATYW", True),
        ("pudełko", "pudełko", True),
        ("statywu", "pompę", False),
        ("pompy", "statyw", False),
        ("statywu", "inny statyw", False),
    ],
)
def test_handoff_requires_the_same_item_across_turns(original, current, accepted):
    users = (
        f"Ułóż krótką wiadomość o przekazaniu {original}. "
        "Mogę przyjść po 16:30 i mam zostawić go u Tomka.",
        f"Poproś Tomka o potwierdzenie, czy będzie o 17:40. Nadal chodzi o {current}.",
        "Jednak nie obiecuj, że będę punktualnie. Zapytaj, czy po 17:00 mu pasuje.",
    )
    result = handoff_sms_recap("Zwróć tylko gotowy SMS, bez tytułu.", users)
    if accepted:
        assert result == (
            f"Cześć, czy pasuje Ci, jeśli zostawię u Ciebie {current} po 17:00?"
        )
    else:
        assert result is None


@pytest.mark.parametrize("expression", ["(10+5)*3.6", "(10+5)*(18/5)", "(10+5)*18/5"])
def test_requested_arithmetic_multiplier_is_not_a_conversion(expression):
    request = "Zwiększ sumę 10 m/s i 5 m/s 3,6 raza i podaj wynik w km/h"
    assert not has_repeated_speed_scale(expression, "m/s", "km/h", request=request)
    assert calculate(f"({expression})*18/5") == "194.4"


@pytest.mark.parametrize(
    ("expression", "message"),
    [
        (
            "((10+5)*3.6)*3.6",
            "Zwiększ sumę 10 m/s i 5 m/s 3,6 raza i podaj wynik w km/h",
        ),
        (
            "((10+5)*18/5)*3.6",
            "Zwiększ sumę 10 m/s i 5 m/s 3,6 raza i podaj wynik w km/h",
        ),
        ("(10+5)*3.6", "Zwiększ sumę 10 m/s i 5 m/s 2 razy i podaj wynik w km/h"),
        ("(10+5)*3.6", "Nie zwiększaj sumy 3,6 raza. Podaj wynik w km/h"),
        ("(720/120)*3.6", "Podaj prędkość w km/h."),
    ],
)
def test_unrequested_or_additional_conversion_is_still_rejected(expression, message):
    assert has_repeated_speed_scale(expression, "m/s", "km/h", request=message)
