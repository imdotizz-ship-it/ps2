#!/usr/bin/env python3
"""fix_txs.py MIX...: make every .TXS in the archives end with the empty line the game needs (in place).

The game reads a texture description file (TXS) up to an empty line; the converters used to drop it."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402

for path in sys.argv[1:]:
    data, entries = mix.read_mix(path)
    payloads = []; n = 0
    for e in entries:
        p = data[e.offset:e.offset + e.stored_size]
        if e.name.upper().endswith(".TXS") and e.flag == 0:
            nl = b"\r\n" if b"\r\n" in p else b"\n"
            q = p.rstrip(b"\r\n") + nl + nl
            if q != p:
                p = q; e.unpacked_size = len(p); n += 1
        payloads.append(p)
    with open(path, "wb") as f:
        f.write(mix.write_mix(entries, payloads))
    print("%s: %d TXS fixed" % (os.path.basename(path), n))
