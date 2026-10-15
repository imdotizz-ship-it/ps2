# MotoGP 08 (SLUS-21811) hook trampolines. Assemble: clang --target=mips64el-unknown-none-gnuabin32 -march=mips3
# Game ABI = R5900 EABI: int args a0-a3,t0-t3 ($4-$11); float args packed f12..f19; ret v0 / f0;
# callee-saved s0-s7, fp (saved 128-bit with sq/lq), f20-f31 ; gp=0x605070 must stay intact.
# Our C (clang n32) differs for float args (positional) and saves s-regs only 64-bit, so every
# trampoline saves s0-s7/fp with sq and f20-f31 itself.
        .set noreorder
        .set noat
FOV_NVAL = 10
        .macro SQ rt, off
        .word 0x7c000000 | (29 << 21) | (\rt << 16) | (\off)
        .endm
        .macro LQ rt, off
        .word 0x78000000 | (29 << 21) | (\rt << 16) | (\off)
        .endm
        .macro SAVEALL
        addiu $sp, $sp, -0x100
        sd   $ra, 0xf0($sp)
        SQ 16, 0x00
        SQ 17, 0x10
        SQ 18, 0x20
        SQ 19, 0x30
        SQ 20, 0x40
        SQ 21, 0x50
        SQ 22, 0x60
        SQ 23, 0x70
        SQ 30, 0x80
        swc1 $f20, 0x90($sp)
        swc1 $f21, 0x94($sp)
        swc1 $f22, 0x98($sp)
        swc1 $f23, 0x9c($sp)
        swc1 $f24, 0xa0($sp)
        swc1 $f25, 0xa4($sp)
        swc1 $f26, 0xa8($sp)
        swc1 $f27, 0xac($sp)
        swc1 $f28, 0xb0($sp)
        swc1 $f29, 0xb4($sp)
        swc1 $f30, 0xb8($sp)
        swc1 $f31, 0xbc($sp)
        .endm
        .macro RESTALL
        LQ 16, 0x00
        LQ 17, 0x10
        LQ 18, 0x20
        LQ 19, 0x30
        LQ 20, 0x40
        LQ 21, 0x50
        LQ 22, 0x60
        LQ 23, 0x70
        LQ 30, 0x80
        lwc1 $f20, 0x90($sp)
        lwc1 $f21, 0x94($sp)
        lwc1 $f22, 0x98($sp)
        lwc1 $f23, 0x9c($sp)
        lwc1 $f24, 0xa0($sp)
        lwc1 $f25, 0xa4($sp)
        lwc1 $f26, 0xa8($sp)
        lwc1 $f27, 0xac($sp)
        lwc1 $f28, 0xb0($sp)
        lwc1 $f29, 0xb4($sp)
        lwc1 $f30, 0xb8($sp)
        lwc1 $f31, 0xbc($sp)
        ld   $ra, 0xf0($sp)
        .endm

        .section .text.hooks, "ax"
# H1: replaces 'jal 0x1f5840' (InputManager::Update(im=a0, dt=f12)) at 0x38eeac
        .globl hook_input_update
hook_input_update:
        SAVEALL
        sw   $a0, 0xc4($sp)
        swc1 $f12, 0xc0($sp)
        jal  0x1f5840               # original InputManager::Update
        nop
        lw   $a0, 0xc4($sp)
        lwc1 $f13, 0xc0($sp)        # n32: 2nd positional arg float -> $f13
        jal  on_input_updated       # void on_input_updated(void *im, float dt)
        nop
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100

# H2: replaces 'jal 0x212e90' (EndScene/ShowRaster(ctx=a0)) at 0x38f00c and 0x38f140
        .globl hook_end_scene
hook_end_scene:
        SAVEALL
        sw   $a0, 0xc4($sp)
        jal  on_draw                # void on_draw(void *ctx)  (debug text allowed here)
        nop
        lw   $a0, 0xc4($sp)
        RESTALL
        j    0x212e90               # tail-call original with original a0/ra
        addiu $sp, $sp, 0x100

