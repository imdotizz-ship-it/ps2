#!/usr/bin/env python3
r"""Add the MotoGP 4 safety car (BMW M6) to MotoGP 08 as a new bike model, BIKE07.

The car goes into BIKES.MIX next to the six bikes (see mgp4to08/car.py); the extra
team and rider that use it are added to DATA.MIX by `data08.py --safety-car`.
Experimental: the car drives with the physics of a MotoGP bike (it leans in the
corners), its wheels do not turn, and the 08 rider sits inside it.

Usage:
  safetycar.py BIKES.MIX MGP4_DIR OUT_DIR [--template ORIGINAL_BIKES.MIX]
      BIKES.MIX: the original or the one from bikes4to08.py (BIKE07 is added to it)
      --template: the disc's original BIKES.MIX, whose BIKE04 is the model the car is built on
                  (needed when BIKES.MIX is a converted one: its BIKE04 is no longer the original)
"""
import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402
from mgp4to08 import car  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mix"); ap.add_argument("mgp4"); ap.add_argument("out")
    ap.add_argument("--template", help="original BIKES.MIX (default: BIKES.MIX itself)")
    a = ap.parse_args()
    data, entries = mix.read_mix(a.mix)
    tdata, tentries = mix.read_mix(a.template) if a.template else (data, entries)
    with tempfile.TemporaryDirectory() as tmp:     # the template bike, unpacked
        files = {}
        for e in tentries:
            n = e.name.upper()
            if n.endswith(".SLX"):
                n = n[:-4] + ".SLI"                   # hidden by bikes4to08.py: still the original model
            if n.startswith("BIKES\\BIKE04\\") and e.flag == 0:
                p = os.path.join(tmp, *n.split("\\"))
                os.makedirs(os.path.dirname(p), exist_ok=True)
                open(p, "wb").write(tdata[e.offset:e.offset + e.stored_size])
        slf, txd, txs, stats = car.build(os.path.join(tmp, "BIKES"), "BIKE04",
                                         os.path.join(a.mgp4, "bike_extra_p03.bin"),
                                         os.path.join(a.mgp4, "CourseCommon.bin"), "BIKE07")
    tmpl = next(e for e in entries if e.name.upper() == "BIKES\\BIKE04\\BIKE04.SLF")
    new = [("BIKES\\BIKE07\\BIKE07.SLF", slf), ("BIKES\\BIKE07\\BIKE07.TXS", txs),
           ("BIKES\\BIKE07\\PICTURES\\BIKE07.TXD", txd)]
    payloads = [data[e.offset:e.offset + e.stored_size] for e in entries]
    names = {e.name.upper() for e in entries}
    for name, payload in new:
        if name in names:
            sys.exit("error: %s is already in the archive" % name)
        entries.append(mix.MixEntry(name, 0, len(payload), len(payload), 0, tmpl.extra))
        payloads.append(payload)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, os.path.basename(a.mix))
    open(out, "wb").write(mix.write_mix(entries, payloads))
    print("BIKE07 <- MotoGP 4 safety car: %d triangles (LOD 1: %d)" % tuple(stats))
    print("wrote %s" % out)


if __name__ == "__main__":
    main()
