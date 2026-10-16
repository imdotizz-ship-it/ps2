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

extern void rf_draw(int pass);
extern void ins_draw(int pass);
extern void blur_tick(void);
extern int ui_begin(void);
extern void ui_end_solid(void), ui_end_text(void);
extern void ui_pill_white(float, float, float, float, float), ui_pill_black(float, float, float, float, float);
extern void ui_text_row(float, float, float, const char *, float, const u8 *, float);
static void fc_draw(int pass) {
    static const u8 white[4] = { 255, 255, 255, 255 }, black[4] = { 16, 16, 18, 255 };
    if (!(FC.active && FC.alive)) return;
    if (pass == 0) { ui_pill_white(24, 64, 204, 88, 1.0f); ui_pill_black(24, 92, 204, 116, 1.0f); return; }
    char b[48]; int o = 0, n = fc_ftoi(FC.fov), k = 0; char d[8];
    const char *p = "FOV "; while (*p) b[o++] = *p++;
    while (n && k < 7) { d[k++] = '0' + n % 10; n /= 10; } while (k) b[o++] = d[--k];
    p = FC.freeze ? "  ·  pausado" : "  ·  rodando"; while (*p) b[o++] = *p++; b[o] = 0;
    ui_text_row(40, 64, 88, "CÂMERA LIVRE", 0.6f, black, 1.0f);
    ui_text_row(40, 92, 116, b, 0.55f, white, 1.0f);
}
void on_draw(void *ctx) {
    (void)ctx;
    MB.draws++;
    blur_tick();
    if (!ui_begin()) return;
    { extern void gore_draw(void); gore_draw(); ui_end_solid(); }
    for (int pass = 0; pass < 2; pass++) {
        rf_draw(pass); ins_draw(pass); fc_draw(pass);
        if (pass == 0) ui_end_solid(); else ui_end_text();
    }
}

/* on_pad_read (H3) now lives in freecam.c */
