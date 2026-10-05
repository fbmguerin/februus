"""Analyzer ``fake``: for development and tests only.

It reports ``fake.detected`` when a file contains the configured marker,
otherwise ``fake.clean``. These codes are not in the production verdict
rules, so they give RED there (unknown code): enabling this analyzer on a
real station by mistake can never produce a green verdict.
FR : ces codes sont absents des règles de production, donc ROUGE : activé
par erreur sur une vraie station, cet analyseur ne donne jamais de vert.

Two more markers simulate problems, to test the session engine:
``slow_marker`` makes the analysis hang (timeout), ``error_marker`` makes
it raise an exception. ``delay_ms`` slows down every file (demo of the
live progress).
"""

import time

from februus.core.checks import Analyzer, Finding, ScannedFile, read_chunks

CHUNK_SIZE = 1024 * 1024


class FakeAnalyzerError(Exception):
    """Raised on purpose when a file contains the error marker."""


class FakeAnalyzer(Analyzer):
    name = "fake"

    def __init__(self, marker: str, slow_marker: str, error_marker: str, delay_ms: int) -> None:
        self.markers = {
            "marker": marker.encode(),
            "slow_marker": slow_marker.encode(),
            "error_marker": error_marker.encode(),
        }
        self.delay_seconds = delay_ms / 1000

    def analyze(self, file: ScannedFile) -> list[Finding]:
        time.sleep(self.delay_seconds)
        found = self._find_markers(file.fd)
        if "error_marker" in found:
            raise FakeAnalyzerError("error marker found")
        if "slow_marker" in found:
            while True:  # Hang until the analyzer process is killed.
                time.sleep(1)
        if "marker" in found:
            return [Finding("fake.detected", "marker found")]
        return [Finding("fake.clean")]

    def _find_markers(self, fd: int) -> set[str]:
        """Names of the markers present in the file (read as bytes)."""
        found: set[str] = set()
        # Keep the end of the previous chunk: a marker may be split.
        keep = max(len(m) for m in self.markers.values()) - 1
        tail = b""
        for chunk in read_chunks(fd, CHUNK_SIZE):
            data = tail + chunk
            found |= {key for key, m in self.markers.items() if m and m in data}
            tail = data[-keep:] if keep > 0 else b""
        return found

