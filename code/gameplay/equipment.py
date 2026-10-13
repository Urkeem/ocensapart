"""Equipment upgrades and tier-preserving repair support."""

from __future__ import annotations

from dataclasses import dataclass

from data.equipment import (
    EQUIPMENT_DEFINITIONS,
    TIER_ORDER,
    UPGRADE_COIN_COSTS,
    equipment_max_durability,
)
from gameplay.events import EquipmentUpgraded, next_event_id, publish_from


@dataclass(frozen=True)
class EquipmentServiceResult:
    success: bool
    message: str
    equipment_id: str | None = None
    old_tier: str | None = None
    new_tier: str | None = None
    cost: int = 0


class EquipmentService:
    """Jim's coin-based durability upgrades, backed by player equipment state."""

    def __init__(self, player, game_state):
        self.player = player
        self.game_state = game_state

    def _record(self, equipment_id):
        return getattr(self.player, "equipment_state", {}).get(equipment_id)

    def next_tier(self, equipment_id):
        record = self._record(equipment_id)
        if record is None or not record.get("owned", False):
            return None
        index = TIER_ORDER.index(record.get("tier", "basic"))
        return TIER_ORDER[index + 1] if index + 1 < len(TIER_ORDER) else None

    def quote(self, equipment_id):
        new_tier = self.next_tier(equipment_id)
        if new_tier is None:
            return None
        return UPGRADE_COIN_COSTS[new_tier]

    def upgrade(self, equipment_id) -> EquipmentServiceResult:
        equipment_id = str(equipment_id or "").strip().lower().replace("_", " ")
        record = self._record(equipment_id)
        if equipment_id not in EQUIPMENT_DEFINITIONS or record is None or not record.get("owned", False):
            return EquipmentServiceResult(False, "That equipment is not owned.", equipment_id)
        if not self.game_state.flag("services.jim_upgrades", False):
            return EquipmentServiceResult(False, "Jim's upgrade service is still locked.", equipment_id)

        old_tier = record.get("tier", "basic")
        new_tier = self.next_tier(equipment_id)
        if new_tier is None:
            return EquipmentServiceResult(False, "This item is already Masterwork.", equipment_id)
        cost = UPGRADE_COIN_COSTS[new_tier]
        if not self.player.spend_coins(cost):
            return EquipmentServiceResult(False, f"The upgrade costs {cost} coins.", equipment_id, old_tier, new_tier, cost)

        record["tier"] = new_tier
        record["max_durability"] = equipment_max_durability(equipment_id, new_tier)
        record["durability"] = record["max_durability"]
        record["broken"] = False
        record["upgrades_purchased"] = int(record.get("upgrades_purchased", 0)) + 1
        self.player.sync_equipment_compatibility()
        publish_from(
            self.player,
            EquipmentUpgraded(
                event_id=next_event_id(self.player, "equipment_upgraded"),
                equipment_id=equipment_id,
                old_tier=old_tier,
                new_tier=new_tier,
            ),
        )
        return EquipmentServiceResult(
            True,
            f"{equipment_id.title()} upgraded to {new_tier.title()}.",
            equipment_id,
            old_tier,
            new_tier,
            cost,
        )
