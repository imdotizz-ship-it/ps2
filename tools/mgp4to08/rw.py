"""Minimal RenderWare 3.x binary stream reader/writer (platform-independent geometry)."""
import struct
VER=0x1C020037
class Chunk:
    def __init__(s,typ,data=b'',children=None,ver=VER):
        s.type=typ; s.data=data; s.children=children; s.ver=ver
    def find(s,t): return [c for c in (s.children or []) if c.type==t]
    def first(s,t):
        r=s.find(t); return r[0] if r else None
    def __repr__(s): return 'Chunk(%x,%d,%s)'%(s.type,len(s.data),len(s.children) if s.children is not None else '-')
CONTAINERS={0x10,0x14,0x0F,0x08,0x07,0x06,0x03,0x1A,0x0E,0x16,0x15,0x0B,0x0A,0x09,0x2B}
def read(d,o=0,end=None,depth=0):
    """read chunks in d[o:end]"""
    end=len(d) if end is None else end; out=[]
    while o+12<=end:
        t,sz,v=struct.unpack_from('<3I',d,o)
        if v!=VER and depth==0 and not out: raise ValueError('bad chunk at %x'%o)
        body=d[o+12:o+12+sz]
        if t in CONTAINERS:
            out.append(Chunk(t,b'',read(body,0,len(body),depth+1),v))
        else: out.append(Chunk(t,body,None,v))
        o+=12+sz
    return out
def write(chunks):
    out=b''
    for c in chunks:
        body=write(c.children) if c.children is not None else c.data
        out+=struct.pack('<3I',c.type,len(body),c.ver)+body
    return out
def string_chunk(s):
    b=s.encode()+b'\0'; b+=b'\0'*((-len(b))%4)
    return Chunk(2,b)

class Geometry:
    pass
def parse_geometry(g):
    """g: Chunk 0x0F. returns Geometry with verts, normals, uvs, prelit, tris(matid,a,b,c), materials raw chunks"""
    st=g.first(1).data
    flags,ntri,nvert,nmorph=struct.unpack_from('<4I',st,0)
    G=Geometry(); G.flags=flags; o=16
    G.native=bool(flags&0x01000000)
    ntex=(flags>>16)&0xff or (2 if flags&0x80 else 1 if flags&0x04 else 0)
    G.prelit=G.uvs=None
    if not G.native:
        if flags&0x08:
            G.prelit=[struct.unpack_from('<4B',st,o+4*i) for i in range(nvert)]; o+=4*nvert
        G.uvsets=[]
        for t in range(ntex):
            G.uvsets.append([struct.unpack_from('<2f',st,o+8*i) for i in range(nvert)]); o+=8*nvert
        G.tris=[]
        for i in range(ntri):
            v2,v1,mid,v3=struct.unpack_from('<4H',st,o+8*i); G.tris.append((mid,v1,v2,v3))
        o+=8*ntri
    sph=struct.unpack_from('<4f',st,o); hasv,hasn=struct.unpack_from('<2I',st,o+16); o+=24
    G.sphere=sph; G.verts=G.normals=None
    if not G.native:
        if hasv: G.verts=[struct.unpack_from('<3f',st,o+12*i) for i in range(nvert)]; o+=12*nvert
        if hasn: G.normals=[struct.unpack_from('<3f',st,o+12*i) for i in range(nvert)]; o+=12*nvert
    G.nvert=nvert; G.ntri=ntri
    G.matlist=g.first(8)
    G.ext=g.first(3)
    return G
def material_texnames(ml):
    out=[]
    for m in ml.find(7):
        t=m.first(6)
        if t is None: out.append(None); continue
        names=[c.data.split(b'\0')[0].decode() for c in t.find(2)]
        out.append(names[0] if names else None)
    return out
