"""Authored interior instances and exterior/interior transitions."""

from __future__ import annotations

from dataclasses import dataclass

import pygame

from data.locations import FARMHOUSE_INTERIOR, LOCATION_CONNECTIONS, LOCATION_DEFINITIONS
from data.story import (
    INSTANCE_NPC_ANCHORS,
    KINGDOM_LOCATION_CHUNK_OFFSETS,
    STORY_NPC_PLACEMENTS,
    WORLD_NPC_OFFSETS,
)
from gameplay.events import AccessDenied, LocationEntered, publish_from
from gameplay.interactions import InteractionTarget
from entities.environment_prop import get_environment_image
from entities.house import get_house_asset_scale, get_house_door_rect, get_house_image
from utils import rp
from world.soil import PLANT_MAX_GROWTH_DAYS


@dataclass
class LocationObject:
    object_id: str
    rect: pygame.Rect
    image: pygame.Surface | None = None
    collision_box: pygame.Rect | None = None
    ground: bool = False

    @property
    def sort_y(self):
        return self.rect.bottom


@dataclass
class ExteriorLocationObject:
    object_id: str
    image: pygame.Surface
    rect: pygame.Rect
    collision_box: pygame.Rect
    location_id: str

    @property
    def sort_y(self):
        return self.rect.bottom


AUTHORED_YARD_DRESSING = {
    "castle_exterior": (
        ("props/lanterns/1.png", 0.12, 46, False),
        ("props/lanterns/1.png", 0.88, 46, False),
        ("props/pots/potsmeduim.png#2", 0.24, 82, True),
        ("props/pots/potsmeduim.png#2", 0.76, 82, True),
    ),
    "jim_home": (
        ("props/trainingyard/armsdisplay2.png", 0.10, 62, True),
        ("props/trainingyard/armsdisplay3.png", 0.24, 92, True),
        ("props/general/barrel.png", 0.78, 62, True),
        ("props/crates/4.png", 0.91, 92, True),
        ("props/lanterns/1.png", 0.68, 40, False),
    ),
    "lillian_home": (
        ("props/general/signpost.png", 0.08, 70, True),
        ("props/crates/1.png", 0.22, 96, True),
        ("props/general/sackopen.png", 0.34, 62, False),
        ("props/pots/potsmeduim.png#1", 0.72, 62, True),
        ("props/flowers_pot_fenced/flowerthin.png#1", 0.84, 92, False),
        ("props/flowers_pot_fenced/flowersmall.png#0", 0.94, 58, False),
    ),
    "alchemist_home": (
        ("props/pots/potsthin.png#0", 0.08, 62, True),
        ("props/pots/potsmeduim.png#0", 0.20, 98, True),
        ("props/buckets/buckets.png#1", 0.32, 62, False),
        ("props/general/barrel.png", 0.76, 98, True),
        ("props/flowers_pot_fenced/flowermeduim.png#1", 0.88, 62, False),
        ("props/lanterns/1.png", 0.94, 98, False),
    ),
    "hunter_lodge": (
        ("props/trainingyard/arrowtrain.png", 0.08, 94, True),
        ("props/trainingyard/trainfigure2.png", 0.22, 58, True),
        ("props/general/hay.png", 0.34, 96, False),
        ("props/trainingyard/tent.png", 0.80, 108, True),
        ("props/general/barrel.png", 0.94, 58, True),
    ),
    "navigator_home": (
        ("props/general/signpost.png", 0.08, 64, True),
        ("props/buckets/buckets.png#2", 0.22, 98, False),
        ("props/crates/3.png", 0.76, 62, True),
        ("props/crates/7.png", 0.88, 98, True),
        ("props/lanterns/1.png", 0.96, 58, False),
    ),
    "pirate_home": (
        ("props/crates/1.png", 0.08, 62, True),
        ("props/crates/6.png", 0.18, 98, True),
        ("props/crates/10.png", 0.30, 62, True),
        ("props/general/barrel.png", 0.76, 98, True),
        ("props/general/sackopen.png", 0.88, 62, False),
        ("props/lanterns/1.png", 0.96, 98, False),
    ),
}


