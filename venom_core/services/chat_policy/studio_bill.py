"""Verify complete PLN bills from item-bound facts stated by the user."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from venom_core.services.grounded_calculator import CalculationError, calculate

# Each recognized statement must consume its entire clause. A number from a
# different product or an unparsed modifier cannot become a calculator operand.
NAME = r"(?P<name>[a-ząćęłńóśźż]+(?:-[a-ząćęłńóśźż]+)?)"
COUNT = r"(?P<count>[1-9][0-9]{0,5})"
PRICE = r"(?P<price>(?:0|[1-9][0-9]{0,6})(?:[.,][0-9]{1,2})?) (?:zł|pln)"
UNIT = r"(?: za sztukę)?"
PREFIX = re.compile(r"^(?:nowy )?rachunek\s*:\s*", re.I)
OPENING = re.compile(
    r"^(?:kupuję|kupił[ea]m|zamawiam|potrzebuję|w koszyku|wypożyczył[ea]m|zestaw obejmuje|"
    r"chcę policzyć koszt|są w ofercie|za wydruk:|za [0-9]|[0-9])",
    re.I,
)
PRICE_SIGNAL = re.compile(r"\b(?:zł|pln|euro|eur|groszy)\b", re.I)
FOLLOW = re.compile(
    r"^(?:zmień (?:cenę|ilość|liczbę)|zmieniam (?:cenę|ilość|liczbę)|korekta\b|cena\b|wycofaj\b|pomiń\b|dolicz\b|dodaj\b|zamiast\b|"
    r"ile (?:razem|za|zapłacę|płacę|zostało)|podaj sumę\b|interesują mnie (?:wyłącznie|tylko)\b|(?:policz )?tylko\b|"
    r"[\w-]+ (?:opłacono|kosztuj\w*|po [0-9]))",
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
    r"(?P<old>[0-9]+(?:[.,][0-9]{1,2})?)(?P<old_unit> zł)? na "
    r"(?P<new>[0-9]{1,7}(?:[.,][0-9]{1,2})?)(?P<new_unit> zł)?"
)
EXCLUDE = re.compile(rf"(?:wycofaj|pomiń) {NAME}(?: z rachunku)?")
SEPARATELY = re.compile(rf"{NAME} opłacono osobno")
SUBSET = re.compile(
    rf"(?:interesują mnie (?:tylko|wyłącznie)|teraz rozliczamy tylko|"
    rf"(?:policz )?tylko|jaki jest koszt samych|ile zostało do zapłaty za) {NAME}"
)
TOTAL = re.compile(
    r"(?:jaki jest łączny koszt|ile (?:razem|płacę|zapłacę|to (?:kosztuje|wyniesie))|"
    r"ile (?:zapłacę )?za (?:całość|cały zestaw)|podaj sumę(?: zamówienia)?)"
)
FILLER = "cena jednostkowa obu pozycji bez zmian"
# Protect decimal separators, including in the middle of a sentence.
SEPARATOR = re.compile(r"[;\n!?]|(?<![0-9])[.,]|[.,](?![0-9])| (?:i|oraz|plus) ")
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
        if len(text) > 1600 or re.search(
            r"(?:\b(?:i|oraz|plus)|[,;:]|\.{2,}|…)\s*$", text, re.I
        ):
            raise BillQuestion(GENERIC)
        text = PREFIX.sub("", text.strip().lower(), count=1)
        text = re.sub(r"\s*\(po (" + PRICE + r")\)", r" po \1", text)
        text = re.sub(r",\s*każd[aye] (?:po|kosztuje) ", " po ", text)
        text = re.sub(r"\bnie wiadomo,\s*ile ", "nie wiadomo ile ", text)
        clauses = SEPARATOR.split(text)
        offer: str | None = None
        selected_in_turn = None
        for raw in clauses:
            clause = " ".join(raw.split())
            if not clause:
                continue
            if selected := SUBSET.fullmatch(clause):
                name = self.resolve(selected["name"])
                if selected_in_turn not in (None, name):
                    raise BillQuestion(
                        "Które pozycje mam zsumować? Podaj jeden zakres rachunku."
                    )
                selected_in_turn = name
            if match := UNIT_OFFER.fullmatch(clause):
                offer = match["name"]
                self.add(offer, None, match["price"])
                continue
            if offer and (match := ORDER_COUNT.fullmatch(clause)):
                self.items[offer].count = match["count"]
            else:
                self._apply_clause(clause)
            offer = None

    def _apply_clause(self, clause: str) -> None:
        if match := ROW.fullmatch(INTRO.sub("", clause, count=1)):
            self.add(match["name"], match["count"], match["price"])
        elif not (self._revise(clause) or self._scope(clause) or clause == FILLER):
            raise BillQuestion(GENERIC)

    def _active(self, name: str) -> Item:
        item = self.items[self.resolve(name)]
        if item.removed:
            raise BillQuestion(
                f"Pozycja „{name}” została wycofana. Podaj pełną aktualną listę."
            )
        return item

    def _revise(self, clause: str) -> bool:
        if match := CHANGE_COUNT.fullmatch(clause):
            self._active(match["name"]).count = match["count"]
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
            raise BillQuestion(
                "Poprzednia wartość nie zgadza się z rachunkiem. Która wartość jest aktualna?"
            )
        if price:
            item.price = new
        elif (
            new.isdigit()
            and int(new) > 0
            and not (match["old_unit"] or match["new_unit"])
        ):
            item.count = new
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
            raise BillQuestion(
                f"Czy zmieniasz cenę pozycji „{name}”? Podaj aktualną cenę jednostkową."
            )
        item.price = price

    def result(self) -> str:
        terms = []
        lines = []
        for name, item in self.items.items():
            if item.removed or self.only not in (None, name):
                continue
            if item.count is None or item.price is None:
                missing = "ilość" if item.count is None else "cenę za sztukę w zł"
                raise BillQuestion(f"Podaj {missing} dla pozycji „{name}”.")
            terms.append(f"{item.count}*{item.price.replace(',', '.')}")
            lines.append(f"{name}: {item.count} × {item.price.replace('.', ',')} zł")
        if not terms:
            raise BillQuestion("Które pozycje uwzględnić w rachunku?")
        total = calculate("+".join(terms)).replace(".", ",")
        return "\n".join([*lines, f"Razem: {total} zł"])


def _starts(text: str) -> bool:
    if PREFIX.match(text):
        return True
    monetary = PRICE_SIGNAL.search(text) or re.search(
        r"\b(?:koszt|zapłacę|do zapłaty)\b", text, re.I
    )
    return bool(OPENING.match(text) and re.search(r"[0-9]", text) and monetary)


def _previous_prompts(records: list[dict[str, object]]) -> list[str]:
    prompts = []
    for index in range(len(records), max(1, len(records) - 16), -2):
        user, assistant = records[index - 2 : index]
        prompt = user.get("content")
        if assistant.get("content") == NEW_OR_CHANGE:
            break
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
        if not FOLLOW.match(prompt):
            break
    return []


def studio_bill_reply(message: str, history: list[dict[str, object]]) -> str | None:
    """Build amounts exclusively from complete user clauses in this bill."""
    message = message.strip()
    prompts: list[str] = []
    if _starts(message) and not PREFIX.match(message) and _previous_prompts(history):
        return NEW_OR_CHANGE
    if not _starts(message):
        if not FOLLOW.match(message):
            return None
        prompts = _previous_prompts(history)
        if not prompts:
            if any(
                rule.match(message.lower())
                for rule in (CHANGE_COUNT, CHANGE_PRICE, CHANGE_FROM)
            ):
                return MISSING_BASE
            return None
    if re.search(
        r"\b(?:nie wybraliśmy|nie wybrano) (?:jeszcze )?wariantu\b", message, re.I
    ):
        return "Który wariant i cenę jednostkową mam przyjąć do rachunku?"
    bill = Bill()
    try:
        for text in [*prompts, message]:
            bill.apply(text)
        return bill.result()
    except BillQuestion as exc:
        return str(exc)
    except CalculationError:
        return GENERIC
