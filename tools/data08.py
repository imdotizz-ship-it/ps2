#!/usr/bin/env python3
r"""Gameplay data mods for MotoGP 08 (PS2), all in DATA.MIX (.BML files, see bml.py).

  DATA\AIPARAMS.BML     the CPU riders keep half the distance from each other: avoidance
                        distance, collision boxes and braking distance are halved, overtakes
                        pass closer and defending riders steer harder (the values that concern
                        the human rider are kept)
  DATA\DB_GAMECONFIG.BML contacts in the style of Burnout takedowns: a bike-to-bike contact
                        knocks a rider down at a lower speed difference and shoves harder,
                        running into a fallen bike brings you down sooner, and collisions sour
                        the rivalry between two riders faster; the replay Orbit camera turns
                        almost all the way round and from below to straight above the bike
  DATA\CAMERAS.BML      a high TV-style chase camera in the in-race camera cycle (instead of
                        the second cockpit view); camera shake at high speed and the speed
                        effect of the cameras starting earlier; the field of view of the race
                        cameras (--fov, cockpit degrees; 70 is the original)

Usage:
  data08.py DATA.MIX OUT_DIR [--fov DEG]   writes OUT_DIR/DATA.MIX (put it back with ps2iso.py)
"""
import argparse
import copy
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bml  # noqa: E402
import mix  # noqa: E402

AI_CHANGES = {
    "General/Avoiding_Distance": "4",      # 7
    "Brake/CollSize_Front": "0.9",         # 1.8
    "Brake/CollSize_Lateral": "0.4",       # 0.8
    "Brake/CollDistance_Front": "2.7",     # 5.5
    "Overtake/Overt_Lateral_Offs": "3",    # 5
    "Defense/Def_Steer_Mult": "0.30",      # 0.15
}

DAMAGE = {                                  # GameConfig/Damage (and its per-mode copies)
    "BikeBikeCollisionDiffSpeed": "55.",    # 92.
    "BikeBikeCollisionSideSpeed": "28.",    # 48.
    "BikeBikeCollisionImpulse": "2.5",      # 1.
    "BikeVsFallenBikeSpeedThreshold": "12.",  # 20.
}
RIVALRY = {"LIGHT": "-3", "MEDIUM": "-8", "HARD": "-15"}   # -1, -3, -5
ORBIT = {"Distance": "7", "DegsPerSecond_X": "150.", "DegsPerSecond_Y": "150.",
         "MinVerticalAngleDeg": "-80.", "MaxVerticalAngleDeg": "89."}

TV_SLOT = "3"          # the bonnet camera, used by no camera list
TV_GAME_INDEX = "2"    # replaces the second cockpit view (camera 6) in the in-race cycle
TV_VALUES = {"vCameraPos": "0.0, 6.5, -11.0", "vCameraDir": "0.0, -5.0, 11.0", "vCameraPosBack": "0.0, 5.0, 9.0",
             "fFocal": "60", "fExtCamFinalFocal": "60"}
SHAKE = {"bVibrationActive": "true", "fVibrationMinSpeed": "50.0", "fVibrationMaxSpeed": "85.0",
         "fVibrationFrequence": "40.0", "fVibrationAmplitude": "0.04"}
SPEED_FX = {"fNitroEffectStartSpeed": "28", "fNitroEffectEndSpeed": "50"}   # 41, 66 (m/s)
FOV_DEFAULT = 70


def ai_params(d):
    return bml.set_values(d, AI_CHANGES)


def gameconfig(d):
    root = bml.load(d)
    dmg = bml.elements(root, "Damage")[0]
    for node in [dmg] + bml.elements(dmg, "Mode"):
        for k, v in DAMAGE.items():
            if bml.elements(node, k):
                bml.set_text(node, k, v)
    rel = bml.elements(root, "Relationships")[0]
    for kind, v in RIVALRY.items():
        for e in bml.elements(rel, "CollisionIncrement", Type=kind):
            next(t for t in e.children if t.kind == 3).value = v
    orbit = bml.elements(root, "OrbitModeConfig")[0]
    for k, v in ORBIT.items():
        bml.set_text(orbit, k, v)
    return bml.save(root)


def cameras(d, fov=FOV_DEFAULT):
    root = bml.load(d)
    cams = {c.attrs[0][1]: c for c in bml.elements(root, "CAMERA")}
    tv = copy.deepcopy(cams["2"])          # the far chase camera, moved up and back
    tv.attrs[0][1] = TV_SLOT
    for k, v in TV_VALUES.items():
        bml.set_text(tv, k, v)
    root.children[root.children.index(cams[TV_SLOT])] = tv
    cams[TV_SLOT] = tv
    game = bml.elements(root, "GAME", index=TV_GAME_INDEX)[0]
    next(t for t in game.children if t.kind == 3).value = TV_SLOT
    race = [g.text() for g in bml.elements(root, "GAME")]           # the in-race cycle
    k = fov / FOV_DEFAULT
    for i in race:
        cam = cams[i]
        for node in [cam] + [c for c in cam.children if c.kind == 1 and c.name.startswith("Bike")]:
            for name in ("fFocal", "fExtCamFinalFocal"):
                v = bml.get_text(node, name)
                if v is not None:            # three digits, so every --fov gives the same file size
                    bml.set_text(node, name, "%03d" % round(float(v.rstrip("f").rstrip(".")) * k))
        for name, v in SHAKE.items():
            bml.set_text(cam, name, v, create=True)
        for name, v in SPEED_FX.items():
            if bml.get_text(cam, name) is not None:
                bml.set_text(cam, name, v)
    return bml.save(root)


def build(mix_path, fov=FOV_DEFAULT):
    data, entries = mix.read_mix(mix_path)
    jobs = {"DATA\\AIPARAMS.BML": ai_params, "DATA\\DB_GAMECONFIG.BML": gameconfig,
            "DATA\\CAMERAS.BML": lambda d: cameras(d, fov)}
    payloads = []
    for e in entries:
        p = data[e.offset:e.offset + e.stored_size]
        fn = jobs.get(e.name.upper())
        if fn:
            if e.flag != 0:
                raise SystemExit("error: %s is compressed in this archive" % e.name)
            p = fn(p); e.flag, e.unpacked_size = 0, len(p)
        payloads.append(p)
    return mix.write_mix(entries, payloads), sorted(jobs)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mix"); ap.add_argument("out")
    ap.add_argument("--fov", type=int, default=FOV_DEFAULT, help="cockpit field of view in degrees (original 70)")
    a = ap.parse_args()
    if not 40 <= a.fov <= 140:
        sys.exit("error: --fov must be between 40 and 140")
    out_data, names = build(a.mix, a.fov)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, os.path.basename(a.mix))
    with open(out, "wb") as f:
        f.write(out_data)
    print("wrote %s (%s)" % (out, ", ".join(names)))


if __name__ == "__main__":
    main()
