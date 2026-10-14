"""Replace the visual scene of a MotoGP 08 track with the same circuit from MotoGP 4.

Kept from MotoGP 08: collision (.BSP/.ADJ), AI line and grid (.SPL), cameras,
visibility (.PVS), lights, sky. Every object of the 08 scene stays in place
(same order, names and ids, so the .PVS keeps working); their geometry is
replaced by the MotoGP 4 triangles that fall in the same sector.
"""
import re
import struct
import numpy as np
from PIL import Image

from . import align, ps2tex, rwworld, track4, trktex
from .build08 import Obj, build_geometry_strips, make_material, rebuild_slf, empty_geometry
from .rw import read, write, parse_geometry, material_texnames, string_chunk
from .slf import dirents, objhdr

KEEP_OBJECTS = re.compile(r"^(palma|pino|meccanico|ambulanza)", re.I)   # 08 props kept as they are
FALLBACK = "M4_GREY"


def texname(tid, decal=False):
    """MotoGP 4 texture in the 08 dictionary; blended decal uses get their own cut-out copy"""
    return "M4_%04d%s" % (tid, "D" if decal else "")


def load_mgp4(course_path, free_path):
    strips = [s for s in track4.course(course_path) if s["kind"] == "W" or _world_local(s)]
    tex = trktex.load(open(free_path, "rb").read())
    return strips, tex


def _world_local(s):
    P = np.array([v[0] for v in s["verts"]])
    c = (P.min(0) + P.max(0)) / 2
    return np.abs(c).max() > 20000            # "local" meshes already placed in world space


