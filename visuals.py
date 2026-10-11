from __future__ import annotations

import json
import math
from pathlib import Path

from panda3d.core import (
    Filename,
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexArrayFormat,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    InternalName,
    Material,
    NodePath,
    SamplerState,
    TexturePool,
    TextureStage,
)
from direct.actor.Actor import Actor
from ursina import Entity, PointLight, Texture as UrsinaTexture, Vec3, color, scene
from ursina.shaders import unlit_shader


ROOT = Path(__file__).resolve().parent
ASSET_DIR = ROOT / "assets3d"
# Ursina's loader on Windows resolves model strings relative to the asset
# folder more reliably than absolute paths containing spaces.
KENNEY_OBJ_DIR = Path("third_party") / "kenney_mini_dungeon" / "Models" / "OBJ format"
KENNEY_TEXTURE = KENNEY_OBJ_DIR / "Textures" / "colormap.png"
DERIVED_KENNEY_DIR = Path("assets3d") / "kenney"
KENNEY_BAM_DIR = Path("assets3d") / "bam"
RUINS_BAM_DIR = Path("assets3d") / "ruins_bam"
QUATERNIUS_MANIFEST_PATH = ROOT / "assets3d" / "quaternius_manifest.json"
QUATERNIUS_MANIFEST = json.loads(QUATERNIUS_MANIFEST_PATH.read_text(encoding="utf-8")) if QUATERNIUS_MANIFEST_PATH.exists() else {}
KNIGHT_MANIFEST_PATH = ROOT / "assets3d" / "knight_manifest.json"
KNIGHT_MANIFEST = json.loads(KNIGHT_MANIFEST_PATH.read_text(encoding="utf-8")) if KNIGHT_MANIFEST_PATH.exists() else {}
PIRATE_BAM_DIR = Path("assets3d") / "pirates"
DETAILED_CHARACTER_DIR = Path("assets3d") / "detailed_characters"

NORMAL_STAGE = TextureStage("normal")
NORMAL_STAGE.set_mode(TextureStage.M_normal)
SELECTOR_STAGE = TextureStage("selector")
SELECTOR_STAGE.set_mode(TextureStage.M_selector)


def _pbr_texture(path: str, *, srgb: bool = False):
    filename = Filename.from_os_specific(str(ROOT / path))
    texture = TexturePool.load_texture(filename)
    if texture:
        if srgb:
            texture.set_format(texture.F_srgb_alpha if texture.get_num_components() == 4 else texture.F_srgb)
        texture.set_wrap_u(SamplerState.WM_repeat)
        texture.set_wrap_v(SamplerState.WM_repeat)
        texture.set_minfilter(SamplerState.FT_linear_mipmap_linear)
        texture.set_magfilter(SamplerState.FT_linear)
        texture.set_anisotropic_degree(8)
    return texture


FLAT_NORMAL = _pbr_texture("assets3d/pbr/flat_normal.png")


