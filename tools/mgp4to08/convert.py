"""Convert a MotoGP 4 bike into a MotoGP 08 bike slot (SLF + TXD + TXS)."""
import struct,copy,sys,numpy as np
from PIL import Image
from .rw import read,write,Chunk
from .slf import dirents
from .build08 import Obj,build_geometry,empty_geometry,make_material,rebuild_slf
from .ps2tex import encode_into,rename
from .texdb import load_texdb
from .m4bike import load

def texname(tid): return 'M4%04X'%tid

def prelit(c): return (min(255,c[0]*2),min(255,c[1]*2),min(255,c[2]*2),255)

ATLAS=256
ATLAS_NAME='chassisA_0'


def build_atlas(db,used,size):
    """(indices, palette, {texture id: (x, y, w, h)}): the textures shelf-packed into one size x size
    8-bit image, halved until they fit; one 256-colour palette, index 255 transparent if needed"""
    imgs={t:db[t] for t in used}
    for scale in (1,2,4,8,16):
        dims={t:(max(4,min(size,im.shape[1])//scale),max(4,min(size,im.shape[0])//scale)) for t,im in imgs.items()}
        order=sorted(dims,key=lambda t:-dims[t][1]); rects={}; x=y=row=0; ok=True
        for t in order:
            w,h=dims[t]
            if x+w>size: x=0; y+=row; row=0
            if y+h>size: ok=False; break
            rects[t]=(x,y,w,h); x+=w; row=max(row,h)
        if ok: break
    canvas=np.zeros((size,size,4),np.uint8)
    for t,(x,y,w,h) in rects.items():
        canvas[y:y+h,x:x+w]=np.array(Image.fromarray(imgs[t],'RGBA').resize((w,h),Image.BILINEAR))
    q=Image.fromarray(canvas[...,:3]).quantize(255,method=Image.MEDIANCUT,dither=Image.NONE)
    idx=np.array(q).astype(np.uint8)
    pal=np.zeros((256,4),np.uint8)
    p=q.getpalette()[:255*3]; p+= [0]*(255*3-len(p))
    pal[:255,:3]=np.array(p).reshape(255,3); pal[:,3]=255
    cut=canvas[...,3]<128
    for t,(x,y,w,h) in rects.items():
        if t==0x2712: cut[y:y+h,x:x+w]=False          # glass: translucency comes from the material
    if cut.any():
        idx[cut]=255; pal[255]=(0,0,0,0)
    return idx,pal,rects


def convert(class_dir,slot,bike_path,common_path):
    """class_dir: extracted MotoGP 08 BIKES folder (from BIKES.MIX); slot: BIKE01..BIKE06;
    bike_path: MotoGP 4 bike file; common_path: MotoGP 4 CourseCommon file (shared textures).
    Returns (slf, txd, txs, stats)."""
    base='%s/%s/%s'%(class_dir,slot,slot)
    d=open(base+'.SLF','rb').read()
    _,es=dirents(d)
    objs={e[0]:Obj(d,e) for e in es if e[3] in (0x303,0x403)}
    byshort={k.split('@')[0]:v for k,v in objs.items()}
    _,M=load(bike_path)
    # textures
    db=load_texdb([bike_path]); own=set(db)
    for k,v in load_texdb([common_path]).items(): db.setdefault(k,v)
    # chassis LODs
    ch=byshort['CHASSIS']; ats=ch.atomics()
    g0=ats[0].first(0xF)
    mats0=g0.first(8).children[1:]
    tmpl_liv=mats0[0]; tmpl_obj=mats0[1] if len(mats0)>1 else mats0[0]
    used=sorted({t for k in ('hi','mid','glass') for t,_ in M[k]})
    atlas_idx,atlas_pal,rects=build_atlas(db,used,ATLAS)
    def remap(tris):
        """uv into the texture's atlas cell (triangles that tile are moved to one repeat and clamped)"""
        out=[]
        for t,tri in tris:
            x,y,w,h=rects[t]
            us=[v[2][0] for v in tri]; vs=[v[2][1] for v in tri]
            fu=np.floor(min(us)); fv=np.floor(min(vs))
            nt=[]
            for v in tri:
                u=min(max(v[2][0]-fu,0.0),1.0); vv=min(max(v[2][1]-fv,0.0),1.0)
                uv=((x+0.5+u*(w-1))/ATLAS,(y+0.5+vv*(h-1))/ATLAS)
                nt.append((v[0],v[1],uv,v[3]))
            out.append((0,nt))
        return out
    def body_geom(tmpl_geom,tris):
        mats=[make_material(tmpl_liv,ATLAS_NAME)]
        T=[(0,[(v[0],v[1],v[2],prelit(v[3])) for v in tri]) for _,tri in remap(tris)]
        return build_geometry(tmpl_geom,T,mats)
    stats={}
    for k,(at,key) in enumerate(zip(ats,['hi','mid'])):
        g=at.first(0xF); ng,nv,nt=body_geom(g,M[key]); stats[key]=(nv,nt)
        at.children[at.children.index(g)]=ng
    # windscreen: bring body-space vertices into the FGLASS object's own frame
    order=[e[0] for e in es if e[3] in (0x303,0x403)]
    def world(name):
        o=objs[name]; m=o.hdr['m']; R=np.array(m[:9]).reshape(3,3); t=np.array(m[9:12])
        if o.hdr['a']>=0:
            PR,Pt=world(order[o.hdr['a']]); R=R@PR; t=t@PR+Pt
        return R,t
    fg=byshort['FGLASS']; at=fg.atomics()[0]; g=at.first(0xF)
    R,t=world(fg.name); Ri=np.linalg.inv(R)
    glass=[(tid,[(tuple((np.array(v[0])-t)@Ri),tuple(np.array(v[1])@Ri),v[2],v[3]) for v in tri]) for tid,tri in M['glass']]
    gm=g.first(8).children[1]      # the 08 windscreen material: chassis texture, translucent material colour
    mats=[make_material(gm,ATLAS_NAME)]
    ng,nv,nt=build_geometry(g,[(0,[(v[0],v[1],v[2],prelit(v[3])) for v in tri]) for _,tri in remap(glass)],mats)
    at.children[at.children.index(g)]=ng; stats['glass']=(nv,nt)
    # hide the 08 number plates (MotoGP 4 liveries carry the numbers)
    for n in ['NUMBERA','NUMBERB','NUMBERACustom','NUMBERBCustom','NUMBERC','NUMBERCCustom']:
        if n in byshort:
            at=byshort[n].atomics()[0]; g=at.first(0xF); at.children[at.children.index(g)]=empty_geometry(g)
    slf=rebuild_slf(d,objs)
    # TXD: the game only takes the textures the bike shipped with (one more breaks the race render),
    # so the atlas replaces the pixels of the livery textures (every paintwork shows the MotoGP 4 one)
    td=read(open('%s/%s/PICTURES/%s.TXD'%(class_dir,slot,slot),'rb').read())[0]
    n=0
    for tn in td.find(0x15):
        name=tn.children[1].data.split(b'\0')[0].decode().upper()
        if name.startswith('CHASSIS') and name.endswith('_0'):
            info=read(tn.children[3].data)[0].data; w,h=struct.unpack_from('<2I',info)
            assert (w,h)==(ATLAS,ATLAS), (name,w,h)
            encode_into(tn,atlas_idx,atlas_pal); n+=1
    assert n, 'no CHASSIS?_0 texture'
    txd=write([td])
    txs=open(base+'.TXS','rb').read()
    return slf,txd,txs,stats
