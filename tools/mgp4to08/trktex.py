"""Track texture sets of MotoGP 4 (Course*_Free: TEX10001 with linear PSMT4/PSMT8 records)."""
import struct,numpy as np
def _is_rec(d,o):
    if o+0x20>len(d): return False
    w,h=struct.unpack_from('<2H',d,o)
    return w in (8,16,32,64,128,256,512) and h in (8,16,32,64,128,256,512) and d[o+0x15:o+0x18]==b'\xff\xff\xff'
def _groups(d,base_off):
    hs=struct.unpack_from('<I',d,base_off+0x20)[0]
    words=struct.unpack_from('<%dH'%((hs-0x20)//2),d,base_off+0x20)
    i=0; groups=[]
    while i+4<=len(words):
        w=words[i]
        if w==0xffff: break
        if w==0xfffc:
            while i<len(words) and words[i]!=0xfffe: i+=1
            i+=1; continue
        if w==0xfffe: i+=1; continue
        off=words[i]|(words[i+1]<<16); tid=words[i+2]|(words[i+3]<<16); i+=4
        ids=[tid]; pending=None
        while i<len(words) and words[i] not in (0xfffc,0xfffe,0xffff):
            w=words[i]; i+=1; lo,hi=w&0xff,w>>8
            if hi&0x80 and hi&0x20 and not hi&0x5f: pending=lo; continue
            delta=1 if hi&0x80 else (pending if pending is not None else hi); pending=None
            ids.append(ids[-1]+delta)
        groups.append((off,ids))
    return groups
def _size(d,o):
    """record size: header 0x20, palette (16/256 colours, none when +0x10 is 0), image + mip levels"""
    w,h=struct.unpack_from('<2H',d,o); f8,f10=struct.unpack_from('<I',d,o+8)[0],struct.unpack_from('<I',d,o+0x10)[0]
    bpp=8 if f8&1 else 4
    npal=(256 if bpp==8 else 16) if f10 else 0
    mips=(f10-0x160)//4 if f10>=0x160 else 0
    sz=0x20+npal*4; mw,mh=w,h
    for _ in range(mips+1):
        sz+=mw*mh*bpp//8; mw//=2; mh//=2
    return sz,bpp,npal

def _resync(d,o,limit=0x40000):
    for p in range(o,min(len(d)-0x20,o+limit),16):
        if _is_rec(d,p) and struct.unpack_from('<I',d,p+0x10)[0] in (0,0x60,0x164,0x168,0x16c,0x170):
            return p
    return None

def load(d,base_off=0):
    """{id: RGBA array} for a track texture set (alpha 0..255, from the PS2 0..0x80 range)"""
    out={}; lastpal={}
    for off,ids in _groups(d,base_off):
        o=base_off+off
        for tid in ids:
            if o is None or not _is_rec(d,o): break
            w,h=struct.unpack_from('<2H',d,o)
            sz,bpp,npal=_size(d,o)
            if npal:
                pal=np.frombuffer(d,np.uint8,npal*4,o+0x20).reshape(npal,4).copy()
                if npal==256:
                    idx=np.arange(256); pal=pal[(idx&0xE7)|((idx&8)<<1)|((idx&16)>>1)]
                pal[:,3]=np.minimum(255,pal[:,3].astype(int)*255//128)
                lastpal[bpp]=pal
            else:
                pal=lastpal.get(bpp)
                if pal is None: break
            if o+0x20+npal*4+w*h*bpp//8>len(d): break
            px=np.frombuffer(d,np.uint8,w*h*bpp//8,o+0x20+npal*4)
            img=np.stack([px&15,px>>4],1).reshape(h,w) if bpp==4 else px.reshape(h,w)
            out[tid]=pal[img]
            nxt=o+sz
            o=nxt if _is_rec(d,nxt) else _resync(d,o+0x20)
    return out