def _build_tangent_cube() -> NodePath:
    """Create a unit cube with UVs, normals and glTF-style vec4 tangents.

    Ursina's stock cube has no tangent column. SimplePBR needs a vec4 tangent
    to transform normal maps correctly, so the dungeon shell uses this mesh.
    """
    array = GeomVertexArrayFormat()
    array.add_column(InternalName.get_vertex(), 3, Geom.NT_float32, Geom.C_point)
    array.add_column(InternalName.get_texcoord(), 2, Geom.NT_float32, Geom.C_texcoord)
    array.add_column(InternalName.get_normal(), 3, Geom.NT_float32, Geom.C_normal)
    array.add_column(InternalName.get_tangent(), 4, Geom.NT_float32, Geom.C_vector)
    fmt = GeomVertexFormat()
    fmt.add_array(array)
    fmt = GeomVertexFormat.register_format(fmt)

    data = GeomVertexData("tangent_cube", fmt, Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    texcoord = GeomVertexWriter(data, "texcoord")
    normal = GeomVertexWriter(data, "normal")
    tangent = GeomVertexWriter(data, "tangent")
    tris = GeomTriangles(Geom.UH_static)

    faces = (
        # normal, tangent(x,y,z,w), p00, p10, p11, p01
        ((0, 0, 1), (1, 0, 0, 1), (-.5, -.5, .5), (.5, -.5, .5), (.5, .5, .5), (-.5, .5, .5)),
        ((0, 0, -1), (-1, 0, 0, 1), (.5, -.5, -.5), (-.5, -.5, -.5), (-.5, .5, -.5), (.5, .5, -.5)),
        ((1, 0, 0), (0, 0, -1, 1), (.5, -.5, .5), (.5, -.5, -.5), (.5, .5, -.5), (.5, .5, .5)),
        ((-1, 0, 0), (0, 0, 1, 1), (-.5, -.5, -.5), (-.5, -.5, .5), (-.5, .5, .5), (-.5, .5, -.5)),
        ((0, 1, 0), (1, 0, 0, -1), (-.5, .5, -.5), (.5, .5, -.5), (.5, .5, .5), (-.5, .5, .5)),
        ((0, -1, 0), (1, 0, 0, -1), (-.5, -.5, .5), (.5, -.5, .5), (.5, -.5, -.5), (-.5, -.5, -.5)),
    )
    uvs = ((0, 0), (1, 0), (1, 1), (0, 1))
    index = 0
    for face_normal, face_tangent, *points in faces:
        for point, uv in zip(points, uvs):
            vertex.add_data3(*point)
            texcoord.add_data2(*uv)
            normal.add_data3(*face_normal)
            tangent.add_data4(*face_tangent)
        tris.add_vertices(index, index + 1, index + 2)
        tris.add_vertices(index, index + 2, index + 3)
        index += 4

    geom = Geom(data)
    geom.add_primitive(tris)
    node = GeomNode("tangent_cube")
    node.add_geom(geom)
    return NodePath(node)


TANGENT_CUBE = _build_tangent_cube()


def tangent_cube_entity(**kwargs) -> Entity:
    """Create a PBR-ready cube that can use real tangent-space normal maps."""
    kwargs.setdefault("model", TANGENT_CUBE.copy_to(NodePath("tangent_cube_instance")))
    return lit_entity(**kwargs)


def apply_surface_maps(entity: Entity, normal_map: str | None = None, selector_map: str | None = None) -> Entity:
    """Attach SimplePBR semantic textures without disturbing base-color UVs."""
    normal = _pbr_texture(normal_map) if normal_map else FLAT_NORMAL
    if normal:
        entity.set_texture(NORMAL_STAGE, normal, 20)
    if selector_map:
        selector = _pbr_texture(selector_map)
        if selector:
            entity.set_texture(SELECTOR_STAGE, selector, 20)
    return entity


def c255(r: int, g: int, b: int, a: int = 255):
    return color.rgba(r / 255, g / 255, b / 255, a / 255)


def lit_entity(**kwargs) -> Entity:
    """Create a world entity that inherits the global SimplePBR shader."""
    roughness = kwargs.pop("roughness", 0.78)
    metallic = kwargs.pop("metallic", 0.0)
    normal_map = kwargs.pop("normal_map", None)
    selector_map = kwargs.pop("selector_map", None)
    base_color = kwargs.pop("color", color.white)
    texture = kwargs.get("texture")
    if isinstance(texture, str):
        candidate = ROOT / texture
        if candidate.exists():
            panda_texture = _pbr_texture(texture, srgb=True)
            if panda_texture:
                kwargs["texture"] = UrsinaTexture(panda_texture)
    kwargs["color"] = base_color
    entity = Entity(**kwargs)
    material = Material()
    material.set_base_color(color.white)
    material.set_roughness(roughness)
    material.set_metallic(metallic)
    entity.set_material(material, 1)
    return apply_surface_maps(entity, normal_map, selector_map)


def kenney_entity(model_name: str, **kwargs) -> Entity:
    """Load one CC0 Kenney Mini Dungeon OBJ with the shared color map."""
    kwargs.setdefault("model", (KENNEY_BAM_DIR / f"{model_name}.bam").as_posix())
    kwargs.setdefault("texture", KENNEY_TEXTURE.as_posix())
    return apply_surface_maps(Entity(**kwargs))


def derived_kenney_entity(model_name: str, **kwargs) -> Entity:
    kwargs.setdefault("model", (KENNEY_BAM_DIR / f"{model_name}.bam").as_posix())
    kwargs.setdefault("texture", KENNEY_TEXTURE.as_posix())
    return apply_surface_maps(Entity(**kwargs))


def ruins_entity(model_name: str, **kwargs) -> Entity:
    """Load one precompiled Quaternius CC0 modular-ruins model."""
    kwargs.setdefault("model", (RUINS_BAM_DIR / f"{model_name}.bam").as_posix())
    base_color = kwargs.pop("color", c255(72, 76, 88))
    kwargs["color"] = base_color
    entity = Entity(**kwargs)
    material = Material()
    material.set_base_color(color.white)
    material.set_roughness(0.86)
    material.set_metallic(0.0)
    entity.set_material(material, 1)
    return apply_surface_maps(entity)


def quaternius_entity(model_name: str, **kwargs) -> Entity:
    """Compose a Quaternius model from material-split BAM children.

    SimplePBR expects Panda3D ``base_color`` materials. The source OBJ/MTL
    files only provide legacy diffuse values, so ``prepare_quaternius_assets``
    bakes each material group into its own BAM and this helper rebuilds the
    authored color palette at runtime.
    """
    material_tint = kwargs.pop("material_tint", (1.0, 1.0, 1.0, 1.0))
    root = Entity(**kwargs)
    for part in QUATERNIUS_MANIFEST.get(model_name, []):
        rgba = part.get("color", [1.0, 1.0, 1.0, 1.0])
        tinted = [
            max(0.0, min(1.0, rgba[i] * material_tint[i]))
            for i in range(4)
        ]
        tint = color.rgba(*tinted)
        material_name = str(part.get("material", ""))
        child = Entity(parent=root, model=part["bam"], color=tint)
        material = Material()
        material.set_base_color(color.white)
        if "Metal" in material_name:
            material.set_metallic(0.78)
            material.set_roughness(0.34)
        elif material_name in {"Eye", "Pupil"}:
            material.set_metallic(0.0)
            material.set_roughness(0.30)
        else:
            material.set_metallic(0.0)
            material.set_roughness(0.78)
        if material_name in {"Fire", "Light"}:
            material.set_emission(tint)
        child.set_material(material, 1)
        apply_surface_maps(child)
    return root


def knight_entity(model_name: str, **kwargs) -> Entity:
    """Compose the CC0 Quaternius knight pieces with substance-aware PBR materials."""
    palette = kwargs.pop("palette", {})
    root = Entity(**kwargs)
    material_parts: list[Entity] = []
    for part in KNIGHT_MANIFEST.get(model_name, []):
        rgba = part.get("color", [1.0, 1.0, 1.0, 1.0])
        material_name = str(part.get("material", ""))
        override = palette.get(material_name)
        tint = color.rgba(*(override if override is not None else rgba))
        child = Entity(parent=root, model=part["bam"], color=tint)
        material = Material()
        material.set_base_color(color.white)

        if material_name in {"Armor", "Grey", "DarkGrey", "Metal"}:
            material.set_metallic(0.92)
            material.set_roughness(0.30 if material_name != "DarkGrey" else 0.38)
        elif material_name == "Gold":
            material.set_metallic(0.95)
            material.set_roughness(0.25)
        elif material_name == "Skin":
            material.set_metallic(0.0)
            material.set_roughness(0.62)
        elif material_name in {"Boots", "Brown"}:
            material.set_metallic(0.0)
            material.set_roughness(0.64)
        else:
            material.set_metallic(0.0)
            material.set_roughness(0.75)
        child.set_material(material, 1)
        apply_surface_maps(child)
        material_parts.append(child)
    root.material_parts = material_parts
    return root


class _ProceduralAnimControl:
    """Tiny Actor-compatible control used by the gameplay state machine."""

    def __init__(self, owner: "ProceduralCharacter", name: str) -> None:
        self.owner = owner
        self.name = name

    def isPlaying(self) -> bool:
        return self.owner.is_playing(self.name)


class ProceduralCharacter:
    """High-detail CPU-skinned humanoid with deterministic runtime poses.

    The detailed CC0 meshes import cleanly, but their external animation
    tracks do not deform consistently in Panda's glTF/Assimp bridges.  Direct
    joint control *does* work reliably with CPU skinning, so the game drives a
    small third-person locomotion/action rig itself instead of accepting a
    frozen T-pose or corrupted animation.
    """

    ACTION_DURATIONS = {
        "sword": 0.42,
        "punch": 0.36,
        "kick": 0.68,
        "hit": 0.52,
        "death": 0.85,
        "dance_1": 3.2,
        "dance_2": 3.4,
        "dance_3": 3.0,
    }
    SWORD_SWING_DEGREES = 210.0

    CONTROLLED_JOINTS = (
        "mixamorig:Hips",
        "mixamorig:Spine",
        "mixamorig:Spine1",
        "mixamorig:Spine2",
        "mixamorig:Head",
        "mixamorig:LeftArm",
        "mixamorig:LeftForeArm",
        "mixamorig:LeftHand",
        "mixamorig:RightArm",
        "mixamorig:RightForeArm",
        "mixamorig:RightHand",
        "mixamorig:LeftUpLeg",
        "mixamorig:LeftLeg",
        "mixamorig:LeftFoot",
        "mixamorig:RightUpLeg",
        "mixamorig:RightLeg",
        "mixamorig:RightFoot",
    )

    _instance_counter = 0

    def __init__(
        self,
        model_name: str,
        parent: Entity,
        *,
        scale: float,
        weapon: bool = True,
        tint=None,
        pose_hz: float = 20.0,
    ) -> None:
        ProceduralCharacter._instance_counter += 1
        self.node = Actor((DETAILED_CHARACTER_DIR / f"{model_name}.bam").as_posix())
        self.node.reparentTo(parent)
        self.node.setScale(scale)
        self.part_bundle = self.node.getPartBundle("modelRoot")
        self.base_tint = tint
        if tint is not None:
            self.node.setColorScale(*tint)

        self.joints = {}
        self.base_hpr: dict[str, Vec3] = {}
        for name in self.CONTROLLED_JOINTS:
            joint = self.node.controlJoint(None, "modelRoot", name)
            if joint:
                self.joints[name] = joint
                hpr = joint.getHpr()
                self.base_hpr[name] = Vec3(hpr.x, hpr.y, hpr.z)

        self.weapon = None
        self.weapon_blade_base = None
        self.weapon_blade_tip = None
        self.weapon_guard_left = None
        self.weapon_guard_right = None
        self.punch_contact = None
        self.kick_contact = None
        right_hand_attachment = self.node.exposeJoint(None, "modelRoot", "mixamorig:RightHand")
        left_hand_attachment = self.node.exposeJoint(None, "modelRoot", "mixamorig:LeftHand")
        right_foot_attachment = self.node.exposeJoint(None, "modelRoot", "mixamorig:RightFoot")
        if weapon and right_hand_attachment:
            # Permanent sword: the grip is parented directly to the real hand
            # joint, so idle/walk/run/dance/attack all use the same weapon.
            # The hand's local +Y axis continues away from the forearm, which
            # makes +Y a stable blade axis and prevents the weapon from jumping
            # or disappearing when the pose changes.
            self.weapon = Entity(
                parent=right_hand_attachment,
                position=(0, 0.025, 0),
                # Cant the carried sword outboard/back so the blade clears the
                # thigh and floor in the relaxed pose. The same grip transform
                # is preserved through locomotion, dances and attacks.
                rotation=(-30, 0, -35),
            )
            lit_entity(
                parent=self.weapon,
                model="cube",
                color=c255(91, 48, 31),
                metallic=0.08,
                roughness=0.58,
                position=(0, -0.075, 0),
                scale=(0.046, 0.22, 0.046),
            )
            lit_entity(
                parent=self.weapon,
                model="cube",
                color=c255(176, 133, 57),
                metallic=0.90,
                roughness=0.22,
                position=(0, 0.055, 0),
                scale=(0.06, 0.038, 0.045),
            )
            lit_entity(
                parent=self.weapon,
                model="cube",
                color=c255(203, 218, 235),
                metallic=0.96,
                roughness=0.16,
                position=(0, 0.325, 0),
                scale=(0.044, 0.50, 0.022),
            )
            # Invisible endpoints used by melee physics.  These move with the
            # exact same hand/joint transforms as the rendered blade.
            self.weapon_blade_base = Entity(parent=self.weapon, position=(0, 0.095, 0), visible=False)
            self.weapon_blade_tip = Entity(parent=self.weapon, position=(0, 0.575, 0), visible=False)
            self.weapon_guard_left = Entity(parent=self.weapon, position=(-0.03, 0.055, 0), visible=False)
            self.weapon_guard_right = Entity(parent=self.weapon, position=(0.03, 0.055, 0), visible=False)

        # Physics markers live on the evaluated skeleton, not on controlJoint
        # nodes. Punch uses the empty left hand so the sword remains safely in
        # the right hand; kick uses the right foot. Their world-space paths are
        # sampled by gameplay for real limb contact instead of invisible ranges.
        if left_hand_attachment:
            self.punch_contact = Entity(parent=left_hand_attachment, position=(0, 0.035, 0), visible=False)
        if right_foot_attachment:
            self.kick_contact = Entity(parent=right_foot_attachment, position=(0, 0.055, 0), visible=False)

        self.state = "idle"
        self.elapsed = 0.0
        self.action_remaining = 0.0
        self.charge_ratio = 0.0
        self.action_power = 0.0
        self.pose_hz = max(1.0, pose_hz)
        self.pose_interval = 1.0 / self.pose_hz
        # Stagger different characters so CPU skinning is spread across frames
        # instead of making every visible rig expensive on the same frame.
        phase = (ProceduralCharacter._instance_counter * 0.37) % 1.0
        self.pose_accumulator = self.pose_interval * phase
        self._apply_pose()

    def __bool__(self) -> bool:
        return True

    def setColorScale(self, *args) -> None:
        self.node.setColorScale(*args)

    def set_pose_hz(self, pose_hz: float) -> None:
        """Adjust visual animation rate without changing gameplay timing."""
        pose_hz = max(1.0, float(pose_hz))
        if abs(pose_hz - self.pose_hz) < 0.01:
            return
        self.pose_hz = pose_hz
        self.pose_interval = 1.0 / pose_hz
        self.pose_accumulator = min(self.pose_accumulator, self.pose_interval)

    def clearColorScale(self) -> None:
        if self.base_tint is not None:
            self.node.setColorScale(*self.base_tint)
        else:
            self.node.clearColorScale()

    def weapon_segment_world(self) -> tuple[Vec3, Vec3] | None:
        """Return the rendered blade segment in world/scene coordinates."""
        if not self.weapon_blade_base or not self.weapon_blade_tip:
            return None
        base = self.weapon_blade_base.getPos(scene)
        tip = self.weapon_blade_tip.getPos(scene)
        return Vec3(base.x, base.y, base.z), Vec3(tip.x, tip.y, tip.z)

    def weapon_guard_world(self) -> tuple[Vec3, Vec3] | None:
        """Return the two rendered guard endpoints in world coordinates."""
        if not self.weapon_guard_left or not self.weapon_guard_right:
            return None
        left = self.weapon_guard_left.getPos(scene)
        right = self.weapon_guard_right.getPos(scene)
        return Vec3(left.x, left.y, left.z), Vec3(right.x, right.y, right.z)

    def limb_contact_world(self, action: str) -> Vec3 | None:
        """Return the rendered fist/foot contact point in world coordinates."""
        marker = self.punch_contact if action == "punch" else self.kick_contact if action == "kick" else None
        if not marker:
            return None
        point = marker.getPos(scene)
        return Vec3(point.x, point.y, point.z)

    def loop(self, name: str) -> None:
        if self.state != name or self.action_remaining > 0:
            self.state = name
            self.elapsed = 0.0
        self.action_remaining = 0.0
        self._apply_pose()

    def play(self, name: str) -> None:
        self.state = name
        self.elapsed = 0.0
        self.action_remaining = self.ACTION_DURATIONS.get(name, 0.45)
        self._apply_pose()

    def set_action_power(self, power: float) -> None:
        self.action_power = max(0.0, min(1.0, float(power)))

    def set_charge_pose(self, action: str, ratio: float) -> None:
        if action not in {"punch", "kick"}:
            return
        self.state = f"{action}_charge"
        self.charge_ratio = max(0.0, min(1.0, float(ratio)))
        self.elapsed = 0.0
        self.action_remaining = 0.0
        self.pose_accumulator = 0.0
        self._apply_pose()
        if self.part_bundle:
            self.part_bundle.forceUpdate()

    def sync_action_progress(self, name: str, progress: float) -> None:
        """Force an action pose to an exact normalized gameplay progress.

        Sword collision uses the rendered blade segment, so attack poses must
        be synchronized before hit testing instead of waiting for the lower
        frequency cosmetic pose timer.
        """
        duration = self.ACTION_DURATIONS.get(name)
        if duration is None:
            return
        progress = max(0.0, min(1.0, float(progress)))
        self.state = name
        self.elapsed = duration * progress
        self.action_remaining = duration * (1.0 - progress)
        self.pose_accumulator = 0.0
        self._apply_pose()
        # Exposed hand/foot/weapon sockets otherwise lag one evaluated skeleton
        # update behind the controlJoint pose. Force the bundle now so combat
        # physics samples the exact fist/foot/blade position rendered this frame.
        if self.part_bundle:
            self.part_bundle.forceUpdate()

    def getAnimControl(self, name: str) -> _ProceduralAnimControl:
        return _ProceduralAnimControl(self, name)

    def is_playing(self, name: str) -> bool:
        if self.state != name:
            return False
        if name in self.ACTION_DURATIONS:
            return self.action_remaining > 0.0
        return True

    def step(self, dt: float) -> None:
        self.elapsed += dt
        force_pose = False
        if self.action_remaining > 0.0:
            self.action_remaining = max(0.0, self.action_remaining - dt)
            if self.action_remaining <= 0.0:
                if self.state == "death":
                    # Hold the corpse pose until the game-over transition.
                    self.elapsed = self.ACTION_DURATIONS["death"]
                    force_pose = True
                else:
                    self.state = "idle"
                    self.elapsed = 0.0
                    force_pose = True
        self.pose_accumulator += dt
        if force_pose or self.pose_accumulator >= self.pose_interval:
            self.pose_accumulator %= self.pose_interval
            self._apply_pose()

    def _reset_pose(self) -> None:
        for name, joint in self.joints.items():
            base = self.base_hpr[name]
            joint.setHpr(base.x, base.y, base.z)

    def _offset(self, name: str, *, h: float = 0.0, p: float = 0.0, r: float = 0.0) -> None:
        joint = self.joints.get(name)
        base = self.base_hpr.get(name)
        if not joint or base is None:
            return
        joint.setHpr(base.x + h, base.y + p, base.z + r)

    def _natural_upper_body(self, arm_drop: float = -70.0) -> None:
        # The source mesh is authored in a T pose. Lowering both upper arms is
        # the neutral stance; locomotion then adds opposing forward/back swing.
        self._offset("mixamorig:LeftArm", p=arm_drop)
        if self.weapon:
            # Keep the sword hand slightly outboard in neutral poses. This
            # prevents the blade from resting through the thigh/torso while
            # still looking like a relaxed one-handed carry.
            self._offset("mixamorig:RightArm", h=8.0, p=arm_drop + 5.0, r=-10.0)
        else:
            self._offset("mixamorig:RightArm", p=arm_drop)
        self._offset("mixamorig:LeftForeArm", p=-8.0)
        self._offset("mixamorig:RightForeArm", p=-5.0 if self.weapon else -8.0)

    def _apply_pose(self) -> None:
        self._reset_pose()
        state = self.state

        if state == "idle":
            self._natural_upper_body(-70.0)
            breathe = math.sin(self.elapsed * 2.1)
            self._offset("mixamorig:Spine2", p=breathe * 1.6)
            self._offset("mixamorig:Head", h=math.sin(self.elapsed * 0.65) * 1.4)
            return

        if state in {"walk", "run"}:
            running = state == "run"
            frequency = 2.35 if running else 1.55
            stride = 40.0 if running else 27.0
            arm_swing = 29.0 if running else 18.0
            arm_lift = 22.0 if running else 14.0
            phase = self.elapsed * math.tau * frequency
            swing = math.sin(phase)
            # Direct P rotation is the clean forward/back thigh axis on these
            # Mixamo-style rigs; opposite signs produce a readable stride.
            self._offset("mixamorig:LeftUpLeg", p=stride * swing)
            self._offset("mixamorig:RightUpLeg", p=-stride * swing)
            # Bend the trailing knee slightly so the legs do not look like two
            # rigid pendulums during the cycle.
            left_knee = max(0.0, -swing) * (22.0 if running else 13.0)
            right_knee = max(0.0, swing) * (22.0 if running else 13.0)
            self._offset("mixamorig:LeftLeg", p=-left_knee)
            self._offset("mixamorig:RightLeg", p=-right_knee)

            self._natural_upper_body(-62.0 if running else -68.0)
            base_arm = -62.0 if running else -68.0
            self._offset(
                "mixamorig:LeftArm",
                h=-arm_swing * 0.45 * swing,
                p=base_arm + arm_lift * swing,
            )
            if self.weapon:
                self._offset(
                    "mixamorig:RightArm",
                    h=10.0 + arm_swing * 0.18 * swing,
                    p=base_arm + 6.0 - arm_lift * 0.35 * swing,
                    r=-10.0,
                )
                self._offset("mixamorig:RightForeArm", p=-5.0)
            else:
                self._offset(
                    "mixamorig:RightArm",
                    h=arm_swing * 0.45 * swing,
                    p=base_arm - arm_lift * swing,
                )
            self._offset("mixamorig:Spine2", h=-swing * 2.5, p=-5.0 if running else -1.5)
            return

        if state == "dance_1":
            # Side-to-side groove: alternating steps, shoulder swing and a
            # little torso twist.  Keep the feet close enough that the pose
            # reads well in the third-person camera without looking broken.
            phase = self.elapsed * math.tau * 1.65
            sway = math.sin(phase)
            bounce = 0.5 + 0.5 * math.sin(phase * 2.0)
            self._offset("mixamorig:Hips", h=9.0 * sway, p=-2.5 * bounce)
            self._offset("mixamorig:Spine2", h=-13.0 * sway, p=-4.0 * bounce)
            self._offset("mixamorig:Head", h=6.0 * sway)
            self._offset("mixamorig:LeftUpLeg", p=16.0 * sway)
            self._offset("mixamorig:RightUpLeg", p=-16.0 * sway)
            self._offset("mixamorig:LeftLeg", p=-10.0 * max(0.0, -sway))
            self._offset("mixamorig:RightLeg", p=-10.0 * max(0.0, sway))
            self._offset("mixamorig:LeftArm", h=-22.0 * sway, p=-48.0 + 12.0 * sway)
            self._offset("mixamorig:RightArm", h=22.0 * sway, p=-48.0 - 12.0 * sway)
            self._offset("mixamorig:LeftForeArm", p=-28.0 + 8.0 * sway)
            self._offset("mixamorig:RightForeArm", p=-28.0 - 8.0 * sway)
            if self.weapon:
                self._offset("mixamorig:RightArm", h=12.0, p=-47.0, r=-12.0)
                self._offset("mixamorig:RightForeArm", p=-6.0)
            return

        if state == "dance_2":
            # Disco-style alternating point: one arm rises while the other
            # drops, with an opposing hip/torso twist and light knee bounce.
            phase = self.elapsed * math.tau * 1.35
            wave = math.sin(phase)
            left_high = 0.5 + 0.5 * wave
            right_high = 1.0 - left_high
            self._offset("mixamorig:Hips", h=-12.0 * wave)
            self._offset("mixamorig:Spine", h=8.0 * wave)
            self._offset("mixamorig:Spine2", h=16.0 * wave, p=-5.0)
            self._offset("mixamorig:Head", h=-9.0 * wave)
            self._offset("mixamorig:LeftArm", h=-16.0, p=-70.0 + 64.0 * left_high, r=-10.0)
            self._offset("mixamorig:RightArm", h=16.0, p=-70.0 + 64.0 * right_high, r=10.0)
            self._offset("mixamorig:LeftForeArm", p=-18.0 - 18.0 * left_high)
            self._offset("mixamorig:RightForeArm", p=-18.0 - 18.0 * right_high)
            self._offset("mixamorig:LeftUpLeg", p=11.0 * wave)
            self._offset("mixamorig:RightUpLeg", p=-11.0 * wave)
            self._offset("mixamorig:LeftLeg", p=-9.0 * max(0.0, -wave))
            self._offset("mixamorig:RightLeg", p=-9.0 * max(0.0, wave))
            if self.weapon:
                self._offset("mixamorig:RightArm", h=14.0, p=-44.0, r=-14.0)
                self._offset("mixamorig:RightForeArm", p=-5.0)
            return

        if state == "dance_3":
            # Celebration bounce: both arms stay high while the character
            # alternates knee lifts and waves the upper body rhythmically.
            phase = self.elapsed * math.tau * 1.9
            wave = math.sin(phase)
            bounce = abs(math.sin(phase))
            self._offset("mixamorig:Hips", h=8.0 * math.sin(phase * 0.5), p=-4.0 * bounce)
            self._offset("mixamorig:Spine2", h=-10.0 * wave, p=-8.0 * bounce)
            self._offset("mixamorig:Head", h=8.0 * wave)
            self._offset("mixamorig:LeftArm", h=-12.0 * wave, p=-14.0 + 8.0 * wave, r=-14.0)
            self._offset("mixamorig:RightArm", h=12.0 * wave, p=-14.0 - 8.0 * wave, r=14.0)
            self._offset("mixamorig:LeftForeArm", p=-42.0 + 12.0 * wave)
            self._offset("mixamorig:RightForeArm", p=-42.0 - 12.0 * wave)
            self._offset("mixamorig:LeftUpLeg", p=20.0 * max(0.0, wave))
            self._offset("mixamorig:RightUpLeg", p=20.0 * max(0.0, -wave))
            self._offset("mixamorig:LeftLeg", p=-18.0 * max(0.0, wave))
            self._offset("mixamorig:RightLeg", p=-18.0 * max(0.0, -wave))
            if self.weapon:
                self._offset("mixamorig:RightArm", h=16.0, p=-42.0, r=-14.0)
                self._offset("mixamorig:RightForeArm", p=-5.0)
            return

        if state == "sword":
            duration = self.ACTION_DURATIONS["sword"]
            progress = max(0.0, min(1.0, self.elapsed / duration))
            ease = 0.5 - 0.5 * math.cos(progress * math.pi)
            self._natural_upper_body(-64.0)
            # True 210-degree *world-space* cut. On this Mixamo rig upper-arm
            # roll is the axis that actually carries the hand horizontally.
            # The calibrated roll + torso counter-turn below measures 210° at
            # the rendered blade tip while keeping the blade outside the torso.
            # 145.035° each side was measured against the exposed hand socket
            # and current blade length to produce a ~210° real blade-tip arc.
            swing_roll = -145.035 + 290.07 * ease
            self._offset("mixamorig:RightArm", p=25.0, r=swing_roll)
            self._offset("mixamorig:RightForeArm", p=-2.0)
            self._offset("mixamorig:RightHand", p=2.0)
            self._offset("mixamorig:Spine2", h=-36.0 + 72.0 * ease, p=-2.0)
            self._offset("mixamorig:LeftArm", h=-10.0 * ease, p=-72.0)
            return

        if state == "punch_charge":
            q = self.charge_ratio
            self._natural_upper_body(-64.0)
            # Wind the torso and draw the empty left fist back beside the ribs.
            self._offset("mixamorig:Hips", h=-5.0 * q)
            self._offset("mixamorig:Spine", h=-8.0 * q, p=2.0 * q)
            self._offset("mixamorig:Spine2", h=-18.0 * q, p=4.0 * q)
            self._offset("mixamorig:LeftArm", h=-14.0 * q, p=-58.0 + 10.0 * q, r=22.0 * q)
            self._offset("mixamorig:LeftForeArm", p=-18.0 - 44.0 * q)
            self._offset("mixamorig:LeftHand", p=6.0 * q)
            return

        if state == "kick_charge":
            q = self.charge_ratio
            self._natural_upper_body(-60.0)
            # Compress before launch: both knees bend, torso lowers/leans forward,
            # and the sword arm remains in its safe carry pose.
            self._offset("mixamorig:Hips", p=-10.0 * q)
            self._offset("mixamorig:Spine", p=-8.0 * q)
            self._offset("mixamorig:Spine2", p=-12.0 * q)
            self._offset("mixamorig:LeftUpLeg", p=-17.0 * q)
            self._offset("mixamorig:RightUpLeg", p=-22.0 * q)
            self._offset("mixamorig:LeftLeg", p=-30.0 * q)
            self._offset("mixamorig:RightLeg", p=-35.0 * q)
            self._offset("mixamorig:LeftArm", h=-8.0 * q, p=-52.0)
            return

        if state == "punch":
            duration = self.ACTION_DURATIONS["punch"]
            progress = max(0.0, min(1.0, self.elapsed / duration))
            power = 0.35 + 0.65 * self.action_power
            # Charged cross: start from the wound-up fist, rotate the hips/torso
            # through the target, fully extend, then recover.
            strike = math.sin(progress * math.pi)
            retract = max(0.0, 1.0 - progress / 0.24)
            self._natural_upper_body(-64.0)
            self._offset("mixamorig:Hips", h=-7.0 * retract * power + 9.0 * strike * power)
            self._offset("mixamorig:Spine", h=-12.0 * retract * power + 13.0 * strike * power)
            self._offset("mixamorig:Spine2", h=-18.0 * retract * power + 17.0 * strike * power, p=-3.0 * strike)
            # Negative upper-arm roll drives the fist along the character's true
            # forward axis on this rig. Keep the elbow tucked during wind-up and
            # straighten through impact.
            self._offset(
                "mixamorig:LeftArm",
                h=-10.0 * retract * power,
                p=-56.0 + 12.0 * strike,
                r=24.0 * retract * power - (88.0 + 12.0 * power) * strike,
            )
            self._offset("mixamorig:LeftForeArm", p=-18.0 - 46.0 * retract + 10.0 * strike)
            self._offset("mixamorig:LeftHand", p=7.0 * strike)
            return

        if state == "kick":
            duration = self.ACTION_DURATIONS["kick"]
            progress = max(0.0, min(1.0, self.elapsed / duration))
            power = 0.35 + 0.65 * self.action_power
            # Flying front kick: both feet leave the floor via root lift in game.py.
            # Here the rear leg tucks while the right leg drives forward and
            # straightens through the contact window.
            flight = math.sin(progress * math.pi)
            strike = math.sin(max(0.0, min(1.0, progress / 0.72)) * math.pi)
            chamber = math.sin(max(0.0, min(1.0, progress / 0.42)) * math.pi)
            self._natural_upper_body(-62.0)
            self._offset("mixamorig:Hips", p=-6.0 * flight)
            self._offset("mixamorig:Spine", p=10.0 * flight)
            self._offset("mixamorig:Spine2", p=14.0 * flight, h=-5.0 * flight)
            self._offset("mixamorig:RightUpLeg", p=(72.0 + 12.0 * power) * strike)
            self._offset("mixamorig:RightLeg", p=-62.0 * chamber + 10.0 * strike)
            self._offset("mixamorig:RightFoot", p=(13.0 + 5.0 * power) * strike)
            self._offset("mixamorig:LeftUpLeg", p=-26.0 * flight)
            self._offset("mixamorig:LeftLeg", p=-48.0 * flight)
            self._offset("mixamorig:LeftFoot", p=12.0 * flight)
            self._offset("mixamorig:LeftArm", h=-18.0 * flight, p=-48.0)
            return

        if state == "hit":
            duration = self.ACTION_DURATIONS["hit"]
            progress = max(0.0, min(1.0, self.elapsed / duration))
            recoil = math.sin(progress * math.pi)
            self._natural_upper_body(-66.0)
            self._offset("mixamorig:Spine2", p=15.0 * recoil, h=-9.0 * recoil)
            self._offset("mixamorig:Head", p=10.0 * recoil)
            self._offset("mixamorig:LeftArm", h=-12.0 * recoil, p=-66.0 + 12.0 * recoil)
            self._offset("mixamorig:RightArm", h=12.0 * recoil, p=-66.0 + 12.0 * recoil)
            return

        if state == "death":
            duration = self.ACTION_DURATIONS["death"]
            progress = max(0.0, min(1.0, self.elapsed / duration))
            ease = 0.5 - 0.5 * math.cos(progress * math.pi)
            self._natural_upper_body(-74.0)
            self._offset("mixamorig:Hips", p=-8.0 * ease, r=18.0 * ease)
            self._offset("mixamorig:Spine", p=10.0 * ease, r=52.0 * ease)
            self._offset("mixamorig:Spine2", p=31.0 * ease, r=22.0 * ease)
            self._offset("mixamorig:Head", p=17.0 * ease, r=12.0 * ease)
            self._offset("mixamorig:LeftArm", p=-82.0 + 12.0 * ease, r=-18.0 * ease)
            self._offset("mixamorig:RightArm", p=-77.0 + 8.0 * ease, r=24.0 * ease)
            self._offset("mixamorig:LeftForeArm", p=-18.0 - 18.0 * ease)
            self._offset("mixamorig:RightForeArm", p=-14.0 - 20.0 * ease)
            self._offset("mixamorig:LeftUpLeg", p=-16.0 * ease, r=-9.0 * ease)
            self._offset("mixamorig:RightUpLeg", p=13.0 * ease, r=8.0 * ease)
            self._offset("mixamorig:LeftLeg", p=-24.0 * ease)
            self._offset("mixamorig:RightLeg", p=-16.0 * ease)
            return

        self._natural_upper_body(-70.0)


def animated_character(name: str, parent: Entity, scale: float = 1.0) -> Actor:
    """Create one self-animated Quaternius character.

    These models and animation clips come from the same source rig, avoiding
    the retarget/rest-pose mismatch we hit with the newer base-character kit.
    Panda3D is Z-up while the Ursina game world is Y-up, hence +90° pitch.
    """
    animations = {
        "idle": (PIRATE_BAM_DIR / f"{name}_Idle.bam").as_posix(),
        "walk": (PIRATE_BAM_DIR / f"{name}_Walk.bam").as_posix(),
        "run": (PIRATE_BAM_DIR / f"{name}_Run.bam").as_posix(),
        "sword": (PIRATE_BAM_DIR / f"{name}_Sword.bam").as_posix(),
        "hit": (PIRATE_BAM_DIR / f"{name}_HitReact.bam").as_posix(),
        "death": (PIRATE_BAM_DIR / f"{name}_Death.bam").as_posix(),
    }
    actor = Actor((PIRATE_BAM_DIR / f"{name}.bam").as_posix(), animations)
    actor.reparentTo(parent)
    actor.setScale(scale)
    actor.setP(90)
    # Match the existing 0.42 s melee cadence to the authored 0.9 s clip.
    actor.setPlayRate(2.1, "sword")
    actor.loop("idle")
    return actor


def add_player_model(root: Entity) -> dict[str, Entity]:
    """Build the player from the high-detail CPU-skinned champion rig."""
    visual = Entity(parent=root)
    actor = ProceduralCharacter("azure-champion", visual, scale=2.0, weapon=True, pose_hz=20.0)
    cape = Entity(parent=visual, enabled=False)
    # Compatibility placeholders only. The real sword is permanently attached
    # to actor.RightHand and is never toggled off.
    sword_pivot = Entity(parent=visual, enabled=False)
    blade = Entity(parent=visual, enabled=False)
    back_sword = Entity(parent=visual, enabled=False)
    shield = Entity(parent=visual, enabled=False)

    return {
        "visual": visual,
        "actor": actor,
        "hero": visual,
        "cape": cape,
        "sword_pivot": sword_pivot,
        "blade": blade,
        "back_sword": back_sword,
        "guard": blade,
        "hilt": blade,
        "blade_tip": blade,
        "shield": shield,
    }


def add_enemy_model(root: Entity, kind: str) -> dict[str, Entity]:
    visual = Entity(parent=root)
    if kind == "brute":
        actor = ProceduralCharacter(
            "hooded-blade",
            visual,
            scale=2.14,
            weapon=False,
            tint=(0.68, 0.55, 0.52, 1.0),
            pose_hz=10.0,
        )
        return {"visual": visual, "actor": actor, "body": visual, "head": visual, "flash_parts": []}

    actor = ProceduralCharacter("hooded-blade", visual, scale=1.86, weapon=False, pose_hz=10.0)
    return {"visual": visual, "actor": actor, "body": visual, "head": visual, "flash_parts": []}


def add_torch(position: tuple[float, float, float], yaw: float = 0.0) -> list[Entity]:
    holder = Entity(position=position, rotation_y=yaw)
    authored_torch = quaternius_entity("Torch", parent=holder, position=(0, -0.55, 0), scale=1.0)
    flame_outer = Entity(parent=holder, model="sphere", shader=unlit_shader, color=c255(255, 111, 42, 210), scale=(0.25, 0.42, 0.25), position=(0, 0.60, 0))
    flame_inner = Entity(parent=holder, model="sphere", shader=unlit_shader, color=c255(255, 230, 118, 245), scale=(0.13, 0.28, 0.13), position=(0, 0.62, -0.01))
    glow = Entity(parent=holder, model="sphere", shader=unlit_shader, color=c255(255, 126, 48, 26), scale=(0.78, 0.78, 0.78), position=(0, 0.60, 0))
    light = PointLight(parent=holder, color=c255(225, 104, 42), position=(0, 0.58, 0))
    light._light.set_attenuation((1.0, 0.25, 0.08))
    holder.torch_phase = (position[0] * 0.37 + position[2] * 0.19) % math.tau
    holder.flame_outer = flame_outer
    holder.flame_inner = flame_inner
    holder.glow = glow
    holder.torch_light = light
    return [holder, authored_torch, flame_outer, flame_inner, glow, light]


def animate_torch(holder: Entity, t: float) -> None:
    phase = getattr(holder, "torch_phase", 0.0)
    flicker = 0.86 + math.sin(t * 9.0 + phase) * 0.08 + math.sin(t * 14.7 + phase * 1.7) * 0.05
    holder.flame_outer.scale_y = 0.42 * flicker
    holder.flame_inner.scale_y = 0.28 * (0.94 + (flicker - 0.86) * 0.65)
    holder.glow.scale = 0.72 + flicker * 0.10
    red = int(235 + 20 * min(1.0, flicker))
    green = int(92 + 36 * min(1.0, flicker))
    holder.torch_light.color = c255(red, green, 42)


def add_floor_decal(position: tuple[float, float, float], scale: tuple[float, float, float]) -> Entity:
    return Entity(
        model="quad",
        texture="assets3d/rune.png",
        color=color.white,
        position=position,
        scale=scale,
        rotation_x=90,
        double_sided=True,
    )


def style_portal(root: Entity) -> list[Entity]:
    ring = Entity(parent=root, model="sphere", shader=unlit_shader, color=c255(122, 72, 230, 185), scale=(0.30, 2.55, 2.20))
    inner = Entity(parent=root, model="sphere", shader=unlit_shader, color=c255(42, 16, 88, 235), scale=(0.23, 1.95, 1.66))
    core = Entity(parent=root, model="sphere", shader=unlit_shader, color=c255(190, 127, 255, 145), scale=(0.16, 1.42, 1.18))
    return [ring, inner, core]


def animate_portal(root: Entity, t: float) -> None:
    pulse = 1.0 + math.sin(t * 3.0) * 0.06
    root.scale_y = pulse
    root.scale_z = pulse
    root.rotation_x = math.sin(t * 0.8) * 3.0
