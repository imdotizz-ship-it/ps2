/* Fatal crash + red flag for MotoGP 08 (SLUS-21811).
 * Hook H5 replaces both 'jal 0x3141d0' (Vehicle::StartFall(veh)) in the fall decision 0x319020
 * (sites 0x319274 / 0x319290; there s1 = rider controller, f20 = impact speed).
 * After the original call, on_fall() may decide the crash was fatal (AI riders only, hard
 * impacts, random chance). Then: the rider stays on the ground (fall timer veh+0xd0e pinned),
 * is flagged retired (veh+0x12c |= 0x440), the race goes to slow motion for ~2 s and then
 * stops (sim dt = 0) under a red flag banner. START still opens the pause menu, where the
 * player restarts or quits the race. */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8; typedef short s16;

#ifndef RF_MIN_SPEED
#define RF_MIN_SPEED 38.0f      /* impact speed (m/s, ~135 km/h) needed for a fatal crash */
#endif
#ifndef RF_CHANCE
#define RF_CHANCE 10            /* 1 in RF_CHANCE hard AI crashes is fatal */
#endif
#ifndef RF_ENABLE
#define RF_ENABLE 1
#endif
#ifndef RF_AI_ONLY
#define RF_AI_ONLY 1
#endif

struct rfstate {
    u32 magic;                  /* 'RFLG' */
    u32 state;                  /* 0 none, 1 slow motion, 2 stopped */
    u32 timer, alive, seed, falls;
    u8 *veh;
    float last_speed, max_speed;
    u32 seen, gone; u16 oldflags, pad;
};
__attribute__((section(".data"))) struct rfstate RF = { 0x474c4652, 0, 0, 0, 0x1234567 };

static inline int rf_flt(float a, float b) {       /* a < b, R5900-safe */
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}

extern void ins_on_fall(u8 *veh, u8 *ctl, float speed);
void on_fall(u8 *veh, u8 *ctl, float speed) {
    if (!veh) return;
    ins_on_fall(veh, ctl, speed);
    { extern void gore_on_fall(u8 *, float, int); gore_on_fall(veh, speed, 0); }
    if (!RF_ENABLE) return;
    RF.falls++;
    RF.last_speed = speed;
    if (rf_flt(RF.max_speed, speed)) RF.max_speed = speed;
    RF.seed = RF.seed * 1103515245u + 12345u + RF.falls;
    if (RF.state) return;                                   /* one red flag at a time */
    { extern int ins_forced(void); if (ins_forced()) return; }   /* forced takedown: its impact speed is fake */
    u16 fl = *(u16 *)(veh + 0x12c);
    if (RF_AI_ONLY && !(fl & 0x2)) return;
    if (rf_flt(speed, RF_MIN_SPEED)) return;
    if (((RF.seed >> 16) % RF_CHANCE) != 0) return;
    { extern void gore_on_fall(u8 *, float, int); gore_on_fall(veh, speed, 1); }
    RF.veh = veh; RF.state = 1; RF.timer = 0; RF.seen = 0; RF.gone = 0;
    RF.oldflags = fl & 0x440;
}

/* called every race update with the frame dt; returns the dt the simulation should use */
float rf_sim_dt(float dt) {
    RF.alive = 30;
    if (!RF.state) return dt;
    RF.timer++;
    if (RF.veh) {
        u8 *v = RF.veh;
        int st = (v[0xd11] >> 1) & 7;                       /* 5 = fallen (set by StartFall) */
        if (st == 5) { RF.seen = 1; RF.gone = 0; }
        else if (RF.seen && ++RF.gone > 10) {               /* race restarted: rider reset */
            *(u16 *)(v + 0x12c) = (*(u16 *)(v + 0x12c) & ~0x440) | RF.oldflags;
            RF.state = 0; RF.veh = 0; RF.timer = 0;
            return dt;
        }
        *(s16 *)(v + 0xd0e) = 0x7fff;                       /* never gets back up */
        *(u16 *)(v + 0x12c) |= 0x440;                       /* retired */
    }
    if (RF.state == 1) {
        if (RF.timer > 150) RF.state = 2;                  /* ~2.5 s of slow motion */
        return dt * 0.25f;
    }
    return 0.0f;
}

/* called once per pad read: forget the red flag once the race is gone */
void rf_tick(void) {
    if (RF.alive) { if (--RF.alive == 0) { RF.state = 0; RF.veh = 0; RF.timer = 0; } }
}

extern int game_printf(void *ctx, int col, int row, const char *fmt, ...);
extern void ui_flag(float, float, u32, const u8 *, float);
extern void ui_pill_white(float, float, float, float, float), ui_pill_black(float, float, float, float, float),
            ui_pill_red(float, float, float, float, float);
extern void ui_text_row(float, float, float, const char *, float, const u8 *, float);
extern float ui_text_width(const char *, float);
/* game HUD style: white pill with the waving flag + red title pill, black rows below.
 * pass 0: pills + flag, pass 1: text */
void rf_draw(int pass) {
    static const u8 red[4] = { 210, 10, 10, 255 }, white[4] = { 255, 255, 255, 255 }, black[4] = { 16, 16, 18, 255 };
#ifdef UI_DEBUG
    if (pass == 0) { static u32 dbgt = 100; RF.timer = ++dbgt; }
    RF.state = 2; RF.alive = 1;
#endif
    if (!RF.state || !RF.alive) return;
    float a = RF.timer < 16 ? RF.timer / 16.0f : 1.0f;          /* fade in */
    float x0 = 170, x1 = 470, y0 = 150;
    float p = ((RF.timer >> 5) & 1) ? 1.0f : 0.6f;               /* slow pulse */
    if (pass == 0) {
        ui_pill_white(x0, y0, x0 + 64, y0 + 40, a);
        ui_flag(x0 + 18, y0 + 4, RF.timer, red, a * 0.9f);
        ui_pill_red(x0 + 70, y0, x1, y0 + 40, a);
        ui_pill_black(x0 + 70, y0 + 44, x1, y0 + 68, a);
        if (RF.state == 2) {
            ui_pill_black(x0 + 70, y0 + 72, x1, y0 + 96, a);
            ui_pill_white(x0 + 70, y0 + 100, x1, y0 + 124, a * p);
        }
        return;
    }
    ui_text_row(x0 + 88, y0, y0 + 40, "BANDEIRA VERMELHA", 0.78f, white, a);
    ui_text_row(x0 + 88, y0 + 44, y0 + 68, "Acidente fatal na pista", 0.6f, white, a);
    if (RF.state == 2) {
        ui_text_row(x0 + 88, y0 + 72, y0 + 96, "A corrida foi interrompida", 0.6f, white, a);
        ui_text_row(x0 + 88, y0 + 100, y0 + 124, "START  ·  Reiniciar a corrida", 0.6f, black, a * p);
    }
}
