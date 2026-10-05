"""Verdict engine: finding codes -> colors -> one verdict.

Colors come only from the ``[verdict.rules]`` table of the TOML. The final
verdict is the worst color found.

FAIL-CLOSED: a code missing from the rules gives RED.
FR : un code absent des règles donne ROUGE.

No finding at all gives GREEN: the session engine is responsible for
checking that every file was really analyzed (otherwise it adds
``internal.error``).
"""

from collections.abc import Iterable, Mapping
from enum import StrEnum


class Color(StrEnum):
    """Verdict color, from the safest to the most severe."""

    GREEN = "green"
    ORANGE = "orange"
    RED = "red"

    @property
    def severity(self) -> int:
        return _SEVERITY[self]


_SEVERITY = {Color.GREEN: 0, Color.ORANGE: 1, Color.RED: 2}


def color_of(code: str, rules: Mapping[str, Color]) -> Color:
    """Color of one finding code. Unknown code (or bad rule value) = RED."""
    color = rules.get(code)
    if not isinstance(color, Color):
        # FAIL-CLOSED / FR : code inconnu = ROUGE.
        return Color.RED
    return color


def worst(colors: Iterable[Color]) -> Color:
    """The most severe color. No color at all gives GREEN."""
    result = Color.GREEN
    for color in colors:
        if not isinstance(color, Color):
            # FAIL-CLOSED / FR : valeur inattendue = ROUGE.
            return Color.RED
        if color.severity > result.severity:
            result = color
    return result


def compute_verdict(codes: Iterable[str], rules: Mapping[str, Color]) -> Color:
    """Verdict of a session from the codes of all its findings."""
    return worst(color_of(code, rules) for code in codes)
