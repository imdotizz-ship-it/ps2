#!/usr/bin/env python3
"""Add / replace / remove / rename waves in a .RWS bank and keep its .CRW in sync.
All chunk sizes, the wave count and the fmt size fields are recomputed on write.

usage:
  rws_edit.py IN.RWS OUT.RWS rebuild                        (no change; round-trip test)
  rws_edit.py IN.RWS OUT.RWS add NAME FILE.wav [opts]       (append -> new index = old count)
  rws_edit.py IN.RWS OUT.RWS replace WAVE FILE.wav [opts]   (WAVE = index or name; keeps name/uuid)
  rws_edit.py IN.RWS OUT.RWS remove WAVE                    (shifts later indices! avoid in-game)
  rws_edit.py IN.RWS OUT.RWS rename WAVE NEWNAME
 FILE may also be FILE.adpcm (raw PS-ADPCM, use --rate).
opts:
  --rate HZ        resample to HZ (default: keep WAV rate; 22050 is a good choice for voice)
  --gain DB        gain before encoding     --normalize 0.9   peak-normalise to 0.9 FS
  --3d / --2d      positional flag of the new wave (default for add: --2d; replace keeps)
  --template N     wave whose header is cloned for 'add' (default 0)
  --crw IN.CRW     sidecar to update (default: IN.RWS with .CRW next to it)
  --crw-out F      where to write it (default: OUT.RWS with .CRW extension)
  --category N     CRW category for 'add' (default 1 = SFX)  --attenuator F (default 1.000000)
  --no-tail-frame  do not append the trailing silent frame (default appends one, like stock banks)
  --budget BYTES   refuse to write if the bank grows by more than BYTES of ADPCM
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rwslib import Bank, Crw, crw_path_for, wav_to_adpcm, Wave

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument('inp'); ap.add_argument('out'); ap.add_argument('op')
ap.add_argument('args', nargs='*')
ap.add_argument('--rate', type=int); ap.add_argument('--gain', type=float, default=0.0)
ap.add_argument('--normalize', type=float)
g = ap.add_mutually_exclusive_group(); g.add_argument('--3d', dest='pos', action='store_const', const=1)
g.add_argument('--2d', dest='pos', action='store_const', const=0)
ap.add_argument('--template', type=int, default=0)
ap.add_argument('--crw'); ap.add_argument('--crw-out'); ap.add_argument('--no-crw', action='store_true')
ap.add_argument('--category', type=int, default=1); ap.add_argument('--attenuator', default='1.000000')
ap.add_argument('--budget', type=int)
ap.add_argument('--no-tail-frame', action='store_true', help='do not append the trailing silent ADPCM frame')
a = ap.parse_args()

b = Bank.load(a.inp)
before = b.adpcm_total()
crwp = None if a.no_crw else (a.crw or crw_path_for(a.inp))
crw = Crw.load(crwp) if crwp else None
if crw and len(crw.entries) != len(b.waves):
    print('warning: CRW has %d entries, RWS %d waves' % (len(crw.entries), len(b.waves)))


def load_audio(path, rate):
    if path.lower().endswith('.adpcm'):
        if not rate:
            sys.exit('--rate required for raw .adpcm')
        d = open(path, 'rb').read()
        if len(d) % 16:
            sys.exit('raw ADPCM length must be a multiple of 16')
        return rate, d
    r, d, n = wav_to_adpcm(path, rate, a.gain, a.normalize, not a.no_tail_frame)
    print('encoded %s: %d samples @ %d Hz (%.3f s) -> %d bytes ADPCM' % (path, n, r, n / r, len(d)))
    return r, d


op, args = a.op, a.args
if op == 'rebuild':
    pass
elif op == 'add':
    name, path = args
    rate, data = load_audio(path, a.rate)
    w = b.new_wave(name, rate, data, positional=a.pos if a.pos is not None else 0, template=a.template)
    b.waves.append(w)
    if crw:
        crw.entries.append({'category': str(a.category), 'name': name, 'attenuator': a.attenuator})
    print('added "%s" as index %d' % (name, len(b.waves) - 1))
elif op == 'replace':
    key, path = args
    i = b.find(key)
    rate, data = load_audio(path, a.rate)
    w = b.waves[i]
    w.rate = rate
    w.set_data(data)
    if a.pos is not None:
        w.positional = a.pos
    print('replaced index %d "%s"' % (i, w.name))
elif op == 'remove':
    i = b.find(args[0])
    del b.waves[i]
    if crw:
        del crw.entries[i]
    print('removed index %d (later indices shift down!)' % i)
elif op == 'rename':
    i = b.find(args[0])
    b.waves[i].name = args[1]
    if crw:
        crw.entries[i]['name'] = args[1]
else:
    sys.exit('unknown op ' + op)

for i, w in enumerate(b.waves):
    for p in w.check():
        sys.exit('wave %d: %s' % (i, p))
grow = b.adpcm_total() - before
if a.budget is not None and grow > a.budget:
    sys.exit('ADPCM grows by %d bytes > budget %d; not written' % (grow, a.budget))
b.save(a.out)
Bank.load(a.out)  # re-parse check
print('wrote %s: %d waves, ADPCM %d -> %d bytes (%+d)' % (a.out, len(b.waves), before, b.adpcm_total(), grow))
if crw and op != 'rebuild' or (crw and a.crw_out):
    co = a.crw_out or os.path.splitext(a.out)[0] + '.CRW'
    crw.save(co)
    print('wrote %s: %d entries' % (co, len(crw.entries)))
