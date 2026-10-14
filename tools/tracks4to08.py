#!/usr/bin/env python3
r"""Put the MotoGP 4 circuits into MotoGP 08 (PS2), on the tracks both games share.

The visual scene of the MotoGP 08 track (every weather variant) is replaced by
the same circuit from MotoGP 4, fitted automatically onto the 08 track: a 2D
rotation/translation found from the 08 AI line and asphalt, then a height
correction so the MotoGP 4 ground lies on the 08 collision. Collision, AI
line, grid, cameras, visibility, lights and sky stay those of MotoGP 08, so
races, lap timing and the AI work as before.

Requires Python 3.8+, numpy and Pillow (pip install numpy pillow).

Usage:
  tracks4to08.py build TRACK.MIX MGP4_DIR OUT_DIR [--course NAME] [--budget N]
      TRACK.MIX  a track archive of the MotoGP 08 disc (TRACKS\JEREZ.MIX ...)
      MGP4_DIR   MOTOGP.DAT of MotoGP 4 extracted with gp4dat.py
      OUT_DIR    receives the new TRACK.MIX (put it back with ps2iso.py replace)
      --course   MotoGP 4 course name (default from the archive name)
      --budget   maximum triangles of the new scene (default: 2x the 08 scene).
                 The smallest/farthest details are dropped first. Lower it if
                 the game runs out of memory when loading the track.
  tracks4to08.py preview TRACK.MIX OUT.png
      six rider-eye views along the AI line (original or converted archive)

Tracks: ASSEN BRNO CATALUN DOHA DONNING ESTORIL JEREZ LEMANS MOTEGI MUGELLO
PHILLIPI SACHSEN SEPANG VALENCIA (the 08 ones without a MotoGP 4 counterpart,
INDIANA LAGUNA MISANO SHANGAI, are not handled).
"""

import argparse
import os
import re
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import mix  # noqa: E402

COURSES = {
    "ASSEN": "Assen", "BRNO": "Brno", "CATALUN": "Catalunya", "DOHA": "Qatar", "DONNING": "Donington",
    "ESTORIL": "Estoril", "JEREZ": "Jerez", "LEMANS": "Lemans", "MOTEGI": "Motegi", "MUGELLO": "Mugello",
    "PHILLIPI": "PhillipIsland", "SACHSEN": "Sachsenring", "SEPANG": "Sepang", "VALENCIA": "Valencia",
}


def _unpack(mix_path):
    data, entries = mix.read_mix(mix_path)
    files = {e.name.upper(): data[e.offset:e.offset + e.stored_size] for e in entries}
    return data, entries, files


def _scn(text):
    return {k.strip().lower(): v.strip() for k, v in re.findall(r"^(\w+)\s*=\s*(.+?)\s*$", text, re.M)}


def _layout(files):
    """track folder and the files the .SCN variants point to"""
    scns = [n for n in files if n.endswith(".SCN")]
    if not scns:
        raise SystemExit("error: no .SCN in this archive (not a track?)")
    folder = scns[0].rsplit("\\", 1)[0]
    scenes, txds, txss, info = set(), set(), set(), {}
    for n in scns:
        s = _scn(files[n].decode("latin1"))
        scenes.add(os.path.splitext(s["scnfile"])[0].upper())
        txds.add(os.path.splitext(s["txdfile"])[0].upper())
        txss.add(os.path.splitext(s["txsfile"])[0].upper())
        info.setdefault("bsp", os.path.splitext(s["bspfile"])[0].upper())
        info.setdefault("spl", os.path.splitext(s["splfile"])[0].upper())
        if "glwfile" in s:
            info.setdefault("glw", os.path.splitext(s["glwfile"])[0].upper())
    for n in files:     # every texture set / texture description of the track, also unused variants
        base = os.path.basename(n.replace("\\", "/"))
        stem = os.path.splitext(base)[0]
        if n.startswith(folder + "\\PICTURES\\") and n.endswith(".TXD") and any(stem.startswith(t) for t in txds):
            txds.add(stem)
        if n.startswith(folder + "\\") and n.endswith(".TXS") and any(stem.startswith(t) for t in txss):
            txss.add(stem)
    return folder, sorted(scenes), sorted(txds), sorted(txss), info


