import re
"""Build a many character, many scene 3D story with MPFB2/MakeHuman humans and render frames.

Run: blender -b -P build_scene.py -- --story s.json --timeline t.json --out frames/ --start 1 --end 100 [--still 1]
"""
import bpy, sys, os, json, math, random
from mathutils import Vector, Quaternion
import addon_utils

argv = sys.argv[sys.argv.index("--") + 1:]
A = dict(zip(argv[::2], argv[1::2]))
STORY = json.load(open(A["--story"]))
TL = json.load(open(A["--timeline"]))
FPS = TL["fps"]
OUT = A["--out"]
HDRI = A.get("--hdri", "")
JAW_SIGN = float(A.get("--jaw", "1"))
ARM_SIDE = float(A.get("--armside", "1"))

for o in list(bpy.data.objects):
    bpy.data.objects.remove(o, do_unlink=True)
addon_utils.enable("bl_ext.user_default.mpfb", default_set=True)
from bl_ext.user_default.mpfb.services.humanservice import HumanService

DATA = os.path.join(bpy.utils.extension_path_user("bl_ext.user_default.mpfb"), "data")
print("MPFB user data:", DATA, os.listdir(DATA) if os.path.isdir(DATA) else "MISSING")


# ---------- humans ----------
def assets(sub, ext):
    res = []
    for d, _, fs in os.walk(os.path.join(DATA, sub)):
        for f in fs:
            if f.endswith(ext):
                res.append(os.path.basename(d) + "/" + f)
    return sorted(res)


def pick(sub, ext, *prefs):
    lst = assets(sub, ext)
    print(f"[{sub}] {len(lst)}:", ", ".join(x.split("/")[1] for x in lst))
    for p in prefs:
        words = p.split()
        for x in lst:
            toks = set(re.split(r"[_/.\-]+", x.lower())) | {x.lower().split("/")[0]}
            if all(w in toks or (w.rstrip("0123456789") != w and any(t.startswith(w) for t in toks)) for w in words):
                return x
    return lst[0] if lst else ""


RACES = {
    "african": {"african": 0.9, "caucasian": 0.05, "asian": 0.05},
    "caucasian": {"african": 0.05, "caucasian": 0.9, "asian": 0.05},
    "asian": {"african": 0.05, "caucasian": 0.05, "asian": 0.9},
}


def human(cid, look):
    info = HumanService._create_default_human_info_dict()
    info["name"] = cid
    pheno = {k: look[k] for k in ("gender", "age", "weight", "muscle", "height")}
    pheno["race"] = RACES[look.get("race", "african")]
    info["phenotype"].update(pheno)
    info["rig"] = "default"
    info["skin_mhmat"] = pick("skins", ".mhmat", *look["skin"])
    info["skin_material_type"] = "ENHANCED_SSS"
    info["eyes"] = pick("eyes", ".mhclo", "high-poly", "")
    info["eyebrows"] = pick("eyebrows", ".mhclo", "eyebrow001", "")
    info["eyelashes"] = pick("eyelashes", ".mhclo", "eyelashes01", "")
    info["teeth"] = pick("teeth", ".mhclo", "teeth_base", "")
    info["tongue"] = pick("tongue", ".mhclo", "tongue01", "")
    info["hair"] = pick("hair", ".mhclo", *look["hair"])
    clothes = []
    for group in look["clothes"]:
        c = pick("clothes", ".mhclo", *group)
        if c and c not in clothes:
            clothes.append(c)
    info["clothes"] = clothes
    print(cid, "INFO", {k: info[k] for k in ["skin_mhmat", "hair", "clothes", "eyes"]})
    s = HumanService.get_default_deserialization_settings()
    s["subdiv_levels"] = 1
    body = HumanService.deserialize_from_dict(info, s)
    return body, body.parent


def tint(rig, cid, table):
    """Give clothes or hair a solid colour. table = {"name part": [r, g, b]}"""
    names = [o.name for o in rig.children_recursive]
    print(cid, "PARTS", names)
    for ob in rig.children_recursive:
        if ob.type != "MESH":
            continue
        for key, rgb in table.items():
            if key.lower() not in ob.name.lower():
                continue
            for slot in ob.material_slots:
                if not slot.material or not slot.material.use_nodes:
                    continue
                slot.material = slot.material.copy()
                nt = slot.material.node_tree
                for n in nt.nodes:
                    if n.type == "BSDF_PRINCIPLED":
                        for l in list(n.inputs["Base Color"].links):
                            nt.links.remove(l)
                        n.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1)
            print(cid, "tinted", ob.name, rgb)


