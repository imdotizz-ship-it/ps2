import struct
from .vif import parse
def packets(d,end):
    """find mesh packets: (hdr_off, sphere, ids, dma_off)"""
    out=[]
    o=0
    while o<end-16:
        t=struct.unpack_from('<I',d,o)[0]
        if (t>>28)&7==6 and (t&0x0fff0000)==0 and (t&0xffff) and d[o+8:o+16] in (bytes.fromhex('0000000503020001'),bytes.fromhex('0000000501010001')):
            out.append(o); o+=16+(t&0xffff)*16
        else: o+=16
    return out
def batches(d,o):
    t=struct.unpack_from('<I',d,o)[0]; qwc=t&0xffff
    cur={}
    for (p,c,num,imm,pay) in parse(d,o+8,o+16+qwc*16):
        if c>=0x60: cur.setdefault(c,[]).append((imm&0x3ff,num,pay))
        if c in (0x14,0x15,0x17):
            yield imm,cur; cur={}
