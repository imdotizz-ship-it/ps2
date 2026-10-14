"""Fit a MotoGP 4 track onto the same circuit in MotoGP 08 (numpy only).

The MotoGP 08 collision, AI line, grid and cameras are kept; only the visual
scene comes from MotoGP 4, so its geometry has to be laid exactly over the
08 collision: a rigid 2D fit (rotation + translation, metres) followed by a
smooth vertical correction field.
"""
import re
import numpy as np


def spline_points(spl_text, name="AIGuidanceSpline", per_seg=20):
    """dense points (N,3) of a CurveGraph spline in a .SPL file (Hermite with the stored tangents)"""
    i = spl_text.find('Name "%s"' % name)
    block = spl_text[i:spl_text.find("CurveGraph\n", i + 10) if spl_text.find("CurveGraph\n", i + 10) > 0 else None]
    P = np.array([[float(x) for x in m.groups()] for m in re.finditer(r"Point (\S+) (\S+) (\S+)", block)])
    T = np.array([[float(x) for x in m.groups()] for m in re.finditer(r"Tangent (\S+) (\S+) (\S+)", block)])
    out = []
    for k in range(len(P)):
        j = (k + 1) % len(P)
        for t in np.linspace(0, 1, per_seg, endpoint=False):
            h00 = 2 * t**3 - 3 * t**2 + 1; h10 = t**3 - 2 * t**2 + t; h01 = -2 * t**3 + 3 * t**2; h11 = t**3 - t**2
            out.append(h00 * P[k] + h10 * T[k] + h01 * P[j] + h11 * T[j])
    return np.array(out)


def distance_field(xz, res=1.0, half=1024, cap=30):
    """approximate distance (in cells) to the nearest point, on a (2*half/res)^2 grid centred on 0"""
    n = int(2 * half / res)
    D = np.full((n, n), float(cap))
    ix = ((xz[:, 0] + half) / res).astype(int); iz = ((xz[:, 1] + half) / res).astype(int)
    ok = (ix >= 0) & (iz >= 0) & (ix < n) & (iz < n)
    D[iz[ok], ix[ok]] = 0
    for _ in range(cap):              # chamfer 3x3 passes
        E = D.copy()
        E[1:, :] = np.minimum(E[1:, :], D[:-1, :] + 1); E[:-1, :] = np.minimum(E[:-1, :], D[1:, :] + 1)
        E[:, 1:] = np.minimum(E[:, 1:], D[:, :-1] + 1); E[:, :-1] = np.minimum(E[:, :-1], D[:, 1:] + 1)
        E[1:, 1:] = np.minimum(E[1:, 1:], D[:-1, :-1] + 1.414); E[:-1, :-1] = np.minimum(E[:-1, :-1], D[1:, 1:] + 1.414)
        E[1:, :-1] = np.minimum(E[1:, :-1], D[:-1, 1:] + 1.414); E[:-1, 1:] = np.minimum(E[:-1, 1:], D[1:, :-1] + 1.414)
        if (E == D).all():
            break
        D = E
    return D


def _rot(deg):
    a = np.radians(deg)
    return np.array([[np.cos(a), -np.sin(a)], [np.sin(a), np.cos(a)]])


def coarse(m4_xz, line_xz, step=2.0, res=2.0, half=2048, top=1):
    """best rotation (deg) / translation mapping 08 points onto MotoGP 4 points: q = R (p - c) + t;
    with top > 1, a list of the best (ang, t, c, score) at least 20 degrees apart"""
    N = int(2 * half / res)
    m = np.median(m4_xz, 0)                      # the field is centred on the MotoGP 4 track
    D = distance_field(m4_xz - m, res, half)
    F = np.fft.rfft2(D)
    c = line_xz.mean(0); best = None; cands = []
    for ang in np.arange(0, 360, step):
        Q = (line_xz - c) @ _rot(ang).T
        img = np.zeros((N, N)); q = np.round(Q / res).astype(int)
        np.add.at(img, (q[:, 1] % N, q[:, 0] % N), 1)
        corr = np.fft.irfft2(F * np.conj(np.fft.rfft2(img)), s=(N, N)) / len(Q)
        k = np.argmin(corr); tz, tx = np.unravel_index(k, corr.shape)
        # a point q lands on field cell q + index, i.e. MotoGP 4 coordinate (q + index) * res - half + m
        cand = (corr.flat[k] * res, ang, np.array([tx * res - half, tz * res - half], float) + m)
        cands.append(cand)
        if best is None or cand[0] < best[0]:
            best = cand
    if top > 1:
        out = []
        for sc, ang, t in sorted(cands, key=lambda x: x[0]):
            if all(abs((ang - o[0] + 180) % 360 - 180) >= 20 for o in out):
                out.append((ang, t, c, sc))
            if len(out) == top:
                break
        return out
    score, ang, t = best
    return ang, t, c, score


