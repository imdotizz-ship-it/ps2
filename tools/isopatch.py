#!/usr/bin/env python3
"""Make and apply patches that rebuild a modified PS2 ISO from the original one.

The patched image is described as a list of pieces: ranges copied from the
original ISO, and new data stored gzip-compressed in "part" files. Nothing
needs the whole image in memory, so the same patch can be applied in a web
browser on a phone (patcher/index.html) as well as here.

Files are replaced like `ps2iso.py replace` does: in place when the new file
fits in the old sectors, otherwise appended at the end of the image. Inside a
replaced .MIX archive, every file stored unchanged is copied from the original
archive instead of being stored again, and identical new files are stored once.

Usage:
  isopatch.py make  ORIGINAL.iso PATCH_DIR ISO_PATH=FILE... [--iso OUT.iso] [--name NAME] [--note TEXT]...
  isopatch.py apply ORIGINAL.iso PATCH_DIR OUT.iso
"""
import argparse
import gzip
import hashlib
import json
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402
from ps2iso import DiscImage, PVD_LBA, SECTOR  # noqa: E402

FORMAT = "ps2-isopatch-1"
CHUNK = 4 << 20           # new data is compressed in pieces of at most 4 MiB
PART = 40 << 20           # and stored in part files of about 40 MiB


def _sha1(b):
    return hashlib.sha1(b).hexdigest()


def _both_endian(v):
    return struct.pack("<I", v) + struct.pack(">I", v)


def _parse_mix(data):
    """entries (name, offset, size) of a .MIX archive in memory"""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".MIX") as t:
        t.write(data); t.flush()
        _, entries = mix.read_mix(t.name)
    return entries


def _file_segments(new, old, old_iso_off):
    """pieces of a new file: ('src', iso_offset, n) for runs equal to a file of the old .MIX,
    ('lit', bytes) for the rest"""
    if old is None or not new[:4] == old[:4]:
        return [("lit", new)]
    try:
        old_e = _parse_mix(old); new_e = _parse_mix(new)
    except Exception:
        return [("lit", new)]
    by_hash = {}
    for e in old_e:
        if e.stored_size >= 4096:
            by_hash.setdefault(_sha1(old[e.offset:e.offset + e.stored_size]), e)
    segs = []; pos = 0
    for e in sorted(new_e, key=lambda e: e.offset):
        if e.stored_size < 4096:
            continue
        o = by_hash.get(_sha1(new[e.offset:e.offset + e.stored_size]))
        if o is None:
            continue
        if e.offset > pos:
            segs.append(("lit", new[pos:e.offset]))
        segs.append(("src", old_iso_off + o.offset, e.stored_size))
        pos = e.offset + e.stored_size
    if pos < len(new):
        segs.append(("lit", new[pos:]))
    return segs


def make(iso, out_dir, replacements, out_iso=None, name="patched.iso", notes=()):
    img = DiscImage(iso)
    if img.sector_size != SECTOR:
        sys.exit("error: only plain 2048-byte-sector ISO images are supported")
    entries = {e.path.upper(): e for e in img.walk() if not e.is_dir}
    src_size = os.path.getsize(iso)
    volume = img.volume_size_bytes() // SECTOR
    writes = []                     # (target offset, [segments])
    for spec in replacements:
        path, _, src = spec.partition("=")
        e = entries.get(path.upper().replace("\\", "/"))
        if e is None:
            sys.exit(f"error: {path!r} not found in the image")
        new = open(src, "rb").read()
        old = img.read_extent(e.lba, e.size)
        old_sec = (e.size + SECTOR - 1) // SECTOR; new_sec = (len(new) + SECTOR - 1) // SECTOR
        if new_sec <= old_sec:
            lba = e.lba
        else:
            lba = volume; volume += new_sec
        segs = _file_segments(new, old, e.lba * SECTOR)
        pad = (old_sec if lba == e.lba else new_sec) * SECTOR - len(new)
        if pad:
            segs.append(("lit", bytes(pad)))
        writes.append((lba * SECTOR, segs))
        writes.append((e.record_pos + 2, [("lit", _both_endian(lba))]))
        writes.append((e.record_pos + 10, [("lit", _both_endian(len(new)))]))
        print(f"{e.path}: {len(new)} bytes at LBA {lba} ({'in place' if lba == e.lba else 'appended'})")
    writes.append((PVD_LBA * SECTOR + 80, [("lit", _both_endian(volume))]))
    tgt_size = max(volume * SECTOR, src_size)
    # flatten: sorted, non-overlapping writes; gaps are copied from the original (zeros past its end)
    ops = []; pos = 0
    for off, segs in sorted(writes, key=lambda w: w[0]):
        if off < pos:
            sys.exit("error: overlapping writes")
        if off > pos:
            ops += _gap(pos, off, src_size)
        for s in segs:
            ops.append(s); off += s[2] if s[0] == "src" else len(s[1])
        pos = off
    if pos < tgt_size:
        ops += _gap(pos, tgt_size, src_size)
    # merge neighbouring pieces, then store the new data
    merged = []
    for s in ops:
        if merged and s[0] == "lit" and merged[-1][0] == "lit" and len(merged[-1][1]) + len(s[1]) <= CHUNK:
            merged[-1] = ("lit", merged[-1][1] + s[1])
        elif merged and s[0] == "src" and merged[-1][0] == "src" and merged[-1][1] + merged[-1][2] == s[1]:
            merged[-1] = ("src", merged[-1][1], merged[-1][2] + s[2])
        else:
            merged.append(s)
    os.makedirs(out_dir, exist_ok=True)
    chunks = []; chunk_of = {}; parts = []; part = None; part_size = 0
    def new_part():
        nonlocal part, part_size
        if part:
            part.close()
        parts.append("part-%02d.patch" % len(parts)); part = open(os.path.join(out_dir, parts[-1]), "wb"); part_size = 0
    final = []
    for s in merged:
        if s[0] != "lit":
            final.append(["s", s[1], s[2]] if s[0] == "src" else ["z", s[1]]); continue
        data = s[1]
        for k in range(0, len(data), CHUNK):
            piece = data[k:k + CHUNK]
            h = _sha1(piece)
            if h not in chunk_of:
                comp = gzip.compress(piece, 9, mtime=0)
                if part is None or part_size + len(comp) > PART:
                    new_part()
                chunk_of[h] = len(chunks)
                chunks.append([len(parts) - 1, part_size, len(comp), len(piece)])
                part.write(comp); part_size += len(comp)
            final.append(["c", chunk_of[h]])
    if part:
        part.close()
    # write the patched image too, if asked, and its checksum
    tgt_sha = hashlib.sha1()
    out = open(out_iso, "wb") if out_iso else None
    src = open(iso, "rb")
    for piece in _pieces(final, src, chunks, out_dir, parts):
        tgt_sha.update(piece)
        if out:
            out.write(piece)
    if out:
        out.close()
    samples = []
    for off in (0, PVD_LBA * SECTOR, src_size // 3, src_size // 2, 2 * src_size // 3, src_size - 65536):
        src.seek(off); samples.append([off, 65536, _sha1(src.read(65536))])
    src.close()
    manifest = {
        "format": FORMAT,
        "changes": list(notes),
        "source": {"size": src_size, "samples": samples},
        "target": {"size": tgt_size, "sha1": tgt_sha.hexdigest(), "name": name},
        "parts": [{"file": p, "size": os.path.getsize(os.path.join(out_dir, p)),
                   "sha1": _sha1(open(os.path.join(out_dir, p), "rb").read())} for p in parts],
        "chunks": chunks,
        "ops": final,
    }
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, separators=(",", ":"))
    total = sum(p["size"] for p in manifest["parts"])
    print(f"patch: {len(parts)} parts, {total / 2**20:.1f} MiB; target {tgt_size} bytes, sha1 {tgt_sha.hexdigest()}")


