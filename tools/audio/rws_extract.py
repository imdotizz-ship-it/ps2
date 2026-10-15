#!/usr/bin/env python3
"""Extract waves of a .RWS bank to 16-bit mono WAV (decoded PS-ADPCM) and/or raw ADPCM.

usage: rws_extract.py BANK.RWS OUTDIR [WAVE ...] [--raw] [--vag]
  WAVE = index or name (default: all). --raw also writes NAME.adpcm (exact 0x804 payload),
  --vag also writes a standard VAGp file (big-endian header) for other tools.
"""
import argparse, os, re, struct, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rwslib import Bank, adpcm_decode, write_wav

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('rws'); ap.add_argument('outdir'); ap.add_argument('waves', nargs='*')
ap.add_argument('--raw', action='store_true'); ap.add_argument('--vag', action='store_true')
a = ap.parse_args()
b = Bank.load(a.rws)
os.makedirs(a.outdir, exist_ok=True)
sel = [b.find(k) for k in a.waves] if a.waves else range(len(b.waves))
for i in sel:
    w = b.waves[i]
    base = '%02d_%s' % (i, re.sub(r'[^A-Za-z0-9_.-]+', '_', os.path.basename(w.name.replace('\\', '/'))).rsplit('.wav', 1)[0])
    p = os.path.join(a.outdir, base)
    write_wav(p + '.wav', w.rate, adpcm_decode(w.data))
    if a.raw:
        open(p + '.adpcm', 'wb').write(w.data)
    if a.vag:
        hdr = b'VAGp' + struct.pack('>IIII', 0x20, 0, len(w.data) + 16, w.rate) + bytes(12) + \
              w.name.encode('latin-1')[:16].ljust(16, b'\0')
        open(p + '.vag', 'wb').write(hdr + bytes(16) + w.data)
    print('%s.wav  %d Hz  %.3f s' % (p, w.rate, w.seconds))
