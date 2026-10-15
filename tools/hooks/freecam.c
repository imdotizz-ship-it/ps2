/* Free camera for MotoGP 08 (SLUS-21811), built with the patch-infra kit.
 *
 * Hold L1+R1 (~0.33 s) during a race to toggle.  While active:
 *   left stick  = move forward/back + strafe      right stick = look (yaw / pitch)
 *   R2 / L2     = up / down (world Y)              SQUARE = fast, CROSS = slow
 *   D-pad up/down = FOV narrower / wider           D-pad left = reset FOV to the game's
 *   TRIANGLE    = toggle world freeze (default: frozen)
 *   START still reaches the game (pause); every other pad-1 input is hidden from the game.
 *
 * Engine facts (verified against code + jerez_race.ram):
 *   RC   = *(u32*)0x84f770        race camera controller, player 1 (pool slot 0, made by 0x4c6580)
 *          RC+0x0c CML*, RC+0xcc cam pos, RC+0xd8 target, RC+0x98 -up, RC+0xe4 fov (rad),
 *          RC+0xe8 fov-dirty byte (0x4c5680 re-applies the game FOV when set)
 *   CML  (game camera wrapper)   +0x08 RwFrame*, +0x18 RwCamera*, +0x20 aspect (640/448)
 *   RwCamera: +0x04 frame, +0x68 viewWindow{x,y}, +0x70 recip, +0x80 near, +0x84 far
 *   RwFrame : +0x10 modelling matrix (right,up,at,pos @ +0x10,+0x20,+0x30,+0x40), LTM @ +0x50
 *   frame "right" points to SCREEN LEFT (RW convention; viewMatrix x row = -right/vw.x*.5+.5*at)
 */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;
typedef struct { float x, y, z; } V3;

#define B_START  0x0008
#define B_UP     0x0010
#define B_RIGHT  0x0020
#define B_DOWN   0x0040
#define B_LEFT   0x0080
#define B_L2     0x0100
#define B_R2     0x0200
#define B_L1     0x0400
#define B_R1     0x0800
#define B_TRI    0x1000
#define B_CROSS  0x4000
#define B_SQUARE 0x8000

#define RC_SLOT0     0x84f770
#define HOLD_FRAMES  20          /* L1+R1 hold time (pad reads, ~60/s) */
#define DEAD         20          /* stick dead zone (raw units of 128) */
#define PI 3.14159265f

extern void rf_tick(void);
extern void ins_tick(void);
extern void game_lookat(void *cml, V3 *pos, V3 *tgt);
extern void game_setfov(void *cml, float h, float v);

struct fcstate {
    u32 magic;                 /* 'FCAM' – find it in RAM dumps */
    u32 active, hold, latched, buttons, prev, alive, freeze;
    int lx, ly, rx, ry;        /* -128..127, dead-zoned */
    V3 pos; float yaw, pitch, fov;
    u32 frames;
};
__attribute__((section(".data"))) struct fcstate FC = { 0x4d414346, 0, 0, 0, 0, 0, 0, 1 };

/* R5900 FPU only implements C.F/C.EQ/C.LT/C.LE (= MIPS c.f/c.eq/c.olt/c.ole). clang emits the
   unordered forms c.ult/c.ule for many C comparisons; PCSX2 treats them as no-ops, leaving FCC stale
   (that made wrap() spin forever = the "frozen" game in the first test). So every float compare
   goes through these inline-asm helpers. */
