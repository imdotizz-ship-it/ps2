/* Burnout 3 style takedown cam for MotoGP 08 (SLUS-21811).
 * When the player knocks a bot down (insult.c bb_post) the camera cuts to the falling rider and
 * slowly orbits it in slow motion for ~4 s while the player's bike is driven by the AI
 * (vehicle flags veh+0x12c: 0x1 human, 0x2 AI), then the race camera comes back.
 * Vehicle world matrix: veh+0x20 right, +0x30 up, +0x40 at, +0x50 position (+Y up).
 * Player vehicle: *(*(RC+0x18)+0x24), RC = *(u32*)0x84f770.
 * Debug build (-DTD_DEBUG): SELECT starts the cam on the nearest bot. */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8; typedef short s16;
typedef struct { float x, y, z; } V3;

#ifndef TD_FRAMES
#define TD_FRAMES 240           /* race updates the cut lasts (~4 s) */
#endif
#define TD_SCALE 0.3f

struct tdstate { u32 magic, active, timer, starts; u8 *victim, *player; u16 saved, pad; u32 prevsel; float ang;
                 u32 fight, fside, frames, fights; float scale, gate; u16 vsaved, pad2; };
__attribute__((section(".data"))) struct tdstate TD = { 0x4d434454 /* 'TDCM' */ };

extern void game_lookat(void *cml, V3 *pos, V3 *tgt);
extern float fc_sin(float), fc_cos(float);
static int td_flt(float a, float b) {
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}
static float fc_sqrt(float v) {         /* R5900 SQRT.S fd, ft: source in the ft field (MIPS uses fs) */
    register float in __asm__("$f1") = v;
    register float out __asm__("$f0");
    __asm__ volatile(".word 0x46010004" : "=f"(out) : "f"(in));
    return out;
}
static int okp(const void *p) { u32 v = (u32)p; return v >= 0x100000 && v < 0x2000000; }

static u8 *player_veh(void) {
    u8 *rc = *(u8 **)0x84f770;
    if (!okp(rc)) return 0;
    u8 *t = *(u8 **)(rc + 0x18);
    if (!okp(t)) return 0;
    u8 *v = *(u8 **)(t + 0x24);
    return okp(v) ? v : 0;
}

void td_start(u8 *victim) {
    if (TD.active || !okp(victim)) return;
    u8 *pv = player_veh();
    if (!pv || pv == victim) return;
    TD.victim = victim; TD.player = pv; TD.active = 1; TD.timer = 0; TD.starts++;
    TD.saved = *(u16 *)(pv + 0x12c);
    *(u16 *)(pv + 0x12c) = (TD.saved & ~0x1) | 0x2;          /* autopilot: AI drives the player bike */
    TD.ang = 0.9f;                                            /* start three-quarter front */
    TD.fight = 0; TD.frames = TD_FRAMES; TD.scale = TD_SCALE;
}

/* "fight" cut: the rider stays on his bike and shakes his fist at the one he knocked down.
 * RiderAnim R = ctl+0x520 (ctl = veh-0x1cc0). Setting its collision-gesture state makes the game
 * itself play rabbiaDX (27) / rabbiaSX (28): R+0x2e0 = 2 state, R+0x2e8/0x2ec side (1 DX, 2 SX),
 * R+0x2e4 timer. The game cancels gestures when |lean| > *(float*)0x63db34 (0.4); raised meanwhile. */
static void arm_gesture(u8 *veh, u32 side) {
    u8 *R = veh - 0x1cc0 + 0x520;
    if (*(u32 *)(R + 0x2e0) == 3) return;                      /* finish celebration */
    *(u32 *)(R + 0x2e0) = 2; *(u32 *)(R + 0x2e8) = side; *(u32 *)(R + 0x2ec) = side; *(float *)(R + 0x2e4) = 0.0f;
}
void td_fight(u8 *angry) {
    if (TD.active || !okp(angry)) return;
    td_start(angry);
    if (!TD.active) return;
    TD.fight = 1; TD.fside = 1; TD.fights++; TD.frames = 400; TD.scale = 0.35f;
    TD.gate = *(float *)0x63db34; *(float *)0x63db34 = 2.0f;
    TD.vsaved = *(u16 *)(angry + 0x12c);
    *(u16 *)(angry + 0x12c) |= 0x10;            /* "in focus": the rider LOD setter 0x34a9f0 keeps full LOD */
}
/* called right after the game's LOD pass for each bike: keep the fighting rider at full animation LOD */
void td_bike_lod(u8 *veh, u8 *B) { (void)veh; (void)B; }
static void td_stop(void) {
    if (TD.player) *(u16 *)(TD.player + 0x12c) = TD.saved;
    if (TD.fight) { *(float *)0x63db34 = TD.gate; if (TD.victim) *(u16 *)(TD.victim + 0x12c) = (*(u16 *)(TD.victim + 0x12c) & ~0x10) | (TD.vsaved & 0x10); TD.fight = 0; }
    TD.active = 0; TD.victim = TD.player = 0;
}
int td_active(void) { return TD.active; }

