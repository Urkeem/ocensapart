"""Dedicated enemy actors and hostile projectiles."""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import pygame

from data.enemies import enemy_definition
from utils import rp


class EnemyAnimationLibrary:
    """Load authored enemy strips lazily using per-animation frame metadata."""

    STATE_MARKERS = {
        "idle": ("idle",),
        "chase": ("run", "walk", "flying"),
        "attack": ("attack01", "attack1", "attack"),
        "special": ("attack02", "attack2", "attack03", "attack3", "attack"),
        "hurt": ("hurt",),
        "death": ("death", "dead"),
    }

    def __init__(self):
        self._cache = {}

    @staticmethod
    def _asset_root(definition) -> Path:
        return Path(rp(*PurePosixPath(definition.asset.root).parts))

    def animation_path(self, definition, state: str, facing: str) -> Path:
        root = self._asset_root(definition)
        directional = root / facing.title()
        search_root = directional if directional.is_dir() else root
        files = sorted(search_root.glob("*.png"), key=lambda path: path.name.lower())
        markers = self.STATE_MARKERS.get(state, self.STATE_MARKERS["idle"])
        for marker in markers:
            for path in files:
                if marker in path.stem.lower():
                    return path
        if state != "idle":
            return self.animation_path(definition, "idle", facing)
        if not files:
            raise FileNotFoundError(f"No animation sheets found below {search_root}")
        return files[0]

    def frames(self, enemy_id: str, state: str, facing: str):
        definition = enemy_definition(enemy_id)
        path = self.animation_path(definition, state, facing)
        cache_key = (enemy_id, str(path), definition.visual_scale)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        sheet = pygame.image.load(str(path)).convert_alpha()
        frame_size = definition.asset.frame_size_for(path.name)
        if frame_size is None:
            frame_size = (sheet.get_height(), sheet.get_height())
        frame_width, frame_height = frame_size
        if (
            frame_width <= 0
            or frame_height <= 0
            or sheet.get_width() % frame_width
            or sheet.get_height() % frame_height
        ):
            raise ValueError(
                f"Enemy sheet {path} cannot be split into {frame_width}x{frame_height} frames"
            )
        frames = []
        for y in range(0, sheet.get_height(), frame_height):
            for x in range(0, sheet.get_width(), frame_width):
                frame = sheet.subsurface((x, y, frame_width, frame_height)).copy()
                if definition.visual_scale != 1:
                    frame = pygame.transform.scale(
                        frame,
                        (
                            round(frame_width * definition.visual_scale),
                            round(frame_height * definition.visual_scale),
                        ),
                    )
                frames.append(frame)
        result = tuple(frames)
        self._cache[cache_key] = result
        return result


