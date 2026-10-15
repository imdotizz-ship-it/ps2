/* After a contact crash, the fallen bot gets up and plays its "lost" gesture (persoA-D, the
 * random one loaded for this race: id *(s16*)0x5ffc04).
 * RiderAnim R = veh-0x17a0 (ctl+0x520). Fall mode: R+0x264 == 1, phase R+0x2a4 (u32); phase 16 =
 * standing idle after rialzata (49/50). Hook H9 wraps 'jal 0x348a70' (fall-mode update, a0 = R,
 * f12 = dt) at 0x33f2ec; afterwards we drive RiderAnim_Play 0x343ae0(R, mode 2 = once, ids,
 * weights, flags 4, step) every frame until it reports the clip finished. */
typedef unsigned int u32; typedef unsigned short u16; typedef unsigned char u8; typedef short s16;

struct gstate { u32 magic, marks, plays, done; };
__attribute__((section(".data"))) struct gstate GST = { 0x54534547 /* 'GEST' */ };
static u8 *MARK[8];

extern int game_anim_play(u8 *R, int mode, const s16 *ids, const float *w, int flags, float step);

void gesture_mark(u8 *veh) {
    for (int i = 0; i < 8; i++) if (MARK[i] == veh) return;
    for (int i = 0; i < 8; i++) if (!MARK[i]) { MARK[i] = veh; GST.marks++; return; }
}
void gesture_reset(void) { for (int i = 0; i < 8; i++) MARK[i] = 0; }

void fall_gesture(u8 *R, float dt) {
    u8 *veh = *(u8 **)(R + 0x4cc);
    int k = -1;
    for (int i = 0; i < 8; i++) if (MARK[i] && MARK[i] == veh) k = i;
    if (k < 0) return;
    if (*(u32 *)(R + 0x264) != 1) { if (*(u32 *)(R + 0x264) == 0) MARK[k] = 0; return; }   /* back on the bike */
    if (*(u32 *)(R + 0x2a4) != 16) return;                       /* not standing yet */
    s16 id = *(s16 *)0x5ffc04;
    if (id <= 0) { MARK[k] = 0; return; }
    static const float w[4] = { 1.0f, 1.0f, 0.5f, 0.0f };
    s16 ids[3] = { id, -1, -1 };
    GST.plays++;
    if (game_anim_play(R, 2, ids, w, 4, dt * *(float *)(R + 0x2f0))) { MARK[k] = 0; GST.done++; }
}
