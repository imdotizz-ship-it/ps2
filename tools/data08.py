#!/usr/bin/env python3
r"""Gameplay data mods for MotoGP 08 (PS2): AI aggression and a TV-style chase camera.

Both live in DATA.MIX as .BML files (binary XML, see bml.py):
  DATA\AIPARAMS.BML  the CPU riders keep half the distance from each other: avoidance distance,
                     collision boxes and braking distance are halved, overtakes pass closer and
                     defending riders steer harder, so contacts and falls between bots happen
                     about twice as often (the values that concern the human rider are kept)
  DATA\CAMERAS.BML   the in-race camera button gets a high chase view, like a TV helicopter
                     shot, in place of the second cockpit view

Usage:
  data08.py DATA.MIX OUT_DIR       writes OUT_DIR/DATA.MIX (put it back with ps2iso.py replace)
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bml  # noqa: E402
import mix  # noqa: E402

AI_CHANGES = {
    "General/Avoiding_Distance": "4",      # 7
    "Brake/CollSize_Front": "0.9",         # 1.8
    "Brake/CollSize_Lateral": "0.4",       # 0.8
    "Brake/CollDistance_Front": "2.7",     # 5.5
    "Overtake/Overt_Lateral_Offs": "3",    # 5
    "Defense/Def_Steer_Mult": "0.30",      # 0.15
}

TV_SLOT = "3"          # the bonnet camera, not used by any camera list
TV_GAME_INDEX = "2"    # replaces the second cockpit view (camera 6) in the in-race cycle
TV_VALUES = {
    "fFocal": "60",
    "fExtCamFinalFocal": "60",
    "vCameraPos": "0.0, 6.5, -11.0",
    "vCameraDir": "0.0, -5.0, 11.0",
    "vCameraPosBack": "0.0, 5.0, 9.0",
}


def ai_params(d):
    return bml.set_values(d, AI_CHANGES)


def _text_node(n, name):
    for c in n.children:
        if c.kind == 1 and c.name == name:
            return next(t for t in c.children if t.kind == 3)
    raise KeyError(name)


def cameras(d):
    root = bml.load(d)
    cams = {a[1]: n for n in root.children if n.name == "CAMERA" for a in n.attrs if a[0] == "index"}
    tv = copy.deepcopy(cams["2"])          # the far chase camera, moved up and back
    for a in tv.attrs:
        if a[0] == "index":
            a[1] = TV_SLOT
    for k, v in TV_VALUES.items():
        _text_node(tv, k).value = v
    root.children[root.children.index(cams[TV_SLOT])] = tv
    for n in root.children:
        if n.name == "GAME" and dict((a[0], a[1]) for a in n.attrs).get("index") == TV_GAME_INDEX:
            next(t for t in n.children if t.kind == 3).value = TV_SLOT
    return bml.save(root)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mix"); ap.add_argument("out")
    a = ap.parse_args()
    data, entries = mix.read_mix(a.mix)
    files = {e.name.upper(): e for e in entries}
    new = {}
    for name, fn in (("DATA\\AIPARAMS.BML", ai_params), ("DATA\\CAMERAS.BML", cameras)):
        e = files[name]
        if e.flag != 0:
            raise SystemExit("error: %s is compressed in this archive" % name)
        raw = data[e.offset:e.offset + e.stored_size]
        new[name] = fn(raw)
    payloads = []
    for e in entries:
        if e.name.upper() in new:
            p = new[e.name.upper()]; e.flag, e.unpacked_size = 0, len(p)
        else:
            p = data[e.offset:e.offset + e.stored_size]
        payloads.append(p)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, os.path.basename(a.mix))
    with open(out, "wb") as f:
        f.write(mix.write_mix(entries, payloads))
    print("wrote %s (%s)" % (out, ", ".join(sorted(new))))


if __name__ == "__main__":
    main()
