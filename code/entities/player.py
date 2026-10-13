"""Player movement, tools, seed planting, pickups, and collision behavior."""

import random
import pygame
from gameplay.controls import (
    BUTTON_CANCEL,
    BUTTON_SEED_NEXT,
    BUTTON_TOOL,
    BUTTON_TOOL_NEXT,
    get_controller_input,
)
from gameplay.config import PLAYER_MAX_HEALTH
from ui.inventory import Inventory, canonical_item_name
from inventory_item import Item
from gameplay.world_objects import (
    can_place_environment_prop_at,
    remove_environment_prop_at,
    set_environment_prop_at,
)
from gameplay.fishing import choose_fish, fishing_block_reason, load_fish_icon
from data.crops import CROP_DEFINITIONS, is_crop_unlocked
from gameplay.stamina import ACTION_STAMINA_COSTS
from data.equipment import (
    EQUIPMENT_DEFINITIONS,
    new_equipment_state,
    normalize_equipment_state,
)
from sprites import AnimatedWorldObject
from swimming import SwimVisual
from world.fence import FENCE_SEGMENT, can_place_fence_at, set_fence_at


FISHING_ANIMATION_SPEED = 6.0
FISHING_STATE_DURATIONS = {
    "initial_cast": 1 / FISHING_ANIMATION_SPEED,
    "cast": 3 / FISHING_ANIMATION_SPEED,
    "reel_in": 2 / FISHING_ANIMATION_SPEED,
    "reel": 4 / FISHING_ANIMATION_SPEED,
}

COMBAT_TOOLS = {"sword", "spear", "shield"}


