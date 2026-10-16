/* Rider insults + takedowns for MotoGP 08 (SLUS-21811).
 *
 * Engine facts (verified in code 0x309500 / 0x319020 / 0x3141d0 and in jerez_race.ram):
 *  - 0x309500 = PhysWorld::BikeBikeCollision(world, vehA, idxA, ...). For every contact pair it
 *    calls RiderCtl::OnCollision 0x319020(ctl, 4 = bike-bike, ...) twice in a row:
 *      0x309f3c: ctl of A (ctlA+0x40d = idx of B)   0x309fb8: ctl of B (ctlB+0x40d = idx of A)
 *    0x319020 decides the fall (DB_GAMECONFIG Damage thresholds, ctl+0x48 -> Damage struct) and
 *    calls Vehicle::StartFall 0x3141d0 (hooked by hook_fall -> on_fall) when the rider goes down.
 *  - hooks H6/H7 (hook_bb1/hook_bb2) wrap those two calls, so a fall seen inside the window is a
 *    fall caused by contact with the other bike of the pair.
 *  - RiderCtl (stride 0x3200 in the jerez dump): +0x3c -> pilot params P; *(char**)(P-0x28) =
 *    pilot key "RossiV" (surname + initial), *(int*)(P-8) = race number (valid for most riders).
 *    +0x428 -> Vehicle.  Vehicle +0x12c u16 flags (0x1 human, 0x2 AI), state (+0xd11>>1)&7 == 5 fallen.
 *  - RtCharset debug font = ASCII only, so the Portuguese text has no accents.
 */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8; typedef signed char s8;

#ifndef INS_COL
#define INS_COL 3              /* text box position (character cells) */
#endif
#ifndef INS_ROW
#define INS_ROW 19
#endif
#define BOX_W      44          /* inner width of the box */
#ifndef SHOW_FR
#ifdef FPS60
#define FR(n) ((n) * 2)                /* 60 fps: frame-counted durations last the same wall time */
#else
#define FR(n) (n)
#endif
#define SHOW_FR    FR(180)         /* ~3 s of draws */
#endif
#define COOLDOWN   FR(60)          /* draws before a new message may replace the current one */
#define TD_SLOW_FR 0           /* slow motion now comes from the takedown cam (td.c) */
#define TD_SCALE   0.3f

extern int game_printf(void *ctx, int col, int row, const char *fmt, ...);

struct insstate {
    u32 magic;                         /* 'INSL' */
    u32 seed, contacts, contact_falls, takedowns, shown;
    u8 *cur;                           /* ctl inside the 0x319020 window (0 = none) */
    u8 *a, *b; u32 a_fell, b_fell;     /* current pair */
    u32 show;                          /* draws left for the box */
    u32 age;                           /* draws since box started */
    u32 td_show, td_slow, alive;
    char who[32];                      /* "Rossi" */
    char num[8];                       /* "46" */
    char line[64];
};
__attribute__((section(".data"))) struct insstate INS = { 0x4c534e49, 0x9e3779b9 };

static const char *const LINES[] = {
    "Você me derrubou, seu maluco!",
    "%s, onde você tirou a carteira?!",
    "Isso não é boliche, %s!",
    "Vou te pegar na próxima volta, %s!",
    "Freia essa moto, seu barbeiro!",
    "%s, aprende a pilotar!",
    "Tá cego, %s?! Era a minha linha!",
    "Que lambança! Vou reclamar na direção!",
    "Seu doido! Quase me matou!",
    "Volta pro kart, %s!",
};
#define NLINES (sizeof(LINES) / sizeof(LINES[0]))
/* the player (human) was knocked down by a bot: the bot mocks him */
static const char *const TAUNTS[] = {
    "Sai da frente, %s!",
    "Desculpa, %s... mentira, não!",
    "Isso é MotoGP, %s, não passeio!",
    "Chão é lugar de piloto lento!",
};
#define NTAUNTS (sizeof(TAUNTS) / sizeof(TAUNTS[0]))

static u32 rnd(void) {
    INS.seed = INS.seed * 1103515245u + 12345u;
    return INS.seed >> 16;
}
static int okptr(const void *p) { u32 v = (u32)p; return v >= 0x100000 && v < 0x2000000; }

/* 2008 grid numbers by pilot key prefix (P-8 is not valid for every rider) */
static const struct { const char *k; int n; } NUMS[] = {
    {"Stoner", 1}, {"Pedrosa", 2}, {"Dovizioso", 4}, {"Edwards", 5}, {"Vermeulen", 7},
    {"West", 13}, {"DePuniet", 14}, {"DeAngelis", 15}, {"Hopkins", 21}, {"Elias", 24},
    {"Melandri", 33}, {"Rossi", 46}, {"Lorenzo", 48}, {"Guintoli", 50}, {"Toseland", 52},
    {"Nakano", 56}, {"Capirossi", 65}, {"Hayden", 69},
};
static int prefix(const char *s, const char *p) { while (*p) if (*s++ != *p++) return 0; return 1; }

