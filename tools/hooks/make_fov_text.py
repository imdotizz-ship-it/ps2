#!/usr/bin/env python3
"""Build MENU.MIX with the 'Field of view' Video Setup texts.
usage: python3 make_fov_text.py [ORIG_MENU.MIX] [OUT_MENU.MIX]
 - COMMONMENU.ZTX: OPTIONS_VIDEO[10] / OPTIONS_VIDEO_DESC[10] ('Standings') -> 'Field of view' + description
 - COMMON.ZTX:     new key 'Horiz_FOV' with FOV_NVAL value strings (index 1 = default = +0 degrees)
for every language folder (root=UK English, USENGLISH, FRENCH, GERMAN, ITALIAN, SPANISH, USSPANISH, JAPANESE)."""
import os, re, sys, subprocess, tempfile
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import ztx
SRC = sys.argv[1] if len(sys.argv) > 1 else '/home/user/extracted/mgp08/MENU.MIX'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out', 'MENU.MIX')
MIX = '/home/user/ps2/tools/mix.py'
N = int(re.search(r'^FOV_NVAL = (\d+)', open(os.path.join(HERE, 'hook.S')).read(), re.M).group(1))
SLOT = 10
H_LABEL, H_DESC, H_FOV = ztx.khash('OPTIONS_VIDEO'), ztx.khash('OPTIONS_VIDEO_DESC'), ztx.khash('Horiz_FOV')
def values(normal):
    return ['%+d°' % ((i - 1) * 5) if i != 1 else '0°' for i in range(N)]
TXT = {  # folder: (label, description, word for the default value)
 '':          ('Field of view', 'Widens or narrows the race camera view (degrees added to the camera angle)', 'Normal'),
 'USENGLISH': ('Field of view', 'Widens or narrows the race camera view (degrees added to the camera angle)', 'Normal'),
 'FRENCH':    ('Champ de vision', 'Elargit ou resserre le champ de vision des caméras de course', 'Normal'),
 'GERMAN':    ('Sichtfeld', 'Vergrößert oder verkleinert das Sichtfeld der Rennkameras', 'Normal'),
 'ITALIAN':   ('Campo visivo', 'Allarga o restringe il campo visivo delle telecamere di gara', 'Normale'),
 'SPANISH':   ('Campo de visión', 'Amplía o reduce el campo de visión de las cámaras de carrera', 'Normal'),
 'USSPANISH': ('Campo de visión', 'Amplía o reduce el campo de visión de las cámaras de carrera', 'Normal'),
 'JAPANESE':  ('FOV', 'FOV', 'Normal'),
}
def main():
    tmp = tempfile.mkdtemp(prefix='fovtext_')
    names = ['MENU\\TEXT\\%s%s' % (l + '\\' if l else '', f) for l in TXT for f in ('COMMONMENU.ZTX', 'COMMON.ZTX')]
    subprocess.check_call(['python3', MIX, 'extract', SRC, tmp] + names)
    reps = []
    for lang, (label, desc, normal) in TXT.items():
        for fname in ('COMMONMENU.ZTX', 'COMMON.ZTX'):
            name = 'MENU\\TEXT\\%s%s' % (lang + '\\' if lang else '', fname)
            path = os.path.join(tmp, *name.split('\\'))
            e = ztx.parse(open(path, 'rb').read())
            if fname == 'COMMONMENU.ZTX':
                hit = 0
                for k in e:
                    if k[0] == H_LABEL: k[1][SLOT] = label; hit += 1
                    if k[0] == H_DESC: k[1][SLOT] = desc; hit += 1
                assert hit == 2, (name, hit)
            else:
                assert all(k[0] != H_FOV for k in e), 'already patched: ' + name
                e.append([H_FOV, values(normal)])
            outp = os.path.join(tmp, 'new', lang or 'ROOT', fname); os.makedirs(os.path.dirname(outp), exist_ok=True)
            open(outp, 'wb').write(ztx.build(e))
            reps.append('%s=%s' % (name, outp))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    subprocess.check_call(['python3', MIX, 'replace', SRC, OUT] + reps)
    print('wrote', OUT, '(%d files replaced)' % len(reps))
main()
