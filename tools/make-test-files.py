#!/usr/bin/env python3
"""Create the test files for the keys of the acceptance test (docs/TEST-PC-B.md).

    python3 tools/make-test-files.py <folder> [--big MB]

Nothing dangerous: EICAR is the standard antivirus TEST string (generated now,
never stored in the repository). The antivirus of the PC where you run this may
complain or delete ``eicar.com``: that is normal, turn it off for this folder.
FR : fichiers de test pour les clés ; EICAR est généré à l'exécution.
"""

import argparse
import io
import os
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tests import samples  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("folder", type=Path, help="folder to fill (created if missing)")
    parser.add_argument("--big", type=int, metavar="MB", help="also create big.bin of MB megabytes")
    args = parser.parse_args()

    folder: Path = args.folder
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "texte.txt").write_text("Fichier sain pour le test.\n", encoding="utf-8")
    (folder / "eicar.com").write_bytes(samples.EICAR)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("dossier/lisez-moi.txt", b"sain")
        archive.writestr("dossier/eicar.txt", samples.EICAR)
    (folder / "eicar-dans-un-zip.zip").write_bytes(buffer.getvalue())
    (folder / "archive-chiffree.zip").write_bytes(samples.encrypted_zip())
    (folder / "pdf-chiffre.pdf").write_bytes(samples.encrypted_pdf())
    (folder / "zip-trop-imbrique.zip").write_bytes(samples.nested_zip(30))
    if args.big:
        with (folder / "big.bin").open("wb") as out:
            for _ in range(args.big):
                out.write(os.urandom(1024 * 1024))
    for path in sorted(folder.iterdir()):
        print(f"{path.stat().st_size:>12}  {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
