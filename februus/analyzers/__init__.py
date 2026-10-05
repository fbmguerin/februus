"""The analyzers: findings about one open file.

``[analyzers] enabled`` of the TOML chooses which of the analyzers below
run on every file (``clamav`` on a station, ``fake`` for development).
"""

from februus.analyzers.clamav import ClamavAnalyzer
from februus.analyzers.fake import FakeAnalyzer
from februus.core.checks import Analyzer
from februus.core.config import AnalyzersConfig


def build_analyzers(config: AnalyzersConfig) -> tuple[Analyzer, ...]:
    """The enabled analyzers, in the order of the TOML. Building one has no
    side effect (no connection, no file access)."""
    built: list[Analyzer] = []
    for name in config.names:
        if name == "clamav" and config.clamav is not None:
            built.append(ClamavAnalyzer(config.clamav.socket, config.clamav.timeout_seconds))
        elif name == "fake" and config.fake is not None:
            fake = config.fake
            built.append(
                FakeAnalyzer(fake.marker, fake.slow_marker, fake.error_marker, fake.delay_ms)
            )
        else:
            # Cannot happen after config validation. FAIL-CLOSED: never run
            # with fewer analyzers than asked.
            # FR : jamais moins d'analyseurs que demandé.
            raise ValueError(f"analyzer {name!r} cannot be built")
    return tuple(built)
