import struct,sys
def dirents(d):
    assert d[0x400:0x404]==b'SLF\0'
    a,ver,n=struct.unpack_from('<3I',d,0x404)
    out=[]
    for i in range(n):
        o=0x424+i*32
        name=d[o:o+20].split(b'\0')[0].decode('latin1')
        off,size,typ=struct.unpack_from('<3I',d,o+20)
        out.append((name,off,size,typ))
    return ver,out
def objhdr(d,off):
    hs=struct.unpack_from('<I',d,off)[0]
    uxid=d[off+4:off+12]; flags=struct.unpack_from('<I',d,off+12)[0]
    one=struct.unpack_from('<I',d,off+16)[0]
    m=struct.unpack_from('<12f',d,off+20)
    a,b,c,e=struct.unpack_from('<4i',d,off+68)
    nl=struct.unpack_from('<I',d,off+84)[0]
    name=d[off+88:off+88+nl].split(b'\0')[0].decode() if nl<64 else ''
    return dict(hs=hs,uxid=uxid,flags=flags,one=one,m=m,a=a,b=b,c=c,e=e,name=name,end=off+88+nl+1)
