"""Read/clone PS2 native RenderWare textures (8-bit palettized, as found in MotoGP 08 TXDs)."""
import struct,numpy as np
from .rw import read,write,Chunk
from .gs import ct32_write,read8,ct32_read
def csm1(n):
    idx=np.arange(n)
    if n==256: idx=(idx&0xE7)|((idx&8)<<1)|((idx&16)>>1)
    return idx
def raster_parts(tn):
    r=tn.children[3].data; inner=read(r)
    return inner[0].data,inner[1].data
def decode(tn):
    info,px=raster_parts(tn)
    w,h,dep,fmt=struct.unpack_from('<4I',info); pxsz,palsz=struct.unpack_from('<2I',info,48)
    assert dep==8
    img=px[0x50:pxsz]; pal=px[pxsz+0x50:pxsz+palsz]
    tw,th=struct.unpack_from('<2I',px,0x20)
    words=np.frombuffer(img[:tw*th*4],np.uint32)
    mem=ct32_write(words,tw,th,max(1,tw//64))
    rbw=max(2,w//64); rbw+=rbw&1
    idx=read8(mem,w,h,rbw)
    if fmt&0xf00==0x100:
        v=np.frombuffer(pal[:512],np.uint16)[csm1(256)].astype(int)
        p=np.stack([(v&31)*255//31,((v>>5)&31)*255//31,((v>>10)&31)*255//31,np.where(v&0x8000,255,0)],1).astype(np.uint8)
    else:
        p=np.frombuffer(pal[:1024],np.uint8).reshape(256,4)[csm1(256)].copy()
        p[:,3]=np.minimum(255,p[:,3].astype(int)*255//128)
    return p[idx]
def encode_into(tn,idx,pal_rgba):
    """replace pixels/palette of an 8bit texture node tn (same size). idx: (h,w) uint8, pal_rgba: (256,4) uint8 (alpha 0..255)"""
    info,px=raster_parts(tn); px=bytearray(px)
    w,h=struct.unpack_from('<2I',info)
    pxsz,palsz=struct.unpack_from('<2I',info,48)
    assert idx.shape==(h,w)
    tw,th=struct.unpack_from('<2I',px,0x20)
    rbw=max(2,w//64); rbw+=rbw&1
    from .gs import addr8
    mem=np.zeros(1<<20,np.uint32); b=mem.view(np.uint8)
    for y in range(h):
        for x in range(w): b[addr8(x,y,rbw)]=idx[y,x]
    words=ct32_read(mem,tw,th,max(1,tw//64))
    px[0x50:0x50+tw*th*4]=words.tobytes()
    p=pal_rgba.copy().astype(int); p[:,3]=(p[:,3]*128+127)//255
    pp=np.zeros((256,4),np.uint8); pp[csm1(256)]=p.astype(np.uint8)
    px[pxsz+0x50:pxsz+0x50+1024]=pp.tobytes()
    inner=read(tn.children[3].data); inner[1].data=bytes(px)
    tn.children[3].data=write(inner)
def rename(tn,name):
    b=name.encode()+b'\0'; b+=b'\0'*((-len(b))%4)
    tn.children[1].data=b
