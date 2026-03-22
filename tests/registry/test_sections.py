"""Tests for SectionParser and PromptSection model."""

from __future__ import annotations


from api.registry.sections import PromptSection, SectionParser


class TestSectionParserH1:
    """Tests for parsing templates with H1 headers."""

    def test_parse_h1_headers_returns_correct_names(self):
        """H1 headers are extracted into PromptSection objects with correct names."""
        template = (
            "# System\nYou are an assistant.\n\n"
            "# Instructions\nDo the task.\n\n"
            "# Constraints\nBe accurate."
        )
        sections = SectionParser.parse(template)

        assert len(sections) == 3
        assert sections[0].name == "System"
        assert sections[1].name == "Instructions"
        assert sections[2].name == "Constraints"

    def test_parse_h1_headers_returns_level_1(self):
        """H1 headers produce sections with level=1."""
        template = "# System\nYou are an assistant.\n\n# Instructions\nDo the task."
        sections = SectionParser.parse(template)

        for section in sections:
            assert section.level == 1


class TestSectionParserH2:
    """Tests for parsing templates with H2 headers."""

    def test_parse_h2_headers_returns_level_2(self):
        """H2 headers produce sections with level=2."""
        template = "## Setup\nConfigure things.\n\n## Run\nExecute the plan."
        sections = SectionParser.parse(template)

        assert len(sections) == 2
        assert sections[0].level == 2
        assert sections[1].level == 2
        assert sections[0].name == "Setup"
        assert sections[1].name == "Run"


class TestSectionParserMixed:
    """Tests for templates with mixed H1/H2 headers."""

    def test_parse_mixed_headers_returns_correct_hierarchy(self):
        """Mixed H1/H2 headers return correct levels."""
        template = (
            "# System\nYou are an assistant.\n\n"
            "## Role\nA helpful role.\n\n"
            "# Instructions\nDo the task."
        )
        sections = SectionParser.parse(template)

        assert len(sections) == 3
        assert sections[0].level == 1
        assert sections[0].name == "System"
        assert sections[1].level == 2
        assert sections[1].name == "Role"
        assert sections[2].level == 1
        assert sections[2].name == "Instructions"


class TestSectionParserXML:
    """Tests for templates with XML-wrapped sections."""

    def test_parse_xml_wrapped_sections_sets_tag_field(self):
        """XML tags in section content set the tag field."""
        template = "# System\n<system_prompt>\nYou are an assistant.\n</system_prompt>"
        sections = SectionParser.parse(template)

        assert len(sections) == 1
        assert sections[0].tag == "system_prompt"

    def test_parse_section_without_xml_has_none_tag(self):
        """Sections without XML tags have tag=None."""
        template = "# System\nPlain text only."
        sections = SectionParser.parse(template)

        assert sections[0].tag is None


class TestSectionParserFallback:
    """Tests for fallback behavior when no headers are present."""

    def test_parse_no_headers_returns_single_unsectioned(self):
        """Template without headers returns single '(unsectioned)' section."""
        template = "Just a plain prompt with no headers at all."
        sections = SectionParser.parse(template)

        assert len(sections) == 1
        assert sections[0].name == "(unsectioned)"
        assert sections[0].content == template

    def test_parse_empty_string_returns_single_unsectioned(self):
        """Empty string returns single unsectioned section."""
        sections = SectionParser.parse("")

        assert len(sections) == 1
        assert sections[0].name == "(unsectioned)"
        assert sections[0].level == 1


class TestSectionContent:
    """Tests for content extraction between headers."""

    def test_section_content_is_text_between_headers(self):
        """Each section's content is the text between its header and the next."""
        template = "# First\nContent A\nMore A\n\n# Second\nContent B"
        sections = SectionParser.parse(template)

        assert sections[0].content.strip() == "Content A\nMore A"
        assert sections[1].content.strip() == "Content B"


class TestSectionStartLine:
    """Tests for start_line tracking."""

    def test_start_line_tracks_line_number(self):
        """start_line tracks the line number of the header in the template."""
        template = "# First\nContent A\n\n# Second\nContent B\n\n# Third\nContent C"
        sections = SectionParser.parse(template)

        assert sections[0].start_line == 0  # line 0
        assert sections[1].start_line == 3  # line 3 (after blank line)
        assert sections[2].start_line == 6  # line 6


class TestPromptSectionDefaults:
    """Tests for PromptSection model defaults."""

    def test_purpose_defaults_to_none(self):
        """PromptSection.purpose defaults to None."""
        section = PromptSection(name="Test", level=1, content="test content")
        assert section.purpose is None


class TestFormatSummary:
    """Tests for SectionParser.format_summary()."""

    def test_format_summary_produces_compact_lines(self):
        """format_summary() produces '- SectionName: purpose' lines."""
        sections = [
            PromptSection(name="System", level=1, content="...", purpose="Sets the role"),
            PromptSection(name="Instructions", level=1, content="...", purpose="Task details"),
        ]
        result = SectionParser.format_summary(sections)

        assert result == "- System: Sets the role\n- Instructions: Task details"

    def test_format_summary_omits_purpose_when_none(self):
        """format_summary() omits purpose when None."""
        sections = [
            PromptSection(name="System", level=1, content="..."),
            PromptSection(name="Extra", level=2, content="...", purpose="Optional stuff"),
        ]
        result = SectionParser.format_summary(sections)

        assert result == "- System\n- Extra: Optional stuff"