def refine(mask_fn, samples, ang, t, c, span_deg=1.0, span_m=4.0, s=1.0):
    """maximise the share of 08 sample points (N,2) falling inside the MotoGP 4 mask"""
    best = (-1, ang, t)
    for da in np.linspace(-span_deg, span_deg, 21):
        R = _rot(ang + da)
        base = s * (samples - c) @ R.T
        for dx in np.arange(-span_m, span_m + 1e-6, 0.5):
            for dz in np.arange(-span_m, span_m + 1e-6, 0.5):
                tt = t + (dx, dz)
                s = mask_fn(base + tt).mean()
                if s > best[0]:
                    best = (s, ang + da, tt)
    return best


def icp(src, dst, ang, t, c, s=1.0, iters=40, start=15.0, end=2.0, smin=0.95, smax=1.05):
    """similarity fit q = s R (p - c) + t of 08 points src (N,2) onto MotoGP 4 points dst (M,2),
    both in metres (iterative closest points, Umeyama step, shrinking outlier threshold; the
    scale stays within smin..smax: both games model real circuits);
    returns ang, t, s and the share of 08 points within `end` metres at the end"""
    from scipy.spatial import cKDTree
    tree = cKDTree(dst)
    for k in range(iters):
        thr = start * (end / start) ** (k / (iters - 1))
        Q = s * (src - c) @ _rot(ang).T + t
        d, j = tree.query(Q)
        m = d < thr
        if m.sum() < 50:
            break
        P = src[m] - c; D = dst[j[m]]
        mp = P.mean(0); md = D.mean(0); P0 = P - mp; D0 = D - md
        U, S, Vt = np.linalg.svd(D0.T @ P0 / len(P))
        E = np.diag([1.0, np.sign(np.linalg.det(U) * np.linalg.det(Vt))])
        R = U @ E @ Vt
        s = float(np.clip(np.trace(np.diag(S) @ E) / (P0 ** 2).sum(1).mean(), smin, smax))
        t = md - s * R @ mp
        ang = float(np.degrees(np.arctan2(R[1, 0], R[0, 0])))
    d, _ = tree.query(s * (src - c) @ _rot(ang).T + t)
    return ang, t, s, float((d < end).mean())


def area_samples(tris, per_m2=0.5, rng=None):
    """random points (N,2) over the x,z footprint of triangles (K,3,2), about `per_m2` per square metre"""
    rng = rng or np.random.default_rng(0)
    a = np.abs(np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])) / 2 if tris.shape[-1] == 3 else \
        np.abs((tris[:, 1, 0] - tris[:, 0, 0]) * (tris[:, 2, 1] - tris[:, 0, 1])
               - (tris[:, 2, 0] - tris[:, 0, 0]) * (tris[:, 1, 1] - tris[:, 0, 1])) / 2
    n = rng.poisson(a * per_m2)
    T = np.repeat(tris, n, 0)
    w = rng.random((len(T), 2)); f = w.sum(1) > 1; w[f] = 1 - w[f]
    return T[:, 0] + w[:, :1] * (T[:, 1] - T[:, 0]) + w[:, 1:] * (T[:, 2] - T[:, 0])


