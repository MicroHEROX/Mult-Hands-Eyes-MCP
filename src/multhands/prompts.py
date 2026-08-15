"""Built-in vision prompt templates: a structured, machine-verifiable report
shape that a downstream model can consume without hallucinated detail. The
online model selects a mode (or writes its own prompt); the local vision
model gets the template verbatim.
"""

from typing import Literal

VisionMode = Literal["analyze", "ocr", "compare"]

#: Analyzer mode: one structured "# Image Analysis Report" with fixed sections.
ANALYZE_PROMPT = (
    "You are analyzing an image. Produce an '# Image Analysis Report' in Markdown "
    "with exactly these sections:\n"
    "1. Summary \u2014 a 2\u20134 sentence overview of the image.\n"
    "2. Image Metadata \u2014 type, style, and dominant color palette (with hex codes).\n"
    "3. Layout & Composition \u2014 spatial arrangement and visual hierarchy.\n"
    "4. Visible Text (VERBATIM) \u2014 every readable character exactly as written, "
    "in reading order; do NOT fix typos, do NOT drop or add symbols, do NOT rephrase.\n"
    "5. Objects & Elements \u2014 what is depicted.\n"
    "6. People & Actions \u2014 if any are present.\n"
    "7. Semantic Context & Inferences \u2014 grounded only in what is visible.\n"
    "8. Uncertainties & Gaps \u2014 honestly mark anything you cannot resolve instead of guessing."
)

#: OCR mode: character-exact text extraction, nothing else.
OCR_PROMPT = (
    "Extract ALL text from the image verbatim, character-exact, in reading order. "
    "Do NOT fix typos, do NOT drop or add symbols, do NOT rephrase, do NOT "
    "summarize. If a glyph cannot be resolved, note it explicitly in brackets. "
    "Output the raw text only."
)

#: Compare mode (2\u20134 images): one structured "# Image Comparison Report".
COMPARE_PROMPT = (
    "Compare the provided images together. Produce an '# Image Comparison Report' "
    "in Markdown with exactly these sections:\n"
    "1. Per-Image Summaries \u2014 one short paragraph per image.\n"
    "2. Common Elements \u2014 what the images share.\n"
    "3. Key Differences \u2014 how they differ.\n"
    "4. Text Differences (VERBATIM) \u2014 quote differing text exactly as written, "
    "character-exact, without fixing typos or rephrasing.\n"
    "5. Overall Conclusion \u2014 one paragraph tying it together."
)

#: The model-facing fidelity rule appended to tool descriptions.
VISION_FIDELITY_RULE = (
    "When relaying the local model's output, keep full fidelity: never rephrase, "
    "shorten, 'fix', or invent visual details the report did not return; preserve "
    "any uncertainty the report explicitly states."
)

VALID_MODES = ("analyze", "ocr", "compare")


def resolve_vision_prompt(mode: VisionMode, prompt: str | None = None) -> str:
    """Resolve the prompt for one call: a caller-supplied custom prompt wins;
    the mode template is the default.
    """
    if prompt is not None and prompt.strip():
        return prompt
    if mode == "analyze":
        return ANALYZE_PROMPT
    if mode == "ocr":
        return OCR_PROMPT
    if mode == "compare":
        return COMPARE_PROMPT
    raise ValueError(f"unknown vision mode {mode!r}; valid modes: {', '.join(VALID_MODES)}")
