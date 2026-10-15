typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;
/* mailbox at a fixed address (segment start) so RAM dumps can read it */
struct mailbox { u32 magic, frames, buttons, sticks, padptr, lastdt_bits, draws, pad[1]; };
__attribute__((section(".mailbox"))) struct mailbox MB = { 0x4b50474d /*'MGPK'*/ };

extern int game_printf(void *ctx, int col, int row, const char *fmt, ...);

/* PS2 button bits (active-high after inversion), same layout as libpad: */
#define B_SELECT 0x0001
#define B_L3     0x0002
#define B_R3     0x0004
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
#define B_CIRCLE 0x2000
#define B_CROSS  0x4000
#define B_SQUARE 0x8000

void on_input_updated(void *im, float dt) {
    u8 *pad = *(u8 **)((u8 *)im + 0x1594);         /* PS2 libpad2 device */
    MB.frames++;
    MB.lastdt_bits = *(u32 *)&dt;
    if (!pad) return;
    MB.padptr = (u32)pad;
    if (!pad[8]) { MB.buttons = 0; return; }          /* port 0 not connected */
    MB.buttons = (~(pad[0x1214] | (pad[0x1215] << 8))) & 0xffff;
    MB.sticks = pad[0x1216] | (pad[0x1217] << 8) | (pad[0x1218] << 16) | ((u32)pad[0x1219] << 24); /* RX RY LX LY */
}

struct fcview { u32 magic, active, hold, latched, buttons, prev, alive, freeze; int lx, ly, rx, ry;
                float px, py, pz, yaw, pitch, fov; u32 frames; };
extern struct fcview FC;
extern int fc_ftoi(float f);

extern void rf_draw(void *ctx);
void on_draw(void *ctx) {
    MB.draws++;
    rf_draw(ctx);
    if (FC.active && FC.alive)
    {   /* <= 8 int args: n32 and EABI agree on $4..$11, avoid stack-passed varargs */
        game_printf(ctx, 2, 2, "FREECAM pos %d %d %d", fc_ftoi(FC.px), fc_ftoi(FC.py), fc_ftoi(FC.pz));
        game_printf(ctx, 2, 3, "fov %d %s", fc_ftoi(FC.fov), FC.freeze ? "frozen (TRI)" : "running (TRI)");
    }
}

/* on_pad_read (H3) now lives in freecam.c */
