# @patch Decorator Order - Definitive Guide

## The Problem

The `test_cancel_job_with_cleanup` test was failing repeatedly due to incorrect parameter order with stacked `@patch` decorators.

## The Rule (VERIFIED)

When using multiple `@patch` decorators, **the parameters must be ordered from bottom to top**:

```python
@patch("A")  # TOP decorator - applied SECOND
@patch("B")  # BOTTOM decorator - applied FIRST
def test_func(
    param1,  # Receives mock for B (BOTTOM decorator)
    param2,  # Receives mock for A (TOP decorator)
):
```

## Verification Test

Created a simple test to prove this behavior:

```python
from unittest.mock import patch

@patch("os.path.exists")  # TOP decorator
@patch("os.path.isfile")  # BOTTOM decorator  
def test_order(param1, param2):
    print(f"param1._mock_name: {param1._mock_name}")
    print(f"param2._mock_name: {param2._mock_name}")

test_order()
```

**Output:**
```
param1._mock_name: isfile   # BOTTOM decorator
param2._mock_name: exists   # TOP decorator
```

**Conclusion:** param1 receives BOTTOM decorator, param2 receives TOP decorator.

## Why This Happens

Decorators are syntactic sugar for nested function calls. This:

```python
@patch("A")
@patch("B")
def test():
    pass
```

Is equivalent to:

```python
test = patch("A")(patch("B")(test))
```

So `patch("B")` wraps the original function first, then `patch("A")` wraps that result. When the test runs:
1. The innermost wrapper (B) passes its mock as the first parameter
2. The outer wrapper (A) passes its mock as the second parameter

## The Correct Implementation

For `test_cancel_job_with_cleanup`:

```python
@patch("venom_core.api.routes.academy._update_job_in_history")  # TOP
@patch("venom_core.api.routes.academy._load_jobs_history")      # BOTTOM
def test_cancel_job_with_cleanup(
    mock_load_jobs_history,        # ✅ Receives BOTTOM decorator
    mock_update_job_in_history,    # ✅ Receives TOP decorator
    # ... other fixtures
):
    mock_load_jobs_history.return_value = [...]
    mock_update_job_in_history.return_value = None
```

## Common Mistakes

### Mistake 1: Visual Order
❌ **Wrong thinking:** "Parameters should match visual order (top to bottom)"

```python
@patch("A")  # TOP
@patch("B")  # BOTTOM
def test(param_A, param_B):  # ❌ WRONG
    pass
```

### Mistake 2: Application Order
❌ **Wrong thinking:** "A is applied second, so it should be second parameter"

Actually, A is applied second in the wrapping process, but it becomes the OUTER wrapper, so its mock is passed AFTER the inner wrapper's mock.

## The Right Way to Think

**Think of it as "inside-out parameter passing":**

1. The innermost decorator (BOTTOM) gets to pass its parameter first
2. The next decorator out (moving UP) passes its parameter second
3. And so on...

So read the decorators from **BOTTOM to TOP** when ordering parameters.

## Debugging Tips

If you're unsure about the order:

1. **Check mock names:**
   ```python
   def test_something(mock1, mock2):
       print(f"mock1: {mock1._mock_name}")
       print(f"mock2: {mock2._mock_name}")
   ```

2. **Use descriptive names:**
   Name your parameters to match what they're mocking, not the decorator order.

3. **Verify with a simple test:**
   Create a minimal test with `os.path` functions to verify the behavior.

## History of This Bug

This test went through multiple incorrect "fixes":

1. **Commit 0d80307:** Incorrectly swapped parameters thinking they should match visual order
2. **Commit a6d5f3d:** Fixed function name but kept wrong parameter order
3. **Commit f7dd0af:** VERIFIED with test and fixed correctly

The key lesson: **When debugging decorator issues, create a verification test first.**

## References

- Python documentation: [unittest.mock.patch](https://docs.python.org/3/library/unittest.mock.html#unittest.mock.patch)
- PEP 318: [Decorators for Functions and Methods](https://www.python.org/dev/peps/pep-0318/)

---

**Created:** 2026-02-11  
**Last Updated:** 2026-02-11  
**Status:** RESOLVED in commit f7dd0af
