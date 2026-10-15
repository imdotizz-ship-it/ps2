/* Crash gore and debris for MotoGP 08 (SLUS-21811): blood spray that falls and leaves pools,
 * plus bike debris flying off, spawned at the rider's position when a fall starts.
 * World -> screen uses the race camera frame (CML+8 -> RwFrame +0x10: right, up, at, pos;
 * "right" points to screen-left) and the RwCamera view window (+0x68). Particles live in sim
 * time, so they follow the slow motion of takedowns and red flags.
 * Drawn as untextured Im2D triangles through ui.c, under the UI panels. */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8;

#ifndef GORE_DROPS
#define GORE_DROPS 24
#endif
#define NP 200

typedef struct { float x, y, z, vx, vy, vz, ground, size, life; u8 kind, c; u16 pad; } P;
enum { K_FREE, K_DROP, K_POOL, K_DEBRIS };

struct gorestate { u32 magic, spawns, live, seed; };
__attribute__((section(".data"))) struct gorestate GORE = { 0x45524f47 /* 'GORE' */, 0, 0, 0x2545f491 };
static P PT[NP];
static int flt(float a, float b);
/* bikes whose windscreen broke off: Selene part node at BikeGfx(ctl+0xae0)+0x10c / +0x118,
 * hidden flag = node byte 0 bit 0x40 (re-applied every frame after the game's LOD pass 0x2f6060) */
static u8 *BROKEN[24]; static int nbroken;
void gore_reset(void) { nbroken = 0; }
void bike_pre(u8 *B) { extern void td_bike_lod(u8 *, u8 *); td_bike_lod(*(u8 **)(B + 0x3bc), B); }
void bike_parts(u8 *B) {
    u8 *veh = *(u8 **)(B + 0x3bc);
    for (int i = 0; i < nbroken; i++) if (BROKEN[i] == veh) {
        u8 *n = *(u8 **)(B + 0x10c); if ((u32)n > 0x100000 && (u32)n < 0x2000000) n[0] |= 0x40;
        n = *(u8 **)(B + 0x118);     if ((u32)n > 0x100000 && (u32)n < 0x2000000) n[0] |= 0x40;
        return;
    }
}
/* active emitters: blood keeps coming out of the tumbling rider for ~2 s */
typedef struct { u8 *veh; float t, acc, speed; } E;
static E EM[4];
/* rider body: 8 points at veh+0xe68 (stride 12) follow the rider once he leaves the bike */
static int rider_pos(u8 *veh, float *o) {
    float x = 0, y = 0, z = 0, *b = (float *)(veh + 0x50);
    for (int i = 0; i < 8; i++) { float *q = (float *)(veh + 0xe68 + 12 * i); x += q[0]; y += q[1]; z += q[2]; }
    x *= 0.125f; y *= 0.125f; z *= 0.125f;
    float dx = x - b[0], dz = z - b[2];
    if (!flt(dx * dx + dz * dz, 900.0f)) { x = b[0]; y = b[1]; z = b[2]; }   /* implausible: use the bike */
    o[0] = x; o[1] = y; o[2] = z;
    return 1;
}

extern void ui_tri(float, float, float, float, float, float, const u8 *, float);
extern float fc_sin(float), fc_cos(float);

static int flt(float a, float b) {
    int r;
    __asm__ volatile(".set push\n\t.set noreorder\n\t"
                     "c.olt.s %1, %2\n\tnop\n\tli %0, 1\n\tbc1t 1f\n\tnop\n\tli %0, 0\n1:\n\t.set pop"
                     : "=&r"(r) : "f"(a), "f"(b));
    return r;
}
static float rnd01(void) { GORE.seed = GORE.seed * 1103515245u + 12345u; return ((GORE.seed >> 9) & 0xffff) * (1.0f / 65536); }
static P *alloc(void) {
    for (int i = 0; i < NP; i++) if (PT[i].kind == K_FREE) return &PT[i];
    for (int i = 0; i < NP; i++) if (PT[i].kind == K_POOL) return &PT[i];     /* recycle oldest-ish pool */
    return 0;
}

