"""
Moduł: code_generation_utils - Narzędzia do bezpiecznego generowania kodu.

Zawiera funkcje pomocnicze do eskejpowania i sanityzacji
wartości używanych w generowanym kodzie Python.
"""


def escape_string_for_code(value: str) -> str:
    """
    Bezpiecznie eskejpuje string do użycia w generowanym kodzie.

    Używa repr() aby uniknąć problemów z cudzysłowami, backslashami
    i innymi znakami specjalnymi, które mogłyby złamać składnię Python
    lub wprowadzić lukę w zabezpieczeniach (code injection).

    Args:
        value: Wartość do eskejpowania

    Returns:
        Bezpiecznie eskejpowana wartość (używa repr())

    Example:
        >>> escape_string_for_code("hello")
        "'hello'"
        >>> escape_string_for_code("it's")
        '"it\'s"'
        >>> escape_string_for_code('test"; drop table')
        '\'test"; drop table\''
    """
    return repr(value)
