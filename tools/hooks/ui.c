/* In-race UI for the mod, drawn with the game's own RenderWare Im2D and the HUD font
 * (HelveticaNeue LT 65 Medium 24, packed by gen_font.py into font_atlas.h).
 *
 * RenderWare (PS2 "sky") facts, from SLUS_218.11:
 *   RwDevice at 0x616780: +0x08 zBufferNear (Im2D z), +0x10 fpRenderStateSet,
 *     +0x20 fpIm2DRenderPrimitive(type, verts, n)
 *   RwRasterCreate 0x163050(w, h, depth, flags)   RwRasterLock 0x163160(r, level, mode)
 *   RwRasterUnlock 0x162d70(r)
 *   Im2D vertex = 64 bytes: x y z @0, u v @0x10, recipZ @0x18, r g b a floats (0..255) @0x20
 *   (layout of the game's own 2D debug-font vertices, 0x25bad0)
 * Everything is drawn from the EndScene hook while the race camera is still in its update.
 */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;
#include "font_atlas.h"

#define RS_TEXRASTER 1
#define RS_ZTEST     6
#define RS_ZWRITE    8
#define RS_FILTER    9
#define RS_SRCBLEND  10
#define RS_DSTBLEND  11
#define RS_VALPHA    12
#define PRIM_TRILIST 3

typedef int (*rsset_fn)(int state, u32 value);
typedef int (*im2d_fn)(int prim, void *verts, int n);
typedef void *(*rcreate_fn)(int w, int h, int depth, int flags);
typedef u8 *(*rlock_fn)(void *r, int level, int mode);
typedef void *(*runlock_fn)(void *r);

typedef struct { float x, y, z, cz, u, v, rz, pad, r, g, b, a, n0, n1, n2, n3; } Vtx;

#define MAXV 3600
static Vtx V[MAXV];
static int nv;
static void *font_raster;
static float vz, vrz;
static u8 gidx[256];                       /* char -> glyph index + 1 */

struct uistate { u32 magic, inited, frames, draws, verts, curcam, rccam; };
__attribute__((section(".data"))) struct uistate UIS = { 0x31495547 /* 'GUI1' */ };

static int flt(float a, float b) {       /* a < b, R5900-safe */
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}

static void font_init(void) {
    for (int i = 0; i < FONT_N; i++) if (FONT_GLYPH[i][0] < 256) gidx[FONT_GLYPH[i][0]] = i + 1;
    void *r = ((rcreate_fn)0x163050)(FONT_W, FONT_H, 32, 4 | 0x500);   /* texture, 8888 */
    if (!r) return;
    u8 *p = ((rlock_fn)0x163160)(r, 0, 1);                              /* write */
    if (p) {
        int stride = *(int *)((u8 *)r + 0x18);
        if (stride < FONT_W * 4) stride = FONT_W * 4;
        for (int y = 0; y < FONT_H; y++) {
            u8 *row = p + y * stride;
            for (int x = 0; x < FONT_W; x++) {
                u8 n = FONT_A4[(y * FONT_W + x) >> 1];
                u32 a = (x & 1) ? (n >> 4) : (n & 15);
                row[x * 4 + 0] = 255; row[x * 4 + 1] = 255; row[x * 4 + 2] = 255;
                row[x * 4 + 3] = (u8)(a * 0x80 / 15);                       /* GS alpha: 0x80 = 1.0 */
            }
        }
        ((runlock_fn)0x162d70)(r);
    }
    font_raster = r;
}

/* ---- primitives ---- */
static void vtx(float x, float y, float u, float v, const u8 *c, float a) {
    Vtx *p = &V[nv++];
    p->x = x; p->y = y; p->z = vz; p->cz = 0; p->u = u; p->v = v; p->rz = vrz; p->pad = 0;
    p->r = c[0]; p->g = c[1]; p->b = c[2]; p->a = c[3] * a;
}
static void quad(float x0, float y0, float x1, float y1, float u0, float v0, float u1, float v1, const u8 *c, float a) {
    if (nv + 6 > MAXV) return;
    vtx(x0, y0, u0, v0, c, a); vtx(x1, y0, u1, v0, c, a); vtx(x0, y1, u0, v1, c, a);
    vtx(x1, y0, u1, v0, c, a); vtx(x1, y1, u1, v1, c, a); vtx(x0, y1, u0, v1, c, a);
}
static void tri(float x0, float y0, float x1, float y1, float x2, float y2, const u8 *c, float a) {
    if (nv + 3 > MAXV) return;
    vtx(x0, y0, 0, 0, c, a); vtx(x1, y1, 0, 0, c, a); vtx(x2, y2, 0, 0, c, a);
}
void ui_tri(float x0, float y0, float x1, float y1, float x2, float y2, const u8 *c, float a) { tri(x0, y0, x1, y1, x2, y2, c, a); }
static void flush(void *raster) {
    if (!nv) return;
    rsset_fn rs = *(rsset_fn *)0x616790;
    im2d_fn draw = *(im2d_fn *)0x6167a0;
    rs(RS_TEXRASTER, (u32)raster);
    rs(RS_VALPHA, 1);
    rs(RS_SRCBLEND, 5); rs(RS_DSTBLEND, 6);
    rs(RS_ZTEST, 0); rs(RS_ZWRITE, 0);
    rs(RS_FILTER, 2);
    draw(PRIM_TRILIST, V, nv);
    UIS.verts += nv;
    nv = 0;
}

