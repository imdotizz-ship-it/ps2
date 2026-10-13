#!/usr/bin/env python3
"""Inspect and extract PS2 disc images (ISO9660) using only the Python stdlib.

Supports plain 2048-byte-sector images (.iso, typical for PS2 DVDs) and raw
2352-byte-sector images (.bin, Mode 1 or Mode 2 Form 1, typical for PS2 CDs).

Usage:
  ps2iso.py info    GAME.iso                 volume info + SYSTEM.CNF (game serial)
  ps2iso.py list    GAME.iso [--magic]       every file with size, LBA, first bytes
  ps2iso.py summary GAME.iso                 file count/size grouped by extension and magic
  ps2iso.py extract GAME.iso OUTDIR [PAT..]  extract all files, or those matching glob patterns
"""

import argparse
import fnmatch
import os
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass

SECTOR = 2048
RAW_SECTOR = 2352
PVD_LBA = 16
MAGIC_LEN = 16


@dataclass
class Entry:
    path: str
    lba: int
    size: int
    is_dir: bool


class DiscImage:
    def __init__(self, path):
        self.f = open(path, "rb")
        self.sector_size, self.data_offset = self._detect_layout()

    def close(self):
        self.f.close()

    def _detect_layout(self):
        candidates = [(SECTOR, 0), (RAW_SECTOR, 16), (RAW_SECTOR, 24)]
        for sector_size, data_offset in candidates:
            self.f.seek(PVD_LBA * sector_size + data_offset)
            head = self.f.read(6)
            if head[1:6] == b"CD001":
                return sector_size, data_offset
        raise ValueError("no ISO9660 volume descriptor found (not a PS2 disc image?)")

    def read_sectors(self, lba, count):
        if self.sector_size == SECTOR:
            self.f.seek(lba * SECTOR)
            return self.f.read(count * SECTOR)
        out = bytearray()
        for i in range(count):
            self.f.seek((lba + i) * self.sector_size + self.data_offset)
            out += self.f.read(SECTOR)
        return bytes(out)

    def read_extent(self, lba, size):
        return self.read_sectors(lba, (size + SECTOR - 1) // SECTOR)[:size]

    def iter_file(self, lba, size, chunk_sectors=512):
        remaining = size
        while remaining > 0:
            n = min(chunk_sectors, (remaining + SECTOR - 1) // SECTOR)
            data = self.read_sectors(lba, n)
            if not data:
                raise IOError(f"image truncated at LBA {lba}")
            yield data[:remaining]
            remaining -= len(data[:remaining])
            lba += n

    def pvd(self):
        return self.read_sectors(PVD_LBA, 1)

    def volume_id(self):
        return self.pvd()[40:72].decode("ascii", "replace").strip()

    def volume_size_bytes(self):
        return struct.unpack_from("<I", self.pvd(), 80)[0] * SECTOR

    def walk(self):
        root = self.pvd()[156:156 + 34]
        lba, size = struct.unpack_from("<I", root, 2)[0], struct.unpack_from("<I", root, 10)[0]
        visited = set()
        yield from self._walk_dir(lba, size, "", visited)

    def _walk_dir(self, lba, size, prefix, visited):
        if lba in visited:
            return
        visited.add(lba)
        data = self.read_extent(lba, size)
        pos = 0
        while pos < len(data):
            rec_len = data[pos]
            if rec_len == 0:
                # Records never span sectors; zero padding means skip to the next one.
                pos = (pos // SECTOR + 1) * SECTOR
                continue
            rec = data[pos:pos + rec_len]
            pos += rec_len
            if len(rec) < 34:
                break
            name_len = rec[32]
            raw_name = rec[33:33 + name_len]
            if raw_name in (b"\x00", b"\x01"):
                continue
            name = _clean_name(raw_name)
            entry_lba = struct.unpack_from("<I", rec, 2)[0]
            entry_size = struct.unpack_from("<I", rec, 10)[0]
            is_dir = bool(rec[25] & 0x02)
            path = f"{prefix}/{name}" if prefix else name
            yield Entry(path, entry_lba, entry_size, is_dir)
            if is_dir:
                yield from self._walk_dir(entry_lba, entry_size, path, visited)


def _clean_name(raw):
    name = raw.decode("ascii", "replace")
    if ";" in name:
        name = name.split(";", 1)[0]
    if name.endswith("."):
        name = name[:-1]
    return name.replace("/", "_").replace("\\", "_")


def _magic(img, entry):
    if entry.size == 0:
        return b""
    return img.read_extent(entry.lba, min(entry.size, MAGIC_LEN))


def _fmt_magic(data):
    hexpart = data.hex(" ")
    asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in data)
    return f"{hexpart:<{MAGIC_LEN * 3}} |{asciipart}|"


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024


def cmd_info(img, args):
    layout = "2048 (ISO)" if img.sector_size == SECTOR else f"2352 raw, data at +{img.data_offset}"
    print(f"Volume ID   : {img.volume_id()}")
    print(f"Volume size : {_human(img.volume_size_bytes())}")
    print(f"Sector      : {layout}")
    files = [e for e in img.walk() if not e.is_dir]
    print(f"Files       : {len(files)} ({_human(sum(e.size for e in files))})")
    cnf = next((e for e in files if e.path.upper() == "SYSTEM.CNF"), None)
    if cnf:
        print("\nSYSTEM.CNF:")
        print(img.read_extent(cnf.lba, cnf.size).decode("ascii", "replace").strip())


def cmd_list(img, args):
    for e in sorted(img.walk(), key=lambda e: e.lba):
        if e.is_dir:
            continue
        line = f"{e.lba:>9}  {e.size:>12}  {e.path}"
        if args.magic:
            line += f"\n{'':>25}{_fmt_magic(_magic(img, e))}"
        print(line)


def cmd_summary(img, args):
    by_ext = defaultdict(lambda: [0, 0])
    by_magic = defaultdict(lambda: [0, 0, None])
    for e in img.walk():
        if e.is_dir:
            continue
        ext = os.path.splitext(e.path)[1].upper() or "(none)"
        by_ext[ext][0] += 1
        by_ext[ext][1] += e.size
        head = _magic(img, e)[:4]
        slot = by_magic[head]
        slot[0] += 1
        slot[1] += e.size
        slot[2] = slot[2] or e.path
    print("By extension:")
    for ext, (count, size) in sorted(by_ext.items(), key=lambda kv: -kv[1][1]):
        print(f"  {ext:<10} {count:>6} files  {_human(size):>10}")
    print("\nBy first 4 bytes (magic):")
    for head, (count, size, example) in sorted(by_magic.items(), key=lambda kv: -kv[1][1]):
        asciipart = "".join(chr(b) if 32 <= b < 127 else "." for b in head)
        print(f"  {head.hex(' '):<11} |{asciipart:<4}| {count:>6} files  {_human(size):>10}  e.g. {example}")


def cmd_extract(img, args):
    out_root = os.path.abspath(args.outdir)
    patterns = [p.upper() for p in args.patterns]
    count = 0
    for e in img.walk():
        if e.is_dir:
            continue
        if patterns and not any(fnmatch.fnmatch(e.path.upper(), p) for p in patterns):
            continue
        parts = [p for p in e.path.split("/") if p not in ("", ".", "..")]
        dest = os.path.join(out_root, *parts)
        if os.path.commonpath([out_root, os.path.abspath(dest)]) != out_root:
            print(f"skipping unsafe path: {e.path}", file=sys.stderr)
            continue
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as out:
            for chunk in img.iter_file(e.lba, e.size):
                out.write(chunk)
        count += 1
        print(f"{e.size:>12}  {e.path}")
    print(f"\n{count} files extracted to {out_root}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("info", "list", "summary", "extract"):
        p = sub.add_parser(name)
        p.add_argument("image")
        if name == "list":
            p.add_argument("--magic", action="store_true", help="show the first 16 bytes of each file")
        if name == "extract":
            p.add_argument("outdir")
            p.add_argument("patterns", nargs="*", help="glob patterns, e.g. 'DATA/*.PAK' (case-insensitive)")
    args = parser.parse_args()

    try:
        img = DiscImage(args.image)
    except (OSError, ValueError) as exc:
        sys.exit(f"error: {exc}")
    try:
        {"info": cmd_info, "list": cmd_list, "summary": cmd_summary, "extract": cmd_extract}[args.cmd](img, args)
    except BrokenPipeError:
        pass
    finally:
        img.close()


if __name__ == "__main__":
    main()
