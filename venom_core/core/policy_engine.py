"""Moduł: policy_engine - silnik weryfikacji zgodności i bezpieczeństwa."""

import re
from typing import List, Literal

from pydantic import BaseModel

from venom_core.utils.logger import get_logger

logger = get_logger(__name__)


class Violation(BaseModel):
    """Reprezentacja naruszenia zasad bezpieczeństwa lub jakości kodu."""

    rule: str  # Nazwa reguły
    severity: Literal["critical", "high", "medium", "low"]  # Poziom ważności
    message: str  # Opis naruszenia
    line_number: int | None = None  # Numer linii (jeśli możliwy do określenia)


class PolicyEngine:
    """Silnik polityk bezpieczeństwa i jakości kodu."""

    # Reguły regex dla wykrywania kluczy API
    API_KEY_PATTERNS = [
        (r"sk-proj-[a-zA-Z0-9]{20,}", "OpenAI Project API Key"),
        (r"sk-[a-zA-Z0-9]{48}", "OpenAI API Key"),
        (r"AKIA[0-9A-Z]{16}", "AWS Access Key"),
        (r"ghp_[a-zA-Z0-9]{36}", "GitHub Personal Access Token"),
        (r"gho_[a-zA-Z0-9]{36}", "GitHub OAuth Token"),
        (r"AIza[0-9A-Za-z_-]{35}", "Google API Key"),
        (r"[0-9]+-[0-9A-Za-z_]{32}\.apps\.googleusercontent\.com", "Google OAuth"),
    ]

    # Niebezpieczne komendy shell
    DANGEROUS_COMMANDS = [
        (r"rm\s+-rf\s+/", "Usuwanie katalogu głównego"),
        (r":\(\)\{\s*:\|:&\s*\};:", "Fork bomb"),
        (r"mkfs\.", "Formatowanie dysku"),
        (r"dd\s+if=/dev/zero", "Nadpisywanie dysku"),
        (r">\s*/dev/sd[a-z]", "Bezpośredni zapis na dysk"),
        (r"push.*--force", "Git push --force (może nadpisać historię)"),
        (
            r"push[^\n]*-f\b",
            "Git push -f (może nadpisać historię)",
        ),  # -f as standalone flag
    ]

    def check_safety(self, content: str) -> List[Violation]:
        """
        Sprawdza bezpieczeństwo i jakość kodu.

        Args:
            content: Kod do sprawdzenia

        Returns:
            Lista naruszeń (jeśli pusta - kod jest bezpieczny)
        """
        violations: List[Violation] = []

        # Sprawdź klucze API
        violations.extend(self._check_api_keys(content))

        # Sprawdź niebezpieczne komendy
        violations.extend(self._check_dangerous_commands(content))

        # Sprawdź docstringi (tylko dla kodu Python)
        if self._is_python_code(content):
            violations.extend(self._check_docstrings(content))

        if violations:
            logger.warning(f"PolicyEngine wykrył {len(violations)} naruszeń")
        else:
            logger.info("PolicyEngine: kod przeszedł kontrolę bezpieczeństwa")

        return violations

    def _check_api_keys(self, content: str) -> List[Violation]:
        """Wykrywa hardcodowane klucze API."""
        violations = []

        for pattern, key_type in self.API_KEY_PATTERNS:
            matches = re.finditer(pattern, content)
            for match in matches:
                line_num = content[: match.start()].count("\n") + 1
                violations.append(
                    Violation(
                        rule="hardcoded_credentials",
                        severity="critical",
                        message=f"Wykryto hardcodowany klucz: {key_type}. Użyj zmiennych środowiskowych.",
                        line_number=line_num,
                    )
                )

        return violations

    def _check_dangerous_commands(self, content: str) -> List[Violation]:
        """Wykrywa niebezpieczne komendy shell."""
        violations = []

        for pattern, description in self.DANGEROUS_COMMANDS:
            matches = re.finditer(pattern, content)
            for match in matches:
                line_num = content[: match.start()].count("\n") + 1
                violations.append(
                    Violation(
                        rule="dangerous_command",
                        severity="critical",
                        message=f"Niebezpieczna komenda wykryta: {description}",
                        line_number=line_num,
                    )
                )

        return violations

    def _check_docstrings(self, content: str) -> List[Violation]:
        """Sprawdza obecność docstringów w funkcjach i klasach Python."""
        violations = []

        # Wykryj definicje funkcji/klas bez docstringów
        # Pattern: def/class następuje po nim brak """ lub '''
        function_pattern = (
            r"(def\s+\w+\s*\([^)]*\)\s*(?:->.*?)?\s*:(?!\s*(?:\"\"\"|''')))"
        )
        class_pattern = r"(class\s+\w+.*?:(?!\s*(?:\"\"\"|''')))"

        for pattern, entity_type in [
            (function_pattern, "funkcja"),
            (class_pattern, "klasa"),
        ]:
            matches = re.finditer(pattern, content, re.MULTILINE)
            for match in matches:
                line_num = content[: match.start()].count("\n") + 1
                # Sprawdź czy to nie jest metoda prywatna/magiczna (możemy je pominąć)
                if not re.search(r"def\s+(__\w+__|_\w+)\s*\(", match.group(0)):
                    violations.append(
                        Violation(
                            rule="missing_docstring",
                            severity="medium",
                            message=f"Brak docstringa dla {entity_type}",
                            line_number=line_num,
                        )
                    )

        return violations

    def _is_python_code(self, content: str) -> bool:
        """Sprawdza czy zawartość to kod Python."""
        # Prosta heurystyka - obecność typowych słów kluczowych Python
        python_keywords = ["def ", "class ", "import ", "from ", "if __name__"]
        return any(keyword in content for keyword in python_keywords)
