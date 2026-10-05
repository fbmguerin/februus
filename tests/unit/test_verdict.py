"""Tests for the verdict engine."""

import pytest

from februus.core.verdict import Color, color_of, compute_verdict, worst

RULES = {
    "clamav.detected": Color.RED,
    "device.multi_partition": Color.ORANGE,
    "fake.clean": Color.GREEN,
}


def test_known_codes_get_their_color():
    assert color_of("clamav.detected", RULES) is Color.RED
    assert color_of("device.multi_partition", RULES) is Color.ORANGE
    assert color_of("fake.clean", RULES) is Color.GREEN


def test_unknown_code_is_red():
    # FAIL-CLOSED: the most important rule of the engine.
    assert color_of("yara.match", RULES) is Color.RED
    assert compute_verdict(["fake.clean", "yara.match"], RULES) is Color.RED


def test_code_matching_is_exact():
    assert color_of("fake.clean.extra", RULES) is Color.RED
    assert color_of("FAKE.CLEAN", RULES) is Color.RED


def test_bad_rule_value_is_red():
    assert color_of("fake.clean", {"fake.clean": "green"}) is Color.RED


def test_empty_rules_make_everything_red():
    assert compute_verdict(["fake.clean"], {}) is Color.RED


@pytest.mark.parametrize(
    ("codes", "expected"),
    [
        (["fake.clean"], Color.GREEN),
        (["fake.clean", "device.multi_partition"], Color.ORANGE),
        (["device.multi_partition", "clamav.detected", "fake.clean"], Color.RED),
        (["clamav.detected", "device.multi_partition"], Color.RED),
    ],
)
def test_worst_color_wins(codes, expected):
    assert compute_verdict(codes, RULES) is expected
    assert compute_verdict(reversed(codes), RULES) is expected


def test_no_finding_is_green():
    assert compute_verdict([], RULES) is Color.GREEN


def test_worst_with_unexpected_value_is_red():
    assert worst([Color.GREEN, "purple"]) is Color.RED


def test_colors_are_ordered():
    assert Color.GREEN.severity < Color.ORANGE.severity < Color.RED.severity
