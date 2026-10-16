#!/usr/bin/env python3
"""Build hook payload (hook.S + user.c) and produce a patched ELF copy.
usage: python3 build_hook.py [IN_ELF] [OUT_ELF]
 - payload is linked at SEG_VA (0x859f80, right after the libc 16KB heap) and added as PT_LOAD #2
 - game heap start is moved up by HEAP_SHIFT via 'lui v1,K' at 0x103fec (heap base = 0x859f80+K*0x10000)
 - call sites are redirected by rewriting their jal targets
"""
import os, sys, struct, subprocess, capstone
HERE = os.path.dirname(os.path.abspath(__file__))
IN = sys.argv[1] if len(sys.argv) > 1 else '/home/user/extracted/mgp08/SLUS_218.11'
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, 'out', 'SLUS_218.11')
SEG_VA = 0x859f80
CL = ['clang', '--target=mips64el-unknown-none-gnuabin32', '-march=mips3', '-mabi=n32', '-msingle-float',
      '-mno-abicalls', '-fno-pic', '-G0', '-Os', '-ffreestanding', '-nostdlib', '-fno-builtin',
      '-fomit-frame-pointer', '-fno-fast-math', '-ffp-contract=off', '-fno-jump-tables', '-mno-check-zero-division']
EXTRA = os.environ.get('RFDEF', '').split()
FPS60 = os.environ.get('FPS60', '1') != '0'
if FPS60: EXTRA = EXTRA + ['-DFPS60']
if os.environ.get('TAKEDOWN', '0') != '1': EXTRA = EXTRA + ['-DNO_TAKEDOWN']   # takedown cut / autopilot code off
B = os.path.join(HERE, 'build'); os.makedirs(B, exist_ok=True); os.makedirs(os.path.dirname(OUT), exist_ok=True)
def run(c): print(' '.join(c)); subprocess.check_call(c)
SRCS = ['hook.S', 'user.c', 'freecam.c', 'redflag.c', 'insult.c', 'blur.c', 'ui.c', 'td.c', 'gore.c', 'gesture.c', 'sound.c']
objs = []
for src in SRCS:
    o = B + '/' + src.rsplit('.', 1)[0] + '.o'
    run(CL + (EXTRA if src.endswith('.c') else []) + ['-c', os.path.join(HERE, src), '-o', o]); objs.append(o)
run(['ld.lld', '-m', 'elf32ltsmipn32', '-T', os.path.join(HERE, 'link.ld'), '--no-check-sections', '-o', B + '/payload.elf'] + objs)
run(['llvm-objcopy', '-O', 'binary', B + '/payload.elf', B + '/payload.bin'])
syms = {}
for l in subprocess.check_output(['llvm-nm', B + '/payload.elf']).decode().splitlines():
    p = l.split()
    if len(p) == 3: syms[p[2]] = int(p[0], 16)
# memsz incl. bss
hdr = subprocess.check_output(['llvm-objdump', '-h', B + '/payload.elf']).decode()
end = SEG_VA
for l in hdr.splitlines():
    p = l.split()
    if len(p) >= 4 and p[0].isdigit() and p[1].startswith('.'):
        sz, va = int(p[2], 16), int(p[3], 16)
        if va >= SEG_VA: end = max(end, va + sz)
binv = open(B + '/payload.bin', 'rb').read()
size = (max(len(binv), end - SEG_VA) + 0x7f) & ~0x7f
binv = binv + b'\0' * (size - len(binv))
# --- forbidden-opcode check (R5900 lacks these) ---
md = capstone.Cs(capstone.CS_ARCH_MIPS, capstone.CS_MODE_MIPS64 + capstone.CS_MODE_LITTLE_ENDIAN)
bad = ('sqrt.', 'rsqrt.', 'trunc.', 'c.lt.', 'c.le.', 'c.eq.', 'c.nge', 'round.', 'ceil.', 'floor.', '.d ', 'c.un', 'c.ueq', 'c.ult', 'c.ule', 'c.ngt', 'c.nge', 'c.ngl', 'c.seq', 'c.ngle', 'c.sf',
       'dmult', 'ddiv', 'll ', 'sc ', 'lld', 'scd', 'ldc1', 'sdc1', 'cvt.d', 'cvt.l', 'cvt.s.l', 'dmfc1', 'dmtc1', 'madd.s', 'msub.s')
