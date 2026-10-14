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


def add_effects(d, count):
    """SLF with `count` more 'Effect_N' entries (copies of Effect_0) after the last one; the directory
    grows, every offset moves, the @____MATLIST___@ effect count follows. Returns (bytes, first new index)."""
    if count <= 0:
        return d, None
    ver, es = dirents(d)
    effs = [i for i, e in enumerate(es) if e[3] == 0x106]
    last = effs[-1]
    base = next(e for e in es if e[0] == 'Effect_0')
    blob = d[base[1]:base[1] + base[2]]
    first = len(effs)
    new = [('Effect_%d' % (first + k), None, len(blob), 0x106) for k in range(count)]
    order = es[:last + 1] + new + es[last + 1:]
    used = [e for e in es if e[3] != 0xfefe]
    data_start = min(e[1] for e in used)
    delta = 32 * count
    head = bytearray(d[:0x424])
    struct.pack_into('<I', head, 0x40c, len(order))
    body = bytearray(d[data_start:])
    tail = bytearray()
    dirb = bytearray()
    end = data_start + delta + len(body)
    for e in order:
        name, off, size, typ = e
        if typ == 0xfefe:
            dirb += d[0x424 + 32 * es.index(e):0x424 + 32 * es.index(e) + 32] if e in es else bytes(32)
            continue
        if off is None:
            off = end + len(tail); tail += blob
        else:
            off += delta
        dirb += name.encode('latin1')[:20].ljust(20, b'\0') + struct.pack('<3I', off, size, typ)
    out = bytes(head) + bytes(dirb) + bytes(body) + bytes(tail)
    # @____MATLIST___@ holds the number of effects in its second word
    _, es2 = dirents(out)
    ml = next(e for e in es2 if e[0].startswith('@____MATLIST'))
    out = bytearray(out); struct.pack_into('<I', out, ml[1] + 4, first + count)
    return bytes(out), first
