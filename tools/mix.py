#!/usr/bin/env python3
"""List and extract Milestone .MIX archives (MotoGP 08 PS2) using only the Python stdlib.

Format notes live in docs/formats/mix.md.

Usage:
  mix.py list    ARCHIVE.MIX                 every file with stored size, unpacked size, flag, name
  mix.py extract ARCHIVE.MIX OUTDIR [PAT..]  extract all files, or those matching glob patterns

Compressed entries (flag 1) are written as-is with a ".packed" suffix until the
compression scheme is known.
"""

import argparse
import fnmatch
import os
import struct
import sys
from dataclasses import dataclass

NAME_KEY_STEP = 0x3A


@dataclass
class MixEntry:
    name: str
    offset: int
    stored_size: int
    unpacked_size: int
    flag: int
    extra: bytes

    @property
    def compressed(self):
        return self.flag == 1


def decode_name(raw):
    plain = bytes(c ^ ((NAME_KEY_STEP * i) & 0xFF) for i, c in enumerate(raw))
    return plain.split(b"\0", 1)[0].decode("latin-1")


def read_mix(path):
    with open(path, "rb") as f:
        data = f.read()
    _, count, toc_offset = struct.unpack_from("<III", data, 0)
    if toc_offset > len(data):
        raise ValueError(f"{path}: table of contents offset {toc_offset} is past the end of the file")
    entries = []
    pos = toc_offset
    for _ in range(count):
        (name_len,) = struct.unpack_from("<I", data, pos)
        pos += 4
        raw_name = data[pos:pos + name_len]
        pos += name_len
        offset, stored, unpacked = struct.unpack_from("<III", data, pos)
        pos += 12
        flag = data[pos]
        extra = data[pos + 1:pos + 9]
        pos += 9
        if offset + stored > toc_offset:
            raise ValueError(f"{path}: entry {decode_name(raw_name)!r} overlaps the table of contents")
        entries.append(MixEntry(decode_name(raw_name), offset, stored, unpacked, flag, extra))
    if pos != len(data):
        print(f"warning: {len(data) - pos} unparsed bytes after the table of contents", file=sys.stderr)
    return data, entries


def cmd_list(data, entries, args):
    for e in entries:
        print(f"{e.stored_size:>10}  {e.unpacked_size:>10}  {e.flag}  {e.name}")
    print(f"\n{len(entries)} files, {sum(e.compressed for e in entries)} compressed")


def cmd_extract(data, entries, args):
    out_root = os.path.abspath(args.outdir)
    patterns = [p.upper().replace("/", "\\") for p in args.patterns]
    count = 0
    for e in entries:
        if patterns and not any(fnmatch.fnmatch(e.name.upper(), p) for p in patterns):
            continue
        parts = [p for p in e.name.replace("\\", "/").split("/") if p not in ("", ".", "..")]
        dest = os.path.join(out_root, *parts)
        if e.compressed:
            dest += ".packed"
        if os.path.commonpath([out_root, os.path.abspath(dest)]) != out_root:
            print(f"skipping unsafe path: {e.name}", file=sys.stderr)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as out:
            out.write(data[e.offset:e.offset + e.stored_size])
        count += 1
    print(f"{count} files extracted to {out_root}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("archive")
    p = sub.add_parser("extract")
    p.add_argument("archive")
    p.add_argument("outdir")
    p.add_argument("patterns", nargs="*", help=r"glob patterns, e.g. 'TRACKS\JEREZ\*.SPL' (case-insensitive)")
    args = parser.parse_args()

    try:
        data, entries = read_mix(args.archive)
    except (OSError, ValueError, struct.error) as exc:
        sys.exit(f"error: {exc}")
    try:
        {"list": cmd_list, "extract": cmd_extract}[args.cmd](data, entries, args)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
