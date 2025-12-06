"""Testy jednostkowe dla PolicyEngine."""

import pytest

from venom_core.core.policy_engine import PolicyEngine


@pytest.fixture
def policy_engine():
    """Fixture dla PolicyEngine."""
    return PolicyEngine()


# --- Testy wykrywania kluczy API ---


def test_detect_openai_api_key(policy_engine):
    """Test wykrywania klucza OpenAI."""
    code = """
import openai
api_key = "sk-proj-abcdefghijklmnopqrstuvwxyz1234567890"
client = openai.Client(api_key=api_key)
"""
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("OpenAI" in v.message for v in violations)
    assert violations[0].severity == "critical"
    assert violations[0].rule == "hardcoded_credentials"


def test_detect_aws_access_key(policy_engine):
    """Test wykrywania klucza AWS."""
    code = 'aws_key = "AKIAIOSFODNN7EXAMPLE"'
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("AWS" in v.message for v in violations)


def test_detect_github_token(policy_engine):
    """Test wykrywania tokenu GitHub."""
    code = 'token = "ghp_1234567890abcdefghijklmnopqrstuv123456"'  # 36 chars after ghp_
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("GitHub" in v.message for v in violations)


def test_detect_google_api_key(policy_engine):
    """Test wykrywania klucza Google API."""
    # Using obviously fake test key that matches pattern (AIza + 35 chars) but won't trigger scanners
    code = 'api_key = "AIzaFAKE_TEST_KEY_01234567890abcdefgh12"'
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("Google" in v.message for v in violations)


def test_no_api_keys_clean_code(policy_engine):
    """Test braku wykrycia kluczy w czystym kodzie."""
    code = """
import os
api_key = os.getenv("OPENAI_API_KEY")
client = openai.Client(api_key=api_key)
"""
    violations = policy_engine.check_safety(code)
    # Mogą być inne naruszenia (np. brak docstrings), ale nie klucze
    api_key_violations = [v for v in violations if v.rule == "hardcoded_credentials"]
    assert len(api_key_violations) == 0


# --- Testy wykrywania niebezpiecznych komend ---


def test_detect_rm_rf(policy_engine):
    """Test wykrywania rm -rf /."""
    code = 'os.system("rm -rf /")'
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("dangerous_command" == v.rule for v in violations)
    assert violations[0].severity == "critical"


def test_detect_fork_bomb(policy_engine):
    """Test wykrywania fork bomb."""
    code = ":(){ :|:& };:"
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("Fork bomb" in v.message for v in violations)


def test_detect_mkfs(policy_engine):
    """Test wykrywania formatowania dysku."""
    code = 'subprocess.run("mkfs.ext4 /dev/sda1")'
    violations = policy_engine.check_safety(code)
    assert len(violations) > 0
    assert any("Formatowanie" in v.message for v in violations)


def test_safe_commands(policy_engine):
    """Test braku fałszywych alarmów dla bezpiecznych komend."""
    code = """
import subprocess
subprocess.run(["ls", "-la"])
subprocess.run(["git", "status"])
"""
    violations = policy_engine.check_safety(code)
    dangerous_violations = [v for v in violations if v.rule == "dangerous_command"]
    assert len(dangerous_violations) == 0


# --- Testy sprawdzania docstringów ---


def test_detect_missing_function_docstring(policy_engine):
    """Test wykrywania braku docstringa w funkcji."""
    code = """
def calculate_sum(a, b):
    return a + b
"""
    violations = policy_engine.check_safety(code)
    docstring_violations = [v for v in violations if v.rule == "missing_docstring"]
    assert len(docstring_violations) > 0
    assert any("funkcja" in v.message for v in docstring_violations)


def test_detect_missing_class_docstring(policy_engine):
    """Test wykrywania braku docstringa w klasie."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    violations = policy_engine.check_safety(code)
    docstring_violations = [v for v in violations if v.rule == "missing_docstring"]
    assert len(docstring_violations) > 0
    assert any("klasa" in v.message for v in docstring_violations)


def test_function_with_docstring(policy_engine):
    """Test braku fałszywych alarmów dla funkcji z docstringiem."""
    code = '''
def calculate_sum(a, b):
    """Oblicza sumę dwóch liczb."""
    return a + b
'''
    violations = policy_engine.check_safety(code)
    # Nie powinno być naruszeń dla tej funkcji
    # (mogą być inne naruszenia w kodzie, ale nie missing_docstring dla tej funkcji)
    docstring_violations = [v for v in violations if v.rule == "missing_docstring"]
    assert len(docstring_violations) == 0


def test_ignore_private_methods(policy_engine):
    """Test ignorowania metod prywatnych."""
    code = """
class MyClass:
    def _private_method(self):
        pass

    def __magic_method__(self):
        pass
"""
    violations = policy_engine.check_safety(code)
    docstring_violations = [v for v in violations if v.rule == "missing_docstring"]
    # Metody prywatne i magiczne powinny być zignorowane
    # (może być naruszenie dla klasy, ale nie dla metod)
    method_violations = [v for v in docstring_violations if "funkcja" in v.message]
    assert len(method_violations) == 0


def test_non_python_code_no_docstring_check(policy_engine):
    """Test braku sprawdzania docstringów dla kodu nie-Python."""
    code = """
function calculateSum(a, b) {
    return a + b;
}
"""
    violations = policy_engine.check_safety(code)
    # Nie powinno być sprawdzania docstringów dla JavaScript
    docstring_violations = [v for v in violations if v.rule == "missing_docstring"]
    assert len(docstring_violations) == 0


# --- Testy kompleksowe ---


def test_multiple_violations(policy_engine):
    """Test wykrywania wielu naruszeń jednocześnie."""
    code = """
api_key = "sk-proj-test123456789012345678901234"

def unsafe_function():
    os.system("rm -rf /tmp/test")
    return api_key
"""
    violations = policy_engine.check_safety(code)
    assert len(violations) >= 2  # Klucz API + brak docstringa (minimum)

    # Sprawdź że są różne typy naruszeń
    rules = {v.rule for v in violations}
    assert "hardcoded_credentials" in rules


def test_line_number_reporting(policy_engine):
    """Test raportowania numerów linii."""
    code = """line 1
line 2
api_key = "sk-proj-test123456789012345678901234"
line 4
"""
    violations = policy_engine.check_safety(code)
    api_violations = [v for v in violations if v.rule == "hardcoded_credentials"]
    assert len(api_violations) > 0
    assert api_violations[0].line_number == 3  # Linia z kluczem API


def test_empty_code(policy_engine):
    """Test pustego kodu."""
    violations = policy_engine.check_safety("")
    assert violations == []


def test_clean_code_minimal_violations(policy_engine):
    """Test czystego kodu z minimalnymi naruszeniami."""
    code = '''
import os

def get_api_key():
    """Pobiera klucz API ze zmiennych środowiskowych."""
    return os.getenv("API_KEY", "default")

class ApiClient:
    """Klient API."""

    def __init__(self):
        """Inicjalizacja."""
        self.key = get_api_key()
'''
    violations = policy_engine.check_safety(code)
    # Powinny być maksymalnie drobne naruszenia lub wcale
    critical_violations = [v for v in violations if v.severity == "critical"]
    assert len(critical_violations) == 0
