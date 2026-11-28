"""Verify complete PLN bills from item-bound facts stated by the user."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field

from venom_core.services.grounded_calculator import CalculationError, calculate

# Each recognized statement must consume its entire clause. A number from a
# different product or an unparsed modifier cannot become a calculator operand.
NAME = r"(?P<name>[a-ząćęłńóśźż]+(?:-[a-ząćęłńóśźż]+)?)"
COUNT = r"(?P<count>[1-9]\d{0,5})"
PRICE = r"(?P<price>(?:0|[1-9]\d{0,6})(?:[.,]\d{1,2})?) (?:zł|pln)"
UNIT = r"(?: za sztukę)?"
BARE_PRICE = re.compile(PRICE + UNIT, re.I)
BARE_COUNT = re.compile(COUNT + r" sztuk(?:i)?", re.I)
SHORT_VALUE = re.compile(
    r"[-+−]?\d+(?:[.,]\d+)?\s+(?P<unit>zł|pln|sztuk[ai]?)(?: za sztukę)?", re.I
)
PREFIX = re.compile(r"^(?:nowy )?rachunek\s*:\s*", re.I)
CALCULATOR = re.compile(r"^kalkulator\s*:\s*", re.I)
COST_QUESTION = re.compile(
    r"^(?:ile zapłacę za|ile kosztuj[ąe]|jaki jest koszt) (?=\d)", re.I
)
OPENING = re.compile(
    r"^(?:kupuję|kupił[ea]m|zamawiam|potrzebuję|w koszyku|wypożyczył[ea]m|zestaw obejmuje|"
    r"chcę policzyć koszt|są w ofercie|za wydruk:|za \d|\d)",
    re.I,
)
PRICE_SIGNAL = re.compile(r"\b(?:zł|pln|euro|eur|groszy)\b", re.I)
FOLLOW = re.compile(
    r"^(?:zmień (?:cenę|ilość|liczbę)|zmieniam (?:cenę|ilość|liczbę)|korekta\b|cena\b|wycofaj\b|pomiń\b|dolicz\b|dodaj\b|zamiast\b|"
    r"ile (?:razem|za|zapłacę|płacę|zostało)|podaj sumę\b|interesują mnie (?:wyłącznie|tylko)\b|(?:policz )?tylko\b|"
    r"[\w-]+ (?:opłacono|kosztuj\w*|po \d))",
    re.I,
)
INTRO = re.compile(
    r"^(?:wypożyczył[ea]m(?: w sumie)?|w koszyku (?:są|mam)|"
    r"(?:oprócz tego )?kupuję|kupił[ea]m|zamawiam|potrzebuję|zestaw obejmuje|"
    r"chcę policzyć koszt|za wydruk:|notatka wspomina także|dodaj|dolicz) "
)
ROW = re.compile(
    rf"(?:za )?{COUNT} {NAME}(?: (?:zapłacę po|sklep nalicza po|po|w cenie) {PRICE}{UNIT})?"
)
UNIT_OFFER = re.compile(rf"za 1 {NAME} liczą {PRICE}")
ORDER_COUNT = re.compile(rf"potrzebuję {COUNT} sztuk(?:i)?")
CHANGE_COUNT = re.compile(rf"korekta (?:liczby|ilości) {NAME}: (?:biorę )?{COUNT}")
CHANGE_PRICE = re.compile(rf"cena {NAME} (?:jednak|teraz|to) {PRICE}{UNIT}")
ITEM_PRICE = re.compile(rf"{NAME} (?:kosztuje|kosztują po|po) {PRICE}{UNIT}")
UNKNOWN_COUNT = re.compile(rf"nie wiadomo ile {NAME} dokupię")
CHANGE_FROM = re.compile(
    rf"(?:zmień|zmieniam) (?P<field>cenę|ilość|liczbę) {NAME} z "
    r"(?P<old>\d+(?:[.,]\d{1,2})?)(?P<old_unit> zł)? na "
    r"(?P<new>\d{1,7}(?:[.,]\d{1,2})?)(?P<new_unit> zł)?"
)
EXCLUDE = re.compile(rf"(?:wycofaj|pomiń) {NAME}(?: z rachunku)?")
SEPARATELY = re.compile(rf"{NAME} opłacono osobno")
SUBSET = re.compile(
    rf"(?:interesują mnie (?:tylko|wyłącznie)|teraz rozliczamy tylko|"
    rf"(?:policz )?tylko|jaki jest koszt samych|ile zapłacę za same|ile zostało do zapłaty za) {NAME}"
)
TOTAL = re.compile(
    r"(?:jaki jest łączny koszt|ile (?:razem|płacę|zapłacę|to (?:kosztuje|wyniesie))|"
    r"ile (?:zapłacę )?za (?:całość|cały zestaw)|podaj sumę(?: zamówienia)?)"
)
FILLER = "cena jednostkowa obu pozycji bez zmian"
# Protect decimal separators, including in the middle of a sentence.
SEPARATOR = re.compile(r"[;\n!?]|(?<!\d)[.,]|[.,](?!\d)| (?:i|oraz|plus) ")
GENERIC = (
    "Podaj pełny rachunek: dla każdej pozycji wpisz ilość, nazwę i cenę za sztukę w zł."
)
NEW_OR_CHANGE = "Czy zaczynasz nowy rachunek? Wpisz „Nowy rachunek:” z pełną listą albo podaj zmianę z nazwą pozycji."
MISSING_BASE = (
    "Którego rachunku dotyczy zmiana? Podaj pełną listę pozycji z ilościami i cenami."
)


class BillQuestion(ValueError):
    """A bill cannot be published until the operator clarifies the evidence."""


@dataclass
class Item:
    count: str | None = None
    price: str | None = None
    removed: bool = False
    price_disputed: bool = False
    count_disputed: bool = False

    def needs_value(self, price: bool) -> bool:
        return (
            (self.price is None or self.price_disputed)
            if price
            else (self.count is None or self.count_disputed)
        )


def _stems(name: str) -> set[str]:
    # Only resolve common noun endings against the actual item inventory.
    endings = ("ów", "ami", "ach", "om", "y", "i", "a", "ę", "e", "u")
    return {name} | {
        name[: -len(end)]
        for end in endings
        if name.endswith(end) and len(name) - len(end) >= 3
    }


@dataclass
class Bill:
    items: dict[str, Item] = field(default_factory=dict)
    only: str | None = None

    def candidates(self, name: str) -> list[str]:
        return [key for key in self.items if _stems(key) & _stems(name)]

    def resolve(self, name: str) -> str:
        if name in self.items:
            return name
        matches = self.candidates(name)
        if len(matches) != 1:
            raise BillQuestion(
                f"Do której pozycji odnosi się „{name}”? Podaj jej nazwę z rachunku."
            )
        return matches[0]

    def add(self, name: str, count: str | None, price: str | None) -> None:
        if self.candidates(name):
            raise BillQuestion(
                f"Pozycja „{name}” występuje kilka razy. Podaj jej aktualną ilość i cenę w pełnym rachunku."
            )
        self.items[name] = Item(count, price)

    def apply(self, text: str) -> None:
        text = _checked_text(text)
        short_answer = text.rstrip(".!").rstrip()
        if match := BARE_PRICE.fullmatch(short_answer) or BARE_COUNT.fullmatch(
            short_answer
        ):
            self._fill_missing(match)
            return
        offer: str | None = None
        selected_in_turn = None
        for clause in _clauses(text):
            if selected := SUBSET.fullmatch(clause):
                selected_in_turn = self._select_once(selected["name"], selected_in_turn)
            if match := UNIT_OFFER.fullmatch(clause):
                offer = match["name"]
                self.add(offer, None, match["price"])
                continue
            if offer and (match := ORDER_COUNT.fullmatch(clause)):
                self.items[offer].count = match["count"]
            else:
                self._apply_clause(clause)
            offer = None

    def _select_once(self, name: str, previous: str | None) -> str:
        selected = self.resolve(name)
        if previous not in (None, selected):
            raise BillQuestion(
                "Które pozycje mam zsumować? Podaj jeden zakres rachunku."
            )
        return selected

    def _apply_clause(self, clause: str) -> None:
        if _bare_value(clause):
            raise BillQuestion(GENERIC)
        if match := ROW.fullmatch(INTRO.sub("", clause, count=1)):
            self.add(match["name"], match["count"], match["price"])
        elif not (self._revise(clause) or self._scope(clause) or clause == FILLER):
            raise BillQuestion(GENERIC)

    def _fill_missing(self, match: re.Match[str]) -> None:
        price = "price" in match.groupdict()
        active = (
            item
            for name, item in self.items.items()
            if not item.removed and self.only in (None, name)
        )
        missing = [item for item in active if item.needs_value(price)]
        if len(missing) != 1:
            raise BillQuestion(
                "Dla której pozycji podajesz wartość? Podaj jej nazwę oraz ilość lub cenę."
            )
        item = missing[0]
        if price:
            item.price, item.price_disputed = match["price"], False
        else:
            item.count, item.count_disputed = match["count"], False

    def _active(self, name: str) -> Item:
        item = self.items[self.resolve(name)]
        if item.removed:
            raise BillQuestion(
                f"Pozycja „{name}” została wycofana. Podaj pełną aktualną listę."
            )
        return item

    def _revise(self, clause: str) -> bool:
        if match := CHANGE_COUNT.fullmatch(clause):
            item = self._active(match["name"])
            item.count = match["count"]
            item.count_disputed = False
        elif match := CHANGE_FROM.fullmatch(clause):
            self._change_from(match)
        elif match := CHANGE_PRICE.fullmatch(clause):
            self._price(match, correction=" jednak " in clause or " teraz " in clause)
        elif match := ITEM_PRICE.fullmatch(clause):
            self._price(match, correction=False)
        elif match := UNKNOWN_COUNT.fullmatch(clause):
            if self.candidates(match["name"]):
                self.items[self.resolve(match["name"])].count = None
            else:
                self.add(match["name"], None, None)
        else:
            return False
        return True

    def _change_from(self, match: re.Match[str]) -> None:
        item = self._active(match["name"])
        price = match["field"] == "cenę"
        current = item.price if price else item.count
        new = match["new"].replace(",", ".")
        if current is None or calculate(current.replace(",", ".")) != calculate(
            match["old"].replace(",", ".")
        ):
            if price:
                item.price_disputed = True
            else:
                item.count_disputed = True
            return
        if price:
            item.price = new
            item.price_disputed = False
        elif (
            new.isdigit()
            and int(new) > 0
            and not (match["old_unit"] or match["new_unit"])
        ):
            item.count = new
            item.count_disputed = False
        else:
            raise BillQuestion(GENERIC)

    def _scope(self, clause: str) -> bool:
        if match := EXCLUDE.fullmatch(clause) or SEPARATELY.fullmatch(clause):
            self.items[self.resolve(match["name"])].removed = True
        elif match := SUBSET.fullmatch(clause):
            self.only = self.resolve(match["name"])
        elif TOTAL.fullmatch(clause):
            if any(
                word in clause
                for word in ("całość", "cały zestaw", "zamówienia", "łączny")
            ):
                self.only = None
        else:
            return False
        return True

    def _price(self, match: re.Match[str], *, correction: bool) -> None:
        name, price = match["name"], match["price"]
        if not correction and not self.candidates(name):
            self.add(name, None, price)
            return
        item = self._active(name)
        if item.price is not None and not correction:
            item.price_disputed = True
            return
        item.price = price
        item.price_disputed = False

    def result(self) -> str:
        terms = []
        lines = []
        for name, item in self.items.items():
            if item.removed or self.only not in (None, name):
                continue
            if item.price_disputed:
                raise BillQuestion(
                    f"Czy zmieniasz cenę pozycji „{name}”? Która cena jednostkowa jest aktualna?"
                )
            if item.count_disputed:
                raise BillQuestion(f"Jaka ilość pozycji „{name}” jest aktualna?")
            if item.count is None or item.price is None:
                missing = "ilość" if item.count is None else "cenę za sztukę w zł"
                raise BillQuestion(f"Podaj {missing} dla pozycji „{name}”.")
            terms.append(f"{item.count}*{item.price.replace(',', '.')}")
            lines.append(f"{name}: {item.count} × {item.price.replace('.', ',')} zł")
        if not terms:
            raise BillQuestion("Które pozycje uwzględnić w rachunku?")
        total = calculate("+".join(terms)).replace(".", ",")
        return "\n".join([*lines, f"Razem: {total} zł"])


def _checked_text(text: str) -> str:
    text = text.strip().lower()
    if not text or len(text) > 1600 or text.endswith((",", ";", ":", "..", "…")):
        raise BillQuestion(GENERIC)
    if any(ch.isdecimal() and not ch.isascii() for ch in text):
        raise BillQuestion(GENERIC)
    if text.rsplit(maxsplit=1)[-1] in {"i", "oraz", "plus"}:
        raise BillQuestion(GENERIC)
    return text


def _clauses(text: str) -> list[str]:
    text = _description(text)
    text = re.sub(r"\(po (" + PRICE + r")\)", r" po \1", text)
    text = re.sub(r",\s*każd[aye] (?:po|kosztuje) ", " po ", text)
    text = re.sub(r"\bnie wiadomo,\s*ile ", "nie wiadomo ile ", text)
    return [" ".join(part.split()) for part in SEPARATOR.split(text) if part.strip()]


def _description(text: str) -> str:
    body = CALCULATOR.sub("", PREFIX.sub("", text, count=1), count=1)
    return COST_QUESTION.sub("", body, count=1)


def _bare_value(text: str) -> bool:
    text = text.rstrip(".!").strip()
    return bool(SHORT_VALUE.fullmatch(text))


def _follow(text: str) -> bool:
    clause = SEPARATOR.split(text.strip().lower(), maxsplit=1)[0].strip()
    return bool(
        FOLLOW.match(text) or TOTAL.fullmatch(clause) or SUBSET.fullmatch(clause)
    ) or _bare_value(text)


def _starts(text: str) -> bool:
    if _bare_value(text):
        return False
    if PREFIX.match(text):
        return True
    if CALCULATOR.match(text) and not re.search(r"\bpo\s+\d", text, re.I):
        return False
    text = _description(text)
    monetary = PRICE_SIGNAL.search(text) or re.search(
        r"\b(?:koszt|zapłacę|do zapłaty)\b", text, re.I
    )
    return bool(OPENING.match(text) and re.search(r"\d", text) and monetary)


def _previous_prompts(records: list[dict[str, object]]) -> list[str] | None:
    prompts = []
    for index in range(len(records), max(1, len(records) - 16), -2):
        user, assistant = records[index - 2 : index]
        prompt = user.get("content")
        if assistant.get("content") == NEW_OR_CHANGE:
            return None
        if not (
            user.get("role") == "user"
            and assistant.get("role") == "assistant"
            and assistant.get("mode") == "studio_normal"
            and assistant.get("status") == "COMPLETED"
            and user.get("request_id")
            and user.get("request_id") == assistant.get("request_id")
            and isinstance(prompt, str)
        ):
            break
        prompt = prompt.strip()
        prompts.append(prompt)
        if _starts(prompt):
            return prompts[::-1]
        if not _follow(prompt):
            break
    else:
        if prompts:
            return None
    return []


def _bill_turns(message: str, history: list[dict[str, object]]) -> list[str] | None:
    if _starts(message):
        if not PREFIX.match(message) and _previous_prompts(history) != []:
            raise BillQuestion(NEW_OR_CHANGE)
        return [message]
    if not _follow(message):
        return None
    previous = _previous_prompts(history)
    if previous:
        return [*previous, message]
    named_change = any(
        rule.match(message.lower())
        for rule in (CHANGE_COUNT, CHANGE_PRICE, CHANGE_FROM)
    )
    if previous is None or named_change or _interrupted_bill(history):
        raise BillQuestion(MISSING_BASE)
    return None


def _interrupted_bill(history: list[dict[str, object]]) -> bool:
    # A cancelled/failed last bill cannot establish a usable previous subtotal.
    if len(history) < 2:
        return False
    user, assistant = history[-2:]
    text = user.get("content")
    return (
        assistant.get("mode") == "studio_normal"
        and assistant.get("status") != "COMPLETED"
        and isinstance(text, str)
        and (_starts(text.strip()) or _follow(text.strip()))
    )


def _short_field(text: str) -> str | None:
    match = SHORT_VALUE.fullmatch(text.strip().rstrip(".!").strip())
    if match is None:
        return None
    return "count" if match["unit"].casefold().startswith("sztuk") else "price"


def _clarifies(text: str, field: str | None) -> bool:
    if field is None:
        return False
    if _short_field(text) == field:
        return True
    clause = next(iter(_clauses(text.strip().lower())), "")
    if match := CHANGE_FROM.fullmatch(clause):
        return field == ("price" if match["field"] == "cenę" else "count")
    if field == "count":
        return CHANGE_COUNT.fullmatch(clause) is not None
    return bool(CHANGE_PRICE.fullmatch(clause) or ITEM_PRICE.fullmatch(clause))


def _replay(turns: list[str]) -> str:
    bill = Bill()
    question = ""
    disputed_field = None
    for text in turns:
        if question and not _clarifies(text, disputed_field):
            continue
        # A rejected edit may contain several clauses. Commit them together
        # only after every clause has been accounted for.
        proposed = deepcopy(bill)
        try:
            proposed.apply(text)
        except BillQuestion as exc:
            question, disputed_field = str(exc), _short_field(text)
        else:
            bill, question = proposed, ""
    return question or bill.result()


def studio_bill_reply(message: str, history: list[dict[str, object]]) -> str | None:
    """Build amounts exclusively from complete user clauses in this bill."""
    message = message.strip()
    try:
        turns = _bill_turns(message, history)
        if turns is None:
            return None
        if re.search(
            r"\b(?:nie wybraliśmy|nie wybrano) (?:jeszcze )?wariantu\b", message, re.I
        ):
            raise BillQuestion(
                "Który wariant i cenę jednostkową mam przyjąć do rachunku?"
            )
        return _replay(turns)
    except BillQuestion as exc:
        return str(exc)
    except CalculationError:
        return GENERIC