def fit_track(strips, spl_text, col_tris, col_terrain, log=print):
    """align MotoGP 4 onto the 08 circuit and build the vertical correction; returns the
    transform, the textures laid on the 08 ground, the 08 height grid and the share of the
    08 tarmac covered by the MotoGP 4 road"""
    from scipy.spatial import cKDTree
    W = np.array([v[0] for s in strips for v in s["verts"]], float)
    near = (np.abs(W[:, 0]) < 1.0e6) & (np.abs(W[:, 2]) < 1.0e6) & (W[:, 1] < 6.0e4)
    m4 = W[near][:, [0, 2]] / 1000.0
    line = align.spline_points(spl_text)
    starts = align.coarse(m4, line[:, [0, 2]], top=4)
    log("  coarse fit: " + ", ".join("%.0f deg (%.1f m)" % (a, sc) for a, _, _, sc in starts))
    # every MotoGP 4 triangle (millimetres) with its texture, and the flat opaque ones
    T4 = []; tid4 = []; blend4 = []
    for s in strips:
        for a_, b_, c_ in track4.triangles(s["verts"]):
            T4.append((a_[0], b_[0], c_[0])); tid4.append(s["tid"]); blend4.append(s["flags"][:1] == (1,))
    T4 = np.array(T4, float); tid4 = np.array(tid4); blend4 = np.array(blend4)
    nrm = np.cross(T4[:, 1] - T4[:, 0], T4[:, 2] - T4[:, 0]); ln = np.linalg.norm(nrm, axis=1)
    flat = (ln > 0) & (np.abs(nrm[:, 1]) > 0.85 * ln)
    small = np.linalg.norm(T4 - T4[:, [1, 2, 0]], axis=2).max(1) < 100000     # not the sky dome
    sel = flat & ~blend4 & small
    rng = np.random.default_rng(1)
    samples = align.area_samples(col_tris[col_terrain == "TARMAC"][:, :, [0, 2]], 0.5, rng)
    t08 = cKDTree(samples)
    # the MotoGP 4 asphalt: among the textures under the 08 AI line, the one whose surface best
    # matches the 08 tarmac after a rotation/translation/scale fit (ICP) both ways
    best = None
    for ang0, t0, c, _ in starts:          # each starting orientation, its likely asphalt textures
        under = _under_line(T4[sel] / 1000.0, tid4[sel], ang0, t0, c, line[:, [0, 2]])
        here = {}
        for k in sorted(under, key=lambda k: -under[k])[:5]:
            dst = align.area_samples(T4[sel & (tid4 == k)][:, :, [0, 2]] / 1000.0, 0.5, rng)
            if len(dst) < 200:
                continue
            a2, t2, s2, rec = align.icp(samples, dst, ang0, t0, c)
            prec = (t08.query((dst - t2) @ align._rot(a2) / s2 + c)[0] < 2).mean()
            here[k] = (rec, prec)
            f = 2 * rec * prec / max(rec + prec, 1e-9)
            if best is None or f > best[0]:
                best = (f, k, a2, t2, s2, here)
    f, road_tid, ang, t, sc, scores = best
    roadlike = [road_tid] + [k for k, (rec, prec) in scores.items() if k != road_tid and prec > 0.6 and rec > 0.1]
    log("  asphalt texture %d (match %.0f%%), rotation %.2f deg, scale %.4f" % (road_tid, f * 100, ang, sc))
    fit = align.Fit(ang, t, c, s=sc)
    # smooth horizontal warp laying the MotoGP 4 asphalt on the 08 tarmac
    road4 = align.area_samples(T4[sel & np.isin(tid4, roadlike)][:, :, [0, 2]], 0.5e-6, rng)
    warp = align.warp_field(fit, road4, samples)
    fit = align.Fit(ang, t, c, s=sc, warp=warp)
    # coverage: share of the 08 tarmac under the MotoGP 4 asphalt
    res = 0.5; half = 1500; n = int(2 * half / res)
    img = Image.new("1", (n, n)); from PIL import ImageDraw; dr = ImageDraw.Draw(img)
    for P in fit.xz(T4[sel & np.isin(tid4, roadlike)][:, :, [0, 2]].reshape(-1, 2)).reshape(-1, 3, 2):
        dr.polygon([((x + half) / res, (z + half) / res) for x, z in P], fill=1)
    mask = np.array(img)
    ij = ((samples + half) / res).astype(int).clip(0, n - 1)
    share = mask[ij[:, 1], ij[:, 0]].mean()
    log("  warped: 08 tarmac covered by MotoGP 4 asphalt %.0f%% (largest move %.1f m)"
        % (share * 100, np.linalg.norm(warp[0], axis=2).max()))
    # MotoGP 4 textures lying on the 08 tarmac = road surface; flat ones over the collision = ground
    tar = col_tris[np.isin(col_terrain, ["TARMAC", "CORDOLO", "TARMACPIT"])]
    Ht = align.height_grid(tar, 1.0)
    hits = {}; tot = {}
    for s in strips:
        P = np.array([v[0] for v in s["verts"]])
        h = align.sample_grid(Ht, fit.xz(P[:, [0, 2]]))
        hits[s["tid"]] = hits.get(s["tid"], 0) + np.count_nonzero(~np.isnan(h))
        tot[s["tid"]] = tot.get(s["tid"], 0) + len(P)
    road = {k for k in tot if tot[k] > 30 and hits[k] / tot[k] > 0.5} | set(roadlike)
    Hall = align.height_grid(col_tris, 1.0)
    over = ~np.isnan(align.sample_grid(Hall, fit.xz(T4.mean(1)[:, [0, 2]])))
    ground = {k for k in np.unique(tid4) if flat[tid4 == k].mean() > 0.8 and over[tid4 == k].mean() > 0.6}
    # vertical correction from the MotoGP 4 terrain (road and flat ground textures) over the 08
    # collision: buildings and stands are left out, so large height differences are trusted
    H = align.height_grid(col_tris, 1.0, layers=True)
    terrain = road | ground
    P = np.array([v[0] for s in strips if s["tid"] in terrain for v in s["verts"]], float)
    if len(P) < 1000:
        P = W[near]
    xz = fit.xz(P[:, [0, 2]])
    F, origin, cell = align.correction_field(xz, P[:, 1] / 1000.0 / sc, H, outlier=40.0)
    fit = align.Fit(ang, t, c, F, origin, cell, s=sc, warp=warp)
    log("  height correction: median %.2f m; %d ground textures laid on the collision" % (float(np.median(F)), len(ground)))
    return fit, road | ground, H, share


def _under_line(T, tids, ang, t, c, line, res=0.5):
    """share of the 08 line points (mapped into MotoGP 4 metres) lying on each texture
    (the topmost surface: big ground planes lie under the road)"""
    from PIL import ImageDraw
    q = (line - c) @ align._rot(ang).T + t
    lo = q.min(0) - 20; n = (np.ceil((q.max(0) + 20 - lo) / res)).astype(int)
    img = Image.new("I", (int(n[0]), int(n[1])), -1); dr = ImageDraw.Draw(img)
    order = np.argsort(T[:, :, 1].mean(1))
    for P, k in zip(T[order][:, :, [0, 2]], tids[order]):
        dr.polygon([tuple((p - lo) / res) for p in P], fill=int(k))
    lab = np.array(img); ij = ((q - lo) / res).astype(int)
    hit = lab[ij[:, 1], ij[:, 0]]
    ks, cnt = np.unique(hit[hit >= 0], return_counts=True)
    return {int(k): v / len(q) for k, v in zip(ks, cnt)}