rigs = {}
for cid, ch in STORY["characters"].items():
    if "look" not in ch:
        continue  # narrator has no body
    body, rig = human(cid, ch["look"])
    tint(rig, cid, ch["look"].get("tint", {}))
    rigs[cid] = rig
bpy.context.view_layer.update()

# ---------- posing ----------
ARM_BONES = ["upperarm01", "upperarm02", "lowerarm01", "lowerarm02"]


def aim(rig, bone, direction):
    pb = rig.pose.bones[bone]
    cur = (pb.tail - pb.head).normalized()
    q = cur.rotation_difference(Vector(direction).normalized())
    m = pb.matrix.copy()
    loc = m.translation.copy()
    nm = q.to_matrix().to_4x4() @ m
    nm.translation = loc
    pb.matrix = nm
    bpy.context.view_layer.update()


def snapshot(rig, bones):
    return {b: rig.pose.bones[b].rotation_quaternion.copy() for b in bones}


def restore(rig, snap):
    for b, q in snap.items():
        rig.pose.bones[b].rotation_quaternion = q
    bpy.context.view_layer.update()


def setup_rig(rig):
    for pb in rig.pose.bones:
        pb.rotation_mode = "QUATERNION"
    for side, sx in (("L", 1), ("R", -1)):
        aim(rig, f"upperarm01.{side}", (sx * 0.18 * ARM_SIDE, 0.02, -1))
        aim(rig, f"upperarm02.{side}", (sx * 0.18 * ARM_SIDE, 0.02, -1))
        aim(rig, f"lowerarm01.{side}", (sx * 0.12 * ARM_SIDE, -0.35, -1))
        aim(rig, f"lowerarm02.{side}", (sx * 0.12 * ARM_SIDE, -0.35, -1))
    bones = [f"{b}.{s}" for b in ARM_BONES for s in "LR"]
    base = snapshot(rig, bones)
    # point: right arm points forward
    aim(rig, "upperarm01.R", (-0.25, -0.75, -0.45))
    aim(rig, "upperarm02.R", (-0.25, -0.75, -0.45))
    aim(rig, "lowerarm01.R", (-0.1, -1, -0.05))
    aim(rig, "lowerarm02.R", (-0.1, -1, -0.05))
    g_point = snapshot(rig, bones)
    restore(rig, base)
    # open: both forearms forward
    for side, sx in (("L", 1), ("R", -1)):
        aim(rig, f"lowerarm01.{side}", (sx * 0.3, -1, -0.15))
        aim(rig, f"lowerarm02.{side}", (sx * 0.3, -1, -0.15))
    g_open = snapshot(rig, bones)
    restore(rig, base)
    return bones, base, {"point": g_point, "open": g_open}


