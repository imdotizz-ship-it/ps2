/* Spoken insults: clips Insult00..09 appended to SFX\COMMON.RWS (indices 11..20, 2D, category SFX).
 * COMMON is resident (loaded at boot), found through the sound manager without touching refcounts. */
#include "snd_api.h"
#define CLIP_BASE 11
#define NCLIPS 10
struct sndstate { u32 magic, plays, fails; u8 *bank; };
__attribute__((section(".data"))) struct sndstate SND = { 0x31444e53 /* 'SND1' */ };
static u8 *VOICE[NCLIPS];

void voice_play(int k) {
    if (k < 0 || k >= NCLIPS) return;
    u8 *b = snd_find_bank("Sfx\\Common.rws");
    if (!b) { SND.fails++; return; }
    if (b != SND.bank) { for (int i = 0; i < NCLIPS; i++) VOICE[i] = 0; SND.bank = b; }
    if (snd_bank_count(b) < CLIP_BASE + NCLIPS) { SND.fails++; return; }   /* stock bank: no clips */
    for (int i = 0; i < NCLIPS; i++) if (VOICE[i] && i != k && snd_is_playing(VOICE[i])) snd_stop(VOICE[i]);
    if (!VOICE[k]) {
        u8 *s = snd_bank_sound(b, CLIP_BASE + k);
        if (!s) { SND.fails++; return; }
        VOICE[k] = snd_new_voice(s);
        if (!VOICE[k]) { SND.fails++; return; }
    }
    snd_stop(VOICE[k]);
    snd_set_volume(VOICE[k], 1.0f);
    snd_play(VOICE[k]);
    SND.plays++;
}