def _gap(a, b, src_size):
    out = []
    if a < min(b, src_size):
        out.append(("src", a, min(b, src_size) - a))
    if b > max(a, src_size):
        out.append(("zero", b - max(a, src_size)))
    return [("src", s[1], s[2]) if s[0] == "src" else ("lit", bytes(s[1])) if s[1] < CHUNK else ("zero", s[1])
            for s in out]


def _pieces(ops, src, chunks, patch_dir, parts):
    files = {}
    for op in ops:
        if op[0] == "s":
            src.seek(op[1]); left = op[2]
            while left:
                b = src.read(min(left, 8 << 20)); left -= len(b); yield b
        elif op[0] == "z":
            yield bytes(op[1])
        else:
            p, off, clen, rlen = chunks[op[1]]
            f = files.get(p) or files.setdefault(p, open(os.path.join(patch_dir, parts[p]), "rb"))
            f.seek(off); b = gzip.decompress(f.read(clen))
            assert len(b) == rlen
            yield b
    for f in files.values():
        f.close()


def apply(iso, patch_dir, out_iso):
    m = json.load(open(os.path.join(patch_dir, "manifest.json")))
    if m.get("format") != FORMAT:
        sys.exit("error: not a patch of this format")
    if os.path.getsize(iso) != m["source"]["size"]:
        sys.exit("error: this is not the expected original ISO (size differs)")
    src = open(iso, "rb")
    for off, n, h in m["source"]["samples"]:
        src.seek(off)
        if _sha1(src.read(n)) != h:
            sys.exit("error: this is not the expected original ISO (contents differ)")
    sha = hashlib.sha1()
    with open(out_iso, "wb") as out:
        for piece in _pieces(m["ops"], src, m["chunks"], patch_dir, [p["file"] for p in m["parts"]]):
            sha.update(piece); out.write(piece)
    ok = sha.hexdigest() == m["target"]["sha1"]
    print(f"wrote {out_iso}; sha1 {sha.hexdigest()} ({'ok' if ok else 'MISMATCH'})")
    if not ok:
        sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("make"); p.add_argument("iso"); p.add_argument("patch_dir")
    p.add_argument("replacements", nargs="+", metavar="ISO_PATH=FILE")
    p.add_argument("--iso", dest="out_iso"); p.add_argument("--name", default="patched.iso")
    p.add_argument("--note", action="append", default=[], help="a line describing the patch (repeatable)")
    p = sub.add_parser("apply"); p.add_argument("iso"); p.add_argument("patch_dir"); p.add_argument("out_iso")
    a = ap.parse_args()
    if a.cmd == "make":
        make(a.iso, a.patch_dir, a.replacements, a.out_iso, a.name, a.note)
    else:
        apply(a.iso, a.patch_dir, a.out_iso)


if __name__ == "__main__":
    main()
