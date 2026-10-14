"""Read/clone PS2 native RenderWare textures (8-bit palettized, as found in MotoGP 08 TXDs)."""
import struct,copy,numpy as np
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

# ---------------------------------------------------------------- any size
from . import gs as _gs

def raw_indices(tn):
    """(idx (h,w) uint8, palette bytes as stored, palette format 0x100 (1555) / 0x500 (8888))"""
    info,px=raster_parts(tn)
    w,h,dep,fmt=struct.unpack_from('<4I',info); pxsz,palsz=struct.unpack_from('<2I',info,48)
    assert dep==8
    tw,th=struct.unpack_from('<2I',px,0x20)
    words=np.frombuffer(px[0x50:0x50+tw*th*4],np.uint32)
    mem=_gs.ct32_write(words,tw,th,max(1,(tw+63)//64))
    rbw=max(2,(w+63)//64); rbw+=rbw&1
    return _gs.read8(mem,w,h,rbw),px[pxsz+0x50:pxsz+palsz],fmt&0xf00

def _layout(w,h):
    """(tbw, palette block offset, gpu words) of a PSMT8 image + 256-colour CLUT, as RenderWare lays them out"""
    tbw=max(2,(w+63)//64); tbw+=tbw&1
    pw=tbw//2; ph=(h+63)//64; pages=pw*ph
    used=set()
    for y in range(0,h,16):
        for x in range(0,w,16):
            used.add(_gs.addr8(x,y,tbw)//256)
    last=pages-1
    if all(last*32+b not in used for b in (28,29,30,31)):
        cbp=last*32+28; total=pages
    else:
        cbp=pages*32; total=pages+1
    return tbw,cbp,total*2048

def make_raster(template,name,idx,pal):
    """new 8-bit texture node from template (same palette format), any power-of-two size.
    idx: (h,w) uint8; pal: (256,4) uint8 RGBA with alpha 0..255"""
    tn=copy.deepcopy(template)
    info,px=[c.data for c in read(tn.children[3].data)]
    info=bytearray(info); h,w=idx.shape
    fmt=struct.unpack_from('<I',info,12)[0]
    tbw,cbp,gpu=_layout(w,h)
    struct.pack_into('<2I',info,0,w,h)
    tex0=struct.unpack_from('<Q',info,16)[0]
    tw=(w-1).bit_length(); th=(h-1).bit_length()
    tex0&=~((0x3f<<14)|(0xf<<26)|(0xf<<30)); tex0|=(tbw<<14)|(tw<<26)|(th<<30)
    struct.pack_into('<Q',info,16,tex0)
    struct.pack_into('<I',info,24,cbp)
    palsz=struct.unpack_from('<I',info,52)[0]
    pxsz=0x50+w*h
    struct.pack_into('<I',info,48,pxsz); struct.pack_into('<I',info,56,gpu)
    hdr=bytearray(px[:0x50]); palpk=px[struct.unpack_from('<I',template_info(template),48)[0]:]
    struct.pack_into('<2I',hdr,0x20,w//2 if w>=2 else 1,h//2 if h>=2 else 1)
    q=struct.unpack_from('<Q',hdr,0x40)[0]; q=(q&~0x7fff)|((w*h)//16); struct.pack_into('<Q',hdr,0x40,q)
    rbw=tbw
    mem=np.zeros(1<<20,np.uint32); b=mem.view(np.uint8)
    for y in range(h):
        for x in range(w): b[_gs.addr8(x,y,rbw)]=idx[y,x]
    tw2,th2=max(1,w//2),max(1,h//2)
    words=_gs.ct32_read(mem,tw2,th2,max(1,(tw2+63)//64))
    p=pal.astype(int).copy(); p[:,3]=(p[:,3]*128+127)//255
    order=csm1(256)
    if fmt&0xf00==0x100:
        v=((p[:,0]*31+127)//255)|(((p[:,1]*31+127)//255)<<5)|(((p[:,2]*31+127)//255)<<10)|(np.where(p[:,3]>=64,0x8000,0))
        pp=np.zeros(256,np.uint16); pp[order]=v.astype(np.uint16); pdata=pp.tobytes()
    else:
        pp=np.zeros((256,4),np.uint8); pp[order]=p.astype(np.uint8); pdata=pp.tobytes()
    phdr=bytearray(palpk[:0x50]); dsax=dsay=0
    if fmt&0xf00==0x500 and tbw==2:      # CLUT position relative to the texture base (buffer width 1)
        page,blk=divmod(cbp,32)
        by,bx=[(r,c) for r in range(4) for c in range(8) if _gs.BT32[r][c]==blk][0]
        dsax,dsay=bx*8,page*32+by*8
    trx=struct.unpack_from('<Q',phdr,0x10)[0]
    trx=(trx&~((0x7ff<<32)|(0x7ff<<48)))|(dsax<<32)|(dsay<<48)
    struct.pack_into('<Q',phdr,0x10,trx)
    newpx=bytes(hdr)+words.tobytes()+bytes(phdr)+pdata
    inner=read(tn.children[3].data); inner[0].data=bytes(info); inner[1].data=newpx
    tn.children[3].data=write(inner); rename(tn,name)
    return tn

def template_info(tn): return read(tn.children[3].data)[0].data
