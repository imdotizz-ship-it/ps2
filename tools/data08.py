#!/usr/bin/env python3
r"""Gameplay data mods for MotoGP 08 (PS2), all in DATA.MIX (.BML files, see bml.py).

  DATA\DB_PILOTS*.BML   every CPU rider has twice the chance of falling (on track, off track,
                        and of a fall being a highside), in all three classes; and every CPU
                        rider gets the pace of the fastest rider of the class (how early he
                        opens the throttle, qualifying time ratios), per difficulty, dry and
                        wet, so the whole grid fights for the win
  DATA\BIKES\*\*.BML   every team's bike of a class gets the engine torque of the strongest
                        bike of that class (MotoGP 94, 250cc 58, 125cc 31), the rest of each
                        bike (gearing, grip, handling) is kept
  DATA\AIPARAMS.BML     the CPU riders keep half the distance from each other: avoidance
                        distance, collision boxes and braking distance are halved, overtakes
                        pass closer and defending riders steer harder (the values that concern
                        the human rider are kept)
  DATA\DB_GAMECONFIG.BML contacts shove a bit harder, and collisions sour
                        the rivalry between two riders faster; the replay Orbit camera turns
                        almost all the way round and from below to straight above the bike
  DATA\CAMERAS.BML      a high TV-style chase camera in the in-race camera cycle (instead of
                        the second cockpit view); the field of view of the race
                        cameras (--fov, cockpit degrees; 70 is the original)

  --safety-car (experimental) DB_VEHICLES, DB_TEAMS and DB_PILOTS get the MotoGP 4 safety
                        car as an extra vehicle, team and rider (the model comes from
                        safetycar.py); it uses the physics, sound and menu names of the Honda
                        team, as the game has no texts for it

Usage:
  data08.py DATA.MIX OUT_DIR [--fov DEG] [--safety-car]   writes OUT_DIR/DATA.MIX
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
    "Defense/Defense_Distance": "15",      # 10
    "Defense/Def_Speed_Mult": "1.00",      # 0.95: defending does not cost speed
    "Overtake/Overtake_Distance": "15",    # 10: attacks start from further back
}

DAMAGE = {                                  # GameConfig/Damage (and its per-mode copies)
    "BikeBikeCollisionImpulse": "1.5",      # 1.: contacts shove a bit harder; the fall thresholds
}                                           # stay original (the hook code forces bot takedowns)
RIVALRY = {"LIGHT": "-3", "MEDIUM": "-8", "HARD": "-15"}   # -1, -3, -5
ORBIT = {"Distance": "7", "DegsPerSecond_X": "150.", "DegsPerSecond_Y": "150.",
         "MinVerticalAngleDeg": "-80.", "MaxVerticalAngleDeg": "89."}

TV_SLOT = "3"          # the bonnet camera, used by no camera list
TV_GAME_INDEX = "2"    # replaces the second cockpit view (camera 6) in the in-race cycle
TV_VALUES = {"vCameraPos": "0.0, 6.5, -11.0", "vCameraDir": "0.0, -5.0, 11.0", "vCameraPosBack": "0.0, 5.0, 9.0",
             "fFocal": "60", "fExtCamFinalFocal": "60"}
FOV_DEFAULT = 70


def ai_params(d):
    return bml.set_values(d, AI_CHANGES)


FALLS = ("ProbFall_OnTrack", "ProbFall_OutTrack", "ProbHiSide")


def pilots(d):
    """every CPU rider, at every difficulty: twice the chance of falling (capped at 1)"""
    root = bml.load(d)
    def walk(n):
        for k in FALLS:
            v = bml.get_text(n, k)
            if v is not None:
                bml.set_text(n, k, ("%.4f" % min(1.0, 2 * float(v))).rstrip("0").rstrip("."))
        for c in n.children:
            if c.kind == 1:
                walk(c)
    walk(root)
    return bml.save(root)


PACE = ("SplineThrottle_MultTreshold", "MaxQualTimeRatio", "MinQualTimeRatio")   # lower is faster


def competitive(d):
    """every rider gets, per AI block (AI / AI_Wet and difficulty), the lowest value of each PACE field"""
    root = bml.load(d)
    blocks = {}
    for p in (c for c in root.children if c.kind == 1):
        for a in (c for c in p.children if c.kind == 1 and c.name in ("AI", "AI_Wet")):
            blocks.setdefault((a.name, tuple((x[0], x[1]) for x in a.attrs)), []).append(a)
    for nodes in blocks.values():
        for k in PACE:
            vals = [bml.get_text(a, k) for a in nodes if bml.get_text(a, k) is not None]
            if vals:
                best = min(vals, key=float)
                for a in nodes:
                    if bml.get_text(a, k) is not None:
                        bml.set_text(a, k, best)
    return bml.save(root)


def team_physics(entries, data):
    """{DATA\\BIKES\\...\\X.BML: torque} for the bikes the teams use: the strongest of each class"""
    used = {}
    for e in entries:
        n = e.name.upper()
        if n.startswith("DATA\\DB_TEAMS") and n.endswith(".BML"):
            root = bml.load(data[e.offset:e.offset + e.stored_size])
            for t in (c for c in root.children if c.kind == 1):
                for ph in bml.elements(t, "Physics"):
                    used.setdefault(n, set()).add(bml.get_text(ph, "Name").upper())
    out = {}
    for names in used.values():
        files = [e for e in entries if e.name.upper().startswith("DATA\\BIKES\\")
                 and e.name.upper().rsplit("\\", 1)[-1][:-4] in names]
        tq = {e.name: bml.get_text(bml.elements(bml.load(data[e.offset:e.offset + e.stored_size]), "Engine")[0],
                                   "fMaxTorque") for e in files}
        best = max(tq.values(), key=float)
        out.update({k: best for k in tq})
    return out


def torque(d, value):
    root = bml.load(d)
    bml.set_text(bml.elements(root, "Engine")[0], "fMaxTorque", value)
    return bml.save(root)


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
    return bml.save(root)


SAFETY_CAR = {"vehicle": "BMW_M6_Safety_Car", "team": "Safety_Car", "pilot": "SafetyCar",
              "model": "Bikes\\Bike07\\Bike07.slf", "like_vehicle": "Honda_RC212V",
              "like_team": "Repsol_Honda", "like_pilot": "Hayden", "number": "99"}


def _clone_entry(root, key, new_key):
    src = next(c for c in root.children if c.attrs and c.attrs[0][1] == key)
    n = copy.deepcopy(src); n.attrs[0][1] = new_key
    root.children.append(n)
    return n


def add_vehicle(d):
    """the safety car as a vehicle: the BIKE07 model, physics and sound of the Honda"""
    root = bml.load(d)
    v = _clone_entry(root, SAFETY_CAR["like_vehicle"], SAFETY_CAR["vehicle"])
    for gfx in bml.elements(v, "Gfx") + bml.elements(v, "GfxGem"):
        bml.set_text(gfx, "Model3d", SAFETY_CAR["model"])
    return bml.save(root)


def add_team(d):
    root = bml.load(d)
    t = _clone_entry(root, SAFETY_CAR["like_team"], SAFETY_CAR["team"])
    bml.elements(t, "Vehicle")[0].attrs[0][1] = SAFETY_CAR["vehicle"]
    return bml.save(root)


def add_pilot(d):
    root = bml.load(d)
    p = _clone_entry(root, SAFETY_CAR["like_pilot"], SAFETY_CAR["pilot"])
    bml.elements(p, "Team")[0].attrs[0][1] = SAFETY_CAR["team"]
    bml.set_text(bml.elements(p, "Menu")[0], "Number", SAFETY_CAR["number"])
    return bml.save(root)


def build(mix_path, fov=FOV_DEFAULT, safety_car=False):
    data, entries = mix.read_mix(mix_path)
    jobs = {"DATA\\AIPARAMS.BML": ai_params, "DATA\\DB_GAMECONFIG.BML": gameconfig,
            "DATA\\CAMERAS.BML": lambda d: cameras(d, fov)}
    for cls in ("", "_125CC", "_250CC"):
        jobs["DATA\\DB_PILOTS%s.BML" % cls] = lambda d: competitive(pilots(d))
    for name, tq in team_physics(entries, data).items():
        jobs[name.upper()] = lambda d, tq=tq: torque(d, tq)
    if safety_car:
        jobs["DATA\\DB_VEHICLES.BML"] = add_vehicle
        jobs["DATA\\DB_TEAMS.BML"] = add_team
        jobs["DATA\\DB_PILOTS.BML"] = lambda d: add_pilot(competitive(pilots(d)))
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
    ap.add_argument("--safety-car", action="store_true",
                    help="experimental: an extra team and rider with the MotoGP 4 safety car (BIKE07, see safetycar.py)")
    a = ap.parse_args()
    if not 40 <= a.fov <= 140:
        sys.exit("error: --fov must be between 40 and 140")
    out_data, names = build(a.mix, a.fov, a.safety_car)
    os.makedirs(a.out, exist_ok=True)
    out = os.path.join(a.out, os.path.basename(a.mix))
    with open(out, "wb") as f:
        f.write(out_data)
    print("wrote %s (%s)" % (out, ", ".join(names)))


if __name__ == "__main__":
    main()