/* called from the fall hook: veh position at +0x50, impact speed in m/s */
void gore_on_fall(u8 *veh, float speed, int fatal) {
    float *vp = (float *)(veh + 0x50);
    float s = speed; if (flt(30.0f, s)) s = 30.0f;
    int n = GORE_DROPS + (fatal ? 30 : 0);
    GORE.spawns++;
#ifdef GEST_DEBUG
    { extern void gesture_mark(u8 *); gesture_mark(veh); }
#endif
    if (flt(12.0f, speed) && nbroken < 24) { int k; for (k = 0; k < nbroken && BROKEN[k] != veh; k++); if (k == nbroken) BROKEN[nbroken++] = veh; }
    for (int e = 0; e < 4; e++) if (!EM[e].veh || EM[e].veh == veh) { EM[e].veh = veh; EM[e].t = 0; EM[e].acc = 0; EM[e].speed = s; break; }
    for (int i = 0; i < n; i++) {
        P *p = alloc(); if (!p) break;
        float a = rnd01() * 6.2831f, h = (0.6f + rnd01() * 2.2f) * (0.5f + s * 0.03f);
        p->x = vp[0]; p->y = vp[1] + 0.5f + rnd01() * 0.4f; p->z = vp[2];
        p->vx = fc_cos(a) * h; p->vz = fc_sin(a) * h; p->vy = 1.5f + rnd01() * 3.5f;
        p->ground = vp[1] - 0.45f;
        p->size = 0.05f + rnd01() * 0.07f; p->life = 9.0f + rnd01() * 4; p->kind = K_DROP; p->c = 0;
    }
    for (int i = 0; i < 14; i++) {                 /* bike debris: fairing shards, carbon, glass */
        P *p = alloc(); if (!p) break;
        float a = rnd01() * 6.2831f, h = (1.0f + rnd01() * 3.0f) * (0.5f + s * 0.04f);
        p->x = vp[0]; p->y = vp[1] + 0.3f; p->z = vp[2];
        p->vx = fc_cos(a) * h; p->vz = fc_sin(a) * h; p->vy = 2.0f + rnd01() * 4.0f;
        p->ground = vp[1] - 0.45f;
        p->size = 0.06f + rnd01() * 0.12f; p->life = 12.0f; p->kind = K_DEBRIS; p->c = (u8)((GORE.seed >> 20) % 3);
    }
}

/* race update with the (slow-motion scaled) sim dt */
void gore_update(float dt) {
    if (!flt(0.0f, dt)) return;
    if (flt(0.1f, dt)) dt = 0.1f;
    for (int e = 0; e < 4; e++) {
        E *m = &EM[e];
        if (!m->veh) continue;
        m->t += dt; m->acc += dt;
        if (!flt(m->t, 1.6f)) { m->veh = 0; continue; }
        float rp[3]; rider_pos(m->veh, rp);
        while (!flt(m->acc, 0.05f)) {                  /* ~20 drops per second of sim time */
            m->acc -= 0.05f;
            P *p = alloc(); if (!p) break;
            float a = rnd01() * 6.2831f, h = 0.4f + rnd01() * 1.6f;
            p->x = rp[0]; p->y = rp[1] + 0.25f; p->z = rp[2];
            p->vx = fc_cos(a) * h; p->vz = fc_sin(a) * h; p->vy = 0.5f + rnd01() * 2.5f;
            p->ground = rp[1] - 0.2f;
            p->size = 0.04f + rnd01() * 0.06f; p->life = 10.0f + rnd01() * 4; p->kind = K_DROP; p->c = 0;
        }
    }
    int live = 0;
    for (int i = 0; i < NP; i++) {
        P *p = &PT[i];
        if (p->kind == K_FREE) continue;
        p->life -= dt;
        if (flt(p->life, 0.0f)) { p->kind = K_FREE; continue; }
        live++;
        if (p->kind == K_POOL) { if (flt(p->size, p->pad * 0.001f)) p->size += dt * 0.05f; continue; }
        p->vy -= 9.8f * dt;
        p->x += p->vx * dt; p->y += p->vy * dt; p->z += p->vz * dt;
        if (flt(p->y, p->ground)) {
            p->y = p->ground;
            if (p->kind == K_DROP) { p->kind = K_POOL; p->size *= 1.3f; p->pad = (u16)(120 + (GORE.seed >> 23) % 140); p->c = (u8)((GORE.seed >> 13) & 7); p->vx = p->vy = p->vz = 0; }
            else { p->vy = -p->vy * 0.3f; p->vx *= 0.5f; p->vz *= 0.5f; }   /* debris bounces */
        }
    }
    GORE.live = live;
}