def _bilinear(F, origin, cell, xz):
    g = (xz - origin) / cell
    n = F.shape[0]
    gx = np.clip(g[:, 0], 0, n - 1.001); gz = np.clip(g[:, 1], 0, n - 1.001)
    x0 = gx.astype(int); z0 = gz.astype(int); fx = gx - x0; fz = gz - z0
    if F.ndim == 3:
        fx = fx[:, None]; fz = fz[:, None]
    return (F[z0, x0] * (1 - fx) * (1 - fz) + F[z0, x0 + 1] * fx * (1 - fz)
            + F[z0 + 1, x0] * (1 - fx) * fz + F[z0 + 1, x0 + 1] * fx * fz)


def _smooth_fill(S, C, iters, default=0.0):
    """average of the samples per cell, filled and smoothed outwards (measured cells kept closer)"""
    known = C > 0
    F = np.where(known[..., None] if S.ndim == 3 else known, S / np.maximum(C, 1)[..., None] if S.ndim == 3
                 else S / np.maximum(C, 1), default)
    K = known[..., None] if S.ndim == 3 else known
    for _ in range(iters):
        A = F.copy()
        A[1:-1, 1:-1] = (F[:-2, 1:-1] + F[2:, 1:-1] + F[1:-1, :-2] + F[1:-1, 2:] + F[1:-1, 1:-1]) / 5
        F = np.where(K, 0.5 * F + 0.5 * A, A)
    return F


class Fit:
    """MotoGP 4 (mm) -> MotoGP 08 (m) transform: rotation, scale and translation, then a smooth
    horizontal warp (MotoGP 4 circuits are not exact replicas) and a vertical correction field"""

    def __init__(self, ang, t, c, field=None, origin=None, cell=8.0, s=1.0, warp=None):
        self.R = _rot(ang); self.t = np.asarray(t, float); self.c = np.asarray(c, float); self.s = s
        self.field = field; self.origin = origin; self.cell = cell
        self.warp = warp                     # (field (n,n,2), origin, cell) over the rigid result

    def rigid(self, p4):
        return (np.asarray(p4, float) / 1000.0 - self.t) @ self.R / self.s + self.c

    def xz(self, p4):
        """MotoGP 4 x,z in millimetres -> MotoGP 08 x,z in metres"""
        r = self.rigid(p4)
        if self.warp is not None:
            r = r + _bilinear(*self.warp, r)
        return r

    def dy(self, xz08):
        if self.field is None:
            return np.zeros(len(xz08))
        return _bilinear(self.field, self.origin, self.cell, xz08)

    def point(self, p4):
        p4 = np.atleast_2d(np.asarray(p4, float))
        xz = self.xz(p4[:, [0, 2]])
        y = p4[:, 1] / 1000.0 / self.s + self.dy(xz)
        return np.stack([xz[:, 0], y, xz[:, 1]], 1)


def warp_field(fit, road4_mm, tar08, iters=8, start=12.0, end=2.5, cell=16.0, half=1500, log=None):
    """smooth horizontal displacement that lays the MotoGP 4 road samples (mm) on the 08 tarmac
    samples (m): matches both ways between the two surfaces, averaged per cell and smoothed"""
    from scipy.spatial import cKDTree
    n = int(2 * half / cell); origin = np.array([-half, -half], float)
    D = np.zeros((n, n, 2))
    rig = fit.rigid(road4_mm)
    t08 = cKDTree(tar08)
    for k in range(iters):
        thr = start * (end / start) ** (k / max(iters - 1, 1))
        r = rig + _bilinear(D, origin, cell, rig)
        d1, j1 = t08.query(r); m1 = d1 < thr
        d2, j2 = cKDTree(r).query(tar08); m2 = d2 < thr
        pos = np.concatenate([rig[m1], rig[j2[m2]]])
        dd = np.concatenate([tar08[j1[m1]] - r[m1], tar08[m2] - r[j2[m2]]])
        g = ((pos - origin) / cell).astype(int).clip(0, n - 1)
        S = np.zeros((n, n, 2)); C = np.zeros((n, n))
        np.add.at(S, (g[:, 1], g[:, 0]), dd); np.add.at(C, (g[:, 1], g[:, 0]), 1)
        D += 0.8 * _smooth_fill(S, C, 30)
        if log:
            log("    warp %d: threshold %.1f m, %d matches, mean move %.2f m" % (k, thr, len(dd), np.linalg.norm(dd, axis=1).mean()))
    return D, origin, cell


