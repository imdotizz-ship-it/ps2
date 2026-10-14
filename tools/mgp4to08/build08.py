"""Build MotoGP 08 bike files (SLF + TXD + TXS) with MotoGP 4 bodies."""
import struct,copy,numpy as np
from .rw import read,write,Chunk,string_chunk,VER
from .slf import dirents,objhdr

# ---------------- geometry ----------------
def make_material(template,texname,effect=None,color=None):
    m=copy.deepcopy(template)
    tex=m.first(6)
    strs=tex.find(2)
    strs[0].data=string_chunk(texname).data
    if color is not None:
        st=bytearray(m.first(1).data); st[4:8]=bytes(color); m.first(1).data=bytes(st)
    if effect is not None:
        for c in m.first(3).children:
            if c.type==0xfffe: c.data=struct.pack('<I',effect)
    return m

def build_geometry_strips(tmpl_geom,strips,materials,flags=0x0001000F):
    """strips: list of (matindex, [(pos,nrm,uv,rgba), ...]) triangle strips.
    Writes a tristrip BinMesh (strips of one material joined with degenerate triangles)."""
    vidx={}; verts=[]; T=[]; per={}
    def vid(v):
        key=(tuple(round(x,5) for x in v[0]),tuple(round(x,3) for x in v[1]),tuple(round(x,5) for x in v[2]),v[3])
        if key not in vidx: vidx[key]=len(verts); verts.append(key)
        return vidx[key]
    for mi,sv in strips:
        ids=[vid(v) for v in sv]
        if len(ids)<3: continue
        for k in range(len(ids)-2):
            a,b,c=(ids[k],ids[k+1],ids[k+2]) if k%2==0 else (ids[k+1],ids[k],ids[k+2])
            if len({a,b,c})==3: T.append((mi,(a,b,c)))
        seq=per.setdefault(mi,[])
        if seq:
            seq.append(seq[-1]); seq.append(ids[0])
            if len(seq)%2: seq.append(ids[0])          # keep the winding parity of the next strip
        seq.extend(ids)
    assert len(verts)<65536
    nv=len(verts); nt=len(T); normals=bool(flags&0x10)
    b=bytearray(struct.pack('<4I',flags|1,nt,nv,1))
    for v in verts: b+=bytes(v[3])
    for v in verts: b+=struct.pack('<2f',*v[2])
    for mi,(a,bb,c) in T: b+=struct.pack('<4H',bb,a,mi,c)
    P=np.array([v[0] for v in verts]); ctr=(P.min(0)+P.max(0))/2; rad=float(np.linalg.norm(P-ctr,axis=1).max())
    b+=struct.pack('<4f',*ctr,rad)+struct.pack('<2I',1,int(normals))
    for v in verts: b+=struct.pack('<3f',*v[0])
    if normals:
        for v in verts: b+=struct.pack('<3f',*v[1])
    g=copy.deepcopy(tmpl_geom)
    g.first(1).data=bytes(b)
    ml=g.first(8)
    ml.children=[Chunk(1,struct.pack('<I',len(materials))+struct.pack('<i',-1)*len(materials))]+materials
    bm=struct.pack('<3I',1,len(per),sum(len(x) for x in per.values()))
    for mi in sorted(per): bm+=struct.pack('<2I',len(per[mi]),mi)+struct.pack('<%dI'%len(per[mi]),*per[mi])
    for c in g.first(3).children:
        if c.type==0x50E: c.data=bm
    return g,nv,nt

