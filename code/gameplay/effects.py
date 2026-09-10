"""Reusable world-space combat FX and environmental particle emitters."""

from __future__ import annotations

from dataclasses import dataclass
import random

import pygame

from utils import rp


@dataclass(frozen=True)
class EffectSpec:
    paths: tuple[tuple[str, ...], ...]
    frame_count: int
    fps: float
    scale: float = 1.0


def _fx(folder, names, frame_count, fps=28, scale=1.0):
    return EffectSpec(
        tuple(("graphics", "effects", "fx", folder, name) for name in names),
        frame_count,
        fps,
        scale,
    )


def _environment(name, fps=16, scale=2.0):
    return EffectSpec(
        (("graphics", "effects", "particles", "environment", f"{name}.png"),),
        6,
        fps,
        scale,
    )


EFFECT_SPECS = {
    "blood": _fx("blood", ("blood_01.png", "blood_02.png", "blood_03.png"), 24, 30),
    "coin": _fx("coin", ("coin_01.png", "coin_02.png", "coin_03.png"), 24, 28),
    "comet": _fx("commet", ("comet_01.png", "comet_02.png", "comet_03.png"), 16, 24),
    "confusion": _fx(
        "confusion",
        ("confusion_01.png", "confusion_02.png", "confusion_03.png"),
        24,
        24,
    ),
    "cut": _fx("cut", ("cut_05.png",), 24, 32),
    "death": _fx("death", ("death_01.png", "death_02.png", "death_03.png"), 24, 26),
    "explosion": _fx(
        "explosion",
        ("explosion_big_01.png", "explosion_big_02.png", "explosion_big_03.png"),
        16,
        24,
    ),
    "fire": _fx("fire", ("fire.png",), 16, 18),
    "gem": _fx("gem", ("gem_01.png", "gem_02.png", "gem_03.png"), 24, 28),
    "impact": _fx("impact", ("impact.png",), 16, 30),
    "spark": _fx("spark", ("spark_01.png", "spark_02.png", "spark_03.png"), 16, 22),
    "bush": _environment("bush", scale=1.0),
    "fruit": _environment("fruit"),
    "grass": _environment("grass", scale=1.0),
    "hay": _environment("hay", scale=1.0),
    "leaf": _environment("leaf", fps=12, scale=1.0),
    "leaf_orange": _environment("leaf_orange", fps=12),
    "petal": _environment("petal", fps=12, scale=1.0),
    "rock": _environment("rock"),
    "sand": _environment("sand", fps=18),
    "shell": _environment("shell"),
    "water": _environment("water"),
    "wood": _environment("wood"),
}


class EffectLibrary:
    """Lazily slice and cache every horizontal strip variant."""

    def __init__(self, specs=None):
        self.specs = specs or EFFECT_SPECS
        self._cache = {}

    def load_variant(self, effect_name, variant_index=0):
        spec = self.specs[effect_name]
        variant_index %= len(spec.paths)
        cache_key = (effect_name, variant_index)
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached

        path = spec.paths[variant_index]
        sheet = pygame.image.load(rp(*path)).convert_alpha()
        if sheet.get_width() % spec.frame_count:
            raise ValueError(
                f"Effect sheet {path!r} cannot be split into "
                f"{spec.frame_count} equal horizontal frames"
            )
        frame_width = sheet.get_width() // spec.frame_count
        frames = []
        for frame_index in range(spec.frame_count):
            frame = sheet.subsurface(
                pygame.Rect(
                    frame_index * frame_width,
                    0,
                    frame_width,
                    sheet.get_height(),
                )
            ).copy()
            if spec.scale != 1:
                frame = pygame.transform.scale(
                    frame,
                    (
                        max(1, round(frame.get_width() * spec.scale)),
                        max(1, round(frame.get_height() * spec.scale)),
                    ),
                )
            frames.append(frame)
        result = tuple(frames)
        self._cache[cache_key] = result
        return result


class EffectAnimation:
    def __init__(
        self,
        frames,
        pos,
        fps,
        *,
        follow=None,
        offset=(0, 0),
        velocity=(0, 0),
        loop=False,
        lifetime=None,
        fade=False,
    ):
        self.frames = frames
        self.pos = pygame.Vector2(pos)
        self.fps = float(fps)
        self.follow = follow
        self.offset = pygame.Vector2(offset)
        self.velocity = pygame.Vector2(velocity)
        self.loop = bool(loop)
        self.lifetime = lifetime
        self.fade = bool(fade)
        self.age = 0.0
        self.index = 0.0
        self.alive = True
        self.image = frames[0]
        self.rect = self.image.get_rect(center=pos)

    @property
    def sort_y(self):
        return self.rect.centery

    def _follow_position(self):
        if self.follow is None:
            return None
        rect = getattr(self.follow, "rect", None)
        if rect is None:
            return None
        return pygame.Vector2(rect.center) + self.offset

    def update(self, dt):
        if not self.alive:
            return
        self.age += dt
        followed = self._follow_position()
        if followed is not None:
            self.pos.update(followed)
        else:
            self.pos += self.velocity * dt

        self.index += self.fps * dt
        if self.loop:
            self.index %= len(self.frames)
        elif self.index >= len(self.frames):
            self.index = len(self.frames) - 1
            self.alive = False
        if self.lifetime is not None and self.age >= self.lifetime:
            self.alive = False

        self.image = self.frames[int(self.index)]
        if self.fade and self.lifetime:
            fade_progress = max(0.0, (self.age / self.lifetime - 0.5) / 0.5)
            if fade_progress > 0:
                self.image = self.image.copy()
                self.image.set_alpha(round(255 * (1.0 - min(1.0, fade_progress))))
        self.rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))


