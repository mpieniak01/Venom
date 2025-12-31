from venom_core.utils.text import trim_to_char_limit


def test_trim_to_char_limit_under_limit():
    text = "abc"
    trimmed, flag = trim_to_char_limit(text, 10)
    assert trimmed == text
    assert flag is False


def test_trim_to_char_limit_exact_limit():
    text = "abcdefghij"
    trimmed, flag = trim_to_char_limit(text, 10)
    assert trimmed == text
    assert flag is False


def test_trim_to_char_limit_over_limit():
    text = "abcdefghijklmno"
    trimmed, flag = trim_to_char_limit(text, 10)
    assert trimmed == "abcdefghij"
    assert flag is True


def test_trim_to_char_limit_zero_limit():
    trimmed, flag = trim_to_char_limit("abc", 0)
    assert trimmed == ""
    assert flag is True


def test_trim_to_char_limit_negative_limit():
    """Test z limitem ujemnym."""
    trimmed, flag = trim_to_char_limit("Jakiś tekst", -5)
    assert trimmed == ""
    assert flag is True


def test_trim_to_char_limit_empty_text():
    """Test z pustym tekstem."""
    trimmed, flag = trim_to_char_limit("", 100)
    assert trimmed == ""
    assert flag is False


def test_trim_to_char_limit_unicode():
    """Test z tekstem zawierającym polskie znaki diakrytyczne i emoji."""
    text = "Zażółć gęślą jaźń 🎉"
    trimmed, flag = trim_to_char_limit(text, 10)
    assert trimmed == "Zażółć gęś"
    assert len(trimmed) == 10
    assert flag is True