class Player(AnimatedWorldObject):
    def __init__(
        self,
        pos,
        assets,
        initial_status="down_idle",
        speed=100,
        size=None,
        visual_scale=1,
        soil_layer=None,
        customization=None,
        controller_input=None,
    ):
        self.assets = assets
        self.customization = self.assets.normalize_character_customization(customization)
        self.status = initial_status
        self.last_status = self.status
        self.direction = pygame.Vector2()
        self.pos = pygame.Vector2(pos)
        self.speed = speed
        self.base_speed = speed
        self.is_sprinting = False
        self.recovery_active = False
        self.stamina_enabled = False
        self.location_tools_enabled = True
        self.mounted_vessel = None
        self.hidden_by_vessel = False
        self.visual_scale = visual_scale
        self.soil_layer = soil_layer
        self.controller_input = controller_input or get_controller_input()
        self.tools = [
            equipment_id
            for equipment_id, definition in EQUIPMENT_DEFINITIONS.items()
            if definition.equipment_type == "tool"
        ]
        self.weapons = [
            equipment_id
            for equipment_id, definition in EQUIPMENT_DEFINITIONS.items()
            if definition.equipment_type == "weapon"
        ]
        self.equipment_state = {
            equipment_id: new_equipment_state(equipment_id)
            for equipment_id in EQUIPMENT_DEFINITIONS
        }
        self.sync_equipment_compatibility()
        self.water_capacity = 8
        self.water_amount = self.water_capacity
        self.tool_index = 0
        self.selected_tool = self.tools[self.tool_index]
        self.weapon_index = 0
        self.selected_weapon = self.weapons[self.weapon_index]
        self.selection_slots = ("seed", "tool", "weapon")
        self.selection_slot_index = 1
        self.selected_selection_slot = self.selection_slots[self.selection_slot_index]
        self._sync_equipped_weapon(refresh=False)
        crop_names = tuple(CROP_DEFINITIONS)
        self.seeds = list(crop_names or ("corn", "tomato"))
        self.seed_index = 0
        self.selected_seed = "corn" if "corn" in self.seeds else self.seeds[self.seed_index]
        self.seed_index = self.seeds.index(self.selected_seed)
        self.seed_inventory = {crop_name: 0 for crop_name in self.seeds}
        for starter_seed in ("corn", "tomato"):
            if starter_seed in self.seed_inventory:
                self.seed_inventory[starter_seed] = 5
        self.harvested_crops = {crop_name: 0 for crop_name in self.seeds}
        self.inventory = Inventory(20)
        self.selected_consumable = None
        self.hotbar_slot_index = 0
        self._consume_button_lock = False
        self.coins = 25
        self.dialogue_active = False
        self.journal_active = False
        self.max_health = PLAYER_MAX_HEALTH
        self.health = self.max_health
        self.invulnerable_timer = 0.0
        self.invulnerable_duration = 0.75
        self.knockback_velocity = pygame.Vector2()
        self.knockback_timer = 0.0
        self.knockback_duration = 0.18
        self.effect_manager = None
        self.combat_action = None
        self.combat_action_timer = 0.0
        self.half_health_effect_shown = False
        self.death_effect_shown = False
        self.facing = "down"
        self.action_timer = 0.0
        self.action_lock_timer = 0.0
        self.action_kind = None
        self.tool_cooldown = 0.0
        self.seed_cooldown = 0.0
        self.tool_switch_cooldown = 0.0
        self.seed_switch_cooldown = 0.0
        self.pickup_cooldown = 0.0
        self.fishing_active = False
        self.fishing_has_bite = False
        self.fishing_timer = 0.0
        self.fishing_bite_time = 0.0
        self.fishing_target_tile = None
        self.fishing_bobber_pos = None
        self.fishing_message = ""
        self.fishing_state = None
        self.fishing_state_timer = 0.0
        self.fishing_locality = None
        self.fishing_pending_catch = None
        self.fishing_reels_remaining = 0
        self.current_season = "Summer"
        self.fishing_rng = random.Random()
        self.world_hint_seen = set()
        self.game_state = None
        self.event_dispatcher = None
        self.world_hint_elapsed = 0.0
        self.rock_drop_callback = None
        self.swim_visual = SwimVisual(visual_scale)
        self.feet_collision_offset = pygame.Vector2(0, -36)
        self.collision_box_offset = pygame.Vector2(0, 4)
        self.house = "farmhouse"

        super().__init__(
            pos=pos,
            frames=self.get_scaled_frames(self.status),
            anchor="midbottom",
            animation_speed=6,
            loop=True
        )

        self.name = "player"
        self.collision_box = self.rect.copy().inflate(-self.rect.width * 0.8, -self.rect.height * 0.8)
        self.feet_collision_box = self._make_feet_collision_box()
        if self.soil_layer is not None:
            self.swim_visual.bind_world(self.soil_layer.world)

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    def get_scaled_frames(self, status):
        frames = self.assets.get_character_frames(status, self.customization)
        if self.visual_scale == 1:
            return frames

        scaled_frames = []
        for frame in frames:
            scaled_frames.append(
                pygame.transform.scale(
                    frame,
                    (
                        int(frame.get_width() * self.visual_scale),
                        int(frame.get_height() * self.visual_scale),
                    )
                )
            )
        return scaled_frames

    def set_customization(self, customization):
        self.customization = self.assets.normalize_character_customization(customization)
        self.frames = self.get_scaled_frames(self.status)
        self.index = 0
        self.image_base = self.frames[0]
        self._refresh_image()

    def get_target_pos(self):
        world_tile = self.get_current_world_tile()
        if world_tile is None:
            return pygame.Vector2(self.feet_collision_box.center)
        tile_size = self.soil_layer.world.tile_size
        return pygame.Vector2(
            world_tile[0] * tile_size + tile_size // 2,
            world_tile[1] * tile_size + tile_size // 2,
        )

    def get_farming_target(self):
        """Return the player's farm tile and the action currently available."""
        if self.soil_layer is None:
            return None
        world_tile = self.get_current_world_tile()
        if world_tile is None:
            return None
        soil = self.soil_layer
        if soil.can_harvest_at_tile(world_tile):
            return world_tile, "harvest"
        if self.selected_tool == "shovel" and self.is_tool_usable("shovel") and self.has_weed_at_tile(world_tile):
            return world_tile, "clear"
        if self.selected_tool == "hoe" and self.is_tool_usable("hoe") and soil.can_till_at_tile(world_tile):
            return world_tile, "till"
        if (
            self.selected_tool == "water"
            and self.is_tool_usable("water")
            and self.water_amount > 0
            and soil.can_water_at_tile(world_tile)
        ):
            return world_tile, "water"
        if (
            self.seed_inventory.get(self.selected_seed, 0) > 0
            and soil.can_plant_at_tile(
                world_tile,
                self.selected_seed,
                getattr(self, "game_state", None),
            )
        ):
            return world_tile, "plant"
        return None

    def get_placement_target(self):
        if self.soil_layer is None:
            return None
        inventory = getattr(self, "inventory", None)
        if inventory is None:
            return None
        item = inventory.get_selected_placeable()
        if item is None:
            return None
        world_tile = (
            self.get_current_world_tile()
            if item.placement_type == "fence"
            else self.get_facing_world_tile()
        )
        if world_tile is None:
            return None
        if item.placement_type == "fence":
            action = "place" if can_place_fence_at(self.soil_layer.world, world_tile) else "blocked"
            return world_tile, action
        if item.placement_type in {"crate", "hay", "wheelbarrow"}:
            action = (
                "place"
                if can_place_environment_prop_at(
                    self.soil_layer.world,
                    world_tile,
                    item.placement_type,
                )
                else "blocked"
            )
            return world_tile, action
        return None

    def has_weed_at_tile(self, world_tile):
        if self.soil_layer is None or world_tile is None:
            return False
        world = self.soil_layer.world
        chunk_w, chunk_h = world.chunk_size
        chunk = world.loaded_chunks.get((world_tile[0] // chunk_w, world_tile[1] // chunk_h))
        if chunk is None:
            return False
        return any(
            isinstance(record, dict)
            and record.get("type") == "environment"
            and record.get("prop_type") in {"weed", "bush"}
            and tuple(record.get("world_tile", ())) == tuple(world_tile)
            and not record.get("removed", False)
            for record in chunk.props
        )

    def _make_feet_collision_box(self):
        width = max(4, int(self.rect.width * 0.2))
        height = max(4, int(self.rect.height * 0.08))
        collision_box = pygame.Rect(0, 0, width, height)
        collision_box.midbottom = self._feet_collision_midbottom()
        return collision_box

    def _feet_collision_midbottom(self):
        return (
            self.rect.midbottom[0] + self.feet_collision_offset.x,
            self.rect.midbottom[1] + self.feet_collision_offset.y,
        )

    def sync_collision_boxes(self):
        self.collision_box.center = self.rect.center + self.collision_box_offset
        self.feet_collision_box.midbottom = self._feet_collision_midbottom()

    def get_collision_box_for(self, obj=None):
        """Return the body box used exclusively for movement blocking."""
        return self.collision_box

    def get_interaction_box(self, reach=None, *, directional=False):
        """Return a feet-anchored interaction area, optionally projected forward."""
        if reach is None:
            if self.soil_layer is not None:
                reach = self.soil_layer.world.tile_size
            else:
                reach = max(self.rect.width, self.rect.height)
        reach = max(0, int(reach))
        interaction_box = self.feet_collision_box.inflate(reach, reach)
        if directional and reach:
            facing_x, facing_y = self.get_facing_offset()
            interaction_box.move_ip(
                int(facing_x * reach * 0.5),
                int(facing_y * reach * 0.5),
            )
        return interaction_box

    def switch_tool(self, direction=1):
        if self.fishing_active:
            self.cancel_fishing("Line reeled in")
        for _ in self.tools:
            self.tool_index = (self.tool_index + (1 if direction >= 0 else -1)) % len(self.tools)
            candidate = self.tools[self.tool_index]
            if self.is_tool_usable(candidate):
                self.selected_tool = candidate
                return

    def switch_weapon(self, direction=1):
        for _ in self.weapons:
            self.weapon_index = (self.weapon_index + (1 if direction >= 0 else -1)) % len(self.weapons)
            candidate = self.weapons[self.weapon_index]
            if self.is_tool_usable(candidate):
                self.selected_weapon = candidate
                self._sync_equipped_weapon()
                return

    def cycle_selection_slot(self):
        self.selection_slot_index = (self.selection_slot_index + 1) % len(self.selection_slots)
        self.selected_selection_slot = self.selection_slots[self.selection_slot_index]
        self._sync_equipped_weapon()
        return self.selected_selection_slot

    def change_active_selection(self, direction=1):
        slot = self.selected_selection_slot
        if slot == "seed":
            self.switch_seed(direction)
        elif slot == "weapon":
            self.switch_weapon(direction)
        else:
            self.switch_tool(direction)

    def _sync_equipped_weapon(self, refresh=True):
        """Keep the character layers aligned with the dedicated weapon slot."""
        selected_weapon = getattr(self, "selected_weapon", None)
        if selected_weapon is None and getattr(self, "selected_tool", None) in COMBAT_TOOLS:
            selected_weapon = self.selected_tool
            self.selected_weapon = selected_weapon
        weapon_slot_active = self.is_weapon_slot_selected()
        customization = dict(self.customization)
        customization["weapon"] = (
            selected_weapon
            if weapon_slot_active and selected_weapon in {"sword", "spear"}
            else None
        )
        customization["offhand"] = (
            "shield" if weapon_slot_active and selected_weapon == "shield" else None
        )
        if refresh and hasattr(self, "rect"):
            self.set_customization(customization)
        else:
            self.customization = self.assets.normalize_character_customization(customization)

    def is_weapon_slot_selected(self):
        """Return whether weapon visuals and combat actions are currently active."""
        return getattr(self, "selected_selection_slot", "weapon") == "weapon"

    def _sync_equipped_tool(self, refresh=True):
        """Compatibility alias for saves and callers from the combined-slot era."""
        if getattr(self, "selected_tool", None) in COMBAT_TOOLS:
            self.selected_weapon = self.selected_tool
            if hasattr(self, "selection_slots"):
                self.selected_selection_slot = "weapon"
                self.selection_slot_index = self.selection_slots.index("weapon")
        self._sync_equipped_weapon(refresh=refresh)

    def has_equipped_weapon(self, weapon_name):
        selected = getattr(self, "selected_weapon", getattr(self, "selected_tool", None))
        return (
            self.is_weapon_slot_selected()
            and selected == weapon_name
            and self.is_tool_usable(weapon_name)
        )

    def is_tool_usable(self, tool_name=None):
        tool_name = tool_name or self.selected_tool
        equipment = getattr(self, "equipment_state", {}).get(tool_name)
        if equipment is not None:
            return (
                equipment.get("owned", True)
                and not equipment.get("broken", False)
                and equipment.get("durability", 0) > 0
            )
        return (
            tool_name not in getattr(self, "broken_tools", set())
            and getattr(self, "tool_durability", {}).get(tool_name, 1) > 0
        )

    def wear_tool(self, tool_name=None, amount=1):
        tool_name = tool_name or self.selected_tool
        equipment = getattr(self, "equipment_state", {}).get(tool_name)
        if equipment is not None:
            equipment["durability"] = max(
                0,
                int(equipment.get("durability", 0)) - max(0, int(amount)),
            )
            equipment["broken"] = equipment["durability"] <= 0
            self.tool_durability[tool_name] = equipment["durability"]
            if equipment["broken"]:
                self.broken_tools.add(tool_name)
            else:
                self.broken_tools.discard(tool_name)
            return True
        if tool_name not in getattr(self, "tool_durability", {}):
            return False
        self.tool_durability[tool_name] = max(
            0, self.tool_durability[tool_name] - max(0, int(amount))
        )
        if self.tool_durability[tool_name] <= 0:
            self.broken_tools.add(tool_name)
        return True

    def restore_tool(self, tool_name):
        tool_name = str(tool_name).strip().lower().replace("_", " ")
        if tool_name == "watering can":
            tool_name = "water"
        if not hasattr(self, "tools"):
            self.tools = [
                equipment_id for equipment_id in getattr(self, "tool_max_durability", {})
                if equipment_id not in COMBAT_TOOLS
            ]
        if not hasattr(self, "weapons"):
            self.weapons = [
                equipment_id for equipment_id in getattr(self, "tool_max_durability", {})
                if equipment_id in COMBAT_TOOLS
            ]
        definition = EQUIPMENT_DEFINITIONS.get(tool_name)
        collection = self.weapons if definition and definition.equipment_type == "weapon" else self.tools
        if tool_name not in collection:
            collection.append(tool_name)
        if tool_name in EQUIPMENT_DEFINITIONS and hasattr(self, "equipment_state"):
            equipment = self.equipment_state
            record = equipment.get(tool_name)
            if record is None:
                record = new_equipment_state(tool_name)
                equipment[tool_name] = record
            record["owned"] = True
            record["durability"] = int(record["max_durability"])
            record["broken"] = False
            self.sync_equipment_compatibility()
            return True
        maximum = self.tool_max_durability.get(tool_name, 40)
        self.tool_max_durability[tool_name] = maximum
        self.tool_durability[tool_name] = maximum
        self.broken_tools.discard(tool_name)
        return True

    def sync_equipment_compatibility(self):
        """Keep legacy durability views synchronized with canonical tier state."""
        equipment = getattr(self, "equipment_state", {})
        self.tool_max_durability = {
            equipment_id: int(record["max_durability"])
            for equipment_id, record in equipment.items()
        }
        self.tool_durability = {
            equipment_id: int(record["durability"])
            for equipment_id, record in equipment.items()
        }
        self.broken_tools = {
            equipment_id
            for equipment_id, record in equipment.items()
            if record.get("broken", False) or record.get("durability", 0) <= 0
        }

    def import_legacy_equipment_state(self):
        legacy_maximum = dict(getattr(self, "tool_max_durability", {}))
        legacy_durability = dict(getattr(self, "tool_durability", {}))
        broken = set(getattr(self, "broken_tools", ()))
        self.equipment_state = {}
        for equipment_id in (*self.tools, *getattr(self, "weapons", ())):
            if equipment_id not in EQUIPMENT_DEFINITIONS:
                continue
            record = new_equipment_state(equipment_id)
            record["max_durability"] = max(
                record["max_durability"],
                int(legacy_maximum.get(equipment_id, record["max_durability"])),
            )
            record["durability"] = max(
                0,
                min(
                    record["max_durability"],
                    int(legacy_durability.get(equipment_id, record["durability"])),
                ),
            )
            record["broken"] = equipment_id in broken or record["durability"] <= 0
            self.equipment_state[equipment_id] = normalize_equipment_state(equipment_id, record)
        self.sync_equipment_compatibility()

    def switch_seed(self, direction=1):
        stocked_seeds = [
            index
            for index, seed in enumerate(self.seeds)
            if self.seed_inventory.get(seed, 0) > 0
            and is_crop_unlocked(seed, getattr(self, "game_state", None))
        ]
        if not stocked_seeds:
            return
        ordered = sorted(stocked_seeds)
        if self.seed_index not in ordered:
            self.seed_index = ordered[0]
        else:
            current = ordered.index(self.seed_index)
            self.seed_index = ordered[(current + (1 if direction >= 0 else -1)) % len(ordered)]
        self.selected_seed = self.seeds[self.seed_index]

    def select_tool(self, tool_name):
        """Equip an owned, usable resource tool from an inventory choice."""
        tool_name = str(tool_name or "").strip().lower().replace(" ", "_")
        if tool_name in self.weapons:
            return self.select_weapon(tool_name)
        if tool_name not in self.tools or not self.is_tool_usable(tool_name):
            return False
        if self.fishing_active and tool_name != "fishing_rod":
            self.cancel_fishing("Line reeled in")
        self.tool_index = self.tools.index(tool_name)
        self.selected_tool = tool_name
        return True

    def select_weapon(self, weapon_name):
        weapon_name = str(weapon_name or "").strip().lower().replace(" ", "_")
        if weapon_name not in self.weapons or not self.is_tool_usable(weapon_name):
            return False
        self.weapon_index = self.weapons.index(weapon_name)
        self.selected_weapon = weapon_name
        self._sync_equipped_weapon()
        return True

    def select_seed(self, crop_id):
        crop_id = str(crop_id or "").strip().lower().replace(" ", "_")
        if (
            crop_id not in self.seeds
            or self.seed_inventory.get(crop_id, 0) <= 0
            or not is_crop_unlocked(crop_id, getattr(self, "game_state", None))
        ):
            return False
        self.seed_index = self.seeds.index(crop_id)
        self.selected_seed = crop_id
        return True

    def select_consumable(self, item_name):
        item_name = Player.inventory_food_name(self, item_name)
        if item_name is None:
            return False
        self.selected_consumable = item_name
        self.inventory.hotbar_item_name = item_name
        return True

    def inventory_food_name(self, item_name):
        """Resolve food that exists in the item inventory, never seed stock."""
        from gameplay.stamina import FOOD_STAMINA

        item_name = canonical_item_name(item_name)
        if item_name in FOOD_STAMINA and self.inventory.count_item(item_name) > 0:
            return item_name
        return None

    def selected_hotbar_food(self):
        """Return edible produce from the active one of the five hotbar slots."""
        slots = self.inventory.slots[:5]
        if not slots:
            return None
        index = int(getattr(self, "hotbar_slot_index", 0)) % len(slots)
        return Player.inventory_food_name(self, slots[index].item.name)

    def select_hotbar_item(self, item_name):
        """Route an inventory selection to the matching semantic hotbar slot."""
        normalized = str(item_name or "").strip().lower().replace(" ", "_")
        if normalized in self.tools:
            return self.select_tool(normalized)
        return self.select_consumable(normalized)

    def cycle_hotbar_slot(self):
        slots = self.inventory.slots[:5]
        if not slots:
            self.hotbar_slot_index = 0
            return 0
        current = int(getattr(self, "hotbar_slot_index", 0)) % len(slots)
        occupied = [index for index, slot in enumerate(slots) if slot.item.name]
        if occupied:
            later = [index for index in occupied if index > current]
            self.hotbar_slot_index = later[0] if later else occupied[0]
        else:
            self.hotbar_slot_index = (current + 1) % len(slots)
        self.activate_hotbar_slot(self.hotbar_slot_index)
        return self.hotbar_slot_index

    def activate_hotbar_slot(self, index):
        slots = self.inventory.slots[:5]
        if not 0 <= int(index) < len(slots):
            return False
        self.hotbar_slot_index = int(index)
        item_name = slots[self.hotbar_slot_index].item.name
        return bool(item_name and self.select_hotbar_item(item_name))

    @property
    def is_alive(self):
        return self.health > 0

    def emit_effect(self, effect_name, pos=None, **kwargs):
        effect_manager = getattr(self, "effect_manager", None)
        if effect_manager is None:
            return None
        if pos is None:
            rect = getattr(self, "rect", None)
            if rect is None:
                return None
            pos = rect.center
        return effect_manager.spawn(
            effect_name,
            pos,
            **kwargs,
        )

    def begin_combat_action(self, action, duration):
        if (
            not self.is_alive
            or self.inventory.is_inv
            or self.dialogue_active
            or self.journal_active
            or self.recovery_active
            or self.combat_action_timer > 0
            or self.action_lock_timer > 0
        ):
            return False
        if not self.spend_stamina(ACTION_STAMINA_COSTS["combat"]):
            return False
        if self.fishing_active:
            self.cancel_fishing("Combat interrupted fishing")
        self.combat_action = action
        self.combat_action_timer = max(0.01, float(duration))
        self.action_lock_timer = self.combat_action_timer
        self.direction.update(0, 0)
        return True

    def take_damage(self, amount=1, *, effects=None, source=None):
        if amount <= 0 or self.invulnerable_timer > 0 or not self.is_alive:
            return False

        previous_health = self.health
        self.health = max(0, self.health - int(amount))
        damage_dealt = previous_health - self.health
        self.invulnerable_timer = self.invulnerable_duration
        self.apply_knockback(source)
        if self.health > 0:
            self.combat_action = "hurt_sword"
            self.combat_action_timer = 0.18
            self.action_lock_timer = max(self.action_lock_timer, 0.18)
            self.direction.update(0, 0)
        effect_manager = effects or self.effect_manager
        if effect_manager is not None:
            effect_manager.spawn("blood", self.rect.center)
            effect_manager.spawn(
                "damage_word",
                self.rect.midtop,
                velocity=(0, -12),
                lifetime=0.7,
                fade=True,
            )
            if hasattr(effect_manager, "floating_text"):
                effect_manager.floating_text(
                    f"-{damage_dealt}",
                    (self.rect.centerx, self.rect.top - 12),
                )
        if (
            self.health > 0
            and self.health <= self.max_health / 2
            and not self.half_health_effect_shown
        ):
            self.half_health_effect_shown = True
            if effect_manager is not None:
                effect_manager.spawn(
                    "confusion",
                    self.rect.center,
                    follow=self,
                    offset=(0, -self.rect.height * 0.3),
                )
        if self.health <= 0 and not self.death_effect_shown:
            self.death_effect_shown = True
            self.direction.update(0, 0)
            self.combat_action = None
            self.combat_action_timer = 0.0
            self.inventory.is_inv = False
            if effect_manager is not None:
                effect_manager.spawn("death", self.rect.center)
        return True

    def apply_knockback(self, source, strength=260, duration=None):
        if source is None:
            return False
        source_center = None
        feet_box = getattr(source, "feet_collision_box", None)
        if feet_box is not None:
            source_center = feet_box.center
        elif hasattr(source, "center"):
            source_center = source.center
        elif hasattr(source, "rect"):
            source_center = source.rect.center
        if source_center is None:
            return False

        delta = pygame.Vector2(self.feet_collision_box.center) - pygame.Vector2(source_center)
        if delta.length_squared() == 0:
            delta = -pygame.Vector2(getattr(source, "direction", (0, 1)))
        if delta.length_squared() == 0:
            delta.update(0, 1)
        self.knockback_velocity = delta.normalize() * max(0.0, float(strength))
        self.knockback_timer = max(
            0.01,
            float(self.knockback_duration if duration is None else duration),
        )
        return True

    @property
    def death_animation_complete(self):
        return not self.is_alive and self.animation_finished

    def revive(self):
        self.health = self.max_health
        self.invulnerable_timer = 1.25
        self.half_health_effect_shown = False
        self.death_effect_shown = False
        self.combat_action = None
        self.combat_action_timer = 0.0
        self.action_kind = None
        self.action_timer = 0.0
        self.action_lock_timer = 0.0
        self.knockback_velocity.update(0, 0)
        self.knockback_timer = 0.0
        self.direction.update(0, 0)
        idle_action = "weapon_idle" if getattr(self, "selected_selection_slot", "tool") == "weapon" else "idle"
        self.status = f"{self.facing}_{idle_action}"
        self.loop = True
        self.animation_finished = False
        self.refresh_animation_set()
        return True

    def heal(self, amount=1):
        if amount <= 0 or not self.is_alive:
            return False

        previous = self.health
        self.health = min(self.max_health, self.health + int(amount))
        if self.health > self.max_health / 2:
            self.half_health_effect_shown = False
        return self.health != previous

    def spend_stamina(self, amount):
        if self.game_state is None or not getattr(self, "stamina_enabled", False):
            return True
        amount = max(0.0, float(amount))
        if self.game_state.stamina <= 0:
            return False
        self.game_state.stamina = max(0.0, self.game_state.stamina - amount)
        return True

    def consume_food(self, item_name=None):
        if (
            self.game_state is None
            or not getattr(self, "stamina_enabled", False)
            or self.game_state.stamina >= self.game_state.max_stamina
        ):
            return 0
        from gameplay.stamina import FOOD_STAMINA

        if item_name is None:
            selected = getattr(self, "selected_consumable", None)
            item_name = selected if selected and self.inventory.count_item(selected) else None
            if item_name is None:
                item_name = next((name for name in FOOD_STAMINA if self.inventory.count_item(name)), None)
        item_name = canonical_item_name(item_name)
        restore = FOOD_STAMINA.get(item_name)
        if restore is None or not self.inventory.remove_item_count(item_name, 1):
            return 0
        previous = self.game_state.stamina
        self.game_state.stamina = min(self.game_state.max_stamina, previous + restore)
        if (
            self.inventory.count_item(item_name) <= 0
            and getattr(self, "selected_consumable", None) == item_name
        ):
            self.selected_consumable = next(
                (name for name in FOOD_STAMINA if self.inventory.count_item(name)),
                None,
            )
            if hasattr(self.inventory, "hotbar_item_name"):
                self.inventory.hotbar_item_name = self.selected_consumable
        return round(self.game_state.stamina - previous, 2)

    def get_facing_offset(self):
        if self.facing == "up":
            return 0, -1
        if self.facing == "left":
            return -1, 0
        if self.facing == "right":
            return 1, 0
        return 0, 1

    def get_facing_world_tile(self, distance=1):
        if self.soil_layer is None:
            return None

        current_tile = self.get_current_world_tile()
        if current_tile is None:
            return None
        offset_x, offset_y = self.get_facing_offset()
        return (
            current_tile[0] + offset_x * distance,
            current_tile[1] + offset_y * distance,
        )

    def get_current_world_tile(self):
        if self.soil_layer is None:
            return None
        world = self.soil_layer.world
        return (
            int(self.feet_collision_box.centerx // world.tile_size),
            int(self.feet_collision_box.centery // world.tile_size),
        )

    def get_world_terrain_at_tile(self, world_tile):
        if self.soil_layer is None or world_tile is None:
            return None

        world = self.soil_layer.world
        chunk_w, chunk_h = world.chunk_size
        chunk_coord = (world_tile[0] // chunk_w, world_tile[1] // chunk_h)
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return None

        local_x = world_tile[0] % chunk_w
        local_y = world_tile[1] % chunk_h
        if not chunk.in_bounds(local_x, local_y):
            return None
        return chunk.layers["terrain"][chunk.get_index(local_x, local_y)]

    def can_fish_at_tile(self, world_tile):
        return self.get_world_terrain_at_tile(world_tile) == -1

    def add_fish_to_inventory(self, species=None):
        species = species or self.fishing_pending_catch
        if species is None:
            return False
        return self.inventory.add_item_to_slot(
            Item(species.id, load_fish_icon(species))
        )

    def _set_fishing_state(self, state):
        self.fishing_state = state
        self.fishing_state_timer = 0.0
        self.fishing_has_bite = False

    def _schedule_fishing_bite(self):
        self.fishing_timer = 0.0
        self.fishing_bite_time = self.fishing_rng.uniform(1.5, 4.5)
        self.fishing_has_bite = False
        self.fishing_message = "Waiting..."

    def cancel_fishing(self, message=""):
        self.fishing_active = False
        self.fishing_has_bite = False
        self.fishing_timer = 0.0
        self.fishing_target_tile = None
        self.fishing_bobber_pos = None
        self.fishing_state = None
        self.fishing_state_timer = 0.0
        self.fishing_locality = None
        self.fishing_pending_catch = None
        self.fishing_reels_remaining = 0
        self.fishing_message = message
        if self.action_kind == "fish":
            self.action_kind = None
            self.action_timer = 0.0

    def start_fishing(self):
        target_tile = None
        for distance in (1, 2):
            candidate_tile = self.get_facing_world_tile(distance=distance)
            if self.can_fish_at_tile(candidate_tile):
                target_tile = candidate_tile
                break

        if target_tile is None:
            self.fishing_message = "Face water to fish"
            return False

        world = self.soil_layer.world
        self.fishing_active = True
        self.fishing_has_bite = False
        self.fishing_timer = 0.0
        self.fishing_target_tile = target_tile
        self.fishing_locality = world.get_water_locality(target_tile)
        game_state = getattr(self, "game_state", None)
        if self.fishing_locality == "ocean":
            vessel = getattr(self, "mounted_vessel", None)
            if vessel is None or not getattr(vessel, "allows_sea_fishing", lambda: False)():
                self.cancel_fishing("Unlock the boat and reach 150 Fishing points to fish at sea")
                return False
        self.fishing_pending_catch = choose_fish(
            self.fishing_locality,
            self.current_season,
            self.fishing_rng,
            game_state,
        )
        if self.fishing_pending_catch is None:
            self.cancel_fishing(
                fishing_block_reason(self.fishing_locality, game_state)
            )
            return False
        self.fishing_reels_remaining = self.fishing_pending_catch.required_reels
        self.fishing_bobber_pos = (
            target_tile[0] * world.tile_size + world.tile_size // 2,
            target_tile[1] * world.tile_size + world.tile_size // 2,
        )
        self._set_fishing_state("initial_cast")
        self.fishing_message = f"Casting in {self.fishing_locality} water..."
        return True

    def reel_fishing_line(self):
        if not self.fishing_active:
            return False

        if self.fishing_state != "fish" or not self.fishing_has_bite:
            self.cancel_fishing("Too soon")
            return False

        self.fishing_reels_remaining -= 1
        if self.fishing_reels_remaining <= 0:
            self._set_fishing_state("reel")
            self.fishing_message = "Landing the catch..."
        else:
            self._set_fishing_state("reel_in")
            self.fishing_message = f"Reeling... {self.fishing_reels_remaining} left"
        return True

    def use_fishing_rod(self):
        if self.fishing_active:
            self.reel_fishing_line()
            return True
        return self.start_fishing()

    def refill_watering_can(self):
        if self.water_amount >= self.water_capacity:
            return False
        for distance in (1, 2):
            if self.can_fish_at_tile(self.get_facing_world_tile(distance)):
                self.water_amount = self.water_capacity
                return True
        return False

    def use_selected_placeable(self):
        if self.soil_layer is None:
            return None
        item = self.inventory.get_selected_placeable()
        if item is None:
            return None
        world_tile = (
            self.get_current_world_tile()
            if item.placement_type == "fence"
            else self.get_facing_world_tile()
        )
        if (
            item.placement_type == "fence"
            and can_place_fence_at(self.soil_layer.world, world_tile)
            and set_fence_at(self.soil_layer.world, world_tile, FENCE_SEGMENT)
        ):
            self.inventory.remove_item_count(item.name, 1)
            return "place"
        if (
            item.placement_type in {"crate", "hay", "wheelbarrow"}
            and set_environment_prop_at(
                self.soil_layer.world,
                world_tile,
                item.placement_type,
            )
        ):
            self.inventory.remove_item_count(item.name, 1)
            return "place"
        return None

    def use_tool(self):
        game_state = getattr(self, "game_state", None)
        if not getattr(self, "location_tools_enabled", True) or (
            getattr(self, "stamina_enabled", False)
            and game_state is not None
            and game_state.stamina <= 0
        ):
            return None
        if self.soil_layer is None:
            return None

        # Combat tools use the dedicated combat buttons, not the resource-tool
        # interaction button.
        if self.selected_tool in COMBAT_TOOLS:
            return None

        target_pos = self.get_target_pos()
        if self.soil_layer.harvest_at(target_pos, self) is not None:
            return "harvest"
        if not self.is_tool_usable(self.selected_tool):
            return None

        target_area = self.get_interaction_box(directional=True)
        for chunk in self.soil_layer.world.loaded_chunks.values():
            for prop in chunk.runtime.get("environment_objects", {}).values():
                if (
                    getattr(prop, "prop_type", "") in {"crate", "barrel"}
                    and prop.alive
                    and target_area.colliderect(prop.collision_box)
                ):
                    result = prop.damage(self)
                    self.emit_effect("wood", prop.rect.center)
                    if result and isinstance(result.get("drops"), dict) and result["drops"].get("coin"):
                        self.emit_effect("coin", prop.rect.center)
                    self.wear_tool(self.selected_tool)
                    return "break"

        if self.selected_tool == "hoe":
            if self.soil_layer.till_at(target_pos):
                self.wear_tool("hoe")
                return "till"
            return None
        elif self.selected_tool == "shovel":
            world_tile = self.get_current_world_tile()
            removed = remove_environment_prop_at(
                self.soil_layer.world,
                world_tile,
                ("weed", "bush"),
                player_inventory=self.inventory,
            )
            if removed is not None:
                self.wear_tool("shovel")
                return "clear"
            return None
        elif self.selected_tool == "water":
            if self.water_amount > 0 and self.soil_layer.water_at(target_pos, player=self):
                self.water_amount -= 1
                self.wear_tool("water")
                return "water"
            if self.refill_watering_can():
                target_tile = self.get_facing_world_tile()
                if target_tile is not None:
                    tile_size = self.soil_layer.world.tile_size
                    self.emit_effect(
                        "water",
                        (
                            target_tile[0] * tile_size + tile_size // 2,
                            target_tile[1] * tile_size + tile_size // 2,
                        ),
                    )
                return "refill"
            return None
        elif self.selected_tool == "fishing rod":
            was_active = self.fishing_active
            if self.use_fishing_rod():
                if not was_active:
                    self.wear_tool("fishing rod")
                return "fish"
            return None
        elif self.selected_tool == "pickaxe":
            for chunk in self.soil_layer.world.loaded_chunks.values():
                for rock in chunk.runtime.get("environment_objects", {}).values():
                    if getattr(rock, "prop_type", "") == "rock" and rock.alive and target_area.colliderect(rock.collision_box):
                        result = rock.damage()
                        self.emit_effect("rock", rock.rect.center)
                        rock_drop_callback = getattr(self, "rock_drop_callback", None)
                        if result and result.get("broken") and rock_drop_callback is not None:
                            rock_drop_callback(chunk, rock, result.get("drops", 0))
                        self.wear_tool("pickaxe")
                        return "pickaxe"
        elif self.selected_tool == "axe":
            for chunk in self.soil_layer.world.loaded_chunks.values():
                for tree in chunk.runtime.get("tree_objects", {}).values():
                    if tree.alive and target_area.colliderect(tree.collision_box):
                        tree.damage(self, self.inventory)
                        self.emit_effect("cut", tree.collision_box.center)
                        self.wear_tool("axe")
                        return "axe"
        return None

    def use_seed(self):
        if not getattr(self, "location_tools_enabled", True) or self.soil_layer is None:
            return False
        if self.seed_inventory.get(self.selected_seed, 0) <= 0:
            return False
        game_state = getattr(self, "game_state", None)
        if not is_crop_unlocked(self.selected_seed, game_state):
            return False

        if self.soil_layer.plant_seed_at(
            self.get_target_pos(),
            self.selected_seed,
            game_state=game_state,
        ):
            self.seed_inventory[self.selected_seed] -= 1
            return True
        return False

    def update_timers(self, dt):
        self.action_timer = max(0.0, self.action_timer - dt)
        self.action_lock_timer = max(
            0.0,
            getattr(self, "action_lock_timer", 0.0) - dt,
        )
        self.tool_cooldown = max(0.0, self.tool_cooldown - dt)
        self.seed_cooldown = max(0.0, self.seed_cooldown - dt)
        self.tool_switch_cooldown = max(0.0, self.tool_switch_cooldown - dt)
        self.seed_switch_cooldown = max(0.0, self.seed_switch_cooldown - dt)
        self.pickup_cooldown = max(0.0, self.pickup_cooldown - dt)
        self.invulnerable_timer = max(0.0, self.invulnerable_timer - dt)
        self.combat_action_timer = max(0.0, self.combat_action_timer - dt)
        if self.combat_action_timer <= 0:
            self.combat_action = None
        if self.fishing_active:
            self.fishing_state_timer += dt
            if self.fishing_state == "initial_cast":
                if self.fishing_state_timer >= FISHING_STATE_DURATIONS["initial_cast"]:
                    self._set_fishing_state("cast")
                    self.fishing_message = "Casting..."
            elif self.fishing_state == "cast":
                if self.fishing_state_timer >= FISHING_STATE_DURATIONS["cast"]:
                    self._set_fishing_state("fish")
                    self._schedule_fishing_bite()
            elif self.fishing_state == "fish":
                self.fishing_timer += dt
                if not self.fishing_has_bite and self.fishing_timer >= self.fishing_bite_time:
                    self.fishing_has_bite = True
                    action_name = "Square" if self.controller_input.connected else "Space"
                    self.fishing_message = f"Bite! {action_name}"
            elif self.fishing_state == "reel_in":
                if self.fishing_state_timer >= FISHING_STATE_DURATIONS["reel_in"]:
                    self._set_fishing_state("fish")
                    self._schedule_fishing_bite()
            elif self.fishing_state == "reel":
                if self.fishing_state_timer >= FISHING_STATE_DURATIONS["reel"]:
                    caught = self.fishing_pending_catch
                    added = self.add_fish_to_inventory(caught)
                    if added:
                        from gameplay.events import FishCaught, next_event_id, publish_from

                        publish_from(
                            self,
                            FishCaught(
                                event_id=next_event_id(self, "fish_caught"),
                                fish_id=caught.id,
                                locality=caught.locality,
                                required_reels=caught.required_reels,
                                point_reward=caught.point_reward,
                            ),
                        )
                    message = (
                        f"Caught {caught.name}" if added else "Inventory full"
                    )
                    self.cancel_fishing(message)

    def handle_input(self):
        keys = pygame.key.get_pressed()
        controls = self.controller_input
        controller_tool_pressed = controls.get_button(BUTTON_TOOL)
        if not controller_tool_pressed:
            self._consume_button_lock = False
        self.speed = self.base_speed
        self.is_sprinting = False

        if self.inventory.is_inv or self.dialogue_active or self.journal_active or self.recovery_active or not self.is_alive:
            self.direction.update(0, 0)
            return

        if self.combat_action_timer > 0:
            self.direction.update(0, 0)
            return

        if (
            keys[pygame.K_q]
            or controls.get_button(BUTTON_TOOL_NEXT)
        ) and self.tool_switch_cooldown <= 0:
            self.inventory.selected_item_name = None
            self.cycle_selection_slot()
            self.tool_switch_cooldown = 0.2

        if (
            keys[pygame.K_e]
            or controls.get_button(BUTTON_SEED_NEXT)
        ) and self.seed_switch_cooldown <= 0 and self.mounted_vessel is None:
            self.switch_seed()
            self.seed_switch_cooldown = 0.2

        if (
            keys[pygame.K_SPACE]
            or (
                controller_tool_pressed
                and not getattr(self, "_consume_button_lock", False)
            )
        ) and self.tool_cooldown <= 0:
            if self.mounted_vessel is not None and self.selected_tool != "fishing rod":
                action_kind = None
            elif self.inventory.get_selected_placeable() is not None:
                action_kind = self.use_selected_placeable()
            else:
                action_kind = self.use_tool()
            if action_kind is not None:
                self.spend_stamina(ACTION_STAMINA_COSTS.get(action_kind, 0.5))
                self.action_kind = action_kind
                self.action_timer = 0.55
                self.action_lock_timer = 0.12
                self.tool_cooldown = 0.4
                self.direction.x = 0
                self.direction.y = 0
                return

        if self.fishing_active:
            self.direction.update(0, 0)
            return

        if self.mounted_vessel is not None:
            # VesselManager reads the same movement controls and keeps the
            # player's collision anchor attached to the boat.
            self.direction.update(0, 0)
            return

        if (
            keys[pygame.K_LCTRL]
            or keys[pygame.K_RCTRL]
            or controls.get_button(BUTTON_CANCEL)
        ) and self.seed_cooldown <= 0:
            if self.use_seed():
                self.spend_stamina(ACTION_STAMINA_COSTS["plant"])
                self.action_kind = "plant"
                self.action_timer = 0.55
                self.action_lock_timer = 0.12
                self.seed_cooldown = 0.4
                self.direction.x = 0
                self.direction.y = 0
                return

        if self.action_lock_timer > 0:
            self.direction.x = 0
            self.direction.y = 0
            return

        keyboard_direction = pygame.Vector2(
            (keys[pygame.K_d] or keys[pygame.K_RIGHT])
            - (keys[pygame.K_a] or keys[pygame.K_LEFT]),
            (keys[pygame.K_s] or keys[pygame.K_DOWN])
            - (keys[pygame.K_w] or keys[pygame.K_UP]),
        )
        controller_direction = controls.movement_vector()
        if controller_direction.length_squared() > 0:
            # Preserve stick magnitude so movement eases in outside the
            # deadzone. D-pad movement is already normalized by the mapper.
            self.direction = controller_direction
        elif keyboard_direction.length_squared() > 0:
            self.direction = keyboard_direction.normalize()
        else:
            self.direction.update(0, 0)
        if (
            self.direction.length_squared() > 0
            and (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT])
            and (
                not getattr(self, "stamina_enabled", False)
                or self.game_state is None
                or self.game_state.stamina > 0
            )
        ):
            self.speed = self.base_speed * 1.45
            self.is_sprinting = True

    def update_status(self):
        if not self.is_alive:
            death_weapon = "spear" if self.selected_weapon == "spear" else "sword"
            self.status = f"{self.facing}_dead_{death_weapon}"
            return

        if self.combat_action_timer > 0 and self.combat_action is not None:
            self.status = f"{self.facing}_{self.combat_action}"
            return

        if self.fishing_active:
            self.status = f"{self.facing}_{self.fishing_state}"
            return

        if self.action_kind == "fish":
            self.action_kind = None
            self.action_timer = 0.0
            self.status = f"{self.facing}_idle"
            return

        if self.action_timer > 0:
            animation_action = {
                "till": "hoe",
                "water": "water",
                "plant": "seed",
                "harvest": "hoe",
                "axe": "axe",
                "pickaxe": "axe",
                "shovel": "axe",
                "break": "axe",
                "clear": "axe",
                "refill": "water",
                "place": "seed",
            }.get(self.action_kind, self.selected_tool)
            self.status = f"{self.facing}_{animation_action}"
            return

        self.action_kind = None

        if self.direction.length_squared() == 0:
            idle_action = "weapon_idle" if getattr(self, "selected_selection_slot", "tool") == "weapon" else "idle"
            self.status = f"{self.facing}_{idle_action}"
            return

        if abs(self.direction.x) > abs(self.direction.y):
            self.status = "right" if self.direction.x > 0 else "left"
        else:
            self.status = "down" if self.direction.y > 0 else "up"
        self.facing = self.status

    def refresh_animation_set(self):
        if self.status == self.last_status:
            return

        self.frames = self.get_scaled_frames(self.status)
        self.index = 0
        self.loop = "_dead_" not in self.status
        self.animation_finished = False
        self.image_base = self.frames[0]
        self._refresh_image()

        self.feet_collision_box = self._make_feet_collision_box()
        self.last_status = self.status

    def move(self, dt, collision_objects=None):
        if collision_objects is None:
            collision_objects = []

        displacement = self.direction * self.speed * dt
        if self.knockback_timer > 0:
            displacement += self.knockback_velocity * min(dt, self.knockback_timer)

        self.pos.x += displacement.x
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.sync_collision_boxes()

        for obj in collision_objects:
            player_collision_box = self.collision_box
            if hasattr(obj, "collision_box") and player_collision_box.colliderect(obj.collision_box):
                if displacement.x > 0:
                    player_collision_box.right = obj.collision_box.left
                elif displacement.x < 0:
                    player_collision_box.left = obj.collision_box.right
                self.rect.centerx = round(
                    player_collision_box.centerx - self.collision_box_offset.x
                )
                self.pos.x = self.rect.midbottom[0]
                self.sync_collision_boxes()

        self.pos.y += displacement.y
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.sync_collision_boxes()

        for obj in collision_objects:
            player_collision_box = self.collision_box
            if hasattr(obj, "collision_box") and player_collision_box.colliderect(obj.collision_box):
                if displacement.y > 0:
                    player_collision_box.bottom = obj.collision_box.top
                elif displacement.y < 0:
                    player_collision_box.top = obj.collision_box.bottom
                # Preserve the collision box's offset from the sprite when
                # applying the correction. Otherwise downward collisions are
                # immediately shifted four pixels back inside the obstacle.
                self.rect.centery = round(
                    player_collision_box.centery - self.collision_box_offset.y
                )
                self.pos.y = self.rect.midbottom[1]
                self.sync_collision_boxes()

        if self.knockback_timer > 0:
            self.knockback_timer = max(0.0, self.knockback_timer - dt)
            self.knockback_velocity *= max(0.0, 1.0 - dt * 7.0)
            if self.knockback_timer <= 0:
                self.knockback_velocity.update(0, 0)

    def update(self, dt, collision_objects=None):
        self.update_timers(dt)
        self.handle_input()
        self.update_status()
        self.refresh_animation_set()
        self.move(dt, collision_objects)
        self.animate(dt)
        if getattr(self, "location_tools_enabled", True):
            self.swim_visual.update(self, dt)
        else:
            self.swim_visual.sink_level = 0.0
            self.swim_visual.target_sink_level = 0.0
        self.tick_opacity(dt)
    def add_coins(self, amount=1):
        amount = max(0, int(amount))
        self.coins += amount
        return amount

    def spend_coins(self, amount=1):
        amount = max(0, int(amount))
        if self.coins < amount:
            return False
        self.coins -= amount
        return True
