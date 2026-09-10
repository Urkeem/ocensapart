"""Animated farm animals that wander and feed inside generated paddocks."""

from __future__ import annotations

import random

import pygame

from sprites import AnimatedWorldObject
from utils import rp


ANIMAL_DIRECTIONS = ("down", "up", "right", "left")
ANIMAL_SPECS = {
    "cow": {
        "walk_frames": 6,
        "feed_frames": 5,
        "speed": 28.0,
        "walk_animation_speed": 4.0,
        "feed_animation_speed": 4.0,
    },
    "chicken": {
        "walk_frames": 6,
        "feed_frames": 3,
        "speed": 88.0,
        "walk_animation_speed": 12.0,
        "feed_animation_speed": 8.0,
    },
    "pig": {
        "walk_frames": 6,
        "feed_frames": 2,
        "speed": 32.0,
        "walk_animation_speed": 4.0,
        "feed_animation_speed": 4.0,
    },
}
ANIMAL_FRAME_SIZE = 64
_ANIMAL_FRAME_CACHE: dict[tuple[str, str, str], tuple[pygame.Surface, ...]] = {}
_SCALED_ANIMAL_FRAME_CACHE: dict[
    tuple[str, str, str, float],
    tuple[pygame.Surface, ...],
] = {}


def get_animal_frames(species: str, variant: str | int, animation: str) -> tuple[pygame.Surface, ...]:
    """Slice one directional walk/feed row from an animal sheet."""
    species = str(species).lower()
    variant = str(variant)
    spec = ANIMAL_SPECS.get(species)
    if spec is None:
        raise ValueError(f"Unknown farm animal species: {species}")
    cache_key = (species, variant, animation)
    cached = _ANIMAL_FRAME_CACHE.get(cache_key)
    if cached is not None:
        return cached

    try:
        action, direction = animation.split("_", 1)
        direction_row = ANIMAL_DIRECTIONS.index(direction)
    except (ValueError, AttributeError) as error:
        raise ValueError(f"Unknown animal animation: {animation}") from error
    if action not in {"walk", "feed"}:
        raise ValueError(f"Unknown animal action: {action}")

    frame_count = int(spec[f"{action}_frames"])
    row = direction_row + (4 if action == "feed" else 0)
    sheet = pygame.image.load(
        rp("graphics", "sprites", "animals", species, f"{variant}.png")
    ).convert_alpha()
    required_size = (frame_count * ANIMAL_FRAME_SIZE, (row + 1) * ANIMAL_FRAME_SIZE)
    if sheet.get_width() < required_size[0] or sheet.get_height() < required_size[1]:
        raise ValueError(
            f"Animal sheet {species}/{variant}.png is too small for {animation}: "
            f"expected at least {required_size}, got {sheet.get_size()}"
        )

    frames = tuple(
        sheet.subsurface(
            pygame.Rect(
                frame_index * ANIMAL_FRAME_SIZE,
                row * ANIMAL_FRAME_SIZE,
                ANIMAL_FRAME_SIZE,
                ANIMAL_FRAME_SIZE,
            )
        ).copy()
        for frame_index in range(frame_count)
    )
    _ANIMAL_FRAME_CACHE[cache_key] = frames
    return frames