class EffectsManager:
    """Own transient animations and low-frequency world interaction emitters."""

    SPARK_PROP_TYPES = frozenset({"chest", "treasure", "crate", "barrel", "clue"})
    CONTACT_EFFECTS = {
        "bush": "bush",
        "hay": "hay",
        "weed": "grass",
    }

    def __init__(self, library=None, rng=None):
        self.library = library or EffectLibrary()
        self.rng = rng or random.Random()
        self.active = []
        self.spark_cooldown = 0.0
        self._recent_sparks = {}
        self._environment_contacts = set()

    def clear(self):
        self.active.clear()
        self._recent_sparks.clear()
        self._environment_contacts.clear()

    def explosion(self, pos):
        """Public hook for bombs, barrels, spells, and other blast sources."""
        return self.spawn("explosion", pos)

    def start_fire(self, pos, lifetime=1.5):
        """Public hook for world fire sources that need a looping ignition FX."""
        return self.spawn("fire", pos, loop=True, lifetime=lifetime)

    def arrow_impact(self, pos):
        """Public hook for a projectile when its collision is resolved."""
        return self.spawn("impact", pos)

    def spawn(
        self,
        effect_name,
        pos,
        *,
        variant=None,
        follow=None,
        offset=(0, 0),
        velocity=(0, 0),
        loop=False,
        lifetime=None,
        fade=False,
    ):
        spec = self.library.specs[effect_name]
        if variant is None:
            variant = self.rng.randrange(len(spec.paths))
        animation = EffectAnimation(
            self.library.load_variant(effect_name, variant),
            pos,
            spec.fps,
            follow=follow,
            offset=offset,
            velocity=velocity,
            loop=loop,
            lifetime=lifetime,
            fade=fade,
        )
        animation.name = effect_name
        self.active.append(animation)
        return animation

    @staticmethod
    def _nearby_chunks(player, world):
        if world is None:
            return ()
        if hasattr(world, "world_to_chunk") and hasattr(world, "get_chunks_near"):
            center_chunk = world.world_to_chunk(player.center)
            return tuple(
                world.loaded_chunks[coord]
                for coord in world.get_chunks_near(center_chunk, radius=1)
                if coord in world.loaded_chunks
            )
        return tuple(world.loaded_chunks.values())

    def _emit_environment_contacts(self, player, world):
        player_box = getattr(player, "feet_collision_box", None)
        if player_box is None or world is None:
            self._environment_contacts.clear()
            return

        current_contacts = set()
        for chunk in self._nearby_chunks(player, world):
            for prop in chunk.runtime.get("environment_objects", {}).values():
                effect_name = self.CONTACT_EFFECTS.get(getattr(prop, "prop_type", ""))
                if (
                    effect_name is None
                    or not getattr(prop, "alive", False)
                    or not player_box.colliderect(prop.rect)
                ):
                    continue
                contact_key = getattr(prop, "prop_id", id(prop))
                current_contacts.add(contact_key)
                if contact_key not in self._environment_contacts:
                    for _ in range(self.rng.randint(3, 5)):
                        angle = self.rng.uniform(0, 360)
                        direction = pygame.Vector2(1, 0).rotate(angle)
                        speed = self.rng.uniform(28, 62)
                        origin = pygame.Vector2(prop.rect.center) + direction * self.rng.uniform(2, 9)
                        self.spawn(
                            effect_name,
                            origin,
                            variant=0,
                            velocity=direction * speed,
                            loop=True,
                            lifetime=self.rng.uniform(0.7, 1.05),
                            fade=True,
                        )
        self._environment_contacts = current_contacts

    def _highlight_nearby_props(self, player, world):
        if self.spark_cooldown > 0 or world is None:
            return
        radius_squared = 150 * 150
        for chunk in world.loaded_chunks.values():
            for prop in chunk.runtime.get("environment_objects", {}).values():
                if (
                    getattr(prop, "alive", False)
                    and getattr(prop, "prop_type", "") in self.SPARK_PROP_TYPES
                    and pygame.Vector2(prop.rect.center).distance_squared_to(player.center)
                    <= radius_squared
                ):
                    prop_key = getattr(prop, "prop_id", id(prop))
                    if self._recent_sparks.get(prop_key, 0) <= 0:
                        self.spawn(
                            "spark",
                            prop.rect.midtop,
                            follow=prop,
                            offset=(0, -prop.rect.height * 0.35),
                        )
                        self._recent_sparks[prop_key] = 3.0
        self.spark_cooldown = 0.6

    def update(self, dt, *, player=None, weather=None, world=None):
        self.spark_cooldown = max(0.0, self.spark_cooldown - dt)
        for key in tuple(self._recent_sparks):
            remaining = self._recent_sparks[key] - dt
            if remaining <= 0:
                del self._recent_sparks[key]
            else:
                self._recent_sparks[key] = remaining

        if player is not None and getattr(player, "is_alive", True):
            self._emit_environment_contacts(player, world)
            self._highlight_nearby_props(player, world)

        for effect in self.active:
            effect.update(dt)
        self.active = [effect for effect in self.active if effect.alive]

    def draw(self, screen, camera):
        for effect in sorted(self.active, key=lambda item: item.sort_y):
            dest = camera.apply(effect.rect)
            image = effect.image
            if dest.size != image.get_size():
                image = pygame.transform.scale(image, dest.size)
            screen.blit(image, dest)
