"""
Przykład użycia: Intent Parsing - Standalone Demo

Демонstracja parsowania intencji bez pełnych zależności.
"""

import re


def parse_intent_simple(content: str) -> dict:
    """
    Uproszczone parsowanie intencji - demonstracja regex.

    Args:
        content: Tekst użytkownika

    Returns:
        Dict z action i targets
    """
    # Wzorzec dla ścieżek plików
    file_path_pattern = r"[\w/\-\.]+\.(py|js|ts|txt|md|json|yaml|yml|html|css|java|go|rs|cpp|c|h)"

    # Wyciągnij ścieżki
    targets = []
    for match in re.finditer(file_path_pattern, content, re.IGNORECASE):
        targets.append(match.group(0))

    # Wykryj akcję
    action = "unknown"
    content_lower = content.lower()

    if any(
        word in content_lower
        for word in ["edytuj", "popraw", "zmień", "edit", "fix", "modify"]
    ):
        action = "edit"
    elif any(word in content_lower for word in ["stwórz", "utwórz", "create"]):
        action = "create"
    elif any(word in content_lower for word in ["usuń", "delete", "remove"]):
        action = "delete"
    elif any(word in content_lower for word in ["czytaj", "pokaż", "read", "show"]):
        action = "read"

    return {"action": action, "targets": targets}


def demo_intent_parsing():
    """Demonstracja parsowania intencji."""
    print("=" * 70)
    print("DEMO: Parsowanie Intencji (Intent Parsing) - Standalone")
    print("=" * 70)
    print()
    print("Implementacja z PR #7: Cognitive Logic v1.0")
    print()

    test_cases = [
        "proszę popraw błąd w pliku venom_core/main.py",
        "stwórz nowy plik test.py i utils.py",
        "usuń stary kod z old_code.py",
        "pokaż mi zawartość readme.md",
        "edytuj src/components/header.js i tests/test_main.py",
        "zmień config.yaml, script.ts, style.css i data.json",
        "napisz kod który oblicza sumę",  # bez plików
    ]

    for i, text in enumerate(test_cases, 1):
        print(f"{i}. Tekst użytkownika:")
        print(f"   '{text}'")
        intent = parse_intent_simple(text)
        print(f"   → Akcja: {intent['action']}")
        if intent["targets"]:
            print(f"   → Cele:  {', '.join(intent['targets'])}")
        else:
            print(f"   → Cele:  (brak wykrytych plików)")
        print()

    print("=" * 70)
    print("✓ Demo zakończone!")
    print()
    print("UWAGA: Pełna implementacja w venom_core/core/dispatcher.py")
    print("       wykorzystuje również LLM fallback gdy regex nie wystarczy.")
    print("=" * 70)


if __name__ == "__main__":
    demo_intent_parsing()
