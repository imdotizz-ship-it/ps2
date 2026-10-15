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
                    [--option ID LABEL DEFAULT v1:ISO_PATH=FILE,v2:ISO_PATH=FILE,...]
                    [--profile ID LABEL NOTE ISO_PATH=FILE,...,@VALUE:ISO_PATH=FILE,...]
  isopatch.py apply ORIGINAL.iso PATCH_DIR OUT.iso [--option ID=VALUE] [--profile ID]

An option is a choice made when the image is built (the field of view, say): one
replacement file per value, all of the same size.
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
PART = 8 << 20            # and stored in part files of about 8 MiB (easy to download on a phone)


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


def _plan(img, entries, src_size, replacements, log=True):
    """the target image as merged pieces: ('src', offset, n), ('lit', bytes), ('zero', n)"""
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
        if log:
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
    merged = []
    for s in ops:
        if merged and s[0] == "lit" and merged[-1][0] == "lit" and len(merged[-1][1]) + len(s[1]) <= CHUNK:
            merged[-1] = ("lit", merged[-1][1] + s[1])
        elif merged and s[0] == "src" and merged[-1][0] == "src" and merged[-1][1] + merged[-1][2] == s[1]:
            merged[-1] = ("src", merged[-1][1], merged[-1][2] + s[2])
        else:
            merged.append(s)
    return merged, tgt_size


class _Store:
    """new data, gzip-compressed in pieces of at most CHUNK bytes, identical pieces kept once"""

    def __init__(self, out_dir):
        self.dir = out_dir; self.chunks = []; self.of = {}; self.parts = []; self.f = None; self.size = 0

    def add(self, data):
        ids = []
        for k in range(0, len(data), CHUNK):
            piece = data[k:k + CHUNK]
            h = _sha1(piece)
            if h not in self.of:
                comp = gzip.compress(piece, 9, mtime=0)
                if self.f is None or self.size + len(comp) > PART:
                    if self.f:
                        self.f.close()
                    self.parts.append("part-%02d.patch" % len(self.parts))
                    self.f = open(os.path.join(self.dir, self.parts[-1]), "wb"); self.size = 0
                self.of[h] = len(self.chunks)
                self.chunks.append([len(self.parts) - 1, self.size, len(comp), len(piece)])
                self.f.write(comp); self.size += len(comp)
            ids.append(self.of[h])
        return ids

    def close(self):
        if self.f:
            self.f.close()


def _compile(img, entries, src_size, replacements, option, store, log=True):
    """ops of one target image; option values (same layout) become "v" pieces"""
    def with_overrides(over):
        keys = {o.partition("=")[0].upper() for o in over}
        return [r for r in replacements if r.partition("=")[0].upper() not in keys] + list(over)
    base, tgt_size = _plan(img, entries, src_size, with_overrides(option[3][option[2]]) if option else replacements, log)
    variants = {}
    if option:
        for v, over in option[3].items():
            plan, size = _plan(img, entries, src_size, with_overrides(over), log=False)
            if size != tgt_size or len(plan) != len(base) or any(
                    x[0] != y[0] or (x[0] == "lit" and len(x[1]) != len(y[1])) or (x[0] != "lit" and x != y)
                    for x, y in zip(plan, base)):
                sys.exit(f"error: option {option[0]}={v} changes the layout (sizes must not change)")
            variants[v] = plan
    diff = {i for i, s in enumerate(base) if s[0] == "lit" and any(variants[v][i][1] != s[1] for v in variants)}
    final = []
    for i, s in enumerate(base):
        if s[0] == "src":
            final.append(["s", s[1], s[2]])
        elif s[0] == "zero":
            final.append(["z", s[1]])
        elif i in diff:
            final.append(["v", option[0], {str(v): store.add(variants[v][i][1]) for v in variants}])
        else:
            final += [["c", c] for c in store.add(s[1])]
    return final, tgt_size


