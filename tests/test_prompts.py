import pytest

from multhands.prompts import (
    ANALYZE_PROMPT,
    COMPARE_PROMPT,
    OCR_PROMPT,
    VISION_FIDELITY_RULE,
    resolve_vision_prompt,
)


def test_resolve_default_modes():
    assert resolve_vision_prompt("analyze") == ANALYZE_PROMPT
    assert resolve_vision_prompt("ocr") == OCR_PROMPT
    assert resolve_vision_prompt("compare") == COMPARE_PROMPT


def test_custom_prompt_wins():
    custom = "What color is the car?"
    assert resolve_vision_prompt("analyze", custom) == custom
    assert resolve_vision_prompt("ocr", custom) == custom


def test_blank_custom_prompt_falls_back():
    assert resolve_vision_prompt("ocr", "   ") == OCR_PROMPT
    assert resolve_vision_prompt("analyze", "") == ANALYZE_PROMPT


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        resolve_vision_prompt("nope")  # type: ignore[arg-type]


def test_templates_shape():
    assert "# Image Analysis Report" in ANALYZE_PROMPT
    assert "# Image Comparison Report" in COMPARE_PROMPT
    assert "VERBATIM" in OCR_PROMPT or "verbatim" in OCR_PROMPT
    assert "verbatim" in ANALYZE_PROMPT.lower()
    assert "verbatim" in COMPARE_PROMPT.lower()


def test_fidelity_rule():
    assert "never rephrase" in VISION_FIDELITY_RULE