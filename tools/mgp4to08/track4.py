"""MotoGP 4 track geometry (Course<Name>: OBJ10001 world meshes + local objects)."""
import struct,numpy as np
from .vif import parse
from .mgp4obj import packets

def _f(u): return struct.unpack('<f',struct.pack('<I',u))[0]

def vu_batches(d,o):
    """emulate VU1 data memory per MSCAL batch: yields (prog, {addr:(cmd,values)}, {cmd:[(base,num,cl,wl)]})"""
    t=struct.unpack_from('<I',d,o)[0]; cl,wl=1,1; mem={}; info={}
    for (p,c,num,imm,pay) in parse(d,o+8,o+16+(t&0xffff)*16):
        if c==0x01: cl,wl=imm&0xff,(imm>>8)&0xff
        elif c>=0x60:
            vn=((c>>2)&3)+1; vl=c&3; n=num or 256; base=imm&0x3ff
            fmt={0:'I',1:'H',2:'B'}[vl]; sz={0:4,1:2,2:1}[vl]
            vals=struct.unpack('<%d%s'%(n*vn,fmt),pay[:n*vn*sz])
            for i in range(n): mem[base+(i//wl)*cl+(i%wl)]=(c,vals[i*vn:(i+1)*vn])
            info.setdefault(c,[]).append((base,n,cl,wl))
        elif c in (0x14,0x15,0x17):
            yield imm,mem,info; mem={}; info={}

def packet_ids(d,o):
    """texture ids of a mesh packet (the last non-padding 16-byte row before the DMA tag)"""
    for k in range(1,5):
        r=d[o-16*k:o-16*(k-1)]
        if r!=b'\xff'*16: return [x for x in struct.unpack('<8H',r) if x!=0xffff]
    return []

def strips(d,o):
    """strips of one packet: dict(kind 'W' world / 'L' local, tid, flags, verts=[(pos,nrm,uv,rgba,adc)])"""
    ids=packet_ids(d,o); out=[]
    for prog,mem,info in vu_batches(d,o):
        hdr=mem.get(0,(0,(0,0,0,0)))[1]
        ti=hdr[1] if len(hdr)>1 else 0
        tid=ids[ti] if ti<len(ids) else (ids[0] if ids else None)
        if 0x68 in info:                 # world: V3 pos | V2 uv (ADC = bit 0 of u) | V4-8 rgba
            n=info[0x68][0][1]; vs=[]
            for k in range(n):
                p=mem[1+3*k][1]; uv=mem.get(2+3*k,(0,(0,0)))[1]; c=mem.get(3+3*k,(0,(128,128,128,128)))[1]
                vs.append(((_f(p[0]),_f(p[1]),_f(p[2])),None,(_f(uv[0]),_f(uv[1])),tuple(c),uv[0]&1))
            out.append(dict(kind='W',tid=tid,flags=hdr[2:],verts=vs))
        elif 0x6c in info and len(info[0x6c])>=2:   # local: xyz nx | u v ny nz (ADC = bit 0 of nx) | rgba
            n=info[0x6c][1][1]//2; vs=[]
            for k in range(n):
                a=mem[1+3*k][1]; b=mem[2+3*k][1]; c=mem.get(3+3*k,(0,(128,128,128,128)))[1]
                vs.append(((_f(a[0]),_f(a[1]),_f(a[2])),(_f(a[3]),_f(b[2]),_f(b[3])),(_f(b[0]),_f(b[1])),tuple(c),a[3]&1))
            out.append(dict(kind='L',tid=tid,flags=hdr[2:],verts=vs))
    return out

def triangles(vs):
    """(a,b,c) vertex triples of a strip; a vertex with the ADC bit set does not close a triangle"""
    for k in range(len(vs)-2):
        if vs[k+2][4]: continue
        a,b,c=(vs[k],vs[k+1],vs[k+2]) if k%2==0 else (vs[k+1],vs[k],vs[k+2])
        if a[0]==b[0] or b[0]==c[0] or a[0]==c[0]: continue
        yield a,b,c

def course(path):
    """all strips of a Course<Name>.bin (first OBJ10001 block)"""
    d=open(path,'rb').read()
    end=d.find(b'OBJ10001',8)
    end=len(d) if end<0 else end
    out=[]
    for o in packets(d,end):
        for s in strips(d,o):
            s['off']=o; out.append(s)
    return out
