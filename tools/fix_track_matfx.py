#!/usr/bin/env python3
"""fix_track_matfx.py TRACK.MIX... : in converted track archives (tracks4to08.py), drop the MatFX
lightmap pass from the scene objects that carry MotoGP 4 geometry (see track08._no_matfx). In place."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402
from mgp4to08.build08 import Obj, rebuild_slf  # noqa: E402
from mgp4to08.slf import dirents  # noqa: E402
from mgp4to08.track08 import _no_matfx  # noqa: E402


def texnames(geom):
    out = []
    for m in geom.first(8).find(7):
        t = m.first(6)
        if t is not None:
            out.append(t.find(2)[0].data.split(b"\0")[0].decode("latin1").upper())
    return out


def fix_slf(d):
    _, es = dirents(d)
    out = {}; n = 0
    for i, e in enumerate(es):
        if e[3] not in (0x103, 0x203):
            continue
        try:
            o = Obj(d, e)
        except AssertionError:
            continue
        hit = False
        for at in o.atomics():
            names = texnames(at.first(0xF))
            if names and all(x.startswith("M4_") for x in names):
                _no_matfx(at); hit = True; n += 1
        if hit:
            out[i] = o
    return rebuild_slf(d, out), n


def main():
    for path in sys.argv[1:]:
        data, entries = mix.read_mix(path)
        payloads = []; total = 0
        for e in entries:
            p = data[e.offset:e.offset + e.stored_size]
            if e.name.upper().endswith(".SLF") and e.name.upper().startswith("TRACKS\\") and e.flag == 0:
                q, n = fix_slf(p)
                if n:
                    p = q; e.unpacked_size = len(p); total += n
            payloads.append(p)
        with open(path, "wb") as f:
            f.write(mix.write_mix(entries, payloads))
        print("%s: %d objects" % (os.path.basename(path), total))


if __name__ == "__main__":
    main()