def height_grid(col_tris, res=1.0, half=1400, layers=False):
    """max collision height per cell (NaN where no collision); with `layers`, the (2, n, n) stack
    of the highest and the lowest collision per cell (bridges: the road under and over)"""
    n = int(2 * half / res)
    H = np.full((n, n), np.nan); L = np.full((n, n), np.nan)
    for T in col_tris:
        x = (T[:, 0] + half) / res; z = (T[:, 2] + half) / res
        x0, x1 = int(np.floor(x.min())), int(np.ceil(x.max())); z0, z1 = int(np.floor(z.min())), int(np.ceil(z.max()))
        if x1 < 0 or z1 < 0 or x0 >= n or z0 >= n:
            continue
        gx, gz = np.meshgrid(np.arange(max(x0, 0), min(x1, n - 1) + 1) + 0.5, np.arange(max(z0, 0), min(z1, n - 1) + 1) + 0.5)
        d = (z[1] - z[2]) * (x[0] - x[2]) + (x[2] - x[1]) * (z[0] - z[2])
        if abs(d) < 1e-9:
            continue
        l0 = ((z[1] - z[2]) * (gx - x[2]) + (x[2] - x[1]) * (gz - z[2])) / d
        l1 = ((z[2] - z[0]) * (gx - x[2]) + (x[0] - x[2]) * (gz - z[2])) / d
        l2 = 1 - l0 - l1
        m = (l0 >= -1e-3) & (l1 >= -1e-3) & (l2 >= -1e-3)
        if not m.any():
            continue
        y = l0 * T[0, 1] + l1 * T[1, 1] + l2 * T[2, 1]
        win = (slice(max(z0, 0), min(z1, n - 1) + 1), slice(max(x0, 0), min(x1, n - 1) + 1))
        sub = H[win]; cur = np.where(np.isnan(sub), -1e9, sub)
        sub[m] = np.maximum(cur[m], y[m])
        sub = L[win]; cur = np.where(np.isnan(sub), 1e9, sub)
        sub[m] = np.minimum(cur[m], y[m])
    return np.stack([H, L]) if layers else H


def ground_height(H2, xz, y):
    """the collision height (highest or lowest layer of `height_grid(.., layers=True)`) closest
    to the heights `y` (NaN where no collision)"""
    hi = sample_grid(H2[0], xz); lo = sample_grid(H2[1], xz)
    return np.where(np.abs(hi - y) <= np.abs(lo - y), hi, lo)


def sample_grid(H, xz, res=1.0, half=1400):
    i = ((xz[:, 0] + half) / res).astype(int); j = ((xz[:, 1] + half) / res).astype(int)
    ok = (i >= 0) & (j >= 0) & (i < H.shape[1]) & (j < H.shape[0])
    out = np.full(len(xz), np.nan)
    out[ok] = H[j[ok], i[ok]]
    return out


def correction_field(xz08, y08_raw, H, cell=8.0, half=1500, iters=200):
    """smooth dy(x,z) = collision height - MotoGP 4 height, from vertices lying over the collision
    (H from height_grid(.., layers=True): under a bridge, the layer closest to the vertex)"""
    hi = sample_grid(H[0], xz08); lo = sample_grid(H[1], xz08)
    single = np.abs(hi - lo) < 0.5
    med = np.nanmedian((hi - y08_raw)[single]) if single.any() else np.nanmedian(hi - y08_raw)
    h = ground_height(H, xz08, y08_raw + med)
    ok = ~np.isnan(h)
    d = h[ok] - y08_raw[ok]
    med = np.median(d)
    keep = np.abs(d - med) < 12
    n = int(2 * half / cell); origin = np.array([-half, -half], float)
    S = np.zeros((n, n)); C = np.zeros((n, n))
    g = ((xz08[ok][keep] - origin) / cell).astype(int)
    np.add.at(S, (g[:, 1], g[:, 0]), d[keep]); np.add.at(C, (g[:, 1], g[:, 0]), 1)
    return _smooth_fill(S, C, iters, med), origin, cell
