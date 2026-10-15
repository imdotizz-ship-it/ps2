#!/usr/bin/env python3
"""List the waves of a RenderWare Audio .RWS bank (MotoGP 08), with its .CRW metadata.

usage: rws_list.py BANK.RWS [--crw BANK.CRW] [--hex]
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rwslib import Bank, Crw, crw_path_for, CATEGORIES

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('rws'); ap.add_argument('--crw'); ap.add_argument('--hex', action='store_true')
a = ap.parse_args()
b = Bank.load(a.rws)
crwp = a.crw or crw_path_for(a.rws)
crw = Crw.load(crwp) if crwp else None
print('%s: dict "%s", %d waves, %d bytes ADPCM (%.1f KB, SPU2 blocks of 0x80: %d)' % (
    a.rws, b.dict_name, len(b.waves), b.adpcm_total(), b.adpcm_total() / 1024,
    sum((len(w.data) + 0x7f) // 0x80 for w in b.waves)))
if crw:
    print('CRW %s: declared %d, %d entries%s' % (crwp, crw.declared, len(crw.entries),
          '' if crw.declared == len(crw.entries) == len(b.waves) else '   *** COUNT MISMATCH ***'))
print('idx  rate   bytes   secs  3D  %-34s %s' % ('name (in RWS)', 'CRW category/attenuator'))
for i, w in enumerate(b.waves):
    c = ''
    if crw and i < len(crw.entries):
        e = crw.entries[i]
        cat = int(e['category'])
        c = '%s(%d) att=%s%s' % (CATEGORIES[cat] if 0 <= cat < len(CATEGORIES) else '?', cat, e['attenuator'],
                                 '' if os.path.basename(e['name']).lower() == os.path.basename(w.name).lower() else ' name=' + e['name'])
    print('%3d %6d %7d %6.3f  %d   %-34s %s' % (i, w.rate, len(w.data), w.seconds, w.positional, w.name, c))
    for p in w.check():
        print('     !! ' + p)
    if a.hex:
        print('     uuid %s  hdrlen 0x%x' % (w.uuid.hex(), len(w.header_bytes())))
