"""Small Decimal calculator for evidence-bound answers; never executes Python."""

from __future__ import annotations

import ast
import operator
import re
from decimal import Decimal, DecimalException, localcontext

MAX_EXPRESSION_CHARS = 160
MAX_MAGNITUDE = Decimal("1e12")
_DECIMAL_LITERAL = re.compile(r"(?:\d+(?:\.\d*)?|\.\d+)", re.ASCII)
_BINARY_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


class CalculationError(ValueError):
    """An expression is unsupported or exceeds the bounded arithmetic contract."""


def _evaluate_node(node: ast.AST, expression: str, depth: int) -> Decimal:
    if isinstance(node, ast.Constant) and type(node.value) in (int, float):
        literal = ast.get_source_segment(expression, node) or ""
        if not _DECIMAL_LITERAL.fullmatch(literal):
            raise CalculationError("calculation_literal_unsupported")
        return Decimal(literal)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _visit(node.operand, expression, depth + 1)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.BinOp):
        left = _visit(node.left, expression, depth + 1)
        right = _visit(node.right, expression, depth + 1)
        operation = _BINARY_OPERATORS.get(type(node.op))
        if operation is None:
            raise CalculationError("calculation_operator_unsupported")
        return operation(left, right)
    raise CalculationError("calculation_syntax_unsupported")


def _visit(node: ast.AST, expression: str, depth: int = 0) -> Decimal:
    if depth > 16:
        raise CalculationError("calculation_depth_limit")
    value = _evaluate_node(node, expression, depth)
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


def result_with_unit(expression: str, unit: str | None) -> dict[str, str | None]:
    """Expose a numeric result and its declared display unit without conversion."""
    if not expression:
        return {"status": "missing_expression", "value": None, "unit": unit}
    try:
        value = calculate(expression)
    except CalculationError:
        return {"status": "invalid_expression", "value": None, "unit": unit}
    return {"status": "succeeded", "value": value, "unit": unit}
