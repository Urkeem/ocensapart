"""Chunk data model and deterministic generation for terrain and objects."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Callable, Optional

from world.ecology import generate_tree_instance
from entities.environment_prop import list_environment_assets
from entities.house import (
    HOUSE_SOURCE_SIZE,
    choose_house_asset_from_category,
    get_house_asset_names_by_category,
    get_house_asset_scale,
    get_house_render_size,
)
from scenemanager import (
    COASTAL_SCENE_TAGS,
    SCENES_PER_CHUNK,
    get_house_scene_footprint,
    scene_template_bounds,
    weighted_scene_template,
)


HOUSES_PER_CHUNK = 16
ENVIRONMENT_PROPS_PER_CHUNK = 180


class Chunk:
    def __init__(
        self,
        coord: tuple[int, int],
        chunk_size: tuple[int, int],
        tile_size: int,
        origin_tile: tuple[int, int] | None = None,
    ):
        self.coord = coord
        self.chunk_size = chunk_size
        self.tile_size = tile_size
        self.origin_tile = origin_tile if origin_tile is not None else (
            coord[0] * chunk_size[0],
            coord[1] * chunk_size[1],
        )

        self.active = False
        self.loaded = True
        self.dirty = False
        self.generated = False

        width, height = self.chunk_size
        size = width * height

        # Fixed-size layer arrays keep terrain, collision, ecology, and farming
        # state aligned by the same local tile index.
        self.layers = {
            "base": [0] * size,
            "terrain": [0] * size,
            "biome": [0] * size,
            "elevation": [0.0] * size,
            "moisture": [0.0] * size,
            "collision": [0] * size,
            "decoration": [None] * size,
            "soil": [0] * size,
            "soil_water": [0] * size,
            "plant": [None] * size,
        }

        self.binary_map = self.layers["base"]
        self.terrain_map = self.layers["terrain"]
        self.collision = self.layers["collision"]

        self.entities = []
        self.props = []
        self.references = {
            "entities": set(),
            "props": set(),
        }

        # Runtime caches hold regenerated surfaces and objects; they do not
        # need to be serialized with procedural chunk data.
        self.runtime = {
            "tilemap": None,
            "scaled_land_sprites": {},
            "water_sprite": None,
            "water_variants": {},
            "water_objects": {},
            "deep_ocean_surface": None,
            "deep_ocean_tilemap": None,
            "deep_ocean_sprite_cache": {},
            "biome_surface": None,
            "biome_tilemaps": {},
            "biome_sprite_cache": {},
            "soil_surface": None,
            "soil_tilemap": None,
            "soil_sprite_cache": {},
            "plant_objects": {},
            "tree_objects": {},
            "house_objects": {},
            "environment_objects": {},
            "surface": None,
            "last_seen_tick": 0,
        }

        # Save data records player/world mutations separately from procedural
        # generation so unchanged chunks stay lightweight.
        self.save_data = {
            "modified_tiles": {},
            "removed_props": set(),
            "placed_props": [],
            "flags": {},
        }

        self.metadata = {}

    def mark_dirty(self) -> None:
        self.dirty = True

    def set_active(self, value: bool) -> None:
        self.active = value

    def get_world_bounds(self) -> tuple[int, int, int, int]:
        chunk_w, chunk_h = self.chunk_size

        left = self.origin_tile[0] * self.tile_size
        top = self.origin_tile[1] * self.tile_size
        right = left + chunk_w * self.tile_size
        bottom = top + chunk_h * self.tile_size
        return left, top, right, bottom

    def get_index(self, local_x: int, local_y: int) -> int:
        width, _ = self.chunk_size
        return local_y * width + local_x

    def in_bounds(self, local_x: int, local_y: int) -> bool:
        width, height = self.chunk_size
        return 0 <= local_x < width and 0 <= local_y < height

    def get_layer_tile(self, layer_name: str, local_x: int, local_y: int):
        if layer_name not in self.layers:
            raise KeyError(f"Unknown layer: {layer_name}")
        if not self.in_bounds(local_x, local_y):
            return None
        return self.layers[layer_name][self.get_index(local_x, local_y)]

    def set_layer_tile(self, layer_name: str, local_x: int, local_y: int, value) -> bool:
        if layer_name not in self.layers:
            raise KeyError(f"Unknown layer: {layer_name}")
        if not self.in_bounds(local_x, local_y):
            return False

        self.layers[layer_name][self.get_index(local_x, local_y)] = value
        self.binary_map = self.layers["base"]
        self.terrain_map = self.layers["terrain"]
        self.collision = self.layers["collision"]
        self.mark_dirty()
        return True

    def set_layer_data(self, layer_name: str, data: list) -> None:
        if layer_name not in self.layers:
            raise KeyError(f"Unknown layer: {layer_name}")

        width, height = self.chunk_size
        expected_size = width * height
        if len(data) != expected_size:
            raise ValueError(f"Layer '{layer_name}' expected {expected_size} tiles, got {len(data)}")

        self.layers[layer_name] = data
        self.binary_map = self.layers["base"]
        self.terrain_map = self.layers["terrain"]
        self.collision = self.layers["collision"]
        self.mark_dirty()

    def get_binary_tile(self, local_x: int, local_y: int) -> int | None:
        return self.get_layer_tile("base", local_x, local_y)

    def set_binary_tile(self, local_x: int, local_y: int, value: int) -> bool:
        return self.set_layer_tile("base", local_x, local_y, value)

    def get_terrain_tile(self, local_x: int, local_y: int) -> int | None:
        return self.get_layer_tile("terrain", local_x, local_y)

    def set_terrain_tile(self, local_x: int, local_y: int, value: int) -> bool:
        return self.set_layer_tile("terrain", local_x, local_y, value)

    def get_biome_tile(self, local_x: int, local_y: int) -> int | None:
        return self.get_layer_tile("biome", local_x, local_y)

    def set_biome_tile(self, local_x: int, local_y: int, value: int) -> bool:
        return self.set_layer_tile("biome", local_x, local_y, value)

    def get_elevation_tile(self, local_x: int, local_y: int) -> float | None:
        return self.get_layer_tile("elevation", local_x, local_y)

    def set_elevation_tile(self, local_x: int, local_y: int, value: float) -> bool:
        return self.set_layer_tile("elevation", local_x, local_y, value)

    def get_moisture_tile(self, local_x: int, local_y: int) -> float | None:
        return self.get_layer_tile("moisture", local_x, local_y)

    def set_moisture_tile(self, local_x: int, local_y: int, value: float) -> bool:
        return self.set_layer_tile("moisture", local_x, local_y, value)

    def get_collision_tile(self, local_x: int, local_y: int) -> int | None:
        return self.get_layer_tile("collision", local_x, local_y)

    def set_collision_tile(self, local_x: int, local_y: int, value: int) -> bool:
        return self.set_layer_tile("collision", local_x, local_y, value)

    def get_decoration_tile(self, local_x: int, local_y: int):
        return self.get_layer_tile("decoration", local_x, local_y)

    def set_decoration_tile(self, local_x: int, local_y: int, value) -> bool:
        return self.set_layer_tile("decoration", local_x, local_y, value)

    def clear_runtime_cache(self) -> None:
        self.runtime["tilemap"] = None
        self.runtime["scaled_land_sprites"] = {}
        self.runtime["water_sprite"] = None
        self.runtime["water_variants"] = {}
        self.runtime["water_objects"] = {}
        self.runtime["deep_ocean_surface"] = None
        self.runtime["deep_ocean_tilemap"] = None
        self.runtime["deep_ocean_sprite_cache"] = {}
        self.runtime["biome_surface"] = None
        self.runtime["biome_tilemaps"] = {}
        self.runtime["biome_sprite_cache"] = {}
        self.runtime["soil_surface"] = None
        self.runtime["soil_tilemap"] = None
        self.runtime["soil_sprite_cache"] = {}
        self.runtime["plant_objects"] = {}
        self.runtime["tree_objects"] = {}
        self.runtime["house_objects"] = {}
        self.runtime["environment_objects"] = {}
        self.runtime["surface"] = None
        self.mark_dirty()

    def set_saved_tile(self, layer_name: str, local_x: int, local_y: int, value) -> bool:
        if layer_name not in self.layers:
            raise KeyError(f"Unknown layer: {layer_name}")
        if not self.in_bounds(local_x, local_y):
            return False

        index = self.get_index(local_x, local_y)
        self.layers[layer_name][index] = value
        self.save_data["modified_tiles"][(layer_name, local_x, local_y)] = value

        self.binary_map = self.layers["base"]
        self.terrain_map = self.layers["terrain"]
        self.collision = self.layers["collision"]
        self.mark_dirty()
        return True

    # --------------------------------------------------
    # Ecology helpers
    # --------------------------------------------------
    def get_world_tile(self, local_x: int, local_y: int) -> tuple[int, int]:
        return (self.origin_tile[0] + local_x, self.origin_tile[1] + local_y)

    def contains_world_tile(self, world_tile_x: int, world_tile_y: int) -> bool:
        width, height = self.chunk_size
        return (
            self.origin_tile[0] <= world_tile_x < self.origin_tile[0] + width
            and self.origin_tile[1] <= world_tile_y < self.origin_tile[1] + height
        )

    def world_to_local_tile(self, world_tile_x: int, world_tile_y: int) -> tuple[int, int]:
        return world_tile_x - self.origin_tile[0], world_tile_y - self.origin_tile[1]

    def get_world_pos(self, local_x: int, local_y: int) -> tuple[int, int]:
        world_tile_x, world_tile_y = self.get_world_tile(local_x, local_y)
        return (
            world_tile_x * self.tile_size + self.tile_size // 2,
            world_tile_y * self.tile_size + self.tile_size // 2,
        )

    def _stable_seed(self, *parts: object) -> int:
        digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()
        return int(digest[:16], 16)

    def _resolve_biome_name(self, biome_value, biome_name_resolver: Optional[Callable[[object], str]] = None) -> str:
        if biome_name_resolver is not None:
            return biome_name_resolver(biome_value)
        if isinstance(biome_value, str):
            return biome_value
        return str(biome_value)

    def _terrain_to_tile_type(self, local_x: int, local_y: int) -> str:
        terrain_value = self.get_terrain_tile(local_x, local_y)
        biome_value = self.get_biome_tile(local_x, local_y)
        moisture = float(self.get_moisture_tile(local_x, local_y) or 0.0)
        elevation = float(self.get_elevation_tile(local_x, local_y) or 0.0)

        # water
        if terrain_value is None or terrain_value < 0:
            return "water"

        # shoreline / coast edge
        if terrain_value == 0:
            return "sand"

        # inland land: refine using biome + scalar layers
        biome_name = self._resolve_biome_name(biome_value)

        # If biome ids are still integers in the chunk layer, map them here.
        # Adjust these names if you already resolve them elsewhere.
        biome_lookup = {
            0: "ocean",
            1: "coast",
            2: "beach",
            3: "grassland",
            4: "forest",
            5: "swamp",
            6: "dryland",
            7: "desert",
            8: "highlands",
            9: "mountain",
            10: "jungle",
        }

        if isinstance(biome_value, int):
            biome_name = biome_lookup.get(biome_value, str(biome_value))

        if biome_name in {"beach", "coast"}:
            return "sand"

        if biome_name == "swamp":
            return "mud" if moisture >= 0.75 else "swamp"

        if biome_name == "desert":
            return "sand"

        if biome_name == "dryland":
            return "dry_grass" if moisture < 0.30 else "dirt"

        if biome_name in {"mountain", "highlands"}:
            if elevation >= 0.78:
                return "rocky"
            return "grass"

        if biome_name == "forest":
            return "dirt" if moisture < 0.45 else "grass"

        if biome_name == "grassland":
            return "grass"

        if biome_name == "jungle":
            return "grass" if moisture < 0.75 else "swamp"

        return "grass"

    def _is_near_water(self, local_x: int, local_y: int) -> bool:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                nx = local_x + dx
                ny = local_y + dy
                if not self.in_bounds(nx, ny):
                    continue
                if self.get_terrain_tile(nx, ny) is not None and self.get_terrain_tile(nx, ny) < 0:
                    return True
        return False

    def _distance_tiles(self, a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.hypot(a[0] - b[0], a[1] - b[1])

    def _can_place_tree(self, local_x: int, local_y: int, min_spacing: int, placed_tiles: list[tuple[int, int]]) -> bool:
        here = (local_x, local_y)
        return all(self._distance_tiles(here, other) >= min_spacing for other in placed_tiles)

    def _area_is_free(self, local_x: int, local_y: int, width: int, height: int) -> bool:
        for y in range(local_y, local_y + height):
            for x in range(local_x, local_x + width):
                if not self.in_bounds(x, y):
                    return False
                idx = self.get_index(x, y)
                if self.layers["terrain"][idx] <= 0:
                    return False
                if self.layers["collision"][idx] != 0:
                    return False
                if self.layers["decoration"][idx] is not None:
                    return False
        return True

    def _scene_anchor_has_land(self, local_x: int, local_y: int, width: int, height: int) -> bool:
        for y in range(local_y, local_y + height):
            for x in range(local_x, local_x + width):
                if not self.in_bounds(x, y):
                    return False
                terrain = self.get_terrain_tile(x, y)
                if terrain is not None and terrain > 0:
                    return True
        return False

    def _mark_house_area(self, local_x: int, local_y: int, width: int, height: int, house_id: str) -> None:
        for y in range(local_y, local_y + height):
            for x in range(local_x, local_x + width):
                self.set_decoration_tile(x, y, {"type": "house", "id": house_id})
                self.set_collision_tile(x, y, 1)

    def _weighted_scene_template(
        self,
        rng: random.Random,
        used_names: set[str] | None = None,
        *,
        prefer_coastal: bool = False,
    ) -> dict:
        return weighted_scene_template(rng, used_names, prefer_coastal=prefer_coastal)

    def _choose_scene_house_asset(self, rng: random.Random, category: str, prefer: str | None = None) -> str:
        assets = []
        if prefer:
            assets = [
                asset
                for asset in get_house_asset_names_by_category(category)
                if prefer in asset.rsplit("/", 1)[-1]
            ]
        if assets:
            return rng.choice(assets)
        return choose_house_asset_from_category(rng, category)

    def _house_scene_footprint(self, category: str) -> tuple[int, int]:
        return get_house_scene_footprint(category)

    def _scene_template_bounds(self, template: dict) -> tuple[int, int]:
        return scene_template_bounds(template)

    def _chunk_has_coast(self) -> bool:
        width, height = self.chunk_size
        for local_y in range(height):
            for local_x in range(width):
                terrain = self.get_terrain_tile(local_x, local_y)
                if terrain == 0 or (terrain is not None and terrain > 0 and self._is_near_water(local_x, local_y)):
                    return True
        return False

    def _area_is_coastal(self, local_x: int, local_y: int, width: int, height: int, padding: int = 5) -> bool:
        start_x = max(0, local_x - padding)
        end_x = min(self.chunk_size[0], local_x + width + padding)
        start_y = max(0, local_y - padding)
        end_y = min(self.chunk_size[1], local_y + height + padding)

        for y in range(start_y, end_y):
            for x in range(start_x, end_x):
                terrain = self.get_terrain_tile(x, y)
                if terrain == 0 or (terrain is not None and terrain < 0):
                    return True
        return False

    def _make_house_scene_record(
        self,
        *,
        scene_id: str,
        template_name: str,
        local_x: int,
        local_y: int,
        asset: str,
        category: str,
        role: str,
        index: int,
    ) -> dict:
        world_tile_x, world_tile_y = self.get_world_tile(local_x, local_y)
        world_x = world_tile_x * self.tile_size
        world_y = world_tile_y * self.tile_size
        render_w, render_h = get_house_render_size(asset)
        door_w = max(32, min(72, render_w // 3))
        door_h = max(36, min(72, render_h // 4))
        door_rect = (
            max(0, (render_w - door_w) // 2),
            max(0, render_h - door_h - 10),
            door_w,
            door_h,
        )
        door_world_x = world_x + door_rect[0] + door_rect[2] // 2
        door_world_y = world_y + door_rect[1] + door_rect[3]
        footprint = self._house_scene_footprint(category)
        return {
            "type": "house",
            "id": f"{scene_id}:house:{index}",
            "scene_id": scene_id,
            "scene": template_name,
            "role": role,
            "category": category,
            "asset": asset,
            "chunk": self.coord,
            "local_tile": (local_x, local_y),
            "world_tile": (world_tile_x, world_tile_y),
            "world_pos": (world_x, world_y),
            "source_size": HOUSE_SOURCE_SIZE,
            "render_size": (render_w, render_h),
            "scale": get_house_asset_scale(asset),
            "footprint": footprint,
            "door_rect": door_rect,
            "door_tile": (
                int(door_world_x // self.tile_size),
                int(door_world_y // self.tile_size),
            ),
            "prop_area_tiles": {
                "left": (world_tile_x, world_tile_y + footprint[1] - 1),
                "right": (world_tile_x + footprint[0] - 1, world_tile_y + footprint[1] - 1),
            },
        }

    def _place_scene_prop(
        self,
        *,
        scene_id: str,
        template_name: str,
        local_x: int,
        local_y: int,
        prop: dict,
        index: int,
    ) -> dict | None:
        if not self._area_is_free(local_x, local_y, 1, 1):
            return None

        world_tile_x, world_tile_y = self.get_world_tile(local_x, local_y)
        world_x = world_tile_x * self.tile_size + self.tile_size // 2
        world_y = (world_tile_y + 1) * self.tile_size
        prop_type = prop.get("prop_type", "scene_prop")
        prop_id = f"{scene_id}:prop:{index}"
        record = {
            "type": "environment",
            "id": prop_id,
            "scene_id": scene_id,
            "scene": template_name,
            "prop_type": prop_type,
            "variant": prop.get("variant", ""),
            "asset": prop["asset"],
            "chunk": self.coord,
            "local_tile": (local_x, local_y),
            "world_tile": (world_tile_x, world_tile_y),
            "world_pos": (world_x, world_y),
            "blocks_movement": prop.get("blocks", False),
            "health": 0,
            "scale": prop.get("scale", 1),
        }
        self.props.append(record)
        self.set_decoration_tile(local_x, local_y, {"type": "environment", "id": prop_id, "prop_type": prop_type})
        if record["blocks_movement"]:
            self.set_collision_tile(local_x, local_y, 1)
        return record

    def _place_scene_tree(
        self,
        *,
        scene_id: str,
        template_name: str,
        local_x: int,
        local_y: int,
        tree: dict,
        index: int,
    ) -> dict | None:
        if not self._area_is_free(local_x, local_y, tree.get("width", 1), tree.get("height", 1)):
            return None

        world_tile_x, world_tile_y = self.get_world_tile(local_x, local_y)
        world_x, world_y = self.get_world_pos(local_x, local_y)
        tree_record = {
            "type": "tree",
            "id": f"{scene_id}:tree:{index}",
            "scene_id": scene_id,
            "scene": template_name,
            "species": tree.get("species", "oak"),
            "size": tree.get("size", 1.0),
            "min_spacing": tree.get("min_spacing", 1),
            "blocks_movement": tree.get("blocks", True),
            "health": tree.get("health", 5),
            "chunk": self.coord,
            "local_tile": (local_x, local_y),
            "world_tile": (world_tile_x, world_tile_y),
            "world_pos": (world_x, world_y),
            "biome": self._resolve_biome_name(self.get_biome_tile(local_x, local_y)),
            "near_water": self._is_near_water(local_x, local_y),
        }
        self.props.append(tree_record)
        self.set_decoration_tile(local_x, local_y, {"type": "tree", "species": tree_record["species"]})
        if tree_record["blocks_movement"]:
            self.set_collision_tile(local_x, local_y, 1)
        return tree_record

    def generate_house_props(
        self,
        world_seed: int = 0,
        *,
        houses_per_chunk: int = HOUSES_PER_CHUNK,
        clear_existing: bool = True,
    ) -> list[dict]:
        if clear_existing:
            self.props = [
                prop
                for prop in self.props
                if not (
                    isinstance(prop, dict)
                    and (
                        prop.get("type") == "house"
                        or (prop.get("type") == "tree" and prop.get("scene_id"))
                        or (prop.get("type") == "environment" and prop.get("scene_id"))
                    )
                )
            ]
            self.metadata.pop("scene_count", None)
            self.metadata.pop("house_scene", None)
            self.metadata.pop("house_scenes", None)

        width, height = self.chunk_size
        rng = random.Random(self._stable_seed(world_seed, "house-scenes", self.coord))
        generated: list[dict] = []
        placed_scene_names: list[str] = []
        used_scene_names: set[str] = set()
        prefer_coastal = self._chunk_has_coast()
        attempts = 0
        max_attempts = SCENES_PER_CHUNK * 10

        while self.metadata.get("scene_count", 0) < SCENES_PER_CHUNK and len(generated) < houses_per_chunk:
            attempts += 1
            if attempts > max_attempts:
                break

            template = self._weighted_scene_template(rng, used_scene_names, prefer_coastal=prefer_coastal)
            scene_w, scene_h = self._scene_template_bounds(template)
            is_coastal_scene = bool(set(template.get("tags", set())) & COASTAL_SCENE_TAGS)
            candidates = [
                (local_x, local_y)
                for local_y in range(1, max(1, height - scene_h))
                for local_x in range(1, max(1, width - scene_w))
                if self._scene_anchor_has_land(local_x, local_y, scene_w, scene_h)
            ]
            if prefer_coastal and is_coastal_scene:
                coastal_candidates = [
                    candidate
                    for candidate in candidates
                    if self._area_is_coastal(candidate[0], candidate[1], scene_w, scene_h)
                ]
                if coastal_candidates:
                    candidates = coastal_candidates
            if not candidates:
                continue
            rng.shuffle(candidates)

            local_x, local_y = candidates[0]
            scene_id = f"scene:{self.coord}:{local_x}:{local_y}:{template['name']}"
            scene_houses: list[dict] = []
            for house_index, house in enumerate(template.get("houses", [])):
                house_local_x = local_x + house["offset"][0]
                house_local_y = local_y + house["offset"][1]
                category = house.get("category", "primary")
                asset = self._choose_scene_house_asset(rng, category, house.get("prefer"))
                record = self._make_house_scene_record(
                    scene_id=scene_id,
                    template_name=template["name"],
                    local_x=house_local_x,
                    local_y=house_local_y,
                    asset=asset,
                    category=category,
                    role=house.get("role", category),
                    index=house_index,
                )
                footprint_w, footprint_h = record["footprint"]
                if not self._area_is_free(house_local_x, house_local_y, footprint_w, footprint_h):
                    continue
                scene_houses.append((record, house_local_x, house_local_y, footprint_w, footprint_h))

            if not scene_houses:
                continue

            for record, house_local_x, house_local_y, footprint_w, footprint_h in scene_houses:
                self._mark_house_area(house_local_x, house_local_y, footprint_w, footprint_h, record["id"])
                self.props.append(record)
                generated.append(record)

            for prop_index, prop in enumerate(template.get("props", [])):
                self._place_scene_prop(
                    scene_id=scene_id,
                    template_name=template["name"],
                    local_x=local_x + prop["offset"][0],
                    local_y=local_y + prop["offset"][1],
                    prop=prop,
                    index=prop_index,
                )
            for tree_index, tree in enumerate(template.get("trees", [])):
                self._place_scene_tree(
                    scene_id=scene_id,
                    template_name=template["name"],
                    local_x=local_x + tree["offset"][0],
                    local_y=local_y + tree["offset"][1],
                    tree=tree,
                    index=tree_index,
                )
            self.metadata["scene_count"] = self.metadata.get("scene_count", 0) + 1
            placed_scene_names.append(template["name"])
            used_scene_names.add(template["name"])

        self.references["props"] = {
            (prop["type"], prop.get("world_tile"), prop.get("species") or prop.get("id"))
            for prop in self.props
            if isinstance(prop, dict)
        }
        if generated:
            self.metadata["house_count"] = len([prop for prop in self.props if isinstance(prop, dict) and prop.get("type") == "house"])
            self.metadata["house_scene"] = placed_scene_names[0]
            self.metadata["house_scenes"] = placed_scene_names
        self.mark_dirty()
        return generated

    def _choose_environment_prop(self, local_x: int, local_y: int, rng: random.Random):
        terrain_value = self.get_terrain_tile(local_x, local_y)
        if terrain_value is None or terrain_value < 0:
            return None

        biome_name = self._resolve_biome_name(self.get_biome_tile(local_x, local_y))
        if isinstance(self.get_biome_tile(local_x, local_y), int):
            biome_name = {
                0: "ocean",
                1: "coast",
                2: "beach",
                3: "grassland",
                4: "forest",
                5: "swamp",
                6: "dryland",
                7: "desert",
                8: "highlands",
                9: "mountain",
                10: "jungle",
            }.get(self.get_biome_tile(local_x, local_y), str(self.get_biome_tile(local_x, local_y)))

        tile_type = self._terrain_to_tile_type(local_x, local_y)
        near_water = self._is_near_water(local_x, local_y)
        roll = rng.random()

        if tile_type == "sand" and near_water:
            if roll < 0.48:
                return ("shell", "", "shells", False, 0)
            if roll < 0.92:
                return ("weed", "", "thickets/weeds", False, 0)
            if roll < 0.98:
                return ("rock", "small", "rocks/small", True, 3)
            return None

        if biome_name in {"grassland", "forest", "highlands", "jungle", "swamp"}:
            if roll < 0.66:
                variant = "big" if rng.random() < 0.45 else "small"
                return ("bush", variant, f"thickets/bushes/{variant}", False, 0)
            if roll < 0.94:
                return ("weed", "", "thickets/weeds", False, 0)
            if roll < 0.99:
                variant = "big" if rng.random() < 0.25 else "small"
                return ("rock", variant, f"rocks/{variant}", True, 6 if variant == "big" else 3)
            return None

        if biome_name in {"desert", "dryland", "mountain"}:
            if roll < 0.68:
                variant = "big" if rng.random() < 0.35 else "small"
                return ("rock", variant, f"rocks/{variant}", True, 6 if variant == "big" else 3)
            if roll < 0.92 and biome_name == "dryland":
                return ("weed", "", "thickets/weeds", False, 0)
            return None

        return None

    def _asset_from_folder(self, folder: str, rng: random.Random):
        assets = list_environment_assets(*folder.split("/"))
        if not assets:
            return None
        return rng.choice(assets)

    def generate_environment_props(
        self,
        world_seed: int = 0,
        *,
        max_props: int = ENVIRONMENT_PROPS_PER_CHUNK,
        clear_existing: bool = True,
    ) -> list[dict]:
        if clear_existing:
            self.props = [
                prop
                for prop in self.props
                if not (
                    isinstance(prop, dict)
                    and prop.get("type") == "environment"
                    and not prop.get("scene_id")
                )
            ]

        width, height = self.chunk_size
        rng = random.Random(self._stable_seed(world_seed, "environment", self.coord))
        candidates = [
            (local_x, local_y)
            for local_y in range(height)
            for local_x in range(width)
            if self.in_bounds(local_x, local_y)
        ]
        rng.shuffle(candidates)

        generated = []
        for local_x, local_y in candidates:
            if len(generated) >= max_props:
                break
            idx = self.get_index(local_x, local_y)
            if self.layers["decoration"][idx] is not None:
                continue
            if self.layers["collision"][idx] != 0:
                continue

            choice = self._choose_environment_prop(local_x, local_y, rng)
            if choice is None:
                continue

            prop_type, variant, asset_folder, blocks_movement, health = choice
            asset = self._asset_from_folder(asset_folder, rng)
            if asset is None:
                continue

            world_tile_x, world_tile_y = self.get_world_tile(local_x, local_y)
            world_x = world_tile_x * self.tile_size + self.tile_size // 2
            world_y = world_tile_y * self.tile_size + self.tile_size // 2
            prop_id = f"environment:{self.coord}:{local_x}:{local_y}:{prop_type}"
            record = {
                "type": "environment",
                "id": prop_id,
                "prop_type": prop_type,
                "variant": variant,
                "asset": asset,
                "chunk": self.coord,
                "local_tile": (local_x, local_y),
                "world_tile": (world_tile_x, world_tile_y),
                "world_pos": (world_x, world_y),
                "blocks_movement": blocks_movement,
                "health": health,
                "scale": 2,
            }
            self.props.append(record)
            generated.append(record)
            self.set_decoration_tile(local_x, local_y, {"type": "environment", "id": prop_id, "prop_type": prop_type})
            if blocks_movement:
                self.set_collision_tile(local_x, local_y, 1)

        if generated:
            self.metadata["environment_count"] = len(
                [prop for prop in self.props if isinstance(prop, dict) and prop.get("type") == "environment"]
            )
        self.mark_dirty()
        return generated

    def generate_tree_props(
        self,
        world_seed: int = 0,
        *,
        biome_name_resolver: Optional[Callable[[object], str]] = None,
        temperature_resolver: Optional[Callable[[int, int, "Chunk"], float]] = None,
        fertility_resolver: Optional[Callable[[int, int, "Chunk"], float]] = None,
        density_noise_resolver: Optional[Callable[[int, int, "Chunk"], float]] = None,
        clear_existing: bool = True,
        block_collisions: bool = True,
    ) -> list[dict]:
        """
        Generates tree prop records and stores them in chunk.props.

        This keeps ecology generation in the chunk layer and delays sprite instantiation
        until a later rendering/entity pass.
        """
        if clear_existing:
            self.props = [prop for prop in self.props if prop.get("type") != "tree" or prop.get("scene_id")]

        width, height = self.chunk_size
        placed_tiles: list[tuple[int, int]] = []
        generated: list[dict] = []

        for local_y in range(height):
            for local_x in range(width):
                terrain_value = self.get_terrain_tile(local_x, local_y)
                if terrain_value is None or terrain_value < 0:
                    continue

                biome_value = self.get_biome_tile(local_x, local_y)
                biome_name = self._resolve_biome_name(biome_value, biome_name_resolver)

                moisture = float(self.get_moisture_tile(local_x, local_y) or 0.0)
                elevation = float(self.get_elevation_tile(local_x, local_y) or 0.0)
                tile_type = self._terrain_to_tile_type(local_x, local_y)
                near_water = self._is_near_water(local_x, local_y)
                world_tile_x, world_tile_y = self.get_world_tile(local_x, local_y)

                temperature = (
                    temperature_resolver(world_tile_x, world_tile_y, self)
                    if temperature_resolver is not None
                    else max(0.0, min(1.0, 1.0 - elevation * 0.35))
                )
                fertility = (
                    fertility_resolver(world_tile_x, world_tile_y, self)
                    if fertility_resolver is not None
                    else max(0.0, min(1.0, (moisture * 0.7) + ((1.0 - elevation) * 0.3)))
                )
                density_noise = (
                    density_noise_resolver(world_tile_x, world_tile_y, self)
                    if density_noise_resolver is not None
                    else random.Random(self._stable_seed(world_seed, "density", world_tile_x, world_tile_y)).random()
                )

                tile_rng = random.Random(self._stable_seed(world_seed, "tree", self.coord, local_x, local_y))
                tree_data = generate_tree_instance(
                    biome_name=biome_name,
                    moisture=moisture,
                    elevation=elevation,
                    temperature=temperature,
                    fertility=fertility,
                    density_noise=density_noise,
                    tile_type=tile_type,
                    near_water=near_water,
                    rng=tile_rng,
                )
                if tree_data is None:
                    continue

                if not self._can_place_tree(local_x, local_y, tree_data["min_spacing"], placed_tiles):
                    continue

                world_x, world_y = self.get_world_pos(local_x, local_y)
                tree_record = {
                    **tree_data,
                    "chunk": self.coord,
                    "local_tile": (local_x, local_y),
                    "world_tile": (world_tile_x, world_tile_y),
                    "world_pos": (world_x, world_y),
                    "biome": biome_name,
                    "near_water": near_water,
                }
                generated.append(tree_record)
                self.props.append(tree_record)
                placed_tiles.append((local_x, local_y))

                self.set_decoration_tile(local_x, local_y, {"type": "tree", "species": tree_record["species"]})
                if block_collisions and tree_record.get("blocks_movement", True):
                    self.set_collision_tile(local_x, local_y, 1)
                # print(f"chunk {self.coord} tile ({local_x},{local_y}) biome={biome_name} tile_type={tile_type}")

        self.references["props"] = {
            (prop["type"], prop.get("world_tile"), prop.get("species"))
            for prop in self.props
        }
        if generated:
            self.metadata["tree_count"] = len([prop for prop in self.props if prop.get("type") == "tree"])
        self.mark_dirty()

        return generated