text_end = syms.get('__text_end', SEG_VA + size)
probs = []
def each_insn():   # word by word: capstone.disasm() stops at the first undecodable word (sq/lq/mmi)
    for o in range(0, min(len(binv), text_end - SEG_VA) - 3, 4):
        l = list(md.disasm(binv[o:o + 4], SEG_VA + o))
        if l: yield l[0]
for ins in each_insn():
    s = ins.mnemonic + ' ' + ins.op_str
    if any(s.startswith(b) or (' ' + b) in (' ' + s) for b in bad) or ins.mnemonic.endswith('.d'):
        probs.append('%x %s' % (ins.address, s))
if probs:
    print('ERROR: R5900-incompatible instructions:\n  ' + '\n  '.join(probs)); sys.exit(1)
print('payload %d bytes at %x..%x' % (size, SEG_VA, SEG_VA + size))
heap_k = (size + 0xffff) >> 16                       # 64KB units reserved
# --- patch ELF ---
d = bytearray(open(IN, 'rb').read())
def va2off(va): return va - 0x100000 + 0x80
def rd(va): return struct.unpack_from('<I', d, va2off(va))[0]
def wr(va, w): struct.pack_into('<I', d, va2off(va), w)
def jal(t): return 0x0c000000 | ((t >> 2) & 0x3ffffff)
# heap shift: 0x103fec 'lui v1,0' -> 'lui v1,K'  (heap size = top - 0x855f80 - (K<<16 | 0x4000))
assert rd(0x103fec) & 0xffff0000 == 0x3c030000, hex(rd(0x103fec))
wr(0x103fec, 0x3c030000 | heap_k)
HOOKS = [(0x38eeac, 0x1f5840, 'hook_input_update'),
         (0x38f00c, 0x212e90, 'hook_end_scene'),
         (0x38f140, 0x212e90, 'hook_end_scene'),
         (0x1f3cec, 0x1f2f80, 'hook_read_port'),     # input filter (H3) -> freecam on_pad_read
         (0x2c7b38, 0x2cbe30, 'hook_race_cam'),      # race update (H4) -> fc_sim_dt / on_race_cam
         (0x319274, 0x3141d0, 'hook_fall'),
         (0x319290, 0x3141d0, 'hook_fall'),
         (0x309f3c, 0x319020, 'hook_bb1'),          # bike-bike contact, ctl of A
         (0x309fb8, 0x319020, 'hook_bb2'),          # bike-bike contact, ctl of B
         (0x27e79c, 0x2880f0, 'hook_ae_render'),     # motion blur: race render after-effects
         (0x2806f8, 0x2880f0, 'hook_ae_render'),
         (0x281630, 0x2880f0, 'hook_ae_render'),
         (0x4c57ac, 0x20ee80, 'hook_fov'),
         (0x2474e8, 0x20ee80, 'setfov_ws'),         # the other SetFOV callers: keep f28-f30 (16:9 patch)
         (0x3fea9c, 0x20ee80, 'setfov_ws'),
         (0x2f1a90, 0x2f6060, 'hook_bike_parts'),
         (0x33f2ec, 0x348a70, 'hook_fall_mode'),      # fallen rider gets up and gestures     # crash damage: hide broken windscreens           # FOV menu option -> race camera
         ]
for site, orig, name in HOOKS:
    assert rd(site) == jal(orig), 'site %x has %08x, expected jal %x' % (site, rd(site), orig)
    wr(site, jal(syms[name]))
