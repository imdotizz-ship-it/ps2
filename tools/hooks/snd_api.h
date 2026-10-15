/* MotoGP 08 (SLUS-21811) sound API, for hook code built like insult_kit (clang n32, -G0).
 * Game code is EABI: ints in a0-a3,t0-t3 (= n32 a0-a7, same registers), floats packed from f12.
 * n32 passes floats POSITIONALLY (2nd arg -> f13), so float-taking calls go through the
 * thunks in snd_thunks.S.  gp (0x605070) must be intact when calling game code.
 */
typedef unsigned int u32; typedef unsigned char u8;

#define SND_MGR_PTR   0x5ffd20                 /* *(u32*) = SoundManager (also gp-0x5350) */
/* SoundManager: +0x04 cfg (category table), +0x0c bank*[20], +0x5c refcount[20], +0x124 nbanks */
/* Bank (0x6c): +0x00 first Sound*, +0x08 count, +0x10 slot, +0x14 dict wrapper (+0x08 = path,
 *              e.g. "Sfx\\Common.rws", "sfx\\collision\\collision.rws") */
/* Sound (0xb4): +0x00 name[128], +0x84 next, +0x98 category, +0xa4 wave wrapper (+8 RwaWave*),
 *              +0xac voice list, +0xb0 attenuator (from .CRW) */
/* Voice: +0x00 type (2 = 2D, 3 = 3D), +0x04 volume, +0x08 f32 sample rate, +0x0c vtable
 *        (0x5fac20 2D / 0x5fac40 3D), +0x3c category, +0x44 RwaVoice wrapper (+0x28 u8 playing),
 *        +0x48 Sound*, +0x51 u8 started, +0x54 attenuator, +0x60 pan (2D) */
/* category table: cfg + cat*20: +0x48 f32, +0x4c u8 enabled, +0x50 f32, +0x54 f32 (AudioConfig
 * fValueLock); final gain = voice vol * f48*f50*f54 * attenuator */

#define snd_get_mgr      ((u8 *(*)(void))0x4355b0)
#define snd_load_bank    ((u8 *(*)(u8 *mgr, const char *path, int flag))0x4352c0) /* refcount++ */
#define snd_unload_bank  ((void (*)(u8 *mgr, u8 *bank))0x435240)                   /* refcount-- */
#define snd_bank_count   ((u32 (*)(u8 *bank))0x437050)
#define snd_bank_sound   ((u8 *(*)(u8 *bank, u32 index))0x437060)   /* index = order in .RWS */
#define snd_bank_find    ((u8 *(*)(u8 *bank, const char *name))0x436fe0) /* by name in .RWS */
#define snd_new_voice    ((u8 *(*)(u8 *sound))0x439100)  /* allocates; 0 on failure */
#define snd_play         ((void (*)(u8 *voice))0x436500)
#define snd_stop         ((void (*)(u8 *voice))0x4363d0)
#define snd_release      ((void (*)(u8 *voice))0x4366e0)  /* unlink from sound + delete */
#define snd_set_loop     ((void (*)(u8 *voice, int loop))0x436370)
#define snd_set_pos3d    ((void (*)(u8 *voice, const float *xyz))0x436dd0) /* 3D only; applied
                                                     on every 4th call (+0x78/+0x7c throttle) */
/* float setters: thunks (snd_thunks.S) */
void snd_set_volume(u8 *voice, float vol);   /* -> 0x436390(voice, f12=vol, a1=1 cancel fade) */
void snd_set_pan(u8 *voice, float pan);      /* -> 0x436950(voice, f12=pan -1..1), 2D only */

static inline int snd_is_playing(u8 *voice) { return *(u8 *)(*(u8 **)(voice + 0x44) + 0x28); }

static int snd_ieq(const char *a, const char *b) {
    for (;; a++, b++) {
        char x = *a, y = *b;
        if (x >= 'A' && x <= 'Z') x += 32;
        if (y >= 'A' && y <= 'Z') y += 32;
        if (x == '/') x = '\\';
        if (y == '/') y = '\\';
        if (x != y) return 0;
        if (!x) return 1;
    }
}

/* find an already loaded bank without touching its refcount */
static u8 *snd_find_bank(const char *path) {
    u8 *mgr = *(u8 **)SND_MGR_PTR;
    if (!mgr) return 0;
    for (int i = 0; i < 20; i++) {
        u8 *b = *(u8 **)(mgr + 0x0c + 4 * i);
        if (b && *(u8 **)(b + 0x14) && snd_ieq((const char *)(*(u8 **)(b + 0x14) + 8), path)) return b;
    }
    return 0;
}
