#!/usr/bin/env python3
"""fix_track_effects.py TRACK.MIX...: give every MotoGP 4 material of the converted track scenes its own
Selene effect slot (see track08.unique_effects). In place."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402
from mgp4to08.track08 import unique_effects  # noqa: E402

for path in sys.argv[1:]:
    data, entries = mix.read_mix(path)
    payloads = []; n = 0
    for e in entries:
        p = data[e.offset:e.offset + e.stored_size]
        if e.name.upper().endswith(".SLF") and e.name.upper().startswith("TRACKS\\") and e.flag == 0 and b"_Sector_" in p:
            q = unique_effects(p)
            if q != p:
                p = q; e.unpacked_size = len(p); n += 1
        payloads.append(p)
    with open(path, "wb") as f:
        f.write(mix.write_mix(entries, payloads))
    print("%s: %d scenes" % (os.path.basename(path), n))
