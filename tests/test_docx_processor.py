from __future__ import annotations

import pytest

from src.docx_processor import LogicalText, RunSpan, TextReplacement


def test_entity_span_maps_across_fragmented_word_runs() -> None:
    logical = LogicalText.from_run_texts(["Sarthak ", "Malvadkar", " is listed"])

    assert logical.text == "Sarthak Malvadkar is listed"
    assert logical.map_span(0, 17) == (
        RunSpan(run_index=0, start_in_run=0, end_in_run=8),
        RunSpan(run_index=1, start_in_run=0, end_in_run=9),
    )


def test_cross_run_replacement_preserves_unaffected_text_and_run_count() -> None:
    logical = LogicalText.from_run_texts(["Contact: Sar", "thak Mal", "vadkar today"])
    start = logical.text.index("Sarthak")
    end = start + len("Sarthak Malvadkar")

    rewritten = logical.rewrite_runs([TextReplacement(start, end, "Arjun Mehta")])

    assert rewritten == ("Contact: Arjun Mehta", "", " today")
    assert "".join(rewritten) == "Contact: Arjun Mehta today"


def test_multiple_non_overlapping_replacements_in_one_run() -> None:
    logical = LogicalText.from_run_texts(["Alice emailed a@example.test."])
    replacements = [
        TextReplacement(0, 5, "Priya"),
        TextReplacement(14, 28, "p@example.com"),
    ]

    assert logical.rewrite_runs(replacements) == ("Priya emailed p@example.com.",)


def test_overlapping_replacements_are_rejected() -> None:
    logical = LogicalText.from_run_texts(["abcdefghij"])
    with pytest.raises(ValueError, match="must not overlap"):
        logical.rewrite_runs([TextReplacement(1, 5, "x"), TextReplacement(4, 8, "y")])
