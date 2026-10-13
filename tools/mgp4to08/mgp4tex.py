import struct,numpy as np
from .gs import ct32_write,read4,read8
def textures(d,base):
    """walk TEX10001 at base; yield dict(off,w,h,tw,th,bpp,pal,idx)"""
    o=base+0x40; out=[]
    while o+0x20<=len(d):
        w,h,tw,th=struct.unpack_from('<4H',d,o)
        if not tw or not th or w>2048 or h>2048: break
        hdr=d[o:o+0x20]
        nbytes=tw*th*4
        bpp=8*nbytes//(w*h)
        npal=16 if bpp==4 else 256 if bpp==8 else 0
        out.append(dict(off=o,w=w,h=h,tw=tw,th=th,bpp=bpp,hdr=hdr))
        o+=0x20+npal*4+nbytes
    return out,o

def decode(d,t):
    import numpy as np
    o=t['off']; w,h,tw,th,bpp=t['w'],t['h'],t['tw'],t['th'],t['bpp']
    npal=16 if bpp==4 else 256
    pal=np.frombuffer(d,np.uint8,npal*4,o+0x20).reshape(npal,4).copy()
    if bpp==8:  # CSM1 palette swizzle
        idx=np.arange(256); idx=(idx&0xE7)|((idx&8)<<1)|((idx&16)>>1); pal=pal[idx]
    pal[:,3]=np.minimum(255,pal[:,3].astype(int)*255//128)
    px=np.frombuffer(d,np.uint32,tw*th,o+0x20+npal*4)
    mem=ct32_write(px,tw,th,max(1,tw//64))
    rbw=max(2,(w+63)//64); rbw+=rbw&1
    img=read4(mem,w,h,rbw) if bpp==4 else read8(mem,w,h,rbw)
    return pal[img]

def tex_ids(d,base_off):
    """texture ids for each texture of the TEX10001 at base_off"""
    hs,base=struct.unpack_from('<2I',d,base_off+0x20)
    words=struct.unpack_from('<%dH'%((hs-0x28)//2),d,base_off+0x28)
    ids=[base]; pending=None; i=0
    while i<len(words):
        w=words[i]; i+=1
        if w==0xffff: break
        if w==0xfffc:   # nested block: skip to 0xfffe
            while i<len(words) and words[i]!=0xfffe: i+=1
            i+=1; continue
        lo,hi=w&0xff,w>>8
        if hi&0x80 and hi&0x20 and not (hi&0x5f):
            pending=lo; continue
        if hi&0x80: delta=1
        elif pending is not None: delta=pending
        else: delta=hi
        pending=None
        ids.append(ids[-1]+delta)
    return ids