# H3 (optional): replaces 'jal 0x1f2f80' (PadPS2::ReadPort(pad=a0, port=a1)) at 0x1f3cec.
# Runs right after the port's floats/raw bytes are refreshed: C may read raw bytes and zero
# the float button slots (pad+port*0x1b8+0x24..0x60) so the game ignores swallowed buttons.
        .globl hook_read_port
hook_read_port:
        SAVEALL
        sw   $a0, 0xc4($sp)
        sw   $a1, 0xc8($sp)
        jal  0x1f2f80
        nop
        lw   $a0, 0xc4($sp)
        jal  on_pad_read            # void on_pad_read(u8 *pad, int port)
        lw   $a1, 0xc8($sp)
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100

# game_printf(ctx, col, row, fmt, a, b, c, d): EABI = n32 for int-only args -> direct jump
        .globl game_printf
game_printf:
        j    0x212720
        nop

# ---------------------------------------------------------------- free camera ----
# H4: replaces 'jal 0x2cbe30' (RaceBase::Update(race=a0, dt=f12)) at 0x2c7b38 inside the race
# state's virtual Update 0x2c7a80 (vtable 0x5f1c50 slot +0x34, called from App::GameUpdate 0x38eed8
# -> 0x35ce40 -> *(0x5ffba4)). 0x2cbe30 steps the fixed-step sim (acc race+0x94 += dt*race+0x8c)
# and calls RaceCam::Update 0x4c7b00 -> 0x4c58a0 -> CML LookAt 0x20d010 (writes the RwFrame).
# fc_sim_dt() may return 0 to freeze the simulation; on_race_cam() then overrides the camera.
        .globl hook_race_cam
hook_race_cam:
        SAVEALL
        sw   $a0, 0xc4($sp)
        swc1 $f12, 0xc0($sp)
        jal  fc_sim_dt              # float fc_sim_dt(float dt)   (n32: f12 -> f0)
        nop
        lw   $a0, 0xc4($sp)
        jal  0x2cbe30               # original (only uses a0 and f12)
        mov.s $f12, $f0
        lw   $a0, 0xc4($sp)
        jal  on_race_cam            # void on_race_cam(u8 *race, float dt)  (n32: dt in $f13)
        lwc1 $f13, 0xc0($sp)
        jal  blur_update            # void blur_update(void): player speed -> blur strength
        nop
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100

# CML_Camera::LookAt(cml, const V3 *pos, const V3 *target), up=(0,-1,0) -> 0x20d010.
# Writes frame modelling matrix (frame+0x10..0x4c), orthonormalizes, RwFrameUpdateObjects.
        .globl game_lookat
game_lookat:
        j    0x20d2a0
        nop

# CML_Camera::SetFOV(cml, hdeg, vdeg) 0x20ee80: n32 passes floats positionally (f13,f14),
# game EABI packs them (f12,f13).  vw = (tan(h/2), tan(v/2)/cml->aspect) -> RwCameraSetViewWindow
        .globl game_setfov
game_setfov:
        mov.s $f12, $f13
        j    0x20ee80
        mov.s $f13, $f14

# H5: replaces 'jal 0x3141d0' (Vehicle::StartFall(veh=a0)) at 0x319274 and 0x319290.
# Caller's s1 = rider controller, f20 = impact speed (callee-saved, still intact here).
        .globl hook_fall
hook_fall:
        SAVEALL
        sw   $a0, 0xc4($sp)
        jal  0x3141d0
        nop
        lw   $a0, 0xc4($sp)
        move $a1, $s1
        jal  on_fall                # void on_fall(u8 *veh, u8 *ctl, float speed)  (n32: f14)
        mov.s $f14, $f20
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100

# H6/H7: replace the two 'jal 0x319020' (RiderCtl::OnCollision(ctl=a0, type=a1, forceFall=a2,
# otherFallen=a3, otherHuman=$8, f12=cos angle, f13=speed diff, f14=side speed)) inside the
# bike-bike collision 0x309500: 0x309f3c (ctl A, partner B) and 0x309fb8 (ctl B, partner A).
# bb_pre/bb_post bracket the call; any StartFall seen in between is a contact fall.
        .macro BBHOOK name, which
        .globl \name