# --- FOV menu option: Video Setup slot 10 ('Standings', VideoList byte +0xe, unused by game code)
# becomes an N-entry spinner whose value texts come from ZTX key 'Horiz_FOV' (existing rodata string
# at 0x5ced0a; key added to MENU\TEXT\*\COMMON.ZTX by make_fov_text.py).  Must match FOV_NVAL in hook.S.
import re; FOV_NVAL = int(re.search(r'^FOV_NVAL = (\d+)', open(os.path.join(HERE, 'hook.S')).read(), re.M).group(1))
def wrc(va, new, old):
    assert rd(va) == old, '%x: %08x != %08x' % (va, rd(va), old); wr(va, new)
assert d[va2off(0x5ced0a):va2off(0x5ced0a) + 10] == b'Horiz_FOV\0'
wrc(0x3cb418, 0x3c05005d, 0x3c05005e)            # lui   a1,0x5d
wrc(0x3cb420, 0x24a5ed0a, 0x24a5c782)            # addiu a1,a1,-0x12f6 -> 0x5ced0a 'Horiz_FOV' (was 'OFF_ON')
wrc(0x3cb424, 0x24060000 | FOV_NVAL, 0x24060002) # addiu a2,zero,N  (count; min 0, step 1, max N-1)
wrc(0x3cb428, 0x24080000, 0x24080001)            # addiu t0,zero,0  (clamp at the ends, no wrap)
wrc(0x3cafa8, 0x00000000, 0x0006302b)            # ZVideoOpt::Apply: 'sltu a2,zero,a2' -> nop (keep index)
# --- 16:9 widescreen for the 3D view: PCSX2 patch database SLUS-21811_73DA9F6F.pnach
# "Widescreen 16:9" by El_Patas (NTSC-U by Arapapa), inside CML_Camera::SetFOV 0x20ee80.
# The emulator still has to show the picture at 16:9 (gsaspectratio=16:9).
if os.environ.get('WIDESCREEN', '1') != '0':
    for va, new, old in [(0x20ee98, 0x4482e000, 0x44820000), (0x20eea8, 0x460ce002, 0x460c0002),
                         (0x20eeac, 0x4483e800, 0x44830800), (0x20eeb8, 0x4600eb02, 0x46000b02),
                         (0x20eebc, 0x00000000, 0xe7a00048), (0x20eec0, 0x3c013f40, 0x3c023f00),
                         (0x20eec4, 0x4481f000, 0x44820000), (0x20eec8, 0x461e0003, 0x3c033c8e),
                         (0x20eecc, 0xe7a00048, 0x3463fa35), (0x20eed4, 0x4614e002, 0x46140002),
                         (0x20eed8, 0x4600e846, 0x44830800)]:
        wrc(va, new, old)
# --- 60 fps (our own, agent-verified): lift the race VBlank cap (2->1) and run the fixed-step
# simulation at 60 Hz so motion and the race clock stay real-time (SetFrameRate(refresh>>1=30)->60).
# Main loop 0x38eb70 waits app->0x44 VBlanks; SetFrameRate at 0x2cecc0 sets g_FrameTime=1/fps,
# g_SubStep=1/(3fps).  Mod timers are frame-counted; -DFPS60 doubles them so they keep their timing.
if FPS60:
    wrc(0x38a474, 0x24030001, 0x24030002)        # race VBlank interval 2 -> 1 (addiu v1,zero,1)
    wrc(0x38f4a0, 0x0040202d, 0x00022042)        # SetFrameRate(refresh) instead of refresh>>1 -> 60 Hz step
# append segment at end of file (aligned) and fill phdr[1]
e_phoff = struct.unpack_from('<I', d, 0x1c)[0]
off = (len(d) + 0x7f) & ~0x7f
d += b'\0' * (off - len(d)) + binv
ph1 = e_phoff + 32
struct.pack_into('<8I', d, ph1, 1, off, SEG_VA, SEG_VA, size, size, 7, 0x10)
open(OUT, 'wb').write(d)
print('heap K=%d (base now %x), wrote %s (%d bytes)' % (heap_k, SEG_VA + (heap_k << 16), OUT, len(d)))
for k in sorted(syms, key=syms.get): print('  %08x %s' % (syms[k], k))