class Enemy:
    """State-driven hostile actor shared by melee, ranged, caster, and boss AI."""

    can_take_damage = True
    is_enemy = True
    hostile = True
    managed_by_encounter = True
    name = "enemy"

    def __init__(
        self,
        enemy_id,
        instance_id,
        encounter_id,
        pos,
        *,
        location_id="player_farm",
        leash_radius=650,
        pathfinder=None,
        animation_library=None,
        on_defeated=None,
        on_health_changed=None,
    ):
        self.definition = enemy_definition(enemy_id)
        self.enemy_id = self.definition.id
        self.instance_id = str(instance_id)
        self.save_id = self.instance_id
        self.encounter_id = str(encounter_id)
        self.location_id = str(location_id)
        self.faction = self.definition.faction
        self.pos = pygame.Vector2(pos)
        self.spawn_pos = pygame.Vector2(pos)
        self.leash_radius = float(leash_radius)
        self.pathfinder = pathfinder
        self.animation_library = animation_library or EnemyAnimationLibrary()
        self.on_defeated = on_defeated
        self.on_health_changed = on_health_changed
        self.max_health = self.definition.health
        self.health = self.max_health
        self.facing = "down"
        self.state = "idle"
        self._animation_key = None
        self.frames = ()
        self.image = pygame.Surface((32, 32), pygame.SRCALPHA)
        self.rect = self.image.get_rect(midbottom=pos)
        self.collision_box = self.rect.copy()
        self.index = 0.0
        self.animation_finished = False
        self.attack_cooldown = 0.0
        self.attack_timer = 0.0
        self.hurt_timer = 0.0
        self.death_age = 0.0
        self.death_reported = False
        self.attack_count = 0
        self.direction = pygame.Vector2()
        self._set_state("idle", force=True)

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def is_alive(self):
        return self.health > 0

    @property
    def death_finished(self):
        return not self.is_alive and self.death_age >= 1.1

    def _sync_boxes(self):
        self.rect = self.image.get_rect(midbottom=(round(self.pos.x), round(self.pos.y)))
        width = max(12, round(self.rect.width * 0.38))
        height = max(10, round(self.rect.height * 0.22))
        self.collision_box = pygame.Rect(0, 0, width, height)
        self.collision_box.midbottom = self.rect.midbottom

    def _set_state(self, state, *, force=False):
        key = (state, self.facing)
        if not force and key == self._animation_key:
            self.state = state
            return
        self.state = state
        self._animation_key = key
        self.frames = self.animation_library.frames(self.enemy_id, state, self.facing)
        self.index = 0.0
        self.animation_finished = False
        self.image = self.frames[0]
        self._sync_boxes()

    def _animate(self, dt):
        if self.animation_finished and self.state == "death":
            return
        self.index += self.definition.animation_fps * max(0.0, float(dt))
        if self.state == "death":
            if self.index >= len(self.frames):
                self.index = len(self.frames) - 1
                self.animation_finished = True
        else:
            self.index %= len(self.frames)
        self.image = self.frames[int(self.index)]
        self._sync_boxes()

    def _face(self, delta):
        if delta.length_squared() == 0:
            return
        if abs(delta.x) > abs(delta.y):
            self.facing = "right" if delta.x > 0 else "left"
        else:
            self.facing = "down" if delta.y > 0 else "up"

    def _move(self, direction, distance):
        if direction.length_squared() == 0 or distance <= 0:
            return False
        direction = direction.normalize()
        candidate = self.pos + direction * distance
        if self.pathfinder is not None:
            tile = self.pathfinder.world_to_tile(candidate)
            if not self.pathfinder.is_walkable(tile):
                return False
        self.direction.update(direction)
        self.pos.update(candidate)
        self._sync_boxes()
        return True

    def take_damage(self, amount=1, *, effects=None, source=None):
        if amount <= 0 or not self.is_alive:
            return False
        self.health = max(0, self.health - int(amount))
        if self.on_health_changed is not None:
            self.on_health_changed(self)
        if effects is not None:
            effects.spawn("blood", self.rect.center)
        if self.health <= 0:
            self.direction.update(0, 0)
            self._set_state("death", force=True)
            if not self.death_reported:
                self.death_reported = True
                if self.on_defeated is not None:
                    self.on_defeated(self)
        else:
            self.hurt_timer = 0.22
            self._set_state("hurt", force=True)
        return True

    def _begin_attack(self, player, effects, projectile_callback):
        self.attack_count += 1
        self.attack_cooldown = self.definition.attack_cooldown
        self.attack_timer = 0.42
        self.direction.update(0, 0)
        self._set_state("special" if self.definition.is_boss and self.health <= self.max_health // 2 else "attack")
        profile = self.definition.attack_profile
        if profile in {"ranged", "caster"}:
            if projectile_callback is not None:
                projectile_callback(self, player.feet_collision_box.center)
        elif profile == "boss" and self.health <= self.max_health // 2:
            if projectile_callback is not None:
                for angle in (-22, 0, 22):
                    projectile_callback(self, player.feet_collision_box.center, angle_offset=angle)
            player.take_damage(self.definition.attack_damage, effects=effects, source=self)
        else:
            player.take_damage(self.definition.attack_damage, effects=effects, source=self)

    def update(self, dt, *, player=None, effects=None, projectile_callback=None):
        dt = max(0.0, float(dt))
        self.attack_cooldown = max(0.0, self.attack_cooldown - dt)
        self.attack_timer = max(0.0, self.attack_timer - dt)
        self.hurt_timer = max(0.0, self.hurt_timer - dt)

        if not self.is_alive:
            self.death_age += dt
            self._set_state("death")
            self._animate(dt)
            return
        if self.hurt_timer > 0:
            self.direction.update(0, 0)
            self._set_state("hurt")
            self._animate(dt)
            return
        if player is None or not getattr(player, "is_alive", True):
            self.direction.update(0, 0)
            self._set_state("idle")
            self._animate(dt)
            return

        player_delta = pygame.Vector2(player.feet_collision_box.center) - self.pos
        spawn_delta = self.spawn_pos - self.pos
        distance = player_delta.length()
        from_spawn = self.pos.distance_to(self.spawn_pos)
        if from_spawn > self.leash_radius:
            self._face(spawn_delta)
            moved = self._move(spawn_delta, self.definition.speed * dt)
            self._set_state("chase" if moved else "idle")
        elif self.attack_timer > 0:
            self.direction.update(0, 0)
            self._set_state(self.state if self.state in {"attack", "special"} else "attack")
        elif distance > self.definition.aggro_radius:
            self.direction.update(0, 0)
            self._set_state("idle")
        else:
            self._face(player_delta)
            profile = self.definition.attack_profile
            ranged = profile in {"ranged", "caster"}
            minimum_range = 125 if ranged else 0
            if ranged and distance < minimum_range:
                retreat = -player_delta
                if profile == "caster":
                    retreat = retreat.rotate(35 if self.attack_count % 2 else -35)
                moved = self._move(retreat, self.definition.speed * dt)
                self._set_state("chase" if moved else "idle")
            elif distance > self.definition.attack_range:
                moved = self._move(player_delta, self.definition.speed * dt)
                self._set_state("chase" if moved else "idle")
            elif self.attack_cooldown <= 0:
                self._begin_attack(player, effects, projectile_callback)
            else:
                self.direction.update(0, 0)
                self._set_state("idle")
        self._animate(dt)


class EnemyProjectile:
    """Single-hit projectile with a finite range and stable owner metadata."""

    managed_by_encounter = True
    can_take_damage = False
    is_enemy = False
    hostile = False
    name = "enemy_projectile"

    def __init__(self, projectile_id, owner, target, *, angle_offset=0):
        self.projectile_id = str(projectile_id)
        self.save_id = self.projectile_id
        self.owner = owner
        self.location_id = owner.location_id
        self.damage = owner.definition.attack_damage
        self.pos = pygame.Vector2(owner.rect.center)
        direction = pygame.Vector2(target) - self.pos
        if direction.length_squared() == 0:
            direction.update(0, 1)
        self.velocity = direction.normalize().rotate(float(angle_offset)) * owner.definition.projectile_speed
        self.remaining_range = 620.0
        self.active = True
        self.image = pygame.Surface((14, 6), pygame.SRCALPHA)
        pygame.draw.ellipse(self.image, (244, 191, 72), self.image.get_rect())
        self.image = pygame.transform.rotate(self.image, -self.velocity.angle_to(pygame.Vector2(1, 0)))
        self.rect = self.image.get_rect(center=self.pos)
        self.collision_box = self.rect.inflate(-2, -2)

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def is_alive(self):
        return False

    def update(self, dt, *, player=None, effects=None):
        if not self.active:
            return False
        step = self.velocity * max(0.0, float(dt))
        self.pos += step
        self.remaining_range -= step.length()
        self.rect.center = (round(self.pos.x), round(self.pos.y))
        self.collision_box.center = self.rect.center
        if player is not None and self.collision_box.colliderect(player.feet_collision_box):
            player.take_damage(self.damage, effects=effects, source=self.owner)
            self.active = False
        elif self.remaining_range <= 0:
            self.active = False
        if not self.active and effects is not None:
            effects.arrow_impact(self.rect.center)
        return self.active
