import struct,numpy as np,sys
from .rw import read
from .slf import dirents
from .build08 import Obj
from .rw import parse_geometry,material_texnames
from .ps2tex import decode
from .render import render
def mat(m):
    R=np.array(m[:9]).reshape(3,3); t=np.array(m[9:12]); return R,t
def scene(slf,txd,lod=0,skip=(),types=(0x303,0x403,0x103,0x203)):
    d=open(slf,'rb').read() if isinstance(slf,str) else slf
    _,es=dirents(d)
    objs=[]
    for e in es:
        if e[3] not in types: continue
        try: objs.append(Obj(d,e))
        except AssertionError: pass      # prop instances
    td=read(open(txd,'rb').read() if isinstance(txd,str) else txd)[0]
    texs={}
    for tn in td.find(0x15):
        try: texs[tn.children[1].data.split(b'\0')[0].decode().upper()]=decode(tn)
        except AssertionError: pass      # 4/32-bit rasters are not decoded (previews only)
    W={}
    def world(i):
        if i in W: return W[i]
        o=objs[i]; R,t=mat(o.hdr['m']); p=o.hdr['a']
        if p>=0:
            PR,Pt=world(p); R=R@PR; t=t@PR+Pt
        W[i]=(R,t); return W[i]
    tris=[];uvs=[];tids=[];cols=[]
    for i,o in enumerate(objs):
        if any(s in o.name for s in skip): continue
        R,t=world(i)
        ats=o.atomics(); at=ats[min(lod,len(ats)-1)]
        G=parse_geometry(at.first(0xF))
        if G.native or not G.verts: continue
        names=material_texnames(G.matlist)
        V=np.array(G.verts)@R+t
        for mid,a,b,c in G.tris:
            tris.append([V[b],V[a],V[c]])
            uvs.append([G.uvsets[0][b],G.uvsets[0][a],G.uvsets[0][c]] if G.uvsets else [(0,0)]*3)
            tids.append((names[mid] or '').upper())
            cols.append(tuple(np.mean([G.prelit[k][:4] for k in (a,b,c)],0)) if G.prelit else (255,255,255))
    return tris,uvs,tids,cols,texs
