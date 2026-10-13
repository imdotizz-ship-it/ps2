"""Extract a MotoGP 4 bike (body hi/mid + windscreen) in MotoGP 08 coordinates."""
import struct,numpy as np
from .mgp4obj import packets
from .mgp4mesh import mesh,strip_tris
def classify(d):
    i=d.find(b'TEX10001'); ms=[]
    for o in packets(d,i):
        m=mesh(d,o)
        if not m: continue
        cx,cy,cz,r=m['sphere']
        if m['ids']==[0x2713] or cy<300 or r>1000: continue
        m['off']=o; m['nv']=sum(len(s['verts']) for s in m['strips'])
        m['kind']='glass' if (cy>950 and r<300) else 'body'
        ms.append(m)
    groups=[]
    for m in ms:
        for g in groups:
            a=g[0]['sphere']; b=m['sphere']
            if g[0]['kind']==m['kind'] and set(g[0]['ids'])==set(m['ids']) and all(abs(a[k]-b[k])<45 for k in range(3)) and abs(a[3]-b[3])<35:
                g.append(m); break
        else: groups.append([m])
    hi=[];mid=[]
    for g in groups:
        g.sort(key=lambda m:-m['nv']); hi.append(g[0]); mid.append(g[-1])
    return hi,mid
def to08(p): return (-p[0]/1000.0, p[1]/1000.0, (724.0-p[2])/1000.0)
def nto08(n):
    l=(n[0]**2+n[1]**2+n[2]**2)**0.5 or 1
    return (-n[0]/l, n[1]/l, -n[2]/l)
def tris(meshes,kind):
    """list of (tid, [(pos,nrm,uv,col)]*3) in 08 space; winding preserved by the 180deg rotation"""
    out=[]
    for m in meshes:
        if m['kind']!=kind: continue
        for s in m['strips']:
            for t in strip_tris(s['verts']):
                out.append((s['tid'],[(to08(v[0]),nto08(v[1]),v[2],v[3]) for v in t]))
    return out
def load(path):
    """path: a MotoGP 4 bike file extracted from MOTOGP.DAT (e.g. bike_motogp_for_46.bin)"""
    d=open(path,'rb').read()
    hi,mid=classify(d)
    return d,dict(hi=tris(hi,'body'),mid=tris(mid,'body'),glass=tris(hi,'glass'))
