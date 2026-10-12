# DungeonFall 3D

A third-person Python/Ursina dungeon game with camera-relative movement,
melee combat, room progression and a darker PBR fantasy-dungeon presentation.

## Run

```powershell
python -m pip install -r requirements.txt
python main.py
```

The game now starts directly in Room 1 so you immediately see the 3D dungeon.

## Controls

- **WASD / Arrow keys** — walk relative to the current camera angle
- **Shift + movement** — sprint / run
- **Mouse** — rotate the camera around the player
- **J / L** — rotate camera left/right (keyboard fallback)
- **I / K** — tilt camera up/down (keyboard fallback)
- **Mouse wheel** — zoom in/out
- **C** — release/capture the mouse cursor
- **F10** — toggle fullscreen / windowed mode
- **Space / Left mouse** — sword attack
- **Hold F, release** — charged left-hand punch (longer hold = more damage)
- **Hold G, release** — charged flying kick (longer hold = more damage/travel)
- **1 / 2 / 3** — three different dance / celebration moves
- **Esc** — pause / resume
- **R** — restart after winning or losing
- **Enter** — return to menu from win/lose screens
- **Q** — quit from menu/end screen

## Current gameplay

- Four enlarged 32x20-unit 3D dungeon rooms
- Close third-person camera rig with free horizontal/vertical rotation
- 6.4-unit default camera distance and 4.2-unit user zoom floor, with
  obstruction-aware orbit recovery that swings around close walls/corners
  instead of letting geometry block the player
- Camera-relative movement
- Mouse + keyboard camera controls, mouse-wheel zoom, wall-aware pull-in and
  automatic clear-view camera angle recovery near walls/cover
- SimplePBR renderer with 2x MSAA, tone mapping, multiple lights, 2048px shadows and fog
- 2K CC0 Poly Haven stone wall/floor diffuse + normal + ARM materials
- Tangent-ready dungeon shell so normal maps react correctly to lighting
- High-detail AutoSprite CC0 humanoid rigs for the player and enemies, optimized
  for CPU skinning while retaining their 4K character textures
- CPU-skinned procedural skeletal posing with visible idle, walk, sprint,
  sword-swing, charged punch, flying kick, hit-reaction and three dance states; normal movement walks instead of sliding
- Adaptive enemy pose refresh rates keep later rooms smooth while AI, movement,
  collision and combat still update every frame
- Quaternius CC0 Gothic architecture and authored room props
- Kenney CC0 supplemental dungeon/weapon assets
- Animated torch flames/light flicker and authored room dressing
- Permanent right-hand PBR sword that stays visible in idle/walk/run/dance,
  with a measured 210-degree world-space attack arc and body-safe carry poses
- Melee collision follows the rendered blade base/tip path (with low-FPS sweep
  interpolation) instead of an invisible forward hit zone
- Punch and flying-kick collision follow the evaluated left-fist/right-foot
  skeleton markers with active strike windows, low-FPS interpolation and one hit per action
- Hold-to-charge punch/kick system with a live charge meter; punch scales from
  12→44 damage and flying kick from 20→68 damage before auto-releasing at full power
- Flying kick uses collision-safe forward root travel plus an airborne arc, then
  lands with dust/camera feedback; walls and enemies stop the root instead of allowing tunneling
- Player and enemies use a 100-HP baseline and every hit spawns a floating
  `-damage  HP remaining/100` number above the target
- Player hit feedback stays in-world: brief red character tint, compact red
  particles and a small camera impulse instead of a screen-covering rectangle
- Lethal damage plays a full falling death sequence, freezes combat/AI during
  the collapse, holds the corpse on the floor, then shows a compact YOU FELL panel
- Sword slash, hit/death/pickup particles and animated portal
- Two enemy types with chase/contact AI
- Body collision between player/enemies so characters cannot overlap or tunnel through one another
- One hit per enemy per sword swing
- Coins and health drops
- 55% enemy health-drop chance
- Extra random health pickups every 8–13 seconds during combat
- Locked room exits until enemies are defeated
- Final-room victory trigger
- HUD, pause, death, victory and restart states

## Art license

The environment uses selected models from **Quaternius – Ultimate Modular
Ruins**, released under **CC0**. The selected OBJ/MTL sources used by the
project are stored under:

`third_party/quaternius_selected/`

The live character visuals use selected models from the **AutoSprite Free 3D
Models** library, released under **CC0**. The repository includes the optimized
Panda3D runtime BAMs required to play the game under:

`assets3d/detailed_characters/`

The much larger downloaded/processed AutoSprite source and conversion caches are
kept out of Git so the repository stays practical to clone. The preparation
scripts remain in the project for development/reference.

Supplemental weapon and dungeon assets come from **Kenney Mini Dungeon**,
also **CC0**. The original pack and `License.txt` are stored under:

`third_party/kenney_mini_dungeon/`

The main wall/floor materials use the **CC0 Poly Haven** assets
`stone_brick_wall_001` and `square_floor`; their 2K diffuse, OpenGL normal and
ARM (ambient-occlusion / roughness / metallic) runtime maps live in
`assets3d/pbr/`.

Additional VFX/procedural helper textures in `assets3d/` are generated locally
by `generate_3d_assets.py`.

`prepare_quaternius_assets.py` converts legacy OBJ/MTL material groups into
Panda3D BAM parts with PBR base colors, so the authored colors survive the
SimplePBR pipeline.

`prepare_knight_assets.py` preserves the older helper weapon pieces, while
`prepare_pbr_maps.py` creates the neutral fallback maps used by SimplePBR on
legacy meshes.

### Repository size note

The local development workspace can contain more than 1 GB of intermediate 3D
conversion data. `.gitignore` intentionally excludes those generated and
experimental files while keeping the runtime assets needed by `python main.py`.
