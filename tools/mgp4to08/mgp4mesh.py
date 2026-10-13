import struct
from .mgp4obj import packets,batches
def mesh(d,o):
    """return list of strips: dict(tid, verts=[(pos,nrm,uv,col)])"""
    h=d[o-0x20:o]; sph=struct.unpack_from('<4f',h,0); ids=[x for x in struct.unpack_from('<8H',h,16) if x!=0xffff]
    out=[]
    for prog,b in batches(d,o):
        if 0x6c not in b: return None
        n,ti=struct.unpack('<2I',b[0x64][0][2]); _,num,pay=b[0x6c][0]
        cols=b[0x6a][0][2] if 0x6a in b else b'\x7f'*(3*n)
        vs=[]
        for k in range(n):
            x,y,z,nx=struct.unpack_from('<4f',pay,32*k); u,v,ny,nz=struct.unpack_from('<4f',pay,32*k+16)
            adc=struct.unpack_from('<I',pay,32*k+12)[0]&1
            vs.append(((x,y,z),(nx,ny,nz),(u,v),tuple(cols[3*k:3*k+3]),adc))
        out.append(dict(tid=ids[ti] if ti<len(ids) else None,prog=prog,verts=vs))
    return dict(sphere=sph,ids=ids,strips=out)
def strip_tris(vs):
    """triangles of a PS2 strip; a vertex with ADC set does not close a triangle.
    Winding is fixed so the face normal agrees with the vertex normals."""
    for k in range(len(vs)-2):
        if vs[k+2][4]: continue
        a,b,c=vs[k],vs[k+1],vs[k+2]
        if a[0]==b[0] or b[0]==c[0] or a[0]==c[0]: continue
        e1=[b[0][i]-a[0][i] for i in range(3)]; e2=[c[0][i]-a[0][i] for i in range(3)]
        fn=(e1[1]*e2[2]-e1[2]*e2[1],e1[2]*e2[0]-e1[0]*e2[2],e1[0]*e2[1]-e1[1]*e2[0])
        vn=[a[1][i]+b[1][i]+c[1][i] for i in range(3)]
        if sum(fn[i]*vn[i] for i in range(3))<0: a,b=b,a
        yield a,b,c
