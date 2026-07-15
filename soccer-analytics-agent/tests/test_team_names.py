"""Unit tests for the team name translation layer.

No DB, no LLM — pure Python. Covers every scenario from REQ-TRANSLATE-001,
REQ-COMPOUND-001, and REQ-AMBIGUITY-001.
"""

from soccer_agent.team_names import translate, translate_many

# ---------------------------------------------------------------------------
# REQ-TRANSLATE-001 scenarios
# ---------------------------------------------------------------------------


def test_spanish_to_english():
    """Spanish name translates to its English counterpart."""
    assert translate("Inglaterra") == "England"
    assert translate("Francia") == "France"
    assert translate("Alemania") == "Germany"


def test_case_insensitive_match():
    """Lowercase and uppercase inputs both match."""
    assert translate("inglaterra") == "England"
    assert translate("INGLATERRA") == "England"
    assert translate("EsPaÑa") == "Spain"


def test_accent_insensitive_match():
    """Accented and unaccented variants both match."""
    assert translate("México") == "Mexico"
    assert translate("Mexico") == "Mexico"
    assert translate("mexico") == "Mexico"
    assert translate("Perú") == "Peru"
    assert translate("Peru") == "Peru"


def test_identity_passthrough():
    """Names already in English return unchanged."""
    assert translate("Argentina") == "Argentina"
    assert translate("Brazil") == "Brazil"
    assert translate("Colombia") == "Colombia"


def test_unknown_name_passthrough():
    """Names not in the dict return the input stripped, never raise."""
    assert translate("Atlantis") == "Atlantis"
    assert translate("Wakanda") == "Wakanda"


def test_empty_and_none_inputs():
    """Empty string returns empty string, None returns None."""
    assert translate("") == ""
    assert translate(None) is None


def test_batch_translation():
    """translate_many translates each name independently."""
    result = translate_many(["Inglaterra", "Francia", "Argentina"])
    assert result == ["England", "France", "Argentina"]


# ---------------------------------------------------------------------------
# REQ-COMPOUND-001 scenarios
# ---------------------------------------------------------------------------


def test_compound_name_exact_match():
    """Compound names match as full keys, not prefix fragments."""
    assert translate("Corea del Norte") == "North Korea"
    assert translate("Corea del Sur") == "South Korea"
    assert translate("Estados Unidos") == "United States"
    assert translate("Costa de Marfil") == "Ivory Coast"


def test_compound_name_with_accents():
    """Compound names with accents still match correctly."""
    assert translate("Países Bajos") == "Netherlands"
    assert translate("Emiratos Árabes Unidos") == "United Arab Emirates"


# ---------------------------------------------------------------------------
# REQ-AMBIGUITY-001 scenarios
# ---------------------------------------------------------------------------


def test_aliases_same_target():
    """Multiple Spanish names map to the same English name."""
    assert translate("Holanda") == "Netherlands"
    assert translate("Países Bajos") == "Netherlands"
    assert translate("Irlanda") == "Republic of Ireland"
    assert translate("Irlanda del Norte") == "Northern Ireland"
