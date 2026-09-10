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
from ui.inventory import Inventory
from inventory_item import Item
from gameplay.world_objects import (
    can_place_environment_prop_at,
    remove_environment_prop_at,
    set_environment_prop_at,
)
from gameplay.fishing import choose_fish, load_fish_icon
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
        self.visual_scale = visual_scale
        self.soil_layer = soil_layer
        self.controller_input = controller_input or get_controller_input()
        # Combat equipment lives in the same one-of-each rotation as the
        # resource tools shown in the bottom-right HUD slot.
        self.tools = [
            "hoe", "axe", "pickaxe", "shovel", "water", "fishing rod",
            "sword", "spear", "shield",
        ]
        self.tool_max_durability = {
            "hoe": 50,
            "axe": 40,
            "pickaxe": 45,
            "shovel": 45,
            "water": 60,
            "fishing rod": 40,
            "sword": 100,
            "spear": 100,
            "shield": 120,
        }
        self.tool_durability = dict(self.tool_max_durability)
        self.broken_tools = set()
        self.water_capacity = 8
        self.water_amount = self.water_capacity
        self.tool_index = 0
        self.selected_tool = self.tools[self.tool_index]
        self._sync_equipped_tool(refresh=False)
        crop_names = tuple(getattr(self.soil_layer, "available_crops", ()))
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
        self.coins = 25
        self.dialogue_active = False
        self.max_health = 5
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
        self.world_hint_elapsed = 0.0
        self.rock_drop_callback = None
        self.swim_visual = SwimVisual(visual_scale)
        self.feet_collision_offset = pygame.Vector2(0, -36)
        self.collision_box_offset = pygame.Vector2(0, 4)

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
            and soil.can_plant_at_tile(world_tile, self.selected_seed)
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

    def switch_tool(self):
        if self.fishing_active:
            self.cancel_fishing("Line reeled in")
        for _ in self.tools:
            self.tool_index = (self.tool_index + 1) % len(self.tools)
            candidate = self.tools[self.tool_index]
            if self.is_tool_usable(candidate):
                self.selected_tool = candidate
                self._sync_equipped_tool()
                return

    def _sync_equipped_tool(self, refresh=True):
        """Make the selected tool slot the only combat-equipment selector."""
        customization = dict(self.customization)
        customization["weapon"] = (
            self.selected_tool if self.selected_tool in {"sword", "spear"} else None
        )
        customization["offhand"] = "shield" if self.selected_tool == "shield" else None
        if refresh and hasattr(self, "rect"):
            self.set_customization(customization)
        else:
            self.customization = self.assets.normalize_character_customization(customization)

    def has_equipped_weapon(self, weapon_name):
        return self.selected_tool == weapon_name

    def is_tool_usable(self, tool_name=None):
        tool_name = tool_name or self.selected_tool
        return (
            tool_name not in getattr(self, "broken_tools", set())
            and getattr(self, "tool_durability", {}).get(tool_name, 1) > 0
        )

    def wear_tool(self, tool_name=None, amount=1):
        tool_name = tool_name or self.selected_tool
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
            self.tools = list(self.tool_max_durability)
        if tool_name not in self.tools:
            self.tools.append(tool_name)
        maximum = self.tool_max_durability.get(tool_name, 40)
        self.tool_max_durability[tool_name] = maximum
        self.tool_durability[tool_name] = maximum
        self.broken_tools.discard(tool_name)
        return True

    def switch_seed(self):
        stocked_seeds = [
            index
            for index, seed in enumerate(self.seeds)
            if self.seed_inventory.get(seed, 0) > 0
        ]
        if not stocked_seeds:
            return
        later = [index for index in stocked_seeds if index > self.seed_index]
        self.seed_index = later[0] if later else stocked_seeds[0]
        self.selected_seed = self.seeds[self.seed_index]

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
            or self.combat_action_timer > 0
            or self.action_lock_timer > 0
        ):
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

        self.health = max(0, self.health - int(amount))
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
        idle_action = "weapon_idle" if self.selected_tool in COMBAT_TOOLS else "idle"
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
            Item(species.name, load_fish_icon(species))
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
        self.fishing_pending_catch = choose_fish(
            self.fishing_locality,
            self.current_season,
            self.fishing_rng,
        )
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
            if self.water_amount > 0 and self.soil_layer.water_at(target_pos):
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
        if self.soil_layer is None:
            return False
        if self.seed_inventory.get(self.selected_seed, 0) <= 0:
            return False

        if self.soil_layer.plant_seed_at(self.get_target_pos(), self.selected_seed):
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
                    message = (
                        f"Caught {caught.name}" if added else "Inventory full"
                    )
                    self.cancel_fishing(message)

    def handle_input(self):
        keys = pygame.key.get_pressed()
        controls = self.controller_input

        if self.inventory.is_inv or self.dialogue_active or not self.is_alive:
            self.direction.update(0, 0)
            return

        if self.combat_action_timer > 0:
            self.direction.update(0, 0)
            return

        if (
            keys[pygame.K_q]
            or controls.get_button(BUTTON_TOOL_NEXT)
        ) and self.tool_switch_cooldown <= 0:
            if self.inventory.get_selected_placeable() is not None:
                self.inventory.selected_item_name = None
            else:
                self.switch_tool()
            self.tool_switch_cooldown = 0.2

        if (
            keys[pygame.K_e]
            or controls.get_button(BUTTON_SEED_NEXT)
        ) and self.seed_switch_cooldown <= 0:
            self.switch_seed()
            self.seed_switch_cooldown = 0.2

        if (
            keys[pygame.K_SPACE]
            or controls.get_button(BUTTON_TOOL)
        ) and self.tool_cooldown <= 0:
            if self.inventory.get_selected_placeable() is not None:
                action_kind = self.use_selected_placeable()
            else:
                action_kind = self.use_tool()
            if action_kind is not None:
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

        if (
            keys[pygame.K_LCTRL]
            or keys[pygame.K_RCTRL]
            or controls.get_button(BUTTON_CANCEL)
        ) and self.seed_cooldown <= 0:
            if self.use_seed():
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

    def update_status(self):
        if not self.is_alive:
            death_weapon = "spear" if self.selected_tool == "spear" else "sword"
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
            idle_action = "weapon_idle" if self.selected_tool in COMBAT_TOOLS else "idle"
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
        self.swim_visual.update(self, dt)
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
