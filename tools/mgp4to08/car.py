"""The MotoGP 4 safety car (BMW M6, `bike_extra_p03`) as a MotoGP 08 bike model.

The car body, lights, windows and its four (static) wheels go into the CHASSIS
object of a copy of an 08 bike; the bike parts (wheels, fork, swingarm, chain,
handlebar, mirrors, windscreen, number plates) are emptied, and the collision
shape (COLLISIONSHAPE) is stretched to the size of the car.
"""
import copy
import struct
import numpy as np
from PIL import Image

from .build08 import Obj, build_geometry, empty_geometry, make_material, rebuild_slf
from .mgp4obj import packets
from .mgp4mesh import mesh, strip_tris
from .ps2native import nativize_slf, template_materials
from .ps2tex import encode_into, rename
from .convert import build_atlas, ATLAS, ATLAS_NAME
from .rw import read, write
from .slf import dirents
from .texdb import load_texdb

# packets of bike_extra_p03: (LOD 0, LOD 1)
BODY = ([0, 3, 1, 2, 4], [5, 8, 6, 7, 9])
WHEELS = ([(11, 12, 13, 14), (19, 20, 21, 22), (27, 28, 29, 30), (35, 36, 37, 38)],
          [(15, 16, 17, 18), (23, 24, 25, 26), (31, 32, 33, 34), (39, 40, 41, 42)])
AXLE_FRONT, AXLE_REAR, TRACK, AXLE_Y = -1380.0, 1340.0, 775.0, 340.0     # millimetres, front at -z
Z0 = 705.0              # 08 bike space: z = (Z0 - z) / 1000 centres the car between the bike axles
KEEP = {"CHASSIS"}
HIDE_ALL_BUT = KEEP | {"COLLISIONSHAPE"}


def texname(tid):
    return "M4%04X" % tid


def _prelit(c):
    return (min(255, c[0] * 2), min(255, c[1] * 2), min(255, c[2] * 2), 255)


def _to08(p, n):
    return ((-p[0] / 1000.0, p[1] / 1000.0, (Z0 - p[2]) / 1000.0), (-n[0], n[1], -n[2]))


def car_triangles(path, lod):
    """[(tid, [(pos, nrm, uv, rgba)] * 3)] in 08 bike space for one level of detail"""
    d = open(path, "rb").read()
    end = d.find(b"TEX10001")
    meshes = [mesh(d, o) for o in packets(d, end)]
    out = []
    def add(m, offset=(0.0, 0.0, 0.0)):
        for s in m["strips"]:
            for a, b, c in strip_tris(s["verts"]):
                tri = []
                for v in (a, b, c):
                    p = tuple(v[0][i] + offset[i] for i in range(3))
                    pos, nrm = _to08(p, v[1])
                    tri.append((pos, nrm, v[2], _prelit(v[3])))
                out.append((s["tid"], tri))
    for i in BODY[lod]:
        add(meshes[i])
    for k, group in enumerate(WHEELS[lod]):
        rim = meshes[group[1]]
        side = 1.0 if rim["sphere"][0] > 0 else -1.0          # the rim face shows the outer side
        axle = AXLE_FRONT if k < 2 else AXLE_REAR             # the last two have the wider (rear) tyres
        for i in group:
            add(meshes[i], (side * TRACK, AXLE_Y, axle))
    return out


def _stretch(geom, fn):
    """move every vertex of an RW geometry chunk in place (same vertex count and layout)"""
    st = bytearray(geom.first(1).data)
    flags, nt, nv, _ = struct.unpack_from("<4I", st, 0)
    o = 16
    if flags & 0x08:
        o += 4 * nv
    ntex = (flags >> 16) & 0xff or (2 if flags & 0x80 else 1 if flags & 0x04 else 0)
    o += 8 * nv * ntex + 8 * nt
    sph = o; o += 16 + 8
    P = np.frombuffer(bytes(st[o:o + 12 * nv]), "<f4").reshape(nv, 3).astype(float)
    Q = fn(P)
    st[o:o + 12 * nv] = Q.astype("<f4").tobytes()
    ctr = (Q.min(0) + Q.max(0)) / 2; rad = float(np.linalg.norm(Q - ctr, axis=1).max())
    struct.pack_into("<4f", st, sph, *ctr, rad)
    geom.first(1).data = bytes(st)


