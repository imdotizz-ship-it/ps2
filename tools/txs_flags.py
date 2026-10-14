#!/usr/bin/env python3
"""txs_flags.py MIX DROP...: remove flag text (e.g. Zc) from the M4_* entries of every TXS in the archive (in place)"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402
path, drop = sys.argv[1], sys.argv[2:]
data, entries = mix.read_mix(path); payloads = []
for e in entries:
    p = data[e.offset:e.offset + e.stored_size]
    if e.name.upper().endswith(".TXS") and e.flag == 0:
        lines = p.decode("latin1").split("\r\n")
        for i, l in enumerate(lines):
            if l.startswith("M4"):
                name, flags = l[:36], l[36:]
                for f in drop: flags = flags.replace(f, "")
                lines[i] = name + flags
        q = "\r\n".join(lines).encode("latin1")
        if q != p: p = q; e.unpacked_size = len(p)
    payloads.append(p)
open(path, "wb").write(mix.write_mix(entries, payloads)); print("ok")
