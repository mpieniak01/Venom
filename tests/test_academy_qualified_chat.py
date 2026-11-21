"""Integration and retention for the opt-in Academy reply controls."""

import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from venom_core.api.dependencies import get_session_store
from venom_core.api.routes import llm_simple
from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services import llm_simple_service, vast_chat_runtime
from venom_core.services.academy.qualified_chat import (
    GENERATION_TRUNCATED,
    QUALIFIED_BOLT_MODEL,
    QUALIFIED_MODEL,
    CalendarClaimStream,
    prepare_reply,
)
from venom_core.services.academy.qualified_chat_constraints import (
    active_constraints,
    constraint_conflicts,
    find_violations,
    uncertain_constraints,
)
from venom_core.services.academy.qualified_chat_options import (
    CountRequirement,
    requested_count,
    split_options,
)
from venom_core.services.academy.qualified_chat_schedule import route_shift
from venom_core.services.session_store import SessionStore


def turn(content, role="user"):
    return {"role": role, "content": content}


def native(content, done=True, reason="stop"):
    return {"message": {"content": content}, "done": done, "done_reason": reason}


def streamed(*chunks, finish="stop"):
    return [
        *[{"choices": [{"delta": {"content": chunk}}]} for chunk in chunks],
        {"choices": [{"delta": {}, "finish_reason": finish}]},
    ]


@pytest.fixture
def studio_chat(monkeypatch, tmp_path, request):
    runtime = SimpleNamespace(
        provider="ollama",
        model_name=getattr(request, "param", QUALIFIED_MODEL),
        endpoint="http://127.0.0.1:11434/v1",
        host_local=True,
        service_type="local",
        runtime_id="runtime",
        config_hash="config",
    )
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", True
    )
    monkeypatch.setattr(llm_simple_service, "get_active_llm_runtime", lambda: runtime)
    monkeypatch.setattr(
        llm_simple_service, "_get_active_adapter_id", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(vast_chat_runtime, "preflight", AsyncMock())
    sent, replies = [], []

    @asynccontextmanager
    async def upstream(**kwargs):
        sent.append(kwargs)
        assert replies, "unexpected model call"
        reply = replies.pop(0)

        async def lines():
            assert isinstance(reply, list), reply
            for packet in reply:
                yield "data: " + json.dumps(packet)
            yield "data: [DONE]"

        yield SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: reply, aiter_lines=lines
        )

    monkeypatch.setattr(
        llm_simple_service.llm_simple_transport, "open_stream_response", upstream
    )
    app = FastAPI()
    app.include_router(llm_simple.router)
    monkeypatch.setattr(llm_simple_service.SETTINGS, "MEMORY_ROOT", str(tmp_path))
    store = SessionStore()
    app.dependency_overrides[get_session_store] = lambda: store
    app.state.studio_runtime = SimpleNamespace(get_vector_store=lambda: None)
    client = TestClient(app)

    def chat(content, history=(), *, session=None, **kwargs):
        session = session or str(uuid4())
        for index, message in enumerate(history):
            store.append_message(
                session,
                {**message, "request_id": str(index // 2), "status": "COMPLETED"},
            )
        response = client.post(
            "/api/v1/llm/simple/stream",
            json={
                "content": content,
                "studio_normal": True,
                "session_id": session,
                **kwargs,
            },
        )
        assert response.status_code == 200, response.text
        events = [chunk.splitlines() for chunk in response.text.strip().split("\n\n")]
        names = [chunk[0] for chunk in events]
        assert names[0] == "event: start"
        assert names[-1] == "event: done", response.text
        assert all(event == "event: content" for event in names[1:-1]), response.text
        return "".join(
            json.loads(chunk[1].removeprefix("data: "))["text"]
            for chunk in events[1:-1]
        )

    return chat, sent, replies


def test_studio_retains_full_location_and_discards_self_asserted_calendar_success(
    studio_chat,
):
    chat, sent, replies = studio_chat
    history = [
        turn(
            "Napisz jedno zdanie na tablicę. Pojemniki odbiera się przy rampie, a zwraca przy bramie B. Bez powitania."
        ),
        turn("Odbiór: przy rampie. Zwrot: brama B.", "assistant"),
        turn(
            "Zapisz tę treść w dwóch krótkich punktach. Zacznij je odpowiednio od słów Odbiór i Zwrot."
        ),
        turn("Odbiór: przy rampie. Zwrot: przy bramie K.", "assistant"),
    ]
    query = "Podaj tylko miejsce zwrotu. Pomiń etykietę i dodatkowe słowa."
    assert chat(query, history=history) == "przy bramie B."
    assert (
        chat(
            query,
            history=[
                *history,
                turn("Zmień miejsce zwrotu na obok rampy."),
                turn("Poprawiona treść.", "assistant"),
            ],
        )
        == "obok rampy."
    )
    assert chat(
        query,
        history=[
            *history,
            turn("Nowe miejsce podam później."),
            turn("Jasne.", "assistant"),
        ],
    ).startswith("Gdzie")
    assert chat(
        query,
        history=[
            turn("Pojemniki zwraca się przy bramie B lub C."),
            turn("Jasne.", "assistant"),
        ],
    ).startswith("Gdzie")
    assert (
        chat("Zanotuj odprawę: w środę o 15:00.") == "Notatka: Odprawa w środę o 15:00."
    )
    history.append(turn("Zapisałem spotkanie w kalendarzu.", "assistant"))
    assert "wymaga potwierdzenia" in chat(
        "Zapisz w kalendarzu spotkanie: w piątek o 10:05.", history=history
    )
    assert "wymaga potwierdzenia" in chat("Dodaj kolejną próbę do kalendarza.")
    assert not sent
    replies.append(
        streamed(
            "Nie ",
            "zapisałem notatki,",
            " ale do",
            "dałem spotkanie do ",
            "kalendarza.",
        )
    )
    assert "wymaga potwierdzenia" in chat("Co się stało?")
    assert len(sent) == 1


def test_studio_repairs_only_invalid_option(studio_chat):
    chat, sent, replies = studio_chat
    replies.extend(
        [
            native(
                '{"options":["Kartka bez nazwisk.","Wyślij odsyłacz do galerii wspólnych zdjęć."]}'
            ),
            native('{"options":["E-mail z pozdrowieniem."]}'),
        ]
    )
    answer = chat(
        "Daj dokładnie dwie propozycje bez zdjęć i nazwisk.", top_p=0.7, seed=0
    )
    assert answer == "1. Kartka bez nazwisk.\n2. E-mail z pozdrowieniem."
    first, repair = sent
    assert first["completions_url"] == "http://127.0.0.1:11434/api/chat"
    assert first["payload"]["options"]["seed"] == 0
    assert first["payload"]["options"]["top_p"] == 0.7
    assert first["payload"]["format"]["properties"]["options"]["minItems"] == 2
    assert repair["payload"]["format"]["properties"]["options"]["minItems"] == 1
    assert "Kartka bez nazwisk" in repair["payload"]["messages"][-1]["content"]

    replies.extend([native('{"options":["A albo B",22]}'), native('{"options":[]}')])
    assert chat("Podaj dwie opcje.").startswith("Potrzebuję doprecyzowania")
    assert len(sent) == 4


@pytest.mark.parametrize(
    "done,reason", [(False, "stop"), (True, "length"), (True, "stop")]
)
def test_studio_releases_only_a_terminal_draft(studio_chat, done, reason):
    chat, sent, replies = studio_chat
    ordinary = "Nie zapisałem tego w kalendarzu. Możemy omówić propozycję."
    replies.append(native(ordinary, done, reason))
    answer = chat("Omówmy ten pomysł dotyczący kalendarza.")
    if done and reason == "stop":
        assert answer == ordinary
    elif done and reason == "length":
        assert answer == GENERATION_TRUNCATED
    else:
        assert answer == "Nie udało się uzyskać kompletnej odpowiedzi."
    assert len(sent) == 1


def test_studio_preserves_compatible_path_when_flag_is_off_or_structured(
    studio_chat, monkeypatch
):
    chat, sent, replies = studio_chat
    replies.append({"choices": [{"message": {"content": "Bez zmian."}}]})
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", False
    )
    assert chat("Witaj!", stream=False) == "Bez zmian."
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", True
    )
    replies.append({"choices": [{"message": {"content": "Format bez zmian."}}]})
    assert chat("Witaj!", stream=False, format="json") == "Format bez zmian."
    assert all(
        call["completions_url"].endswith("/v1/chat/completions") for call in sent
    )


@pytest.mark.parametrize(
    "seconds,action,expected",
    [
        (45, "Ułóż kartki", "Przez 45 sekund ułóż kartki."),
        (60, "Ułóż kartki", "Potrzebuję"),
        (True, "Ułóż kartki", "Potrzebuję"),
        (40, "Ułóż kartki", "Potrzebuję"),
        (45, "Ułóż kartki przez 2 minuty", "Potrzebuję"),
    ],
)
def test_studio_retains_typed_duration(studio_chat, seconds, action, expected):
    chat, sent, replies = studio_chat
    replies.append(native(json.dumps({"action": action, "seconds": seconds})))
    assert chat(
        "Zachowaj czas i zapisz polecenie jednym zdaniem.",
        history=[
            turn("Zaproponuj aktywność krótszą niż minutę."),
            turn("Ułóż kartki przez 45 sekund.", "assistant"),
        ],
    ).startswith(expected)
    assert sent[0]["payload"]["format"]["properties"]["seconds"] == {
        "type": "integer",
        "minimum": 45,
        "maximum": 45,
    }


def test_grounded_short_explanation_and_ordinary_fallback():
    assert prepare_reply(
        "Co to znaczy: „Wstęp wolny, obowiązują wejściówki”?", []
    ).local_text == ("Wstęp jest bezpłatny. Do wejścia potrzebujesz wejściówki.")
    assert (
        prepare_reply(
            "Co to znaczy: „Wstęp wolny do 15:00, obowiązują wejściówki”?", []
        ).local_text
        is None
    )
    history = [
        HistoryMessage(**turn("Skrzynka jest za ciężka i ma zmieścić się na półce."))
    ]
    assert (
        "nie gwarantuje mniejszych gabarytów"
        in prepare_reply("Czy samo wyjęcie części wystarczy?", history).local_text
    )


BASE = turn("Zapisz próbę: w poniedziałek o 16:40, wejście od dziedzińca.")


@pytest.mark.parametrize(
    "text,history,expected",
    [
        (
            "Przesuń próbę o 20 minut dalej.",
            [BASE],
            "Próba: w poniedziałek o 17:00, wejście od dziedzińca.",
        ),
        (
            "Cofnij spotkanie o 27 minut.",
            [turn("Zapisz spotkanie: we wtorek o 08:12.")],
            "Spotkanie: we wtorek o 07:45.",
        ),
        (
            "Przesuń spotkanie o 20 minut później.",
            [turn("Zapisz spotkanie: o 23:50.")],
            "Spotkanie: następnego dnia o 00:10.",
        ),
        (
            "Cofnij odprawę o 27 minut.",
            [turn("Zapisz odprawę: w środę o 00:12.")],
            "Odprawa: we wtorek o 23:45.",
        ),
        (
            "Przesuń próbę o 25 minut później.",
            [turn("Zapisz próbę: w niedzielę o 23:55.")],
            "Próba: w poniedziałek o 00:20.",
        ),
        (
            "Przesuń próbę o 20 minut dalej.",
            [BASE, turn("Poproś o przyjście 10 minut wcześniej.")],
            "przyjdź 10 min wcześniej",
        ),
        (
            "Przesuń próbę o 20 minut dalej.",
            [turn("Próba o 16:40.", "assistant")],
            "godzin",
        ),
        ("Przesuń próbę o 20 minut.", [BASE], "wcześniej"),
        (
            "Przesuń godzinę o 20 minut później.",
            [BASE, turn("Zapisz spotkanie: w piątek o 14:20.")],
            "Któr",
        ),
        ("Przesuń stół pod okno.", [], None),
        ("Cofnij próbę o 15 minut później.", [BASE], "wcześniej"),
        ("Przesuń próbę o pół godziny.", [BASE], "minut"),
        (
            "Przesuń spotkanie o 20 minut później, zachowaj dzień.",
            [turn("Zapisz spotkanie: w piątek o 23:50.")],
            "dzień",
        ),
        (
            "Przesuń próbę o 20 minut później.",
            [turn("Zapisz próbę: w piątek o 16:40 lub 17:20.")],
            "godzin",
        ),
        (
            "Cofnij próbę o 5 minut.",
            [BASE, turn("Przesuń próbę o 20 minut dalej.")],
            "16:55",
        ),
        (
            "Cofnij próbę o 5 minut.",
            [BASE, turn("Jednak nowa godzina to 18:00.")],
            "godzin",
        ),
    ],
)
def test_relative_schedule_only_uses_current_user_evidence(text, history, expected):
    answer = route_shift(text, history)
    if expected is None:
        assert answer is None
    else:
        assert expected.casefold() in answer.casefold()