\name:
        SAVEALL
        sw   $4, 0xc4($sp)
        sw   $5, 0xc8($sp)
        sw   $6, 0xcc($sp)
        sw   $7, 0xd0($sp)
        sw   $8, 0xd4($sp)
        swc1 $f12, 0xd8($sp)
        swc1 $f13, 0xdc($sp)
        swc1 $f14, 0xe0($sp)
        jal  bb_pre                 # void bb_pre(u8 *ctl, int which)
        addiu $5, $0, \which
        lw   $4, 0xc4($sp)
        lw   $5, 0xc8($sp)
        lw   $6, 0xcc($sp)
        lw   $7, 0xd0($sp)
        lw   $8, 0xd4($sp)
        lwc1 $f12, 0xd8($sp)
        lwc1 $f13, 0xdc($sp)
        jal  0x319020
        lwc1 $f14, 0xe0($sp)
        lw   $4, 0xc4($sp)
        jal  bb_post                # void bb_post(u8 *ctl, int which)
        addiu $5, $0, \which
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100
        .endm
        BBHOOK hook_bb1, 1
        BBHOOK hook_bb2, 2
# ---------------------------------------------------------------- motion blur ----
# H6: replaces 'jal 0x2880f0' (AfterEffects::Render(fx=a0, cam2d=a1, a2, a3)) in the race
# render 0x27d8d0 at 0x27e79c, 0x2806f8, 0x281630. After the game's own effects we blend the
# previous (front) frame over the frame being drawn: blur_post -> 0x294950(fx, cam, FIX).
        .globl hook_ae_render
hook_ae_render:
        SAVEALL
        sw   $a0, 0xc4($sp)
        sw   $a1, 0xc8($sp)
        jal  0x2880f0
        nop
        lw   $a0, 0xc4($sp)
        jal  blur_post              # void blur_post(void *fx, void *cam)
        lw   $a1, 0xc8($sp)
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100

# 0x294950(fx, cam2d, FIX): full-screen front->back blend, ALPHA (Cs-Cd)*FIX/128+Cd. Int args only.
        .globl game_blur
game_blur:
        j    0x294950
        nop

# ---------------------------------------------------------------- FOV option ----
# H6: replaces 'jal 0x20ee80' (CML_Camera::SetFOV(cml=a0, hdeg=f12, vdeg=f13)) at 0x4c57ac inside
# RaceCam::ApplyFov 0x4c5680 (runs when RC+0xe8 dirty / +0x111 set; delay slot 'mov.s f13,f12' kept).
# Setting = Options->VideoList byte +0xe (ex-"Standings", dead in game code): options = *(gp-0x52fc)
# (=*0x5ffd74), byte at +0x8e. index 1 (= old 'true' / DB default) -> +0; delta = (index-1)*5 degrees.
# Out-of-range index -> unchanged.  Clobbers only v0/v1/at/f0 (caller-saved at a jal).
        .globl hook_fov
hook_fov:
        lw    $2, -0x52fc($28)
        beqz  $2, 1f
        nop
        lbu   $2, 0x8e($2)
        sltiu $1, $2, FOV_NVAL
        beqz  $1, 1f
        addiu $2, $2, -1
        sll   $3, $2, 2
        addu  $2, $2, $3
        mtc1  $2, $f0
        nop
        cvt.s.w $f0, $f0
        add.s $f12, $f12, $f0
        add.s $f13, $f13, $f0
1:      j     0x20ee80
        nop

        .globl game_show
game_show:
        j    0x4f8aa0
        nop
        .globl game_fall_evt
game_fall_evt:
        j    0x414bd0
        nop

# H8: replaces 'jal 0x2f6060' (BikeGfx LOD/part visibility pass, a0 = BikeGfx) at 0x2f1a90.
# After it, bike_parts() re-hides the parts of bikes that lost them in a crash.
        .globl hook_bike_parts
hook_bike_parts:
        SAVEALL
        sw   $a0, 0xc4($sp)
        jal  bike_pre               # void bike_pre(u8 *B): before the LOD pass
        nop
        lw   $a0, 0xc4($sp)
        jal  0x2f6060
        nop
        jal  bike_parts             # void bike_parts(u8 *B)
        lw   $a0, 0xc4($sp)
        RESTALL
        jr   $ra
        addiu $sp, $sp, 0x100