class FarmAnimal(AnimatedWorldObject):
    """A lightweight actor constrained to the grass inside one animal pen."""

    def __init__(self, record: dict, tile_size: int):
        self.record = record
        self.species = str(record["species"]).lower()
        self.variant = str(record.get("variant", "1"))
        self.tile_size = int(tile_size)
        self.visual_scale = float(record.get("scale", 2.0))
        self.home_rect = tuple(map(int, record["home_world_rect"]))
        self.rng = random.Random(record.get("behavior_seed", record.get("id")))
        self.facing = self.rng.choice(ANIMAL_DIRECTIONS)
        self.action = "feed"
        self.status = f"feed_{self.facing}"
        self.pos = pygame.Vector2(record["world_pos"])
        self.target_pos: pygame.Vector2 | None = None
        self.state_timer = self.rng.uniform(1.4, 3.8)
        self.speed = float(ANIMAL_SPECS[self.species]["speed"])

        super().__init__(
            pos=self.pos,
            frames=self._get_scaled_frames(self.status),
            anchor="midbottom",
            animation_speed=self._animation_speed("feed"),
            loop=True,
        )
        self.name = self.species
        self.collision_box = self.rect.copy().inflate(
            -int(self.rect.width * 0.55),
            -int(self.rect.height * 0.65),
        )

    def _get_scaled_frames(self, animation: str) -> tuple[pygame.Surface, ...]:
        cache_key = (
            self.species,
            self.variant,
            animation,
            self.visual_scale,
        )
        cached = _SCALED_ANIMAL_FRAME_CACHE.get(cache_key)
        if cached is not None:
            return cached

        frames = get_animal_frames(self.species, self.variant, animation)
        if self.visual_scale == 1:
            scaled = frames
        else:
            frame_size = max(1, round(ANIMAL_FRAME_SIZE * self.visual_scale))
            scaled = tuple(
                pygame.transform.scale(frame, (frame_size, frame_size))
                for frame in frames
            )
        _SCALED_ANIMAL_FRAME_CACHE[cache_key] = scaled
        return scaled

    def _animation_speed(self, action: str) -> float:
        return float(ANIMAL_SPECS[self.species][f"{action}_animation_speed"])

    def _set_animation(self, action: str, facing: str | None = None) -> None:
        if facing is not None:
            self.facing = facing
        status = f"{action}_{self.facing}"
        if status == self.status:
            return
        anchor = self.rect.midbottom
        self.action = action
        self.status = status
        self.animation_speed = self._animation_speed(action)
        self.frames = list(self._get_scaled_frames(status))
        self.index = 0
        self.image_base = self.frames[0]
        self.image = self.image_base.copy()
        self.rect = self.image.get_rect(midbottom=anchor)
        self.mask = pygame.mask.from_surface(self.image_base)
        self.collision_box = self.rect.copy().inflate(
            -int(self.rect.width * 0.55),
            -int(self.rect.height * 0.65),
        )

    def _tile_position(self, world_tile: tuple[int, int]) -> pygame.Vector2:
        tile_x, tile_y = world_tile
        return pygame.Vector2(
            tile_x * self.tile_size + self.tile_size // 2,
            (tile_y + 1) * self.tile_size,
        )

    def _home_tiles(self) -> tuple[tuple[int, int], ...]:
        left, top, width, height = self.home_rect
        return tuple(
            (tile_x, tile_y)
            for tile_y in range(top, top + height)
            for tile_x in range(left, left + width)
        )

    def begin_walking(self) -> None:
        choices = list(self._home_tiles())
        self.rng.shuffle(choices)
        for tile in choices:
            target = self._tile_position(tile)
            if target.distance_squared_to(self.pos) < 4:
                continue
            self.target_pos = target
            delta = target - self.pos
            if abs(delta.x) > abs(delta.y):
                facing = "right" if delta.x > 0 else "left"
            else:
                facing = "down" if delta.y > 0 else "up"
            self._set_animation("walk", facing)
            return
        self.begin_feeding()

    def begin_feeding(self) -> None:
        self.target_pos = None
        self.state_timer = self.rng.uniform(1.6, 4.2)
        self._set_animation("feed")

    def _move(self, dt: float) -> None:
        if self.target_pos is None:
            return
        delta = self.target_pos - self.pos
        step = self.speed * dt
        if delta.length() <= max(1.0, step):
            self.pos.update(self.target_pos)
            self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
            self.collision_box.center = self.rect.center
            self.begin_feeding()
            return
        self.pos += delta.normalize() * step
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.collision_box.center = self.rect.center

    def update(self, dt: float) -> None:
        if self.action == "feed":
            self.state_timer -= dt
            if self.state_timer <= 0:
                self.begin_walking()
        else:
            self._move(dt)
        self.animate(dt)
        self.tick_opacity(dt)