static inline int flt(float a, float b) {        /* a < b */
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}
#define fgt(a, b) flt((b), (a))
static float fabsf_(float x) { return flt(x, 0.f) ? -x : x; }
static float fclamp(float x, float lo, float hi) { if (flt(x, lo)) return lo; if (fgt(x, hi)) return hi; return x; }
static float wrap(float a) {                      /* bounded: no loops */
    if (fgt(a, PI)) a -= 2 * PI;
    if (fgt(a, PI)) a -= 2 * PI;
    if (flt(a, -PI)) a += 2 * PI;
    if (flt(a, -PI)) a += 2 * PI;
    return fclamp(a, -PI, PI);
}
static float sin_(float x) {
    x = wrap(x);
    if (fgt(x, PI / 2)) x = PI - x; else if (flt(x, -PI / 2)) x = -PI - x;      /* |x| <= pi/2 */
    float x2 = x * x;
    return x * (1 - x2 / 6 * (1 - x2 / 20 * (1 - x2 / 42 * (1 - x2 / 72))));
}
static float cos_(float x) { return sin_(x + PI / 2); }
float fc_sin(float x) { return sin_(x); }
float fc_cos(float x) { return cos_(x); }
static float atan_(float z) {          /* |z| <= 1 */
    float z2 = z * z;
    return z * (0.9998660f + z2 * (-0.3302995f + z2 * (0.1801410f + z2 * (-0.0851330f + z2 * 0.0208351f))));
}
static float atan2_(float y, float x) {
    float ax = fabsf_(x), ay = fabsf_(y);
    if (!fgt(ax, 1e-12f) && !fgt(ay, 1e-12f)) return 0;
    if (!flt(ax, ay)) { float a = atan_(y / x); return fgt(x, 0.f) ? a : (flt(y, 0.f) ? a - PI : a + PI); }
    float a = atan_(x / y); return fgt(y, 0.f) ? PI / 2 - a : -PI / 2 - a;
}
static float sqrt_(float v) {         /* R5900 SQRT.S fd, ft: source in the ft field (MIPS uses fs) */
    register float in __asm__("$f1") = v;
    register float out __asm__("$f0");
    __asm__ volatile(".word 0x46010004" : "=f"(out) : "f"(in));
    return out;
}
static int axis(u8 v) { int a = (int)v - 128; if (a > -DEAD && a < DEAD) return 0; return a; }
int fc_ftoi(float f) { int i; __asm__("cvt.w.s %1,%1\n\tmfc1 %0,%1" : "=r"(i), "+f"(f)); return i; }

/* kit H3 (0x1f3cec): right after PadPS2::ReadPort(pad, port).
   raw libpad bytes at pad+0x1214 (+port*0x12?): [0..1] buttons active-low, [2]RX [3]RY [4]LX [5]LY.
   Float slots written by ReadPort for port 0: 0x0c-0x1c axes, 0x24-0x60 buttons (START = 0x44,
   L1 = 0x5c, R1 = 0x60), 0x74-0xb0 pressure/derived, 0xb4-0xd8 half-axes. */
void on_pad_read(u8 *pad, int port) {
    if (port != 0) return;
    rf_tick();
    ins_tick();
    u8 *raw = pad + 0x1214;
    u32 b = (~(raw[0] | (raw[1] << 8))) & 0xffff;
    FC.prev = FC.buttons;
    FC.buttons = b;
    FC.rx = axis(raw[2]); FC.ry = axis(raw[3]); FC.lx = axis(raw[4]); FC.ly = axis(raw[5]);
    if (FC.alive) FC.alive--;                       /* >0 only while the race camera is ticking */
    u32 *f = (u32 *)pad;
    if ((b & (B_L1 | B_R1)) == (B_L1 | B_R1)) {
        f[0x5c >> 2] = 0; f[0x60 >> 2] = 0;         /* never let the combo reach the game */
        if (++FC.hold >= HOLD_FRAMES && !FC.latched && FC.alive) {
            FC.active ^= 1; FC.latched = 1; FC.frames = 0;
        }
    } else { FC.hold = 0; FC.latched = 0; }
    if (FC.active && FC.alive) {                    /* outside the race (menus/pause) never swallow input */
        if ((b & ~FC.prev) & B_TRI) FC.freeze ^= 1;
        for (int o = 0x0c; o <= 0xd8; o += 4) {
            if (o == 0x44 || o == 0x14 || o == 0x20 || o == 0xc4 || o == 0xc8) continue; /* keep START; skip unwritten */
            if (o > 0x60 && o < 0x74) continue;
            f[o >> 2] = 0;
        }
    }
}