def smooth(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def local(axis, ang):
    return Quaternion(axis, ang)


def animate(rig, cid, bones, base, gests, phase):
    head = rig.pose.bones["head"]
    jaw = rig.pose.bones["jaw"]
    spine = rig.pose.bones["spine03"]
    neck = rig.pose.bones["neck02"]
    h0, j0, s0, n0 = head.rotation_quaternion.copy(), jaw.rotation_quaternion.copy(), spine.rotation_quaternion.copy(), neck.rotation_quaternion.copy()
    rnd = random.Random(int(phase * 100))
    blinks, bt = [], rnd.uniform(0.5, 2.0)
    while bt < TL["frames"] / FPS:
        blinks.append(bt); bt += rnd.uniform(2.2, 5.0)
    lids = [(rig.pose.bones[n], rig.pose.bones[n].rotation_quaternion.copy()) for n in ("orbicularis03.L", "orbicularis03.R") if n in rig.pose.bones]
    print(cid, "eyelid bones", len(lids))
    hips = rig.pose.bones.get("spine05")
    p0 = hips.rotation_quaternion.copy() if hips else None
    mine = [ln for ln in TL["lines"] if ln["who"] == cid]
    others = [ln for ln in TL["lines"] if ln["who"] not in (cid, "narrator", "none")]
    for f in range(1, TL["frames"] + 1):
        t = (f - 1) / FPS
        env = 0.0
        w = {"point": 0.0, "open": 0.0}
        for ln in mine:
            if ln["start"] <= t < ln["end"]:
                k = int((t - ln["start"]) * FPS)
                env = ln["env"][min(k, len(ln["env"]) - 1)]
            g = ln.get("gesture", "none")
            if g in w:
                w[g] = max(w[g], smooth((t - ln["start"] + 0.1) / 0.4) * (1 - smooth((t - ln["end"] + 0.1) / 0.5)))
        other = 0.0
        for ln in others:
            if ln["start"] <= t < ln["end"] + 0.3:
                other = 1.0
        breathe = math.sin(t * 2 * math.pi / 3.8 + phase)
        spine.rotation_quaternion = s0 @ local((1, 0, 0), 0.015 * breathe)
        neck.rotation_quaternion = n0 @ local((0, 0, 1), 0.03 * math.sin(t * 0.7 + phase))
        nod = env * 0.07 + 0.02 * math.sin(t * 4.3 + phase) * (1 if env > 0.05 else 0.3)
        nod += other * 0.035 * max(0.0, math.sin(t * 2 * math.pi / 1.7 + phase)) ** 3
        turn = 0.025 * math.sin(t * 1.1 + phase)
        tilt = other * 0.04 * math.sin(t * 0.5 + phase)
        head.rotation_quaternion = h0 @ local((1, 0, 0), nod) @ local((0, 1, 0), turn) @ local((0, 0, 1), tilt)
        if hips:
            hips.rotation_quaternion = p0 @ local((0, 1, 0), 0.018 * math.sin(t * 2 * math.pi / 7.0 + phase))
        bl = 0.0
        for bt in blinks:
            d = t - bt
            if 0 <= d < 0.18:
                bl = 1 - abs(d - 0.09) / 0.09
        for lid, q0 in lids:
            lid.rotation_quaternion = q0 @ local((1, 0, 0), 0.45 * bl)
        jaw.rotation_quaternion = j0 @ local((1, 0, 0), JAW_SIGN * 0.28 * env)
        for b in bones:
            q = base[b].slerp(gests["open"][b], w["open"])
            q = q.slerp(gests["point"][b], w["point"])
            rig.pose.bones[b].rotation_quaternion = q
        for pb in [head, jaw, spine, neck] + ([hips] if hips else []) + [l for l, _ in lids] + [rig.pose.bones[b] for b in bones]:
            pb.keyframe_insert("rotation_quaternion", frame=f)


for n, (cid, rig) in enumerate(rigs.items()):
    bones, base, gests = setup_rig(rig)
    animate(rig, cid, bones, base, gests, 1.7 * n)

# head heights (used for cameras)
for rig in rigs.values():
    rig.location = (0, 0, 0)
bpy.context.view_layer.update()
HZ = {cid: (rig.matrix_world @ rig.pose.bones["head"].head).z + 0.06 for cid, rig in rigs.items()}
print("HEAD HEIGHTS", HZ)

# ---------- world ----------
scn = bpy.context.scene
world = bpy.data.worlds.new("W")
scn.world = world
world.use_nodes = True
nt = world.node_tree
bg = nt.nodes["Background"]
if HDRI and os.path.exists(HDRI):
    envn = nt.nodes.new("ShaderNodeTexEnvironment")
    envn.image = bpy.data.images.load(HDRI)
    nt.links.new(envn.outputs["Color"], bg.inputs["Color"])
    bg.inputs["Strength"].default_value = 0.8
else:
    bg.inputs["Color"].default_value = (0.05, 0.06, 0.08, 1)


# ---------- sets (simple 3D rooms and streets, one per scene, 40 m apart) ----------
def mat(name, color, rough=0.6, emit=0.0, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (color[0], color[1], color[2], 1)
    b.inputs["Roughness"].default_value = rough
    b.inputs["Metallic"].default_value = metal
    if emit > 0:
        b.inputs["Emission Color"].default_value = (color[0], color[1], color[2], 1)
        b.inputs["Emission Strength"].default_value = emit
    return m


def box(name, loc, dims, m):
    bpy.ops.mesh.primitive_cube_add(size=1, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = dims
    o.data.materials.append(m)
    return o


def plane(loc, size, m):
    bpy.ops.mesh.primitive_plane_add(size=size, location=loc)
    o = bpy.context.object
    o.data.materials.append(m)
    return o


def build_set(kind, ox, seed):
    rnd = random.Random(seed)
    if kind == "street":
        plane((ox, 0, 0), 38, mat("asphalt", (0.07, 0.07, 0.08), 0.8))
        box("sidewalk", (ox, 3.0, 0.015), (30, 5, 0.03), mat("sidewalk", (0.33, 0.32, 0.30), 0.85))
        pal = [(0.45, 0.40, 0.36), (0.32, 0.36, 0.42), (0.52, 0.46, 0.38), (0.28, 0.30, 0.33), (0.6, 0.55, 0.5)]
        for k in range(-3, 4):
            h = rnd.uniform(6, 14)
            box(f"bld{k}", (ox + k * 4.6, 9.5, h / 2), (4.2, 4, h), mat(f"b{k}", rnd.choice(pal), 0.7))
    elif kind == "car":
        plane((ox, 0, 0), 6, mat("carfloor", (0.03, 0.03, 0.035), 0.5))
        door = mat("door", (0.06, 0.06, 0.07), 0.45)
        box("doorL", (ox - 1.0, 0.3, 0.9), (0.08, 2.6, 1.0), door)
        box("doorR", (ox + 1.0, 0.3, 0.9), (0.08, 2.6, 1.0), door)
        box("window", (ox, 1.5, 1.5), (2.4, 0.03, 1.0), mat("win", (0.7, 0.8, 0.9), 0.3, emit=3.0))
        box("headrest", (ox, 0.55, 1.2), (0.45, 0.22, 0.32), mat("seat", (0.04, 0.04, 0.045), 0.4))
    else:  # office, office_desk
        plane((ox, 0, 0), 12, mat("wood", (0.25, 0.15, 0.08), 0.35))
        wall = mat("wall", (0.75, 0.74, 0.70), 0.8)
        box("back", (ox, 2.5, 1.7), (7, 0.1, 3.4), wall)
        box("sideL", (ox - 3.0, 0, 1.7), (0.1, 6, 3.4), wall)
        box("sideR", (ox + 3.0, 0, 1.7), (0.1, 6, 3.4), wall)
        box("window", (ox + 0.9, 2.43, 1.7), (1.7, 0.03, 1.3), mat("officewin", (1.0, 0.95, 0.85), 0.3, emit=6.0))
        box("shelf", (ox - 1.7, 2.3, 1.0), (1.2, 0.3, 2.0), mat("shelf", (0.12, 0.07, 0.04), 0.5))
        if kind == "office_desk":
            box("desk", (ox + 0.55, -0.45, 0.375), (1.5, 0.8, 0.75), mat("desk", (0.18, 0.1, 0.05), 0.35))
            box("laptop", (ox + 0.55, -0.45, 0.77), (0.38, 0.26, 0.03), mat("lap", (0.12, 0.12, 0.13), 0.3, metal=0.6))
    # lights
    def light(name, loc, energy, size, color=(1, 1, 1)):
        d = bpy.data.lights.new(name, "AREA")
        d.energy, d.size, d.color = energy, size, color
        o = bpy.data.objects.new(name, d)
        scn.collection.objects.link(o)
        o.location = loc
        o.rotation_euler = (Vector((ox, 0, 1.4)) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()

    light("key", (ox - 1.6, -2.4, 2.6), 260, 1.8, (1, 0.93, 0.85))
    light("fill", (ox + 2.0, -2.2, 1.8), 90, 2.5, (0.85, 0.9, 1))
    light("rimL", (ox - 1.5, 2.0, 2.2), 180, 1.0, (1, 0.8, 0.6))
    light("rimR", (ox + 1.5, 2.0, 2.2), 180, 1.0, (0.7, 0.8, 1))


# ---------- cameras and scene timing ----------
SLOTS = {"left": ((-0.42, 0, 0), 68), "right": ((0.42, 0, 0), -68), "center": ((0, 0, 0), 0)}
CLOSE_OFF = {"left": (0.95, -1.15), "right": (-0.95, -1.15), "center": (0.2, -1.2)}


def camera(name, loc, target, lens):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.dof.use_dof = True
    cd.dof.focus_distance = (Vector(target) - Vector(loc)).length
    cd.dof.aperture_fstop = 2.2
    o = bpy.data.objects.new(name, cd)
    scn.collection.objects.link(o)
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    return o


SC = STORY["scenes"]
starts = [int(s["start"] * FPS) + 1 for s in TL["scenes"]]
ends = [starts[i + 1] - 1 for i in range(len(starts) - 1)] + [TL["frames"]]
marker_cam = {}
scene_cams = []

for si, sc in enumerate(SC):
    ox = si * 40.0
    build_set(sc["set"], ox, si)
    cast = sc["cast"]
    close, mid = {}, {}
    for cid, slot in cast.items():
        (sx, sy, _), _rot = SLOTS[slot]
        tgt = Vector((ox + sx, sy, HZ[cid]))
        off = CLOSE_OFF[slot] if len(cast) > 1 else CLOSE_OFF["center"]
        close[cid] = camera(f"close_{si}_{cid}", tgt + Vector((off[0], off[1], 0)), tgt, 70)
        mid[cid] = camera(f"mid_{si}_{cid}", tgt + Vector((-0.25, -2.1, -0.3)), tgt - Vector((0, 0, 0.35)), 45)
    cx = sum(SLOTS[s][0][0] for s in cast.values()) / max(1, len(cast))
    if sc["set"] == "car":
        wide = mid[next(iter(cast))]
    else:
        wide = camera(f"wide_{si}", Vector((ox + cx, -3.4, 1.2)), Vector((ox + cx, 0, 1.0)), 35)
        wide.keyframe_insert("location", frame=starts[si])
        wide.location += Vector((0, 0.6, 0.03))
        wide.keyframe_insert("location", frame=max(ends[si], starts[si] + 1))
    scene_cams.append((close, mid, wide))

# which camera for each line
speak_count = {}
for ln in TL["lines"]:
    si = ln["scene"]
    close, mid, wide = scene_cams[si]
    cast = SC[si]["cast"]
    who, sh = ln["who"], ln.get("shot", "")
    if who in cast:
        c = speak_count.get((si, who), 0)
        speak_count[(si, who)] = c + 1
        cam = mid[who] if (len(cast) == 1 and c % 2 == 1) else close[who]
    elif sh in cast:
        cam = close[sh]
    else:
        cam = wide
    first = ln is next(l for l in TL["lines"] if l["scene"] == si)
    f = starts[si] if first else max(starts[si] + 1, int((ln["start"] - 0.25) * FPS))
    marker_cam[f] = cam

for f, cam in sorted(marker_cam.items()):
    scn.timeline_markers.new(f"m{f}", frame=max(1, f)).camera = cam
scn.camera = scene_cams[0][2]

# ---------- place characters per scene (hidden far below the floor when not in a scene) ----------
for si, sc in enumerate(SC):
    for cid, rig in rigs.items():
        if cid in sc["cast"]:
            (sx, sy, _), rot = SLOTS[sc["cast"][cid]]
            loc, rz = (si * 40.0 + sx, sy, 0.0), math.radians(rot)
        else:
            loc, rz = (si * 40.0, 0.0, -200.0), 0.0
        rig.location = loc
        rig.rotation_euler = (0, 0, rz)
        for f in (starts[si], max(ends[si], starts[si])):
            rig.keyframe_insert("location", frame=f)
            rig.keyframe_insert("rotation_euler", frame=f)

# ---------- render settings ----------
scn.render.engine = "CYCLES"
scn.cycles.device = "CPU"
scn.cycles.samples = int(A.get("--samples", "24"))
scn.cycles.use_denoising = True
scn.cycles.max_bounces = 3
scn.cycles.diffuse_bounces = 2
scn.cycles.glossy_bounces = 2
scn.cycles.transparent_max_bounces = 6
scn.cycles.adaptive_threshold = 0.05
scn.render.film_transparent = False
scn.cycles.use_adaptive_sampling = True
scn.render.use_persistent_data = True
scn.render.resolution_x, scn.render.resolution_y = 720, 1280
scn.render.fps = FPS
scn.view_settings.view_transform = "AgX"
scn.view_settings.look = "AgX - Medium High Contrast"
scn.render.image_settings.file_format = "PNG"
scn.frame_start = 1
scn.frame_end = TL["frames"]

os.makedirs(OUT, exist_ok=True)
if "--still" in A:
    # one test picture from the middle of every scene
    for si in range(len(SC)):
        f = (starts[si] + ends[si]) // 2
        scn.frame_set(f)
        scn.render.filepath = os.path.join(OUT, f"still_scene{si + 1:02d}_{f:05d}.png")
        bpy.ops.render.render(write_still=True)
        print("still", si + 1, flush=True)
else:
    for f in range(int(A["--start"]), min(int(A["--end"]), TL["frames"]) + 1):
        scn.frame_set(f)
        scn.render.filepath = os.path.join(OUT, f"{f:05d}.png")
        bpy.ops.render.render(write_still=True)
        print("rendered", f, flush=True)
