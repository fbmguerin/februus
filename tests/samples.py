"""Test samples generated at runtime. Never store test malware in the repo.

FR : les échantillons de test sont générés à l'exécution, jamais stockés.
"""

import io
import struct
import zipfile

# EICAR test string, split so that this source file is not detected itself.
EICAR = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR" + b"-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"


def encrypted_zip() -> bytes:
    """A zip whose entry is flagged as encrypted (ZipCrypto bit)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("secret.txt", b"x" * 100)
    data = bytearray(buffer.getvalue())
    # Set bit 0 ("encrypted") of the general purpose flags, in the local
    # header (offset 6) and in the central directory (offset 8).
    for signature, offset in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = data.find(signature) + offset
        (flags,) = struct.unpack_from("<H", data, start)
        struct.pack_into("<H", data, start, flags | 1)
    return bytes(data)


def encrypted_pdf() -> bytes:
    """A one-page PDF with a /Encrypt dictionary (unknown password)."""
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 200] /Contents 5 0 R >>",
        b"<< /Filter /Standard /V 1 /R 2 /O <" + b"11" * 32
        + b"> /U <" + b"22" * 32 + b"> /P -4 >>",
        b"<< /Length 10 >>\nstream\n0123456789\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for number, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objects) + 1)
    for offset in offsets:
        out += b"%010d 00000 n \n" % offset
    out += (
        b"trailer\n<< /Size %d /Root 1 0 R /Encrypt 4 0 R /ID [<%s> <%s>] >>\n"
        b"startxref\n%d\n%%%%EOF\n"
        % (len(objects) + 1, b"ab" * 16, b"ab" * 16, xref)
    )
    return bytes(out)


def nested_zip(depth: int) -> bytes:
    """Zip archives nested ``depth`` times (to exceed clamd MaxRecursion)."""
    data, name = b"hello", "file.txt"
    for level in range(depth):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(name, data)
        data, name = buffer.getvalue(), f"level{level}.zip"
    return data