def scene_strips(strips, fit, H, ground=(), tex=None):
    """[(tid, kind, [(pos,uv,rgba), ...])] triangle strips in 08 space; vertices near the
    ground are laid on the 08 collision. Exact duplicates are dropped, and so are blended
    overlays that the 08 alpha test (cut-out at half alpha) would not draw at all."""
    faint = {t for t, im in (tex or {}).items() if (im[..., 3] >= 128).mean() < 0.05}
    out = []
    for s in strips:
        if s["flags"][:1] == (1,) and (s["tid"] in faint or max(v[3][3] for v in s["verts"]) < 64):
            continue                                   # soft blends (rubber, dust, tints): invisible with an alpha test
        vs = s["verts"]
        P = np.array([v[0] for v in vs], float)
        Q = fit.point(P)
        h = align.ground_height(H, Q[:, [0, 2]], Q[:, 1])
        # a terrain strip that touches the ground follows the 08 collision (a roof or canopy with a
        # ground texture, all of it high up, stays where it is); other geometry only where it
        # already touches the ground
        over = ~np.isnan(h); dy = np.abs(Q[:, 1] - np.nan_to_num(h))
        if s["tid"] in ground:
            ok = over if (over & (dy < 8.0)).any() else np.zeros(len(Q), bool)
        else:
            ok = over & (dy < 1.0)
        Q[ok, 1] = h[ok] + 0.02
        kind = "cut" if s["flags"][:1] == (1,) else "solid"
        if kind == "cut":
            Q[ok, 1] += 0.02                           # blended decals (lines, kerb paint) sit on top
        # every maximal run of drawn triangles (k, k+1, k+2 with no ADC on k+2) is one strip;
        # a triangle far bigger than the rest of its strip joins unrelated parts: it is left out
        edge = np.linalg.norm(Q[1:] - Q[:-1], axis=1)
        big = np.zeros(len(vs), bool)
        if len(edge) > 2:
            tri_edge = np.maximum(np.maximum(edge[:-1], edge[1:]), np.linalg.norm(Q[2:] - Q[:-2], axis=1))
            big[2:] = tri_edge > max(30.0, 8 * float(np.median(edge)))
        k = 0; n = len(vs)
        while k < n - 2:
            if vs[k + 2][4] or big[k + 2]:
                k += 1; continue
            e = k
            while e + 1 < n - 2 and not vs[e + 3][4] and not big[e + 3]:
                e += 1
            out.append((s["tid"], kind, [(tuple(Q[j]), vs[j][2], vs[j][3]) for j in range(k, e + 3)]))
            k = e + 1
    keep = []; seen = set()
    for tid, kind, sv in out:
        P = np.array([v[0] for v in sv])
        if np.abs(P[:, [0, 2]]).max() > 2000 or P[:, 1].max() > 150:
            continue                                   # sky dome and far horizon (08 draws its own sky)
        e = np.linalg.norm(P[1:] - P[:-1], axis=1).max()
        if e > 120 and tid not in ground:
            continue                                   # backdrop hills (huge panels drawn behind everything in MotoGP 4)
        key = (tid, tuple(np.round(P, 2).ravel()))
        if key in seen:
            continue                                   # the same strip emitted twice
        seen.add(key); keep.append((tid, kind, sv))
    return keep


