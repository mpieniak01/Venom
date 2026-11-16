"""Small Decimal calculator for evidence-bound answers; never executes Python."""

from __future__ import annotations

import ast
import re
from decimal import Decimal, DecimalException, localcontext

MAX_EXPRESSION_CHARS = 160
MAX_MAGNITUDE = Decimal("1e12")


class CalculationError(ValueError):
    """An expression is unsupported or exceeds the bounded arithmetic contract."""


def _visit(node: ast.AST, expression: str, depth: int = 0) -> Decimal:
    if depth > 16:
        raise CalculationError("calculation_depth_limit")
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        literal = ast.get_source_segment(expression, node) or ""
        if not re.fullmatch(r"(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)", literal):
            raise CalculationError("calculation_literal_unsupported")
        value = Decimal(literal)
    elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _visit(node.operand, expression, depth + 1)
        if isinstance(node.op, ast.USub):
            value = -value
    elif isinstance(node, ast.BinOp):
        left = _visit(node.left, expression, depth + 1)
        right = _visit(node.right, expression, depth + 1)
        if isinstance(node.op, ast.Add):
            value = left + right
        elif isinstance(node.op, ast.Sub):
            value = left - right
        elif isinstance(node.op, ast.Mult):
            value = left * right
        elif isinstance(node.op, ast.Div):
            value = left / right
        else:
            raise CalculationError("calculation_operator_unsupported")
    else:
        raise CalculationError("calculation_syntax_unsupported")
    if not value.is_finite() or abs(value) > MAX_MAGNITUDE:
        raise CalculationError("calculation_magnitude_limit")
    return value


def calculate(expression: str) -> str:
    """Return a canonical decimal; cap syntax, precision and intermediate values."""
    if (
        not isinstance(expression, str)
        or not 1 <= len(expression) <= MAX_EXPRESSION_CHARS
    ):
        raise CalculationError("calculation_length_limit")
    try:
        tree = ast.parse(expression.strip(), mode="eval")
        if len(list(ast.walk(tree))) > 64:
            raise CalculationError("calculation_node_limit")
        with localcontext() as context:
            context.prec = 28
            value = _visit(tree.body, expression.strip())
            result = format(value.normalize(), "f")
        if len(result) > 160:
            raise CalculationError("calculation_result_limit")
        return "0" if value == 0 else result
    except (SyntaxError, DecimalException, RecursionError) as exc:
        raise CalculationError("calculation_invalid") from exc