static const char *pilot_key(u8 *ctl) {
    if (!okptr(ctl)) return 0;
    u8 *P = *(u8 **)(ctl + 0x3c);
    if (!okptr(P)) return 0;
    const char *k = *(const char **)(P - 0x28);
    return okptr(k) ? k : 0;
}
static int pilot_num(u8 *ctl, const char *k) {
    if (k) for (u32 i = 0; i < sizeof(NUMS) / sizeof(NUMS[0]); i++) if (prefix(k, NUMS[i].k)) return NUMS[i].n;
    u8 *P = *(u8 **)(ctl + 0x3c);
    int n = okptr(P) ? *(int *)(P - 8) : 0;
    return (n > 0 && n < 100) ? n : 0;
}
/* "RossiV" -> "Rossi", "DePunietR" -> "De Puniet" */
static void pilot_name(u8 *ctl, char *out, int max) {
    const char *k = pilot_key(ctl);
    int o = 0;
    if (!k) { const char *u = "Piloto"; while (*u && o < max - 1) out[o++] = *u++; out[o] = 0; return; }
    int n = 0; while (k[n] && n < 30) n++;
    if (n > 1 && k[n - 1] >= 'A' && k[n - 1] <= 'Z' && k[n - 2] >= 'a' && k[n - 2] <= 'z') n--;  /* initial */
    for (int i = 0; i < n && o < max - 1; i++) {
        char c = k[i];
        if (i > 0 && c >= 'A' && c <= 'Z' && k[i - 1] >= 'a' && k[i - 1] <= 'z' && o < max - 2) out[o++] = ' ';
        out[o++] = c;
    }
    out[o] = 0;
}

static int cat(char *d, int o, int max, const char *s) { while (*s && o < max - 1) d[o++] = *s++; d[o] = 0; return o; }
static int catnum(char *d, int o, int max, int n) {
    char t[8]; int k = 0;
    if (n <= 0) return o;
    while (n && k < 7) { t[k++] = '0' + n % 10; n /= 10; }
    while (k && o < max - 1) d[o++] = t[--k];
    d[o] = 0; return o;
}
static void fmt1(char *d, int max, const char *f, const char *arg) {   /* only %s */
    int o = 0;
    while (*f && o < max - 1) {
        if (f[0] == '%' && f[1] == 's') { o = cat(d, o, max, arg); f += 2; }
        else d[o++] = *f++;
    }
    d[o] = 0;
}

extern u8 *td_player(void);
static int is_human(u8 *ctl) {                 /* the player, also while the autopilot drives him */
    u8 *veh = *(u8 **)(ctl + 0x428);
    return okptr(veh) && ((*(u16 *)(veh + 0x12c) & 0x1) || veh == td_player());
}

/* speaker talks to target */
static void say(u8 *speaker, u8 *target, int taunt) {
    if (INS.show && INS.age < COOLDOWN) return;
    char sname[24], tname[24];
    pilot_name(speaker, sname, sizeof sname);
    pilot_name(target, tname, sizeof tname);
    int num = pilot_num(speaker, pilot_key(speaker));
    int o = 0;
    INS.who[0] = 0; INS.num[0] = 0;
    if (num) catnum(INS.num, 0, sizeof INS.num, num);
    cat(INS.who, o, sizeof INS.who, sname);
    int li = (int)(rnd() % NLINES);
    const char *f = taunt ? TAUNTS[rnd() % NTAUNTS] : LINES[li];
    { extern void voice_play(int); if (!taunt) voice_play(li); }
    fmt1(INS.line, sizeof INS.line, f, tname);
    INS.show = SHOW_FR; INS.age = 0; INS.shown++;
}

