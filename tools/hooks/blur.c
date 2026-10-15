/* Speed-dependent motion blur for MotoGP 08 (SLUS-21811).
 *
 * Engine facts (verified offline against SLUS_218.11 + jerez_race.ram):
 *  - GS double buffer (sceGsDBuff at 0x61b090): 640x448 PSMCT32, FB0 at FBP 0, FB1 at FBP 0x8c
 *    (byte 0x118000), Z24 at ZBP 0x118. Flip = 0x16de80 (frame counter gp 0x5ff2b8, then
 *    0x177460 re-points the two frame rasters):
 *      *(gp 0x5ff2b0) via 0x177b40 = FRONT raster (the frame on screen = previous frame)
 *      *(gp 0x5ff2b4) via 0x177b50 = BACK  raster (the frame being drawn)
 *  - 0x294950(fx, cam2d, FIX) is the game's own full-screen feedback pass: one textured
 *    sprite (PRIM 0x156) from FRONT into BACK with ALPHA = 0x64 | FIX<<32, i.e.
 *    Cd = Cd + (Cs - Cd) * FIX / 128 (packet built by 0x28afe0). The game only uses it with a
 *    constant 0x3c (fx+0x2c) or a fade (fx+0x9b). fx is not read by it.
 *  - The after-effects pass 0x2880f0(fx, cam2d, ?, ?) is called by the race render 0x27d8d0
 *    at 0x27e79c / 0x2806f8 / 0x281630. We hook those three calls and run 0x294950 after it,
 *    with FIX proportional to the player's speed.
 *  - Player speed: RC = *(0x84f770); target = *(RC+0x18); speed = target->vt[0x84]() =
 *    *(float*)(*(target+0x24) + 0xc80)   (m/s; same source as the NitroEffect).
 *
 * Everything below is tunable at run time through the BL struct (fixed address, see nm).
 */
typedef unsigned int u32; typedef unsigned char u8;

#ifndef BLUR_START
#define BLUR_START 25          /* m/s (90 km/h): blur starts                                 */
#endif
#ifndef BLUR_END
#define BLUR_END   75          /* m/s (270 km/h): full blur                                  */
#endif
#ifndef BLUR_MAX
#define BLUR_MAX   0x60        /* FIX at full speed: 96/128 = 75% of the previous frame        */
#endif
#ifndef BLUR_MIN
#define BLUR_MIN   0x00        /* FIX floor once above BLUR_START                            */
#endif

struct blurstate {
    u32 magic;                 /* 'BLUR' */
    u32 enable;                /* 0 = off                                                   */
    int start10, end10;        /* speed thresholds, tenths of m/s                           */
    int fmax, fmin;            /* FIX range                                                 */
    int alive;                 /* >0 while the race update runs (set there, aged per draw)  */
    int speed10;               /* last player speed, tenths of m/s                          */
    int target16, cur16;       /* FIX << 4 (target and smoothed)                            */
    int fix;                   /* FIX actually sent                                         */
    u32 updates, passes, lastcam;
};
__attribute__((section(".data"))) struct blurstate BL = {
    0x52554c42, 1, BLUR_START * 10, BLUR_END * 10, BLUR_MAX, BLUR_MIN, 0, 0, 0, 0, 0, 0, 0, 0 };

extern int fc_ftoi(float f);
extern void game_blur(void *fx, void *cam, int fix);   /* 0x294950 */

typedef float (*speedfn)(void *);

/* race update (H4, after RaceBase::Update + on_race_cam) */
void blur_update(void) {
    u8 *rc = *(u8 **)0x84f770;
    BL.updates++;
    if (!rc) return;
    u8 *t = *(u8 **)(rc + 0x18);
    if (!t || !*(u8 **)(t + 0x24)) return;
    u32 vt = *(u32 *)t;
    if (vt < 0x5d0000 || vt > 0x605000) return;
    speedfn fn = *(speedfn *)(vt + 0x84);
    if ((u32)fn < 0x100000 || (u32)fn > 0x500000) return;
    int s = fc_ftoi(fn(t) * 10.0f);
    if (s < 0) s = -s;
    BL.speed10 = s;
    int tg = 0, span = BL.end10 - BL.start10;
    if (span < 1) span = 1;
    if (s > BL.start10) {
        int k = s - BL.start10;
        if (k > span) k = span;
        tg = BL.fmin + (BL.fmax - BL.fmin) * k / span;
    }
    BL.target16 = tg << 4;
    BL.cur16 += (BL.target16 - BL.cur16) / 6;            /* ~0.1 s smoothing at 60 Hz */
    BL.alive = 4;
}

/* once per frame from the EndScene hook */
void blur_tick(void) {
    if (BL.alive > 0) BL.alive--;
    if (!BL.alive) { BL.cur16 = 0; BL.fix = 0; }
}

/* right after the after-effects pass of the race render (3 call sites) */
void blur_post(void *fx, void *cam) {
    int f = BL.cur16 >> 4;
    if (f > 0x80) f = 0x80;
    BL.fix = f;
    BL.lastcam = (u32)cam;
    if (!BL.enable || BL.alive <= 0 || !cam || f < 2) return;
    BL.passes++;
    game_blur(fx, cam, f);
}
