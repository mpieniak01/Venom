"""Bounded proofs for single drafts and explicit claims about evaporation."""

import re

_PARAGRAPH = re.compile(r"\n[ \t]*\n")
_HUMID_FLOW = (
    r"wiatr (?:dostarcza|doprowadza|nawiewa)"
    r"(?: do niej| do tkaniny| przy tkaninie| nad powierzchnię)? wilgotn[ey] powietrze"
)
_BAD_MECHANISM = re.compile(
    rf"(?:wiatr przyspiesza (?:parowanie|schnięcie|wysychanie),? "
    rf"(?:bo|ponieważ) (?:(?:{_HUMID_FLOW})|"
    rf"(?:dostarcza|doprowadza|nawiewa) wilgotn[ey] powietrze)"
    rf"|(?:woda|wilgoć) z (?:[\w-]+ ){{1,5}}"
    rf"(?:ucieka z powierzchni|paruje) szybciej, gdy {_HUMID_FLOW}, "
    rf"co przyspiesza (?:parowanie|schnięcie|wysychanie))[.!]",
    re.IGNORECASE,
)
_QUALIFIED = re.compile(
    r"\b(?:mniej wilgotn\w+|suchsz\w+|względn\w+ wilgotno\w+|"
    r"nie|nieprawd\w+|fałsz\w*|mit\b|cytat\b|hipotez\w+)\b",
    re.I,
)
_KINDS = {"single_draft", "evaporation"}


def text_expectation(case: dict) -> dict | None:
    """Read an explicitly selected proof type for one content criterion."""
    if "text_check" not in case:
        return None
    rule = case["text_check"]
    if (
        not isinstance(rule, dict)
        or rule.keys() != {"criterion", "kind"}
        or not isinstance(rule["kind"], str)
        or rule["kind"] not in _KINDS
        or not any(
            item["id"] == rule["criterion"] and item.get("kind") == "content"
            for item in case["criteria"]
        )
    ):
        raise ValueError("conversation_review_text_rule_invalid")
    return rule


def _repeated_body(text: str) -> list[str]:
    first: dict[str, str] = {}
    for paragraph in _PARAGRAPH.split(text):
        quote = paragraph.strip()
        normalized = " ".join(quote.split())
        # Salutations, signatures, and short labels are not draft bodies.
        if len(normalized.split()) < 12:
            continue
        if normalized in first:
            return [first[normalized], quote]
        first[normalized] = quote
    return []


def _wrong_evaporation(text: str) -> list[str]:
    if len(text) > 240 or _QUALIFIED.search(text):
        return []
    return [text] if _BAD_MECHANISM.fullmatch(text) else []


def text_proof(answer: dict, expected: dict | None) -> dict | None:
    """Emit a negative proof for clear cases. All other text stays with the reviewer."""
    if expected is None or answer.get("finish") == "length":
        return None
    text = answer["text"].strip()
    critical = expected["kind"] == "evaporation"
    quotes = _wrong_evaporation(text) if critical else _repeated_body(text)
    if not quotes:
        return None
    return {
        "criterion": expected["criterion"],
        "kind": expected["kind"],
        "quotes": quotes,
        "critical": critical,
    }
