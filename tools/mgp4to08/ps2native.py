"""Pre-instance RenderWare geometry for the PS2 the way MotoGP 08's tools do (native geometry).

The game loads bike models from the precompiled .SLI, whose geometry is native: each mesh is a
DMA program of VIF UNPACKs for the VU1 renderer. Instancing a bike's plain (.SLF) geometry at run
time hangs the game, so a converted bike must ship native geometry. Layout, per mesh (one material):
  DMA ret tag, FLUSH, FLUSH
  per batch of up to 52 strip vertices (consecutive batches share 2 vertices):
    NOP STMOD STCYCL(1,3) UNPACK V4-32 positions -> addr 0 (w = 0x8000 when the vertex must not
                                                            close a triangle: ADC)
    NOP STMOD STCYCL(1,3) UNPACK V2-32 uv        -> addr 1
    NOP STMOD STCYCL(1,3) UNPACK V3-8  normals   -> addr 2 (signed bytes)
    NOPs to the next qword, ITOP n, MSCALF 0 (first batch) / MSCNT, then NOP NOP or FLUSH FLUSH
"""
import struct
from .rw import Chunk, read

BATCH = 52
NATIVE = 0x01000000


def plain_arrays(geom):
    """(flags, tris, verts, uv, positions, normals, sphere) of a plain geometry chunk"""
    st = geom.first(1).data
    flags, nt, nv, nm = struct.unpack_from('<4I', st)
    o = 16
    if flags & 0x08: o += 4 * nv
    ntex = (flags >> 16) & 0xff or (2 if flags & 0x80 else 1 if flags & 0x04 else 0)
    uv = [struct.unpack_from('<2f', st, o + 8 * k) for k in range(nv)] if ntex else None
    o += 8 * nv * ntex + 8 * nt
    sphere = st[o:o + 16]; hp, hn = struct.unpack_from('<2I', st, o + 16); o += 24
    pos = [struct.unpack_from('<3f', st, o + 12 * k) for k in range(nv)]; o += 12 * nv
    nrm = [struct.unpack_from('<3f', st, o + 12 * k) for k in range(nv)] if hn else None
    return flags, nt, nv, uv, pos, nrm, sphere


def binmesh(geom):
    d = geom.first(3).first(0x50e).data
    fl, nm, tot = struct.unpack_from('<3I', d); o = 12; out = []
    for _ in range(nm):
        n, mat = struct.unpack_from('<2I', d, o); o += 8
        out.append((mat, list(struct.unpack_from('<%dI' % n, d, o)))); o += 4 * n
    return fl, out


def strip_with_adc(idx):
    """[(index, adc)] of a RenderWare tristrip: every vertex is kept (so the winding parity of the
    strip is kept), and the ones closing a degenerate triangle are flagged"""
    out = [[i, False] for i in idx]
    for k in range(2, len(out)):
        a, b, c = idx[k - 2], idx[k - 1], idx[k]
        if a == b or b == c or a == c: out[k][1] = True
    return out


