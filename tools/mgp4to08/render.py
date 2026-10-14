import numpy as np
from PIL import Image
def _clip_near(T,eye,f,near,uvs,tids,colors):
    """clip triangles against the near plane (dot(p-eye,f)=near), carrying uvs"""
    d=(T-eye)@f-near
    inside=(d>0).all(1); part=(d>0).any(1)&~inside
    idx=list(np.nonzero(inside)[0]); out=[T[i] for i in idx]; ouv=[uvs[i] for i in idx] if uvs is not None else None
    extra=[]
    for i in np.nonzero(part)[0]:
        P=list(T[i]); U=[np.asarray(q,float) for q in (uvs[i] if uvs is not None else [(0,0)]*3)]; D=d[i]
        poly=[]
        for k in range(3):
            a,b=k,(k+1)%3
            if D[a]>0: poly.append((P[a],U[a]))
            if (D[a]>0)!=(D[b]>0):
                t=D[a]/(D[a]-D[b]); poly.append((P[a]+t*(P[b]-P[a]),U[a]+t*(U[b]-U[a])))
        for k in range(1,len(poly)-1):
            out.append(np.array([poly[0][0],poly[k][0],poly[k+1][0]]))
            if ouv is not None: ouv.append([poly[0][1],poly[k][1],poly[k+1][1]])
            idx.append(i)
    T=np.array(out).reshape(-1,3,3)
    return (T,ouv,[tids[i] for i in idx] if tids is not None else None,
            [colors[i] for i in idx] if colors is not None else None)

def render(tris, view='side', size=(800,500), colors=None, texs=None, uvs=None, tids=None, bbox=None, light=(0.3,0.6,-0.7)):
    """tris: (N,3,3) float positions. view: side (look along -x), front (along +z), top"""
    T=np.asarray(tris,float)
    if view=='side': P=T[...,[2,1,0]]*np.array([1,1,1])     # screen x=z, y=y, depth=x
    elif view=='side2': P=T[...,[2,1,0]]*np.array([-1,1,-1])
    elif view=='front': P=T[...,[0,1,2]]
    elif view=='top': P=T[...,[2,0,1]]
    elif isinstance(view,tuple):           # ('cam', eye, target, fov_deg)
        _,eye,tgt,fov=view
        eye=np.asarray(eye,float); f=np.asarray(tgt,float)-eye; f/=np.linalg.norm(f)
        r=np.cross(f,[0,1,0]); r/=np.linalg.norm(r); u=np.cross(r,f)
        T,uvs,tids,colors=_clip_near(T,eye,f,0.3,uvs,tids,colors)
        V=T-eye; z=V@f; x=V@r; y=V@u
        W,H=size; foc=(W/2)/np.tan(np.radians(fov)/2)
        P=np.stack([x/z*foc+W/2, y/z*foc+H/2, -z],-1)
        bbox=(np.array([0,0,0]),np.array([W,H,0]))
    elif view=='persp':
        a=np.radians(35); b=np.radians(20)
        R=np.array([[np.cos(a),0,np.sin(a)],[0,1,0],[-np.sin(a),0,np.cos(a)]])
        R2=np.array([[1,0,0],[0,np.cos(b),-np.sin(b)],[0,np.sin(b),np.cos(b)]])
        P=T@ (R2@R).T; P=P[...,[0,1,2]]
    W,H=size
    if bbox is None:
        mn=P.reshape(-1,3).min(0); mx=P.reshape(-1,3).max(0)
    else: mn,mx=bbox
    if isinstance(view,tuple):
        sx=P[...,0]; sy=H-P[...,1]; sz=P[...,2]
    else:
        sc=min((W-20)/max(mx[0]-mn[0],1e-9),(H-20)/max(mx[1]-mn[1],1e-9))
        sx=(P[...,0]-mn[0])*sc+10; sy=H-((P[...,1]-mn[1])*sc+10); sz=P[...,2]
    img=np.zeros((H,W,3),np.uint8); img[:]=(120,150,190) if isinstance(view,tuple) else 40; zb=np.full((H,W),-1e30)
    nrm=np.cross(T[:,1]-T[:,0],T[:,2]-T[:,0]); nl=np.linalg.norm(nrm,axis=1)+1e-12; nrm/=nl[:,None]
    L=np.array(light)/np.linalg.norm(light)
    for i in range(len(T)):
        x=sx[i]; y=sy[i]; z=sz[i]
        x0=int(max(0,np.floor(x.min()))); x1=int(min(W-1,np.ceil(x.max())))
        y0=int(max(0,np.floor(y.min()))); y1=int(min(H-1,np.ceil(y.max())))
        if x1<x0 or y1<y0: continue
        gx,gy=np.meshgrid(np.arange(x0,x1+1)+0.5,np.arange(y0,y1+1)+0.5)
        d=(y[1]-y[2])*(x[0]-x[2])+(x[2]-x[1])*(y[0]-y[2])
        if abs(d)<1e-9: continue
        l0=((y[1]-y[2])*(gx-x[2])+(x[2]-x[1])*(gy-y[2]))/d
        l1=((y[2]-y[0])*(gx-x[2])+(x[0]-x[2])*(gy-y[2]))/d
        l2=1-l0-l1
        m=(l0>=0)&(l1>=0)&(l2>=0)
        if not m.any(): continue
        zz=l0*z[0]+l1*z[1]+l2*z[2]
        sub=zb[y0:y1+1,x0:x1+1]; m&=zz>sub
        if not m.any(): continue
        shade=0.35+0.65*abs(nrm[i]@L)
        if texs is not None and tids is not None and tids[i] in texs:
            tx=texs[tids[i]]; th,tw=tx.shape[:2]
            u=l0*uvs[i][0][0]+l1*uvs[i][1][0]+l2*uvs[i][2][0]
            v=l0*uvs[i][0][1]+l1*uvs[i][1][1]+l2*uvs[i][2][1]
            texel=tx[(np.floor(v*th).astype(int)%th),(np.floor(u*tw).astype(int)%tw)]
            va=colors[i][3] if colors is not None and len(colors[i])>3 else 255
            if tx.shape[-1]==4 and ((tx[...,3]<128).any() and (tx[...,3]==0).mean()>0.001 or va<255):
                m&=texel[...,3].astype(float)*va/255>=128 # alpha test on texture x vertex alpha (failed pixels write nothing)
                if not m.any(): continue
            sub[m]=zz[m]
            px=texel[...,:3].astype(float)
            if colors is not None: px=px*np.asarray(colors[i][:3])/255.0
            img[y0:y1+1,x0:x1+1][m]=np.clip(px[m]*shade,0,255).astype(np.uint8)
        else:
            sub[m]=zz[m]
            c=np.asarray(colors[i][:3] if colors is not None else (200,200,200),float)
            img[y0:y1+1,x0:x1+1][m]=np.clip(c*shade,0,255).astype(np.uint8)
    return Image.fromarray(img)
