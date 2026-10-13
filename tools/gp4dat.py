#!/usr/bin/env python3
"""List and extract MOTOGP.DAT from MotoGP 4 (PS2, Namco) using only the Python stdlib.

The archive has no index of its own: the file table lives inside the game
executable (SLUS_211.59 on the US disc). Format notes: docs/formats/gp4dat.md.

Usage:
  gp4dat.py list    SLUS_211.59 MOTOGP.DAT
  gp4dat.py extract SLUS_211.59 MOTOGP.DAT OUTDIR [PAT..]   glob patterns on entry names, e.g. 'Course*'
"""

import argparse
import fnmatch
import os
import struct
import sys
from dataclasses import dataclass

SECTOR = 2048
ENTRY_SIZE = 36


@dataclass
class DatEntry:
    name: str
    sector: int
    sectors: int
    packed_size: int
    size: int

    @property
    def compressed(self):
        return self.packed_size != 0


class Elf:
    def __init__(self, data):
        if data[:4] != b"\x7fELF":
            raise ValueError("not an ELF executable")
        self.data = data
        phoff, = struct.unpack_from("<I", data, 28)
        phnum, = struct.unpack_from("<H", data, 44)
        self.segments = []
        for i in range(phnum):
            p_type, p_offset, p_vaddr, _, p_filesz = struct.unpack_from("<5I", data, phoff + 32 * i)
            if p_type == 1:
                self.segments.append((p_vaddr, p_offset, p_filesz))

    def offset(self, vaddr):
        for seg_va, seg_off, size in self.segments:
            if seg_va <= vaddr < seg_va + size:
                return seg_off + vaddr - seg_va
        return None

    def cstring(self, vaddr):
        off = self.offset(vaddr)
        if off is None:
            return None
        raw = self.data[off:off + 64].split(b"\0", 1)[0]
        if not raw or not all(32 <= c < 127 for c in raw):
            return None
        return raw.decode("ascii")


def _entry_at(elf, pos, dat_sectors):
    name_ptr, sector, info, _, packed, size = struct.unpack_from("<6I", elf.data, pos)
    count = info & 0xFFFF
    if count == 0 or sector + count > dat_sectors or packed > count * SECTOR:
        return None
    name = elf.cstring(name_ptr)
    if name is None:
        return None
    return DatEntry(name, sector, count, packed, size)


def find_table(elf, dat_size):
    """Locate the file table: the longest run of valid 36-byte entries."""
    dat_sectors = (dat_size + SECTOR - 1) // SECTOR
    data = elf.data
    best = []
    pos = 0
    limit = len(data) - ENTRY_SIZE
    while pos < limit:
        entry = _entry_at(elf, pos, dat_sectors)
        if entry is None:
            pos += 4
            continue
        run = [entry]
        nxt = pos + ENTRY_SIZE
        while nxt < limit:
            e = _entry_at(elf, nxt, dat_sectors)
            if e is None:
                break
            run.append(e)
            nxt += ENTRY_SIZE
        if len(run) > len(best):
            best = run
        pos = nxt if len(run) > 1 else pos + 4
    if len(best) < 16:
        raise ValueError("file table not found in the executable")
    return best


def decompress(src, out_size):
    """Namco LZ used by MOTOGP.DAT.

    Tokens are two bytes (b0, b1). b1 == 0xFF: copy b0 + 1 literal bytes.
    Otherwise v = b0 | b1 << 8 is a back-reference of (v & 0x1F) + 3 bytes
    starting (v >> 5) + 1 bytes back in the output.
    """
    out = bytearray()
    i = 0
    while len(out) < out_size:
        b0, b1 = src[i], src[i + 1]
        i += 2
        if b1 == 0xFF:
            count = b0 + 1
            out += src[i:i + count]
            i += count
        else:
            v = b0 | (b1 << 8)
            dist = (v >> 5) + 1
            if dist > len(out):
                raise ValueError(f"back-reference before start of output at byte {i}")
            for _ in range((v & 0x1F) + 3):
                out.append(out[-dist])
    if len(out) != out_size or i != len(src):
        raise ValueError("compressed stream size mismatch")
    return bytes(out)


def read_entry(dat, e):
    base = e.sector * SECTOR
    if not e.compressed:
        return dat[base:base + e.sectors * SECTOR]
    # Compressed data is stored right-aligned in its sector range.
    start = base + e.sectors * SECTOR - e.packed_size
    return decompress(dat[start:start + e.packed_size], e.size)


def cmd_list(entries, dat, args):
    for e in entries:
        size = e.size if e.compressed else e.sectors * SECTOR
        flag = "lz" if e.compressed else "--"
        print(f"{e.sector:>8}  {e.packed_size:>10}  {size:>10}  {flag}  {e.name}")
    print(f"\n{len(entries)} entries, {sum(e.compressed for e in entries)} compressed")


def cmd_extract(entries, dat, args):
    out_root = os.path.abspath(args.outdir)
    os.makedirs(out_root, exist_ok=True)
    count = 0
    for e in entries:
        if args.patterns and not any(fnmatch.fnmatchcase(e.name, p) for p in args.patterns):
            continue
        safe = e.name.replace("/", "_").replace("\\", "_")
        with open(os.path.join(out_root, safe + ".bin"), "wb") as out:
            out.write(read_entry(dat, e))
        count += 1
    print(f"{count} files extracted to {out_root}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    for name in ("list", "extract"):
        p = sub.add_parser(name)
        p.add_argument("elf", help="game executable, e.g. SLUS_211.59")
        p.add_argument("dat", help="MOTOGP.DAT")
        if name == "extract":
            p.add_argument("outdir")
            p.add_argument("patterns", nargs="*", help="glob patterns on entry names (case-sensitive)")
    args = parser.parse_args()

    try:
        with open(args.elf, "rb") as f:
            elf = Elf(f.read())
        with open(args.dat, "rb") as f:
            dat = f.read()
        entries = find_table(elf, len(dat))
        {"list": cmd_list, "extract": cmd_extract}[args.cmd](entries, dat, args)
    except (OSError, ValueError, struct.error) as exc:
        sys.exit(f"error: {exc}")
    except BrokenPipeError:
        pass


if __name__ == "__main__":
    main()
