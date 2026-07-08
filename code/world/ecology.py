"""Biome-specific rules for tree species, density, and spawn conditions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple
import random


@dataclass(frozen=True)
class TreeRule:
    name: str
    weight: float = 1.0
    moisture_range: tuple[float, float] = (0.0, 1.0)
    elevation_range: tuple[float, float] = (0.0, 1.0)
    temperature_range: tuple[float, float] = (0.0, 1.0)
    min_spacing: int = 2
    base_chance: float = 0.1
    can_spawn_near_water: bool = True
    blocks_movement: bool = True
    spawn_on_tiles: tuple[str, ...] = ("grass", "dirt")
    size_range: tuple[float, float] = (0.9, 1.1)
    health: int = 5


@dataclass(frozen=True)
class BiomeEcology:
    biome_name: str
    tree_density: float = 0.2
    allow_trees: bool = True
    tree_rules: tuple[TreeRule, ...] = field(default_factory=tuple)


# BIOME_ECOLOGY: dict[str, BiomeEcology] = {}


OAK = TreeRule(
    name="oak",
    weight=4.0,
    moisture_range=(0.35, 0.85),
    elevation_range=(0.0, 0.75),
    temperature_range=(0.35, 0.8),
    min_spacing=2,
    base_chance=0.6,
    can_spawn_near_water=False,
    spawn_on_tiles=("grass", "dirt", "sand"),
    size_range=(0.95, 1.20),
)

PINE = TreeRule(
    name="pine",
    weight=3.0,
    moisture_range=(0.25, 0.75),
    elevation_range=(0.2, 1.0),
    temperature_range=(0.15, 0.65),
    min_spacing=2,
    base_chance=0.6,
    can_spawn_near_water=False,
    spawn_on_tiles=("grass", "dirt", "rocky", "sand"),
    size_range=(0.9, 1.25),
)

PALM = TreeRule(
    name="palm",
    weight=3.0,
    moisture_range=(0.45, 1.0),
    elevation_range=(0.0, 0.35),
    temperature_range=(0.7, 1.0),
    min_spacing=3,
    base_chance=0.6,
    can_spawn_near_water=True,
    spawn_on_tiles=("sand", "grass"),
    size_range=(0.9, 1.15),
)

MANGROVE = TreeRule(
    name="mangrove",
    weight=2.5,
    moisture_range=(0.75, 1.0),
    elevation_range=(0.0, 0.25),
    temperature_range=(0.65, 1.0),
    min_spacing=2,
    base_chance=0.16,
    can_spawn_near_water=True,
    spawn_on_tiles=("mud", "swamp", "grass"),
    size_range=(0.85, 1.10),
)

DEAD_TREE = TreeRule(
    name="dead_tree",
    weight=1.5,
    moisture_range=(0.1, 0.5),
    elevation_range=(0.0, 0.8),
    temperature_range=(0.4, 1.0),
    min_spacing=3,
    base_chance=0.08,
    can_spawn_near_water=False,
    spawn_on_tiles=("dirt", "dry_grass"),
    size_range=(0.9, 1.2),
)

BIRCH = TreeRule(
    name="birch",
    weight=2.0,
    moisture_range=(0.4, 0.85),
    elevation_range=(0.0, 0.7),
    temperature_range=(0.3, 0.75),
    min_spacing=2,
    base_chance=0.6,
    can_spawn_near_water=False,
    spawn_on_tiles=("grass", "dirt", "sand"),
    size_range=(0.95, 1.15),
)

APPLE = TreeRule(
    name="apple",
    weight=2.0,
    moisture_range=(0.4, 0.85),
    elevation_range=(0.0, 0.7),
    temperature_range=(0.3, 0.75),
    min_spacing=2,
    base_chance=0.6,
    can_spawn_near_water=False,
    spawn_on_tiles=("grass", "dirt", "sand"),
    size_range=(0.95, 1.15),
)

PEACH = TreeRule(
    name="peach",
    weight=2.0,
    moisture_range=(0.4, 0.85),
    elevation_range=(0.0, 0.7),
    temperature_range=(0.3, 0.75),
    min_spacing=2,
    base_chance=0.6,
    can_spawn_near_water=False,
    spawn_on_tiles=("grass", "dirt", "sand"),
    size_range=(0.95, 1.15),
)

CHERRY = TreeRule(
    name="cherry",
    weight=2.0,
    moisture_range=(0.4, 0.85),
    elevation_range=(0.0, 0.7),
    temperature_range=(0.3, 0.75),
    min_spacing=2,
    base_chance=0.6,
    can_spawn_near_water=False,
    spawn_on_tiles=("grass", "dirt", "sand"),
    size_range=(0.95, 1.15),
)


BIOME_ECOLOGY: Dict[str, BiomeEcology] = {
    "forest": BiomeEcology("forest", tree_density=0.72, allow_trees=True, tree_rules=(OAK, PINE, BIRCH, PEACH, APPLE, CHERRY)),
    "grassland": BiomeEcology("plains", tree_density=0.60, allow_trees=True, tree_rules=(OAK, BIRCH, APPLE, PEACH, APPLE, CHERRY)),
    "swamp": BiomeEcology("swamp", tree_density=0.28, allow_trees=True, tree_rules=(MANGROVE, DEAD_TREE)),
    "coast": BiomeEcology("coast", tree_density=0.46, allow_trees=True, tree_rules=(PALM, DEAD_TREE)),
    "beach": BiomeEcology("coast", tree_density=0.46, allow_trees=True, tree_rules=(PALM, DEAD_TREE)),
    "jungle": BiomeEcology("jungle", tree_density=0.56, allow_trees=True, tree_rules=(PALM, MANGROVE, OAK, BIRCH)),
    "mountain": BiomeEcology("mountain", tree_density=0.30, allow_trees=True, tree_rules=(PINE,BIRCH, OAK, CHERRY)),
    "highlands": BiomeEcology("mountain", tree_density=0.38, allow_trees=True, tree_rules=(PINE, APPLE, BIRCH)),
    "desert": BiomeEcology("desert", tree_density=0.10, allow_trees=True, tree_rules=(DEAD_TREE, PALM, BIRCH)),
    "dryland": BiomeEcology("desert", tree_density=0.56, allow_trees=True, tree_rules=(DEAD_TREE, PALM)),
    "deep_ocean": BiomeEcology("deep_ocean", tree_density=0.0, allow_trees=False, tree_rules=()),
    "shallow_ocean": BiomeEcology("shallow_ocean", tree_density=0.0, allow_trees=False, tree_rules=()),
}


def get_biome_ecology(biome_name: str) -> Optional[BiomeEcology]:
    return BIOME_ECOLOGY.get(biome_name)


def value_in_range(value: float, value_range: Tuple[float, float]) -> bool:
    return value_range[0] <= value <= value_range[1]


def tree_matches_environment(
    tree_rule: TreeRule,
    moisture: float,
    elevation: float,
    temperature: float,
    tile_type: str,
    near_water: bool,
) -> bool:
    return (
        value_in_range(moisture, tree_rule.moisture_range)
        and value_in_range(elevation, tree_rule.elevation_range)
        and value_in_range(temperature, tree_rule.temperature_range)
        and tile_type in tree_rule.spawn_on_tiles
        and (tree_rule.can_spawn_near_water or not near_water)
    )


def choose_tree_rule(
    biome_name: str,
    moisture: float,
    elevation: float,
    temperature: float,
    tile_type: str,
    near_water: bool,
    rng: random.Random,
) -> Optional[TreeRule]:
    biome = get_biome_ecology(biome_name)
    if biome is None or not biome.allow_trees or not biome.tree_rules:
        return None

    weights = []
    for rule in biome.tree_rules:
        weight = rule.weight
        if not value_in_range(moisture, rule.moisture_range):
            weight *= 0.35
        if not value_in_range(elevation, rule.elevation_range):
            weight *= 0.35
        if not value_in_range(temperature, rule.temperature_range):
            weight *= 0.35
        if tile_type not in rule.spawn_on_tiles:
            weight *= 0.35
        if near_water and not rule.can_spawn_near_water:
            weight *= 0.35
        weights.append(weight)

    return rng.choices(biome.tree_rules, weights=weights, k=1)[0]


def should_spawn_tree(
    biome_name: str,
    fertility: float,
    density_noise: float,
    rng: random.Random,
) -> bool:
    biome = get_biome_ecology(biome_name)
    if biome is None or not biome.allow_trees:
        return False

    spawn_score = biome.tree_density
    spawn_score *= 0.6 + 0.4 * fertility
    spawn_score *= 0.5 + 0.5 * density_noise
    return rng.random() < spawn_score


def generate_tree_instance(
    biome_name: str,
    moisture: float,
    elevation: float,
    temperature: float,
    fertility: float,
    density_noise: float,
    tile_type: str,
    near_water: bool,
    rng: random.Random,
) -> Optional[dict]:
    if not should_spawn_tree(
        biome_name=biome_name,
        fertility=fertility,
        density_noise=density_noise,
        rng=rng,
    ):
        return None

    rule = choose_tree_rule(
        biome_name=biome_name,
        moisture=moisture,
        elevation=elevation,
        temperature=temperature,
        tile_type=tile_type,
        near_water=near_water,
        rng=rng,
    )
    if rule is None:
        return None

    if rng.random() > rule.base_chance:
        return None

    return {
        "type": "tree",
        "species": rule.name,
        "size": rng.uniform(*rule.size_range),
        "min_spacing": rule.min_spacing,
        "blocks_movement": rule.blocks_movement,
        "health": rule.health,
    }
