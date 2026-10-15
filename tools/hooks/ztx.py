"""MotoGP 08 .ZTX localized text tables (MENU\\TEXT\\<LANG>\\*.ZTX).
layout: 12 zero bytes, u16 count, u16 1, u32 0 (runtime: entry-table pointer), then count entries
{u32 nstrings, u32 hash, u32 off}; entry e's string table is at e+off: nstrings u32 offsets (relative to e)
each pointing at a NUL-terminated UTF-32LE string. Entries sorted by hash as SIGNED int32 (binary search at 0x4e5960).
hash (0x4fa070): key uppercased, NUL-padded, summed over 32-bit LE words: h += (w - 0x30303030) * [1, 0x2f2f2f2f, 0x9df44aa1][i % 3]
"""
import struct,sys
K=0x30303030; T=[1,0x2f2f2f2f,0x9df44aa1]
def khash(s):
    b=s.upper().encode()[:0x7f]; b=b+b'\0'*(0x84-len(b))
    acc=0; i=0; p=0
    while True:
        w=struct.unpack_from('<I',b,p)[0]
        acc=(acc+(w-K)*T[i%3])&0xffffffff
        p+=4; i+=1
        if b[p]==0: break
    return acc
def s32(h): return h-(1<<32) if h&0x80000000 else h
def parse(d):
    cnt=struct.unpack_from('<H',d,12)[0]
    out=[]
    for i in range(cnt):
        E=0x14+12*i
        n,h,off=struct.unpack_from('<III',d,E)
        strs=[]
        for j in range(n):
            x=struct.unpack_from('<I',d,E+off+4*j)[0]
            p=E+x; s=''
            while True:
                c=struct.unpack_from('<I',d,p)[0]
                if c==0: break
                s+=chr(c); p+=4
            strs.append(s)
        out.append([h,strs])
    return out
def build(entries, sort=True):
    if sort: entries=sorted(entries,key=lambda e:s32(e[0]))
    cnt=len(entries)
    hdr=b'\0'*12+struct.pack('<HHI',cnt,1,0)
    tab=bytearray(12*cnt); body=bytearray()
    base=0x14+12*cnt
    for i,(h,strs) in enumerate(entries):
        E=0x14+12*i
        blk=base+len(body)
        struct.pack_into('<III',tab,12*i,len(strs),h,blk-E)
        offs=bytearray(4*len(strs)); sb=bytearray()
        for j,s in enumerate(strs):
            struct.pack_into('<I',offs,4*j,blk+4*len(strs)+len(sb)-E)
            sb+=s.encode('utf-32-le')+b'\0\0\0\0'
        body+=offs+sb
    return hdr+bytes(tab)+bytes(body)
if __name__=='__main__':
    d=open(sys.argv[1],'rb').read()
    for h,s in parse(d): print('%08x %d %r'%(h,len(s),s))
