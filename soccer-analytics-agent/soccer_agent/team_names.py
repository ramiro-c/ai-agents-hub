"""Spanish→English national team name translation.

Static dict + pre-built accent-folded index. O(1) lookup, no deps beyond stdlib,
no DB calls, never raises.
"""

from __future__ import annotations

import unicodedata

# ---------------------------------------------------------------------------
# Dictionary of ~55 Spanish→English national-team pairs
# ---------------------------------------------------------------------------

_ES_TO_EN: dict[str, str] = {
    # A
    "Alemania": "Germany",
    "Arabia Saudita": "Saudi Arabia",
    "Argelia": "Algeria",
    # B
    "Bélgica": "Belgium",
    "Brasil": "Brazil",
    # C
    "Camerún": "Cameroon",
    "Canadá": "Canada",
    "Catar": "Qatar",
    "China": "China",
    "Corea del Norte": "North Korea",
    "Corea del Sur": "South Korea",
    "Costa de Marfil": "Ivory Coast",
    "Croacia": "Croatia",
    # D
    "Dinamarca": "Denmark",
    # E
    "Egipto": "Egypt",
    "Emiratos Árabes Unidos": "United Arab Emirates",
    "Escocia": "Scotland",
    "Eslovaquia": "Slovakia",
    "Eslovenia": "Slovenia",
    "España": "Spain",
    "Estados Unidos": "United States",
    # F
    "Filipinas": "Philippines",
    "Finlandia": "Finland",
    "Francia": "France",
    # G
    "Gales": "Wales",
    "Grecia": "Greece",
    # H
    "Holanda": "Netherlands",
    "Hungría": "Hungary",
    # I
    "India": "India",
    "Inglaterra": "England",
    "Irak": "Iraq",
    "Irán": "Iran",
    "Irlanda": "Republic of Ireland",
    "Irlanda del Norte": "Northern Ireland",
    "Islandia": "Iceland",
    "Italia": "Italy",
    # J
    "Japón": "Japan",
    # M
    "Marruecos": "Morocco",
    "México": "Mexico",
    # N
    "Noruega": "Norway",
    "Nueva Zelanda": "New Zealand",
    # P
    "Países Bajos": "Netherlands",
    "Perú": "Peru",
    "Polonia": "Poland",
    # R
    "República Checa": "Czech Republic",
    "República Dominicana": "Dominican Republic",
    "Rumania": "Romania",
    "Rusia": "Russia",
    # S
    "Singapur": "Singapore",
    "Sudáfrica": "South Africa",
    "Suecia": "Sweden",
    "Suiza": "Switzerland",
    # T
    "Tailandia": "Thailand",
    "Túnez": "Tunisia",
    "Turquía": "Turkey",
    # U
    "Ucrania": "Ukraine",
}


def _fold(text: str) -> str:
    """Normalize to an accent- and case-insensitive key."""
    decomposed = unicodedata.normalize("NFKD", text)
    return (
        "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()
    )


# Pre-built lookup index: _fold(key) → English value
_INDEX: dict[str, str] = {_fold(k): v for k, v in _ES_TO_EN.items()}


def translate(name: str | None) -> str | None:
    """Spanish→English team name. Identity passthrough for unknown/English.

    Case-insensitive, accent-insensitive. Never raises.
    """
    if name is None:
        return None
    stripped = name.strip()
    if not stripped:
        return ""
    return _INDEX.get(_fold(stripped), stripped)


def translate_many(names: list[str]) -> list[str]:
    """Batch translate — wraps translate()."""
    return [translate(n) for n in names]
