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
#define SHOW_FR    180         /* ~3 s of draws */
#define COOLDOWN   60          /* draws before a new message may replace the current one */
#define TD_SLOW_FR 70          /* race updates of slow motion after a takedown */
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
    char who[40];                      /* "#46 Rossi:" */
    char line[64];
};
__attribute__((section(".data"))) struct insstate INS = { 0x4c534e49, 0x9e3779b9 };

static const char *const LINES[] = {
    "Voce me derrubou, seu maluco!",
    "%s, onde voce tirou a carteira?!",
    "Isso nao e boliche, %s!",
    "Vou te pegar na proxima volta, %s!",
    "Freia essa moto, seu barbeiro!",
    "%s, aprende a pilotar!",
    "Ta cego, %s?! Era a minha linha!",
    "Que lambanca! Vou reclamar na direcao!",
    "Seu doido! Quase me matou!",
    "Volta pro kart, %s!",
};
#define NLINES (sizeof(LINES) / sizeof(LINES[0]))
/* the player (human) was knocked down by a bot: the bot mocks him */
static const char *const TAUNTS[] = {
    "Sai da frente, %s!",
    "Desculpa, %s... mentira, nao!",
    "Isso e MotoGP, %s, nao passeio!",
    "Chao e lugar de piloto lento!",
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

static int is_human(u8 *ctl) {
    u8 *veh = *(u8 **)(ctl + 0x428);
    return okptr(veh) && (*(u16 *)(veh + 0x12c) & 0x1);
}

/* speaker talks to target */
static void say(u8 *speaker, u8 *target, int taunt) {
    if (INS.show && INS.age < COOLDOWN) return;
    char sname[24], tname[24];
    pilot_name(speaker, sname, sizeof sname);
    pilot_name(target, tname, sizeof tname);
    int num = pilot_num(speaker, pilot_key(speaker));
    int o = 0;
    INS.who[0] = 0;
    if (num) { o = catnum(INS.who, o, sizeof INS.who, num); o = cat(INS.who, o, sizeof INS.who, " - "); }
    o = cat(INS.who, o, sizeof INS.who, sname);
    cat(INS.who, o, sizeof INS.who, ":");
    const char *f = taunt ? TAUNTS[rnd() % NTAUNTS] : LINES[rnd() % NLINES];
    fmt1(INS.line, sizeof INS.line, f, tname);
    INS.show = SHOW_FR; INS.age = 0; INS.shown++;
}

/* --- called from hook.S around the two 0x319020 calls of 0x309500 --- */
void bb_pre(u8 *ctl, int which) {
    INS.cur = ctl;
    if (which == 1) { INS.a = ctl; INS.a_fell = 0; INS.b = 0; INS.b_fell = 0; }
    else            { INS.b = ctl; INS.b_fell = 0; }
}
void bb_post(u8 *ctl, int which) {
    (void)ctl;
    INS.cur = 0;
    if (which != 2 || !INS.a || !INS.b) return;
    INS.contacts++;
    u8 *victim = 0, *attacker = 0;
    if (INS.a_fell && !INS.b_fell) { victim = INS.a; attacker = INS.b; }
    else if (INS.b_fell && !INS.a_fell) { victim = INS.b; attacker = INS.a; }
    INS.a = INS.b = 0;
    if (!victim) return;                         /* nobody or both fell */
    INS.contact_falls++;
    if (is_human(attacker)) {                    /* player knocked a bot down: TAKEDOWN */
        INS.takedowns++;
        INS.td_show = SHOW_FR; INS.td_slow = TD_SLOW_FR;
    }
    if (!is_human(victim)) say(victim, attacker, 0);     /* bot insults whoever hit him */
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
    INS.seed += 0x6d2b79f5u;
    if (INS.alive && --INS.alive == 0) { INS.show = INS.td_show = INS.td_slow = 0; INS.cur = INS.a = INS.b = 0; }
}

static void boxline(void *ctx, int row, const char *s, char edge, char fill) {
    char b[BOX_W + 4]; int o = 0;
    edge = ' ';                                  /* the race font has no + or | */
    b[o++] = edge;
    if (fill != ' ') { while (o < BOX_W + 1) b[o++] = fill; }
    else { b[o++] = ' '; while (*s && o < BOX_W) b[o++] = *s++; while (o < BOX_W + 1) b[o++] = ' '; }
    b[o++] = edge; b[o] = 0;
    game_printf(ctx, INS_COL, row, "%s", b);
}

void ins_draw(void *ctx) {
    if (!INS.alive) return;
    if (INS.show) {
        INS.show--; INS.age++;
        boxline(ctx, INS_ROW, "", '+', '-');
        boxline(ctx, INS_ROW + 1, INS.who, '|', ' ');
        boxline(ctx, INS_ROW + 2, INS.line, '|', ' ');
        boxline(ctx, INS_ROW + 3, "", '+', '-');
    }
    if (INS.td_show) {
        INS.td_show--;
        if (INS.td_show > SHOW_FR - 90 || ((INS.td_show >> 3) & 1))
            game_printf(ctx, 16, 5, "*** TAKEDOWN! ***");
        game_printf(ctx, 16, 6, "Takedowns: %d", (int)INS.takedowns);
    }
}