/* --- called from hook.S around the two 0x319020 calls of 0x309500 --- */
static u8 *last_bot;
u8 *ins_last_bot(void) { return last_bot; }
extern void td_start(u8 *veh);
static int bb_flt(float a, float b) {
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}
#ifndef TK_MIN
#define TK_MIN 4.0f             /* m/s of speed difference or side speed for a "real" hit */
#endif
#ifndef TK_CHANCE
#define TK_CHANCE 6             /* 1 in TK_CHANCE real hits knocks the slower rider down */
#endif
#define TK_COOLDOWN FR(360)         /* race updates between forced crashes */
struct tkstate { u32 magic, hist[6], hits, forced, cool; float maxd, maxs; };
__attribute__((section(".data"))) struct tkstate TK = { 0x4b444b54 /* 'TKDK' */ };
static u8 *tk_victim;
static int tk_forcing;                       /* a forced takedown is in progress (fake 100 m/s impact) */
int ins_forced(void) { return tk_forcing; }
static float fabs_(float x) { return bb_flt(x, 0.0f) ? -x : x; }
/* called before each of the two 0x319020 calls of a bike-bike contact; returns 1 to force the fall */
int bb_pre(u8 *ctl, int which, float diff, float side) {
    INS.cur = ctl;
    if (!is_human(ctl)) last_bot = ctl;
    if (which == 1) { INS.a = ctl; INS.a_fell = 0; INS.b = 0; INS.b_fell = 0; }
    else            { INS.b = ctl; INS.b_fell = 0; }
    float d = fabs_(diff), sd = fabs_(side), m = bb_flt(d, sd) ? sd : d;
    if (bb_flt(TK.maxd, d)) TK.maxd = d;
    if (bb_flt(TK.maxs, sd)) TK.maxs = sd;
    static const float B[6] = { 0.5f, 1, 2, 4, 8, 16 };
    for (int k = 0; k < 6; k++) if (bb_flt(B[k], m)) TK.hist[k]++;
    if (which == 1) {
        tk_victim = 0;
        if (TK.cool || !bb_flt(TK_MIN, m)) return 0;
        TK.hits++;
        if ((rnd() % TK_CHANCE) != 0) return 0;
        TK.cool = TK_COOLDOWN; TK.forced++;
        if (bb_flt(diff, 0.0f)) {                    /* A is the slower one: A goes down now */
            if (is_human(ctl)) { TK.cool = 0; TK.forced--; return 0; }   /* never the player */
            tk_forcing = 1; return 1;
        }
        tk_victim = (u8 *)2;                         /* B is the slower one: force B's call */
        return 0;
    }
    if (tk_victim == (u8 *)2) { tk_victim = 0; if (is_human(ctl)) { TK.cool = 0; TK.forced--; return 0; } tk_forcing = 1; return 1; }
    return 0;
}
void bb_post(u8 *ctl, int which) {
    (void)ctl;
    tk_forcing = 0;
    INS.cur = 0;
    if (which != 2 || !INS.a || !INS.b) return;
    INS.contacts++;
    u8 *victim = 0, *attacker = 0;
    if (INS.a_fell && !INS.b_fell) { victim = INS.a; attacker = INS.b; }
    else if (INS.b_fell && !INS.a_fell) { victim = INS.b; attacker = INS.a; }
    INS.a = INS.b = 0;
    if (!victim) return;                         /* nobody or both fell */
    INS.contact_falls++;
    { extern void gesture_mark(u8 *); if (!is_human(victim)) gesture_mark(*(u8 **)(victim + 0x428)); }
    if (is_human(attacker)) {                    /* player knocked a bot down: TAKEDOWN */
        INS.takedowns++;
#ifndef NO_TAKEDOWN
        INS.td_show = SHOW_FR; INS.td_slow = TD_SLOW_FR;
#endif
        td_start(*(u8 **)(victim + 0x428));
    }
    extern void td_fight(u8 *veh); extern int td_active(void);
    if (!is_human(victim) && !is_human(attacker) && !td_active() && (rnd() % 3) == 0) {
        td_fight(*(u8 **)(attacker + 0x428));            /* random fight cut: attacker shakes his fist */
        say(attacker, victim, 0);
    } else if (!is_human(victim)) say(victim, attacker, 0);     /* bot insults whoever hit him */
    else say(attacker, victim, 1);                       /* bot mocks the fallen player */
}

/* called from redflag.c on_fall (Vehicle::StartFall hook), ctl = rider controller */
void ins_on_fall(u8 *veh, u8 *ctl, float speed) {
    (void)veh; (void)speed;
#ifdef INS_DEBUG_ANYFALL
    if (!INS.cur && okptr(ctl) && is_human(ctl)) {           /* test build: own crash fakes a contact */
        u8 *o = ctl + 0x3200;
        if (!pilot_key(o)) o = ctl - 0x3200;
        if (pilot_key(o)) { say(o, ctl, 0); INS.takedowns++; INS.td_show = SHOW_FR; INS.td_slow = TD_SLOW_FR; }
        return;
    }
#endif
    if (!INS.cur || ctl != INS.cur) return;
    if (ctl == INS.a) INS.a_fell = 1;
    else if (ctl == INS.b) INS.b_fell = 1;
}

