# Story Studio v2

Free 3D story video maker. Many characters, many scenes.
Voices: Kokoro. People: MakeHuman (free). Drawing: Blender. Joining: FFmpeg. Runs on GitHub Actions.

## How to run
1. Actions tab, choose "Produce episode", press Run workflow.
2. First set mode to `still`. You get one test picture per scene.
3. If the pictures look good, run again with mode `full`.

## Make a new story
1. Copy story/kindness-destiny.json to a new name.
2. Change the title, characters, scenes and lines.
3. Type the new file path in the "episode" box when you run the workflow.

## Story file in short
- characters: voice, subtitle colour, and a "look" (age, body, clothes, hair, colours).
- scenes: "set" is street, car, office or office_desk.
- cast: who is in the scene and where: left, right or center.
- items: a spoken line, or a pause in seconds. "shot" names who the camera should show.
- gesture: none, open or point.
