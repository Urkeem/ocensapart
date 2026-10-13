"""Atomic crafting/refining mutations driven by data-defined recipes."""

from __future__ import annotations

from dataclasses import dataclass

from data.crafting import recipe_for
from data.equipment import EQUIPMENT_DEFINITIONS
from gameplay.events import ItemCrafted, next_event_id, publish_from
from inventory_item import Item


@dataclass(frozen=True)
class CraftResult:
    success: bool
    message: str
    item_id: str | None = None
    count: int = 0
    unlocked: str | None = None


class CraftingService:
    def __init__(self, inventory, player=None, game_state=None):
        self.inventory = inventory
        self.player = player
        self.game_state = game_state or getattr(player, "game_state", None)

    def available_count(self, item_id, *, include_seed_inventory=True):
        amount = self.inventory.count_item(item_id)
        if (
            include_seed_inventory
            and self.player is not None
            and item_id in self.player.seed_inventory
        ):
            amount += self.player.seed_inventory.get(item_id, 0)
        return amount

    def _consume(self, item_id, amount, *, include_seed_inventory=True):
        inventory_amount = min(amount, self.inventory.count_item(item_id))
        if inventory_amount:
            self.inventory.remove_item_count(item_id, inventory_amount)
        remaining = amount - inventory_amount
        if remaining and include_seed_inventory:
            self.player.seed_inventory[item_id] -= remaining

    def craft(self, category, output_id) -> CraftResult:
        recipe = recipe_for(category, output_id)
        if recipe is None:
            return CraftResult(False, "Unknown recipe.")
        if not recipe.is_unlocked(self.game_state):
            return CraftResult(False, "That recipe is still locked.", output_id)
        include_seed_inventory = recipe.category != "seeds"
        if any(
            self.available_count(
                item_id,
                include_seed_inventory=include_seed_inventory,
            ) < count
            for item_id, count in recipe.ingredients.items()
        ):
            return CraftResult(False, "Required ingredients are missing.", output_id)

        inventory_output = (
            recipe.output_id not in EQUIPMENT_DEFINITIONS
            and recipe.category != "seeds"
        )
        if inventory_output and not self.inventory.can_add_item(recipe.output_id, recipe.output_count):
            return CraftResult(False, "There is no inventory space for the result.", output_id)

        for item_id, count in recipe.ingredients.items():
            self._consume(
                item_id,
                count,
                include_seed_inventory=include_seed_inventory,
            )

        self.inventory.add_crafted_item(recipe.output_id, recipe.output_count)
        if recipe.category == "seeds" and self.player is not None:
            self.player.seed_inventory[recipe.output_id] = self.player.seed_inventory.get(recipe.output_id, 0) + recipe.output_count
        elif recipe.output_id in EQUIPMENT_DEFINITIONS and self.player is not None:
            self.player.restore_tool(recipe.output_id)
        else:
            self.inventory.add_item_to_slot(Item(recipe.output_id), recipe.output_count)

        unlocked = None
        if self.game_state is not None and recipe.grants_unlock:
            if self.game_state.unlock(recipe.grants_unlock):
                unlocked = recipe.grants_unlock
        if self.player is not None:
            publish_from(
                self.player,
                ItemCrafted(
                    event_id=next_event_id(self.player, "item_crafted"),
                    item_id=recipe.output_id,
                    recipe_id=recipe.id,
                    count=recipe.output_count,
                ),
            )
        return CraftResult(
            True,
            f"Crafted {recipe.output_id.replace('_', ' ').title()}.",
            recipe.output_id,
            recipe.output_count,
            unlocked,
        )
