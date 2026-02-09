from venom_core.utils.markdown_blocks import extract_fenced_block, strip_fenced_blocks


def test_extract_fenced_block_without_language():
    text = "A\n```python\nprint('x')\n```\nB"
    assert extract_fenced_block(text) == "print('x')"


def test_extract_fenced_block_with_language_filter():
    text = "A\n```json\n{}\n```\nC\n```python\nx = 1\n```\nD"
    assert extract_fenced_block(text, language="python") == "x = 1"
    assert extract_fenced_block(text, language="yaml") is None


def test_extract_fenced_block_handles_missing_terminators():
    assert extract_fenced_block("```python") is None
    assert extract_fenced_block("```python\nx = 1") is None


def test_strip_fenced_blocks_removes_all_closed_blocks():
    text = "Start\n```txt\none\n```\nMiddle\n```python\nx=1\n```\nEnd"
    stripped = strip_fenced_blocks(text)
    assert "one" not in stripped
    assert "x=1" not in stripped
    assert "Start" in stripped
    assert "Middle" in stripped
    assert "End" in stripped


def test_strip_fenced_blocks_keeps_text_when_block_is_unclosed():
    text = "Intro\n```python\nx = 1"
    assert strip_fenced_blocks(text) == text
