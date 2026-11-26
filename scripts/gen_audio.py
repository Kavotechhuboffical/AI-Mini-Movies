"""Make voices with Kokoro (free, offline) and a timeline for Blender.

Usage: python gen_audio.py story.json out_dir
Story items: {"who": "woman", "text": "...", "gesture": "open|point|none", "shot": "..."}
             {"pause": 1.5, "shot": "woman"}   (silent moment)
"""
import json, sys, os
import numpy as np
import soundfile as sf
from kokoro import KPipeline

FPS = 24
SR = 24000
story = json.load(open(sys.argv[1]))
out = sys.argv[2]
os.makedirs(out, exist_ok=True)

# The end card is a silent hold added to the last scene
if story.get("end_card"):
    last = story["scenes"][-1]
    last["items"].append({"pause": 3.5, "card": story["end_card"], "shot": last.get("end_shot", "")})

pipe = KPipeline(lang_code="a")
LEAD, GAP, TAIL = 0.6, 0.35, 0.8
t = LEAD
mix = [np.zeros(int(LEAD * SR), dtype=np.float32)]
timeline = {"fps": FPS, "lines": [], "scenes": []}
n = 0
for si, sc in enumerate(story["scenes"]):
    scene_start = 0.0 if si == 0 else t
    items = sc["items"]
    for k, it in enumerate(items):
        if "pause" in it:
            dur = float(it["pause"])
            mix.append(np.zeros(int(dur * SR), dtype=np.float32))
            timeline["lines"].append({"who": "none", "text": "", "gesture": "none", "shot": it.get("shot", ""),
                                      "card": it.get("card", ""), "scene": si, "start": t, "end": t + dur, "env": [0.0]})
            t += dur
            continue
        ch = story["characters"][it["who"]]
        chunks = [a.numpy() if hasattr(a, "numpy") else np.asarray(a)
                  for _, _, a in pipe(it["text"], voice=ch["voice"], speed=ch.get("speed", 0.95))]
        audio = np.concatenate(chunks).astype(np.float32)
        sf.write(f"{out}/line{n:02d}.wav", audio, SR)
        n += 1
        dur = len(audio) / SR
        spf = SR // FPS
        env = [float(np.sqrt(np.mean(audio[j:j + spf] ** 2))) for j in range(0, len(audio), spf)]
        peak = max(env) or 1.0
        env = [min(1.0, e / (peak * 0.7)) for e in env]
        timeline["lines"].append({"who": it["who"], "text": it["text"], "gesture": it.get("gesture", "none"),
                                  "shot": it.get("shot", ""), "card": "", "scene": si,
                                  "start": t, "end": t + dur, "env": env})
        mix.append(audio)
        gap = GAP
        if k + 1 < len(items) and items[k + 1].get("who") == "narrator":
            gap += 0.4
        mix.append(np.zeros(int(gap * SR), dtype=np.float32))
        t += dur + gap
    timeline["scenes"].append({"start": scene_start, "end": t})

mix.append(np.zeros(int(TAIL * SR), dtype=np.float32))
t += TAIL
timeline["scenes"][-1]["end"] = t
full = np.concatenate(mix)
sf.write(f"{out}/dialogue.wav", full, SR)
timeline["duration"] = len(full) / SR
timeline["frames"] = int(timeline["duration"] * FPS) + 1
json.dump(timeline, open(f"{out}/timeline.json", "w"), indent=1)
print("duration", timeline["duration"], "frames", timeline["frames"], "scenes", len(timeline["scenes"]))
