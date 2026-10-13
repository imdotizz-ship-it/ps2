import struct
VN={0:1,1:2,2:3,3:4}
def unpack_size(cmd,num):
    vn=(cmd>>2)&3; vl=cmd&3
    bits={0:32,1:16,2:8,3:16}[vl] if vl!=3 else 16
    comps=vn+1
    if vl==3: return (num*16+31)//32*4  # V4-5: 16 bits per vector
    return ((num*comps*{0:32,1:16,2:8}[vl])+31)//32*4
def parse(d,o,end):
    """yield (offset, cmd, num, imm, payload bytes)"""
    while o<end:
        w=struct.unpack_from('<I',d,o)[0]; cmd=(w>>24)&0x7f; num=(w>>16)&0xff; imm=w&0xffff
        o+=4; pay=b''
        if cmd>=0x60:
            n=num or 256
            sz=unpack_size(cmd,n); pay=d[o:o+sz]; o+=sz
        elif cmd==0x20: pay=d[o:o+4]; o+=4
        elif cmd in (0x30,0x31): pay=d[o:o+16]; o+=16
        elif cmd in (0x50,0x51):
            o=(o+15)&~15; n=imm or 65536; pay=d[o:o+n*16]; o+=n*16
        elif cmd==0x4a:
            n=num or 256; pay=d[o:o+n*8]; o+=n*8
        yield (o,w>>24,num,imm,pay)
