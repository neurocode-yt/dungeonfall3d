from __future__ import annotations

import math
import random
from dataclasses import dataclass

import simplepbr
from panda3d.core import Point2, Point3, WindowProperties

from ursina import (
    AmbientLight,
    DirectionalLight,
    Entity,
    Sky,
    Text,
    Ursina,
    Vec3,
    application,
    camera,
    color,
    destroy,
    held_keys,
    mouse,
    raycast,
    scene,
    time,
    window,
)

from settings import (
    CAMERA_DISTANCE,
    CAMERA_COLLISION_MIN_DISTANCE,
    CAMERA_COLLISION_PADDING,
    CAMERA_KEY_PITCH_SPEED,
    CAMERA_KEY_YAW_SPEED,
    CAMERA_MAX_DISTANCE,
    CAMERA_MAX_PITCH,
    CAMERA_MIN_DISTANCE,
    CAMERA_MIN_PITCH,
    CAMERA_MOUSE_SENSITIVITY,
    CAMERA_PITCH,
    CAMERA_PROBE_RADIUS,
    CAMERA_TARGET_HEIGHT,
    CAMERA_ZOOM_STEP,
    DOOR_HALF_WIDTH,
    HEALTH_AMOUNT,
    HEALTH_DROP_CHANCE,
    HEALTH_SPAWN_MAX,
    HEALTH_SPAWN_MIN,
    MAX_ROOM_HEALTH,
    PLAYER_ATTACK_COOLDOWN,
    PLAYER_ATTACK_RANGE,
    PLAYER_ATTACK_WIDTH,
    PLAYER_BODY_RADIUS,
    CRAWLER_BODY_RADIUS,
    BRUTE_BODY_RADIUS,
    MAX_CHARACTER_MOVE_STEP,
    PLAYER_DAMAGE,
    PLAYER_PUNCH_DAMAGE,
    PLAYER_PUNCH_MAX_DAMAGE,
    PLAYER_PUNCH_MAX_CHARGE,
    PLAYER_PUNCH_DURATION,
    PLAYER_PUNCH_COOLDOWN,
    PLAYER_KICK_DAMAGE,
    PLAYER_KICK_MAX_DAMAGE,
    PLAYER_KICK_MAX_CHARGE,
    PLAYER_KICK_DURATION,
    PLAYER_KICK_COOLDOWN,
    PLAYER_KICK_MIN_TRAVEL,
    PLAYER_KICK_MAX_TRAVEL,
    PLAYER_KICK_MIN_HEIGHT,
    PLAYER_KICK_MAX_HEIGHT,
    PLAYER_INVULNERABILITY,
    PLAYER_MAX_HEALTH,
    PLAYER_SPRINT_SPEED,
    PLAYER_WALK_SPEED,
    ROOM_HALF_DEPTH,
    ROOM_HALF_WIDTH,
    WALL_HEIGHT,
    WALL_THICKNESS,
    WINDOW_TITLE,
)
from visuals import (
    add_enemy_model,
    add_floor_decal,
    add_player_model,
    add_torch,
    animate_torch,
    animate_portal,
    kenney_entity,
    lit_entity,
    quaternius_entity,
    style_portal,
    tangent_cube_entity,
)


@dataclass(frozen=True)
class EnemySpec:
    x: float
    z: float
    kind: str = "crawler"


@dataclass(frozen=True)
class ObstacleSpec:
    x: float
    z: float
    width: float
    depth: float
    height: float = 1.8


@dataclass(frozen=True)
class RoomSpec:
    name: str
    obstacles: tuple[ObstacleSpec, ...]
    enemies: tuple[EnemySpec, ...]


ROOMS = (
    RoomSpec(
        "The Antechamber",
        (ObstacleSpec(-2.6, -1.2, 1.2, 5.0), ObstacleSpec(3.5, 2.3, 3.0, 1.1)),
        (EnemySpec(-3.8, 3.0), EnemySpec(5.0, -1.6)),
    ),
    RoomSpec(
        "Broken Gallery",
        (
            ObstacleSpec(-5.0, -2.0, 3.5, 1.0),
            ObstacleSpec(0.8, -1.1, 1.0, 4.0),
            ObstacleSpec(-0.5, 3.0, 4.5, 1.0),
        ),
        (EnemySpec(-0.4, 0.4), EnemySpec(6.2, -2.8), EnemySpec(5.6, 3.0, "brute")),
    ),
    RoomSpec(
        "Vault of Echoes",
        (
            ObstacleSpec(-6.0, -2.5, 1.0, 3.6),
            ObstacleSpec(-6.0, 3.3, 1.0, 2.0),
            ObstacleSpec(1.3, -0.5, 4.0, 1.0),
            ObstacleSpec(6.0, 2.2, 1.0, 3.0),
        ),
        (EnemySpec(-2.8, -3.0, "brute"), EnemySpec(1.5, 3.2), EnemySpec(6.0, -3.2), EnemySpec(4.0, 3.1)),
    ),
    RoomSpec(
        "The Heart Chamber",
        (
            ObstacleSpec(-4.8, -2.4, 2.8, 1.0),
            ObstacleSpec(3.8, -2.4, 2.8, 1.0),
            ObstacleSpec(-4.8, 2.7, 2.8, 1.0),
            ObstacleSpec(3.8, 2.7, 2.8, 1.0),
        ),
        (EnemySpec(-0.5, -0.5, "brute"), EnemySpec(5.0, 0.4, "brute"), EnemySpec(-0.8, 3.4), EnemySpec(6.4, 3.4)),
    ),
)


def xz_distance(a: Vec3, b: Vec3) -> float:
    return math.hypot(a.x - b.x, a.z - b.z)


def c255(r: int, g: int, b: int, a: int = 255):
    """Convert familiar 0-255 channels into Ursina's 0.0-1.0 color range."""
    return color.rgba(r / 255, g / 255, b / 255, a / 255)


class EffectParticle(Entity):
    def __init__(self, position: Vec3, tint, velocity: Vec3, life: float = 0.45, size: float = 0.10) -> None:
        super().__init__(model="sphere", color=tint, position=position, scale=size)
        self.velocity = velocity
        self.life = life
        self.max_life = life

    def tick(self) -> bool:
        self.life -= time.dt
        if self.life <= 0:
            return False
        self.velocity.y -= 5.5 * time.dt
        self.position += self.velocity * time.dt
        self.scale = max(0.001, self.scale_x * (1.0 - time.dt * 2.2))
        return True


class FloatingDamageNumber:
    """High-contrast screen-space damage popup anchored to a 3D hit point."""

    def __init__(self, world_position: Vec3, loss_100: int, health_100: int, *, player_hit: bool = False) -> None:
        self.world_position = Vec3(world_position)
        self.life = 1.35
        self.max_life = self.life
        self.player_hit = player_hit
        popup_text = f"-{loss_100}\nHP {health_100}/100"
        # Draw a dark duplicate a few pixels behind the bright text.  In this
        # dungeon the character/background values are often similar, so plain
        # text can visually disappear even though it is technically rendered.
        self.shadow = Text(
            parent=camera.ui,
            text=popup_text,
            origin=(0, 0),
            scale=0.78,
            color=c255(0, 0, 0, 235),
            always_on_top=True,
        )
        self.text = Text(
            parent=camera.ui,
            text=popup_text,
            origin=(0, 0),
            scale=0.78,
            color=c255(255, 86, 86) if player_hit else c255(255, 225, 72),
            always_on_top=True,
        )

    def destroy(self) -> None:
        destroy(self.shadow)
        destroy(self.text)

    def tick(self) -> bool:
        self.life -= time.dt
        if self.life <= 0.0:
            return False
        self.world_position.y += time.dt * 0.58
        relative = camera.getRelativePoint(scene, Point3(self.world_position.x, self.world_position.y, self.world_position.z))
        projected = Point2()
        if application.base.camLens.project(relative, projected):
            self.text.enabled = True
            self.shadow.enabled = True
            # Panda lens projection returns normalized device coordinates in
            # [-1, 1]. Ursina's camera.ui spans roughly half that vertically
            # (y ~= +/-0.5) and half-aspect horizontally, so convert directly
            # into normal Ursina UI coordinates. The old 0.025 multiplier made
            # these popups about 20x too small and clustered near screen center.
            x = projected.x * window.aspect_ratio * 0.5
            y = projected.y * 0.5
            # Keep readable popups inside the visible play area even if the
            # impact point is near an edge of the screen.
            x_limit = max(0.15, window.aspect_ratio * 0.5 - 0.09)
            x = max(-x_limit, min(x_limit, x))
            y = max(-0.39, min(0.40, y))
            self.text.x = x
            self.text.y = y
            self.shadow.x = x + 0.0025
            self.shadow.y = y - 0.0025
        else:
            self.text.enabled = False
            self.shadow.enabled = False
        fade = max(0.0, min(1.0, self.life / 0.38))
        if self.player_hit:
            self.text.color = c255(255, 86, 86, int(255 * fade))
        else:
            self.text.color = c255(255, 225, 72, int(255 * fade))
        self.shadow.color = c255(0, 0, 0, int(235 * fade))
        return True


class Pickup(Entity):
    def __init__(self, game: "DungeonFall3D", kind: str, position: Vec3, amount: int) -> None:
        self.game = game
        self.kind = kind
        self.amount = amount
        super().__init__(position=position)
        self.visual = Entity(parent=self)
        if kind == "heal":
            lit_entity(parent=self.visual, model="cube", color=c255(79, 94, 91), scale=(0.34, 0.48, 0.28), position=(0, 0, 0))
            lit_entity(parent=self.visual, model="cube", color=c255(190, 205, 196), scale=(0.24, 0.12, 0.20), position=(0, 0.30, 0))
            Entity(parent=self.visual, model="cube", color=c255(83, 255, 155, 210), scale=(0.25, 0.29, 0.20), position=(0, -0.04, -0.05))
            Entity(parent=self.visual, model="sphere", color=c255(102, 255, 173, 70), scale=0.68)
        else:
            lit_entity(parent=self.visual, model="sphere", color=c255(235, 179, 49), scale=(0.16, 0.52, 0.52))
            Entity(parent=self.visual, model="sphere", color=c255(255, 222, 91, 160), scale=(0.12, 0.38, 0.38))
        self.base_y = position.y
        self.phase = random.random() * math.tau

    def tick(self) -> None:
        self.rotation_y += 85 * time.dt
        self.y = self.base_y + math.sin(self.phase + time.time() * 2.8) * 0.15
        pulse = 1.0 + math.sin(self.phase + time.time() * 4.0) * 0.06
        self.visual.scale = pulse