def make(iso, out_dir, replacements, out_iso=None, name="patched.iso", notes=(), option=None, profiles=()):
    """option: (id, label, default value, {value: [ISO_PATH=FILE overrides]}, unit, note), e.g. one
    DATA.MIX per field of view, every value giving files of the same sizes.
    profiles: [(id, label, note, [ISO_PATH=FILE overrides], {value: [overrides]} or None)]:
    alternative images (an experimental extra, say) chosen with a checkbox"""
    img = DiscImage(iso)
    if img.sector_size != SECTOR:
        sys.exit("error: only plain 2048-byte-sector ISO images are supported")
    entries = {e.path.upper(): e for e in img.walk() if not e.is_dir}
    src_size = os.path.getsize(iso)
    os.makedirs(out_dir, exist_ok=True)
    store = _Store(out_dir)
    ops, tgt_size = _compile(img, entries, src_size, replacements, option, store)
    built = []
    for pid, label, note, over, opt_over in profiles:
        keys = {o.partition("=")[0].upper() for o in over}
        repl = [r for r in replacements if r.partition("=")[0].upper() not in keys] + list(over)
        popt = option and (option[:3] + (opt_over or option[3],) + tuple(option[4:]))
        print(f"profile {pid}:")
        pops, psize = _compile(img, entries, src_size, repl, popt, store)
        built.append({"id": pid, "label": label, "note": note, "ops": pops, "size": psize})
    store.close()
    src = open(iso, "rb")
    def shas_of(the_ops, write_default):
        values = [str(v) for v in option[3]] if option else [None]
        out = {}
        for v in values:
            sha = hashlib.sha1()
            w = write_default and (v is None or v == str(option[2]))
            f = open(out_iso, "wb") if w else None
            for piece in _pieces(the_ops, src, store.chunks, out_dir, store.parts, {option[0]: v} if option else {}):
                sha.update(piece)
                if f:
                    f.write(piece)
            if f:
                f.close()
            out[v] = sha.hexdigest()
        return out
    shas = shas_of(ops, bool(out_iso))
    for pr in built:
        pr["sha1"] = shas_of(pr["ops"], False)
        if not option:
            pr["sha1"] = pr["sha1"][None]
    samples = []
    for off in (0, PVD_LBA * SECTOR, src_size // 3, src_size // 2, 2 * src_size // 3, src_size - 65536):
        src.seek(off); samples.append([off, 65536, _sha1(src.read(65536))])
    src.close()
    # content-addressed part names: a CDN or browser cache can never mix two patch versions
    for i, p in enumerate(store.parts):
        h = _sha1(open(os.path.join(out_dir, p), "rb").read())[:10]
        q = "part-%02d-%s.patch" % (i, h)
        os.replace(os.path.join(out_dir, p), os.path.join(out_dir, q))
        store.parts[i] = q
    manifest = {
        "format": FORMAT,
        "changes": list(notes),
        "source": {"size": src_size, "samples": samples},
        "target": {"size": tgt_size, "name": name,
                   "sha1": shas[str(option[2])] if option else shas[None]},
        "parts": [{"file": p, "size": os.path.getsize(os.path.join(out_dir, p)),
                   "sha1": _sha1(open(os.path.join(out_dir, p), "rb").read())} for p in store.parts],
        "chunks": store.chunks,
        "ops": ops,
    }
    if option:
        manifest["options"] = [{"id": option[0], "label": option[1], "default": str(option[2]),
                                "values": [str(v) for v in option[3]], "sha1": shas,
                                "unit": option[4] if len(option) > 4 else "",
                                "note": option[5] if len(option) > 5 else ""}]
    if built:
        manifest["profiles"] = built
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, separators=(",", ":"))
    total = sum(p["size"] for p in manifest["parts"])
    print(f"patch: {len(store.parts)} parts, {total / 2**20:.1f} MiB; target {tgt_size} bytes, sha1 {manifest['target']['sha1']}")