def _front(pos, nrm, a, b, c):
    """True if (a, b, c) faces the side its vertex normals point to"""
    pa, pb, pc = pos[a], pos[b], pos[c]
    u = [pb[i] - pa[i] for i in range(3)]; v = [pc[i] - pa[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    s = [nrm[a][i] + nrm[b][i] + nrm[c][i] for i in range(3)]
    return n[0] * s[0] + n[1] * s[1] + n[2] * s[2] >= 0


def strip_from_triangles(tris, pos, nrm):
    """[(index, adc)] drawing the triangles `tris` [(a, b, c)]: greedy strips joined with ADC
    vertices. The triangle closed at an even position faces front in (k-2, k-1, k) order, at an odd
    position in reverse order, as in the game's own models."""
    tris = [t if _front(pos, nrm, *t) else (t[0], t[2], t[1]) for t in tris]   # front-facing order
    by_edge = {}
    for n, (a, b, c) in enumerate(tris):
        for e in ((a, b), (b, c), (c, a)):
            by_edge.setdefault(e, []).append(n)
    used = [False] * len(tris)
    out = []
    for start in range(len(tris)):
        if used[start]: continue
        a, b, c = tris[start]
        k = len(out) + 2                      # position of the vertex that closes the first triangle
        seq = [a, b, c] if k % 2 == 0 else [a, c, b]
        used[start] = True
        while True:
            x, y = seq[-2], seq[-1]
            k = len(out) + len(seq)           # position the next vertex would take
            # the next triangle must be front-facing as (x, y, z) at even k and as (y, x, z) at odd k,
            # i.e. contain the directed edge x->y (even) or y->x (odd)
            edge = (x, y) if k % 2 == 0 else (y, x)
            nxt = None
            for n in by_edge.get(edge, ()):
                if not used[n]:
                    nxt = n; break
            if nxt is None: break
            t = tris[nxt]
            z = [v for v in t if v not in edge]
            if len(z) != 1: used[nxt] = True; continue
            used[nxt] = True; seq.append(z[0])
        # the first two vertices of a strip would close triangles joining it to the previous one
        out.extend([v, j < 2] for j, v in enumerate(seq))
    return out


def _nb(x):
    return max(-127, min(127, int(round(x * 127.0)))) & 0xff


def mesh_program(strip, uv, pos, nrm):
    """DMA program bytes of one mesh from the cleaned strip [(index, adc)]"""
    w = bytearray()
    def word(v): w.extend(struct.pack('<I', v))
    def pad_qw():
        while len(w) % 16: word(0)
    batches = []
    k = 0
    while True:
        batches.append(strip[k:k + BATCH])
        if k + BATCH >= len(strip): break
        k += BATCH - 2
    w.extend(b'\0' * 8); word(0x11000000); word(0x11000000)            # tag filled below
    for bi, b in enumerate(batches):
        n = len(b)
        for j, (vn, vl, addr) in enumerate(((3, 0, 0), (1, 0, 1), (2, 2, 2))):
            word(0); word(0x05000000); word(0x01000103)
            word(((0x60 | vn << 2 | vl) << 24) | (n << 16) | 0x8000 | addr)
            for jj, (i, adc) in enumerate(b):
                if j == 0:
                    w.extend(struct.pack('<3fI', *pos[i], 0x8000 if (adc and jj >= 2) else 0))
                elif j == 1:
                    w.extend(struct.pack('<2f', *uv[i]))
                else:
                    w.extend(bytes(_nb(c) for c in nrm[i]))
            while len(w) % 4: w.append(0)
            if j < 2: pad_qw()
        while len(w) % 16 != 0: word(0)
        last = bi == len(batches) - 1
        word(0x04000000 | n); word(0x15000000 if bi == 0 else 0x17000000)
        word(0x11000000 if last else 0); word(0x11000000 if last else 0)
    qwc = len(w) // 16 - 1
    struct.pack_into('<2I', w, 0, 0x60000000 | qwc, 0)
    return bytes(w)


def decode_triangles(prog):
    """set of triangles (as frozensets of rounded positions) a mesh program draws"""
    from collections import Counter
    tris = Counter(); o = 16; m = prog
    qwc = struct.unpack_from('<I', m)[0] & 0xffff; end = 16 + 16 * qwc; p = 8
    while p < end:
        c = struct.unpack_from('<I', m, p)[0]; cmd = (c >> 24) & 0x7f; num = (c >> 16) & 0xff or 256
        if cmd >= 0x60:
            vn, vl = (cmd >> 2) & 3, cmd & 3
            size = 2 * num if vl == 3 else ((vn + 1) * (32 >> vl) // 8) * num
            if (vn, vl) == (3, 0):
                vs = [struct.unpack_from('<3fI', m, p + 4 + 16 * k) for k in range(num)]
                for k in range(2, num):
                    if vs[k][3] & 0x8000: continue
                    t = frozenset(tuple(round(x, 4) for x in vs[j][:3]) for j in (k - 2, k - 1, k))
                    if len(t) == 3: tris[t] += 1
            p += 4 + ((size + 3) & ~3)
        else:
            p += 4
    return tris


def to_native(geom):
    """native copy of a plain geometry chunk (materials and user data kept)"""
    flags, nt, nv, uv, pos, nrm, sphere = plain_arrays(geom)
    if flags & NATIVE:
        return geom
    if uv is None: uv = [(0.0, 0.0)] * nv
    if nrm is None: nrm = [(0.0, 0.0, 0.0)] * nv
    strip_mesh, meshes = binmesh(geom)
    progs = []
    bm = bytearray()
    for mat, idx in meshes:
        if strip_mesh & 1:
            strip = strip_with_adc(idx)
        else:
            strip = strip_from_triangles([tuple(idx[q:q + 3]) for q in range(0, len(idx) - 2, 3)], pos, nrm)
        if len(strip) < 3:
            continue
        progs.append(mesh_program(strip, uv, pos, nrm))
        bm += struct.pack('<2I', len(strip), mat)
    nd = bytearray(struct.pack('<I', 4))
    for p in progs:
        nd += struct.pack('<2I', len(p), 1) + p
    ext = [Chunk(0x50e, struct.pack('<3I', 1, len(meshes), sum(struct.unpack_from('<I', bm, 8 * q)[0] for q in range(len(meshes)))) + bytes(bm)),
           Chunk(0x510, struct.pack('<3I', 1, len(nd), 0x1c020037) + bytes(nd))]
    old = geom.first(3)
    ext += [c for c in (old.children if old else []) if c.type not in (0x50e, 0x510, 0x134)]
    ext.append(Chunk(0x134, struct.pack('<I', 0)))
    # the bike renderer takes positions, uv and normals (lit, no vertex colours)
    flags = (flags & ~0x08) | 0x01 | 0x20 | NATIVE
    st = struct.pack('<4I', flags, nt, nv, 1) + sphere + struct.pack('<2I', 0, 0)
    return Chunk(0xF, b'', [Chunk(1, st, None, geom.ver), geom.first(8)] + [Chunk(3, b'', ext, geom.ver)], geom.ver)


def template_materials(slf, sli):
    """{object short name: [native material chunks]} of a bike as the game ships it: its plain .SLF
    paired with the native geometry of its .SLI (paired by vertex and triangle counts, in order)"""
    from .slf import dirents
    from .build08 import Obj
    natives = {}
    for i in range(len(sli) - 24):
        t, sz, v = struct.unpack_from('<3I', sli, i)
        if t == 0xF and v == 0x1c020037 and struct.unpack_from('<I', sli, i + 12)[0] == 1:
            fl, nt, nv, nm = struct.unpack_from('<4I', sli, i + 24)
            if fl & NATIVE:
                natives.setdefault((nv, nt), []).append(read(sli, i, i + 12 + sz)[0])
    out = {}
    _, es = dirents(slf)
    for e in es:
        if e[3] not in (0x303, 0x403): continue
        for at in Obj(slf, e).atomics():
            fl, nt, nv, _ = struct.unpack_from('<4I', at.first(0xF).first(1).data)
            cand = natives.get((nv, nt))
            if cand:
                out.setdefault(e[0].split('@')[0], []).extend(cand.pop(0).first(8).find(7))
    return out


def _effect(m):
    ext = m.first(3)
    c = ext.first(0xfffe) if ext is not None else None
    return c.data if c is not None else None


def native_material(plain, templates, obj):
    """the material as the native bike pipeline wants it (pipeline rights 0x1f, MatFX environment map
    without the run-time cube texture, sky mipmap K on the textures...): a copy of the game's native
    material of the same object and effect, with the texture name and colour of `plain`"""
    import copy
    same = templates.get(obj, [])
    every = [m for ms in templates.values() for m in ms if m.first(6) is not None]
    eff = _effect(plain)
    pick = (next((m for m in same if _effect(m) == eff and m.first(6) is not None), None)
            or next((m for m in same if m.first(6) is not None), None)
            or next((m for m in every if _effect(m) == eff), None)
            or every[0])
    m = copy.deepcopy(pick)
    st = bytearray(m.first(1).data); st[4:8] = plain.first(1).data[4:8]; m.first(1).data = bytes(st)
    tp, tm = plain.first(6), m.first(6)
    if tp is not None and tm is not None:
        name = tp.find(2)[0].data.split(b'\0')[0].decode('latin1').upper().encode('latin1') + b'\0'
        name += b'\0' * (-len(name) % 4)
        tm.find(2)[0].data = name
    if eff is not None and m.first(3) is not None and m.first(3).first(0xfffe) is not None:
        m.first(3).first(0xfffe).data = eff
    return m


def nativize_slf(d, templates=None):
    """an SLF whose every drawn model geometry is native (see the module notes); `templates` from
    template_materials() of the bike the model was made from converts the materials as well"""
    from .slf import dirents
    from .build08 import Obj, rebuild_slf
    _, es = dirents(d)
    objs = {e[0]: Obj(d, e) for e in es if e[3] in (0x303, 0x403)}
    for name, o in objs.items():
        for at in o.atomics():
            g = at.first(0xF)
            if struct.unpack_from('<I', g.first(1).data)[0] & 0x04:    # drawn (textured): not the collision shape
                ng = to_native(g)
                if templates:
                    ml = ng.first(8)
                    ml.children = [ml.children[0]] + [native_material(m, templates, name.split('@')[0]) for m in ml.find(7)]
                at.children[at.children.index(g)] = ng
    return rebuild_slf(d, objs)


def check(prog, pos, nrm, expect=None):
    """(drawn triangles, back-facing ones, missing ones) of a mesh program; expect: triangles as index triples"""
    from collections import Counter
    m = prog; qwc = struct.unpack_from('<I', m)[0] & 0xffff; end = 16 + 16 * qwc; p = 8
    drawn = Counter(); back = 0
    key = lambda p3: tuple(round(x, 4) for x in p3)
    vkey = {}
    for i, q in enumerate(pos): vkey.setdefault(key(q), i)
    P = None
    while p < end:
        c = struct.unpack_from('<I', m, p)[0]; cmd = (c >> 24) & 0x7f; num = (c >> 16) & 0xff or 256
        if cmd >= 0x60:
            vn, vl = (cmd >> 2) & 3, cmd & 3
            size = 2 * num if vl == 3 else ((vn + 1) * (32 >> vl) // 8) * num
            if (vn, vl) == (3, 0):
                P = [struct.unpack_from('<3fI', m, p + 4 + 16 * k) for k in range(num)]
                for k in range(2, num):
                    if P[k][3] & 0x8000: continue
                    ids = [vkey[key(P[j][:3])] for j in (k - 2, k - 1, k)]
                    if len(set(ids)) < 3: continue
                    a, b, cc = ids if k % 2 == 0 else (ids[1], ids[0], ids[2])
                    if not _front(pos, nrm, a, b, cc): back += 1
                    drawn[frozenset(key(pos[i]) for i in ids)] += 1
            p += 4 + ((size + 3) & ~3)
        else:
            p += 4
    missing = None
    if expect is not None:
        want = Counter(frozenset(key(pos[i]) for i in t) for t in expect if len({key(pos[i]) for i in t}) == 3)
        missing = sum((want - drawn).values())
    return sum(drawn.values()), back, missing
