"""Enemy combat definitions layered over the authored asset manifest."""

from __future__ import annotations

from dataclasses import dataclass

from data.content_manifest import ENEMY_ASSETS, EnemyAssetSpec


@dataclass(frozen=True)
class LootDefinition:
    item_id: str
    count: int = 1


@dataclass(frozen=True)
class EnemyDefinition:
    id: str
    display_name: str
    tier: str
    asset: EnemyAssetSpec
    health: int
    speed: float
    attack_profile: str
    attack_damage: int
    attack_range: float
    aggro_radius: float
    attack_cooldown: float
    xp_reward: int
    drops: tuple[LootDefinition, ...]
    faction: str = "invader"
    animation_fps: float = 10.0
    visual_scale: float = 2.0
    projectile_speed: float = 250.0

    @property
    def is_boss(self) -> bool:
        return self.attack_profile == "boss"


_TIER_DEFAULTS = {
    "primary": {"health": 3, "speed": 72, "damage": 1, "xp": 10, "coins": 2},
    "secondary": {"health": 7, "speed": 78, "damage": 2, "xp": 25, "coins": 5},
    "tertiary": {"health": 12, "speed": 84, "damage": 3, "xp": 50, "coins": 10},
}

_RANGED_IDS = {
    "eyeball_monster",
    "goblin_slinger",
    "necromancer",
    "skeleton_hunter",
    "warlock",
}
_BOSS_IDS = {"skeleton_king", "necromancer"}


def _definition(enemy_id: str, asset: EnemyAssetSpec) -> EnemyDefinition:
    defaults = _TIER_DEFAULTS[asset.tier]
    profile = "boss" if enemy_id in _BOSS_IDS else "ranged" if enemy_id in _RANGED_IDS else "melee"
    if enemy_id == "cultist":
        profile = "caster"
    is_boss = profile == "boss"
    if is_boss:
        item_drop = LootDefinition("diamond_ore")
    elif asset.tier == "tertiary":
        item_drop = LootDefinition("stamina_potion", 2)
    elif asset.tier == "secondary":
        item_drop = LootDefinition("stamina_potion")
    else:
        item_drop = LootDefinition("iron_ore")
    return EnemyDefinition(
        id=enemy_id,
        display_name=enemy_id.replace("_", " ").title(),
        tier="boss" if is_boss else asset.tier,
        asset=asset,
        health=max(18, defaults["health"] * 3) if is_boss else defaults["health"],
        speed=defaults["speed"] * (0.9 if is_boss else 1.0),
        attack_profile=profile,
        attack_damage=defaults["damage"] + (1 if is_boss else 0),
        attack_range=82 if profile in {"melee", "boss"} else 290,
        aggro_radius=520 if is_boss else 390,
        attack_cooldown=1.4 if is_boss else 1.7 if profile in {"ranged", "caster"} else 1.15,
        xp_reward=100 if is_boss else defaults["xp"],
        drops=(
            LootDefinition("coin", max(25, defaults["coins"] * 4) if is_boss else defaults["coins"]),
            item_drop,
        ),
        animation_fps=9 if is_boss else 11,
        projectile_speed=285 if asset.tier != "primary" else 245,
    )


ENEMY_DEFINITIONS = {
    enemy_id: _definition(enemy_id, asset)
    for enemy_id, asset in ENEMY_ASSETS.items()
}


def enemy_definition(enemy_id: str) -> EnemyDefinition:
    try:
        return ENEMY_DEFINITIONS[str(enemy_id)]
    except KeyError as error:
        raise KeyError(f"Unknown enemy {enemy_id!r}") from error