def _crop_record(crop_id: str, index: int) -> dict:
    max_days = PLANT_MAX_GROWTH_DAYS.get(crop_id, 5)
    mature = index in (0, 1)
    growth_days = max_days if mature else max(1, max_days // 2)
    return {
        "type": crop_id,
        "age": 1.0 if mature else growth_days / max_days,
        "growth_days": growth_days,
        "max_growth_days": max_days,
        "planted_at": 360.0,
        "planted_day": 1,
        "last_growth_day": 1,
        "last_watered_at": None,
        "last_watered_day": None,
        "dead": False,
    }


def player_farm_chunk_coord(world, game_state):
    stored = game_state.flag("player_farm.chunk")
    if stored is not None:
        return tuple(stored)
    spawn = world.spawn_chunk
    return min(
        world.farmstead_chunks,
        key=lambda coord: abs(coord[0] - spawn[0]) + abs(coord[1] - spawn[1]),
    )


def ensure_player_farm(world, soil_layer, game_state):
    """Designate one guaranteed farmstead and seed its two tutorial plots."""
    if game_state.flag("game.mode") != "story":
        return None
    chunk_coord = player_farm_chunk_coord(world, game_state)
    chunk = world.loaded_chunks.get(chunk_coord)
    if chunk is None:
        chunk = world.load_chunk(chunk_coord)
    farmhouse = next(
        (
            record
            for record in chunk.props
            if isinstance(record, dict)
            and record.get("type") == "house"
            and record.get("scene") == "farmstead"
            and record.get("role") == "farmhouse"
        ),
        None,
    )
    if farmhouse is None:
        return None

    door_tile = tuple(farmhouse["door_tile"])
    exterior_spawn = (
        door_tile[0] * world.tile_size + world.tile_size // 2,
        (door_tile[1] + 1) * world.tile_size + world.tile_size // 2,
    )
    game_state.set_flag("player_farm.chunk", chunk_coord)
    game_state.set_flag("player_farm.house_id", farmhouse["id"])
    game_state.set_flag("player_farm.door_tile", door_tile)
    game_state.set_flag("player_farm.exterior_spawn", exterior_spawn)

    if not game_state.flag("player_farm.plots_initialized", False):
        soil_tiles = []
        width, height = chunk.chunk_size
        for local_y in range(height):
            for local_x in range(width):
                index = chunk.get_index(local_x, local_y)
                if chunk.layers["soil"][index] == 1 and chunk.layers["plant"][index] is None:
                    soil_tiles.append(chunk.get_world_tile(local_x, local_y))
        soil_tiles.sort(
            key=lambda tile: (
                abs(tile[0] - door_tile[0]) + abs(tile[1] - door_tile[1]),
                tile[1],
                tile[0],
            )
        )
        selected = soil_tiles[:12]
        selected.sort(key=lambda tile: (tile[1], tile[0]))
        if len(selected) >= 5:
            split = len(selected) // 2
            plots = {"corn": selected[:split], "tomato": selected[split:]}
            for crop_id, tiles in plots.items():
                for crop_index, world_tile in enumerate(tiles):
                    target_chunk, (local_x, local_y) = soil_layer.get_chunk_and_local(world_tile)
                    target_chunk.set_saved_tile("soil", local_x, local_y, 1)
                    target_chunk.set_saved_tile("soil_water", local_x, local_y, 0)
                    target_chunk.set_saved_tile("plant", local_x, local_y, _crop_record(crop_id, crop_index))
                    target_chunk.runtime["plant_objects"] = {}
                world.invalidate_soil_chunk_and_neighbors(chunk_coord)
            game_state.set_flag("player_farm.plots", plots)
            game_state.set_flag("player_farm.plots_initialized", True)
    return farmhouse


class LocationInstance:
    """Composed authored room that shares Player movement/collision interfaces."""

    def __init__(self, screen, definition=FARMHOUSE_INTERIOR):
        self.screen = screen
        self.definition = definition
        self.location_id = definition["id"]
        source_size = definition["size"]
        self.scale = float(definition.get("scale", 1.0))
        self.size = (round(source_size[0] * self.scale), round(source_size[1] * self.scale))
        self.origin = pygame.Vector2(
            (screen.get_width() - self.size[0]) // 2,
            (screen.get_height() - self.size[1]) // 2,
        )
        self.floor_source = pygame.image.load(rp(*definition["floor_asset"].split("/"))).convert_alpha()
        self.wall_source = pygame.image.load(rp(*definition["wall_asset"].split("/"))).convert_alpha()
        self.furniture_source = pygame.image.load(rp(*definition["furniture_asset"].split("/"))).convert_alpha()
        self.floor = pygame.transform.scale(self.floor_source, self.size)
        self.wall = pygame.transform.scale(self.wall_source, self.size)
        self.furniture = self._build_furniture()
        self.collisions = self._build_collisions()

    def point(self, anchor_name):
        x, y = self.definition["anchors"][anchor_name]
        return self.origin.x + x * self.scale, self.origin.y + y * self.scale

    def _scaled_rect(self, rect):
        x, y, width, height = rect
        return pygame.Rect(
            round(self.origin.x + x * self.scale),
            round(self.origin.y + y * self.scale),
            max(1, round(width * self.scale)),
            max(1, round(height * self.scale)),
        )

    def _build_furniture(self):
        objects = []
        regions = self.definition.get("furniture_regions", {})
        for record in self.definition.get("furniture", ()):
            source_rect = pygame.Rect(regions[record["region"]])
            source = self.furniture_source.subsurface(source_rect).copy()
            destination = self._scaled_rect((*record["position"], source_rect.width, source_rect.height))
            image = pygame.transform.scale(source, destination.size)
            collision = self._scaled_rect(record["collision"]) if record.get("collision") else None
            objects.append(LocationObject(record["id"], destination, image, collision, record.get("ground", False)))
        return tuple(objects)

    def _build_collisions(self):
        collisions = []
        grid = int(self.definition.get("collision_grid", 16))
        width, height = self.definition["size"]
        for y in range(0, height, grid):
            for x in range(0, width, grid):
                sample_points = (
                    (min(width - 1, x + grid // 2), min(height - 1, y + grid // 2)),
                    (min(width - 1, x + 3), min(height - 1, y + 3)),
                    (min(width - 1, x + grid - 3), min(height - 1, y + grid - 3)),
                )
                if not any(self.floor_source.get_at(point).a for point in sample_points):
                    rect = self._scaled_rect((x, y, min(grid, width - x), min(grid, height - y)))
                    collisions.append(LocationObject(f"boundary:{x}:{y}", rect, collision_box=rect))
        bounds = pygame.Rect(self.origin, self.size)
        thickness = max(8, round(8 * self.scale))
        edge_rects = (
            pygame.Rect(bounds.left, bounds.top, bounds.width, thickness),
            pygame.Rect(bounds.left, bounds.bottom - thickness, bounds.width, thickness),
            pygame.Rect(bounds.left, bounds.top, thickness, bounds.height),
            pygame.Rect(bounds.right - thickness, bounds.top, thickness, bounds.height),
        )
        collisions.extend(
            LocationObject(f"outer-boundary:{index}", rect, collision_box=rect)
            for index, rect in enumerate(edge_rects)
        )
        collisions.extend(obj for obj in self.furniture if obj.collision_box is not None)
        return tuple(collisions)

    def contains(self, point):
        return pygame.Rect(self.origin, self.size).collidepoint(point)

    def draw(self, player, npcs=()):
        self.screen.fill(self.definition.get("accent", (7, 10, 15)))
        self.screen.blit(self.floor, self.origin)
        self.screen.blit(self.wall, self.origin)
        for obj in self.furniture:
            if obj.ground:
                self.screen.blit(obj.image, obj.rect)
        actors = [player, *npcs, *(obj for obj in self.furniture if not obj.ground)]
        for actor in sorted(actors, key=lambda item: getattr(item, "sort_y", item.rect.bottom)):
            self.screen.blit(actor.image, actor.rect)


class LocationManager:
    """Own location instances, authored transitions, and their access rules."""

    def __init__(
        self,
        screen,
        world,
        soil_layer,
        player,
        game_state,
        npc_manager=None,
        event_dispatcher=None,
        definitions=None,
    ):
        self.screen = screen
        self.world = world
        self.soil_layer = soil_layer
        self.player = player
        self.game_state = game_state
        self.npc_manager = npc_manager
        self.event_dispatcher = event_dispatcher
        self.definitions = definitions or LOCATION_DEFINITIONS
        self.instances = {FARMHOUSE_INTERIOR["id"]: LocationInstance(screen)}
        self.interior = self.instances[FARMHOUSE_INTERIOR["id"]]
        self.last_denial_reason = ""
        self.message_callback = None
        self._exterior_objects = {}
        self._exterior_yard_objects = {}
        self.wife = next(
            (npc for npc in getattr(npc_manager, "npcs", ()) if getattr(npc, "story_id", None) == "wife"),
            None,
        )
        self.sleep_callback = None
        self._initialize_kingdom_locations()
        self.restore_current_location()

    def _initialize_kingdom_locations(self):
        """Assign stable world coordinates to every authored kingdom district."""
        farm_spawn = self.game_state.flag(
            "player_farm.exterior_spawn",
            self.world.get_spawn_position(),
        )
        self.game_state.set_flag("location.player_farm.spawn", tuple(farm_spawn))
        farm_chunk = self.game_state.flag(
            "player_farm.chunk",
            self.world.world_to_chunk(farm_spawn),
        )
        chunk_size = getattr(self.world, "chunk_size", (32, 32))
        tile_size = getattr(self.world, "tile_size", 16)
        chunk_w = chunk_size[0] * tile_size
        chunk_h = chunk_size[1] * tile_size
        for location_id, (offset_x, offset_y) in KINGDOM_LOCATION_CHUNK_OFFSETS.items():
            chunk_x = int(farm_chunk[0]) + int(offset_x)
            chunk_y = int(farm_chunk[1]) + int(offset_y)
            position = (
                chunk_x * chunk_w + chunk_w // 2,
                chunk_y * chunk_h + chunk_h // 2,
            )
            self.game_state.set_flag(f"location.{location_id}.spawn", position)

        legacy_locations = {"jim": "player_farm"}
        legacy_locations.update({
            npc_id: "village"
            for npc_id in ("lillian", "alchemist", "hunter", "navigator", "pirate")
        })
        for npc_id, old_location in legacy_locations.items():
            state = self.game_state.story_npcs.get(npc_id)
            if state is not None and state.get("location_id") == old_location:
                state["location_id"] = STORY_NPC_PLACEMENTS[npc_id]["location_id"]

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager
        self.wife = next(
            (npc for npc in getattr(npc_manager, "npcs", ()) if getattr(npc, "story_id", None) == "wife"),
            None,
        )
        self._sync_location_npcs()

    @property
    def is_interior(self):
        definition = self.definitions.get(self.game_state.current_location_id, {})
        return definition.get("runtime") == "instance"

    @property
    def active_instance(self):
        if not self.is_interior:
            return None
        return self._instance(self.game_state.current_location_id)

    def _instance(self, location_id):
        if location_id not in self.instances:
            definition = self.definitions[location_id]
            self.instances[location_id] = LocationInstance(self.screen, definition)
        return self.instances[location_id]

    @staticmethod
    def _quest_status(game_state, quest_id):
        return game_state.quests.get(quest_id, {}).get("status", "locked")

    @staticmethod
    def _normalize_requirement(requirement):
        if "type" in requirement:
            return requirement
        aliases = {
            "min_level": ("min_level", "level"),
            "quest_completed": ("quest_completed", "quest_id"),
            "quest_active": ("quest_active", "quest_id"),
            "story_flag": ("flag", "flag_id"),
            "flag": ("flag", "flag_id"),
            "possess_item": ("possess_item", "item_id"),
            "key_item": ("key_item", "item_id"),
            "min_trust": ("min_trust", "amount"),
            "trust_tier": ("trust_tier", "tier"),
            "kingdom_reputation": ("min_reputation", "amount"),
            "min_reputation": ("min_reputation", "amount"),
            "transport_unlock": ("transport_unlock", "transport_id"),
        }
        for key, (requirement_type, value_name) in aliases.items():
            if key not in requirement:
                continue
            value = requirement[key]
            normalized = dict(requirement)
            normalized["type"] = requirement_type
            if isinstance(value, dict):
                normalized.update(value)
            else:
                normalized[value_name] = value
            return normalized
        raise ValueError(f"Unsupported location requirement {requirement!r}")

    def _has_item(self, item_id):
        inventory = getattr(self.player, "inventory", None)
        if inventory is None:
            return False
        counter = getattr(inventory, "count_item", None)
        return bool(counter and counter(item_id) > 0)

    def _requirement_met(self, requirement):
        requirement = self._normalize_requirement(requirement)
        requirement_type = requirement.get("type")
        progression = self.game_state.progression
        if requirement_type == "min_level":
            return progression.level >= int(requirement.get("level", requirement.get("amount", 1)))
        if requirement_type == "quest_completed":
            return self._quest_status(self.game_state, requirement["quest_id"]) == "completed"
        if requirement_type == "quest_active":
            return self._quest_status(self.game_state, requirement["quest_id"]) in {"active", "ready_to_turn_in"}
        if requirement_type == "flag":
            return self.game_state.flag(requirement["flag_id"]) == requirement.get("value", True)
        if requirement_type in {"key_item", "possess_item"}:
            return self._has_item(requirement["item_id"])
        if requirement_type == "min_trust":
            relationship = self.game_state.relationship(requirement["npc_id"])
            if "tier" in requirement:
                tiers = {"unknown": 0, "guarded": 1, "familiar": 2, "trusted": 3, "ally": 4}
                return tiers.get(relationship.tier, 0) >= tiers.get(requirement["tier"], 0)
            return relationship.trust >= int(requirement.get("amount", 0))
        if requirement_type == "trust_tier":
            tiers = {"unknown": 0, "guarded": 1, "familiar": 2, "trusted": 3, "ally": 4}
            return tiers.get(self.game_state.relationship(requirement["npc_id"]).tier, 0) >= tiers.get(requirement["tier"], 0)
        if requirement_type == "min_reputation":
            return progression.kingdom_reputation >= int(requirement.get("amount", 0))
        if requirement_type == "transport_unlock":
            transport_id = requirement["transport_id"]
            record = self.game_state.transports.get(transport_id, {})
            return bool(record.get("unlocked")) or f"transport.{transport_id}" in progression.unlocks
        raise ValueError(f"Unsupported location requirement {requirement_type!r}")

    @staticmethod
    def _default_denial(requirement):
        requirement = LocationManager._normalize_requirement(requirement)
        requirement_type = requirement["type"]
        if requirement_type == "min_level":
            return f"Reach level {requirement.get('level', requirement.get('amount', 1))} before entering."
        if requirement_type == "quest_completed":
            return f"Complete {requirement['quest_id'].replace('_', ' ')} before entering."
        if requirement_type == "quest_active":
            return f"Start {requirement['quest_id'].replace('_', ' ')} before entering."
        if requirement_type == "flag":
            return "Advance the story before entering this location."
        if requirement_type in {"key_item", "possess_item"}:
            return f"Find the {requirement['item_id'].replace('_', ' ')} before trying this door."
        if requirement_type in {"min_trust", "trust_tier"}:
            return f"Build more Trust with {requirement['npc_id'].replace('_', ' ').title()} before entering."
        if requirement_type == "min_reputation":
            return f"Earn {requirement.get('amount', 0)} kingdom reputation before entering."
        if requirement_type == "transport_unlock":
            return f"Unlock {requirement['transport_id'].replace('_', ' ')} before travelling there."
        return "You cannot enter this location yet."

    def can_enter(self, location_id):
        """Return eligibility and the first useful, player-facing denial reason."""
        definition = self.definitions.get(location_id)
        if definition is None:
            return False, f"The route to {str(location_id).replace('_', ' ')} is not available yet."
        requirements = definition.get("requirements", ())
        if isinstance(requirements, dict):
            requirements = requirements.get("all", ())
        for requirement in requirements:
            if not self._requirement_met(requirement):
                return False, requirement.get("reason") or self._default_denial(requirement)
        return True, ""

    def _deny(self, reason, location_id=None):
        self.last_denial_reason = str(reason)
        if self.event_dispatcher is not None:
            self.event_dispatcher.publish(
                AccessDenied(
                    event_id=self.game_state.next_event_id("access_denied"),
                    location_id=location_id or self.game_state.current_location_id,
                    reason=self.last_denial_reason,
                )
            )
        if self.message_callback is not None:
            self.message_callback(self.last_denial_reason)
        return False

    def enter_location(self, location_id, anchor="entry_spawn"):
        allowed, reason = self.can_enter(location_id)
        if not allowed:
            return self._deny(reason, location_id)
        if location_id == self.game_state.current_location_id:
            return True

        origin_id = self.game_state.current_location_id
        self.game_state.location_return_points[location_id] = {
            "location_id": origin_id,
            "position": tuple(self.player.pos),
        }
        self.game_state.set_location(location_id)
        definition = self.definitions[location_id]
        if definition.get("runtime") == "instance":
            instance = self._instance(location_id)
            self._move_actor(self.player, instance.point(anchor))
            self.player.location_tools_enabled = False
        else:
            flag_id = f"location.{location_id}.spawn"
            position = self.game_state.flag(flag_id)
            if position is None:
                position = tuple(self.player.pos)
                self.game_state.set_flag(flag_id, position)
            self._move_actor(self.player, position)
            self.player.location_tools_enabled = True
            self.world.current_player_chunk = self.world.world_to_chunk(self.player.center)
        self.last_denial_reason = ""
        publish_from(
            self,
            LocationEntered(
                event_id=self.game_state.next_event_id("location_entered"),
                location_id=location_id,
            ),
        )
        self._sync_location_npcs()
        return True

    def exit_location(self):
        location_id = self.game_state.current_location_id
        record = self.game_state.location_return_points.get(location_id, {})
        if not isinstance(record, dict):
            record = {"location_id": "player_farm", "position": record}
        target_id = record.get("location_id", "player_farm")
        position = record.get(
            "position",
            self.game_state.flag("player_farm.exterior_spawn", self.world.get_spawn_position()),
        )
        self.game_state.set_location(target_id)
        self._move_actor(self.player, position)
        self.player.location_tools_enabled = self.definitions.get(target_id, {}).get("runtime") != "instance"
        if self.player.location_tools_enabled:
            self.world.current_player_chunk = self.world.world_to_chunk(self.player.center)
        self._sync_location_npcs()
        return True

    def _move_actor(self, actor, position):
        actor.pos.update(position)
        actor.rect.midbottom = (round(actor.pos.x), round(actor.pos.y))
        if hasattr(actor, "sync_collision_boxes"):
            actor.sync_collision_boxes()
        elif hasattr(actor, "collision_box"):
            actor.collision_box.center = actor.rect.center

    def _sync_wife(self):
        if self.wife is None:
            return
        self.wife.location_id = "player_house_interior"
        self._move_actor(self.wife, self.interior.point("wife"))
        self.game_state.set_story_npc_state("wife", location_id="player_house_interior")

    @staticmethod
    def _house_asset_name(asset_path):
        normalized = str(asset_path).replace("\\", "/")
        marker = "houses/"
        return normalized.split(marker, 1)[1] if marker in normalized else normalized

    def _exterior_npc_position(self, location_id, slot=0):
        """Place a story NPC just beyond the front door of an authored house."""
        definition = self.definitions.get(location_id, {})
        asset_path = definition.get("asset")
        base_position = self.game_state.flag(f"location.{location_id}.spawn")
        if not asset_path or base_position is None:
            return None

        asset_name = self._house_asset_name(asset_path)
        scale = float(definition.get("scale", get_house_asset_scale(asset_name)))
        image = get_house_image(asset_name, scale)
        base = pygame.Vector2(base_position)
        house_rect = image.get_rect(midbottom=(round(base.x), round(base.y - 48)))
        door_rect = get_house_door_rect(asset_name, scale)
        spacing = max(20, round(getattr(self.world, "tile_size", 16) * 0.75))
        side_offset = (int(slot) % 3 - 1) * spacing if slot else 0
        return pygame.Vector2(
            house_rect.left + door_rect.centerx + side_offset,
            house_rect.bottom + spacing,
        )

    def _sync_location_npcs(self):
        """Place every authored cast member at the anchor for their location."""
        if self.npc_manager is None:
            return
        for npc in self.npc_manager.npcs:
            story_id = getattr(npc, "story_id", None)
            if not story_id or getattr(npc, "managed_by_survivor_transport", False):
                continue
            state = self.game_state.story_npcs.get(story_id, {})
            npc.location_id = state.get("location_id", getattr(npc, "location_id", "player_farm"))
            placement = STORY_NPC_PLACEMENTS.get(story_id, {})
            slot = int(placement.get("slot", sum(ord(ch) for ch in story_id)))
            definition = self.definitions.get(npc.location_id, {})
            is_instance = definition.get("runtime") == "instance"
            if is_instance:
                instance = self._instance(npc.location_id)
                anchor = placement.get("anchor")
                if anchor in instance.definition.get("anchors", {}):
                    position = instance.point(anchor)
                else:
                    local = pygame.Vector2(INSTANCE_NPC_ANCHORS[slot % len(INSTANCE_NPC_ANCHORS)])
                    position = instance.origin + local * instance.scale
            else:
                position = self._exterior_npc_position(npc.location_id, slot)
                if position is None:
                    base = pygame.Vector2(
                        self.game_state.flag(
                            f"location.{npc.location_id}.spawn",
                            self.game_state.flag("player_farm.exterior_spawn", tuple(self.player.pos)),
                        )
                    )
                    position = base + pygame.Vector2(WORLD_NPC_OFFSETS[slot % len(WORLD_NPC_OFFSETS)])
            self._move_actor(npc, position)

    def restore_current_location(self):
        if self.is_interior:
            active = self.active_instance
            saved_position = tuple(self.player.pos)
            if (
                (
                    active.location_id == "player_house_interior"
                    and not self.game_state.flag("player_house.initialized", False)
                )
                or
                not active.contains(saved_position)
            ):
                preferred = "bedside_spawn" if self.game_state.current_location_id == "player_house_interior" else "entry_spawn"
                saved_position = active.point(preferred)
            self._move_actor(self.player, saved_position)
            self.player.location_tools_enabled = False
            if self.game_state.current_location_id == "player_house_interior":
                self.game_state.set_flag("player_house.initialized", True)
                self._sync_wife()
        else:
            self.player.location_tools_enabled = True
        self._sync_location_npcs()

    def enter_interior(self, anchor="entry_spawn"):
        exterior_position = tuple(self.player.pos)
        self.game_state.location_return_points["player_house_interior"] = exterior_position
        self.game_state.set_location("player_house_interior")
        self.game_state.set_flag("player_house.initialized", True)
        self._move_actor(self.player, self.interior.point(anchor))
        self.player.location_tools_enabled = False
        self._sync_wife()
        self._sync_location_npcs()
        return True

    def exit_interior(self):
        fallback = self.game_state.flag("player_farm.exterior_spawn", self.world.get_spawn_position())
        position = self.game_state.location_return_points.get("player_house_interior", fallback)
        self.game_state.set_location("player_farm")
        self._move_actor(self.player, position)
        self.player.location_tools_enabled = True
        self.world.current_player_chunk = self.world.world_to_chunk(self.player.center)
        self._sync_location_npcs()
        return True

    def send_to_recovery_spawn(self):
        self.game_state.set_location("player_house_interior")
        self.game_state.set_flag("player_house.initialized", True)
        self._move_actor(self.player, self.interior.point("recovery_spawn"))
        self.player.location_tools_enabled = False
        self._sync_wife()

    def interaction_targets(self, player, max_distance):
        if self.is_interior:
            active = self.active_instance
            if active.location_id == "player_house_interior":
                yield InteractionTarget(
                    "farmhouse-bed",
                    "bed",
                    self,
                    active.point("bed"),
                    priority=5,
                    prompt="Sleep",
                    action=lambda: self.sleep_callback() if self.sleep_callback else False,
                )
            yield InteractionTarget(
                f"{active.location_id}-exit",
                "door",
                self,
                active.point("exit"),
                priority=5,
                prompt="Leave this location",
                action=self.exit_interior if active.location_id == "player_house_interior" else self.exit_location,
            )
            for connection in LOCATION_CONNECTIONS.get(active.location_id, ()):
                target_id = connection["target"]
                yield InteractionTarget(
                    connection["id"],
                    "door",
                    self,
                    active.point(connection.get("anchor", "encounter_spawn")),
                    priority=4,
                    prompt=connection["prompt"],
                    action=lambda target_id=target_id: self.enter_location(target_id),
                )
            return
        exterior = self.game_state.flag("player_farm.exterior_spawn")
        if exterior and self.game_state.current_location_id == "player_farm":
            yield InteractionTarget(
                "farmhouse-entry",
                "door",
                self,
                tuple(exterior),
                priority=5,
                prompt="Enter farmhouse",
                action=self.enter_interior,
            )
        base = pygame.Vector2(
            self.game_state.flag(
                f"location.{self.game_state.current_location_id}.spawn",
                exterior or tuple(self.player.pos),
            )
        )
        connections = LOCATION_CONNECTIONS.get(self.game_state.current_location_id, ())
        for index, connection in enumerate(connections):
            target_id = connection["target"]
            target_definition = self.definitions[target_id]
            target_spawn = self.game_state.flag(f"location.{target_id}.spawn")
            if target_definition.get("runtime") == "world" and target_spawn is not None:
                interaction_position = tuple(target_spawn)
            else:
                offset = pygame.Vector2(connection.get("offset", ((index * 2 - len(connections) + 1) * 128, -112)))
                interaction_position = tuple(base + offset)
            yield InteractionTarget(
                connection["id"],
                "world_edge" if self.definitions[target_id].get("runtime") == "world" else "door",
                self,
                interaction_position,
                priority=3,
                prompt=connection["prompt"],
                action=lambda target_id=target_id: self.enter_location(target_id),
            )

    def collision_objects(self):
        return self.active_instance.collisions if self.is_interior else ()

    def exterior_objects(self):
        if self.is_interior:
            return ()
        objects = []
        for location_id, definition in self.definitions.items():
            asset = definition.get("asset") if definition.get("runtime") == "world" else None
            base_position = self.game_state.flag(f"location.{location_id}.spawn")
            if not asset or base_position is None:
                continue
            scenery = self._exterior_objects.get(location_id)
            if scenery is None:
                asset_name = self._house_asset_name(asset)
                scale = float(definition.get("scale", get_house_asset_scale(asset_name)))
                image = get_house_image(asset_name, scale)
                base = pygame.Vector2(base_position)
                rect = image.get_rect(midbottom=(round(base.x), round(base.y - 48)))
                collision = pygame.Rect(0, 0, round(rect.width * 0.72), max(32, round(rect.height * 0.18)))
                collision.midbottom = rect.midbottom
                scenery = ExteriorLocationObject(
                    f"location-scenery:{location_id}", image, rect, collision, location_id
                )
                self._exterior_objects[location_id] = scenery
            objects.append(scenery)
            yard = self._exterior_yard_objects.get(location_id)
            if yard is None:
                yard = []
                for index, (yard_asset, x_ratio, y_offset, blocks) in enumerate(
                    AUTHORED_YARD_DRESSING.get(location_id, ())
                ):
                    yard_image = get_environment_image(yard_asset, scale=2)
                    yard_rect = yard_image.get_rect(
                        midbottom=(
                            round(scenery.rect.left + scenery.rect.width * x_ratio),
                            scenery.rect.bottom + int(y_offset),
                        )
                    )
                    if blocks:
                        yard_collision = yard_rect.inflate(
                            -round(yard_rect.width * 0.5),
                            -round(yard_rect.height * 0.62),
                        )
                        yard_collision.midbottom = yard_rect.midbottom
                    else:
                        yard_collision = pygame.Rect(yard_rect.midbottom, (0, 0))
                    yard.append(
                        ExteriorLocationObject(
                            f"location-yard:{location_id}:{index}",
                            yard_image,
                            yard_rect,
                            yard_collision,
                            location_id,
                        )
                    )
                yard = tuple(yard)
                self._exterior_yard_objects[location_id] = yard
            objects.extend(yard)
        return tuple(objects)

    def exterior_collision_objects(self):
        return self.exterior_objects()

    def interior_npcs(self):
        return tuple(
            npc
            for npc in getattr(self.npc_manager, "npcs", ())
            if getattr(npc, "location_id", "player_farm") == self.game_state.current_location_id
            and getattr(npc, "is_alive", True)
        )

    def draw(self, extra_objects=()):
        self.active_instance.draw(
            self.player,
            (*self.interior_npcs(), *(extra_objects or ())),
        )