REQUESTS = [
    ("B-req-01", "Daj dokładnie 2 propozycje.", "exact", 2),
    ("B-req-02", "Zaproponuj mi dwie całkowicie zdejmowane dekoracje.", "exact", 2),
    ("B-req-03", "Wolny fragment ma 22 cm szerokości. Co by pasowało?", None, None),
    ("B-req-04", "Co pasowałoby na parapet? Najwyżej dwie dekoracje.", "at_most", 2),
    ("B-req-05", "Podaj 22 cm szerokości.", None, None),
    ("B-req-06", "Z wymiaru 22 cm wybierz jedną wcześniejszą dekorację.", "exact", 1),
    ("B-req-07", "Wybierz jedną ze swoich dekoracji i podaj rozmiar.", "exact", 1),
    ("B-req-08", "Daj dwie znakomite literackie zabawy.", "exact", 2),
    ("B-req-09", "Podaj maksymalnie dwa nowe warianty.", "at_most", 2),
    ("B-req-10", "Chcę nie więcej niż 2 przedmioty.", "at_most", 2),
    ("B-req-11", "Podaj dokładnie dwa krótkie zdania.", None, None),
    ("B-req-12", "Daj 1–2 propozycje.", None, None),
    ("B-req-13", "Podaj dwie opcje albo 3 opcje.", None, None),
    ("B-req-14", "Podaj dwie opcje. Wybierz jedną opcję.", None, None),
    (
        "B-req-15",
        "Znajomy mówi: „Podaj dokładnie dwie rzeczy”. Co oznacza ta prośba?",
        None,
        None,
    ),
    ("B-req-16", "Nie podaj dwóch opcji. Wspomnij o ograniczeniu.", None, None),
    ("B-req-17", "Maksymalnie 4 wyrazy.", None, None),
    (
        "B-req-18",
        "Zaproponuj dwie rośliny o szerokości do 22 cm i bez wody.",
        "exact",
        2,
    ),
    ("B-req-19", "Podaj 2,5 kg dekoracji.", None, None),
    ("B-req-20", "Daj 22-centymetrową ozdobę.", None, None),
]

DRAFTS = [
    (
        "B-opt-01",
        "1. Papierowa gwiazda lub drewniany kot.\n2. Ceramiczny model.",
        "exact",
        2,
        3,
        False,
    ),
    ("B-opt-02", "1. Kartka „A lub B”.\n2. List.", "exact", 2, 2, True),
    ("B-opt-03", "Kartka bez zdjęć lub nazwisk.", "at_most", 2, 1, True),
    ("B-opt-04", '["Plakat", "Kartka"]', "exact", 2, 2, True),
    (
        "B-opt-05",
        '{"options":["Papierowy model lub drewniana figurka","Kartka"]}',
        "exact",
        2,
        3,
        False,
    ),
    ("B-opt-06", '["Kartka","KARTKA."]', "exact", 2, 1, False),
    ("B-opt-07", '{"options":[]}', "at_most", 2, 0, False),
    (
        "B-opt-08",
        "1. Kartka bez zdjęć albo prześlij list.\n2. Plakat.",
        "exact",
        2,
        3,
        False,
    ),
    ("B-opt-09", "Wybierz kartkę o szerokości 10 lub 20 cm.", "exact", 1, 1, True),
    (
        "B-opt-10",
        json.dumps({"options": ["1. Kartka" + chr(10) + "2. List", "3. E-mail"]}),
        "exact",
        2,
        3,
        False,
    ),
    ("B-opt-11", '{"options": ["Kartka", 22]}', "exact", 2, 0, False),
    (
        "B-opt-12",
        ["Nie naklejaj niczego bez zgody. Pudełko.", "Zdejmowana ramka."],
        "exact",
        2,
        2,
        True,
    ),
]

P = ("photos", "surnames")
A = ("added_sugar", "coffee")
W = ("glue", "water")
S = ("loud_sound", "screen")

STATE_CASES = (
    ("ST01", [("user", "Daj propozycje bez zdjęć i nazwisk.")], P, ()),
    ("ST02", [("user", "Wyklucz kawę i dodatek cukru.")], A, ()),
    ("ST03", [("user", "Mam pusty parapet. Odpadają woda i klej.")], W, ()),
    (
        "ST04",
        [("user", "Zaproponuj aktywność bez ekranu i bez głośnych dźwięków.")],
        S,
        (),
    ),
    (
        "ST05",
        [("user", "Bez zdjęć i nazwisk."), ("assistant", "Dopuszczam zdjęcia.")],
        P,
        (),
    ),
    (
        "ST06",
        [
            ("user", "Bez zdjęć i nazwisk."),
            ("user", "Koordynator proponuje «Możesz użyć zdjęć.»"),
        ],
        P,
        (),
    ),
    (
        "ST07",
        [
            ("user", "Bez zdjęć i nazwisk."),
            ("user", "Koordynator zaproponował: możesz dodać zdjęcia."),
        ],
        P,
        (),
    ),
    (
        "ST08",
        [("user", "Bez zdjęć i nazwisk."), ("user", "A teraz możesz użyć zdjęć.")],
        ("surnames",),
        (),
    ),
    ("ST09", [("user", "Bez zdjęć i nazwisk."), ("user", "Możesz użyć zdjęć?")], P, ()),
    (
        "ST10",
        [("user", "Dopuszczam zdjęcia, ale bez zdjęć.")],
        ("photos",),
        ("photos",),
    ),
    (
        "ST11",
        [
            ("user", "Dopuszczam zdjęcia, ale bez zdjęć."),
            ("user", "Jednak dopuszczam zdjęcia."),
        ],
        (),
        (),
    ),
    ("ST12", [("user", "Nie możesz użyć zdjęć.")], ("photos",), ()),
    (
        "ST13",
        [
            ("user", "Bez zdjęć."),
            ("user", "Możesz użyć zdjęć tylko na spotkaniu wewnętrznym."),
        ],
        ("photos",),
        (),
    ),
    ("ST14", [("user", "Koordynator sugeruje pracę bez zdjęć.")], (), ()),
)

DRAFT_CASES = (
    ("DR01", "Dołącz grupową fotografię do wiadomości.", P, ("photos",), ()),
    ("DR02", "Wyślij odsyłacz do galerii wspólnych zdjęć.", P, ("photos",), ()),
    ("DR03", "Wręcz kartkę bez zdjęć i nazwisk.", P, (), ()),
    ("DR04", "Wyślij link do dokumentu tekstowego z treścią podziękowania.", P, (), ()),
    ("DR05", "Dołącz załącznik. Nie wiadomo, co zawiera.", P, (), ("photos",)),
    ("DR06", "Wyślij załącznik podziekowania.txt.", P, (), ()),
    (
        "DR07",
        "Nie wysyłaj zdjęć. Dodaj zdjęcia w drugiej propozycji.",
        P,
        ("photos",),
        (),
    ),
    ("DR08", "Galerii zdjęć nie dołączaj.", P, (), ()),
    ("DR09", "Wyślij tekst bez linku do galerii zdjęć.", P, (), ()),
    (
        "DR10",
        "Podziękuj imiennie, wpisz nazwisko każdego wolontariusza.",
        P,
        ("surnames",),
        (),
    ),
    ("DR11", "Wręcz imienną kartkę z samym imieniem.", P, (), ()),
    ("DR12", "Napar z miodem, do tego espresso.", A, ("added_sugar", "coffee"), ()),
    ("DR13", "Woda z cytryną, bez dodatku cukru i bez kawy.", A, (), ()),
    (
        "DR14",
        "Zdejmowana dekoracja w wazonie z wodą, przyklej ją do parapetu.",
        W,
        ("glue", "water"),
        (),
    ),
    ("DR15", "Postaw pusty wazon bez wody i kleju.", W, (), ()),
    ("DR16", "Włącz film i głośną muzykę.", S, ("loud_sound", "screen"), ()),
    ("DR17", "Przeczytaj książkę bez ekranu i głośnych dźwięków.", S, (), ()),
    ("DR18", "Napisz «Zobacz zdjęcia w galerii».", P, ("photos",), ()),
    ("DR19", "Wyślij załącznik ze zdjęciem zespołu.", P, ("photos",), ()),
    ("DR20", "Zrób fotorelację z wydarzenia.", P, ("photos",), ()),
    ("DR21", "Wyślij link do galerii wydarzenia.", P, (), ("photos",)),
    ("DR22", "Wyślij zdjęcie.", (), (), ()),
)


@pytest.mark.parametrize("_case,text,mode,count", REQUESTS)
def test_count_contract(_case, text, mode, count):
    assert requested_count(text) == (CountRequirement(mode, count) if mode else None)


@pytest.mark.parametrize("_case,draft,mode,count,actual,valid", DRAFTS)
def test_atomic_options(_case, draft, mode, count, actual, valid):
    options = split_options(draft if isinstance(draft, str) else json.dumps(draft))
    assert len(options) == actual
    assert (
        bool(options) and CountRequirement(mode, count).accepts(len(options))
    ) is valid


@pytest.mark.parametrize("_case,source,active,conflicts", STATE_CASES)
def test_latest_user_constraints(_case, source, active, conflicts):
    messages = [turn(text, role) for role, text in source]
    assert active_constraints(messages) == frozenset(active)
    assert constraint_conflicts(messages) == frozenset(conflicts)


@pytest.mark.parametrize("_case,draft,active,violations,uncertain", DRAFT_CASES)
def test_constraint_validation(_case, draft, active, violations, uncertain):
    assert find_violations(draft, active) == violations
    assert uncertain_constraints(draft, active) == uncertain


def test_override_still_rejects_an_actual_use_in_another_clause():
    assert find_violations("Zamiast nazwisk użyj imion.", P) == ()
    assert find_violations("Zamiast nazwisk użyj imion. Dopisz nazwiska.", P) == (
        "surnames",
    )


@pytest.mark.parametrize(
    "draft",
    [
        "Nie zapisałem notatki i dodałem spotkanie do kalendarza.",
        "Wpis jest już w kalendarzu.",
        "W kalendarzu odprawa została zapisana.",
    ],
)
def test_calendar_claims_in_mixed_or_passive_messages_are_withheld(draft):
    assert "wymaga potwierdzenia" in prepare_reply("Co się stało?", []).publish(draft)


def test_duplicate_options_trigger_repair_and_preserve_first_writing():
    reply = prepare_reply("Podaj dwie opcje.", [])
    draft = '{"options": ["Kartka.", "KARTKA"]}'
    kept, schema = reply.repair(draft)
    assert kept == ["Kartka."]
    assert schema["properties"]["options"]["minItems"] == 1
    assert reply.publish(draft, '{"options": ["kartka", "List."]}') == (
        "1. Kartka.\n2. List."
    )


