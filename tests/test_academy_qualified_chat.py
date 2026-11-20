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
    assert "trzech krótkich zdaniach" in one["messages"][0]["content"]
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