/* race update: slow motion while the cut runs */
float td_sim_dt(float dt) { return TD.active ? dt * TD.scale : dt; }

/* debug trigger + bookkeeping, once per race update */
/* nearest AI bike to the player: rider controllers are an array with stride 0x3200 */
static u8 *nearest_bot(u8 *anyctl) {
    u8 *pv = player_veh(); if (!pv || !okp(anyctl)) return 0;
    float *pp = (float *)(pv + 0x50), best = 1e9f; u8 *bv = 0;
    for (int k = -18; k <= 18; k++) {
        u8 *c = anyctl + k * 0x3200;
        if (!okp(c) || !okp(c + 0x430)) continue;
        u8 *v = *(u8 **)(c + 0x428);
        if (!okp(v) || v == pv || !(*(u16 *)(v + 0x12c) & 0x2)) continue;
        float *q = (float *)(v + 0x50), dx = q[0] - pp[0], dz = q[2] - pp[2], d2 = dx * dx + dz * dz;
        if (td_flt(d2, best)) { best = d2; bv = v; }
    }
    return bv;
}
void td_tick(u32 buttons, u8 *last_bot_ctl) {
    u32 sel = buttons & 0x0001;
#ifdef TD_DEBUG
    if (sel && !TD.prevsel && last_bot_ctl) td_fight(nearest_bot(last_bot_ctl));
#else
    (void)nearest_bot;
#endif
    TD.prevsel = sel;
}

/* camera, called from on_race_cam after the game camera; returns 1 if it took over */
int td_cam(void *cml) {
    if (!TD.active) return 0;
    if (++TD.timer >= TD.frames || !okp(TD.victim)) { td_stop(); return 0; }
    if (TD.fight) {
        u32 st = *(u32 *)(TD.victim - 0x1cc0 + 0x520 + 0x2e0);
        if (TD.timer == 3) arm_gesture(TD.victim, 1);              /* LOD forced since frame 1 */
        s16 cur = *(s16 *)(TD.victim - 0x1cc0 + 0x520 + 0x278);
        if (TD.fside == 1 && cur == 27) TD.fside = 2;                 /* gesture started */
        else if (TD.fside == 2 && (cur != 27 || st != 2)) {           /* gesture over: wrap up the cut */
            *(u32 *)(TD.victim - 0x1cc0 + 0x520 + 0x2e0) = 0;          /* no follow-up pose */
            TD.fside = 3; if (TD.frames > TD.timer + 25) TD.frames = TD.timer + 25;
        }
    }
    float *vp = (float *)(TD.victim + 0x50), *pp = (float *)(TD.player + 0x50);
    V3 p = { vp[0], vp[1], vp[2] };
    /* horizontal direction player -> victim, orbiting slowly around the victim */
    float dx = p.x - pp[0], dz = p.z - pp[2], l2 = dx * dx + dz * dz;
    if (!td_flt(0.01f, l2)) { dx = 1; dz = 0; l2 = 1; }
    float il = 1.0f / fc_sqrt(l2); dx *= il; dz *= il;
    float s = fc_sin(TD.ang), c = fc_cos(TD.ang);
    float rx = dx * c - dz * s, rz = dx * s + dz * c;
    float d = TD.fight ? 3.2f : 5.0f - TD.timer * 0.008f;     /* fight: close on the rider */
    V3 cam = { p.x - rx * d, p.y + 1.6f, p.z - rz * d };
    V3 tgt = { p.x, p.y + 0.4f, p.z };
    TD.ang += 0.01f;
    game_lookat(cml, &cam, &tgt);
    return 1;
}
