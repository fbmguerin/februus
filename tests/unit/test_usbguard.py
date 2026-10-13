"""The USBGuard storage rule (deploy/usbguard/rules.conf)."""

from pathlib import Path

RULES = Path(__file__).resolve().parents[2] / "deploy" / "usbguard" / "rules.conf"


def test_storage_rule_uses_match_all_not_equals():
    # "equals { 08:*:* }" needs EXACTLY one interface and wrongly blocks a
    # USB3 enclosure that also offers UAS (08:06:50 + 08:06:62). "match-all"
    # allows a device whose interfaces are all mass storage, whatever their
    # number, and still blocks a "key" that also declares a keyboard (HID).
    text = RULES.read_text()
    assert "allow with-interface match-all { 08:*:* }" in text
    # No active rule still uses "equals" (the word may appear in a comment).
    rules = [ln for ln in text.splitlines() if ln.strip() and not ln.startswith("#")]
    assert not any("equals" in ln for ln in rules)
