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


def coarse(m4_xz, line_xz, step=2.0, res=2.0, half=2048):
    """best rotation (deg) / translation mapping 08 points onto MotoGP 4 points: q = R (p - c) + t"""
    N = int(2 * half / res)
    m = np.median(m4_xz, 0)                      # the field is centred on the MotoGP 4 track
    D = distance_field(m4_xz - m, res, half)
    F = np.fft.rfft2(D)
    c = line_xz.mean(0); best = None
    for ang in np.arange(0, 360, step):
        Q = (line_xz - c) @ _rot(ang).T
        img = np.zeros((N, N)); q = np.round(Q / res).astype(int)
        np.add.at(img, (q[:, 1] % N, q[:, 0] % N), 1)
        corr = np.fft.irfft2(F * np.conj(np.fft.rfft2(img)), s=(N, N)) / len(Q)
        k = np.argmin(corr); tz, tx = np.unravel_index(k, corr.shape)
        # a point q lands on field cell q + index, i.e. MotoGP 4 coordinate (q + index) * res - half + m
        cand = (corr.flat[k] * res, ang, np.array([tx * res - half, tz * res - half], float) + m)
        if best is None or cand[0] < best[0]:
            best = cand
    score, ang, t = best
    return ang, t, c, score


def refine(mask_fn, samples, ang, t, c, span_deg=1.0, span_m=4.0):
    """maximise the share of 08 sample points (N,2) falling inside the MotoGP 4 mask"""
    best = (-1, ang, t)
    for da in np.linspace(-span_deg, span_deg, 21):
        R = _rot(ang + da)
        base = (samples - c) @ R.T
        for dx in np.arange(-span_m, span_m + 1e-6, 0.5):
            for dz in np.arange(-span_m, span_m + 1e-6, 0.5):
                tt = t + (dx, dz)
                s = mask_fn(base + tt).mean()
                if s > best[0]:
                    best = (s, ang + da, tt)
    return best


class Fit:
    """MotoGP 4 (mm) -> MotoGP 08 (m) transform with a vertical correction field"""

    def __init__(self, ang, t, c, field=None, origin=None, cell=8.0):
        self.R = _rot(ang); self.t = np.asarray(t, float); self.c = np.asarray(c, float)
        self.field = field; self.origin = origin; self.cell = cell

    def xz(self, p4):
        """MotoGP 4 x,z in millimetres -> MotoGP 08 x,z in metres"""
        return (np.asarray(p4, float) / 1000.0 - self.t) @ self.R + self.c

    def dy(self, xz08):
        if self.field is None:
            return np.zeros(len(xz08))
        g = (xz08 - self.origin) / self.cell
        n = self.field.shape[0]
        gx = np.clip(g[:, 0], 0, n - 1.001); gz = np.clip(g[:, 1], 0, n - 1.001)
        x0 = gx.astype(int); z0 = gz.astype(int); fx = gx - x0; fz = gz - z0
        F = self.field
        return (F[z0, x0] * (1 - fx) * (1 - fz) + F[z0, x0 + 1] * fx * (1 - fz)
                + F[z0 + 1, x0] * (1 - fx) * fz + F[z0 + 1, x0 + 1] * fx * fz)

    def point(self, p4):
        p4 = np.atleast_2d(np.asarray(p4, float))
        xz = self.xz(p4[:, [0, 2]])
        y = p4[:, 1] / 1000.0 + self.dy(xz)
        return np.stack([xz[:, 0], y, xz[:, 1]], 1)


def height_grid(col_tris, res=1.0, half=1400):
    """max collision height per cell (NaN where no collision)"""
    n = int(2 * half / res)
    H = np.full((n, n), np.nan)
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
        sub = H[max(z0, 0):min(z1, n - 1) + 1, max(x0, 0):min(x1, n - 1) + 1]
        cur = np.where(np.isnan(sub), -1e9, sub)
        sub[m] = np.maximum(cur[m], y[m])
    return H


def sample_grid(H, xz, res=1.0, half=1400):
    i = ((xz[:, 0] + half) / res).astype(int); j = ((xz[:, 1] + half) / res).astype(int)
    ok = (i >= 0) & (j >= 0) & (i < H.shape[1]) & (j < H.shape[0])
    out = np.full(len(xz), np.nan)
    out[ok] = H[j[ok], i[ok]]
    return out


def correction_field(xz08, y08_raw, H, cell=8.0, half=1500, iters=200):
    """smooth dy(x,z) = collision height - MotoGP 4 height, from vertices lying over the collision"""
    h = sample_grid(H, xz08)
    ok = ~np.isnan(h)
    d = h[ok] - y08_raw[ok]
    med = np.median(d)
    keep = np.abs(d - med) < 12
    n = int(2 * half / cell); origin = np.array([-half, -half], float)
    S = np.zeros((n, n)); C = np.zeros((n, n))
    g = ((xz08[ok][keep] - origin) / cell).astype(int)
    np.add.at(S, (g[:, 1], g[:, 0]), d[keep]); np.add.at(C, (g[:, 1], g[:, 0]), 1)
    known = C > 0
    F = np.where(known, S / np.maximum(C, 1), med)
    for _ in range(iters):                       # fill and smooth, keeping measured cells
        A = F.copy()
        A[1:-1, 1:-1] = (F[:-2, 1:-1] + F[2:, 1:-1] + F[1:-1, :-2] + F[1:-1, 2:] + F[1:-1, 1:-1]) / 5
        F = np.where(known, 0.5 * F + 0.5 * A, A)
    return F, origin, cell
