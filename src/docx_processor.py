"""DOCX logical-text extraction and run-aware rewriting."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Iterator, Mapping, Sequence

from docx import Document
from docx.document import Document as DocumentObject
from docx.enum.section import WD_HEADER_FOOTER
from docx.oxml.ns import qn
from docx.oxml.table import CT_Tbl
from docx.oxml.text.paragraph import CT_P
from docx.section import _Footer, _Header
from docx.table import Table, _Cell
from docx.text.paragraph import Paragraph
from docx.text.run import Run


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


class UnsupportedRunContentError(ValueError):
    """Raised rather than silently deleting embedded run content."""


_SAFE_REWRITE_TAGS = frozenset(
    {
        qn("w:rPr"),
        qn("w:t"),
        qn("w:tab"),
        qn("w:br"),
        qn("w:cr"),
        qn("w:noBreakHyphen"),
    }
)


@dataclass(slots=True)
class TextContainer:
    """One independently rewritable paragraph and its logical run map."""

    id: str
    story_type: StoryKind
    paragraph: Paragraph
    logical: LogicalText
    runs: tuple[Run, ...]
    metadata: Mapping[str, str | int]

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("TextContainer id must be non-empty")
        if len(self.runs) != len(self.logical.run_texts):
            raise ValueError("Run objects and logical run texts must align")
        self.metadata = MappingProxyType(dict(self.metadata))

    @classmethod
    def from_paragraph(
        cls,
        paragraph: Paragraph,
        *,
        container_id: str,
        story_type: StoryKind,
        metadata: Mapping[str, str | int] | None = None,
    ) -> "TextContainer":
        # paragraph.runs omits runs nested in hyperlinks. Direct OOXML traversal
        # includes those runs while count(ancestor::w:p)=1 excludes text-box
        # paragraphs nested inside a drawing in this paragraph.
        run_elements = paragraph._p.xpath(".//w:r[count(ancestor::w:p) = 1]")
        runs = tuple(Run(element, paragraph) for element in run_elements)
        logical = LogicalText.from_run_texts([run.text for run in runs])
        return cls(
            id=container_id,
            story_type=story_type,
            paragraph=paragraph,
            logical=logical,
            runs=runs,
            metadata=metadata or {},
        )

    @property
    def text(self) -> str:
        return self.logical.text

    @property
    def run_map(self) -> tuple[RunFragment, ...]:
        return self.logical.fragments

    def rewrite(self, replacements: Sequence[TextReplacement]) -> None:
        """Apply replacements without flattening the paragraph.

        Replacement text inherits the formatting of the first affected run.
        A run containing fields, drawings, or other unsupported children is
        rejected before any mutation so embedded content cannot be discarded.
        """

        rewritten = self.logical.rewrite_runs(replacements)
        changed = [
            index
            for index, (before, after) in enumerate(
                zip(self.logical.run_texts, rewritten, strict=True)
            )
            if before != after
        ]
        for index in changed:
            unsupported = [
                child.tag
                for child in self.runs[index]._r
                if child.tag not in _SAFE_REWRITE_TAGS
            ]
            if unsupported:
                raise UnsupportedRunContentError(
                    f"Container {self.id!r} run {index} contains unsupported XML"
                )
        for index in changed:
            self.runs[index].text = rewritten[index]
        self.logical = LogicalText.from_run_texts([run.text for run in self.runs])


StoryParent = DocumentObject | _Header | _Footer | _Cell


def _iter_story_blocks(parent: StoryParent) -> Iterator[Paragraph | Table]:
    if isinstance(parent, DocumentObject):
        element = parent.element.body
    elif isinstance(parent, _Cell):
        element = parent._tc
    else:
        element = parent._element

    for child in element.iterchildren():
        if isinstance(child, CT_P):
            yield Paragraph(child, parent)
        elif isinstance(child, CT_Tbl):
            yield Table(child, parent)


def _iter_table_containers(
    table: Table,
    *,
    path: str,
    story_type: StoryKind,
) -> Iterator[TextContainer]:
    """Traverse each physical cell once, including nested tables."""

    for row_index, row_element in enumerate(table._tbl.tr_lst):
        for cell_index, cell_element in enumerate(row_element.tc_lst):
            cell = _Cell(cell_element, table)
            cell_path = f"{path}/r{row_index:04d}/c{cell_index:04d}"
            paragraph_index = 0
            table_index = 0
            for block in _iter_story_blocks(cell):
                if isinstance(block, Paragraph):
                    container_id = f"{cell_path}/p{paragraph_index:04d}"
                    yield TextContainer.from_paragraph(
                        block,
                        container_id=container_id,
                        story_type=story_type,
                        metadata={
                            "row_index": row_index,
                            "cell_index": cell_index,
                        },
                    )
                    paragraph_index += 1
                else:
                    yield from _iter_table_containers(
                        block,
                        path=f"{cell_path}/t{table_index:04d}",
                        story_type=story_type,
                    )
                    table_index += 1


def _iter_root_containers(
    parent: StoryParent,
    *,
    story_prefix: str,
    paragraph_story_type: StoryKind,
    table_story_type: StoryKind,
) -> Iterator[TextContainer]:
    paragraph_index = 0
    table_index = 0
    for block in _iter_story_blocks(parent):
        if isinstance(block, Paragraph):
            yield TextContainer.from_paragraph(
                block,
                container_id=f"{story_prefix}/p{paragraph_index:04d}",
                story_type=paragraph_story_type,
            )
            paragraph_index += 1
        else:
            yield from _iter_table_containers(
                block,
                path=f"{story_prefix}/t{table_index:04d}",
                story_type=table_story_type,
            )
            table_index += 1


_HEADER_VARIANTS = (
    ("default", "header", WD_HEADER_FOOTER.PRIMARY),
    ("first", "first_page_header", WD_HEADER_FOOTER.FIRST_PAGE),
    ("even", "even_page_header", WD_HEADER_FOOTER.EVEN_PAGE),
)
_FOOTER_VARIANTS = (
    ("default", "footer", WD_HEADER_FOOTER.PRIMARY),
    ("first", "first_page_footer", WD_HEADER_FOOTER.FIRST_PAGE),
    ("even", "even_page_footer", WD_HEADER_FOOTER.EVEN_PAGE),
)


def _has_story_reference(section: object, reference_type: object, tag: str) -> bool:
    sect_pr = section._sectPr  # type: ignore[attr-defined]
    references = sect_pr.xpath(f"./w:{tag}Reference")
    return any(reference.type_ == reference_type for reference in references)


def iter_text_containers(document: DocumentObject) -> Iterator[TextContainer]:
    """Yield body, table, header, and footer paragraphs deterministically.

    Header/footer parts are keyed by package part name and emitted once even if
    multiple sections share them.
    """

    yield from _iter_root_containers(
        document,
        story_prefix="body",
        paragraph_story_type=StoryKind.BODY_PARAGRAPH,
        table_story_type=StoryKind.TABLE_CELL_PARAGRAPH,
    )

    seen_parts: set[str] = set()
    for section in document.sections:
        for variant, attribute, reference_type in _HEADER_VARIANTS:
            if not _has_story_reference(section, reference_type, "header"):
                continue
            story = getattr(section, attribute)
            part_name = str(story.part.partname)
            if part_name in seen_parts:
                continue
            seen_parts.add(part_name)
            yield from _iter_root_containers(
                story,
                story_prefix=f"header:{part_name}:{variant}",
                paragraph_story_type=StoryKind.HEADER_PARAGRAPH,
                table_story_type=StoryKind.HEADER_PARAGRAPH,
            )

        for variant, attribute, reference_type in _FOOTER_VARIANTS:
            if not _has_story_reference(section, reference_type, "footer"):
                continue
            story = getattr(section, attribute)
            part_name = str(story.part.partname)
            if part_name in seen_parts:
                continue
            seen_parts.add(part_name)
            yield from _iter_root_containers(
                story,
                story_prefix=f"footer:{part_name}:{variant}",
                paragraph_story_type=StoryKind.FOOTER_PARAGRAPH,
                table_story_type=StoryKind.FOOTER_PARAGRAPH,
            )


def extract_text_containers(path: Path | str) -> tuple[TextContainer, ...]:
    """Open a DOCX and extract all supported logical text containers."""

    document = Document(str(path))
    return tuple(iter_text_containers(document))