def build_geometry(tmpl_geom,tris,materials,flags=0x0001005E):
    """tris: list of (matindex, [(pos,nrm,uv,rgba)]*3). returns new geometry chunk"""
    vidx={}; verts=[]; T=[]
    for mi,t in tris:
        ids=[]
        for v in t:
            key=(tuple(round(x,5) for x in v[0]),tuple(round(x,3) for x in v[1]),tuple(round(x,5) for x in v[2]),v[3])
            if key not in vidx: vidx[key]=len(verts); verts.append(key)
            ids.append(vidx[key])
        if len(set(ids))==3: T.append((mi,ids))
    assert len(verts)<65536
    # default: positions|textured|prelit|normals|modulate, 1 uv set, not lit
    nv=len(verts); nt=len(T); normals=bool(flags&0x10)
    b=bytearray(struct.pack('<4I',flags,nt,nv,1))
    for v in verts: b+=bytes(v[3])
    for v in verts: b+=struct.pack('<2f',*v[2])
    for mi,(a,bb,c) in T: b+=struct.pack('<4H',bb,a,mi,c)
    P=np.array([v[0] for v in verts]); ctr=(P.min(0)+P.max(0))/2; rad=float(np.linalg.norm(P-ctr,axis=1).max())
    b+=struct.pack('<4f',*ctr,rad)+struct.pack('<2I',1,int(normals))
    for v in verts: b+=struct.pack('<3f',*v[0])
    if normals:
        for v in verts: b+=struct.pack('<3f',*v[1])
    g=copy.deepcopy(tmpl_geom)
    g.first(1).data=bytes(b)
    ml=g.first(8)
    ml.children=[Chunk(1,struct.pack('<I',len(materials))+struct.pack('<i',-1)*len(materials))]+materials
    # binmesh: triangle lists per material
    per={}
    for mi,ids in T: per.setdefault(mi,[]).extend(ids)
    bm=struct.pack('<3I',0,len(per),sum(len(x) for x in per.values()))
    for mi in sorted(per): bm+=struct.pack('<2I',len(per[mi]),mi)+struct.pack('<%dI'%len(per[mi]),*per[mi])
    ext=g.first(3)
    for c in ext.children:
        if c.type==0x50E: c.data=bm
    return g,nv,nt

def empty_geometry(tmpl_geom):
    """keep materials, collapse to one sub-millimetre triangle inside the body (hidden)"""
    v=((0.0,0.5,0.6),(0.0,1.0,0.0),(0.0,0.0),(0,0,0,255))
    mats=tmpl_geom.first(8).children[1:]
    g,_,_=build_geometry(tmpl_geom,[(0,[v,((0.0,0.5,0.6001),)+v[1:],((0.0001,0.5,0.6),)+v[1:]])],mats)
    return g

# ---------------- SLF objects ----------------
class Obj:
    def __init__(s,d,e):
        s.name,off,size,s.type=e
        s.raw=d[off:off+size]; h=objhdr(d,off); s.hdr=h
        s.hlen=h['end']-off
        s.lod=bool(h['flags']&0x100)
        s.parts=[]   # list of ('raw',bytes) / ('atomic',Chunk)
        body=s.raw[s.hlen:]
        if s.lod:
            o0,o1=struct.unpack_from('<2I',body,0)
            rel=[o0-off-s.hlen,o1-off-s.hlen]
            s.lodrel=rel
            cur=0; segs=[]
            for r in rel:
                at=r+0x30
                segs.append(('raw',body[cur:at]))
                sz=struct.unpack_from('<I',body,at+4)[0]
                segs.append(('atomic',read(body,at,at+12+sz)[0])); cur=at+12+sz
            segs.append(('raw',body[cur:]))
            s.parts=segs
        else:
            sz=struct.unpack_from('<I',body,4)[0]
            assert struct.unpack_from('<I',body,0)[0]==0x14
            s.parts=[('atomic',read(body,0,12+sz)[0]),('raw',body[12+sz:])]
    def atomics(s): return [p[1] for p in s.parts if p[0]=='atomic']
    def serialize(s,fileoff):
        out=bytearray(s.raw[:s.hlen]); body=bytearray(); lodpos=[]
        for kind,v in s.parts:
            if kind=='raw': body+=v
            else:
                if s.lod: lodpos.append(len(body)-0x30)
                body+=write([v])
        if s.lod:
            struct.pack_into('<2I',body,0,*[fileoff+s.hlen+p for p in lodpos])
        return bytes(out+body)

def rebuild_slf(d,objs_by_name):
    """objs_by_name: directory name or directory index -> Obj (possibly modified); keeps everything else.
    Directory names are cut at 20 characters, so scenes with long names must use indices."""
    ver,es=dirents(d)
    out=bytearray(d[:es[0][1]])   # header + directory, patched below
    newdir=[]
    for i,e in enumerate(es):
        name,off,size,typ=e
        if typ==0xfefe: newdir.append(e); continue
        key=i if i in objs_by_name else name
        if key in objs_by_name:
            blob=objs_by_name[key].serialize(len(out))
        else: blob=d[off:off+size]
        newdir.append((name,len(out),len(blob),typ)); out+=blob
    for i,e in enumerate(newdir):
        if e[3]==0xfefe: continue
        struct.pack_into('<2I',out,0x424+i*32+20,e[1],e[2])
    return bytes(out)