class Enemy(Entity):
    _next_id = 1

    def __init__(self, game: "DungeonFall3D", spec: EnemySpec) -> None:
        self.game = game
        self.enemy_id = Enemy._next_id
        Enemy._next_id += 1
        self.kind = spec.kind
        if self.kind == "brute":
            self.max_health = 100
            self.speed = 2.35
            self.damage = 18
            root_y = 0.0
        else:
            self.max_health = 100
            self.speed = 3.2
            self.damage = 12
            root_y = 0.0
        self.health = self.max_health
        self.hit_cooldown = 0.0
        self.flash_timer = 0.0
        super().__init__(
            position=(spec.x, root_y, spec.z),
        )
        parts = add_enemy_model(self, self.kind)
        self.visual = parts["visual"]
        self.actor = parts.get("actor")
        self.anim_state = "idle"
        self.flash_parts = parts.get("flash_parts", [parts["body"], parts["head"]])
        self.normal_colors = [part.color for part in self.flash_parts]
        self.bob_phase = random.random() * math.tau

    @property
    def alive(self) -> bool:
        return self.health > 0

    def take_damage(self, amount: int) -> None:
        self.health = max(0, self.health - amount)
        self.flash_timer = 0.11
        if self.actor and self.alive:
            self.actor.play("hit")
            self.anim_state = "hit"

    def tick(self) -> None:
        self.hit_cooldown = max(0.0, self.hit_cooldown - time.dt)
        self.flash_timer = max(0.0, self.flash_timer - time.dt)
        if self.actor:
            if self.flash_timer > 0:
                self.actor.setColorScale(1.0, 0.45, 0.45, 1.0)
            else:
                self.actor.clearColorScale()
        for part, normal in zip(self.flash_parts, self.normal_colors):
            part.color = color.white if self.flash_timer > 0 else normal
        if not self.actor:
            self.visual.y = math.sin(time.time() * (4.2 if self.kind == "crawler" else 2.5) + self.bob_phase) * (0.05 if self.kind == "crawler" else 0.025)

        player = self.game.player
        if not player or not self.alive:
            return
        action_playing = False
        if self.actor and self.anim_state in {"hit", "sword"}:
            action_control = self.actor.getAnimControl(self.anim_state)
            action_playing = bool(action_control and action_control.isPlaying())
        dist = xz_distance(self.position, player.position)
        contact_distance = self.game.body_radius(self) + self.game.body_radius(player) + 0.06
        if contact_distance < dist < 14.0:
            dx = player.x - self.x
            dz = player.z - self.z
            length = max(0.001, math.hypot(dx, dz))
            dx /= length
            dz /= length
            move = Vec3(dx * self.speed * time.dt, 0, dz * self.speed * time.dt)
            self.game.try_move(self, move, radius=self.game.body_radius(self), ignore=self)
            self.rotation_y = math.degrees(math.atan2(dx, dz))
            dist = xz_distance(self.position, player.position)
            locomotion_anim = "walk" if self.kind == "brute" else "run"
            if self.actor and not action_playing and self.anim_state != locomotion_anim:
                self.actor.loop(locomotion_anim)
                self.anim_state = locomotion_anim
        elif self.actor and not action_playing and self.anim_state != "idle":
            self.actor.loop("idle")
            self.anim_state = "idle"

        if dist <= contact_distance + 0.12 and self.hit_cooldown <= 0:
            self.hit_cooldown = 0.65
            if self.actor and not (self.anim_state == "hit" and action_playing):
                self.actor.play("sword")
                self.anim_state = "sword"
            self.game.damage_player(self.damage)
        if self.actor and hasattr(self.actor, "step"):
            if hasattr(self.actor, "set_pose_hz"):
                # Distant enemies still move/think every frame, but their
                # expensive CPU-skinned pose does not need the same visual
                # refresh rate until they approach the camera/player.
                if dist < 4.5 or self.anim_state in {"hit", "sword"}:
                    self.actor.set_pose_hz(12.0)
                elif dist < 8.0:
                    self.actor.set_pose_hz(8.0)
                else:
                    self.actor.set_pose_hz(5.0)
            self.actor.step(time.dt)


class Player(Entity):
    def __init__(self, game: "DungeonFall3D") -> None:
        self.game = game
        self.max_health = PLAYER_MAX_HEALTH
        self.health = self.max_health
        self.coins = 0
        self.invulnerability = 0.0
        self.attack_cooldown = 0.0
        self.attack_timer = 0.0
        self.attack_kind: str | None = None
        self.attack_duration = PLAYER_ATTACK_COOLDOWN
        self.attack_power = 0.0
        self.attack_damage = PLAYER_DAMAGE
        self.previous_action_progress = 0.0
        self.previous_limb_contact: Vec3 | None = None
        self.charge_kind: str | None = None
        self.charge_time = 0.0
        self.charge_ratio = 0.0
        self.charge_pose_timer = 0.0
        self.charge_keys_held: set[str] = set()
        self.kick_travel_total = 0.0
        self.kick_jump_height = 0.0
        self.locked_attack_facing = Vec3(0, 0, 1)
        # Visible character faces local +Z at rotation_y == 0, so keep the
        # gameplay facing vector aligned with the rendered model from frame 1.
        self.facing = Vec3(0, 0, 1)
        self.hit_this_swing: set[int] = set()
        self.previous_sword_segment: tuple[Vec3, Vec3] | None = None
        super().__init__(
            position=(-7.4, 0.0, 0),
        )
        model = add_player_model(self)
        self.visual = model["visual"]
        self.actor = model.get("actor")
        self.anim_state = "idle"
        self.cape = model["cape"]
        self.sword_pivot = model["sword_pivot"]
        self.blade = model["blade"]
        self.back_sword = model.get("back_sword")
        self.walk_time = 0.0

    def tick(self) -> None:
        self.invulnerability = max(0.0, self.invulnerability - time.dt)
        self.attack_cooldown = max(0.0, self.attack_cooldown - time.dt)
        actor_pose_synced = False

        if self.charge_kind:
            max_charge = PLAYER_PUNCH_MAX_CHARGE if self.charge_kind == "punch" else PLAYER_KICK_MAX_CHARGE
            self.charge_time = min(max_charge, self.charge_time + time.dt)
            self.charge_ratio = min(1.0, self.charge_time / max(0.001, max_charge))
            charging_action = self.charge_kind
            self.charge_pose_timer = max(0.0, self.charge_pose_timer - time.dt)
            if self.actor and hasattr(self.actor, "set_charge_pose") and self.charge_pose_timer <= 0.0:
                self.actor.set_charge_pose(self.charge_kind, self.charge_ratio)
                self.anim_state = f"{self.charge_kind}_charge"
                actor_pose_synced = True
                self.charge_pose_timer = 1.0 / 24.0
            preview_damage = self._charged_damage(self.charge_kind, self.charge_ratio)
            self.game.update_charge_display(self.charge_kind, self.charge_ratio, preview_damage)
            if self.charge_time >= max_charge - 1e-5:
                # Auto-fire at full power so a lost key-up/focus event cannot
                # leave the player rooted in a permanent charge pose.
                self.release_charge(charging_action, auto=True)
        else:
            self.game.hide_charge_display()

        was_attacking = self.attack_timer > 0
        active_attack = self.attack_kind
        previous_progress = self.previous_action_progress
        self.attack_timer = max(0.0, self.attack_timer - time.dt)
        if was_attacking:
            progress = 1.0 - self.attack_timer / max(0.001, self.attack_duration)
            if active_attack == "kick":
                self._step_flying_kick(previous_progress, progress)
            if self.actor and hasattr(self.actor, "sync_action_progress"):
                # Put the rendered hand/sword at this exact attack time before
                # collision is evaluated.  The blade physics below then uses
                # the same geometry the player sees on screen.
                self.actor.sync_action_progress(active_attack or "sword", progress)
                self.anim_state = active_attack or "sword"
                actor_pose_synced = True
            if active_attack == "sword":
                # Resolve during the whole visible sword swing, not only on
                # key-down. The physical sword is the only attack visual.
                self.game.resolve_attack()
            elif active_attack in {"punch", "kick"}:
                self.game.resolve_unarmed_attack(active_attack, previous_progress, progress)
            self.previous_action_progress = progress
            if self.attack_timer <= 0:
                self.attack_kind = None
                if active_attack == "kick":
                    self.visual.y = 0.0
                    self.game.spawn_burst(
                        self.position + Vec3(0, 0.10, 0),
                        c255(145, 108, 72),
                        count=4 + round(4 * self.attack_power),
                        speed=1.05 + 0.55 * self.attack_power,
                        size=0.055 + 0.025 * self.attack_power,
                    )
                    self.game.camera_shake_timer = max(self.game.camera_shake_timer, 0.08)
                    self.game.camera_shake_strength = max(
                        self.game.camera_shake_strength,
                        0.018 + 0.018 * self.attack_power,
                    )
        else:
            self.previous_sword_segment = None
            self.previous_limb_contact = None
            self.previous_action_progress = 0.0
            if self.visual.y != 0.0 and self.charge_kind is None:
                self.visual.y = 0.0

        hit_playing = False
        if self.actor and self.anim_state == "hit":
            hit_control = self.actor.getAnimControl("hit")
            hit_playing = bool(hit_control and hit_control.isPlaying())

        dance_playing = False
        if self.actor and self.anim_state in {"dance_1", "dance_2", "dance_3"}:
            dance_control = self.actor.getAnimControl(self.anim_state)
            dance_playing = bool(dance_control and dance_control.isPlaying())

        # Poll physical key state for locomotion instead of relying on input
        # events. This keeps movement/sprint correct through pause/resume and
        # avoids sticky or missing key-up events after focus changes.
        strafe = int(bool(held_keys["d"] or held_keys["right arrow"])) - int(bool(held_keys["a"] or held_keys["left arrow"]))
        forward_input = int(bool(held_keys["w"] or held_keys["up arrow"])) - int(bool(held_keys["s"] or held_keys["down arrow"]))
        locomotion_allowed = self.charge_kind is None and (not was_attacking or active_attack == "sword")
        if (strafe or forward_input) and locomotion_allowed:
            camera_forward, camera_right = self.game.camera_basis()
            direction = camera_right * strafe + camera_forward * forward_input
            if direction.length() > 0:
                direction = direction.normalized()
            self.facing = direction
            self.rotation_y = math.degrees(math.atan2(direction.x, direction.z))
            sprinting = bool(held_keys["left shift"] or held_keys["right shift"])
            move_speed = PLAYER_SPRINT_SPEED if sprinting else PLAYER_WALK_SPEED
            locomotion_anim = "run" if sprinting else "walk"
            self.game.try_move(self, direction * move_speed * time.dt, radius=self.game.body_radius(self), ignore=self)
            if self.actor and not was_attacking and not hit_playing and self.anim_state != locomotion_anim:
                self.actor.loop(locomotion_anim)
                self.anim_state = locomotion_anim
            if not self.actor:
                self.walk_time += time.dt * 9.0
                self.visual.y = abs(math.sin(self.walk_time)) * 0.035
                self.cape.rotation_x = -7 - abs(math.sin(self.walk_time)) * 5
        else:
            if self.actor and self.charge_kind is None and not was_attacking and not hit_playing and not dance_playing and self.anim_state != "idle":
                self.actor.loop("idle")
                self.anim_state = "idle"
            if not self.actor:
                self.visual.y *= max(0.0, 1.0 - time.dt * 12.0)
                self.cape.rotation_x += (-7 - self.cape.rotation_x) * min(1.0, time.dt * 8.0)
        if self.actor and hasattr(self.actor, "step") and not actor_pose_synced:
            self.actor.step(time.dt)

    def attack(self) -> None:
        if self.charge_kind:
            return
        self._start_combat_action("sword")

    def punch(self) -> None:
        self._start_combat_action("punch", 0.0)

    def kick(self) -> None:
        self._start_combat_action("kick", 0.0)

    def _charged_damage(self, action: str, ratio: float) -> int:
        ratio = max(0.0, min(1.0, ratio))
        # Smoothstep gives predictable low/mid/full charge growth without a
        # tiny early hold receiving most of the bonus damage.
        curve = ratio * ratio * (3.0 - 2.0 * ratio)
        if action == "punch":
            return round(PLAYER_PUNCH_DAMAGE + (PLAYER_PUNCH_MAX_DAMAGE - PLAYER_PUNCH_DAMAGE) * curve)
        return round(PLAYER_KICK_DAMAGE + (PLAYER_KICK_MAX_DAMAGE - PLAYER_KICK_DAMAGE) * curve)

    def begin_charge(self, action: str) -> None:
        if action not in {"punch", "kick"} or action in self.charge_keys_held:
            return
        self.charge_keys_held.add(action)
        if self.charge_kind or self.attack_timer > 0 or self.attack_cooldown > 0:
            return
        if self.actor and self.anim_state == "hit":
            hit_control = self.actor.getAnimControl("hit")
            if hit_control and hit_control.isPlaying():
                return
        self.charge_kind = action
        self.charge_time = 0.0
        self.charge_ratio = 0.0
        self.charge_pose_timer = 0.0
        if self.facing.length() <= 0.001:
            self.facing = Vec3(0, 0, 1)
        self.facing = Vec3(self.facing.x, 0, self.facing.z).normalized()
        self.rotation_y = math.degrees(math.atan2(self.facing.x, self.facing.z))
        if self.actor and hasattr(self.actor, "set_charge_pose"):
            self.actor.set_charge_pose(action, 0.0)
            self.anim_state = f"{action}_charge"

    def release_charge(self, action: str, *, auto: bool = False) -> None:
        if not auto:
            self.charge_keys_held.discard(action)
        if self.charge_kind != action:
            return
        ratio = self.charge_ratio
        self.charge_kind = None
        self.charge_time = 0.0
        self.charge_ratio = 0.0
        self.charge_pose_timer = 0.0
        self.game.hide_charge_display()
        self._start_combat_action(action, ratio)

    def cancel_charge(self, *, clear_key_latch: bool = False) -> None:
        if clear_key_latch:
            self.charge_keys_held.clear()
        if not self.charge_kind:
            return
        self.charge_kind = None
        self.charge_time = 0.0
        self.charge_ratio = 0.0
        self.charge_pose_timer = 0.0
        self.game.hide_charge_display()
        if self.actor:
            self.actor.loop("idle")
            self.anim_state = "idle"

    def _step_flying_kick(self, previous_progress: float, progress: float) -> None:
        previous_progress = max(0.0, min(1.0, previous_progress))
        progress = max(0.0, min(1.0, progress))

        def travel_curve(value: float) -> float:
            t = max(0.0, min(1.0, value / 0.68))
            return t * t * (3.0 - 2.0 * t)

        previous_curve = travel_curve(previous_progress)
        current_curve = travel_curve(progress)
        step_distance = max(0.0, current_curve - previous_curve) * self.kick_travel_total
        if step_distance > 0.0:
            direction = Vec3(self.locked_attack_facing)
            self.game.try_move(
                self,
                direction * step_distance,
                radius=self.game.body_radius(self),
                ignore=self,
                allow_slide=False,
            )
        self.visual.y = math.sin(progress * math.pi) * self.kick_jump_height

    def _start_combat_action(self, action: str, charge_ratio: float = 0.0) -> None:
        if self.attack_cooldown > 0 or self.attack_timer > 0 or self.charge_kind:
            return
        if self.actor and self.anim_state == "hit":
            hit_control = self.actor.getAnimControl("hit")
            if hit_control and hit_control.isPlaying():
                return
        # Attack in the direction the character is visibly facing. The old
        # camera-forward snap made the sword and hit test disagree.
        if self.facing.length() <= 0.001:
            self.facing = Vec3(0, 0, 1)
        else:
            self.facing = Vec3(self.facing.x, 0, self.facing.z).normalized()
        self.rotation_y = math.degrees(math.atan2(self.facing.x, self.facing.z))
        self.locked_attack_facing = Vec3(self.facing)
        durations = {
            "sword": PLAYER_ATTACK_COOLDOWN,
            "punch": PLAYER_PUNCH_DURATION,
            "kick": PLAYER_KICK_DURATION,
        }
        cooldowns = {
            "sword": PLAYER_ATTACK_COOLDOWN,
            "punch": PLAYER_PUNCH_COOLDOWN,
            "kick": PLAYER_KICK_COOLDOWN,
        }
        duration = durations[action]
        self.attack_cooldown = cooldowns[action]
        self.attack_timer = duration
        self.attack_duration = duration
        self.attack_kind = action
        self.attack_power = max(0.0, min(1.0, charge_ratio)) if action in {"punch", "kick"} else 0.0
        self.attack_damage = PLAYER_DAMAGE if action == "sword" else self._charged_damage(action, self.attack_power)
        if action == "kick":
            self.kick_travel_total = PLAYER_KICK_MIN_TRAVEL + (PLAYER_KICK_MAX_TRAVEL - PLAYER_KICK_MIN_TRAVEL) * self.attack_power
            self.kick_jump_height = PLAYER_KICK_MIN_HEIGHT + (PLAYER_KICK_MAX_HEIGHT - PLAYER_KICK_MIN_HEIGHT) * self.attack_power
        else:
            self.kick_travel_total = 0.0
            self.kick_jump_height = 0.0
        self.previous_action_progress = 0.0
        self.hit_this_swing.clear()
        self.previous_sword_segment = None
        self.previous_limb_contact = None
        if self.actor:
            if hasattr(self.actor, "set_action_power"):
                self.actor.set_action_power(self.attack_power)
            self.actor.play(action)
            self.anim_state = action
            if hasattr(self.actor, "sync_action_progress"):
                self.actor.sync_action_progress(action, 0.0)
            if action in {"punch", "kick"} and hasattr(self.actor, "limb_contact_world"):
                self.previous_limb_contact = self.actor.limb_contact_world(action)
        # Sword contact is valid at the start of its physical arc. Punch/kick
        # deliberately wait until the fist/foot reaches its active strike
        # window, so they cannot damage an enemy before visible contact.
        if action == "sword":
            self.game.resolve_attack()

    def dance(self, name: str) -> None:
        """Start a stationary emote; movement or combat can interrupt it."""
        if not self.actor or name not in {"dance_1", "dance_2", "dance_3"}:
            return
        if self.attack_timer > 0 or self.attack_cooldown > 0 or self.charge_kind:
            return
        if any(
            held_keys[key]
            for key in ("w", "a", "s", "d", "up arrow", "down arrow", "left arrow", "right arrow")
        ):
            return
        if self.anim_state == "hit":
            hit_control = self.actor.getAnimControl("hit")
            if hit_control and hit_control.isPlaying():
                return
        self.actor.play(name)
        self.anim_state = name


