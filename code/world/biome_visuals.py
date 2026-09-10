"""Deterministic visual subdivisions shared by terrain and ecology systems."""

from __future__ import annotations

import math


SUBDIVIDED_GRASS_BIOMES = frozenset({3})
SUBDIVIDED_GRASS_TILESET = "Tilesets/grass.png"
SUBDIVIDED_GRASS_CACHE_KEY = "subdivided_grass"

# Two low-frequency value-noise fields produce small, soft-edged patches while
# remaining stable in world space and therefore seamless across chunk borders.
_PRIMARY_PATCH_SCALE = 7
_DETAIL_PATCH_SCALE = 4


def _hash_unit(world_seed: int, grid_x: int, grid_y: int, salt: int) -> float:
    value = (
        int(world_seed) * 0x9E3779B1
        + int(grid_x) * 0x85EBCA77
        + int(grid_y) * 0xC2B2AE3D
        + int(salt) * 0x27D4EB2F
    ) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    value ^= value >> 16
    return value / 0xFFFFFFFF


def _smoothstep(value: float) -> float:
    return value * value * (3.0 - 2.0 * value)


def _value_noise(world_seed: int, world_x: int, world_y: int, scale: int, salt: int) -> float:
    grid_x = math.floor(world_x / scale)
    grid_y = math.floor(world_y / scale)
    offset_x = _smoothstep((world_x - grid_x * scale) / scale)
    offset_y = _smoothstep((world_y - grid_y * scale) / scale)

    top_left = _hash_unit(world_seed, grid_x, grid_y, salt)
    top_right = _hash_unit(world_seed, grid_x + 1, grid_y, salt)
    bottom_left = _hash_unit(world_seed, grid_x, grid_y + 1, salt)
    bottom_right = _hash_unit(world_seed, grid_x + 1, grid_y + 1, salt)
    top = top_left + (top_right - top_left) * offset_x
    bottom = bottom_left + (bottom_right - bottom_left) * offset_x
    return top + (bottom - top) * offset_y


def is_subdivided_grass_biome(biome_id: object) -> bool:
    return biome_id in SUBDIVIDED_GRASS_BIOMES


def is_grass_patch_tile(
    world_seed: int,
    world_x: int,
    world_y: int,
    biome_id: object,
) -> bool:
    """Return whether a merged grassland/forest tile belongs to a grass patch."""
    if not is_subdivided_grass_biome(biome_id):
        return False

    primary = _value_noise(
        world_seed,
        world_x,
        world_y,
        _PRIMARY_PATCH_SCALE,
        31,
    )
    detail = _value_noise(
        world_seed,
        world_x,
        world_y,
        _DETAIL_PATCH_SCALE,
        73,
    )
    return primary * 0.72 + detail * 0.28 >= 0.48


def is_weed_patch_tile(
    world_seed: int,
    world_x: int,
    world_y: int,
    biome_id: object,
) -> bool:
    """Return whether a subdivided biome tile is reserved for weeds."""
    return is_subdivided_grass_biome(biome_id) and not is_grass_patch_tile(
        world_seed,
        world_x,
        world_y,
        biome_id,
    )