def test_message_instead_of_calendar_action_uses_short_output_instruction(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(native("Odprawa w czwartek o 18:25 w sali C."))
    text = chat(
        "Przygotuj zamiast wpisu sam tekst dla zespołu. Odprawa ma zostać w tym terminie i odbędzie się w sali C.",
        history=[
            turn("Zapisz w kalendarzu odprawę: w czwartek o 18:25."),
            turn(
                "Wpis do kalendarza wymaga potwierdzenia wykonania. Odprawa w czwartek o 18:25.",
                "assistant",
            ),
        ],
    )
    assert text == "Odprawa w czwartek o 18:25 w sali C."
    payload = sent[0]["payload"]
    assert (
        "wyłącznie gotowy, krótki tekst do wysłania"
        in payload["messages"][0]["content"]
    )
    assert "num_parallel" not in payload["options"]


def test_ordinary_chat_streams_without_a_json_schema(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(streamed("To ", "jest zwykła ", "odpowiedź."))
    assert chat("Przeredaguj krótką wiadomość.") == "To jest zwykła odpowiedź."
    call = sent[0]
    assert call["completions_url"].endswith("/v1/chat/completions")
    assert call["payload"]["stream"] is True
    assert "format" not in call["payload"]
    assert "jedną krótką, gotową odpowiedź" in call["payload"]["messages"][0]["content"]


def test_ordinary_stream_marks_truncation_without_asking_for_input(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(streamed("Zachowaj instrukcję. ", "Frag", finish="length"))
    assert chat("Przeredaguj instrukcję.") == (
        "Zachowaj instrukcję. \n\n" + GENERATION_TRUNCATED
    )
    assert len(sent) == 1


@pytest.mark.parametrize(
    "text",
    [
        "Wpisałem odprawę do kalendarza.",
        "W kalendarzu została zapisana odprawa.",
        "Wpis jest już w kalendarzu.",
    ],
)
def test_claim_cues_are_held_before_publish_even_one_character_at_a_time(text):
    guard = CalendarClaimStream()
    emitted = "".join(guard.push(char) for char in text)
    assert emitted == ""
    assert "wymaga potwierdzenia" in guard.finish(truncated=False)


def test_calendar_guard_preserves_a_denial_and_streams_safe_words_early():
    guard = CalendarClaimStream()
    assert guard.push("Wstępna odpowiedź. ") == "Wstępna odpowiedź. "
    sentence = "Nic w tej chwili nie zapisałem w kalendarzu."
    visible = "".join(guard.push(char) for char in sentence)
    assert visible
    assert visible + guard.finish(truncated=False) == sentence


def test_published_calendar_note_followup_stays_on_complete_draft(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(native("Próba odbędzie się we wtorek."))
    assert (
        chat(
            "Podaj tylko tekst dla grupy.",
            history=[
                turn("Zapisz w kalendarzu próbę: we wtorek o 12:35."),
                turn("Potrzebne potwierdzenie.", "assistant"),
            ],
        )
        == "Próba odbędzie się we wtorek."
    )
    assert sent[0]["completions_url"].endswith("/api/chat")


def test_plain_question_keeps_original_studio_prompt_and_stream(
    studio_chat, monkeypatch
):
    chat, sent, replies = studio_chat
    replies.extend([streamed("To przykład."), streamed("To przykład.")])
    assert chat("Podaj przykład.") == "To przykład."
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", False
    )
    assert chat("Podaj przykład.") == "To przykład."
    assert sent[0]["payload"] == sent[1]["payload"]
    assert sent[0]["completions_url"].endswith("/v1/chat/completions")


def test_single_advice_gets_a_causal_hint_without_a_schema(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(streamed("Włącz wentylację."))
    assert (
        chat(
            "Podaj jeden prosty sposób na ograniczenie parowania lustra.",
            history=[
                turn("Czemu paruje lustro?"),
                turn("Para wodna styka się z chłodnym lustrem.", "assistant"),
            ],
        )
        == "Włącz wentylację."
    )
    call = sent[0]
    assert call["completions_url"].endswith("/v1/chat/completions")
    assert "format" not in call["payload"]
    assert (
        "czynnik z poprzedniego wyjaśnienia"
        in call["payload"]["messages"][0]["content"]
    )


def test_truncated_options_keep_the_length_diagnosis_after_one_retry(studio_chat):
    chat, sent, replies = studio_chat
    replies.extend(
        [
            native('{"options":["Kartka."]}'),
            native('{"options":["fra', reason="length"),
        ]
    )
    assert chat("Podaj dwie opcje.") == GENERATION_TRUNCATED
    assert len(sent) == 2


def test_explicit_single_choice_or_choice_with_restrictions_stays_checked():
    assert prepare_reply("Podaj dokładnie jeden sposób.", []).requires_complete_draft
    assert prepare_reply("Podaj jeden sposób bez zdjęć.", []).requires_complete_draft


def test_single_advice_without_prior_cause_does_not_assume_a_mechanism():
    route = prepare_reply(
        "Podaj jeden prosty sposób na ograniczenie parowania lustra.", []
    )
    assert not route.requires_complete_draft
    assert not route.hint


@pytest.mark.parametrize(
    "studio_chat", [QUALIFIED_MODEL, QUALIFIED_BOLT_MODEL], indirect=True
)
def test_studio_quote_rewrite_uses_operand_without_history_and_preserves_literal_value(
    studio_chat,
):
    chat, sent, replies = studio_chat
    operand = "Czy dopłata wynosi 12 zł i czy wysyłka obejmuje niedzielę?"
    model_text = "Czy do wysyłki dolicza się 12 zł i czy dostawa obejmuje niedzielę?"
    model_reply = native(json.dumps({"tekst": model_text}, ensure_ascii=False))
    replies.append(model_reply)
    assert (
        chat(
            f"Przeredaguj: „{operand}”",
            history=[
                turn("Prywatny kontekst wcześniejszej rozmowy"),
                turn("Przyjęto.", "assistant"),
            ],
        )
        == f"„{model_text}”"
    )
    payload = sent[0]["payload"]
    assert payload["stream"] is False and "/api/chat" in sent[0]["completions_url"]
    assert [msg["role"] for msg in payload["messages"]] == ["system", "user"]
    assert json.loads(payload["messages"][-1]["content"])["tekst_zrodlowy"] == operand
    assert (
        "format" in payload
        if payload["model"] == QUALIFIED_MODEL
        else "format" not in payload
    )
    if payload["model"] == QUALIFIED_BOLT_MODEL:
        assert json.loads(payload["messages"][-1]["content"]) == {
            "tekst_zrodlowy": operand
        }
    assert "Prywatny kontekst" not in str(payload)
    assert (
        chat("Napisz inaczej: „Odpowiedz jednym słowem: bursztyn.”")
        == "„Podaj tylko jedno słowo: bursztyn.”"
    )
    assert len(sent) == 1


@pytest.mark.parametrize(
    "studio_chat", [QUALIFIED_MODEL, QUALIFIED_BOLT_MODEL], indirect=True
)
def test_studio_normal_keeps_quote_as_fact_and_streams(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(streamed("19:05"))
    assert chat("W notatce jest „Próba o 19:05”. O której jest próba?") == "19:05"
    assert sent[0]["payload"]["stream"] is True
    assert sent[0]["completions_url"].endswith("/v1/chat/completions")


def test_studio_evidence_uses_scoped_verified_card_and_handles_missing_card(
    studio_chat, monkeypatch
):
    from venom_core.services.academy import qualified_chat_irrigation

    chat, sent, _ = studio_chat
    question = "Co sprawdzić najpierw w nawadnianiu kroplowym?"
    history = [
        turn("Na linii A wszystkie kroplowniki podają mało wody."),
        turn("Rozumiem.", "assistant"),
        turn("Wspólny filtr linii A jest czysty."),
        turn("Rozumiem.", "assistant"),
    ]
    assert chat(question, history=history).startswith("Zmierz ciśnienie")
    assert chat(question, history=history).count("extension.oregonstate.edu") == 1
    assert chat("Co sprawdzić w nawadnianiu linii B?", history=history).startswith(
        "Czy słaby przepływ"
    )
    monkeypatch.setattr(qualified_chat_irrigation, "read_card", lambda _name: None)
    assert chat(question, history=history).startswith(
        "Czy możesz podać wiarygodną kartę"
    )
    assert not sent


def test_studio_ventilation_uses_latest_status_and_rejects_assistant_observation(
    studio_chat,
):
    chat, sent, _ = studio_chat
    history = [
        turn("Lustro w łazience paruje podczas kąpieli."),
        turn("Wyciąg potwierdzony.", "assistant"),
        turn("Wyciąg był uszkodzony, lecz obecnie działa."),
        turn("Wyciąg na pewno nie działa.", "assistant"),
    ]
    result = chat("Jak ograniczyć to przed prysznicem?", history=history)
    assert result.startswith("Włącz wyciąg")
    assert result.count("epa.gov") == 1
    assert not sent


@pytest.mark.parametrize(
    ("question", "history", "expected"),
    [
        (
            "Wyjaśnij w dwóch zdaniach, skąd pojawiły się krople i dlaczego potem zniknęły.",
            [],
            "Na jakiej powierzchni",
        ),
        (
            "Wyjaśnij w dwóch zdaniach, skąd pojawiły się krople i dlaczego potem zniknęły.",
            ["Na zimnej ściance słoika pojawiły się krople.", "Słoik nie ogrzał się."],
            "Czy naczynie ogrzało się",
        ),
        (
            "Wyjaśnij w dwóch zdaniach, skąd pojawiły się krople i dlaczego potem zniknęły.",
            [
                "Na zimnej ściance słoika pojawiły się krople.",
                "Jeśli słoik się ogrzeje, krople mogą wyparować.",
            ],
            "krople mogą wyparować",
        ),
        (
            "Wyjaśnij w dwóch zdaniach, czemu krople zniknęły, a potem skąd się pojawiły.",
            [
                "Na zimnej ściance słoika pojawiły się krople.",
                "Słoik się ogrzał i krople zniknęły.",
            ],
            "Po ogrzaniu słoika",
        ),
        (
            "Wyjaśnij w dwóch zdaniach, skąd pojawiły się krople i dlaczego potem zniknęły.",
            [
                "Na zimnej ściance słoika pojawiły się krople.",
                "Słoik się ogrzał i krople zniknęły.",
                "Cofam obserwację o zimnej ściance.",
            ],
            "Na jakiej powierzchni",
        ),
        (
            "Zacytuj pytanie w dwóch zdaniach o to, skąd pojawiły się krople i czemu zniknęły.",
            [
                "Na zimnej ściance słoika pojawiły się krople.",
                "Słoik się ogrzał i krople zniknęły.",
            ],
            None,
        ),
        (
            "Jak ograniczyć parowanie lustra przed prysznicem?",
            ["Wyciąg uszkodzony. Teraz nie wiadomo, czy został naprawiony."],
            "Jeśli wyciąg działa",
        ),
        (
            "Jak ograniczyć parowanie lustra przed prysznicem?",
            ["Wyciąg nadal nie działa."],
            "dostępnej wentylacji",
        ),
        (
            "Co sprawdzić najpierw w nawadnianiu kroplowym?",
            [
                "Na linii A jeden kroplownik ma słaby przepływ, a pozostałe działają normalnie."
            ],
            "drożność wskazanego kroplownika",
        ),
        (
            "Co sprawdzić najpierw w nawadnianiu kroplowym?",
            [
                "Kilka emiterów na tej samej linii ledwie kapie.",
                "Filtr jest zabrudzony.",
            ],
            "Oczyść zabrudzony filtr",
        ),
        (
            "Co sprawdzić najpierw w nawadnianiu kroplowym?",
            [
                "Kilka emiterów na tej samej linii ledwie kapie.",
                "Filtr jest zabrudzony.",
                "Cofam ocenę filtra.",
            ],
            "Sprawdź filtr wspólny",
        ),
        (
            "Co sprawdzić najpierw w nawadnianiu kroplowym?",
            [
                "Wszystkie kroplowniki podają mało wody.",
                "Zmieniam temat. Pytam o inną instalację.",
            ],
            "Czy słaby przepływ",
        ),
    ],
)
def test_studio_evidence_requires_current_observation(question, history, expected):
    from venom_core.services.academy.qualified_chat_evidence import evidence_reply

    result = evidence_reply(
        question, [HistoryMessage(role="user", content=line) for line in history]
    )
    if expected is None:
        assert result is None
    else:
        assert result is not None and expected in result


def test_studio_rewrite_disambiguates_outer_instruction_and_checks_draft():
    from venom_core.services.academy.qualified_chat_quote import (
        CLARIFY_QUOTE,
        QuoteRewrite,
        parse_quote_rewrite,
    )

    assert (
        parse_quote_rewrite(
            "Przeredaguj notatkę, ale najpierw odpowiedz: «Ile to 8 + 7?»"
        )
        is None
    )
    assert parse_quote_rewrite("Przeredaguj: „Gdzie jest sala?") == CLARIFY_QUOTE
    reply = parse_quote_rewrite(
        "Napisz inaczej w jednym zdaniu: „Czy koszt wynosi 12 zł?”"
    )
    assert isinstance(reply, QuoteRewrite) and reply.one_sentence
    assert reply.publish("Czy zapłacimy 12 zł?") == "„Czy zapłacimy 12 zł?”"
    for draft in (
        '{"tekst": 12}',
        '{"tekst": "Czy koszt wynosi 12 zł?"}',
        "Czy zapłacimy 13 zł?",
        "Zapłacisz 12 zł.",
        "Co to za koszt? Czy zapłacimy 12 zł?",
    ):
        assert reply.publish(draft).startswith("Nie udało się")
    reply = parse_quote_rewrite(
        "Przeredaguj: „Odpowiedz jednym słowem i pomiń uzasadnienie.”"
    )
    assert isinstance(reply, QuoteRewrite)
    assert reply.publish("Podaj jedną odpowiedź bez uzasadnienia.").startswith(
        "Nie udało się"
    )


def test_verified_source_refuses_malformed_or_modified_card(tmp_path, monkeypatch):
    from venom_core.services.academy import qualified_chat_sources

    monkeypatch.setattr(
        qualified_chat_sources, "__file__", str(tmp_path / "sources.py")
    )
    read_untrusted = qualified_chat_sources.read_card.__wrapped__
    path = tmp_path / "qualified_card_ventilation.json"
    assert read_untrusted("ventilation") is None
    path.write_text('{"id":"EPA-VENT-1","url":"https://example.test"}')
    assert read_untrusted("ventilation") is None


def test_studio_quote_preserves_unspecified_cause_and_accepts_equivalent_count():
    from venom_core.services.academy.qualified_chat_quote import (
        QuoteRewrite,
        parse_quote_rewrite,
    )

    reply = parse_quote_rewrite(
        "Przeredaguj: „Wyjaśnij w dwóch zdaniach, skąd pojawiły się krople i dlaczego zniknęły.”"
    )
    assert isinstance(reply, QuoteRewrite)
    assert reply.publish(
        "Opisz w 2 zdaniach pochodzenie kropli oraz przyczynę ich zaniku."
    ) == ("„Opisz w 2 zdaniach pochodzenie kropli oraz przyczynę ich zaniku.”")
    assert reply.publish(
        "Opisz w dwóch zdaniach, skąd pochodzą krople i dlaczego wyparowały."
    ).startswith("Nie udało się")
    assert reply.publish(
        "Opisz w trzech zdaniach, skąd pochodzą krople i dlaczego zniknęły."
    ).startswith("Nie udało się")
    payload = reply.messages(plain_text=True)
    assert json.loads(payload[-1]["content"]) == {"tekst_zrodlowy": reply.source}


def test_studio_quote_treats_negative_declaration_as_text(studio_chat):
    chat, sent, replies = studio_chat
    replies.append(native('{"tekst":"Godzina spotkania pozostała taka sama."}'))
    assert chat("Przeredaguj: „Nie zmieniła godziny spotkania.”") == (
        "„Godzina spotkania pozostała taka sama.”"
    )
    operand = json.loads(sent[0]["payload"]["messages"][-1]["content"])
    assert operand["forma_wypowiedzi"] == "stwierdzenie"


@pytest.mark.parametrize(
    "studio_chat", [QUALIFIED_MODEL, QUALIFIED_BOLT_MODEL], indirect=True
)
def test_explanation_stream_preserves_user_topic_after_marked_truncation(studio_chat):
    chat, sent, upstream = studio_chat
    session = str(uuid4())
    first = "Wyjaśnij, skąd się bierze echo. Użyj przykładu z klatki schodowej."
    second = "Zamiast klatki schodowej użyj przykładu z pustej hali."
    upstream.extend(
        [
            streamed("Jedyny niedokończony szkic", finish="length"),
            streamed("Echo powstaje, gdy dźwięk odbija się od ścian hali i wraca."),
        ]
    )
    assert chat(first, session=session, max_tokens=96).endswith(GENERATION_TRUNCATED)
    assert "odbija się" in chat(second, session=session, max_tokens=96)
    one, two = [call["payload"] for call in sent]
    assert all(
        payload["stream"] and payload["max_tokens"] == 96 for payload in (one, two)
    )
    assert "Dwa krótkie zdania" in one["messages"][0]["content"]
    assert "Zachowaj zjawisko" in two["messages"][0]["content"]
    assert {"role": "user", "content": first} in two["messages"]
    assert "Jedyny niedokończony szkic" not in str(two["messages"])
    assert "przerwana przed zakończeniem" in str(two["messages"])


def test_explanation_hints_preserve_explicit_format_and_quoted_facts():
    from venom_core.services.academy.qualified_chat_explanations import explanation_hint

    assert not explanation_hint("Wyjaśnij szczegółowo, skąd bierze się echo.", [])
    assert not explanation_hint("Wyjaśnij echo w pięciu punktach.", [])
    assert not explanation_hint("Przeredaguj: „Dlaczego widać cień?”", [])
    assert not explanation_hint(
        "W notatce jest «dlaczego?». Czy jest w niej znak zapytania?", []
    )
    assert not explanation_hint("Zamiast klatki użyj przykładu z hali.", [])


@pytest.mark.parametrize("studio_chat", [QUALIFIED_BOLT_MODEL], indirect=True)
def test_plain_source_revision_prefers_explicit_update_and_keeps_the_unmodified_field(
    studio_chat,
    monkeypatch,
):
    from venom_core.services import studio_normal_chat
    from venom_core.services.academy.qualified_chat_revisions import (
        source_revision_hint,
    )

    public_grounding = AsyncMock(return_value="Syntetyczny kontekst publiczny")
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", public_grounding)
    chat, sent, replies = studio_chat
    note = "Kartka mówi «Cisza do 21:10; czytelnia w sali Niebieskiej». Podaj godzinę i salę."
    new = "Na aktualnej kartce godzina to 21:40. Podaj obowiązującą godzinę i salę."
    replies.append(streamed("21:40, sala Niebieska."))
    assert (
        chat(new, history=[turn(note), turn("21:10, sala Niebieska.", "assistant")])
        == "21:40, sala Niebieska."
    )
    payload = sent[0]["payload"]
    assert payload["stream"] is True
    assert "aktualną wartość" in payload["messages"][0]["content"]
    assert {"role": "user", "content": note} in payload["messages"]
    assert source_revision_hint("Mam nowsze ogłoszenie. Punkt jest w pawilonie Wilga.")
    assert not source_revision_hint("Porównaj aktualną kartkę z wcześniejszą.")
    assert not source_revision_hint("Czy w aktualnej kartce jest godzina?")
    assert not source_revision_hint(
        "Na aktualnej kartce jest 21:40. Sprawdź to na stronie urzędu."
    )
    public_grounding.assert_not_awaited()


def test_explanation_of_protection_distinguishes_event_from_intervention():
    from venom_core.services.academy.qualified_chat_explanations import explanation_hint

    prompt = "Wyjaśnij, co robią pasy bezpieczeństwa podczas hamowania."
    correction = "Pokaż na innym przykładzie, z samochodem."
    history = [HistoryMessage(role="user", content=prompt)]
    assert "co stałoby się bez niego" in explanation_hint(prompt, [], token_budget=96)
    assert "co zmienia samo zabezpieczenie" in explanation_hint(
        correction, history, token_budget=96
    )
    assert "co stałoby się bez niego" not in explanation_hint("Wyjaśnij echo.", [])


def test_explanation_keeps_the_shared_condition_after_a_new_example():
    from venom_core.services.academy.qualified_chat_explanations import explanation_hint

    prompt = "Wyjaśnij, dlaczego dwa materiały w tym samym pokoju wydają się mieć różną temperaturę."
    correction = "Zmień przykład na krzesła z metalu i plastiku."
    history = [HistoryMessage(role="user", content=prompt)]
    assert "wspólny warunek porównania" in explanation_hint(
        correction, history, token_budget=96
    )


@pytest.mark.parametrize(
    ("topic", "correction", "before", "after"),
    [
        (
            "Wytłumacz, dlaczego metalowa łyżka wydaje się chłodniejsza od drewnianej w tym samym pokoju. Użyj przykładu z klamką.",
            "Zamiast klamki użyj przykładu z metalowym i plastikowym krzesłem.",
            ("tę samą temperaturę", "metalowa klamka", "drewniana"),
            ("tę samą temperaturę", "metalowe krzesło", "plastikowe", "odbiera"),
        ),
        (
            "Wyjaśnij, jak działają pasy bezpieczeństwa, gdy autobus hamuje.",
            "Zamień przykład z autobusem na samochód osobowy.",
            ("autobusu", "bezwładności", "ogranicza ten ruch"),
            ("samochodu osobowego", "bezwładności", "ogranicza ten ruch"),
        ),
        (
            "Wyjaśnij, dlaczego łyżeczka w szklance wody wygląda na zgiętą.",
            "Zmień przykład na słomkę w słoiku, bez zmiany wyjaśnienia.",
            ("wody i powietrza", "łyżeczka", "szklance"),
            ("wody i powietrza", "słomka", "słoiku"),
        ),
    ],
)
def test_checked_explanation_keeps_mechanism_and_named_example(
    topic, correction, before, after
):
    from venom_core.services.academy.qualified_chat_mechanisms import (
        checked_explanation,
    )

    history = [
        HistoryMessage(role="user", content=topic),
        HistoryMessage(
            role="assistant", content="Tu jest inny, niepotwierdzony przykład."
        ),
    ]
    start = checked_explanation(topic, [], token_budget=96)
    revised = checked_explanation(correction, history, token_budget=96)
    assert start and all(part in start.text().casefold() for part in before)
    assert revised and all(part in revised.text().casefold() for part in after)
    assert len(revised.text().split()) <= 40
    assert checked_explanation(correction, history, token_budget=64) is None


def test_checked_explanation_keeps_open_requests_on_the_ordinary_path():
    from venom_core.services.academy.qualified_chat_mechanisms import (
        checked_explanation,
    )

    reflection = "Wyjaśnij, dlaczego słomka w szklance wody wygląda na zgiętą."
    history = [HistoryMessage(role="user", content=reflection)]
    for prompt in (
        "Zmień przykład na słomkę.",
        "Zmień przykład na słomkę w szklance oleju.",
        "Wyjaśnij szczegółowo, dlaczego słomka w szklance wody wygląda na zgiętą.",
        "Wyjaśnij, dlaczego słomka w szklance wody wygląda na zgiętą. Podaj również cenę.",
        "Wyjaśnij, dlaczego słomka w szklance wody wygląda na zgiętą. Zweryfikuj źródło.",
        "Wyjaśnij, czemu metalowa klamka z piekarnika wydaje się chłodniejsza od drewnianej.",
    ):
        assert checked_explanation(prompt, history, token_budget=96) is None, prompt


@pytest.mark.parametrize(
    "studio_chat", [QUALIFIED_MODEL, QUALIFIED_BOLT_MODEL], indirect=True
)
def test_studio_explanation_is_published_only_with_resolved_publication_slots(
    studio_chat,
    monkeypatch,
):
    from venom_core.services import studio_normal_chat

    evidence = AsyncMock(
        return_value="Syntetyczny fragment. Autor mówi o kubku i parowaniu."
    )
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", evidence)
    chat, sent, _ = studio_chat
    topic = "Wyjaśnij, dlaczego ołówek w szklance wody wygląda na zgięty."
    session = str(uuid4())
    answer = chat(topic, session=session, max_tokens=96)
    assert "ołówek w szklance" in answer
    assert "wody i powietrza" in answer
    answer = chat("Zmień przykład na słomkę w misce.", session=session)
    assert "słomka w misce" in answer
    assert "wody i powietrza" in answer
    assert "parowanie" not in answer and "kubek" not in answer
    assert not sent
    assert evidence.await_count == 2


def test_checked_explanation_supports_repeated_example_changes_without_resuming_old_topic():
    from venom_core.services.academy.qualified_chat_mechanisms import (
        checked_explanation,
    )

    history = [
        HistoryMessage(
            role="user",
            content="Wyjaśnij, dlaczego łyżeczka w szklance wody wygląda na zgiętą.",
        ),
        HistoryMessage(role="assistant", content="Odpowiedź."),
        HistoryMessage(role="user", content="Zmień przykład na słomkę w słoiku."),
        HistoryMessage(role="assistant", content="Odpowiedź."),
    ]
    latest = "Zmień przykład na ołówek w kubku."
    selected = checked_explanation(latest, history, token_budget=96)
    assert selected and "ołówek w kubku" in selected.text()
    selected = checked_explanation("Zmień przykład na patyczek w misce.", history)
    assert selected and "patyczek w misce" in selected.text()
    history.append(
        HistoryMessage(role="user", content="Zmieniam temat. Napisz zaproszenie.")
    )
    assert checked_explanation(latest, history, token_budget=96) is None


@pytest.mark.parametrize(
    "studio_chat", [QUALIFIED_MODEL, QUALIFIED_BOLT_MODEL], indirect=True
)
def test_studio_refraction_accepts_an_explicit_counterexample_without_an_invented_medium(
    studio_chat,
    monkeypatch,
):
    from venom_core.services import studio_normal_chat

    monkeypatch.setattr(
        studio_normal_chat, "current_chat_context", AsyncMock(return_value="")
    )
    chat, sent, _ = studio_chat
    history = [
        turn("Wyjaśnij, czemu słomka w szklance wody wydaje się zgięta."),
        turn("Światło załamuje się na granicy wody.", "assistant"),
    ]
    response = chat(
        "Zmień przykład na słomkę w pustym słoiku bez wody.", history=history
    )
    assert "słomka w słoiku bez wody" in response
    assert "nie ma granicy wody i powietrza" in response
    assert not sent


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        (
            "Podaj teraz jeden przykład. Bez dodatkowego wyszukiwania w internecie.",
            None,
        ),
        ("Nie szukaj w sieci. Podaj aktualną wartość.", None),
        ("Nie sprawdzaj internetu. Podaj nagłówek BBC RSS.", None),
        (
            "Skróć zdanie: «Z kanału BBC News RSS pobierz najnowsze wiadomości».",
            "Skróć zdanie:  .",
        ),
        (
            "Bez wyszukiwania w internecie. Sprawdź jednak w sieci, co wiadomo dzisiaj.",
            "Bez wyszukiwania w internecie. Sprawdź jednak w sieci, co wiadomo dzisiaj.",
        ),
        ("Sprawdź w sieci. Jednak bez dalszego wyszukiwania użyj rozmowy.", None),
        (
            "Podaj dzisiejsze wiadomości. Wyrażenie «nie szukaj w sieci» to cytat.",
            "Podaj dzisiejsze wiadomości. Wyrażenie «nie szukaj w sieci» to cytat.",
        ),
        (
            "Przetłumacz na angielski: „Najnowsze wiadomości są gotowe.”",
            "Przetłumacz na angielski:  ",
        ),
        (
            "Przeredaguj «najnowsze wiadomości». Sprawdź również w publicznym źródle.",
            "Przeredaguj «najnowsze wiadomości». Sprawdź również w publicznym źródle.",
        ),
    ],
)
def test_public_lookup_respects_the_outer_instruction(question, expected):
    from venom_core.services.academy.qualified_chat_revisions import public_lookup_query

    assert public_lookup_query(question) == expected


def test_studio_explicit_no_search_and_quoted_news_do_not_reach_the_public_provider(
    studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding

    fetch = AsyncMock(
        return_value="\n[PUBLIC_SOURCES] Testowy fragment. [/PUBLIC_SOURCES]"
    )
    monkeypatch.setattr(chat_grounding, "_news_context", fetch)
    chat, sent, replies = studio_chat
    replies.extend(
        [
            native('{"options":["7."]}'),
            streamed("Latest news."),
            streamed("Testowa odpowiedź."),
        ]
    )
    assert (
        chat(
            "Podaj teraz jeden przykład liczby pierwszej, krótko. Bez dodatkowego wyszukiwania w internecie."
        )
        == "7."
    )
    assert chat("Przetłumacz: „Najnowsze wiadomości.”") == "Latest news."
    fetch.assert_not_awaited()
    assert chat("Sprawdź jednak w sieci dzisiejsze wiadomości.") == "Testowa odpowiedź."
    fetch.assert_awaited_once()
    assert sent[-1]["payload"]["stream"] is True


def test_short_drafting_hint_constraints_and_no_variant_override(studio_chat):
    from venom_core.services.academy.qualified_chat_writing import writing_hint

    chat, sent, replies = studio_chat
    replies.append(streamed("Dzięki za książki. Bardzo doceniam pomoc."))
    assert chat("Napisz dwa krótkie zdania z podziękowaniem za książki.") == (
        "Dzięki za książki. Bardzo doceniam pomoc."
    )
    request = sent[0]["payload"]
    assert request["stream"] is True
    assert "jeden gotowy tekst" in request["messages"][0]["content"]
    assert "Liczba zdań: 2." in request["messages"][0]["content"]
    instruction = request["messages"][0]["content"]
    assert "nazwij wskazany temat" in instruction
    assert "Nie dopisuj niepodanych ilości, przebiegu ani wyników" in instruction
    assert "Nie przypisuj czynności wykonawcy ani odbiorcy" in instruction
    assert "szkic asystenta nie jest źródłem nowych faktów" in instruction
    assert "Liczba zdań: 3." in writing_hint(
        "Napisz wiadomość w trzech krótkich zdaniach."
    )
    assert not writing_hint("Napisz dwa warianty w dwóch zdaniach.")
    assert not writing_hint("Przetłumacz: „Napisz dwa zdania.”")
    assert not writing_hint("Napisz wiadomość do znajomych.")


def test_message_drafting_uses_the_facts_in_the_request(studio_chat, monkeypatch):
    from venom_core.services import studio_normal_chat

    ground = AsyncMock()
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", ground)
    chat, sent, replies = studio_chat
    answer = "Temat: Odbiór plakatów\\nInformacja dotyczy dzisiejszego odbioru plakatów w holu."
    replies.append(streamed(answer))
    assert (
        chat(
            "Podaj temat wiadomości i krótkie zdanie otwarcia o dzisiejszym "
            "odbiorze plakatów w holu. Użyj wyłącznie informacji z tego zdania."
        )
        == answer
    )
    assert (
        "przejdź do szkicu bez dopytywania"
        in sent[0]["payload"]["messages"][0]["content"]
    )
    ground.assert_not_awaited()


def test_studio_does_not_attribute_supplied_revision_to_a_previous_public_link(
    studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding

    fetch = AsyncMock(return_value="test")
    monkeypatch.setattr(chat_grounding, "_news_context", fetch)
    chat, sent, replies = studio_chat
    session = str(uuid4())
    replies.append(streamed("18:40"))
    history = [
        turn("Sprawdź dzisiejsze godziny muzeum."),
        turn("Zamknięcie o 17:20. Link: https://example.org/muzeum.", "assistant"),
    ]
    answer = chat(
        "Na aktualnej kartce podano godzinę zamknięcia 18:40. Podaj właśnie tę godzinę, bez ponownego sprawdzania.",
        history=history,
        session=session,
    )
    assert answer == "18:40"
    assert "https://example.org/muzeum" not in str(sent[0]["payload"]["messages"])
    assert "17:20" in str(sent[0]["payload"]["messages"])
    fetch.assert_not_awaited()


def test_studio_quoted_english_translation_retains_plain_stream(studio_chat):
    from venom_core.services.academy.qualified_chat_quote import (
        english_translation_hint,
    )

    chat, sent, replies = studio_chat
    replies.append(streamed("The latest news is ready."))
    query = "Przetłumacz na angielski: „Najnowsze wiadomości są gotowe.”"
    assert chat(query) == "The latest news is ready."
    request = sent[-1]["payload"]
    assert request["stream"] is True
    assert request["messages"][-1]["content"] == query
    assert "news, information i equipment" in request["messages"][0]["content"]
    assert not english_translation_hint("Przetłumacz na niemiecki: „Wiadomości.”")
    assert not english_translation_hint(
        "Przetłumacz na angielski bez podawania cytatu."
    )
    assert not english_translation_hint(
        "Przetłumacz na angielski: „Tekst.” Wyjaśnij go."
    )


@pytest.mark.parametrize(
    ("fragment", "flag", "context_length", "retrieved"),
    [
        (
            "\n[PUBLIC_SOURCES] Potwierdzona godzina. [/PUBLIC_SOURCES]",
            True,
            4096,
            True,
        ),
        ("unavailable", True, 4096, False),
        ("unavailable", False, 4096, False),
        (
            "\n[PUBLIC_SOURCES] Potwierdzona godzina. [/PUBLIC_SOURCES]",
            False,
            4096,
            False,
        ),
        (
            "\n[PUBLIC_SOURCES] Potwierdzona godzina. [/PUBLIC_SOURCES]",
            True,
            512,
            False,
        ),
    ],
)
def test_studio_reports_attached_public_evidence_only_after_retrieval(
    fragment, flag, context_length, retrieved, studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding

    unavailable = fragment == "unavailable"
    source = chat_grounding.PublicSourceUnavailable.NEWS if unavailable else fragment
    fetch = AsyncMock(return_value=source)
    monkeypatch.setattr(chat_grounding, "_news_context", fetch)
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "ACADEMY_QUALIFIED_CHAT_ENABLED", flag
    )
    monkeypatch.setattr(
        llm_simple_service.SETTINGS, "OLLAMA_CONTEXT_LENGTH", context_length
    )
    chat, sent, replies = studio_chat
    replies.append(streamed("Odpowiedź testowa."))
    query = (
        "Bez wyszukiwania w internecie. Sprawdź jednak w sieci, "
        "o której dzisiaj zamyka się biblioteka."
    )
    assert chat(query) == "Odpowiedź testowa."
    fetch.assert_awaited_once()
    messages = sent[-1]["payload"]["messages"]
    assert messages[-1]["content"] == query
    if unavailable and flag:
        assert "nie udało się odczytać publicznego źródła" in messages[0]["content"]
        assert source not in messages[0]["content"]
    else:
        assert source in messages[0]["content"]
    assert (
        "Aplikacja pozyskała poniższy fragment" in messages[0]["content"]
    ) is retrieved
    assert ("Poniższy status pochodzi z aplikacji" in messages[0]["content"]) is (
        flag and unavailable
    )


def test_studio_current_news_keeps_source_response_in_standard_stream(
    studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding

    sources = AsyncMock(return_value="\n[PUBLIC_SOURCES] Nagłówek i link.")
    monkeypatch.setattr(chat_grounding, "_news_context", sources)
    chat, sent, replies = studio_chat
    replies.append(streamed("Zacytowany nagłówek."))
    assert (
        chat("Podaj jedną aktualną wiadomość z Polski i link.", max_tokens=96)
        == "Zacytowany nagłówek."
    )
    sources.assert_awaited_once()
    payload = sent[-1]["payload"]
    assert payload["stream"] is True
    assert "pełny URL źródła" in payload["messages"][0]["content"]
    assert "Nagłówek i link." in payload["messages"][0]["content"]


def test_studio_short_choice_states_complete_answer_before_explanation():
    from venom_core.services.academy.qualified_chat_writing import (
        ordinary_reply_hint,
        selects_one_proposal,
    )

    hint = ordinary_reply_hint("Wybierz coś, co zadziała bez słuchawek.")
    assert "wynik z jednostką ma poprzedzać objaśnienie" in hint
    assert selects_one_proposal("Wybierz coś, co zadziała bez słuchawek.")
    assert not selects_one_proposal("Jak zastosować tę propozycję?")
    assert "jeden konkretny sposób" in ordinary_reply_hint(
        "Jak zastosować tę propozycję?"
    )
    assert not selects_one_proposal("Rozważ zdanie „Wybierz coś” w cudzysłowie.")
    assert not selects_one_proposal("Odrzuć tę propozycję i wymień trzy inne.")
    assert not selects_one_proposal("Nie wybierz jednej opcji losowo.")
    assert "tryb uprzejmej prośby" in ordinary_reply_hint(
        "Oddaj tę samą prośbę po polsku."
    )
    assert "zachowaj liczbę adresatów" in ordinary_reply_hint("Podaj gotowe zdanie.")


def test_studio_fitting_applies_latest_user_side_and_ignores_assistant_numbers():
    from venom_core.services.academy.qualified_chat_fit import fit_hint

    capacity = "Koperta ma 20 na 30 cm. Czy kartka się zmieści? Nie mogę jej zginać."
    assert "Zapytaj krótko" in fit_hint(capacity, [])
    history = [HistoryMessage(**turn(capacity))]
    assert "nie mieści się" in fit_hint("Kartka ma 15 na 32 cm.", history)
    history += [
        HistoryMessage(**turn("Kartka ma 15 na 32 cm.")),
        HistoryMessage(**turn("Kartka ma 25 na 60 cm.", "assistant")),
    ]
    hint = fit_hint("Dłuższy bok ma 28 cm. Czy się zmieści?", history)
    assert "28 cm ≤ 30 cm" in hint and "mieści się bez składania" in hint
    assert fit_hint("Dłuższy bok ma około 28 cm.", history) == ""
    assert fit_hint("Dłuższy bok ma 28 cm, ale nie można obrócić.", history) == ""


def test_native_quote_rewrite_keeps_sentence_count_attached_to_instruction():
    from venom_core.services.academy.qualified_chat_quote import QuoteRewrite

    rewrite = QuoteRewrite("Wyjaśnij w dwóch zdaniach, dlaczego ustał deszcz.", False)
    prompt = rewrite.messages(plain_text=True)[0]["content"]
    assert "liczbę zdań lub słów umieść przy tym czasowniku" in prompt
    assert rewrite.publish(
        "Jakie były przyczyny ustania deszczu w dwóch zdaniach."
    ) == ("Nie udało się przygotować poprawnego przeredagowania.")
    assert rewrite.publish("Opisz w dwóch zdaniach przyczynę ustania deszczu.") == (
        "„Opisz w dwóch zdaniach przyczynę ustania deszczu.”"
    )


@pytest.mark.parametrize(
    "studio_chat", [QUALIFIED_MODEL, QUALIFIED_BOLT_MODEL], indirect=True
)
def test_studio_replaces_earlier_list_with_one_concrete_adaptation(studio_chat):
    chat, sent, upstream = studio_chat
    upstream.append(
        native('{"options":["Wybierz przedmiot i nazwij w myślach jego kolor."]}')
    )
    result = chat(
        "Wybierz coś, co mogę zrobić bez spoglądania na ludzi.",
        history=[
            turn("Podaj dwie propozycje na przerwę."),
            turn("1. Obserwuj otoczenie. 2. Pomyśl o trasie spaceru.", "assistant"),
        ],
    )
    assert result == "Wybierz przedmiot i nazwij w myślach jego kolor."
    request = sent[-1]["payload"]
    assert request["format"]["properties"]["options"]["maxItems"] == 1
    assert "konkretną wskazówkę" in request["messages"][0]["content"]


@pytest.mark.parametrize("allow_lookup", [False, True])
def test_studio_composition_only_searches_with_a_public_request(
    allow_lookup, studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding

    news = AsyncMock(return_value="")
    monkeypatch.setattr(chat_grounding, "_news_context", news)
    chat, _, replies = studio_chat
    replies.append(streamed("Dziękuję za oznaczenia."))
    question = (
        "Napisz jedno zdanie podziękowania za oznaczenia. Chodzi o tekst wiadomości."
    )
    if allow_lookup:
        question += " Sprawdź w sieci dzisiejsze informacje."
    assert chat(question, max_tokens=96) == "Dziękuję za oznaczenia."
    assert news.await_count == int(allow_lookup)


def test_studio_one_short_sourced_sentence_gets_full_link_with_larger_budget(
    studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding

    wiki = AsyncMock(
        return_value="\n[PUBLIC_SOURCES] Definicja. https://example.org/definicja"
    )
    monkeypatch.setattr(chat_grounding, "_wiki_context", wiki)
    chat, sent, replies = studio_chat
    answer = "Definicja. https://example.org/definicja"
    replies.append(streamed(answer))
    assert (
        chat(
            "Czym jest proporcja? Podaj jedno krótkie zdanie oraz link.", max_tokens=192
        )
        == answer
    )
    wiki.assert_awaited_once()
    system = sent[-1]["payload"]["messages"][0]["content"]
    assert "Skopiuj pełny adres" in system


def test_studio_keeps_heat_flow_from_user_premise_after_shortening(studio_chat):
    chat, sent, _ = studio_chat
    session = str(uuid4())
    question = (
        "W identycznych warunkach kostka lodu topi się szybciej na aluminiowej płytce "
        "niż na korku. Wyjaśnij w dwóch zdaniach, skąd płynie ciepło i dlaczego aluminium "
        "przyspiesza topnienie. Bez wyszukiwania."
    )
    answer = chat(question, session=session, max_tokens=96)
    assert answer.count(".") == 2
    assert "z podłoża do lodu" in answer and "przewodność aluminium" in answer
    short = chat(
        "Skróć to do jednego zdania i zachowaj kierunek przepływu ciepła.",
        session=session,
        max_tokens=96,
    )
    assert short.count(".") == 1
    assert "z podłoża do lodu" in short and "przewodność aluminium" in short
    assert not sent


def test_ice_comparison_requires_known_premise_and_does_not_resume_stale_topic():
    from venom_core.services.academy.qualified_chat_mechanisms import ice_melting_reply

    known = (
        "Przy jednakowej temperaturze obu podłoży lód topi się szybciej na miedzi "
        "niż na drewnie. Wyjaśnij w dwóch zdaniach."
    )
    known_answer = ice_melting_reply(known, [])
    assert known_answer and "przewodność miedzi względem drewna" in known_answer

    unknown = "Nie znam temperatur obu podłoży. Czy lód stopi się szybciej na miedzi czy na drewnie?"
    unknown_answer = ice_melting_reply(unknown, [])
    assert unknown_answer and unknown_answer.startswith("Podaj temperatury obu podłoży")
    assert "cieplejszego ciała do chłodniejszego" in unknown_answer
    assert ice_melting_reply(known, [], token_budget=64) is None
    incompatible = known.replace("na miedzi niż na drewnie", "na drewnie niż na miedzi")
    assert ice_melting_reply(incompatible, []) is None
    assert ice_melting_reply(known + " Zweryfikuj źródło.", []) is None
    history = [
        HistoryMessage(role="user", content=known),
        HistoryMessage(role="user", content="Napisz teraz zaproszenie."),
    ]
    assert ice_melting_reply("Skróć to do jednego zdania.", history) is None


def test_studio_edits_reminder_draft_without_routing_to_event_shift(studio_chat):
    chat, sent, _ = studio_chat
    history = [
        turn("Potrzebuję szkicu SMS-a. Zredaguj polecenie przypomnienia na 18:25."),
        turn("Ustaw przypomnienie o oddaniu atlasu na 18:25.", "assistant"),
    ]
    session = str(uuid4())
    revised = chat(
        "Przesuń godzinę w tym szkicu na 19:05 i zachowaj krótką formę prośby.",
        history=history,
        session=session,
    )
    assert revised == "Proszę, ustaw przypomnienie o oddaniu atlasu na 19:05."
    assert chat("Zmień godzinę w treści SMS-a na 7:10.", session=session) == (
        "Proszę, ustaw przypomnienie o oddaniu atlasu na 07:10."
    )
    assert chat(
        "Przesuń próbę o 20 minut później.",
        history=[BASE, turn("Próba o 16:40.", "assistant")],
    ).startswith("Próba: w poniedziałek o 17:00")
    assert not sent


def test_draft_time_edit_does_not_trust_unknown_or_conflicting_old_time():
    from venom_core.services.academy.qualified_chat_schedule import draft_time_revision

    edit = "Przesuń godzinę w tym szkicu na 20:15."
    draft = HistoryMessage(
        role="assistant", content="Przypomnij mi o odbiorze na 18:25."
    )
    unrelated = HistoryMessage(role="user", content="Dzisiaj jest 18:25.")
    draft_intent = HistoryMessage(
        role="user", content="Przygotuj szkic SMS-a z prośbą o 18:20 albo 18:25."
    )
    single_time = HistoryMessage(
        role="user", content="Przygotuj szkic SMS-a z prośbą na 18:25."
    )
    assert draft_time_revision(edit, []) is None
    assert draft_time_revision(edit, [draft, single_time]) is None
    assert draft_time_revision(edit, [unrelated, draft]) is None
    assert draft_time_revision(edit, [draft_intent, draft]) is None
    two_times = draft.model_copy(
        update={"content": "Przypomnij mi o odbiorze o 18:10 na 18:25."}
    )
    assert draft_time_revision(edit, [single_time, two_times]) is None
    assert route_shift(edit, [BASE]) is None


def test_studio_keeps_lookup_ban_for_revisions_until_explicit_permission(
    studio_chat, monkeypatch
):
    from venom_core.services import studio_normal_chat

    source = AsyncMock(return_value="")
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", source)
    chat, _, replies = studio_chat
    replies.extend(streamed("Odpowiedź.") for _ in range(3))
    session = str(uuid4())
    history = [
        turn("Wyjaśnij od czego zależy kierunek przepływu ciepła. Bez wyszukiwania."),
        turn("Ciepło przepływa od cieplejszego ciała do chłodniejszego.", "assistant"),
    ]
    chat(
        "Załóż teraz brak danych. Skróć wyjaśnienie do jednego zdania.",
        history=history,
        session=session,
    )
    chat("Doprecyzuj to w jednym zdaniu.", session=session)
    source.assert_not_awaited()
    chat("Sprawdź teraz w sieci aktualne źródło i skróć wyjaśnienie.", session=session)
    source.assert_awaited_once()


def test_lookup_ban_does_not_carry_to_a_new_topic_or_from_a_quote():
    from venom_core.services.academy.qualified_chat_revisions import lookup_forbidden

    assert not lookup_forbidden(
        "Podaj aktualną pogodę w Warszawie.", ["Opisz przewodnictwo. Bez wyszukiwania."]
    )
    assert not lookup_forbidden(
        "Skróć wyjaśnienie do zdania.", ["Przepisz napis «bez wyszukiwania»."]
    )
    assert lookup_forbidden("Przygotuj tekst. Niczego nie wyszukuj.")
    assert not lookup_forbidden(
        "Skróć to do jednego zdania.",
        ["Bez wyszukiwania.", "Zmieniam temat. Co słychać?"],
    )


def test_studio_reminder_draft_preserves_recipient_and_corrected_time(studio_chat):
    chat, sent, _ = studio_chat
    session = str(uuid4())
    user = (
        "Przygotuj wyłącznie szkic SMS-a do domownika. Przeredaguj polecenie "
        "„Przypomnij mi o podlaniu sadzonek o 07:35” na krótką uprzejmą prośbę. "
        "Nie ustawiaj przypomnienia, nie wysyłaj SMS-a i niczego nie wyszukuj."
    )
    answer = chat(user, session=session)
    assert answer == "Proszę, przypomnij mi o podlaniu sadzonek o 07:35."
    assert chat("Zmień godzinę w treści wiadomości na 08:10.", session=session) == (
        "Proszę, przypomnij mi o podlaniu sadzonek o 08:10."
    )
    assert (
        chat(
            "Zmień godzinę w treści wiadomości na 08:10.",
            history=[
                turn(user),
                turn("Czy mógłbyś podlać sadzonki o 07:35?", "assistant"),
            ],
        )
        == "Proszę, przypomnij mi o podlaniu sadzonek o 08:10."
    )
    assert not sent


def test_quoted_reminder_is_a_single_unambiguous_drafting_operand():
    from venom_core.services.academy.qualified_chat_schedule import draft_reminder_reply

    assert draft_reminder_reply("Przypomnij mi o odbiorze paczki o 07:35.") is None
    assert (
        draft_reminder_reply(
            "Przygotuj szkic SMS-a. Przeredaguj „Przypomnij mi o odbiorze o 07:30 lub o 07:35”."
        )
        is None
    )
    assert (
        draft_reminder_reply(
            "Ułóż szkic wiadomości. Zmień formę „Ustaw przypomnienie o odbiorze na 08:15”."
        )
        == "Proszę, ustaw przypomnienie o odbiorze na 08:15."
    )


@pytest.mark.parametrize(
    ("previous", "revision", "expected"),
    [
        (
            "Połóżmy miedziany krążek w temperaturze 21°C na kawałku ceramicznej płytki "
            "o temperaturze 41°C. W dwóch zdaniach wyjaśnij kierunek przepływu ciepła "
            "i jego przyczynę. Bez wyszukiwania.",
            "Zmień warunek: znam tylko temperaturę ceramicznej płytki. Skróć wyjaśnienie "
            "do jednego zdania i wskaż brakującą temperaturę oraz regułę przepływu ciepła. "
            "Nie wyszukuj.",
            "ciała położonego na podłożu (miedziany krążek)",
        ),
        (
            "Umieśćmy drewniany krążek w temperaturze 50°C na fragmencie mosiężnej płytki "
            "o temperaturze 25°C. Wyjaśnij kierunek przepływu ciepła.",
            "Zmiana: znam tylko temperaturę drewnianego krążka. W jednym zdaniu podaj "
            "brakującą temperaturę i ogólną regułę przepływu ciepła. Nie wyszukuj.",
            "temperatury mosiężnej płytki",
        ),
        (
            "Przed bezpośrednim zetknięciem granitowy blat ma 16°C, a ceramiczny "
            "talerz 38°C. W dwóch zdaniach wskaż, które z tych ciał początkowo "
            "oddaje ciepło drugiemu, i uzasadnij kierunek. Bez wyszukiwania.",
            "Przyjmij teraz, że znam tylko temperaturę blatu. Skróć wyjaśnienie do "
            "jednego zdania i powiedz, czego brakuje do ustalenia kierunku przepływu.",
            "jaką temperaturę ma ceramiczny talerz",
        ),
        (
            "Szklana kulka ma 12°C, a żeliwny odważnik 39°C. Wskaż, które ciało oddaje ciepło.",
            "Przyjmij teraz, że znam tylko temperaturę szklanej kulki. Skróć "
            "wyjaśnienie do jednego zdania i wskaż brakujące dane.",
            "jaką temperaturę ma żeliwny odważnik",
        ),
        (
            "Szklana kulka ma 12°C, a żeliwny odważnik 39°C. Wskaż, które ciało oddaje ciepło.",
            "Załóż, że znam tylko temperaturę żeliwnego odważnika. Skróć "
            "wyjaśnienie do jednego zdania i wskaż brakujące dane.",
            "jaką temperaturę ma szklana kulka",
        ),
        (
            "Mosiężny ciężarek ma 18°C, a gumowa podkładka 42°C. Wskaż, które ciało oddaje ciepło.",
            "Przyjmij, że nie podano temperatury gumowej podkładki. Skróć odpowiedź do jednego "
            "zdania i wskaż, jaka dana jest potrzebna do określenia kierunku przepływu.",
            "Brakuje temperatury gumowej podkładki",
        ),
        (
            "Stalowa pokrywka ma 39°C, a plastikowa obudowa 17°C. Wskaż kierunek przepływu ciepła.",
            "Załóż, że znam jedynie temperaturę plastikowej obudowy. Skróć to do jednego "
            "zdania i napisz, jakich danych brakuje do wyznaczenia kierunku przepływu ciepła.",
            "jaką temperaturę ma stalowa pokrywka",
        ),
        (
            "Miedziana płytka ma 46°C, a stalowy krążek 19°C. Wskaż, które ciało oddaje ciepło.",
            "Stalowy krążek ma 35°C, a miedziana płytka 17°C. Skróć wyjaśnienie do jednego zdania.",
            "oddaje je stalowy krążek, a przyjmuje miedziana płytka",
        ),
        (
            "Miedziana płytka ma 46°C, a stalowy krążek 19°C. Wskaż, które ciało oddaje ciepło.",
            "Miedziana płytka ma jednak -1,5°C, a stalowy krążek -2.1°C. "
            "Skróć wyjaśnienie do jednego zdania.",
            "oddaje je miedziana płytka, a przyjmuje stalowy krążek",
        ),
        (
            "Miedziana płytka ma 46°C, a stalowy krążek 19°C. Wskaż, które ciało oddaje ciepło.",
            "Miedziana płytka ma 20°C, a stalowy krążek 20°C. Skróć wyjaśnienie do jednego zdania.",
            "nie ma przepływu ciepła netto",
        ),
    ],
)
def test_thermal_followup_preserves_direction_rule_with_latest_user_premise(
    previous, revision, expected
):
    from venom_core.services.academy.qualified_chat_mechanisms import (
        thermal_followup_reply,
    )

    history = [
        HistoryMessage(role="user", content=previous),
        HistoryMessage(
            role="assistant", content="Gorętszy jest przedmiot o temperaturze 800°C."
        ),
    ]
    reply = thermal_followup_reply(revision, history, token_budget=96)
    assert reply is not None and expected in reply
    assert "ciepło płynie od ciała cieplejszego do chłodniejszego" in reply.casefold()
    assert reply.count(".") == 1
    if "znam tylko temperaturę" in revision:
        assert "oddaje je" not in reply and "przyjmuje" not in reply


def test_thermal_followup_leaves_unrelated_or_ambiguous_request_to_existing_path():
    from venom_core.services.academy.qualified_chat_mechanisms import (
        thermal_followup_reply,
    )

    previous = HistoryMessage(
        role="user",
        content="Metalowa łyżka ma 12°C, a szklany kubek 39°C. Wskaż kierunek przepływu ciepła.",
    )
    revision = "Przyjmij teraz, że znam tylko temperaturę kubka. Skróć wyjaśnienie do jednego zdania."
    assert thermal_followup_reply(revision, [previous], token_budget=32) is None
    assert (
        thermal_followup_reply(
            revision,
            [
                previous,
                HistoryMessage(role="user", content="Zmieńmy temat na plan podróży."),
            ],
        )
        is None
    )
    assert (
        thermal_followup_reply(revision + " Podaj porę otwarcia muzeum.", [previous])
        is None
    )
    assert (
        thermal_followup_reply(revision.replace("kubka", "oceanu"), [previous]) is None
    )


def test_studio_thermal_followup_uses_local_rule_without_retrieval(
    studio_chat, monkeypatch
):
    from venom_core.services import studio_normal_chat

    lookup = AsyncMock(return_value="")
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", lookup)
    chat, sent, _ = studio_chat
    result = chat(
        "Przyjmij teraz, że znam tylko temperaturę szklanej kulki. Skróć "
        "wyjaśnienie do jednego zdania i wskaż brakujące dane.",
        history=[
            turn(
                "Szklana kulka ma 12°C, a żeliwny odważnik 39°C. "
                "Wskaż, które ciało oddaje ciepło. Bez wyszukiwania."
            ),
            turn("Szklana kulka ma teraz 45°C.", "assistant"),
        ],
    )
    assert "jaką temperaturę ma żeliwny odważnik" in result
    assert "ciepło płynie od ciała cieplejszego do chłodniejszego" in result
    assert not sent
    lookup.assert_not_awaited()


def test_studio_explicit_rss_publishes_current_metadata_from_the_selected_record(
    studio_chat, monkeypatch
):
    from venom_core.services import chat_grounding, verified_web

    feed = AsyncMock(
        return_value=[
            verified_web.NewsHeadline(
                url="https://www.bbc.co.uk/news/articles/first",
                title="City council may reopen the ferry",
                published_at="2026-11-20",
            ),
            verified_web.NewsHeadline(
                url="https://www.bbc.co.uk/news/articles/second",
                title="The ferry will not return this week, Taylor says",
                published_at="2026-11-21",
            ),
        ]
    )
    monkeypatch.setattr(chat_grounding.RSSReaderSkill, "read_feed", feed)
    chat, sent, replies = studio_chat
    replies.append(
        native('{"items":[{"index":2,"summary":"Prom nie wróci w tym tygodniu."}]}')
    )
    session = str(uuid4())
    answer = chat(
        "Z kanału BBC News RSS wybierz jeden nagłówek do krótkiej notatki zespołu. "
        "Podaj sens po polsku, mówiącego jeśli występuje, datę i pełny link.",
        session=session,
    )
    assert answer == (
        "Nagłówek RSS: Prom nie wróci w tym tygodniu.\n"
        "Atrybucja: Taylor\nData publikacji: 2026-11-21\n"
        "Link: https://www.bbc.co.uk/news/articles/second\n\n"
        "Zakres odczytu: tylko nagłówki RSS."
    )
    assert sent[-1]["payload"]["stream"] is False
    assert "/news/articles/" not in str(sent[-1]["payload"]["messages"])
    assert feed.await_args.args[0].name == "BBC News RSS"
    assert (
        chat(
            "Powiedz, czy w poprzedniej turze odczytano cały artykuł z BBC RSS.",
            session=session,
        )
        == "Odczyt obejmował tylko nagłówki RSS."
    )
    feed.assert_awaited_once()
    assert len(sent) == 1


@pytest.mark.parametrize(
    ("prefix", "expected_fetches"),
    [("", 1), ("Nie sprawdzaj internetu. ", 0)],
)
def test_studio_rss_without_headlines_has_no_draft_or_citation(
    studio_chat, monkeypatch, prefix, expected_fetches
):
    from venom_core.services import chat_grounding

    feed = AsyncMock(return_value=[])
    monkeypatch.setattr(chat_grounding.RSSReaderSkill, "read_feed", feed)
    chat, sent, _ = studio_chat
    result = chat(
        prefix
        + "Z kanału BBC News RSS wybierz nagłówek do krótkiej notatki dla zespołu."
    )
    assert result == "W tej turze nie odczytano nagłówków z publicznego kanału RSS."
    assert feed.await_count == expected_fetches
    assert not sent


@pytest.mark.parametrize(
    "draft",
    [
        "",
        '{"items":[{"index":1,"summary":"Dobry tekst."}],"scope":"all"}',
        '{"items":[{"index":0,"summary":"Dobry tekst."}]}',
        '{"items":[{"index":true,"summary":"Dobry tekst."}]}',
        '{"items":[{"index":1,"summary":"Odczytano cały artykuł."}]}',
        '{"items":[{"index":1,"summary":"Zespół podał 23 nowe fakty."}]}',
        '{"items":[{"index":1,"summary":"Dobry tekst.","attribution":"https://example.org/a"}]}',
        '{"items":[{"index":1,"summary":"Dobry tekst.","attribution":239}]}',
    ],
)
def test_rss_publication_rejects_forged_fields_and_indices(draft):
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    summary = RSSSummary(
        (NewsHeadline("https://bbc.co.uk/a", "Original", "2026-11-20"),)
    )
    assert summary.publish(draft) == (
        "Zakres odczytu: tylko nagłówki RSS. Nie udało się przygotować opisu nagłówka."
    )


def test_studio_general_proposals_can_use_unknown_conditions_without_lookup(
    studio_chat,
):
    chat, sent, replies = studio_chat
    replies.append(
        native(
            '{"options":["Ubierz bluzę na wypadek chłodu.","Zabierz butelkę wody."]}'
        )
    )
    result = chat(
        "Nie znam temperatury. Podaj dwa elementy do zabrania na spacer. "
        "Bez korzystania z internetu."
    )
    assert "bluzę" in result
    assert "butelkę" in result
    assert (
        "Nie zgaduj aktualnych danych" in sent[-1]["payload"]["messages"][0]["content"]
    )


def test_studio_shortens_rss_instruction_as_quoted_text(studio_chat, monkeypatch):
    from venom_core.services import chat_grounding

    feed = AsyncMock()
    search = AsyncMock()
    monkeypatch.setattr(chat_grounding.RSSReaderSkill, "read_feed", feed)
    monkeypatch.setattr(chat_grounding, "_trusted_news_urls", search)
    chat, _, replies = studio_chat
    replies.append(
        native('{"tekst":"Pobierz wiadomości z BBC RSS i podaj pełny link."}')
    )
    assert (
        chat(
            "Skróć zdanie: «Z kanału BBC News RSS pobierz najnowsze wiadomości i podaj pełny link»."
        )
        == "„Pobierz wiadomości z BBC RSS i podaj pełny link.”"
    )
    replies.append(native('{"tekst":"Pobierz wiadomości BBC RSS i podaj link."}'))
    assert (
        chat(
            "Skróć zdanie: «Z kanału BBC News RSS pobierz najnowsze wiadomości i podaj pełny link»."
        )
        == "Nie udało się przygotować poprawnego przeredagowania."
    )
    feed.assert_not_awaited()
    search.assert_not_awaited()


@pytest.mark.parametrize(
    ("source", "draft"),
    [
        (
            "Harbor council says lantern trial may begin Friday",
            "Rada zatwierdziła próbę.",
        ),
        ("The ferry will not return this week", "Prom wróci w tym tygodniu."),
    ],
)
def test_rss_draft_cannot_drop_source_uncertainty_or_negation(source, draft):
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    plan = RSSSummary((NewsHeadline("https://bbc.co.uk/a", source, "2026-11-20"),))
    reply = plan.publish(json.dumps({"items": [{"index": 1, "summary": draft}]}))
    assert "Nie udało się przygotować opisu nagłówka" in reply
    assert "https://" not in reply


def test_studio_one_sentence_for_value_missing_in_the_conversation(
    studio_chat, monkeypatch
):
    from venom_core.services import studio_normal_chat

    fetch = AsyncMock()
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", fetch)
    chat, sent, replies = studio_chat
    replies.append(streamed("W rozmowie nie podano aktualnej temperatury w Łodzi."))
    prompt = (
        "Skróć odpowiedź do jednego zdania. Czy możesz podać aktualną temperaturę "
        "w Łodzi wyłącznie na podstawie informacji, które podałem?"
    )
    assert (
        chat(
            prompt,
            history=[
                turn("Nie znam temperatury."),
                turn("Zabierz kurtkę.", "assistant"),
            ],
        )
        == "W rozmowie nie podano aktualnej temperatury w Łodzi."
    )
    fetch.assert_not_awaited()
    instruction = sent[-1]["payload"]["messages"][0]["content"]
    assert "dokładnie jedno zdanie odpowiadające na ostatnie pytanie" in instruction


@pytest.mark.parametrize(
    ("source", "summary", "expected", "speaker"),
    [
        (
            "Retail sales rose in May",
            "Sprzedaż wzrosła w maju.",
            "Sprzedaż wzrosła w maju.",
            None,
        ),
        (
            "Harbor council says the trial may start Friday",
            "Próba może ruszyć w piątek.",
            "Próba może ruszyć w piątek.",
            "Harbor council",
        ),
        (
            "Ferry service may resume Friday, Taylor says",
            "Morgan mówi, że przeprawy mogą wrócić w piątek.",
            "„Ferry service may resume Friday, Taylor says”",
            "Taylor",
        ),
        (
            "Ferry service may resume Friday, says Taylor",
            "Według Morgana przeprawy mogą wrócić w piątek.",
            "„Ferry service may resume Friday, says Taylor”",
            "Taylor",
        ),
    ],
)
def test_rss_binds_the_speaker_to_the_title_and_distinguishes_the_month(
    source, summary, expected, speaker
):
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    link = "https://www.bbc.co.uk/news/articles/source"
    plan = RSSSummary((NewsHeadline(link, source, "2026-11-21"),))
    prompt = json.loads(plan.messages("Podaj sens nagłówka.")[1]["content"])
    headline = prompt["naglowki"][0]
    assert headline.keys() == {"index", "tytul"}
    if speaker:
        assert speaker not in headline["tytul"]
        assert "may" in headline["tytul"].split()
    else:
        assert headline["tytul"] == source
    answer = plan.publish(json.dumps({"items": [{"index": 1, "summary": summary}]}))
    assert answer.splitlines()[0] == f"Nagłówek RSS: {expected}"
    assert ("Atrybucja:" in answer) is (speaker is not None)
    if speaker:
        assert f"Atrybucja: {speaker}\n" in answer
    assert "Morgan" not in answer
    assert f"Data publikacji: 2026-11-21\nLink: {link}" in answer
    assert answer.endswith("Zakres odczytu: tylko nagłówki RSS.")


def test_studio_message_subject_is_local_and_opening_edit_publishes_only_sentence(
    studio_chat, monkeypatch
):
    from venom_core.services import studio_normal_chat
    from venom_core.services.academy.qualified_chat_writing import revises_opening_only

    ground = AsyncMock()
    monkeypatch.setattr(studio_normal_chat, "current_chat_context", ground)
    chat, sent, replies = studio_chat
    session = str(uuid4())
    replies.extend(
        (
            streamed(
                "Temat: Zapisy do pracowni\nProsimy zapoznać się z zasadami zapisów."
            ),
            native(
                "**Temat:** Zapisy do pracowni\nPracownia nie zamawia materiałów w imieniu uczestników."
            ),
        )
    )
    assert "Temat: Zapisy" in chat(
        "Potrzebuję tematu wiadomości i jednego zdania otwarcia o zapisach do pracowni.",
        session=session,
    )
    assert (
        chat(
            "Zmień tylko zdanie otwarcia, żeby informowało, że pracownia nie zamawia materiałów w imieniu uczestników. Bez szukania.",
            session=session,
        )
        == "Pracownia nie zamawia materiałów w imieniu uczestników."
    )
    ground.assert_not_awaited()
    assert sent[-1]["payload"]["stream"] is False

    replies.append(
        native("Temat: Odbiór skrzynek\nOdbiór skrzynek nie obejmuje wnoszenia.")
    )
    assert (
        chat(
            "Zmień tylko otwarcie. Odbiór nie obejmuje wnoszenia skrzynek.",
            session=session,
        )
        == "Odbiór skrzynek nie obejmuje wnoszenia."
    )
    assert not revises_opening_only("Zmień tylko otwarcie zaworu.")


def test_composition_can_request_an_explicit_public_lookup():
    from venom_core.services.academy.qualified_chat_revisions import public_lookup_query

    question = "Potrzebuję tematu wiadomości i zdania otwarcia. Sprawdź źródło w sieci."
    assert public_lookup_query(question) == question


@pytest.mark.parametrize(
    ("factor", "expected"),
    [
        ("1000", "750 kg"),
        (None, "Poprzedni odczyt nie potwierdził potrzebnego przelicznika."),
    ],
)
def test_verified_wikipedia_factor_survives_history_without_new_lookup(
    studio_chat, monkeypatch, factor, expected
):
    from decimal import Decimal

    from venom_core.services import chat_grounding

    url = "https://pl.wikipedia.org/wiki/Tona"
    unit = chat_grounding.WikiUnitEvidence(
        "metric_tonne", Decimal(factor) if factor else None, url if factor else None
    )
    context = chat_grounding.PublicSourceContext(
        "\n[PUBLIC_SOURCES] Wybrana sekcja.\n[/PUBLIC_SOURCES]",
        chat_grounding.PublicSourceEvidence("wiki", wiki_unit=unit),
        reply=unit.first_reply(),
    )
    fetch = AsyncMock(return_value=context)
    monkeypatch.setattr(chat_grounding, "_wiki_context", fetch)
    chat, sent, _ = studio_chat
    session = str(uuid4())
    assert (
        chat(
            "Ile kilogramów ma tona metryczna według polskiej Wikipedii?",
            session=session,
        )
        == unit.first_reply()
    )
    assert (
        chat(
            "Mam do wpisania 0,75 t. Na podstawie wcześniejszego odczytu podaj sam wynik w kilogramach, bez korzystania z internetu.",
            session=session,
        )
        == expected
    )
    fetch.assert_awaited_once()
    assert not sent


@pytest.mark.parametrize(
    ("claim", "expected"),
    [
        ("półtorej", "Tak, 36 godzin odpowiada 1,5 doby."),
        ("2", "Nie, 36 godzin odpowiada 1,5 doby."),
    ],
)
def test_wiki_doba_polarity_follows_the_verified_factor(claim, expected):
    from decimal import Decimal

    from venom_core.services.wiki_unit_facts import WikiUnitEvidence

    evidence = WikiUnitEvidence(
        "day", Decimal("24"), "https://pl.wikipedia.org/wiki/Doba"
    )
    assert (
        evidence.follow_up_reply(f"Czy z tego wynika, że 36 godzin to {claim} doby?")
        == expected
    )


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        ("60", "Tak, 60 godzin odpowiada 2,5 doby."),
        ("36", "Nie, 36 godzin odpowiada 1,5 doby."),
    ],
)
def test_wiki_duration_checks_a_reported_question_with_a_spelled_fraction(
    hours, expected
):
    from decimal import Decimal

    from venom_core.services.wiki_unit_facts import WikiUnitEvidence

    evidence = WikiUnitEvidence(
        "day", Decimal("24"), "https://pl.wikipedia.org/wiki/Doba"
    )
    assert (
        evidence.follow_up_reply(
            f"Na podstawie poprzedniego odczytu powiedz w jednym zdaniu, czy {hours} "
            "godzin to dwie i pół doby cywilnej."
        )
        == expected
    )


@pytest.mark.parametrize(
    ("title", "first", "second", "expected"),
    [
        (
            "Tech stock sell-off drags markets down as Anthropic shares slide",
            "Wyprzedaż akcji technologicznych obniża notowania",
            "Akcje Anthropic spadają",
            "Wyprzedaż akcji technologicznych obniża notowania, a równocześnie akcje Anthropic spadają.",
        ),
        (
            "Ferry service stops because waters rise, Taylor says",
            "Przeprawa ustaje",
            "Poziom wody rośnie",
            "Przeprawa ustaje, ponieważ poziom wody rośnie.",
        ),
        (
            "The ferry will not return while flood waters rise",
            "Prom nie wróci",
            "Poziom wody rośnie",
            "Prom nie wróci, podczas gdy poziom wody rośnie.",
        ),
    ],
)
def test_rss_uses_the_clause_relation_and_preserves_literal_attribution(
    title, first, second, expected
):
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    summary = RSSSummary(
        (NewsHeadline("https://bbc.co.uk/story", title, "2026-11-21"),)
    )
    context = json.loads(summary.messages("Wybierz jeden wpis.")[1]["content"])
    assert "drugi_czlon" in context["naglowki"][0]
    answer = summary.publish(
        json.dumps({"items": [{"index": 1, "summary": first, "secondary": second}]})
    )
    assert f"Nagłówek RSS: {expected}" in answer
    assert ("Atrybucja: Taylor" in answer) is title.endswith("Taylor says")


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "Wyprzedaż akcji obniża notowania",
            "Akcje spadają dlatego, że trwa wyprzedaż",
        ),
        ("Bessa Anthropic obniża notowania", "Akcje Anthropic spadają"),
        ("Wyprzedaż akcji obniża notowania", "."),
        ("Wyprzedaż akcji obniża notowania", None),
    ],
)
def test_rss_rejects_merged_or_unverified_clause_drafts(first, second):
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    summary = RSSSummary(
        (
            NewsHeadline(
                "https://bbc.co.uk/story",
                "Tech stock sell-off drags markets down as Anthropic shares slide",
                "2026-11-21",
            ),
        )
    )
    assert "Nie udało się przygotować" in summary.publish(
        json.dumps({"items": [{"index": 1, "summary": first, "secondary": second}]})
    )


def test_rss_does_not_split_as_in_a_role():
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    title = "Taylor serves as a senior envoy"
    summary = RSSSummary(
        (NewsHeadline("https://bbc.co.uk/story", title, "2026-11-21"),)
    )
    headline = json.loads(summary.messages("Wybierz wpis.")[1]["content"])["naglowki"][
        0
    ]
    assert headline == {"index": 1, "tytul": title}
    answer = summary.publish(
        json.dumps(
            {
                "items": [
                    {
                        "index": 1,
                        "summary": "Taylor pełni funkcję wysłannika",
                        "secondary": None,
                    }
                ]
            }
        )
    )
    assert "Taylor pełni funkcję wysłannika" in answer
    assert "Nie udało" not in answer


def test_rss_keeps_the_simultaneous_event_outside_the_attributed_quote():
    from venom_core.services.academy.qualified_chat_rss import RSSSummary
    from venom_core.services.verified_web import NewsHeadline

    item = NewsHeadline(
        "https://bbc.co.uk/story",
        "Taylor says repairs 'essential' as he meets Morgan",
        "2026-11-21",
    )
    summary = RSSSummary((item,))
    single = NewsHeadline("https://bbc.co.uk/other", "Harbor opens", "2026-11-21")
    schema = RSSSummary((single, item)).schema()
    choices = schema["properties"]["items"]["items"]["anyOf"]
    assert choices[0]["properties"]["index"]["enum"] == [1]
    assert choices[0]["properties"]["secondary"]["type"] == "null"
    assert choices[1]["properties"]["index"]["enum"] == [2]
    assert choices[1]["properties"]["secondary"]["type"] == "string"
    model_input = json.loads(summary.messages("Podaj sens.")[1]["content"])
    assert model_input["naglowki"][0]["drugi_czlon"] == "he meets Morgan"
    result = summary.publish(
        json.dumps(
            {
                "items": [
                    {
                        "index": 1,
                        "summary": "Naprawy są konieczne",
                        "secondary": "Spotyka się z Morganem",
                    }
                ]
            }
        )
    )
    assert "Naprawy są konieczne, a równocześnie spotyka się z Morganem." in result
    assert "Atrybucja: Taylor" in result