def _gap(a, b, src_size):
    out = []
    if a < min(b, src_size):
        out.append(("src", a, min(b, src_size) - a))
    if b > max(a, src_size):
        out.append(("zero", b - max(a, src_size)))
    return [("src", s[1], s[2]) if s[0] == "src" else ("lit", bytes(s[1])) if s[1] < CHUNK else ("zero", s[1])
            for s in out]


def _pieces(ops, src, chunks, patch_dir, parts, choice=None):
    files = {}
    expanded = []
    for op in ops:
        if op[0] == "v":
            expanded += [["c", c] for c in op[2][str(choice[op[1]])]]
        else:
            expanded.append(op)
    for op in expanded:
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


def apply(iso, patch_dir, out_iso, options=(), profile=None):
    m = json.load(open(os.path.join(patch_dir, "manifest.json")))
    ops, want_sha = m["ops"], None
    if profile:
        pr = next((p for p in m.get("profiles", []) if p["id"] == profile), None)
        if pr is None:
            sys.exit(f"error: unknown profile {profile!r}")
        ops, want_sha = pr["ops"], pr["sha1"]
    choice = {o["id"]: o["default"] for o in m.get("options", [])}
    for spec in options:
        k, _, v = spec.partition("=")
        opt = next((o for o in m.get("options", []) if o["id"] == k), None)
        if opt is None or v not in opt["values"]:
            sys.exit(f"error: unknown option {spec!r}")
        choice[k] = v
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
        for piece in _pieces(ops, src, m["chunks"], patch_dir, [p["file"] for p in m["parts"]], choice):
            sha.update(piece); out.write(piece)
    want = m["target"]["sha1"]
    for o in m.get("options", []):
        want = o["sha1"][choice[o["id"]]]
    if want_sha is not None:
        want = want_sha[choice[m["options"][0]["id"]]] if isinstance(want_sha, dict) else want_sha
    ok = sha.hexdigest() == want
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
    p.add_argument("--option", nargs=4, metavar=("ID", "LABEL", "DEFAULT", "VALUES"),
                   help="a choice in the patch: VALUES is v1:ISO_PATH=FILE,v2:ISO_PATH=FILE,...")
    p.add_argument("--profile", nargs=4, action="append", default=[], metavar=("ID", "LABEL", "NOTE", "OVERRIDES"),
                   help="an alternative image: OVERRIDES is ISO_PATH=FILE,...; add @VALUE:ISO_PATH=FILE "
                        "items to override option values too")
    p.add_argument("--option-unit", default="", help="unit shown after the option value")
    p.add_argument("--option-note", default="", help="a line explaining the option")
    p = sub.add_parser("apply"); p.add_argument("iso"); p.add_argument("patch_dir"); p.add_argument("out_iso")
    p.add_argument("--option", action="append", default=[], metavar="ID=VALUE")
    p.add_argument("--profile", help="an alternative image of the patch (see its manifest)")
    a = ap.parse_args()
    if a.cmd == "make":
        option = None
        if a.option:
            oid, label, default, spec = a.option
            values = {}
            for item in spec.split(","):
                v, _, over = item.partition(":")
                values.setdefault(v, []).append(over)
            option = (oid, label, default, values, a.option_unit, a.option_note)
        profiles = []
        for pid, label, note, spec in a.profile:
            over = []; opt_over = {}
            for item in spec.split(","):
                if item.startswith("@"):
                    v, _, o = item[1:].partition(":")
                    opt_over.setdefault(v, []).append(o)
                else:
                    over.append(item)
            profiles.append((pid, label, note, over, opt_over or None))
        make(a.iso, a.patch_dir, a.replacements, a.out_iso, a.name, a.note, option, profiles)
    else:
        apply(a.iso, a.patch_dir, a.out_iso, a.option, a.profile)


if __name__ == "__main__":
    main()
