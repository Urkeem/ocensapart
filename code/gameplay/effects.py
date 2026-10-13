"""Reusable world-space combat FX and environmental particle emitters."""

from __future__ import annotations

from dataclasses import dataclass
import random

import pygame

from utils import rp
from data.content_manifest import EFFECT_ASSETS


@dataclass(frozen=True)
class EffectSpec:
    paths: tuple[tuple[str, ...], ...]
    frame_count: int
    fps: float
    scale: float = 1.0
    frame_size: tuple[int, int] | None = None
    columns: int | None = None


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
    "fire": EffectSpec(
        (("graphics", "effects", "fire", "fire.png"),),
        EFFECT_ASSETS["fire"].frame_count,
        18,
        1.0,
        EFFECT_ASSETS["fire"].frame_size,
        EFFECT_ASSETS["fire"].columns,
    ),
    "points_reward": EffectSpec(
        (("graphics", "sprites", "items", "star.png"),),
        EFFECT_ASSETS["points_reward"].frame_count,
        18,
        2.0,
    ),
    "gem": _fx("gem", ("gem_01.png", "gem_02.png", "gem_03.png"), 24, 28),
    "impact": _fx("impact", ("impact.png",), 16, 30),
    "damage_word": EffectSpec(
        tuple(("graphics", "effects", "word", name) for name in ("bam.png", "bang.png", "pow.png")),
        1,
        1,
        2.0,
    ),
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
        if spec.frame_size is not None:
            frame_width, frame_height = spec.frame_size
            columns = spec.columns or max(1, sheet.get_width() // frame_width)
            rects = tuple(
                pygame.Rect(
                    (frame_index % columns) * frame_width,
                    (frame_index // columns) * frame_height,
                    frame_width,
                    frame_height,
                )
                for frame_index in range(spec.frame_count)
            )
            if any(not sheet.get_rect().contains(rect) for rect in rects):
                raise ValueError(
                    f"Effect sheet {path!r} cannot hold {spec.frame_count} "
                    f"{frame_width}x{frame_height} row-major frames"
                )
        elif sheet.get_width() % spec.frame_count:
            raise ValueError(
                f"Effect sheet {path!r} cannot be split into "
                f"{spec.frame_count} equal horizontal frames"
            )
        else:
            frame_width = sheet.get_width() // spec.frame_count
            frame_height = sheet.get_height()
            rects = tuple(
                pygame.Rect(frame_index * frame_width, 0, frame_width, frame_height)
                for frame_index in range(spec.frame_count)
            )
        frames = []
        for rect in rects:
            frame = sheet.subsurface(rect).copy()
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


class FloatingText:
    """World-space text that rises and fades after a combat event."""

    def __init__(self, text, pos, *, color=(255, 92, 92), lifetime=0.9, velocity=(0, -48)):
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(velocity)
        self.lifetime = max(0.05, float(lifetime))
        self.age = 0.0
        self.alive = True
        font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 26)
        foreground = font.render(str(text), True, color)
        outline = font.render(str(text), True, (38, 8, 12))
        self.base_image = pygame.Surface(
            (foreground.get_width() + 4, foreground.get_height() + 4),
            pygame.SRCALPHA,
        )
        for offset in ((0, 2), (4, 2), (2, 0), (2, 4)):
            self.base_image.blit(outline, outline.get_rect(center=(self.base_image.get_width() // 2 + offset[0] - 2, self.base_image.get_height() // 2 + offset[1] - 2)))
        self.base_image.blit(foreground, foreground.get_rect(center=self.base_image.get_rect().center))
        self.image = self.base_image
        self.rect = self.image.get_rect(center=pos)

    @property
    def sort_y(self):
        return self.rect.centery

    def update(self, dt):
        self.age += max(0.0, float(dt))
        self.pos += self.velocity * max(0.0, float(dt))
        if self.age >= self.lifetime:
            self.alive = False
            return
        self.image = self.base_image.copy()
        fade_start = self.lifetime * 0.45
        if self.age > fade_start:
            alpha = round(255 * (1.0 - (self.age - fade_start) / (self.lifetime - fade_start)))
            self.image.set_alpha(max(0, alpha))
        self.rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))


class FloatingItemGain(FloatingText):
    """A harvested-item icon and quantity that rise together in world space."""

    def __init__(self, item_name, amount, pos, *, lifetime=1.05, velocity=(0, -48)):
        from ui.inventory import load_item_icon

        super().__init__(f"+{int(amount)}", pos, color=(248, 238, 174), lifetime=lifetime, velocity=velocity)
        text_image = self.base_image
        icon = load_item_icon(item_name, (30, 30))
        if not isinstance(icon, pygame.Surface):
            return
        combined = pygame.Surface(
            (icon.get_width() + 5 + text_image.get_width(), max(icon.get_height(), text_image.get_height())),
            pygame.SRCALPHA,
        )
        combined.blit(icon, icon.get_rect(midleft=(0, combined.get_height() // 2)))
        combined.blit(text_image, text_image.get_rect(midright=(combined.get_width(), combined.get_height() // 2)))
        self.base_image = combined
        self.image = combined
        self.rect = combined.get_rect(center=pos)


class EffectsManager:
    """Own transient animations and low-frequency world interaction emitters."""

    SPARK_PROP_TYPES = frozenset({"chest", "treasure", "crate", "barrel", "clue"})
    CONTACT_EFFECTS = {
        "bush": "bush",
        "hay": "hay",
        "weed": "grass",
    }

    def __init__(self, library=None, rng=None, *, reduced_motion=False):
        self.library = library or EffectLibrary()
        self.rng = rng or random.Random()
        self.reduced_motion = bool(reduced_motion)
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

    def floating_text(self, text, pos, *, color=(255, 92, 92), lifetime=0.9):
        effect = FloatingText(
            text,
            pos,
            color=color,
            lifetime=lifetime,
            velocity=(0, -18 if self.reduced_motion else -48),
        )
        self.active.append(effect)
        return effect

    def item_gain(self, item_name, amount, pos):
        effect = FloatingItemGain(
            item_name,
            amount,
            pos,
            velocity=(0, -18 if self.reduced_motion else -48),
        )
        self.active.append(effect)
        return effect

    def burst(self, effect_name, pos, *, count=5, speed=(28, 68)):
        """Scatter the same fading particles used by environmental contact FX."""
        spawned = []
        for _ in range(max(1, int(count))):
            direction = pygame.Vector2(1, 0).rotate(self.rng.uniform(0, 360))
            origin = pygame.Vector2(pos) + direction * self.rng.uniform(2, 9)
            spawned.append(
                self.spawn(
                    effect_name,
                    origin,
                    velocity=direction * self.rng.uniform(*speed),
                    loop=True,
                    lifetime=self.rng.uniform(0.65, 1.0),
                    fade=True,
                )
            )
        return tuple(spawned)

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

        if player is not None and getattr(player, "is_alive", True) and not self.reduced_motion:
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
