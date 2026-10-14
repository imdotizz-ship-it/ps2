"""RenderWare world (.BSP) reader: collision triangles of a MotoGP 08 track."""
import struct,numpy as np
from .rw import read
def world(d):
    w=read(d)[0]; assert w.type==0x0B
    st=w.first(1).data
    root,ox,oy,oz,ntri,nvert,nplane,nsect,colsz,fmt=struct.unpack_from('<I3f6I',st)
    mats=[m for m in w.first(8).children if m.type==7]
    info=[]
    for m in mats:
        ud=m.first(3).first(0x11f) if m.first(3) else None
        info.append(ud.data if ud else b'')
    tris=[];secs=[]
    def walk(c):
        if c.type==0x09:
            s=c.first(1).data
            mbase,nt,nv=struct.unpack_from('<3I',s); o=12+24+8   # bbox(6f), unused(2u32)
            V=np.frombuffer(s,np.float32,nv*3,o).reshape(nv,3); o+=12*nv
            if fmt&0x10: o+=12*nv          # normals
            if fmt&0x08: o+=4*nv           # prelit
            ntex=(fmt>>16)&0xff or (1 if fmt&0x04 else 0)
            o+=8*nv*ntex
            T=np.frombuffer(s,np.uint16,nt*4,o).reshape(nt,4)   # v0, v1, v2, material
            secs.append((V,T[:,:3].astype(int),T[:,3].astype(int)+mbase))
        for k in (c.children or []):
            if k.type in (0x0A,0x09): walk(k)
    for c in w.children:
        if c.type in (0x0A,0x09): walk(c)
    return dict(fmt=fmt,ntri=ntri,nvert=nvert,sectors=secs,materials=info)

def triangles(W):
    """(N,3,3) triangle positions and (N,) terrain names"""
    names=[]
    for m in W['materials']:
        i=m.find(b'TerrainType\0')
        names.append(m[i+12+12:].split(b'\0')[0].decode() if i>=0 else '')
    P=[];M=[]
    for V,T,mat in W['sectors']:
        if len(T): P.append(V[T]); M.extend(names[k] if k<len(names) else '' for k in mat)
    return np.concatenate(P),np.array(M)
