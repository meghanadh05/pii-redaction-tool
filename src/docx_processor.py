"""DOCX logical-text and run-span primitives.

The python-docx/OOXML traversal and save layer is intentionally deferred to
Phase 2. These pure primitives make fragmented-run behavior testable now.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Sequence


class StoryKind(str, Enum):
    BODY_PARAGRAPH = "BODY_PARAGRAPH"
    TABLE_CELL_PARAGRAPH = "TABLE_CELL_PARAGRAPH"
    HEADER_PARAGRAPH = "HEADER_PARAGRAPH"
    FOOTER_PARAGRAPH = "FOOTER_PARAGRAPH"
    TEXT_BOX_PARAGRAPH = "TEXT_BOX_PARAGRAPH"


@dataclass(frozen=True, slots=True)
class RunFragment:
    run_index: int
    logical_start: int
    logical_end: int


@dataclass(frozen=True, slots=True)
class RunSpan:
    run_index: int
    start_in_run: int
    end_in_run: int


@dataclass(frozen=True, slots=True)
class TextReplacement:
    start: int
    end: int
    replacement: str

    def __post_init__(self) -> None:
        if self.start < 0 or self.end <= self.start:
            raise ValueError("Replacement span must be non-empty")


@dataclass(frozen=True, slots=True)
class LogicalText:
    """Concatenated run text and the mapping back to each source run."""

    text: str
    fragments: tuple[RunFragment, ...]
    run_texts: tuple[str, ...]

    @classmethod
    def from_run_texts(cls, run_texts: Sequence[str]) -> "LogicalText":
        fragments: list[RunFragment] = []
        cursor = 0
        for run_index, run_text in enumerate(run_texts):
            next_cursor = cursor + len(run_text)
            if run_text:
                fragments.append(RunFragment(run_index, cursor, next_cursor))
            cursor = next_cursor
        immutable_runs = tuple(run_texts)
        return cls("".join(immutable_runs), tuple(fragments), immutable_runs)

    def map_span(self, start: int, end: int) -> tuple[RunSpan, ...]:
        if start < 0 or end <= start or end > len(self.text):
            raise ValueError("Span is outside the logical text")
        mapped: list[RunSpan] = []
        for fragment in self.fragments:
            overlap_start = max(start, fragment.logical_start)
            overlap_end = min(end, fragment.logical_end)
            if overlap_start < overlap_end:
                mapped.append(
                    RunSpan(
                        run_index=fragment.run_index,
                        start_in_run=overlap_start - fragment.logical_start,
                        end_in_run=overlap_end - fragment.logical_start,
                    )
                )
        if not mapped:
            raise ValueError("Non-empty logical span did not map to a source run")
        return tuple(mapped)

    def rewrite_runs(
        self,
        replacements: Sequence[TextReplacement],
    ) -> tuple[str, ...]:
        """Project non-overlapping replacements into source run strings.

        A cross-run replacement is inserted into its first affected run, so it
        inherits that run's formatting. Covered text in later runs is removed;
        unaffected prefixes and suffixes remain in their original runs.
        """

        ordered = sorted(replacements, key=lambda item: (item.start, item.end))
        previous_end = 0
        for index, replacement in enumerate(ordered):
            if replacement.end > len(self.text):
                raise ValueError("Replacement is outside the logical text")
            if index and replacement.start < previous_end:
                raise ValueError("Replacements must not overlap")
            previous_end = replacement.end

        operations: dict[int, list[tuple[int, int, str]]] = {}
        for replacement in ordered:
            spans = self.map_span(replacement.start, replacement.end)
            for position, span in enumerate(spans):
                value = replacement.replacement if position == 0 else ""
                operations.setdefault(span.run_index, []).append(
                    (span.start_in_run, span.end_in_run, value)
                )

        rewritten = list(self.run_texts)
        for run_index, run_operations in operations.items():
            value = rewritten[run_index]
            for start, end, inserted_text in sorted(run_operations, reverse=True):
                value = value[:start] + inserted_text + value[end:]
            rewritten[run_index] = value

        expected = self.text
        for replacement in sorted(ordered, key=lambda item: item.start, reverse=True):
            expected = (
                expected[: replacement.start]
                + replacement.replacement
                + expected[replacement.end :]
            )
        if "".join(rewritten) != expected:
            raise RuntimeError("Run projection changed logical replacement order")
        return tuple(rewritten)
