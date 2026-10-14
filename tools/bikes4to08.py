#!/usr/bin/env python3
r"""Put the MotoGP 4 bikes into MotoGP 08 (PS2).

Each of the six MotoGP-class bike models of MotoGP 08 (BIKE01..BIKE06 in
BIKES.MIX) gets the body (fairing, frame, engine, exhaust, tail, dashboard)
and windscreen of one MotoGP 4 bike, with its textures. Wheels, forks,
swingarm, handlebars and chain stay those of MotoGP 08, so the physics and the
rider animations are untouched. The bike's .SLI (precompiled PS2 copy of the
model) is renamed inside the archive so the game loads the new .SLF, whose geometry is
pre-instanced for the PS2 like the .SLI's (mgp4to08/ps2native.py): the game hangs when it has to
instance a bike's plain geometry itself.

Requires Python 3.8+, numpy and Pillow (pip install numpy pillow).

Usage:
  bikes4to08.py build BIKES.MIX MGP4_DIR OUT_DIR [--map BIKE01=duc_65 ...]
      BIKES.MIX  from the MotoGP 08 disc (ps2iso.py extract)
      MGP4_DIR   MOTOGP.DAT of MotoGP 4 extracted with gp4dat.py
      OUT_DIR    receives BIKES.MIX (to put back with ps2iso.py replace)
                 and the converted SLF/TXD/TXS of each slot
  bikes4to08.py preview BIKES.MIX OUT.png
      render the six bikes of an archive (original or converted)

Default mapping (MotoGP 08 model -> MotoGP 4 bike, same manufacturer):
  BIKE01 Ducati          -> duc_65  (Capirossi, Ducati Marlboro)
  BIKE02 Suzuki          -> suz_21  (Hopkins, Suzuki)
  BIKE03 Kawasaki        -> kaw_56  (Nakano, Kawasaki)
  BIKE04 Repsol Honda    -> rep_69  (Hayden, Repsol Honda)
  BIKE05 Yamaha          -> for_46  (Rossi, Gauloises Yamaha)
  BIKE06 satellite Honda -> mov_15  (Gibernau, Movistar Honda)
Any bike_motogp_*.bin of MotoGP 4 can be used (name without prefix/suffix).
"""

import argparse
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402
from mgp4to08.ps2native import nativize_slf, template_materials  # noqa: E402

DEFAULT_MAP = {
    "BIKE01": "duc_65",
    "BIKE02": "suz_21",
    "BIKE03": "kaw_56",
    "BIKE04": "rep_69",
    "BIKE05": "for_46",
    "BIKE06": "mov_15",
}


def _unpack(mix_path, dest):
    data, entries = mix.read_mix(mix_path)
    for e in entries:
        parts = [p for p in e.name.split("\\") if p not in ("", ".", "..")]
        path = os.path.join(dest, *parts)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data[e.offset:e.offset + e.stored_size])
    return data, entries


def cmd_build(args):
    from mgp4to08.convert import convert

    mapping = dict(DEFAULT_MAP)
    for spec in args.map or []:
        slot, sep, bike = spec.partition("=")
        if not sep or slot.upper() not in DEFAULT_MAP:
            sys.exit(f"error: expected BIKE0n=team_nn, got {spec!r}")
        mapping[slot.upper()] = bike
    common = os.path.join(args.mgp4, "CourseCommon.bin")
    if not os.path.exists(common):
        sys.exit(f"error: {common} not found (extract MOTOGP.DAT with gp4dat.py)")
    os.makedirs(args.out, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        data, entries = _unpack(args.mix, tmp)
        new = {}
        for slot, bike in sorted(mapping.items()):
            bike_path = os.path.join(args.mgp4, f"bike_motogp_{bike}.bin")
            if not os.path.exists(bike_path):
                sys.exit(f"error: {bike_path} not found")
            slf, txd, txs, stats = convert(os.path.join(tmp, "BIKES"), slot, bike_path, common)
            # the game hangs instancing a bike's plain geometry itself: ship native geometry and the
            # native form of the materials, copied from the slot's own .SLI
            base = os.path.join(tmp, "BIKES", slot, slot)
            with open(base + ".SLF", "rb") as f, open(base + ".SLI", "rb") as g:
                slf = nativize_slf(slf, template_materials(f.read(), g.read()))
            files = {
                f"BIKES\\{slot}\\{slot}.SLF": slf,
                f"BIKES\\{slot}\\{slot}.TXS": txs,
                f"BIKES\\{slot}\\PICTURES\\{slot}.TXD": txd,
            }
            for name, blob in files.items():
                with open(os.path.join(args.out, name.split("\\")[-1]), "wb") as f:
                    f.write(blob)
            new.update({k.upper(): v for k, v in files.items()})
            print(f"{slot} <- {bike}: body {stats['hi'][1]} triangles (LOD 1: {stats['mid'][1]}), "
                  f"windscreen {stats['glass'][1]}")
        payloads = []
        for e in entries:
            name = e.name.upper()
            if name in new:
                payloads.append(new[name])
                e.flag, e.unpacked_size = 0, len(new[name])
                continue
            stem, ext = os.path.splitext(name)
            if ext == ".SLI" and stem.split("\\")[-1] in mapping and name.startswith("BIKES\\"):
                e.name = e.name[:-1] + "X"      # hide the precompiled model: the game falls back to .SLF
            payloads.append(data[e.offset:e.offset + e.stored_size])
        out_mix = os.path.join(args.out, "BIKES.MIX")
        with open(out_mix, "wb") as f:
            f.write(mix.write_mix(entries, payloads))
        print(f"wrote {out_mix}")


def cmd_preview(args):
    from PIL import Image
    from mgp4to08.render import render
    from mgp4to08.view08 import scene

    with tempfile.TemporaryDirectory() as tmp:
        _unpack(args.mix, tmp)
        ims = []
        for slot in sorted(DEFAULT_MAP):
            base = os.path.join(tmp, "BIKES", slot)
            with open(os.path.join(base, slot + ".SLF"), "rb") as f:
                slf = f.read()
            with open(os.path.join(base, "PICTURES", slot + ".TXD"), "rb") as f:
                txd = f.read()
            tris, uvs, tids, cols, texs = scene(slf, txd, skip=("COLLISION", "DIRT", "BLURRED"))
            ims.append(render(tris, "persp", size=(400, 300), texs=texs, uvs=uvs, tids=tids, colors=cols))
    sheet = Image.new("RGB", (1200, 600))
    for k, im in enumerate(ims):
        sheet.paste(im, ((k % 3) * 400, (k // 3) * 300))
    sheet.save(args.png)
    print(f"wrote {args.png}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("mix")
    p.add_argument("mgp4")
    p.add_argument("out")
    p.add_argument("--map", action="append", metavar="BIKE0n=team_nn")
    p = sub.add_parser("preview")
    p.add_argument("mix")
    p.add_argument("png")
    args = parser.parse_args()
    {"build": cmd_build, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    main()