/* race update: slow motion after a takedown */
float ins_sim_dt(float dt) {
    INS.alive = 30;
    if (INS.td_slow) { INS.td_slow--; return dt * TD_SCALE; }
    return dt;
}
void ins_tick(void) {               /* per pad read: drop state when not racing */
    if (TK.cool) TK.cool--;
    INS.seed += 0x6d2b79f5u;
    if (INS.alive && --INS.alive == 0) { extern void gore_reset(void), gesture_reset(void), td_reset(void); gore_reset(); gesture_reset(); td_reset(); INS.show = INS.td_show = INS.td_slow = 0; INS.cur = INS.a = INS.b = 0; }
}

static int ins_flt(float a, float b) {   /* a < b, R5900-safe */
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}
extern void ui_pill_white(float, float, float, float, float), ui_pill_black(float, float, float, float, float),
            ui_pill_red(float, float, float, float, float);
extern void ui_text_row(float, float, float, const char *, float, const u8 *, float);
extern float ui_text_width(const char *, float);
/* drawn like the game's own HUD widgets (OVERTAKE / standings rows):
 *   [red pill: number] name          <- black pill row
 *   [white pill: the line, black text]
 * pass 0: pills, pass 1: text; counters advance once per frame (pass 1) */
void ins_draw(int pass) {
    static const u8 white[4] = { 255, 255, 255, 255 }, black[4] = { 16, 16, 18, 255 };
    if (!INS.alive) return;
#ifdef UI_DEBUG
    if (pass == 0 && !INS.show) { const char *s = "Lorenzo", *n = "48", *l = "Tá cego, Melandri?! Era a minha linha!";
        int i = 0; while ((INS.who[i] = s[i])) i++; i = 0; while ((INS.num[i] = n[i])) i++; i = 0; while ((INS.line[i] = l[i])) i++;
        INS.show = SHOW_FR; INS.age = 0; INS.takedowns = 3; }
#endif
    if (INS.show) {
        float a = INS.age < 10 ? INS.age / 10.0f : (INS.show < 20 ? INS.show / 20.0f : 1.0f);
        float sc = 0.6f, w = ui_text_width(INS.line, sc);
        if (ins_flt(440.0f, w)) { sc = sc * 440 / w; w = 440; }
        float nw = ui_text_width(INS.who, 0.62f); int hasnum = INS.num[0] != 0; float bw = hasnum ? 46.0f : 0.0f;
        float x0 = 320 - (w + 36) * 0.5f, y0 = 318;
        if (pass == 0) {
            ui_pill_black(x0, y0, x0 + bw + nw + 34, y0 + 24, a);
            if (hasnum) ui_pill_red(x0, y0, x0 + bw, y0 + 24, a);
            ui_pill_white(x0, y0 + 28, x0 + w + 36, y0 + 52, a);
        } else {
            if (hasnum) ui_text_row(x0 + (bw - ui_text_width(INS.num, 0.62f)) * 0.5f, y0, y0 + 24, INS.num, 0.62f, white, a);
            ui_text_row(x0 + bw + 14, y0, y0 + 24, INS.who, 0.62f, white, a);
            ui_text_row(x0 + 18, y0 + 28, y0 + 52, INS.line, sc, black, a);
            INS.show--; INS.age++;
        }
    }
    if (INS.td_show) {
        float a = INS.td_show < 30 ? INS.td_show / 30.0f : 1.0f;
        float big = INS.td_show > SHOW_FR - 10 ? 1.25f - (SHOW_FR - INS.td_show) * 0.025f : 1.0f;  /* punch-in */
        const char *t = "TAKEDOWN!";
        char b[24]; int o = 0; const char *p0 = "Takedowns  "; while (*p0) b[o++] = *p0++;
        int n = (int)INS.takedowns, k2 = 0; char d[8]; if (!n) d[k2++] = '0'; while (n) { d[k2++] = '0' + n % 10; n /= 10; }
        while (k2) b[o++] = d[--k2]; b[o] = 0;
        float w = ui_text_width(t, big), h = 30 * big, wb = ui_text_width(b, 0.6f);
        if (pass == 0) {
            ui_pill_red(320 - w / 2 - 22, 104, 320 + w / 2 + 22, 104 + h + 6, a);
            ui_pill_black(320 - wb / 2 - 18, 104 + h + 10, 320 + wb / 2 + 18, 104 + h + 34, a);
        } else {
            ui_text_row(320 - w / 2, 104, 104 + h + 6, t, big, white, a);
            ui_text_row(320 - wb / 2, 104 + h + 10, 104 + h + 34, b, 0.6f, white, a);
            INS.td_show--;
        }
    }
}
