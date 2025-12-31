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
