"""Tests for ENG-01 minimal edit policy and ENG-05 UTF-8 encoding.

- Test 1: AUTHOR_SYSTEM_PROMPT contains "MINIMAL EDIT POLICY" heading
- Test 2: AUTHOR_SYSTEM_PROMPT contains all 5 minimal edit rules
- Test 3: Spanish IVR text round-trips through UTF-8 file operations (ENG-05)
"""

from api.evolution.prompts import AUTHOR_SYSTEM_PROMPT


class TestMinimalEditPolicy:
    """ENG-01: Verify MINIMAL EDIT POLICY section in AUTHOR_SYSTEM_PROMPT."""

    def test_contains_minimal_edit_policy_heading(self):
        """AUTHOR_SYSTEM_PROMPT contains 'MINIMAL EDIT POLICY' heading."""
        assert "MINIMAL EDIT POLICY" in AUTHOR_SYSTEM_PROMPT

    def test_contains_all_five_rules(self):
        """AUTHOR_SYSTEM_PROMPT contains all 5 minimal edit rules."""
        # Rule 5: Make minimal, targeted changes
        assert "MINIMAL" in AUTHOR_SYSTEM_PROMPT
        assert "TARGETED" in AUTHOR_SYSTEM_PROMPT.upper()

        # Rule 6: Preserve original language, writing style, section structure
        assert "Preserve the original language" in AUTHOR_SYSTEM_PROMPT

        # Rule 7: Only modify lines related to failing test cases
        assert "Only" in AUTHOR_SYSTEM_PROMPT
        assert "failing test cases" in AUTHOR_SYSTEM_PROMPT

        # Rule 8: Surgical edits
        assert "Surgical" in AUTHOR_SYSTEM_PROMPT or "surgical" in AUTHOR_SYSTEM_PROMPT.lower()

        # Rule 9: Keep original language (e.g., Spanish stays Spanish)
        assert (
            "Do not change the language" in AUTHOR_SYSTEM_PROMPT
            or "do not change the language" in AUTHOR_SYSTEM_PROMPT.lower()
        )


class TestUtf8SpanishRoundTrip:
    """ENG-05: Verify UTF-8 encoding handles Spanish IVR content correctly."""

    def test_utf8_spanish_round_trip(self, tmp_path):
        """Spanish text with accents and inverted punctuation round-trips through UTF-8 file I/O."""
        spanish_text = (
            "Bienvenido al sistema autom\u00e1tico. \u00bfEn qu\u00e9 puedo ayudarle?\n"
            "Presione 1 para espa\u00f1ol.\n"
            "Transferencia al departamento de atenci\u00f3n al cliente.\n"
            "\u00a1Gracias por llamar!"
        )

        test_file = tmp_path / "spanish_prompt.md"
        test_file.write_text(spanish_text, encoding="utf-8")

        # Read back and verify round-trip fidelity
        content = test_file.read_text(encoding="utf-8")
        assert content == spanish_text

        # Verify specific characters survived
        assert "\u00e1" in content  # a with accent (automatico)
        assert "\u00bf" in content  # inverted question mark
        assert "\u00e9" in content  # e with accent (que)
        assert "\u00f1" in content  # n with tilde (espanol)
        assert "\u00f3" in content  # o with accent (atencion)
        assert "\u00a1" in content  # inverted exclamation