def build(bikes_dir, template, car_path, common_path, new_slot):
    """SLF, TXD and TXS of a new bike slot made from `template` (e.g. BIKE04)"""
    base = "%s/%s/%s" % (bikes_dir, template, template)
    d = open(base + ".SLF", "rb").read()
    _, es = dirents(d)
    objs = {e[0]: Obj(d, e) for e in es if e[3] in (0x303, 0x403)}
    byshort = {k.split("@")[0]: v for k, v in objs.items()}
    db = load_texdb([car_path]); own = set(db)
    for k, v in load_texdb([common_path]).items():
        db.setdefault(k, v)
    ch = byshort["CHASSIS"]; ats = ch.atomics()
    mats0 = ats[0].first(0xF).first(8).children[1:]
    tmpl_liv = mats0[0]; tmpl_obj = mats0[1] if len(mats0) > 1 else mats0[0]
    stats = []
    lods = [car_triangles(car_path, min(lod, 1)) for lod in range(len(ats[:2]))]
    used = sorted({t for tris in lods for t, _ in tris})
    atlas_idx, atlas_pal, rects = build_atlas(db, used, ATLAS)
    for lod, at in enumerate(ats[:2]):
        tris = []
        for t, tri in lods[lod]:
            x, y, w, h = rects[t]
            fu = np.floor(min(v[2][0] for v in tri)); fv = np.floor(min(v[2][1] for v in tri))
            tris.append((0, [(v[0], v[1], ((x + 0.5 + min(max(v[2][0] - fu, 0), 1) * (w - 1)) / ATLAS,
                                           (y + 0.5 + min(max(v[2][1] - fv, 0), 1) * (h - 1)) / ATLAS), v[3])
                             for v in tri]))
        g = at.first(0xF)
        ng, nv, nt = build_geometry(g, tris, [make_material(tmpl_liv, ATLAS_NAME)])
        at.children[at.children.index(g)] = ng
        stats.append(nt)
    # stretch the bike's collision shape over the car: x +-0.95 m, top 1.45 m, length of the car
    col = byshort.get("COLLISIONSHAPE")
    if col is not None:
        g = col.atomics()[0].first(0xF)
        def fit(P):
            lo, hi = P.min(0), P.max(0)
            Q = P.copy()
            Q[:, 0] = P[:, 0] / max(abs(lo[0]), abs(hi[0])) * 0.95
            Q[:, 1] = lo[1] + (P[:, 1] - lo[1]) / (hi[1] - lo[1]) * (1.45 - lo[1])
            Q[:, 2] = -1.775 + (P[:, 2] - lo[2]) / (hi[2] - lo[2]) * (3.035 + 1.775)
            return Q
        _stretch(g, fit)
    for short, o in byshort.items():
        if short in HIDE_ALL_BUT:
            continue
        for at in o.atomics():
            g = at.first(0xF); at.children[at.children.index(g)] = empty_geometry(g)
    # BIKE07 has no .SLI: the geometry and materials must be native (templates: the template's .SLI)
    with open(base + ".SLI", "rb") as f:
        slf = nativize_slf(rebuild_slf(d, objs), template_materials(d, f.read()))
    slf = slf.replace(template.encode(), new_slot.encode()).replace(
        template.capitalize().encode(), new_slot.capitalize().encode())
    # textures: the game takes only the textures a bike ships with, so the MotoGP 4 textures go into
    # an atlas written over the template's livery textures (see convert.build_atlas)
    td = read(open("%s/%s/PICTURES/%s.TXD" % (bikes_dir, template, template), "rb").read())[0]
    for tn in td.find(0x15):
        name = tn.children[1].data.split(b"\0")[0].decode().upper()
        if name.startswith("CHASSIS") and name.endswith("_0"):
            encode_into(tn, atlas_idx, atlas_pal)
    txd = write([td])
    txs = open(base + ".TXS", "rb").read()
    return slf, txd, txs, stats