/* H4 pre-step: dt fed to RaceBase::Update. 0 = no fixed sim steps (bikes, AI, timers, game cam frozen) */
extern float rf_sim_dt(float dt);
extern float ins_sim_dt(float dt);
extern float td_sim_dt(float); extern int td_cam(void *); extern void td_tick(u32, u8 *); extern u8 *ins_last_bot(void);
float fc_sim_dt(float dt) { td_tick(FC.buttons, ins_last_bot()); dt = td_sim_dt(ins_sim_dt(rf_sim_dt(dt))); if (FC.active && FC.freeze) dt = 0.0f; { extern void gore_update(float); gore_update(dt); } return dt; }

/* H4 post-step: game camera already written for this frame; render happens after App::GameUpdate
   reaches BeginScene (0x38ef50), so whatever we write here is what gets drawn. */
void on_race_cam(u8 *race, float dt) {
    (void)race;
    u8 *rc = *(u8 **)RC_SLOT0;
    if (!rc) return;
    u8 *cml = *(u8 **)(rc + 0x0c);
    if (!cml) return;
    u8 *cam = *(u8 **)(cml + 0x18);
    u8 *frm = *(u8 **)(cml + 0x08);
    if (!cam || !frm || cam[0] != 4) return;       /* RwCamera object type 4 */
    FC.alive = 30;
    if (!FC.active && td_cam(cml)) return;
    if (!FC.active) {
        if (FC.frames) { *(u8 *)(rc + 0xe8) = 1; FC.frames = 0; }   /* give the game its FOV back */
        return;
    }
    if (FC.frames++ == 0) {                          /* start from the current game view */
        float *m = (float *)(frm + 0x10);            /* right(0..2) up(4..6) at(8..10) pos(12..14) */
        FC.pos.x = m[12]; FC.pos.y = m[13]; FC.pos.z = m[14];
        FC.yaw = atan2_(m[8], m[10]);
        FC.pitch = atan2_(m[9], sqrt_(m[8] * m[8] + m[10] * m[10]));
        FC.fov = *(float *)(rc + 0xe4) * 57.29578f;
        if (flt(FC.fov, 10.f) || fgt(FC.fov, 150.f)) FC.fov = 63.5f;
    }
    if (!fgt(dt, 0.f) || fgt(dt, 0.1f)) dt = 1.0f / 60;
    u32 b = FC.buttons;
    float spd = 15.f, rot = 1.8f;                    /* m/s, rad/s */
    if (b & B_SQUARE) spd *= 4;
    if (b & B_CROSS) spd *= 0.2f;
    /* frame right = screen left, so turning/strafing to screen-right uses -right */
    FC.yaw = wrap(FC.yaw - FC.rx / 128.f * rot * dt);
    FC.pitch -= FC.ry / 128.f * rot * dt;            /* stick up (ry<0) = look up */
    FC.pitch = fclamp(FC.pitch, -1.5f, 1.5f);
    float cp = cos_(FC.pitch), sp = sin_(FC.pitch), cy = cos_(FC.yaw), sy = sin_(FC.yaw);
    V3 fwd = { sy * cp, sp, cy * cp };
    V3 sright = { -cy, 0, sy };                      /* screen-right, horizontal */
    float mv = -FC.ly / 128.f * spd * dt, st = FC.lx / 128.f * spd * dt;
    float up = (((b & B_R2) ? 1.f : 0.f) - ((b & B_L2) ? 1.f : 0.f)) * spd * dt;
    FC.pos.x += fwd.x * mv + sright.x * st;
    FC.pos.y += fwd.y * mv + up;
    FC.pos.z += fwd.z * mv + sright.z * st;
    if (b & B_UP) FC.fov -= 30 * dt;
    if (b & B_DOWN) FC.fov += 30 * dt;
    if (b & B_LEFT) FC.fov = *(float *)(rc + 0xe4) * 57.29578f;
    FC.fov = fclamp(FC.fov, 10.f, 120.f);
    V3 tgt = { FC.pos.x + fwd.x, FC.pos.y + fwd.y, FC.pos.z + fwd.z };
    game_lookat(cml, &FC.pos, &tgt);
    game_setfov(cml, FC.fov, FC.fov);
}