/* 10-gon with a per-particle wobble so pools look irregular */
static void blob(float sx, float sy, float rx, float ry, const u8 *c, float a, int var) {
    static const float CS[11] = { 1, .809f, .309f, -.309f, -.809f, -1, -.809f, -.309f, .309f, .809f, 1 },
                       SN[11] = { 0, .588f, .951f, .951f, .588f, 0, -.588f, -.951f, -.951f, -.588f, 0 };
    static const float W[8][10] = {
        {1,.8f,1.1f,.9f,1,1.2f,.85f,1,.9f,1.1f},{.9f,1.15f,.8f,1,1.1f,.9f,1,1.2f,.8f,1},
        {1.1f,.9f,1,.75f,1.2f,1,.9f,1,1.1f,.85f},{.8f,1,1.2f,1,.9f,.8f,1.1f,.9f,1,1.15f},
        {1,1.1f,.9f,1.2f,.8f,1,1,.85f,1.15f,.9f},{1.2f,.9f,1,.85f,1,1.1f,.8f,1,.95f,1.05f},
        {.85f,1,1.1f,.9f,1.15f,.8f,1,1.1f,.9f,1},{1,.9f,.85f,1.1f,1,1.2f,.9f,.8f,1.05f,1}};
    const float *w = W[var & 7];
    for (int k = 0; k < 10; k++) {
        float r0 = w[k], r1 = w[(k + 1) % 10];
        ui_tri(sx, sy, sx + CS[k] * rx * r0, sy + SN[k] * ry * r0, sx + CS[k + 1] * rx * r1, sy + SN[k + 1] * ry * r1, c, a);
    }
}

/* pass 0 of the UI (solid triangles), before the panels */
void gore_draw(void) {
    u8 *rc = *(u8 **)0x84f770; if (!rc) return;
    u8 *cml = *(u8 **)(rc + 0x0c); if (!cml) return;
    u8 *cam = *(u8 **)(cml + 0x18), *frm = *(u8 **)(cml + 0x08);
    if (!cam || !frm || cam[0] != 4) return;
    float *m = (float *)(frm + 0x10);
    float vwx = *(float *)(cam + 0x68), vwy = *(float *)(cam + 0x6c);
    if (!flt(0.01f, vwx) || !flt(0.01f, vwy)) return;
    float kx = 320.0f / vwx, ky = 224.0f / vwy;
    static const u8 drop[4] = { 150, 0, 0, 235 }, pool[4] = { 85, 2, 4, 200 },
                    deb[3][4] = { { 235, 235, 240, 255 }, { 30, 30, 34, 255 }, { 160, 200, 230, 170 } };
    for (int i = 0; i < NP; i++) {
        P *p = &PT[i];
        if (p->kind == K_FREE) continue;
        float dx = p->x - m[12], dy = p->y - m[13], dz = p->z - m[14];
        float z = dx * m[8] + dy * m[9] + dz * m[10];
        if (flt(z, 0.4f) || flt(120.0f, z)) continue;
        float iz = 1.0f / z;
        float sx = 320 - (dx * m[0] + dy * m[1] + dz * m[2]) * iz * kx;
        float sy = 224 - (dx * m[4] + dy * m[5] + dz * m[6]) * iz * ky;
        float r = p->size * iz * kx;
        if (flt(r, 0.6f)) r = 0.6f;
        if (flt(30.0f, r)) r = 30.0f;
        float a = flt(p->life, 2.0f) ? p->life * 0.5f : 1.0f;      /* fade out */
        if (p->kind == K_DROP) blob(sx, sy, r, r * 1.3f, drop, a, i);
        else if (p->kind == K_POOL) blob(sx, sy, r * 1.5f, r * 0.5f, pool, a, p->c);
        else ui_tri(sx - r, sy + r * 0.6f, sx + r, sy + r * 0.3f, sx + r * 0.2f, sy - r, deb[p->c], a);
    }
}