/* ---- text ---- */
static int next_char(const char **s) {   /* UTF-8 -> Latin-1 code */
    const u8 *p = (const u8 *)*s;
    int c = *p++;
    if (c >= 0xc0 && c < 0xe0 && (*p & 0xc0) == 0x80) { c = ((c & 0x1f) << 6) | (*p++ & 0x3f); }
    else if (c >= 0xe0) { while ((*p & 0xc0) == 0x80) p++; c = '-'; }
    *s = (const char *)p;
    return c;
}
float ui_text_width(const char *s, float scale) {
    float w = 0;
    while (*s) {
        int c = next_char(&s), g = c < 256 ? gidx[c] : 0;
        if (g) w += (FONT_GLYPH[g - 1][3]) * scale;
    }
    return w;
}
void ui_text(float x, float y, const char *s, float scale, const u8 *col, float a) {
    const float iw = 1.0f / FONT_W, ih = 1.0f / FONT_H;
    while (*s) {
        int c = next_char(&s), g = c < 256 ? gidx[c] : 0;
        if (!g) continue;
        const u16 *G = FONT_GLYPH[g - 1];
        float w = G[3] * scale, h = G[4] * scale;
        if (c != ' ')
            quad(x, y, x + w, y + h, G[1] * iw, G[2] * ih, (G[1] + G[3]) * iw, (G[2] + G[4]) * ih, col, a);
        x += w;
    }
}
/* text with a soft drop shadow */
void ui_text_sh(float x, float y, const char *s, float scale, const u8 *col, float a) {
    static const u8 sh[4] = { 0, 0, 0, 200 };
    ui_text(x + 2, y + 2, s, scale, sh, a);
    ui_text(x, y, s, scale, col, a);
}

/* ---- frame ---- */
int ui_begin(void) {
    u8 *rc = *(u8 **)0x84f770;
    UIS.curcam = *(u32 *)0x616770;
    if (!rc) return 0;
    u8 *cml = *(u8 **)(rc + 0x0c);
    if (!cml) return 0;
    u8 *cam = *(u8 **)(cml + 0x18);
    UIS.rccam = (u32)cam;
    if (!cam || cam[0] != 4) return 0;
    float nearp = *(float *)(cam + 0x80);
    if (!flt(0.0001f, nearp)) nearp = 0.1f;
    vz = *(float *)0x616788;
    vrz = 1.0f / nearp;
    if (!UIS.inited) { UIS.inited = 1; font_init(); }
    UIS.frames++;
    nv = 0;
    return 1;
}
/* callers draw in two passes: pass 0 = panels and icons (no texture), pass 1 = text (font) */
void ui_end_solid(void) { flush(0); }
void ui_end_text(void) { if (font_raster) flush(font_raster); else nv = 0; UIS.draws++; }

/* ---- widgets ---- */
void ui_box(float x0, float y0, float x1, float y1, const u8 *c, float a) { quad(x0, y0, x1, y1, 0, 0, 0, 0, c, a); }

/* panel: translucent dark body, coloured accent bar on the left, thin top highlight */
void ui_panel(float x0, float y0, float x1, float y1, const u8 *accent, float a) {
    static const u8 body[4] = { 12, 14, 20, 190 }, hl[4] = { 255, 255, 255, 40 };
    ui_box(x0, y0, x1, y1, body, a);
    ui_box(x0, y0, x0 + 6, y1, accent, a);
    ui_box(x0 + 6, y0, x1, y0 + 2, hl, a);
}

/* waving red flag icon (pole + 4 strips) at (x,y), ~44x40 */
void ui_flag(float x, float y, u32 t, const u8 *col, float a) {
    static const u8 pole[4] = { 220, 220, 220, 255 }, dark[4] = { 140, 0, 0, 255 };
    static const signed char wave[8] = { 0, 2, 3, 2, 0, -2, -3, -2 };
    ui_box(x, y, x + 3, y + 44, pole, a);
    float fx = x + 3, w = 9;
    for (int i = 0; i < 4; i++) {
        float o0 = wave[(t / 4 + i * 2) & 7], o1 = wave[(t / 4 + i * 2 + 2) & 7];
        const u8 *c = (i & 1) ? dark : col;
        tri(fx, y + o0, fx + w, y + o1, fx, y + 26 + o0, c, a);
        tri(fx + w, y + o1, fx + w, y + 26 + o1, fx, y + 26 + o0, c, a);
        fx += w;
    }
}
