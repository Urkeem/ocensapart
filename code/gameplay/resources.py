"""Deterministic ore selection for procedural resource placement."""

from __future__ import annotations

from hashlib import blake2b


ORE_SPAWN_CHANCE = {
    "grassland_and_forest": 0.006,
    "dryland": 0.035,
    "desert": 0.025,
    "mountain": 0.075,
}

COMMON_ORE_WEIGHTS = (
    ("coal_ore", 48),
    ("iron_ore", 38),
    ("gold_ore", 8),
    ("ruby_ore", 3),
    ("diamond_ore", 2),
    ("blue_sapphire_ore", 1),
)


def _stable_fraction(*parts) -> float:
    payload = "|".join(map(str, parts)).encode("utf-8")
    value = int.from_bytes(blake2b(payload, digest_size=8).digest(), "big")
    return value / ((1 << 64) - 1)


def deterministic_ore_id(world_seed, world_tile, biome_name, danger=1) -> str | None:
    """Return a stable raw-ore ID for a tile, with rare ores favoring danger."""
    chance = ORE_SPAWN_CHANCE.get(str(biome_name), 0.0)
    danger = max(1, int(danger))
    chance = min(0.18, chance * (1.0 + (danger - 1) * 0.12))
    if _stable_fraction(world_seed, world_tile, biome_name, "ore-spawn") >= chance:
        return None

    weighted = []
    for ore_id, weight in COMMON_ORE_WEIGHTS:
        if ore_id not in {"coal_ore", "iron_ore"}:
            weight += max(0, danger - 1)
        weighted.append((ore_id, weight))
    total = sum(weight for _, weight in weighted)
    roll = _stable_fraction(world_seed, world_tile, biome_name, "ore-kind") * total
    for ore_id, weight in weighted:
        roll -= weight
        if roll < 0:
            return ore_id
    return weighted[-1][0]
