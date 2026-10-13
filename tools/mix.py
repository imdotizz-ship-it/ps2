#!/usr/bin/env python3
r"""List, extract and rebuild Milestone .MIX archives (MotoGP 08 PS2) using only the Python stdlib.

Format notes live in docs/formats/mix.md.

Usage:
  mix.py list    ARCHIVE.MIX                 every file with stored size, unpacked size, flag, name
  mix.py extract ARCHIVE.MIX OUTDIR [PAT..]  extract all files, or those matching glob patterns
  mix.py replace ARCHIVE.MIX OUT.MIX 'NAME=FILE' [...]
                                             rebuild the archive with some files replaced
                                             (NAME as shown by list, e.g. BIKES\BIKE01\PICTURES\BIKE01.TXD)

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
HEADER_SIZE = 0x20
DATA_ALIGN = 32


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


def _xor_name(raw):
    return bytes(c ^ ((NAME_KEY_STEP * i) & 0xFF) for i, c in enumerate(raw))


def decode_name(raw):
    return _xor_name(raw).split(b"\0", 1)[0].decode("latin-1")


def encode_name(name):
    return _xor_name(name.encode("latin-1") + b"\0")


def _align(n):
    return (n + DATA_ALIGN - 1) // DATA_ALIGN * DATA_ALIGN


def write_mix(entries, payloads):
    """Build an archive. payloads[i] holds the stored bytes of entries[i].

    Matches the original layout: data in table order, each file and the table
    aligned to 32 bytes with zero padding.
    """
    body = bytearray(HEADER_SIZE)
    toc = bytearray()
    for e, payload in zip(entries, payloads):
        body += bytes(_align(len(body)) - len(body))
        offset = len(body)
        body += payload
        raw_name = encode_name(e.name)
        toc += struct.pack("<I", len(raw_name)) + raw_name
        toc += struct.pack("<IIIB", offset, len(payload), e.unpacked_size, e.flag) + e.extra
    body += bytes(_align(len(body)) - len(body))
    struct.pack_into("<III", body, 0, 0, len(entries), len(body))
    return bytes(body + toc)


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


def cmd_replace(data, entries, args):
    replacements = {}
    for spec in args.replacements:
        name, sep, path = spec.partition("=")
        if not sep:
            sys.exit(f"error: expected NAME=FILE, got {spec!r}")
        replacements[name.upper().replace("/", "\\")] = path
    payloads = []
    for e in entries:
        path = replacements.pop(e.name.upper(), None)
        if path is None:
            payloads.append(data[e.offset:e.offset + e.stored_size])
            continue
        with open(path, "rb") as f:
            new = f.read()
        # Replacements are stored uncompressed.
        e.flag, e.unpacked_size = 0, len(new)
        payloads.append(new)
        print(f"replaced {e.name} ({len(new)} bytes)")
    if replacements:
        sys.exit("error: not found in archive: " + ", ".join(replacements))
    with open(args.out, "wb") as f:
        f.write(write_mix(entries, payloads))
    print(f"wrote {args.out}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list")
    p.add_argument("archive")
    p = sub.add_parser("extract")
    p.add_argument("archive")
    p.add_argument("outdir")
    p.add_argument("patterns", nargs="*", help=r"glob patterns, e.g. 'TRACKS\JEREZ\*.SPL' (case-insensitive)")
    p = sub.add_parser("replace")
    p.add_argument("archive")
    p.add_argument("out")
    p.add_argument("replacements", nargs="+", metavar="NAME=FILE")
    args = parser.parse_args()

    try:
        data, entries = read_mix(args.archive)
    except (OSError, ValueError, struct.error) as exc:
        sys.exit(f"error: {exc}")
    try:
        {"list": cmd_list, "extract": cmd_extract, "replace": cmd_replace}[args.cmd](data, entries, args)
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
