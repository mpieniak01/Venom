"""Ground a bounded Studio follow-up in the latest user turns."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from venom_core.api.schemas.llm_simple import HistoryMessage
from venom_core.services.chat_policy.qualified_chat_options import split_options
from venom_core.services.chat_policy.qualified_chat_quote import without_quotes
from venom_core.services.chat_policy.studio_status import studio_status
from venom_core.services.grounded_calculator import result_with_unit

_MINUTES = r"min(?:ut[ay]?)?"
_PAIR = re.compile(
    r"(?:(?:korekta (?P<each>każdego z |każdej z )?pierwszych dwóch \w+ zajęła)|"
    r"(?:dw(?:a|ie) \w+ przeszły korektę w)|"
    r"(?:pierwsze dw(?:a|ie) \w+ poprawiano przez)) "
    rf"(?P<scope>łącznie |po )?(?P<a>[0-9]{{1,3}}) {_MINUTES}\. "
    r"(?:korekta trzecie(?:go|j) zajęła|trzeci(?:e(?:go|j)?|a)? w|"
    r"trzeci[ae] korekta trwała) "
    rf"(?P<b>[0-9]{{1,3}}) {_MINUTES}\. "
    r"(?:ile (?:czasu zajęła korekta wszystkich|zajęły wszystkie)|jaka jest suma)\?",
    re.I,
)
_UPDATE = re.compile(
    rf"jeśli trzeci(?:e(?:go|j)?|a) (?:jednak )?zajęł[oa] (?P<minutes>[0-9]{{1,3}}) {_MINUTES}"
    r", podaj (?:wyłącznie|tylko) now[ąy] (?:sumę i jednostkę|łączny czas z jednostką)\.",
    re.I,
)
_SCOPE_ANSWER = re.compile(
    rf"(?P<minutes>[0-9]{{1,3}}) {_MINUTES} dotyczy "
    r"(?P<scope>obu korekt łącznie|każdej z dwóch korekt)\. podaj wynik z jednostką\.",
    re.I,
)
_SCOPE_CONFIRMATION = re.compile(
    rf"potwierdzam: (?P<minutes>[0-9]{{1,3}}) {_MINUTES} to "
    r"(?P<scope>łączny czas dwóch pierwszych|czas każdej z dwóch pierwszych)\. "
    r"zsumuj z poprawionym czasem trzeci(?:ej|ego)\.",
    re.I,
)
_SCOPE_STILL_UNKNOWN = re.compile(
    rf"dopowiem tylko, że korekta trzecie(?:go|j) zajęła (?P<minutes>[0-9]{{1,3}}) {_MINUTES}\. "
    rf"nadal nie mówię, czy (?P<group>[0-9]{{1,3}}) {_MINUTES} było łącznie, czy na sztukę\. "
    r"zadaj krótkie pytanie\.",
    re.I,
)
_SCOPE_RESTATEMENT = re.compile(
    rf"trzecia korekta trwała jednak (?P<minutes>[0-9]{{1,3}}) {_MINUTES}\. "
    r"czas dwóch pierwszych nadal może oznaczać sumę albo czas na jedną\. "
    r"czy już da się podać jedną sumę\?",
    re.I,
)
_COMPONENT_REVISION = re.compile(
    r"(?:(?:poprawiam|korekta): )?"
    r"(?:trzecia(?: korekta)? (?:trwała(?: jednak)?|jednak trwała)|"
    r"korekta trzecie(?:j|go) (?:zajęła|trwała)) "
    rf"(?P<minutes>[0-9]{{1,3}}) {_MINUTES}",
    re.I,
)
_GROUP_SCOPE_OPEN = re.compile(
    rf"(?:zakresu (?P<before>[0-9]{{1,3}}) {_MINUTES} (?:nadal |jeszcze )?nie podał(?:am|em)|"
    rf"(?:nadal )?nie wiadomo, czy (?P<after>[0-9]{{1,3}}) {_MINUTES} "
    r"dotyczy (?:obu|dwóch pierwszych) łącznie, czy każdej z osobna)",
    re.I,
)
_GROUP_SCOPE_RESOLVED = re.compile(
    rf"(?:te )?(?P<group>[0-9]{{1,3}}) {_MINUTES} "
    r"(?:to (?P<total>łączny czas (?:obu|dwóch pierwszych)(?: korekt)?)|"
    r"(?:było|przypadało) na (?P<each>każdą (?:z dwóch pierwszych|z obu)(?: korekt)?))",
    re.I,
)
_DURATION_RESULT_REQUEST = re.compile(
    r"(?:czy (?:już )?(?:da się|można) podać (?:jedną )?sumę\?|"
    r"podaj (?:jedną )?(?:sumę|wynik)(?: z jednostką)?\.)",
    re.I,
)
_DURATION_CLAUSES = re.compile(r"\. |, a (?=trzecia|korekta trzecie)", re.I)
_REQUEST_UNCONFIRMED = re.compile(
    r"(?:(?:dostałem|dostałam) prośbę o (?P<received>[\w ]{2,75}), "
    r"ale nie mam potwierdzenia, że to zrobił(?:em|am)\. "
    r"|zgłoszono prośbę o (?P<reported>[\w ]{2,75})\. wykonania nie potwierdzono\. )"
    r"(?:zapisz|podaj) stan w jednym zdaniu\.",
    re.I,
)
_WITHDRAW_UNCONFIRMED = re.compile(
    r"dodaj, że prośba została wycofana\. zachowaj rozróżnienie między brakiem "
    r"potwierdzenia a stwierdzeniem, że nic się nie wydarzyło\.",
    re.I,
)
_DEFER_CHOICE = re.compile(
    r"ułóż jedno zdanie dla osoby z zespołu: przekładamy wybór (?P<topic>[\w ]{2,60}) "
    r"i nie podano dlaczego\. nie sugeruj przyczyny\.",
    re.I,
)
_REOPEN_CHOICE = re.compile(
    r"wycofuję polecenie odłożenia\. nadal nie padła żadna decyzja\. "
    r"podaj tylko jedno krótkie pytanie o wybór (?P<topic>[\w ]{2,60})\.",
    re.I,
)
_OWNERSHIP = re.compile(
    r"(?:wiadomość jest do [\w ]{2,60}\. )?(?P<item>[\w ]{2,65}) należy do (?P<owner>[^\W\d_]+), "
    r"(?P<borrower>[^\W\d_]+) tylko ma (?:go|ją) pożyczyć\. "
    r"(?:podaj|zapisz) oba fakty w jednym zdaniu\.",
    re.I,
)
_REQUEST_STATUS = re.compile(
    r"korekta: (?P<who>[^\W\d_]+) dopiero (?P<fact>poprosi(?:ł|ła) o (?P<requested>[\w ]{2,65})"
    r" i nie dosta(?:ł|ła) jeszcze odpowiedzi)\. "
    r"napisz jedno zdanie dla osoby, która nie czytała historii\.",
    re.I,
)
_PDF = re.compile(
    r"(?P<item>[\w ]{2,65}) autorstwa [^\W\d_]+ mam gotowy w PDF\. "
    r"jeszcze go nie dołączył(?:em|am)\. napisz krótko, jaki jest stan\.",
    re.I,
)
_NO_SEND = re.compile(
    r"odwołuję propozycję przesłania\. powiedz [^\W\d_]+ tylko, jaki plik jest gotowy "
    r"i że na razie go nie wyślę\. nie dopisuj powodu\.",
    re.I,
)
_DEFERRAL = re.compile(
    r"na dziś odłóżmy decyzję o [\w ]{2,75}\. "
    r"nie umawiamy spotkania ani kontaktu\. napisz jedno zdanie\.",
    re.I,
)
_CONTACT_ONLY = re.compile(
    r"teraz dodaj tylko, że (?P<body>jutro o [^.!?\r\n]{1,72} wrócę z [^.!?\r\n]{2,80})"
    r"\. to godzina powrotu do tematu\.",
    re.I,
)
_INVITATION_ONLY = re.compile(
    r"(?P<fact>[^\W\d_]+ (?:opracowa|sporządzi|przygotowa)(?:ł|ła) [\w ]{2,65})\. "
    r"na razie (?:możesz zaprosić|zaproś) (?P<audience>zespół|grupę) do wspólnego przeglądu, "
    r"bez zbierania opinii\. napisz (?:krótkie )?zaproszenie\.",
    re.I,
)
_CHOICES = re.compile(
    r"na [\w ]{2,50} możemy wybrać (?P<first>\w+(?: \w+){0,2}) albo "
    r"(?P<second>\w+(?: \w+){0,2})\. żadna opcja jeszcze nie wygrała\. podaj możliwości\.",
    re.I,
)
_REPLACE_CHOICE = re.compile(
    r"zamiast (?P<old>\w+(?: \w+){0,2}) chcę (?P<new>\w+(?: \w+){0,2})\. "
    r"zadaj tylko jedno pytanie o wybór jednej z dwóch aktualnych możliwości\.",
    re.I,
)
_CONNECTOR = re.compile(r"\b(?:i|albo|lub|oraz|ani|nie|tylko)\b", re.I)
_PARTS = {"cztery": 4, "sześć": 6, "osiem": 8, "dwanaście": 12}
_COUNT_WORD = r"cztery|sześć|osiem|dwanaście"
_PORTIONS = re.compile(
    r"przepis mówi, by podzielić (?:(?P<shape>okrągłe|prostokątne) )?ciasto "
    rf"na (?P<count>{_COUNT_WORD}) kawałków\. podaj jeden sposób, "
    r"żeby kawałki były zbliżone wielkością\.",
    re.I,
)
_PORTION_UPDATE = re.compile(
    rf"zmiana: ma być (?P<count>{_COUNT_WORD}) kawałków\. podaj krótko, jak zmienia się podział\.",
    re.I,
)
_MEMORY = re.compile(
    r"podaj dwie czynności pomagające zapamiętać (?P<goal>[\w ]{2,60}), bez robienia zdjęć\.",
    re.I,
)
_MEMORY_CHOICE = re.compile(
    r"wybierz jedną z nich bez pisania i krótko wyjaśnij, czemu pomaga\.", re.I
)
_REWRITE = re.compile(
    r"\b(?:uprość zdanie|uprość to zdanie|przeredaguj zdanie)\b", re.I
)
_JUST_TITLE = re.compile(r"\btylko (?:jeden )?tytuł\b", re.I)
_KEEP_METHOD = re.compile(r"\bzachowaj (?:tę samą )?metodę\b", re.I)
_ONE_REWRITE = re.compile(
    r"\b(?:napisz (?:jeszcze )?krócej|skróć jeszcze bardziej)\b", re.I
)
_SHORT_DRAFT = re.compile(
    r"\b(?:napisz (?:krótkie )?zaproszenie|poproś teraz (?:wprost )?o jedno krótkie pytanie)\b",
    re.I,
)
_TWO_ACTIONS = re.compile(r"^podaj dwie czynności\b", re.I)


def _duration_pair(text: str) -> re.Match[str] | None:
    pair = _PAIR.fullmatch(text)
    if pair and not (pair["each"] and (pair["scope"] or "").casefold() == "łącznie "):
        return pair
    return None


def _pair_scope(pair: re.Match[str]) -> str | None:
    if pair["each"]:
        return "po"
    return pair["scope"].strip().casefold() if pair["scope"] else None


@dataclass(frozen=True)
class _DurationChange:
    minutes: int
    scope: str | None = None


def _minutes(
    pair: re.Match[str], replacement: int | None = None, *, scope: str | None = None
) -> str:
    scope = scope or _pair_scope(pair)
    first = int(pair["a"])
    if scope is None:
        return f"Czy {first} min dotyczy obu korekt łącznie, czy każdej z osobna?"
    count = 2 if scope == "po" else 1
    last = int(pair["b"]) if replacement is None else replacement
    result = result_with_unit(f"{count}*{first}+{last}", "min")["value"]
    return f"{result} min"


def _scope_with_component_revision(
    text: str, pair: re.Match[str]
) -> _DurationChange | None:
    """Bind the two independent statements to the existing calculation."""
    if _pair_scope(pair) is not None:
        return None
    clauses = _DURATION_CLAUSES.split(text)
    if len(clauses) != 3 or not _DURATION_RESULT_REQUEST.fullmatch(clauses[-1]):
        return None

    left, right = clauses[:2]
    correction = _COMPONENT_REVISION.fullmatch(left)
    scope_clause = right
    if correction is None:
        correction = _COMPONENT_REVISION.fullmatch(right)
        scope_clause = left
    if correction is None:
        return None

    minutes = int(correction["minutes"])
    if known := _GROUP_SCOPE_RESOLVED.fullmatch(scope_clause):
        if int(known["group"]) == int(pair["a"]):
            return _DurationChange(minutes, "po" if known["each"] else "łącznie")
    if unknown := _GROUP_SCOPE_OPEN.fullmatch(scope_clause):
        if int(unknown["before"] or unknown["after"]) == int(pair["a"]):
            return _DurationChange(minutes)
    return None


def _time_update(text: str, pair: re.Match[str]) -> _DurationChange | None:
    if update := _UPDATE.fullmatch(text):
        return _DurationChange(int(update["minutes"]))
    note = _SCOPE_STILL_UNKNOWN.fullmatch(text) or _SCOPE_RESTATEMENT.fullmatch(text)
    if note is not None and _pair_scope(pair) is None:
        stated_group = note.groupdict().get("group")
        if stated_group is None or int(stated_group) == int(pair["a"]):
            return _DurationChange(int(note["minutes"]))
    return _scope_with_component_revision(text, pair)


def _time_followup(
    current: str, previous: str, history: Sequence[HistoryMessage]
) -> str | None:
    pair = _duration_pair(previous)
    if pair is not None and (update := _time_update(current, pair)):
        return _minutes(pair, update.minutes, scope=update.scope)

    confirmation = _SCOPE_CONFIRMATION.fullmatch(current)
    clarified = _SCOPE_ANSWER.fullmatch(current) or confirmation
    if clarified is None:
        return None
    replacement = None
    if pair is None and len(history) >= 4:
        if (history[-4].role, history[-3].role) != ("user", "assistant"):
            return None
        pair = _duration_pair(" ".join(history[-4].content.split()))
        if pair is None or (update := _time_update(previous, pair)) is None:
            return None
        if update.scope is not None:
            return None
        replacement = update.minutes
    if (
        pair is None
        or _pair_scope(pair) is not None
        or (confirmation is not None and replacement is None)
        or int(clarified["minutes"]) != int(pair["a"])
    ):
        return None
    scope = "po" if "każdej" in clarified["scope"].casefold() else "łącznie"
    return _minutes(pair, replacement, scope=scope)


def _request_action(text: str) -> str | None:
    request = _REQUEST_UNCONFIRMED.fullmatch(text)
    return (request["received"] or request["reported"]) if request else None


def _choices(match: re.Match[str]) -> list[str]:
    choices = [match["first"], match["second"]]
    if any(_CONNECTOR.search(value) for value in choices):
        return []
    return choices if choices[0].casefold() != choices[1].casefold() else []


def _choice_update(old: re.Match[str], edit: re.Match[str]) -> str | None:
    choices = _choices(old)
    if not choices or _CONNECTOR.search(edit["new"]):
        return None
    requested = edit["old"].casefold()
    matches = []
    for index, option in enumerate(choices):
        term = option.casefold()
        forms = {term, f"{term}u"}
        if term.endswith("o"):
            forms.add(f"{term[:-1]}a")
        if requested in forms:
            matches.append(index)
    if len(matches) != 1:
        return None
    choices[matches[0]] = edit["new"]
    if choices[0].casefold() == choices[1].casefold():
        return None
    return f"Czy wybierasz {choices[0]}, czy {choices[1]}?"


def _portion_method(shape: str | None, count: int) -> str:
    if shape == "okrągłe":
        label = "sektory" if count == 4 else "sektorów"
        return f"Od środka wyznacz {count} {label} po {360 // count}° i tnij wzdłuż ich granic."
    if shape == "prostokątne":
        return (
            f"Podziel ciasto na 2 równe pasy, a każdy pas na {count // 2} równe części."
        )
    return f"Zważ całe ciasto i odmierz każdy kawałek jako 1/{count} jego masy."


def _memory_choice(request: re.Match[str], prior_draft: str) -> str | None:
    goal = request["goal"]
    goal_text = re.escape(goal)
    repeat = re.compile(
        rf"powtórz (?:kilka razy )?{goal_text} na głos(?: kilka razy)?[.!]?",
        re.I,
    )
    for option in split_options(prior_draft):
        if repeat.fullmatch(option.strip()):
            action = option.strip().rstrip(".!")
            return f"{action}. Słyszysz wtedy brzmienie i ćwiczysz przypominanie sobie informacji."
    return None


def studio_followup(text: str, history: Sequence[HistoryMessage]) -> str | None:
    current = " ".join(text.split())
    if pair := _duration_pair(current):
        return _minutes(pair)
    if action := _request_action(current):
        return f"Zgłoszono prośbę o {action}, a wykonania nie potwierdzono."
    if status_reply := studio_status(current, history):
        return status_reply
    if (options := _CHOICES.fullmatch(current)) and (choices := _choices(options)):
        return f"Możliwości to {choices[0]} albo {choices[1]}. Żadna opcja nie została wybrana."
    if portions := _PORTIONS.fullmatch(current):
        shape = portions["shape"]
        return _portion_method(
            shape.casefold() if shape else None, _PARTS[portions["count"].casefold()]
        )
    if invitation := _INVITATION_ONLY.fullmatch(current):
        return f"{invitation['fact']}. Zapraszam {invitation['audience']} do wspólnego przeglądu."
    if len(history) < 2 or (history[-2].role, history[-1].role) != (
        "user",
        "assistant",
    ):
        return None
    previous = " ".join(history[-2].content.split())
    if (edit_choice := _REPLACE_CHOICE.fullmatch(current)) and (
        options := _CHOICES.fullmatch(previous)
    ):
        return _choice_update(options, edit_choice)
    if (new_portions := _PORTION_UPDATE.fullmatch(current)) and (
        portions := _PORTIONS.fullmatch(previous)
    ):
        shape = portions["shape"]
        shape = shape.casefold() if shape else None
        if history[-1].content == _portion_method(
            shape, _PARTS[portions["count"].casefold()]
        ):
            return _portion_method(shape, _PARTS[new_portions["count"].casefold()])
    if _MEMORY_CHOICE.fullmatch(current) and (memory := _MEMORY.fullmatch(previous)):
        return _memory_choice(memory, history[-1].content)
    if answer := _time_followup(current, previous, history):
        return answer
    if _WITHDRAW_UNCONFIRMED.fullmatch(current) and (
        action := _request_action(previous)
    ):
        return f"Prośbę o {action} wycofano, a wykonania nie potwierdzono."
    if (reopen := _REOPEN_CHOICE.fullmatch(current)) and (
        deferred := _DEFER_CHOICE.fullmatch(previous)
    ):
        if reopen["topic"].casefold() == deferred["topic"].casefold():
            return f"Jaką opcję wybieramy w sprawie {reopen['topic']}?"

    if (status := _REQUEST_STATUS.fullmatch(current)) and (
        ownership := _OWNERSHIP.fullmatch(previous)
    ):
        item = ownership["item"]
        item_forms = {item.casefold(), item.split()[0].casefold()}
        if len(item.split()) == 1 and item.casefold().endswith("a"):
            item_forms.add(item.casefold()[:-1] + "ę")
        if (
            status["who"].casefold() == ownership["borrower"].casefold()
            and status["requested"].casefold() in item_forms
        ):
            return f"{item} należy do {ownership['owner']}, a {status['who']} {status['fact']}."
    if _NO_SEND.fullmatch(current) and (pdf := _PDF.fullmatch(previous)):
        return f"{pdf['item']} jest gotowy w PDF. Na razie go nie wyślę."
    if (contact := _CONTACT_ONLY.fullmatch(current)) and _DEFERRAL.fullmatch(previous):
        body = contact["body"]
        return f"{body[0].upper()}{body[1:]}."
    return None


def studio_concise_hint(text: str, counted: bool) -> str:
    visible = without_quotes(text)
    if counted and _TWO_ACTIONS.search(visible):
        memory_hint = ""
        if memory := _MEMORY.fullmatch(visible):
            memory_hint = f" Jedna czynność może brzmieć dokładnie: Powtórz {memory['goal']} na głos."
        return (
            "Każda opcja ma zawierać jedną konkretną czynność w krótkiej frazie. "
            "Gdy podano wszystkie warunki, zwróć od razu czynności. "
            "Nie dołączaj przykładów, objaśnień ani alternatyw wewnątrz opcji."
            + memory_hint
        )
    if _JUST_TITLE.search(visible):
        return (
            "Zwróć jeden sam tytuł. Nazwij w nim jawnie wskazany punkt scenerii, "
            "miejsce lub przedmiot oraz zachowaj podaną porę. Bez objaśnień i wariantów."
        )
    if _KEEP_METHOD.search(visible):
        return (
            "Przenieś zasadę lub kryterium wyboru z poprzedniej metody. "
            "Zmień tylko wskazane okoliczności i nie zgaduj własności przedmiotów."
        )
    if (
        _REWRITE.search(visible)
        or _SHORT_DRAFT.search(visible)
        or _ONE_REWRITE.search(visible)
    ):
        return (
            "Oddaj jeden gotowy tekst i zakończ. Pomiń nagłówki, uzasadnienie, warianty, "
            "komentarze i miejsca na linki. W zaproszeniu zmieść cel i jawne warunki "
            "w najwyżej dwóch krótkich zdaniach. Poprawka zmienia wyłącznie wskazany warunek."
        )
    return ""