def apply_budget(strips, budget, col_xz, H=None, track_xz=None, log=print):
    """keep at most `budget` triangles, by apparent size seen from the track: area / distance^2.
    With the 08 height grid `H` and the tarmac points `track_xz`, the ground lying on the
    collision within 12 m of the tarmac is always kept (gaps there show under the wheels)."""
    ntri = sum(len(sv) - 2 for _, _, sv in strips)
    if ntri <= budget:
        return strips
    grid = {}
    for p in col_xz:
        grid.setdefault((int(p[0] // 20), int(p[1] // 20)), []).append(p)
    def dist(c):
        i, j = int(c[0] // 20), int(c[1] // 20)
        for r in range(0, 60):
            cand = [p for di in range(-r, r + 1) for dj in range(-r, r + 1)
                    if max(abs(di), abs(dj)) == r for p in grid.get((i + di, j + dj), ())]
            if cand:
                return min(np.hypot(*(np.array(cand) - c).T))
        return 1e9
    score = []
    for _, _, sv in strips:
        P = np.array([v[0] for v in sv])
        area = sum(np.linalg.norm(np.cross(P[k + 1] - P[k], P[k + 2] - P[k])) / 2 for k in range(len(P) - 2))
        score.append(area / (dist(P.mean(0)[[0, 2]]) + 10.0) ** 2)
        if H is not None:
            h = align.ground_height(H, P[:, [0, 2]], P[:, 1])
            if (~np.isnan(h)).all() and (np.abs(P[:, 1] - h) < 0.1).all() and \
                    (track_xz is None or track_xz.query(P.mean(0)[[0, 2]])[0] < 12):
                score[-1] = np.inf
    order = np.argsort(score)[::-1]; acc = 0; sel = []
    for k in order:
        n = len(strips[k][2]) - 2
        if acc + n > budget:
            continue
        acc += n; sel.append(k)
    log("  triangle budget %d: kept %d of %d triangles (the smallest/farthest details are dropped)" % (budget, acc, ntri))
    return [strips[k] for k in sorted(sel)]


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def fill_holes(scene, col_tris, col_terrain, H, log=print, res=0.5, half=1400):
    """08 run-off the MotoGP 4 ground does not cover (the layouts differ in places): the
    uncovered parts of the 08 collision, just under the MotoGP 4 ground, drawn with the
    MotoGP 4 texture most often lying on that terrain type"""
    from PIL import ImageDraw
    n = int(2 * half / res)
    def px(P):
        return [((x + half) / res, (z + half) / res) for x, z in P[:, [0, 2]]]
    def cells(Q):
        i = ((Q[:, 0] + half) / res).astype(int); j = ((Q[:, 2] + half) / res).astype(int)
        return i.clip(0, n - 1), j.clip(0, n - 1)
    names = sorted(set(col_terrain)); terr = Image.new("L", (n, n), 255); dt = ImageDraw.Draw(terr)
    for T, t in zip(col_tris, col_terrain):
        dt.polygon(px(T), fill=names.index(t))
    terr = np.array(terr)
    # every scene triangle with the strip it comes from
    tris = []; own = []
    for si, (tid, kind, sv) in enumerate(scene):
        P = np.array([v[0] for v in sv])
        for k in range(len(P) - 2):
            tris.append(P[k:k + 3]); own.append((si, k))
    tris = np.array(tris)
    h = align.ground_height(H, tris.mean(1)[:, [0, 2]], tris[:, :, 1].mean(1))
    dy = tris[:, :, 1].mean(1) - np.nan_to_num(h)
    nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    up = np.abs(nrm[:, 1]) > 0.5 * np.linalg.norm(nrm, axis=1)
    flat = ~np.isnan(h) & up & (dy >= -0.3) & (dy <= 3.0)     # ground hiding the 08 collision
    cover = Image.new("1", (n, n)); dc = ImageDraw.Draw(cover)
    vote = {}; dens = {}; color = {}
    for T, (si, k) in zip(tris[flat], np.array(own)[flat]):
        dc.polygon(px(T), fill=1)
        tid, kind, sv = scene[si]
        a = abs(_cross2(T[1, [0, 2]] - T[0, [0, 2]], T[2, [0, 2]] - T[0, [0, 2]])) / 2
        if kind != "solid" or a < 0.05 or abs(T[:, 1].mean() - align.ground_height(H, T.mean(0)[None, [0, 2]], T[:, 1].mean()[None])[0]) > 0.3:
            continue
        i, j = cells(T.mean(0)[None])
        if terr[j[0], i[0]] < len(names):
            key = (names[terr[j[0], i[0]]], tid); vote[key] = vote.get(key, 0) + a
        U = np.array([sv[k + m][1] for m in range(3)], float)
        dens.setdefault(tid, []).append(np.sqrt(abs(_cross2(U[1] - U[0], U[2] - U[0])) / 2 / a))
        color.setdefault(tid, []).extend(sv[k + m][2] for m in range(3))
    cover = np.array(cover)
    pick = {}
    for (t, tid), a in vote.items():
        if a > pick.get(t, (0, None))[0]:
            pick[t] = (a, tid)
    def covered(T):
        """coverage of sample points about 1.5 m apart over the triangle"""
        m = max(2, int(np.ceil(np.linalg.norm(T - T[[1, 2, 0]], axis=1).max() / 1.5)))
        w = np.array([(a, b, m - a - b) for a in range(m + 1) for b in range(m + 1 - a)], float) / m
        w = (w + 0.05) / 1.15                       # just inside the edges
        i, j = cells(w @ T)
        return cover[j, i]
    out = []; added = {}
    for T, t in zip(col_tris, col_terrain):
        if t not in pick:
            continue
        tid = pick[t][1]; d = float(np.median(dens[tid])); rgba = tuple(int(x) for x in np.median(color[tid], 0))
        S = T.astype(float)
        if covered(S).all():
            continue
        S[:, 1] -= 0.05                                   # the whole triangle, under the MotoGP 4 ground
        if np.cross(S[1] - S[0], S[2] - S[0])[1] < 0:      # face up, the order the strips use
            S = S[[1, 0, 2]]
        out.append((tid, "solid", [(tuple(p), (p[0] * d, p[2] * d), rgba) for p in S]))
        added[t] = added.get(t, 0) + 1
    if added:
        log("  holes filled from the 08 collision (triangles): " + ", ".join("%s %d" % kv for kv in sorted(added.items())))
    return scene + out


def _cells(d, es):
    cells = {}
    for i, e in enumerate(es):
        if e[3] not in (0x103, 0x203):
            continue
        name = objhdr(d, e[1])["name"]
        m = re.search(r"_Sector_(\d+)_(\d+)@", name)
        if m:
            cells.setdefault((int(m.group(1)), int(m.group(2))), []).append(i)
    return cells


def build_scene(slf, strips, road, used_names):
    """new scene SLF bytes: strips distributed over the 08 sector objects"""
    _, es = dirents(slf)
    objs = {}; centres = {}
    cells = _cells(slf, es)
    for k, idx in cells.items():
        pts = []
        for i in idx:
            o = Obj(slf, es[i]); objs[i] = o
            for at in o.atomics():
                G = parse_geometry(at.first(0xF))
                if G.verts:
                    pts.append(np.array(G.verts).mean(0))
        if pts:
            centres[k] = np.mean(pts, 0)
    keys = list(centres); C = np.array([centres[k] for k in keys])[:, [0, 2]]
    # target object per (cell, kind)
    def pick(idx, kind):
        def name(i): return objs[i].name
        if kind == "road":
            r = [i for i in idx if "(TRACK)" in name(i)]
            if r: return r[0]
        if kind == "cut":
            r = [i for i in idx if es[i][3] == 0x203]
            if r: return r[0]
        r = [i for i in idx if es[i][3] == 0x103 and "(TRACK)" not in name(i)]
        return (r or idx)[0]
    buckets = {}
    cent = np.array([np.mean([v[0] for v in sv], 0) for _, _, sv in strips])[:, [0, 2]]
    near = np.argmin(((cent[:, None, :] - C[None]) ** 2).sum(-1), 1)
    for (tid, kind, sv), ci in zip(strips, near):
        if kind == "solid" and tid in road:
            kind = "road"
        buckets.setdefault(pick(cells[keys[ci]], kind), []).append((tid, kind == "cut", sv))
    out = {}
    for i, e in enumerate(es):
        if e[3] not in (0x103, 0x203):
            continue
        try:
            o = objs.get(i) or Obj(slf, e)
        except AssertionError:
            continue                                   # instance of a shared prop: kept as is
        if KEEP_OBJECTS.match(o.name) and i not in buckets:
            for at in o.atomics():
                used_names.update(n.upper() for n in material_texnames(at.first(0xF).first(8)) if n)
            continue
        for k, at in enumerate(o.atomics()):
            g = at.first(0xF)
            if k == 0 and i in buckets:
                ng = _geometry(g, buckets[i], used_names)
            else:
                ng = empty_geometry(g)
                for m in ng.first(8).find(7):
                    tx = m.first(6)
                    if tx is not None:
                        tx.find(2)[0].data = string_chunk(FALLBACK).data
                used_names.add(FALLBACK)
            at.children[at.children.index(g)] = ng
            _no_matfx(at)
        out[i] = o
    return rebuild_slf(slf, out)


def _no_matfx(atomic):
    """the 08 road objects are lightmapped: a MatFX dual pass on a second uv set, which the new
    geometry does not have (the game then samples nonsense, the road came out flat light blue).
    Drop the MatFX pipeline from the atomic and the effect from its materials."""
    ext = atomic.first(3)
    if ext is not None:
        ext.children = [c for c in ext.children if c.type not in (0x1F, 0x120)]
    for m in atomic.first(0xF).first(8).find(7):
        me = m.first(3)
        if me is not None:
            me.children = [c for c in me.children if c.type != 0x120]


def _geometry(tmpl, strips, used_names):
    mats0 = tmpl.first(8).children[1:]
    names = sorted({texname(t, dc) for t, dc, _ in strips})
    mi = {n: k for k, n in enumerate(names)}
    mats = [make_material(mats0[0], n) for n in names]
    used_names.update(names)
    S = [(mi[texname(t, dc)], [((p[0], p[1], p[2]), (0.0, 1.0, 0.0), uv,
                                 (min(255, c[0] * 2), min(255, c[1] * 2), min(255, c[2] * 2),
                                  min(255, c[3] * 2) if dc and len(c) > 3 else 255)) for p, uv, c in v])
         for t, dc, v in strips]
    g, _, _ = build_geometry_strips(tmpl, S, mats, flags=0x0001000E)
    return g


def build_txd(txd, tex, used_names, glow_names):
    """keep the 08 textures still referenced, add MotoGP 4 ones"""
    td = read(txd)[0]
    tmpl = {}
    keep = []
    for tn in td.find(0x15):
        name = tn.children[1].data.split(b"\0")[0].decode().upper()
        info = ps2tex.template_info(tn); w, h, dep, fmt = struct.unpack_from("<4I", info)
        if dep == 8 and fmt == 0x22504:
            tmpl.setdefault("8888", tn)
        if dep == 8 and fmt == 0x22104:
            tmpl.setdefault("1555", tn)
        if name in used_names or name in glow_names:
            keep.append(tn)
    if "8888" not in tmpl:
        raise ValueError("no 8-bit 8888 texture to use as template")
    new = []; cut = set()
    for name in sorted(n for n in used_names if n.startswith("M4_")):
        if name == FALLBACK:
            rgba = np.full((16, 16, 4), (150, 150, 150, 255), np.uint8)
        else:
            rgba = tex.get(int(name[3:7]))
            if rgba is None:
                rgba = np.full((16, 16, 4), (150, 150, 150, 255), np.uint8)
        h, w = rgba.shape[:2]
        if w < 16 or h < 16:
            rgba = np.array(Image.fromarray(rgba, "RGBA").resize((max(w, 16), max(h, 16)), Image.NEAREST))
        a = rgba[..., 3]
        # MotoGP 4 alpha is only transparency on blended decals; elsewhere the texture is opaque
        is_cut = name.endswith("D") and (a < 128).mean() > 0.002
        q = Image.fromarray(rgba[..., :3]).quantize(255 if is_cut else 256, method=Image.MEDIANCUT, dither=Image.NONE)
        idx = np.array(q).astype(np.uint8)
        pal = np.zeros((256, 4), np.uint8)
        p = q.getpalette()[: 3 * 256]; p += [0] * (768 - len(p))
        pal[:, :3] = np.array(p).reshape(256, 3); pal[:, 3] = 255
        if is_cut:
            idx[a < 128] = 255; pal[255] = (0, 0, 0, 0)
        if name.endswith("D"):
            cut.add(name)        # alpha-tested: the vertex alpha of blended strips cuts them too
        new.append(ps2tex.make_raster(tmpl["8888"], name, idx, pal))
    td.children = [c for c in td.children if c.type != 0x15 and c.type != 0x03] + keep + new + \
                  [c for c in td.children if c.type == 0x03]
    st = bytearray(td.first(1).data); struct.pack_into("<H", st, 0, len(keep) + len(new)); td.first(1).data = bytes(st)
    return write([td]), cut


def build_txs(txs, used_names, cut):
    text = txs.decode("latin1").rstrip("\r\n")
    nl = "\r\n" if "\r\n" in text else "\n"
    lines = ["%-36s%s" % (n, ("KT5A128" if n in cut else "") + "Zc") for n in sorted(used_names) if n.startswith("M4_")]
    return (text + nl + nl.join(lines) + nl).encode("latin1")
