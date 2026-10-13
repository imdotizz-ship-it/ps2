#!/usr/bin/env python3
"""Inspect and recolor PS2 RenderWare texture dictionaries (.TXD) using only the Python stdlib.

Usage:
  rwtxd.py list    FILE.TXD
  rwtxd.py recolor FILE.TXD OUT.TXD ORDER [PAT..]
      Reorder the RGB channels of the palettes of the textures matching the
      glob patterns (all textures if none). ORDER names the source channel for
      each output channel: 'bgr' swaps red and blue, 'gbr' rotates the hues.

Only palettized textures (4/8-bit) are changed. The file size never changes.
"""

import argparse
import fnmatch
import struct
import sys
from dataclasses import dataclass

CHUNK_STRUCT = 0x01
CHUNK_STRING = 0x02
CHUNK_TEXTURE_NATIVE = 0x15
CHUNK_TEXDICT = 0x16

RASTER_HAS_HEADERS = 0x20000
RASTER_PIXEL_FORMAT = 0xF00
FORMAT_1555 = 0x100
FORMAT_8888 = 0x500
GS_HEADER_SIZE = 0x50


@dataclass
class Texture:
    name: str
    width: int
    height: int
    depth: int
    raster_format: int
    palette_size: int
    data_end: int

    @property
    def palette_offset(self):
        """Start of the palette entries (after the GS upload header, if any)."""
        start = self.data_end - self.palette_size
        if self.raster_format & RASTER_HAS_HEADERS:
            start += GS_HEADER_SIZE
        return start


def _chunks(data, start, end):
    pos = start
    while pos + 12 <= end:
        kind, size, _ = struct.unpack_from("<III", data, pos)
        body = pos + 12
        if body + size > end:
            raise ValueError(f"chunk at {pos:#x} runs past its parent")
        yield kind, body, body + size
        pos = body + size


def read_textures(data):
    textures = []
    for kind, start, end in _chunks(data, 0, len(data)):
        if kind != CHUNK_TEXDICT:
            raise ValueError("not a RenderWare texture dictionary")
        for kind2, start2, end2 in _chunks(data, start, end):
            if kind2 != CHUNK_TEXTURE_NATIVE:
                continue
            parts = list(_chunks(data, start2, end2))
            if len(parts) < 4 or data[parts[0][1]:parts[0][1] + 4] != b"PS2\0":
                raise ValueError("only PS2 native textures are supported")
            name = data[parts[1][1]:parts[1][2]].split(b"\0", 1)[0].decode("latin-1")
            raster = list(_chunks(data, parts[3][1], parts[3][2]))
            info_start = raster[0][1]
            width, height, depth, raster_format = struct.unpack_from("<4I", data, info_start)
            palette_size, = struct.unpack_from("<I", data, info_start + 52)
            textures.append(Texture(name, width, height, depth, raster_format, palette_size, raster[1][2]))
    return textures


def _swap_palette(data, tex, order):
    fmt = tex.raster_format & RASTER_PIXEL_FORMAT
    pos = tex.palette_offset
    entries = 1 << tex.depth
    if fmt == FORMAT_8888:
        for i in range(entries):
            p = pos + 4 * i
            rgb = data[p:p + 3]
            data[p:p + 3] = bytes(rgb[c] for c in order)
    elif fmt == FORMAT_1555:
        for i in range(entries):
            p = pos + 2 * i
            v, = struct.unpack_from("<H", data, p)
            rgb = (v & 0x1F, (v >> 5) & 0x1F, (v >> 10) & 0x1F)
            r, g, b = (rgb[c] for c in order)
            struct.pack_into("<H", data, p, (v & 0x8000) | r | (g << 5) | (b << 10))
    else:
        return False
    return True


def cmd_list(data, args):
    for t in read_textures(data):
        print(f"{t.name:<24} {t.width:>4}x{t.height:<4} {t.depth:>2}-bit  format={t.raster_format:#07x}  palette={t.palette_size}")


def cmd_recolor(data, args):
    order = args.order.lower()
    if sorted(order) != ["b", "g", "r"]:
        sys.exit("error: ORDER must be a permutation of 'rgb', e.g. bgr")
    order = ["rgb".index(c) for c in order]
    buf = bytearray(data)
    changed = 0
    for t in read_textures(data):
        if args.patterns and not any(fnmatch.fnmatch(t.name.upper(), p.upper()) for p in args.patterns):
            continue
        if t.depth not in (4, 8) or not t.palette_size:
            print(f"skipped {t.name}: not palettized")
            continue
        if _swap_palette(buf, t, order):
            changed += 1
            print(f"recolored {t.name}")
        else:
            print(f"skipped {t.name}: unsupported palette format {t.raster_format:#x}")
    with open(args.out, "wb") as f:
        f.write(buf)
    print(f"{changed} textures recolored, wrote {args.out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("txd")
    p = sub.add_parser("recolor")
    p.add_argument("txd")
    p.add_argument("out")
    p.add_argument("order")
    p.add_argument("patterns", nargs="*")
    args = parser.parse_args()
    try:
        with open(args.txd, "rb") as f:
            data = f.read()
        {"list": cmd_list, "recolor": cmd_recolor}[args.cmd](data, args)
    except (OSError, ValueError, struct.error) as exc:
        sys.exit(f"error: {exc}")


if __name__ == "__main__":
    main()
