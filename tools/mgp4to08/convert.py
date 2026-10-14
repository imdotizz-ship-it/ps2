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
    def body_geom(tmpl_geom,tris):
        tids=sorted({t for t,_ in tris}); mi={t:i for i,t in enumerate(tids)}
        mats=[make_material(tmpl_liv if t in own else tmpl_obj,texname(t)) for t in tids]
        T=[(mi[t],[(v[0],v[1],v[2],prelit(v[3])) for v in tri]) for t,tri in tris]
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
    M['glass']=[(tid,[(tuple((np.array(v[0])-t)@Ri),tuple(np.array(v[1])@Ri),v[2],v[3]) for v in tri]) for tid,tri in M['glass']]
    gm=g.first(8).children[1]
    tids=sorted({t for t,_ in M['glass']}); mi={t:i for i,t in enumerate(tids)}
    mats=[make_material(gm,texname(t)) for t in tids]
    ng,nv,nt=build_geometry(g,[(mi[t],[(v[0],v[1],v[2],prelit(v[3])) for v in tri]) for t,tri in M['glass']],mats)
    at.children[at.children.index(g)]=ng; stats['glass']=(nv,nt)
    # hide the 08 number plates (MotoGP 4 liveries carry the numbers)
    for n in ['NUMBERA','NUMBERB','NUMBERACustom','NUMBERBCustom','NUMBERC','NUMBERCCustom']:
        if n in byshort:
            at=byshort[n].atomics()[0]; g=at.first(0xF); at.children[at.children.index(g)]=empty_geometry(g)
    slf=rebuild_slf(d,objs)
    # TXD
    used=sorted({t for k in M for t,_ in M[k]})
    td=read(open('%s/%s/PICTURES/%s.TXD'%(class_dir,slot,slot),'rb').read())[0]
    tmpl={}
    for tn in td.find(0x15):
        n=tn.children[1].data.split(b'\0')[0].decode()
        info=read(tn.children[3].data)[0].data
        w,h,dep,fmt=struct.unpack_from('<4I',info)
        if dep==8 and fmt&0xf00==0x500 and w==h and w not in tmpl: tmpl[w]=tn
    txs_add=[]
    for t in used:
        img=db[t]; h,w=img.shape[:2]; s=max(w,h)
        s=min([k for k in sorted(tmpl) if k>=s] or [max(tmpl)])
        im=Image.fromarray(img,'RGBA').resize((s,s),Image.NEAREST)
        a=np.array(im)
        cut=(a[...,3]<128).mean()>0.005 and t!=0x2712
        rgb=Image.fromarray(a[...,:3]).quantize(255,method=Image.MEDIANCUT,dither=Image.NONE)
        idx=np.array(rgb).astype(np.uint8)
        pal=np.zeros((256,4),np.uint8)
        p=np.array(rgb.getpalette()[:255*3]+[0]*(255*3-len(rgb.getpalette()[:255*3]))).reshape(255,3)
        pal[:255,:3]=p
        if t==0x2712:      # glass keeps its translucency
            pal[:255,3]=int(a[...,3].mean())
        elif cut:
            idx[a[...,3]<128]=255; pal[255]=(0,0,0,0); pal[:255,3]=255
        else:
            pal[:,3]=0x50*255//128
        tn=copy.deepcopy(tmpl[s]); encode_into(tn,idx,pal); rename(tn,texname(t))
        td.children.append(tn)
        txs_add.append('%-36s%s'%(texname(t),'KT5A128' if cut else ''))
    st=bytearray(td.first(1).data); struct.pack_into('<H',st,0,len(td.find(0x15))); td.first(1).data=bytes(st)
    txd=write([td])
    txs=open(base+'.TXS','rb').read().decode('latin1').rstrip('\r\n')
    nl='\r\n' if '\r\n' in txs else '\n'
    txs=(txs+nl+nl.join(txs_add)+nl+nl).encode('latin1')   # entries end at an empty line
    return slf,txd,txs,stats