def cmd_build(args):
    import numpy as np
    from mgp4to08 import rwworld, track08
    from mgp4to08.build08 import Obj
    from mgp4to08.rw import parse_geometry
    from mgp4to08.slf import dirents

    data, entries, files = _unpack(args.mix)
    folder, scenes, txds, txss, info = _layout(files)
    track = folder.split("\\")[-1]
    course = args.course or COURSES.get(track)
    if not course:
        sys.exit(f"error: no MotoGP 4 course for {track}; pass --course")
    cpath = os.path.join(args.mgp4, f"Course{course}.bin"); fpath = os.path.join(args.mgp4, f"Course{course}_Free.bin")
    for p in (cpath, fpath):
        if not os.path.exists(p):
            sys.exit(f"error: {p} not found (extract MOTOGP.DAT with gp4dat.py)")
    print(f"{track} <- MotoGP 4 {course}")
    strips, tex = track08.load_mgp4(cpath, fpath)
    col, ter = rwworld.triangles(rwworld.world(files[f"{folder}\\{info['bsp']}.BSP"]))
    spl = files[f"{folder}\\{info['spl']}.SPL"].decode("latin1")
    fit, ground, H, share = track08.fit_track(strips, spl, col, ter)
    if share < 0.4:
        print(f"warning: only {share:.0%} of the 08 tarmac is covered by the MotoGP 4 road; "
              "the circuits differ too much or the fit failed (check the preview)")
    first = files[f"{folder}\\{scenes[0]}.SLF"]
    budget = args.budget
    if budget is None:
        _, es = dirents(first); n = 0
        for e in es:
            if e[3] in (0x103, 0x203):
                try:
                    for at in Obj(first, e).atomics():
                        n += parse_geometry(at.first(0xF)).ntri
                except AssertionError:
                    pass
        budget = 2 * n
    road_xz = col[np.isin(ter, ["TARMAC", "CORDOLO", "TARMACPIT", "GRASS", "SAND"])].mean(1)[:, [0, 2]]
    scene = track08.scene_strips(strips, fit, H, ground, tex)
    scene = track08.fill_holes(scene, col, ter, H)
    from scipy.spatial import cKDTree
    tarmac = cKDTree(col[np.isin(ter, ["TARMAC", "CORDOLO", "TARMACPIT"])].mean(1)[:, [0, 2]])
    scene = track08.apply_budget(scene, budget, road_xz, H, tarmac)
    used = set(); new = {}
    for s in scenes:
        new[f"{folder}\\{s}.SLF"] = track08.unique_effects(
            track08.build_scene(files[f"{folder}\\{s}.SLF"], scene, ground, used))
    glow = set()
    if "glw" in info and f"{folder}\\{info['glw']}.GLW" in files:
        glow = {m.upper() for m in re.findall(r"TextureName\s*=\s*(\S+)", files[f"{folder}\\{info['glw']}.GLW"].decode("latin1"))}
    cut = set()
    for t in txds:
        name = f"{folder}\\PICTURES\\{t}.TXD"
        if name in files:
            new[name], cut = track08.build_txd(files[name], tex, used, glow)
    for t in txss:
        name = f"{folder}\\{t}.TXS"
        if name in files:
            new[name] = track08.build_txs(files[name], used, cut)
    hide = {f"{folder}\\{s}.SLI" for s in scenes}
    payloads = []
    for e in entries:
        n = e.name.upper()
        if n in new:
            payloads.append(new[n]); e.flag, e.unpacked_size = 0, len(new[n])
            continue
        if n in hide:
            e.name = e.name[:-1] + "X"      # precompiled copy of the old scene: the game falls back to .SLF
        payloads.append(data[e.offset:e.offset + e.stored_size])
    os.makedirs(args.out, exist_ok=True)
    out = os.path.join(args.out, os.path.basename(args.mix))
    with open(out, "wb") as f:
        f.write(mix.write_mix(entries, payloads))
    print(f"wrote {out} ({', '.join(os.path.basename(k.replace(chr(92), '/')) for k in sorted(new))})")


def cmd_preview(args):
    import numpy as np
    from PIL import Image
    from mgp4to08 import align
    from mgp4to08.render import render
    from mgp4to08.view08 import scene

    data, entries, files = _unpack(args.mix)
    folder, scenes, txds, txss, info = _layout(files)
    slf = files[f"{folder}\\{scenes[0]}.SLF"]
    txd = files[f"{folder}\\PICTURES\\{txds[0]}.TXD"]
    line = align.spline_points(files[f"{folder}\\{info['spl']}.SPL"].decode("latin1"))
    tris, uvs, tids, cols, texs = scene(slf, txd)
    sheet = Image.new("RGB", (480 * 3, 300 * 2))
    for n, k in enumerate(np.linspace(0, len(line) - 1, 6).astype(int)):
        eye = line[k] + (0, 1.3, 0); tgt = line[(k + 6) % len(line)] + (0, 1.0, 0)
        im = render(tris, ("cam", eye, tgt, 70), size=(480, 300), texs=texs, uvs=uvs, tids=tids, colors=cols)
        sheet.paste(im, ((n % 3) * 480, (n // 3) * 300))
    sheet.save(args.png)
    print(f"wrote {args.png}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("build")
    p.add_argument("mix"); p.add_argument("mgp4"); p.add_argument("out")
    p.add_argument("--course"); p.add_argument("--budget", type=int)
    p = sub.add_parser("preview")
    p.add_argument("mix"); p.add_argument("png")
    args = parser.parse_args()
    {"build": cmd_build, "preview": cmd_preview}[args.cmd](args)


if __name__ == "__main__":
    main()
