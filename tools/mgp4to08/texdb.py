import struct,numpy as np
from .mgp4tex import textures,decode,tex_ids
def load_texdb(paths):
    db={}
    for p in paths:
        d=open(p,'rb').read(); i=d.find(b'TEX10001')
        while i>=0:
            hs=struct.unpack_from('<I',d,i+0x20)[0]
            ts,_=textures(d,i+hs-0x40); ids=tex_ids(d,i)
            for tid,t in zip(ids,ts):
                if tid not in db: db[tid]=decode(d,t)
            i=d.find(b'TEX10001',i+8)
    return db
