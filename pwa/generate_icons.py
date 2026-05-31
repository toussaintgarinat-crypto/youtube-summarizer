"""
Generate PWA icons (solid-color PNG) using only Python stdlib.
"""
import struct, zlib, pathlib

def _make_png(width, height, r, g, b):
    def chunk(ctype, data):
        c = ctype + data
        crc = struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        return struct.pack(">I", len(data)) + c + crc

    header = b"\x89PNG\r\n\x1a\n"
    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))

    raw = bytearray()
    for y in range(height):
        raw.append(0)
        for x in range(width):
            raw.extend([r, g, b])

    idat = chunk(b"IDAT", zlib.compress(bytes(raw)))
    iend = chunk(b"IEND", b"")
    return header + ihdr + idat + iend

HERE = pathlib.Path(__file__).parent
COLOR = (0xE0, 0x38, 0x38)

for size in (192, 512):
    path = HERE / f"icon-{size}.png"
    if not path.exists():
        path.write_bytes(_make_png(size, size, *COLOR))
        print(f"  Created {path.name} ({size}x{size})")
    else:
        print(f"  {path.name} already exists")
