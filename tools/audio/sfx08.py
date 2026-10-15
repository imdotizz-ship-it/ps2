#!/usr/bin/env python3
r"""Builds the modded SFX.MIX of MotoGP 08 (PS2).

  sfx08.py SFX.MIX OUT_DIR        -> OUT_DIR/SFX.MIX

  SFX\COMMON.RWS/.CRW      + Insult00..09 (voice/t0..t9.wav, Piper pt-br voice) at indices 11..20,
                           11025 Hz, played by the hook code (sound.c, voice_play)
  SFX\ENVIRONMENT.RWS/.CRW crowd louder: soft limiter (+~4 dB loudness, peaks kept below full scale),
                           re-encoded at 16 kHz (frees ~108 KB of SPU2 RAM for the insults),
                           CRW attenuator 0.794328 (-2 dB) -> 1.0
  SFX\*.ENS                fFreq 28000 -> 16000 (the crowd samples' new rate); emitters unchanged
  SFX\AUDIOCONFIG.BML/.XML ENVIRONMENT master volume (fValueLock) 0.85 -> 1.0
"""
import glob, os, re, subprocess, sys, wave
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import bml  # noqa: E402

MIX = os.path.join(os.path.dirname(HERE), 'mix.py')
EDIT = os.path.join(HERE, 'rws_edit.py')
CROWD = ['Normal', 'Winner', 'Cheers']


def run(*a):
    subprocess.run([sys.executable] + [str(x) for x in a], check=True, stdout=subprocess.DEVNULL)


def louder(src, dst, k=1.8):
    w = wave.open(src)
    p = w.getparams()
    a = np.frombuffer(w.readframes(w.getnframes()), np.int16).astype(float) / 32768
    y = 0.97 * np.tanh(k * a) / np.tanh(k)
    o = wave.open(dst, 'wb')
    o.setparams(p)
    o.writeframes((y * 32767).astype(np.int16).tobytes())
    o.close()


def main():
    src, out = sys.argv[1], sys.argv[2]
    w = os.path.join(out, 'work')
    os.makedirs(w, exist_ok=True)
    run(MIX, 'extract', src, w, r'SFX\COMMON.*', r'SFX\ENVIRONMENT.*', r'SFX\*.ENS', r'SFX\AUDIOCONFIG.*')
    s = os.path.join(w, 'SFX')
    files = {}

    cur = os.path.join(s, 'COMMON.RWS')
    for i in range(10):
        nxt = os.path.join(w, 'c%d.RWS' % i)
        run(EDIT, cur, nxt, 'add', 'Insult%02d' % i, os.path.join(HERE, 'voice', 't%d.wav' % i),
            '--rate', 11025, '--normalize', 0.9, '--2d', '--category', 1)
        cur = nxt
    files['COMMON.RWS'], files['COMMON.CRW'] = cur, cur[:-3] + 'CRW'

    wavs = os.path.join(w, 'envwav')
    run(os.path.join(HERE, 'rws_extract.py'), os.path.join(s, 'ENVIRONMENT.RWS'), wavs)
    cur = os.path.join(s, 'ENVIRONMENT.RWS')
    for i, n in enumerate(CROWD):
        wav = glob.glob(os.path.join(wavs, '*%s*.wav' % n))[0]
        loud = os.path.join(w, 'loud%d.wav' % i)
        louder(wav, loud)
        nxt = os.path.join(w, 'e%d.RWS' % i)
        run(EDIT, cur, nxt, 'replace', i, loud, '--rate', 16000)
        cur = nxt
    crw = open(cur[:-3] + 'CRW', 'rb').read().replace(b'0.794328', b'1.000000')
    open(cur[:-3] + 'CRW', 'wb').write(crw)
    files['ENVIRONMENT.RWS'], files['ENVIRONMENT.CRW'] = cur, cur[:-3] + 'CRW'

    for f in glob.glob(os.path.join(s, '*.ENS')):
        t = open(f, 'rb').read().decode('latin1')
        t = re.sub(r'(fFreq\s+)[\d.]+', lambda m: m.group(1) + '16000.000000', t)
        open(f, 'wb').write(t.encode('latin1'))
        files[os.path.basename(f)] = f

    f = os.path.join(s, 'AUDIOCONFIG.BML')
    root = bml.load(open(f, 'rb').read())
    for mv in bml.elements(root, 'MasterVolume'):
        if bml.get_text(mv, 'szName') == 'ENVIRONMENT':
            bml.set_text(mv, 'fValueLock', '1.0')
    open(f, 'wb').write(bml.save(root))
    files['AUDIOCONFIG.BML'] = f
    f = os.path.join(s, 'AUDIOCONFIG.XML')
    x = open(f, newline='').read()
    x = re.sub(r'(<szName>ENVIRONMENT</szName>\s*<fValueLock>)[\d.]+', r'\g<1>1.0', x)
    open(f, 'w', newline='').write(x)
    files['AUDIOCONFIG.XML'] = f

    run(MIX, 'replace', src, os.path.join(out, 'SFX.MIX'), *['SFX\\%s=%s' % kv for kv in sorted(files.items())])
    print('wrote', os.path.join(out, 'SFX.MIX'))


if __name__ == '__main__':
    main()
