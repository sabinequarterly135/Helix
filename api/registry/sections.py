"""Prompt sectioning standard: parse H1/H2 + XML sections from templates.

Provides the PromptSection model and SectionParser utility for extracting
section metadata from prompt templates. This enables section-aware evolution
where the StructuralMutator can make targeted mutations informed by the
template's structure.

Supported section markers:
- H1 headers: ``# Section Name``
- H2 headers: ``## Section Name``
- XML tags within sections (detected, stored as metadata)

Templates without headers gracefully fall back to a single "(unsectioned)"
section.
"""

from __future__ import annotations

import re

from pydantic import BaseModel

# Match H1 (# ) and H2 (## ) markdown headers at the start of a line.
_HEADER_RE = re.compile(r"^(#{1,2})\s+(.+)$", re.MULTILINE)

# Match opening XML tags in section content (first match used).
_XML_TAG_RE = re.compile(r"<(\w+)>")


class PromptSection(BaseModel):
    """A single section of a prompt template.

    Attributes:
        name: Section heading text (or "(unsectioned)" for fallback).
        level: Header level -- 1 for H1, 2 for H2.
        purpose: Optional one-liner describing section purpose.
        content: Text content between this header and the next.
        tag: XML tag name if content is wrapped in XML, else None.
        start_line: Zero-based line number of the header in the template.
    """

    name: str
    level: int
    purpose: str | None = None
    content: str
    tag: str | None = None
    start_line: int = 0


class SectionParser:
    """Parses prompt templates into a list of PromptSection objects.

    Extracts H1/H2 markdown headers and their content. If no headers are
    found, returns a single "(unsectioned)" section containing the full
    template text. Also detects XML tags within section content.
    """

    @staticmethod
    def parse(template: str) -> list[PromptSection]:
        """Parse a template string into sections based on markdown headers.

        Args:
            template: The raw prompt template text.

        Returns:
            List of PromptSection objects. Always contains at least one entry
            (the unsectioned fallback if no headers are found).
        """
        matches = list(_HEADER_RE.finditer(template))

        if not matches:
            return [
                PromptSection(
                    name="(unsectioned)",
                    level=1,
                    content=template,
                    start_line=0,
                )
            ]

        sections: list[PromptSection] = []

        for i, match in enumerate(matches):
            hashes = match.group(1)
            name = match.group(2).strip()
            level = len(hashes)

            # Determine start line (zero-based)
            start_line = template[: match.start()].count("\n")

            # Content runs from after the header line to just before the next
            # header (or end of template).
            content_start = match.end()
            if i + 1 < len(matches):
                content_end = matches[i + 1].start()
            else:
                content_end = len(template)

            content = template[content_start:content_end]
            # Strip leading newline right after header
            if content.startswith("\n"):
                content = content[1:]

            # Detect first XML tag in content
            xml_match = _XML_TAG_RE.search(content)
            tag = xml_match.group(1) if xml_match else None

            sections.append(
                PromptSection(
                    name=name,
                    level=level,
                    content=content,
                    tag=tag,
                    start_line=start_line,
                )
            )

        return sections

    @staticmethod
    def format_summary(sections: list[PromptSection]) -> str:
        """Produce a compact summary of sections for mutation prompts.

        Format per section: ``- SectionName: purpose`` (purpose omitted if None).
        This compact format prevents prompt bloat (Pitfall 6 from research).

        Args:
            sections: List of PromptSection objects.

        Returns:
            Newline-joined summary string.
        """
        lines: list[str] = []
        for section in sections:
            if section.purpose:
                lines.append(f"- {section.name}: {section.purpose}")
            else:
                lines.append(f"- {section.name}")
        return "\n".join(lines)