class RuntimeController(Entity):
    """Engine-facing bridge so Ursina dispatches update/input directly to the game."""

    def __init__(self, game: "DungeonFall3D") -> None:
        super().__init__(eternal=True)
        self.game = game

    def update(self) -> None:
        self.game.update()

    def input(self, key: str) -> None:
        self.game.input(key)


class DungeonFall3D:
    MENU = "menu"
    PLAYING = "playing"
    PAUSED = "paused"
    LOST = "lost"
    WON = "won"

    def __init__(self) -> None:
        self.app = Ursina(borderless=False)
        window.title = WINDOW_TITLE
        # Ursina's internal fullscreen flag defaults to True on this build even
        # though the initial window is actually a centered window.  Normalize
        # it so the very first F10 press always enters real fullscreen.
        if window.fullscreen:
            window.fullscreen = False
        window.color = c255(12, 14, 20)
        window.exit_button.visible = False
        window.fps_counter.enabled = False
        # Hide Ursina's development/editor chrome completely. These widgets
        # were visible in the user's runtime screenshot and are not part of
        # the game UI.
        window.editor_ui.enabled = False
        window.entity_counter.enabled = False
        window.collider_counter.enabled = False
        window.cog_button.enabled = False
        window.render_mode = "default"
        # Ursina 8.3 also binds F10 on its hidden developer input entity to
        # cycle render modes (default -> wireframe -> ...).  Our game uses F10
        # for fullscreen, so leaving that handler active makes a single press
        # both resize the window and switch the entire scene to wireframe,
        # which looks like transparent/striped characters.  Disable the hidden
        # dev-key listener; it is not part of the shipped game controls.
        if getattr(window, "input_entity", None):
            window.input_entity.enabled = False
        native_props = WindowProperties()
        native_props.set_title(WINDOW_TITLE)
        application.base.win.request_properties(native_props)
        mouse.locked = False

        # Global PBR + tone mapping pipeline. World entities intentionally do
        # not set their own shader so they inherit this pipeline.
        self.pbr = simplepbr.init(
            msaa_samples=2,
            max_lights=8,
            use_normal_maps=True,
            use_emission_maps=True,
            use_occlusion_maps=True,
            # The detailed character rigs are driven directly through their
            # joints. Panda's CPU skinning path is required for those runtime
            # joint controls to deform the mesh correctly.
            use_hardware_skinning=False,
            exposure=-0.88,
            enable_shadows=True,
            shadow_bias=0.0025,
            enable_fog=True,
        )

        self.state = self.MENU
        self.room_index = 0
        self.room_entities: list[Entity] = []
        self.obstacles: list[tuple[Entity, float, float]] = []
        self.enemies: list[Enemy] = []
        self.pickups: list[Pickup] = []
        self.effects: list[EffectParticle] = []
        self.damage_numbers: list[FloatingDamageNumber] = []
        self.damage_banner_timer = 0.0
        self.player: Player | None = None
        self.health_spawn_timer = random.uniform(HEALTH_SPAWN_MIN, HEALTH_SPAWN_MAX)
        self.transition_lock = 0.0
        self.door_entity: Entity | None = None
        self.portal_entity: Entity | None = None
        self.room_decor: list[Entity] = []
        # Aim the initial view along a clear diagonal through Room 1 rather than
        # directly at the short wall / first obstacle. W now has useful travel
        # distance immediately after launch while remaining camera-relative.
        self.camera_yaw = 65.0
        self.camera_pitch = CAMERA_PITCH
        self.camera_distance = CAMERA_DISTANCE
        self.pre_pause_mouse_locked = True
        self.keys_down: set[str] = set()
        self.runtime_controller = RuntimeController(self)
        self.player_hit_tint_timer = 0.0
        self.camera_shake_timer = 0.0
        self.camera_shake_duration = 0.16
        self.camera_shake_strength = 0.0
        self.death_sequence_timer = 0.0
        self.death_sequence_duration = 1.05

        # A single shadowed key light plus a restrained ambient fill gives the
        # stylized geometry real depth without fighting Ursina's one-light
        # built-in shadow shader.
        AmbientLight(color=c255(4, 5, 9))
        self.sun = DirectionalLight(
            shadows=True,
            shadow_map_resolution=(2048, 2048),
            color=c255(42, 52, 82),
        )
        self.sun.look_at(Vec3(1.2, -2.4, -1.0))
        # Low-intensity warm fill keeps faces/armor from collapsing into a
        # single flat value while the cool key light still defines the room.
        self.fill_light = DirectionalLight(shadows=False, color=c255(26, 22, 18))
        self.fill_light.look_at(Vec3(-1.0, -0.7, 1.2))
        self.shadow_bounds = Entity(
            model="cube",
            visible=False,
            position=(0, WALL_HEIGHT / 2, 0),
            scale=(ROOM_HALF_WIDTH * 2.2, WALL_HEIGHT + 2.0, ROOM_HALF_DEPTH * 2.2),
        )
        self.sky = Sky(color=c255(5, 7, 12))
        scene.fog_color = c255(8, 10, 15)
        scene.fog_density = (12, 30)

        self.camera_rig = Entity(position=(0, 1.5, 0))
        self.camera_pitch_pivot = Entity(parent=self.camera_rig, rotation_x=self.camera_pitch)
        camera.parent = self.camera_pitch_pivot
        camera.position = (0, 0, -self.camera_distance)
        camera.rotation = (0, 0, 0)
        camera.fov = 60

        # Ursina 8.3 Text renders reliably when parented directly to camera.ui.
        # Keep lightweight group entities only as visibility/state flags and
        # explicitly toggle their direct UI children together. camera.ui uses
        # normal Ursina UI coordinates (roughly y +/-0.5), so HUD values below
        # deliberately use normal screen-sized positions/scales. The previous
        # 0.02-ish positions and 0.04-ish text scales made the HUD microscopic
        # and placed it around the center of the screen.
        self.hud = Entity(parent=camera.ui, enabled=False)
        # Clear player-health card in the top-left.  The previous thin red bar
        # blended into combat effects and was easy to miss; use a larger green
        # bar with an explicit PLAYER HP label and numeric value.
        # Explicit UI depth ordering matters in this Ursina build: larger z is
        # drawn in front.  The old panel/background were in front of the fill,
        # so the green health bar could exist but be visually covered.
        self.hp_panel = Entity(
            parent=camera.ui,
            model="quad",
            color=c255(3, 10, 7, 230),
            position=(-0.66, 0.43, 0.01),
            scale=(0.38, 0.12),
            enabled=False,
            always_on_top=True,
        )
        self.hp_bar_bg = Entity(
            parent=camera.ui,
            model="quad",
            color=c255(12, 34, 22, 255),
            position=(-0.66, 0.414, 0.02),
            scale=(0.31, 0.030),
            enabled=False,
            always_on_top=True,
        )
        self.hp_bar_fill = Entity(
            parent=camera.ui,
            model="quad",
            color=c255(35, 238, 94, 255),
            position=(-0.66, 0.414, 0.03),
            scale=(0.305, 0.022),
            enabled=False,
            always_on_top=True,
        )
        self.room_panel = Entity(parent=camera.ui, model="quad", color=c255(5, 8, 13, 185), position=(0, 0.455, 0.10), scale=(0.26, 0.070), enabled=False, always_on_top=True)
        self.coin_panel = Entity(parent=camera.ui, model="quad", color=c255(5, 8, 13, 185), position=(0.70, 0.455, 0.10), scale=(0.26, 0.070), enabled=False, always_on_top=True)
        self.hp_text = Text(parent=camera.ui, text="PLAYER HP   100/100", position=(-0.825, 0.468), scale=0.74, color=c255(225, 255, 235), enabled=False, always_on_top=True)
        # Text-rendered fallback health bar.  This is deliberately independent
        # of the quad bar so the HP indicator remains visible even on drivers
        # where camera.ui quad depth ordering behaves inconsistently.
        self.hp_bar_text_bg = Text(
            parent=camera.ui,
            text="====================",
            position=(-0.825, 0.388),
            scale=0.53,
            color=c255(28, 54, 39),
            enabled=False,
            always_on_top=True,
        )
        self.hp_bar_text_fill = Text(
            parent=camera.ui,
            text="====================",
            position=(-0.825, 0.388),
            scale=0.53,
            color=c255(35, 238, 94),
            enabled=False,
            always_on_top=True,
        )
        self.room_text = Text(parent=camera.ui, text="Room 1/4", origin=(0, 0), y=0.462, scale=0.58, enabled=False, always_on_top=True)
        self.coin_text = Text(parent=camera.ui, text="Coins 0", origin=(0, 0), position=(0.70, 0.462), scale=0.58, enabled=False, always_on_top=True)
        self.message_text = Text(parent=camera.ui, text="", origin=(0, 0), y=0.395, scale=0.68, color=color.azure, enabled=False, always_on_top=True)
        self.damage_banner = Text(
            parent=camera.ui,
            text="",
            origin=(0, 0),
            y=0.335,
            scale=0.84,
            color=c255(255, 225, 72),
            enabled=False,
            always_on_top=True,
        )
        self.camera_hint_text = Text(
            parent=camera.ui,
            text="Mouse: camera   Shift: sprint   Hold F: punch   Hold G: flying kick   F10: fullscreen   1/2/3: dance   J/L: orbit   I/K: tilt   Wheel: zoom",
            origin=(0, 0),
            y=-0.475,
            scale=0.39,
            color=c255(210, 220, 235, 180),
            enabled=False,
        )
        self.hud_elements = [
            self.hp_panel,
            self.hp_bar_bg,
            self.hp_bar_fill,
            self.hp_bar_text_bg,
            self.hp_bar_text_fill,
            self.room_panel,
            self.coin_panel,
            self.hp_text,
            self.room_text,
            self.coin_text,
            self.message_text,
            self.camera_hint_text,
        ]

        self.charge_bg = Entity(
            parent=camera.ui,
            model="quad",
            color=c255(8, 10, 15, 205),
            position=(0, -0.410, 0.02),
            scale=(0.38, 0.032),
            enabled=False,
            always_on_top=True,
        )
        self.charge_fill = Entity(
            parent=camera.ui,
            model="quad",
            color=c255(232, 154, 54, 240),
            position=(-0.185, -0.410, 0.03),
            origin=(-0.5, 0),
            scale=(0.0, 0.022),
            enabled=False,
            always_on_top=True,
        )
        self.charge_text = Text(
            parent=camera.ui,
            text="",
            origin=(0, 0),
            y=-0.372,
            scale=0.62,
            color=c255(255, 226, 164),
            always_on_top=True,
            enabled=False,
        )

        # Do not use a full-screen damage quad. On lethal hits it could freeze
        # after the state changed and obscure the whole scene. Impacts are now
        # communicated by character tint, particles and a small camera impulse.

        self.overlay = Entity(parent=camera.ui)
        self.overlay_bg = Entity(
            parent=camera.ui,
            model="quad",
            color=c255(5, 6, 10, 205),
            scale=(0.62, 0.23),
            z=0.1,
        )
        self.overlay_title = Text(
            parent=camera.ui,
            text="DUNGEONFALL 3D",
            origin=(0, 0),
            y=0.08,
            scale=1.45,
            always_on_top=True,
        )
        self.overlay_line = Text(
            parent=camera.ui,
            text="WASD walk   •   Shift sprint   •   Space sword   •   Hold F punch   •   Hold G flying kick",
            origin=(0, 0),
            y=0.0,
            scale=0.62,
            always_on_top=True,
        )
        self.overlay_hint = Text(
            parent=camera.ui,
            text="Press ENTER to descend",
            origin=(0, 0),
            y=-0.08,
            scale=0.58,
            color=color.azure,
            always_on_top=True,
        )
        self.overlay_elements = [self.overlay_bg, self.overlay_title, self.overlay_line, self.overlay_hint]
        self.set_overlay_visible(True)
        # Start straight in the 3D dungeon so launch always shows gameplay.
        # The menu remains available from end/pause flows.
        self.new_game()

    def run(self) -> None:
        # Skip Ursina's optional package/version info scan; on some Windows
        # Python installs it can delay the game window for several seconds.
        self.app.run(info=False)

    def set_hud_visible(self, visible: bool) -> None:
        self.hud.enabled = visible
        for element in self.hud_elements:
            element.enabled = visible
        if not visible:
            self.hide_charge_display()

    def update_charge_display(self, action: str, ratio: float, preview_damage: int) -> None:
        ratio = max(0.0, min(1.0, ratio))
        self.charge_bg.enabled = True
        self.charge_fill.enabled = True
        self.charge_text.enabled = True
        self.charge_fill.scale_x = 0.37 * ratio
        if ratio >= 0.99:
            self.charge_fill.color = c255(255, 79, 54, 245)
        elif action == "kick":
            self.charge_fill.color = c255(235, 104, 52, 240)
        else:
            self.charge_fill.color = c255(232, 154, 54, 240)
        label = "FLYING KICK" if action == "kick" else "PUNCH"
        self.charge_text.text = f"{label}  {round(ratio * 100):d}%   DAMAGE {preview_damage}"

    def hide_charge_display(self) -> None:
        self.charge_bg.enabled = False
        self.charge_fill.enabled = False
        self.charge_text.enabled = False

    def set_overlay_visible(self, visible: bool) -> None:
        self.overlay.enabled = visible
        for element in self.overlay_elements:
            element.enabled = visible

    def input(self, key: str) -> None:
        # F10 is available in every state (playing, paused, menu, win/lose) so
        # the user can always switch between windowed and fullscreen mode.
        if key == "f10":
            window.fullscreen = not bool(window.fullscreen)
            return

        if self.state == self.PLAYING and self.death_sequence_timer > 0.0:
            self.keys_down.clear()
            return

        if self.state == self.PLAYING and self.player:
            if key == "f":
                self.player.begin_charge("punch")
                return
            if key == "g":
                self.player.begin_charge("kick")
                return
            if key == "f up":
                self.player.release_charge("punch")
                return
            if key == "g up":
                self.player.release_charge("kick")
                return

        continuous_keys = {
            "w", "a", "s", "d", "up arrow", "down arrow", "left arrow", "right arrow",
            "j", "l", "i", "k", "left shift", "right shift",
        }
        if key.endswith(" up"):
            released = key[:-3]
            self.keys_down.discard(released)
            if released in continuous_keys:
                return
        elif key in continuous_keys:
            if self.state == self.PLAYING:
                self.keys_down.add(key)
            return

        if key == "escape":
            if self.state == self.PLAYING:
                self.set_paused(True)
            elif self.state == self.PAUSED:
                self.set_paused(False)
            elif self.state in (self.WON, self.LOST):
                self.show_menu()
            return

        if self.state == self.MENU:
            if key in ("enter", "space"):
                self.new_game()
            elif key == "q":
                application.quit()
            return

        if self.state == self.PAUSED:
            if key == "q":
                self.show_menu()
            return

        if self.state in (self.WON, self.LOST):
            if key == "r":
                self.new_game()
            elif key == "enter":
                self.show_menu()
            elif key == "q":
                application.quit()
            return

        if self.state == self.PLAYING:
            if key in ("space", "left mouse down") and self.player:
                self.player.attack()
            elif key in {"1", "2", "3"} and self.player:
                self.player.dance({"1": "dance_1", "2": "dance_2", "3": "dance_3"}[key])
            elif key == "scroll up":
                self.camera_distance = max(CAMERA_MIN_DISTANCE, self.camera_distance - CAMERA_ZOOM_STEP)
            elif key == "scroll down":
                self.camera_distance = min(CAMERA_MAX_DISTANCE, self.camera_distance + CAMERA_ZOOM_STEP)
            elif key == "c":
                mouse.locked = not mouse.locked

    def new_game(self) -> None:
        self.keys_down.clear()
        self.hide_charge_display()
        self.clear_room()
        for effect in self.effects:
            destroy(effect)
        self.effects.clear()
        for number in self.damage_numbers:
            number.destroy()
        self.damage_numbers.clear()
        self.damage_banner_timer = 0.0
        self.damage_banner.enabled = False
        if self.player:
            destroy(self.player)
        self.player = Player(self)
        self.room_index = 0
        self.health_spawn_timer = random.uniform(HEALTH_SPAWN_MIN, HEALTH_SPAWN_MAX)
        self.load_room(0)
        self.state = self.PLAYING
        self.set_hud_visible(True)
        self.set_overlay_visible(False)
        self.hp_text.text = "PLAYER HP   100/100"
        self.hp_bar_fill.scale_x = 0.305
        self.hp_bar_fill.x = -0.66
        self.hp_bar_text_fill.text = "===================="
        self.camera_yaw = 65.0
        self.camera_pitch = CAMERA_PITCH
        self.camera_distance = CAMERA_DISTANCE
        self.player_hit_tint_timer = 0.0
        self.camera_shake_timer = 0.0
        self.camera_shake_strength = 0.0
        self.death_sequence_timer = 0.0
        mouse.locked = True
        self.update_camera()

    def show_menu(self) -> None:
        self.keys_down.clear()
        for number in self.damage_numbers:
            number.destroy()
        self.damage_numbers.clear()
        self.damage_banner_timer = 0.0
        self.damage_banner.enabled = False
        self.player_hit_tint_timer = 0.0
        self.camera_shake_timer = 0.0
        self.camera_shake_strength = 0.0
        if self.player and self.player.actor:
            self.player.actor.clearColorScale()
        self.state = self.MENU
        self.set_hud_visible(False)
        self.set_overlay_visible(True)
        self.overlay_bg.scale = (0.84, 0.28)
        self.overlay_title.scale = 1.35
        self.overlay_line.scale = 0.42
        self.overlay_hint.scale = 0.56
        mouse.locked = False
        self.overlay_title.text = "DUNGEONFALL 3D"
        self.overlay_line.text = "WASD walk   •   Shift sprint   •   Space sword   •   Hold F punch   •   Hold G flying kick   •   1/2/3 dance"
        self.overlay_hint.text = "Press ENTER to descend"

    def set_paused(self, paused: bool) -> None:
        if paused:
            self.keys_down.clear()
            if self.player:
                self.player.cancel_charge(clear_key_latch=True)
            for number in self.damage_numbers:
                number.destroy()
            self.damage_numbers.clear()
            self.damage_banner_timer = 0.0
            self.damage_banner.enabled = False
            self.player_hit_tint_timer = 0.0
            self.camera_shake_timer = 0.0
            self.camera_shake_strength = 0.0
            if self.player and self.player.actor:
                self.player.actor.clearColorScale()
            self.pre_pause_mouse_locked = mouse.locked
            self.state = self.PAUSED
            self.set_overlay_visible(True)
            self.overlay_bg.scale = (0.58, 0.24)
            self.overlay_title.scale = 1.30
            self.overlay_line.scale = 0.52
            self.overlay_hint.scale = 0.52
            mouse.locked = False
            self.overlay_title.text = "PAUSED"
            self.overlay_line.text = "Combat and health spawning are frozen"
            self.overlay_hint.text = "Esc to resume   •   Q for menu"
        else:
            self.state = self.PLAYING
            self.set_overlay_visible(False)
            mouse.locked = self.pre_pause_mouse_locked

    def clear_room(self) -> None:
        for entity in self.room_entities + self.enemies + self.pickups:
            if entity:
                destroy(entity)
        self.room_entities.clear()
        self.obstacles.clear()
        self.enemies.clear()
        self.pickups.clear()
        self.room_decor.clear()
        self.door_entity = None
        self.portal_entity = None

    def load_room(self, index: int) -> None:
        self.clear_room()
        self.room_index = index
        spec = ROOMS[index]
        self.transition_lock = 0.45
        self.health_spawn_timer = random.uniform(HEALTH_SPAWN_MIN, HEALTH_SPAWN_MAX)
        self.build_room_shell()
        for obstacle in spec.obstacles:
            block = tangent_cube_entity(
                color=c255(150, 154, 162),
                position=(obstacle.x, obstacle.height / 2, obstacle.z),
                scale=(obstacle.width, obstacle.height, obstacle.depth),
                texture="assets3d/pbr/stone_wall_diff_2k.jpg",
                texture_scale=(max(1.0, obstacle.width / 1.6), max(1.0, obstacle.height / 1.2)),
                roughness=1.0,
                normal_map="assets3d/pbr/stone_wall_nor_2k.jpg",
                selector_map="assets3d/pbr/stone_wall_arm_2k.jpg",
                collider="box",
            )
            self.room_entities.append(block)
            self.obstacles.append((block, obstacle.width / 2, obstacle.depth / 2))

            # Dark stone cap + foot makes obstacles feel built into the room
            # rather than plain collision boxes.
            cap = lit_entity(
                model="cube",
                color=c255(57, 60, 72),
                position=(obstacle.x, obstacle.height + 0.07, obstacle.z),
                scale=(obstacle.width + 0.10, 0.14, obstacle.depth + 0.10),
            )
            foot = lit_entity(
                model="cube",
                color=c255(44, 47, 56),
                position=(obstacle.x, 0.08, obstacle.z),
                scale=(obstacle.width + 0.13, 0.16, obstacle.depth + 0.13),
            )
            self.room_entities.extend([cap, foot])
        self.enemies = [Enemy(self, e) for e in spec.enemies]
        self.sun.update_bounds(self.shadow_bounds)
        if self.player:
            self.player.position = (-7.4, 0.0, 0.0)
            self.update_camera()
        self.message_text.text = spec.name

    def build_room_shell(self) -> None:
        floor = tangent_cube_entity(
            color=color.white,
            position=(0, -0.24, 0),
            scale=(ROOM_HALF_WIDTH * 2, 0.48, ROOM_HALF_DEPTH * 2),
            texture="assets3d/pbr/stone_floor_diff_2k.jpg",
            texture_scale=(7.0, 4.1),
            roughness=1.0,
            normal_map="assets3d/pbr/stone_floor_nor_2k.jpg",
            selector_map="assets3d/pbr/stone_floor_arm_2k.jpg",
        )
        self.room_entities.append(floor)
        ceiling = tangent_cube_entity(
            color=c255(70, 74, 82),
            position=(0, WALL_HEIGHT + 0.18, 0),
            scale=(ROOM_HALF_WIDTH * 2, 0.20, ROOM_HALF_DEPTH * 2),
            texture="assets3d/pbr/stone_wall_diff_2k.jpg",
            texture_scale=(7.0, 4.0),
            roughness=1.0,
            normal_map="assets3d/pbr/stone_wall_nor_2k.jpg",
            selector_map="assets3d/pbr/stone_wall_arm_2k.jpg",
        )
        self.room_entities.append(ceiling)

        walls = (
            (-ROOM_HALF_WIDTH, WALL_HEIGHT / 2, 0, WALL_THICKNESS, WALL_HEIGHT, ROOM_HALF_DEPTH * 2),
            (0, WALL_HEIGHT / 2, -ROOM_HALF_DEPTH, ROOM_HALF_WIDTH * 2, WALL_HEIGHT, WALL_THICKNESS),
            (0, WALL_HEIGHT / 2, ROOM_HALF_DEPTH, ROOM_HALF_WIDTH * 2, WALL_HEIGHT, WALL_THICKNESS),
        )
        for x, y, z, sx, sy, sz in walls:
            wall = tangent_cube_entity(
                color=color.white,
                position=(x, y, z),
                scale=(sx, sy, sz),
                texture="assets3d/pbr/stone_wall_diff_2k.jpg",
                texture_scale=(max(1.0, sx / 2.6), max(1.0, sy / 1.8)),
                roughness=1.0,
                normal_map="assets3d/pbr/stone_wall_nor_2k.jpg",
                selector_map="assets3d/pbr/stone_wall_arm_2k.jpg",
                collider="box",
            )
            self.room_entities.append(wall)

        side_depth = ROOM_HALF_DEPTH - DOOR_HALF_WIDTH
        for z in (-((ROOM_HALF_DEPTH + DOOR_HALF_WIDTH) / 2), ((ROOM_HALF_DEPTH + DOOR_HALF_WIDTH) / 2)):
            wall = tangent_cube_entity(
                color=color.white,
                position=(ROOM_HALF_WIDTH, WALL_HEIGHT / 2, z),
                scale=(WALL_THICKNESS, WALL_HEIGHT, side_depth),
                texture="assets3d/pbr/stone_wall_diff_2k.jpg",
                texture_scale=(1.0, 2.0),
                roughness=1.0,
                normal_map="assets3d/pbr/stone_wall_nor_2k.jpg",
                selector_map="assets3d/pbr/stone_wall_arm_2k.jpg",
                collider="box",
            )
            self.room_entities.append(wall)

        # Architectural trim gives the room readable depth at a glance.
        trim_color = c255(44, 47, 58)
        for z in (-ROOM_HALF_DEPTH + 0.20, ROOM_HALF_DEPTH - 0.20):
            self.room_entities.append(lit_entity(model="cube", color=trim_color, position=(0, 0.14, z), scale=(ROOM_HALF_WIDTH * 2, 0.20, 0.22)))
            self.room_entities.append(lit_entity(model="cube", color=trim_color, position=(0, WALL_HEIGHT - 0.12, z), scale=(ROOM_HALF_WIDTH * 2, 0.18, 0.22)))
        self.room_entities.append(lit_entity(model="cube", color=trim_color, position=(-ROOM_HALF_WIDTH + 0.20, 0.14, 0), scale=(0.22, 0.20, ROOM_HALF_DEPTH * 2)))

        # Authored round stone pillars and wall torches make the room feel built.
        pillar_positions = (
            (-ROOM_HALF_WIDTH + 0.65, -ROOM_HALF_DEPTH + 0.65),
            (-ROOM_HALF_WIDTH + 0.65, ROOM_HALF_DEPTH - 0.65),
            (ROOM_HALF_WIDTH - 0.65, -ROOM_HALF_DEPTH + 0.65),
            (ROOM_HALF_WIDTH - 0.65, ROOM_HALF_DEPTH - 0.65),
        )
        for px, pz in pillar_positions:
            pillar = quaternius_entity(
                "Column_Round",
                position=(px, 0, pz),
                scale=(1.25, 1.10, 1.25),
                material_tint=(0.75, 0.86, 1.16, 1.0),
            )
            self.room_entities.append(pillar)

        # Gothic stone arch frames the east-room exit while the existing
        # collision shell continues to own progression/camera blocking.
        self.room_entities.append(
            quaternius_entity(
                "Wall_ArchGothic",
                position=(11.48, 0, 0),
                rotation_y=90,
                scale=(0.91, 1.10, 1.0),
                material_tint=(0.75, 0.86, 1.16, 1.0),
            )
        )

        for torch_pos in ((-8.0, 1.55, -ROOM_HALF_DEPTH + 0.46), (2.2, 1.55, -ROOM_HALF_DEPTH + 0.46), (-4.0, 1.55, ROOM_HALF_DEPTH - 0.46), (6.8, 1.55, ROOM_HALF_DEPTH - 0.46)):
            torch_parts = add_torch(torch_pos)
            self.room_entities.append(torch_parts[0])
            inward_z = torch_pos[2] + (1.05 if torch_pos[2] < 0 else -1.05)
            glow = Entity(
                model="quad",
                texture="radial_gradient",
                color=c255(255, 126, 54, 38),
                position=(torch_pos[0], 0.022, inward_z),
                rotation_x=90,
                scale=(2.5, 2.5),
                double_sided=True,
            )
            self.room_entities.append(glow)

        # Room-specific authored dressing avoids the repeated "test arena"
        # look while staying collider-free so combat/navigation remain stable.
        room_props = (
            (
                ("Bookcase_Full", (-3.7, 0, 5.95), 0.78, 180),
                ("Barrel", (-1.8, 0, 5.35), 0.92, 12),
                ("Barrel", (-1.0, 0, 5.58), 0.72, -16),
                ("Candles_1", (1.8, 0, 5.45), 1.05, 0),
                ("Bricks", (5.4, 0.02, 5.15), 0.82, 22),
            ),
            (
                ("Bookcase_Full", (6.2, 0, -6.05), 0.82, 180),
                ("Barrel", (-6.3, 0, 5.45), 0.95, -18),
                ("Candles_1", (-1.4, 0, -5.55), 0.92, 0),
                ("Bricks", (7.0, 0.02, 5.25), 1.0, -14),
            ),
            (
                ("Bookcase_Full", (-6.6, 0, 5.98), 0.76, 180),
                ("Bookcase_Full", (5.9, 0, -6.02), 0.76, 0),
                ("Barrel", (7.6, 0, 5.35), 0.90, 24),
                ("Candles_1", (0.4, 0, 5.55), 1.0, 0),
                ("Bricks", (-3.6, 0.02, -5.20), 0.90, 8),
            ),
            (
                ("Bookcase_Full", (-6.4, 0, -6.05), 0.72, 0),
                ("Barrel", (6.8, 0, -5.42), 0.92, 10),
                ("Candles_1", (-4.1, 0, 5.55), 1.1, 0),
                ("Candles_1", (4.1, 0, 5.55), 1.1, 0),
                ("Bricks", (0.0, 0.02, -5.10), 1.05, 0),
            ),
        )
        for model_name, position, prop_scale, yaw in room_props[self.room_index]:
            prop = quaternius_entity(model_name, position=position, scale=prop_scale, rotation_y=yaw)
            self.room_entities.append(prop)

        if self.room_index in (1, 3):
            rune = add_floor_decal((0, 0.018, 0), (3.4, 3.4, 3.4))
            self.room_entities.append(rune)

    def update_door_visual(self) -> None:
        # The gameplay boundary remains closed on the final room, but once
        # that room is cleared the visible gate should disappear so the
        # portal reads cleanly instead of competing with a locked-door mesh.
        needs_locked = bool(self.enemies)
        if self.door_entity:
            self.door_entity.enabled = needs_locked

        final_room_clear = self.room_index == len(ROOMS) - 1 and not self.enemies
        if final_room_clear and not self.portal_entity:
            self.portal_entity = Entity(position=(ROOM_HALF_WIDTH - 1.8, 1.35, 0))
            style_portal(self.portal_entity)
            Entity(
                parent=self.portal_entity,
                model="quad",
                texture="radial_gradient",
                color=c255(142, 78, 255, 70),
                position=(0, -1.31, 0),
                rotation_x=90,
                scale=(3.2, 3.2),
                double_sided=True,
            )
            self.room_entities.append(self.portal_entity)

    def ensure_door(self) -> None:
        if self.door_entity and self.door_entity in self.room_entities:
            return
        self.door_entity = Entity(position=(ROOM_HALF_WIDTH - 0.22, 1.3, 0))
        slab = quaternius_entity(
            "Doors_GothicArch",
            parent=self.door_entity,
            position=(-0.04, -1.30, 0),
            rotation_y=90,
            scale=(1.42, 1.38, 1.0),
        )
        # Camera collision proxy for the authored multi-part door.
        lit_entity(
            parent=self.door_entity,
            model="cube",
            color=c255(38, 24, 18, 16),
            position=(-0.04, 0.0, 0),
            scale=(0.34, 4.25, DOOR_HALF_WIDTH * 2),
            collider="box",
        )
        # Stone frame around the authored gate.
        for z in (-DOOR_HALF_WIDTH - 0.18, DOOR_HALF_WIDTH + 0.18):
            lit_entity(parent=self.door_entity, model="cube", color=c255(72, 75, 87), texture="assets3d/stone_wall.png", scale=(0.64, 3.15, 0.34), position=(-0.10, 0, z))
        lit_entity(parent=self.door_entity, model="cube", color=c255(63, 66, 78), texture="assets3d/stone_wall.png", scale=(0.64, 0.34, DOOR_HALF_WIDTH * 2 + 0.70), position=(-0.10, 1.48, 0))
        self.room_entities.append(self.door_entity)

    def camera_basis(self) -> tuple[Vec3, Vec3]:
        """Flat forward/right vectors driven by the actual camera rig."""
        forward = Vec3(self.camera_rig.forward.x, 0, self.camera_rig.forward.z)
        right = Vec3(self.camera_rig.right.x, 0, self.camera_rig.right.z)
        if forward.length() > 0:
            forward = forward.normalized()
        if right.length() > 0:
            right = right.normalized()
        return forward, right

    def update_camera_input(self) -> None:
        if self.state != self.PLAYING:
            return

        if mouse.locked:
            self.camera_yaw = (self.camera_yaw + mouse.velocity[0] * CAMERA_MOUSE_SENSITIVITY) % 360.0
            self.camera_pitch -= mouse.velocity[1] * CAMERA_MOUSE_SENSITIVITY

        yaw_input = int("l" in self.keys_down) - int("j" in self.keys_down)
        pitch_input = int("i" in self.keys_down) - int("k" in self.keys_down)
        self.camera_yaw = (self.camera_yaw + yaw_input * CAMERA_KEY_YAW_SPEED * time.dt) % 360.0
        self.camera_pitch += pitch_input * CAMERA_KEY_PITCH_SPEED * time.dt
        self.camera_pitch = max(CAMERA_MIN_PITCH, min(CAMERA_MAX_PITCH, self.camera_pitch))

        self.camera_rig.rotation_y = self.camera_yaw
        self.camera_pitch_pivot.rotation_x = self.camera_pitch

    def update_camera(self) -> None:
        if not self.player:
            return
        visual_lift = max(0.0, min(0.55, self.player.visual.y * 0.45)) if hasattr(self.player, "visual") else 0.0
        target = self.player.position + Vec3(0, CAMERA_TARGET_HEIGHT + visual_lift, 0)
        if self.player.health <= 0:
            if self.death_sequence_timer > 0.0:
                death_progress = 1.0 - self.death_sequence_timer / max(0.001, self.death_sequence_duration)
            else:
                death_progress = 1.0
            death_progress = max(0.0, min(1.0, death_progress))
            fall = 0.5 - 0.5 * math.cos(death_progress * math.pi)
            facing = Vec3(math.sin(math.radians(self.player.rotation_y)), 0, math.cos(math.radians(self.player.rotation_y)))
            target += -facing * (0.65 * fall) + Vec3(0, -0.55 * fall, 0)
        self.camera_rig.position = target
        self.camera_rig.rotation_y = self.camera_yaw
        self.camera_pitch_pivot.rotation_x = self.camera_pitch

        backward = -self.camera_pitch_pivot.forward
        ignored_entities = [self.player, *self.enemies, *self.pickups]
        right = self.camera_pitch_pivot.right
        up = self.camera_pitch_pivot.up
        r = CAMERA_PROBE_RADIUS
        origins = (
            target,
            target + right * r,
            target - right * r,
            target + up * r,
            target - up * r * 0.55,
        )
        hits = [raycast(origin, backward, distance=self.camera_distance, ignore=ignored_entities) for origin in origins]
        hit_distances = [hit.distance for hit in hits if hit.hit]
        safe_distance = self.camera_distance
        if hit_distances:
            safe_distance = min(safe_distance, min(hit_distances) - CAMERA_COLLISION_PADDING)
        # Never allow wall avoidance to collapse the camera into/through the
        # player.  The user's zoom floor is even farther out; this lower hard
        # clearance only applies when a wall is forcing the camera closer.
        safe_distance = max(CAMERA_COLLISION_MIN_DISTANCE, safe_distance)
        shake_x = 0.0
        shake_y = 0.0
        if self.camera_shake_timer > 0.0 and self.camera_shake_strength > 0.0:
            fade = min(1.0, self.camera_shake_timer / max(0.001, self.camera_shake_duration))
            phase = time.time() * 58.0
            shake_x = math.sin(phase) * self.camera_shake_strength * fade
            shake_y = math.cos(phase * 1.37) * self.camera_shake_strength * 0.55 * fade
        camera.position = (shake_x, shake_y, -safe_distance)
        camera.rotation = (0, 0, 0)

    def body_radius(self, actor: Entity) -> float:
        """Gameplay body size used consistently by movement and melee."""
        if actor is self.player:
            return PLAYER_BODY_RADIUS
        if isinstance(actor, Enemy):
            return BRUTE_BODY_RADIUS if actor.kind == "brute" else CRAWLER_BODY_RADIUS
        return 0.45

    def try_move(
        self,
        actor: Entity,
        delta: Vec3,
        radius: float,
        ignore: Entity | None = None,
        *,
        allow_slide: bool = True,
    ) -> Vec3:
        start_x = actor.x
        start_z = actor.z
        door_locked = bool(self.enemies) or self.room_index == len(ROOMS) - 1

        def blocked(test_x: float, test_z: float) -> bool:
            for block, half_w, half_d in self.obstacles:
                # Exact circle-vs-rectangle contact. The previous expanded AABB
                # falsely treated empty corner space as solid, causing snagging.
                closest_x = max(block.x - half_w, min(test_x, block.x + half_w))
                closest_z = max(block.z - half_d, min(test_z, block.z + half_d))
                if math.hypot(test_x - closest_x, test_z - closest_z) < radius:
                    return True
            for enemy in self.enemies:
                if enemy is ignore or not enemy.alive:
                    continue
                other_radius = self.body_radius(enemy)
                if math.hypot(test_x - enemy.x, test_z - enemy.z) < radius + other_radius:
                    return True
            if self.player and self.player is not ignore and actor is not self.player:
                if math.hypot(test_x - self.player.x, test_z - self.player.z) < radius + self.body_radius(self.player):
                    return True
            return False

        # Endpoint-only collision lets fast movement tunnel through a body on a
        # long/slow frame. Split the move into small safe increments instead.
        max_component = max(abs(delta.x), abs(delta.z))
        steps = max(1, math.ceil(max_component / MAX_CHARACTER_MOVE_STEP))
        step_x = delta.x / steps
        step_z = delta.z / steps

        for _ in range(steps):
            nx = actor.x + step_x
            nz = actor.z + step_z

            max_x = ROOM_HALF_WIDTH - radius - 0.35
            if not door_locked and abs(nz) < DOOR_HALF_WIDTH - radius * 0.25:
                max_x = ROOM_HALF_WIDTH + 1.0
            nx = max(-ROOM_HALF_WIDTH + radius + 0.35, min(max_x, nx))
            nz = max(-ROOM_HALF_DEPTH + radius + 0.35, min(ROOM_HALF_DEPTH - radius - 0.35, nz))

            if allow_slide:
                if not blocked(nx, actor.z):
                    actor.x = nx
                if not blocked(actor.x, nz):
                    actor.z = nz
            elif not blocked(nx, nz):
                actor.x = nx
                actor.z = nz
            else:
                break

        return Vec3(actor.x - start_x, 0, actor.z - start_z)

    def melee_path_blocked(self, start: Vec3, end: Vec3, padding: float = 0.05) -> bool:
        """Return True when a gameplay obstacle separates a limb from its target."""
        distance = math.hypot(end.x - start.x, end.z - start.z)
        steps = max(2, math.ceil(distance / 0.08))
        for index in range(1, steps):
            t = index / steps
            x = start.x + (end.x - start.x) * t
            z = start.z + (end.z - start.z) * t
            for block, half_w, half_d in self.obstacles:
                if (
                    block.x - half_w - padding <= x <= block.x + half_w + padding
                    and block.z - half_d - padding <= z <= block.z + half_d + padding
                ):
                    return True
        return False

    def spawn_burst(self, position: Vec3, tint, count: int = 8, speed: float = 2.8, size: float = 0.10) -> None:
        for _ in range(count):
            angle = random.random() * math.tau
            horizontal = random.uniform(speed * 0.35, speed)
            velocity = Vec3(
                math.cos(angle) * horizontal,
                random.uniform(1.2, 3.5),
                math.sin(angle) * horizontal,
            )
            self.effects.append(
                EffectParticle(
                    Vec3(position.x, position.y, position.z),
                    tint,
                    velocity,
                    life=random.uniform(0.30, 0.58),
                    size=random.uniform(size * 0.65, size * 1.35),
                )
            )

    def spawn_damage_number(
        self,
        position: Vec3,
        previous_health: int,
        current_health: int,
        max_health: int,
        *,
        player_hit: bool = False,
    ) -> None:
        """Show actual damage plus remaining health normalized to a 100-point scale."""
        max_health = max(1, int(max_health))
        before_100 = int(round(max(0, previous_health) / max_health * 100.0))
        health_100 = int(round(max(0, current_health) / max_health * 100.0))
        loss_100 = max(0, before_100 - health_100)
        self.damage_numbers.append(
            FloatingDamageNumber(position, loss_100, health_100, player_hit=player_hit)
        )
        self.damage_banner_timer = 1.15
        if player_hit:
            self.damage_banner.text = f"YOU  -{loss_100}     HP {health_100}/100"
            self.damage_banner.color = c255(255, 92, 92)
        else:
            self.damage_banner.text = f"HIT  -{loss_100}     ENEMY HP {health_100}/100"
            self.damage_banner.color = c255(255, 225, 72)
        self.damage_banner.enabled = True

    def update_damage_numbers(self) -> None:
        self.damage_banner_timer = max(0.0, self.damage_banner_timer - time.dt)
        if self.damage_banner_timer <= 0.0:
            self.damage_banner.enabled = False
        for number in list(self.damage_numbers):
            if not number.tick():
                self.damage_numbers.remove(number)
                number.destroy()

    def resolve_attack(self) -> None:
        if not self.player:
            return
        actor = self.player.actor
        if not actor or not hasattr(actor, "weapon_segment_world"):
            return

        current_segment = actor.weapon_segment_world()
        if not current_segment:
            return
        current_base, current_tip = current_segment

        # Interpolate between the previous and current visible blade positions
        # so a fast 210-degree swing cannot tunnel through an enemy on a slow
        # frame. These are purely collision samples; the rendered sword remains
        # at the current pose.
        previous = self.player.previous_sword_segment
        blade_samples: list[tuple[Vec3, Vec3]] = []
        if previous:
            prev_base, prev_tip = previous
            travel = max(
                math.hypot(current_base.x - prev_base.x, current_base.z - prev_base.z),
                math.hypot(current_tip.x - prev_tip.x, current_tip.z - prev_tip.z),
            )
            steps = max(1, min(10, math.ceil(travel / 0.18)))
            for index in range(1, steps + 1):
                t = index / steps
                base = prev_base + (current_base - prev_base) * t
                tip = prev_tip + (current_tip - prev_tip) * t
                blade_samples.append((base, tip))
        else:
            blade_samples.append((current_base, current_tip))
        self.player.previous_sword_segment = (current_base, current_tip)

        def blade_distance_xz(enemy: Enemy, base: Vec3, tip: Vec3) -> float:
            seg_x = tip.x - base.x
            seg_z = tip.z - base.z
            seg_len_sq = seg_x * seg_x + seg_z * seg_z
            if seg_len_sq <= 1e-6:
                return math.hypot(enemy.x - base.x, enemy.z - base.z)
            t = max(
                0.0,
                min(
                    1.0,
                    ((enemy.x - base.x) * seg_x + (enemy.z - base.z) * seg_z) / seg_len_sq,
                ),
            )
            closest_x = base.x + seg_x * t
            closest_z = base.z + seg_z * t
            return math.hypot(enemy.x - closest_x, enemy.z - closest_z)

        killed: list[Enemy] = []
        for enemy in self.enemies:
            if not enemy.alive or enemy.enemy_id in self.player.hit_this_swing:
                continue
            hit_radius = self.body_radius(enemy) + 0.14
            if not any(blade_distance_xz(enemy, base, tip) <= hit_radius for base, tip in blade_samples):
                continue
            self.player.hit_this_swing.add(enemy.enemy_id)
            previous_health = enemy.health
            enemy.take_damage(PLAYER_DAMAGE)
            actual_damage = previous_health - enemy.health
            self.spawn_damage_number(
                enemy.position + Vec3(0, 1.80 if enemy.kind == "brute" else 1.58, 0),
                previous_health,
                enemy.health,
                enemy.max_health,
            )
            # A small dark-red impact burst confirms contact without the old
            # bright white/cyan flash that obscured the sword.
            self.spawn_burst(enemy.position + Vec3(0, 0.55, 0), c255(176, 42, 48), count=5, speed=2.2, size=0.07)
            if not enemy.alive:
                killed.append(enemy)
        for enemy in killed:
            death_color = c255(173, 83, 210) if enemy.kind == "brute" else c255(221, 68, 75)
            self.spawn_burst(enemy.position + Vec3(0, 0.45, 0), death_color, count=18, speed=4.0, size=0.13)
            self.drop_loot(enemy.position)
            if enemy in self.enemies:
                self.enemies.remove(enemy)
            destroy(enemy)

    def resolve_unarmed_attack(self, action: str, previous_progress: float, progress: float) -> None:
        """Resolve punch/kick contact from the real animated fist/foot path.

        Unlike a forward range check, this samples the exposed skeleton marker
        that the player actually sees. The active window prevents damage during
        wind-up/recovery, while interpolation prevents tunneling on slower
        frames. Each enemy can still only be hit once per action.
        """
        if not self.player or action not in {"punch", "kick"}:
            return
        actor = self.player.actor
        if not actor or not hasattr(actor, "limb_contact_world"):
            return

        current = actor.limb_contact_world(action)
        if current is None:
            return

        active_start, active_end = ((0.20, 0.58) if action == "punch" else (0.22, 0.62))
        previous_point = self.player.previous_limb_contact

        # Sample real intermediate poses through the active window. This keeps
        # collision faithful to the curved fist/foot trajectory and also makes
        # a large frame spike unable to tunnel across the whole strike.
        path: list[Vec3] = []
        overlap_start = max(previous_progress, active_start)
        overlap_end = min(progress, active_end)
        if overlap_start <= overlap_end and hasattr(actor, "sync_action_progress"):
            span = max(0.0, overlap_end - overlap_start)
            steps = max(1, min(8, math.ceil(span / 0.06)))
            for index in range(steps + 1):
                sample_progress = overlap_start + span * (index / steps)
                actor.sync_action_progress(action, sample_progress)
                sample = actor.limb_contact_world(action)
                if sample is not None:
                    path.append(sample)
            actor.sync_action_progress(action, progress)
            current = actor.limb_contact_world(action) or current
        elif previous_point is not None and active_start <= previous_progress <= active_end:
            path.extend((previous_point, current))

        self.player.previous_limb_contact = current
        if not path:
            return

        def segment_segment_contact_3d(p1: Vec3, q1: Vec3, p2: Vec3, q2: Vec3) -> tuple[float, Vec3, Vec3]:
            """Shortest distance and closest points between finite 3D segments."""
            d1 = q1 - p1
            d2 = q2 - p2
            r = p1 - p2
            a = d1.dot(d1)
            e = d2.dot(d2)
            f = d2.dot(r)
            eps = 1e-7
            if a <= eps and e <= eps:
                return r.length(), Vec3(p1), Vec3(p2)
            if a <= eps:
                s = 0.0
                t = max(0.0, min(1.0, f / e))
            else:
                c = d1.dot(r)
                if e <= eps:
                    t = 0.0
                    s = max(0.0, min(1.0, -c / a))
                else:
                    b = d1.dot(d2)
                    denom = a * e - b * b
                    s = max(0.0, min(1.0, (b * f - c * e) / denom)) if abs(denom) > eps else 0.0
                    t = (b * s + f) / e
                    if t < 0.0:
                        t = 0.0
                        s = max(0.0, min(1.0, -c / a))
                    elif t > 1.0:
                        t = 1.0
                        s = max(0.0, min(1.0, (b - c) / a))
            c1 = p1 + d1 * s
            c2 = p2 + d2 * t
            return (c1 - c2).length(), c1, c2

        path_segments = list(zip(path, path[1:])) if len(path) > 1 else [(path[0], path[0])]
        damage = max(1, int(self.player.attack_damage))
        limb_radius = 0.12 if action == "punch" else 0.17
        if action == "punch":
            knockback = 0.18 + 0.34 * self.player.attack_power
        else:
            knockback = 0.48 + 0.78 * self.player.attack_power

        killed: list[Enemy] = []
        for enemy in list(self.enemies):
            if not enemy.alive or enemy.enemy_id in self.player.hit_this_swing:
                continue
            # Model the enemy as a vertical body capsule instead of one magic
            # hit point. A chest-level fist and lower kick can therefore make
            # contact with the part of the body they visibly reach.
            body_bottom = enemy.position + Vec3(0, 0.20 if enemy.kind == "brute" else 0.18, 0)
            body_top = enemy.position + Vec3(0, 1.90 if enemy.kind == "brute" else 1.65, 0)
            contact_radius = self.body_radius(enemy) * 0.65 + limb_radius
            contacts = [segment_segment_contact_3d(a, b, body_bottom, body_top) for a, b in path_segments]
            distance, _limb_point, body_point = min(contacts, key=lambda item: item[0])
            if distance > contact_radius:
                continue
            player_to_contact = Vec3(self.player.x, body_point.y, self.player.z)
            if self.melee_path_blocked(player_to_contact, body_point, padding=0.045):
                continue

            self.player.hit_this_swing.add(enemy.enemy_id)
            previous_health = enemy.health
            enemy.take_damage(damage)
            actual_damage = previous_health - enemy.health
            self.spawn_damage_number(
                enemy.position + Vec3(0, 1.80 if enemy.kind == "brute" else 1.58, 0),
                previous_health,
                enemy.health,
                enemy.max_health,
            )

            if action == "punch":
                self.spawn_burst(
                    body_point,
                    c255(224, 72, 48),
                    count=4 + round(4 * self.player.attack_power),
                    speed=1.75 + 0.95 * self.player.attack_power,
                    size=0.050 + 0.020 * self.player.attack_power,
                )
            else:
                # Kick has a heavier impact: a compact red hit plus a low dust
                # puff, both avoiding the white/cyan effects removed earlier.
                self.spawn_burst(
                    body_point,
                    c255(204, 55, 45),
                    count=6 + round(5 * self.player.attack_power),
                    speed=2.25 + 1.25 * self.player.attack_power,
                    size=0.060 + 0.026 * self.player.attack_power,
                )
                self.spawn_burst(
                    enemy.position + Vec3(0, 0.16, 0),
                    c255(166, 126, 82),
                    count=4 + round(5 * self.player.attack_power),
                    speed=1.35 + 0.65 * self.player.attack_power,
                    size=0.068 + 0.022 * self.player.attack_power,
                )
                self.camera_shake_timer = max(self.camera_shake_timer, 0.10)
                self.camera_shake_strength = max(
                    self.camera_shake_strength,
                    0.020 + 0.025 * self.player.attack_power,
                )

            if enemy.alive:
                dx = enemy.x - self.player.x
                dz = enemy.z - self.player.z
                length = max(0.001, math.hypot(dx, dz))
                push = Vec3(dx / length * knockback, 0, dz / length * knockback)
                self.try_move(enemy, push, radius=self.body_radius(enemy), ignore=enemy)
            else:
                killed.append(enemy)

        for enemy in killed:
            death_color = c255(173, 83, 210) if enemy.kind == "brute" else c255(221, 68, 75)
            self.spawn_burst(enemy.position + Vec3(0, 0.45, 0), death_color, count=18, speed=4.0, size=0.13)
            self.drop_loot(enemy.position)
            if enemy in self.enemies:
                self.enemies.remove(enemy)
            destroy(enemy)

    def damage_player(self, amount: int) -> None:
        if not self.player or self.player.invulnerability > 0 or self.death_sequence_timer > 0.0:
            return
        previous_health = self.player.health
        self.player.health = max(0, self.player.health - amount)
        actual_damage = previous_health - self.player.health
        self.spawn_damage_number(
            self.player.position + Vec3(0, 1.75, 0),
            previous_health,
            self.player.health,
            self.player.max_health,
            player_hit=True,
        )
        self.player.invulnerability = PLAYER_INVULNERABILITY
        self.player_hit_tint_timer = 0.18
        self.camera_shake_timer = self.camera_shake_duration
        self.camera_shake_strength = 0.12 if self.player.health <= 0 else 0.075
        self.spawn_burst(self.player.position + Vec3(0, 0.82, 0), c255(220, 48, 54), count=7, speed=2.25, size=0.075)
        if self.player.health <= 0:
            # Death is the only incoming hit that is allowed to cancel a held
            # punch/flying-kick charge. Non-lethal enemy hits keep the charge
            # alive so the player can still release it into a counterattack.
            self.player.cancel_charge(clear_key_latch=True)
            self.keys_down.clear()
            self.death_sequence_timer = self.death_sequence_duration
            self.player.attack_timer = 0.0
            self.player.attack_cooldown = 0.0
            self.player.attack_kind = None
            self.player.visual.y = 0.0
            self.player.previous_sword_segment = None
            self.player.previous_limb_contact = None
            self.player.hit_this_swing.clear()
            # A lethal blow always overrides sword/punch/kick/hit animations.
            if self.player.actor:
                self.player.actor.play("death")
                if hasattr(self.player.actor, "sync_action_progress"):
                    self.player.actor.sync_action_progress("death", 0.0)
                self.player.anim_state = "death"
            # A small floor-level dust burst sells the collapse without putting
            # an opaque UI element between the camera and the action.
            self.spawn_burst(self.player.position + Vec3(0, 0.12, 0), c255(120, 93, 70), count=6, speed=1.25, size=0.07)
            return
        # Do not replace a held charge pose with the normal hit animation.
        # Damage feedback still comes from tint/particles/camera shake, while
        # the charged punch or flying kick remains ready to release.
        if self.player.actor and self.player.attack_timer <= 0 and self.player.charge_kind is None:
            self.player.actor.play("hit")
            self.player.anim_state = "hit"

    def drop_loot(self, position: Vec3) -> None:
        if random.random() < HEALTH_DROP_CHANCE:
            self.pickups.append(Pickup(self, "heal", Vec3(position.x, 0.45, position.z), HEALTH_AMOUNT))
        else:
            self.pickups.append(Pickup(self, "coin", Vec3(position.x, 0.3, position.z), random.randint(8, 18)))

    def spawn_random_health(self) -> bool:
        if sum(1 for p in self.pickups if p.kind == "heal") >= MAX_ROOM_HEALTH:
            return False
        for _ in range(35):
            x = random.uniform(-ROOM_HALF_WIDTH + 1.5, ROOM_HALF_WIDTH - 2.3)
            z = random.uniform(-ROOM_HALF_DEPTH + 1.3, ROOM_HALF_DEPTH - 1.3)
            if self.position_is_free(x, z, 0.75):
                self.pickups.append(Pickup(self, "heal", Vec3(x, 0.45, z), HEALTH_AMOUNT))
                return True
        return False

    def position_is_free(self, x: float, z: float, radius: float) -> bool:
        if self.player and math.hypot(x - self.player.x, z - self.player.z) < 1.8:
            return False
        for block, half_w, half_d in self.obstacles:
            if abs(x - block.x) < half_w + radius and abs(z - block.z) < half_d + radius:
                return False
        for enemy in self.enemies:
            if math.hypot(x - enemy.x, z - enemy.z) < 1.5:
                return False
        for pickup in self.pickups:
            if math.hypot(x - pickup.x, z - pickup.z) < 1.2:
                return False
        return True

    def collect_pickups(self) -> None:
        if not self.player:
            return
        for pickup in list(self.pickups):
            if xz_distance(self.player.position, pickup.position) > 0.9:
                continue
            if pickup.kind == "heal":
                if self.player.health >= self.player.max_health:
                    continue
                self.player.health = min(self.player.max_health, self.player.health + pickup.amount)
                burst_color = c255(96, 255, 158)
            else:
                self.player.coins += pickup.amount
                burst_color = c255(255, 210, 72)
            self.spawn_burst(pickup.position + Vec3(0, 0.20, 0), burst_color, count=11, speed=2.2, size=0.075)
            self.pickups.remove(pickup)
            destroy(pickup)

    def finish(self, result: str) -> None:
        self.hide_charge_display()
        for number in self.damage_numbers:
            number.destroy()
        self.damage_numbers.clear()
        self.damage_banner_timer = 0.0
        self.damage_banner.enabled = False
        self.player_hit_tint_timer = 0.0
        self.camera_shake_timer = 0.0
        self.camera_shake_strength = 0.0
        self.death_sequence_timer = 0.0
        if self.player and self.player.actor:
            self.player.actor.clearColorScale()
        self.state = result
        mouse.locked = False
        self.set_overlay_visible(True)
        if result == self.WON:
            self.overlay_bg.scale = (0.66, 0.23)
            self.overlay_title.scale = 1.35
            self.overlay_line.scale = 0.58
            self.overlay_hint.scale = 0.56
            self.overlay_title.text = "DUNGEON CLEARED"
            self.overlay_line.text = f"You escaped with {self.player.coins if self.player else 0} coins"
        else:
            self.overlay_bg.scale = (0.62, 0.23)
            self.overlay_title.scale = 1.45
            self.overlay_line.scale = 0.62
            self.overlay_hint.scale = 0.58
            self.overlay_title.text = "YOU FELL"
            self.overlay_line.text = "The dungeon claimed another adventurer"
        self.overlay_hint.text = "R to restart   •   Enter for menu   •   Q to quit"

    def update(self) -> None:
        if self.state != self.PLAYING:
            return
        self.transition_lock = max(0.0, self.transition_lock - time.dt)
        self.camera_shake_timer = max(0.0, self.camera_shake_timer - time.dt)
        self.player_hit_tint_timer = max(0.0, self.player_hit_tint_timer - time.dt)

        if self.player and self.player.actor:
            if self.player_hit_tint_timer > 0.0:
                self.player.actor.setColorScale(1.0, 0.34, 0.34, 1.0)
            else:
                self.player.actor.clearColorScale()

        # Lethal hits play out in-world first. Enemies/player controls are
        # frozen, but the camera, death skeleton, particles and room ambience
        # keep updating until the fall finishes.
        if self.death_sequence_timer > 0.0:
            # Clamp the death simulation step so a single render hitch cannot
            # skip the collapse and jump straight to the result screen.
            death_dt = min(time.dt, 0.05)
            self.death_sequence_timer = max(0.0, self.death_sequence_timer - death_dt)
            if self.player:
                death_progress = 1.0 - self.death_sequence_timer / max(0.001, self.death_sequence_duration)
                death_progress = max(0.0, min(1.0, death_progress))
                fall = 0.5 - 0.5 * math.cos(death_progress * math.pi)
                if self.player.actor and hasattr(self.player.actor, "step"):
                    self.player.actor.step(death_dt)
                # Rotate the visual root around the feet so the body actually
                # falls to the floor; the gameplay/collision root stays fixed.
                self.player.visual.rotation_x = -82.0 * fall
                self.player.visual.rotation_z = -4.0 * fall
                self.update_camera()

            for effect in list(self.effects):
                if not effect.tick():
                    self.effects.remove(effect)
                    destroy(effect)
            self.update_damage_numbers()
            for entity in self.room_entities:
                if hasattr(entity, "torch_phase"):
                    animate_torch(entity, time.time())

            if self.player:
                self.hp_text.text = f"PLAYER HP   {self.player.health}/{self.player.max_health}"
                self.hp_bar_fill.scale_x = 0.0001
                self.hp_bar_text_fill.text = ""

            if self.death_sequence_timer <= 0.0:
                self.finish(self.LOST)
            return

        self.ensure_door()
        self.update_door_visual()

        if self.player:
            self.update_camera_input()
            self.player.tick()
            self.update_camera()
        for enemy in list(self.enemies):
            enemy.tick()
        for pickup in list(self.pickups):
            pickup.tick()
        self.collect_pickups()

        for effect in list(self.effects):
            if not effect.tick():
                self.effects.remove(effect)
                destroy(effect)
        self.update_damage_numbers()

        if self.portal_entity:
            animate_portal(self.portal_entity, time.time())

        for entity in self.room_entities:
            if hasattr(entity, "torch_phase"):
                animate_torch(entity, time.time())

        if self.enemies:
            self.health_spawn_timer -= time.dt
            if self.health_spawn_timer <= 0:
                self.spawn_random_health()
                self.health_spawn_timer = random.uniform(HEALTH_SPAWN_MIN, HEALTH_SPAWN_MAX)

        if self.player:
            self.hp_text.text = f"PLAYER HP   {self.player.health}/{self.player.max_health}"
            self.room_text.text = f"Room {self.room_index + 1}/{len(ROOMS)}"
            self.coin_text.text = f"Coins {self.player.coins}"
            ratio = max(0.0, min(1.0, self.player.health / self.player.max_health))
            bar_width = 0.305 * ratio
            self.hp_bar_fill.scale_x = max(0.0001, bar_width)
            self.hp_bar_fill.x = -0.8125 + bar_width / 2
            filled_blocks = int(round(ratio * 20))
            self.hp_bar_text_fill.text = "=" * filled_blocks

        if not self.enemies and self.player and self.transition_lock <= 0:
            if self.room_index == len(ROOMS) - 1:
                if self.player.x > ROOM_HALF_WIDTH - 2.0 and abs(self.player.z) < DOOR_HALF_WIDTH:
                    self.finish(self.WON)
            elif self.player.x > ROOM_HALF_WIDTH - 0.4 and abs(self.player.z) < DOOR_HALF_WIDTH:
                self.load_room(self.room_index + 1)
