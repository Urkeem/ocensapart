"""Equipment base durability and tier definitions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EquipmentDefinition:
    id: str
    base_max_durability: int
    equipment_type: str


EQUIPMENT_DEFINITIONS = {
    definition.id: definition
    for definition in (
        EquipmentDefinition("hoe", 50, "tool"),
        EquipmentDefinition("axe", 40, "tool"),
        EquipmentDefinition("pickaxe", 45, "tool"),
        EquipmentDefinition("shovel", 45, "tool"),
        EquipmentDefinition("water", 60, "tool"),
        EquipmentDefinition("fishing rod", 40, "tool"),
        EquipmentDefinition("sword", 100, "weapon"),
        EquipmentDefinition("spear", 100, "weapon"),
        EquipmentDefinition("shield", 120, "weapon"),
    )
}

TIER_ORDER = ("basic", "sturdy", "forged", "masterwork")
TIER_DURABILITY_MULTIPLIERS = {
    "basic": 1.0,
    "sturdy": 1.5,
    "forged": 2.0,
    "masterwork": 3.0,
}
UPGRADE_COIN_COSTS = {
    "sturdy": 20,
    "forged": 60,
    "masterwork": 140,
}


def equipment_max_durability(equipment_id: str, tier: str = "basic") -> int:
    definition = EQUIPMENT_DEFINITIONS[equipment_id]
    return round(definition.base_max_durability * TIER_DURABILITY_MULTIPLIERS[tier])


def new_equipment_state(equipment_id: str, *, owned=True) -> dict:
    maximum = equipment_max_durability(equipment_id)
    return {
        "tier": "basic",
        "durability": maximum,
        "max_durability": maximum,
        "broken": False,
        "upgrades_purchased": 0,
        "owned": bool(owned),
    }


def normalize_equipment_state(equipment_id: str, state=None) -> dict:
    state = dict(state or {})
    tier = str(state.get("tier", "basic")).lower()
    if tier not in TIER_ORDER:
        tier = "basic"
    expected_maximum = equipment_max_durability(equipment_id, tier)
    maximum = max(expected_maximum, int(state.get("max_durability", expected_maximum)))
    durability = max(0, min(maximum, int(state.get("durability", maximum))))
    return {
        "tier": tier,
        "durability": durability,
        "max_durability": maximum,
        "broken": bool(state.get("broken", durability <= 0)) or durability <= 0,
        "upgrades_purchased": max(0, int(state.get("upgrades_purchased", TIER_ORDER.index(tier)))),
        "owned": bool(state.get("owned", True)),
    }
