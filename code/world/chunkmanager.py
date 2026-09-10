"""Chunk data model and deterministic generation for terrain and objects."""

from __future__ import annotations

import hashlib
import math
import random
from typing import Callable, Optional

from world.ecology import generate_tree_instance
from world.fence import FENCE_GATE, FENCE_SEGMENT
from world.biome_visuals import is_grass_patch_tile, is_weed_patch_tile
from entities.environment_prop import list_environment_assets
from entities.house import (
    HOUSE_SOURCE_SIZE,
    choose_house_asset_from_category,
    get_house_asset_names_by_category,
    get_house_asset_scale,
    get_house_door_rect,
    get_house_footprint_tiles,
    get_house_render_size,
)
from scenemanager import (
    COASTAL_SCENE_TAGS,
    HOUSE_SCENE_TEMPLATES,
    SCENES_PER_CHUNK,
    explicit_scene_fence_tiles,
    get_house_scene_footprint,
    scene_template_bounds,
    scene_fence_prop_pairs,
    scene_fence_tiles,
    weighted_scene_template,
)


HOUSES_PER_CHUNK = 16
HOUSE_YARD_MARGINS = (3, 4)
ENVIRONMENT_PROPS_PER_CHUNK = 180
DOCK_CHANCE_PER_COASTAL_CHUNK = 0.35
DOCK_MIN_APPROACH_TILES = 2
DOCK_MAX_APPROACH_TILES = 4
MARKET_STALL_KINDS = ("produce", "grain", "fish_meat")
MARKET_STALL_FOOTPRINT = (2, 2)
MARKET_STALL_GAP = 1
ANIMAL_PEN_SIZES = ((6, 6), (5, 5))
FARM_ANIMAL_POPULATION = ("cow", "pig", "chicken", "chicken")
# Each tuple describes the inclusive left/right extent of one platform row,
# measured perpendicular to the approach pier. Variants keep a solid 5x5
# house core while producing tapered, asymmetric shore silhouettes.
DOCK_PLATFORM_PROFILES = (
    ((-2, 2), (-3, 3), (-4, 3), (-4, 4), (-4, 4), (-3, 4), (-3, 3), (-2, 2)),
    ((-3, 2), (-4, 3), (-4, 4), (-4, 4), (-3, 4), (-3, 3), (-2, 3), (-2, 2)),
    ((-2, 3), (-3, 4), (-4, 4), (-4, 3), (-4, 4), (-3, 4), (-3, 3), (-2, 2)),
)
DOCK_DIRECTIONS = (
    ("east", 1, 0),
    ("west", -1, 0),
    ("south", 0, 1),
    ("north", 0, -1),
)


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
            "path": [0] * size,
            "soil": [0] * size,
            "soil_water": [0] * size,
            "plant": [None] * size,
            "dock": [None] * size,
            "fence": [0] * size,
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
            "water_prefix_sum": None,
            "underwater_surface": None,
            "underwater_distances": None,
            "underwater_mask": None,
            "deep_ocean_surface": None,
            "deep_ocean_tilemap": None,
            "deep_ocean_sprite_cache": {},
            "biome_surface": None,
            "biome_tilemaps": {},
            "biome_sprite_cache": {},
            "mountain_surface": None,
            "path_surface": None,
            "path_tilemap": None,
            "path_sprite_cache": {},
            "soil_surface": None,
            "soil_tilemap": None,
            "soil_sprite_cache": {},
            "soil_water_tilemap": None,
            "soil_water_sprite_cache": {},
            "dock_surface": None,
            "dock_sprite_cache": {},
            "fence_surface": None,
            "fence_tilemap": None,
            "fence_collision_objects": None,
            "plant_objects": {},
            "tree_objects": {},
            "house_objects": {},
            "animal_objects": {},
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

    def _invalidate_layer_runtime(self, layer_name: str) -> None:
        """Invalidate only caches derived from the layer that changed."""
        self.runtime["surface"] = None
        self.runtime.pop("camera_scaled_surface", None)

        if layer_name == "base":
            self.runtime["tilemap"] = None
            self.runtime["scaled_land_sprites"] = {}
        elif layer_name in {"terrain", "elevation"}:
            self.runtime["water_objects"] = {}
            self.runtime["water_prefix_sum"] = None
            self.runtime["deep_ocean_surface"] = None
            self.runtime["deep_ocean_tilemap"] = None
            self.runtime["deep_ocean_sprite_cache"] = {}
            self.runtime["underwater_surface"] = None
            self.runtime["underwater_distances"] = None
            self.runtime["underwater_mask"] = None
        elif layer_name == "biome":
            self.runtime["biome_surface"] = None
            self.runtime["biome_tilemaps"] = {}
            self.runtime["biome_sprite_cache"] = {}
            self.runtime["mountain_surface"] = None
            self.runtime["underwater_surface"] = None
            self.runtime["underwater_distances"] = None
            self.runtime["underwater_mask"] = None
        elif layer_name == "path":
            self.runtime["path_surface"] = None
            self.runtime["path_tilemap"] = None
            self.runtime["path_sprite_cache"] = {}
        elif layer_name in {"soil", "soil_water"}:
            self.runtime["soil_surface"] = None
            self.runtime["soil_water_tilemap"] = None
            self.runtime["soil_water_sprite_cache"] = {}
            if layer_name == "soil":
                self.runtime["soil_tilemap"] = None
                self.runtime["soil_sprite_cache"] = {}
        elif layer_name == "plant":
            self.runtime["plant_objects"] = {}
        elif layer_name == "dock":
            self.runtime["dock_surface"] = None
            self.runtime["dock_sprite_cache"] = {}
        elif layer_name == "fence":
            self.runtime["fence_surface"] = None
            self.runtime["fence_tilemap"] = None
            self.runtime["fence_collision_objects"] = None

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
        self._invalidate_layer_runtime(layer_name)
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
        self._invalidate_layer_runtime(layer_name)
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

    def get_fence_tile(self, local_x: int, local_y: int) -> int | None:
        return self.get_layer_tile("fence", local_x, local_y)

    def set_fence_tile(self, local_x: int, local_y: int, value: int) -> bool:
        return self.set_layer_tile("fence", local_x, local_y, value)

    def get_path_tile(self, local_x: int, local_y: int) -> int | None:
        return self.get_layer_tile("path", local_x, local_y)

    def set_path_tile(self, local_x: int, local_y: int, value: int) -> bool:
        return self.set_layer_tile("path", local_x, local_y, value)

    def generate_path_tiles(self, world_seed: int = 0, *, clear_existing: bool = True):
        from world.paths import generate_path_network

        return generate_path_network(self, world_seed, clear_existing=clear_existing)

    def clear_runtime_cache(self) -> None:
        self.runtime["market_stalls"] = {}
        self.runtime["tilemap"] = None
        self.runtime["scaled_land_sprites"] = {}
        self.runtime["water_sprite"] = None
        self.runtime["water_variants"] = {}
        self.runtime["water_objects"] = {}
        self.runtime["water_prefix_sum"] = None
        self.runtime["underwater_surface"] = None
        self.runtime["underwater_distances"] = None
        self.runtime["underwater_mask"] = None
        self.runtime["deep_ocean_surface"] = None
        self.runtime["deep_ocean_tilemap"] = None
        self.runtime["deep_ocean_sprite_cache"] = {}
        self.runtime["biome_surface"] = None
        self.runtime["biome_tilemaps"] = {}
        self.runtime["biome_sprite_cache"] = {}
        self.runtime["mountain_surface"] = None
        self.runtime["path_surface"] = None
        self.runtime["path_tilemap"] = None
        self.runtime["path_sprite_cache"] = {}
        self.runtime["soil_surface"] = None
        self.runtime["soil_tilemap"] = None
        self.runtime["soil_sprite_cache"] = {}
        self.runtime["soil_water_tilemap"] = None
        self.runtime["soil_water_sprite_cache"] = {}
        self.runtime["dock_surface"] = None
        self.runtime["dock_sprite_cache"] = {}
        self.runtime["fence_surface"] = None
        self.runtime["fence_tilemap"] = None
        self.runtime["fence_collision_objects"] = None
        self.runtime["plant_objects"] = {}
        self.runtime["tree_objects"] = {}
        self.runtime["house_objects"] = {}
        self.runtime["animal_objects"] = {}
        self.runtime["environment_objects"] = {}
        self.runtime["surface"] = None
        self.runtime.pop("camera_scaled_surface", None)
        for cache_name in (
            "_water_objects_cache",
            "_tree_objects_cache",
            "_house_objects_cache",
            "_animal_objects_cache",
            "_environment_objects_cache",
            "_plant_objects_cache",
        ):
            self.runtime.pop(cache_name, None)
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
        self._invalidate_layer_runtime(layer_name)
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
            3: "grassland_and_forest",
            4: "underwater",
            6: "dryland",
            7: "desert",
            9: "mountain",
        }

        if isinstance(biome_value, int):
            biome_name = biome_lookup.get(biome_value, str(biome_value))

        if biome_name in {"beach", "coast"}:
            return "sand"

        if biome_name == "desert":
            return "sand"

        if biome_name == "dryland":
            return "dry_grass" if moisture < 0.30 else "dirt"

        if biome_name == "mountain":
            if elevation >= 0.78:
                return "rocky"
            return "grass"

        if biome_name == "grassland_and_forest":
            return "grass"

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

    @staticmethod
    def _rects_overlap(first: tuple[int, int, int, int], second: tuple[int, int, int, int]) -> bool:
        first_x, first_y, first_w, first_h = first
        second_x, second_y, second_w, second_h = second
        return not (
            first_x + first_w <= second_x
            or second_x + second_w <= first_x
            or first_y + first_h <= second_y
            or second_y + second_h <= first_y
        )

    @staticmethod
    def _house_yard_rect(
        local_x: int,
        local_y: int,
        footprint_w: int,
        footprint_h: int,
        margin: int,
    ) -> tuple[int, int, int, int]:
        return (
            local_x - margin,
            local_y - margin,
            footprint_w + margin * 2,
            footprint_h + margin * 2,
        )

    def _find_house_yard_position(
        self,
        preferred_x: int,
        preferred_y: int,
        footprint_w: int,
        footprint_h: int,
        margin: int,
        reserved_yards: list[tuple[int, int, int, int]],
    ) -> tuple[int, int] | None:
        max_x = self.chunk_size[0] - footprint_w - margin
        max_y = self.chunk_size[1] - footprint_h - margin
        if max_x < margin or max_y < margin:
            return None

        candidates = [
            (x, y)
            for y in range(margin, max_y + 1)
            for x in range(margin, max_x + 1)
        ]
        candidates.sort(
            key=lambda tile: (
                abs(tile[0] - preferred_x) + abs(tile[1] - preferred_y),
                tile[1],
                tile[0],
            )
        )
        for local_x, local_y in candidates:
            yard_rect = self._house_yard_rect(
                local_x,
                local_y,
                footprint_w,
                footprint_h,
                margin,
            )
            if any(self._rects_overlap(yard_rect, reserved) for reserved in reserved_yards):
                continue
            if self._area_is_free(*yard_rect):
                return local_x, local_y
        return None

    def _configure_house_yard(self, record: dict, margin: int) -> None:
        house_x, house_y = record["local_tile"]
        footprint_w, footprint_h = record["footprint"]
        yard_x, yard_y, yard_w, yard_h = self._house_yard_rect(
            house_x,
            house_y,
            footprint_w,
            footprint_h,
            margin,
        )
        door_x = int(record["door_tile"][0] - self.origin_tile[0])
        gate_x = max(yard_x + 1, min(yard_x + yard_w - 2, door_x))
        gate_y = yard_y + yard_h - 1
        record["yard_margin"] = margin
        record["yard_rect"] = (yard_x, yard_y, yard_w, yard_h)
        record["yard_gate_tile"] = (gate_x, gate_y)
        record["yard_entry_tiles"] = tuple(
            (gate_x, y)
            for y in range(house_y + footprint_h, gate_y + 1)
        )

    def _reserved_yard_walkways(self) -> set[tuple[int, int]]:
        return {
            tuple(tile)
            for prop in self.props
            if isinstance(prop, dict) and prop.get("type") == "house"
            for tile in prop.get("yard_entry_tiles", ())
        }

    @staticmethod
    def _yard_fence_tiles(record: dict) -> tuple[tuple[int, int, bool], ...]:
        """Build a few disconnected fence runs instead of a closed perimeter."""
        left, top, width, height = record["yard_rect"]
        right = left + width - 1
        bottom = top + height - 1
        gate = tuple(record["yard_gate_tile"])
        seed_text = f"{record.get('id', '')}|{record['yard_rect']}"
        seed = int(hashlib.sha256(seed_text.encode("utf-8")).hexdigest()[:16], 16)
        rng = random.Random(seed)

        def choose_run(tiles, minimum=2, maximum=4):
            tiles = list(tiles)
            if not tiles:
                return ()
            run_length = min(len(tiles), rng.randint(min(minimum, len(tiles)), min(maximum, len(tiles))))
            start = rng.randint(0, len(tiles) - run_length)
            return tuple(tiles[start:start + run_length])

        # Corners are deliberately excluded so runs on adjacent sides cannot
        # accidentally join into another enclosure.
        runs = [choose_run(((x, top) for x in range(left + 1, right)), 3, 5)]
        side_x = rng.choice((left, right))
        runs.append(choose_run(((side_x, y) for y in range(top + 1, bottom)), 2, 4))

        front_candidates = [
            (x, bottom)
            for x in range(left + 1, right)
            if abs(x - gate[0]) >= 2
        ]
        runs.append(choose_run(front_candidates, 2, 3))
        if width >= 11 and rng.random() < 0.5:
            opposite_x = right if side_x == left else left
            runs.append(choose_run(((opposite_x, y) for y in range(top + 1, bottom)), 2, 3))

        perimeter = {tile for run in runs for tile in run}
        perimeter.add(gate)
        return tuple(
            (x, y, (x, y) == gate)
            for x, y in sorted(perimeter, key=lambda tile: (tile[1], tile[0]))
        )

    def _place_house_yard_fence(self, record: dict, scene_id: str) -> int:
        fence_tiles = self._yard_fence_tiles(record)
        if not fence_tiles:
            return 0
        for fence_x, fence_y, _ in fence_tiles:
            if not self.in_bounds(fence_x, fence_y):
                return 0
            index = self.get_index(fence_x, fence_y)
            if (
                self.layers["terrain"][index] <= 0
                or self.layers["collision"][index] != 0
                or self.layers["decoration"][index] is not None
                or self.layers["fence"][index] != 0
            ):
                return 0

        for fence_x, fence_y, is_gate in fence_tiles:
            index = self.get_index(fence_x, fence_y)
            self.layers["fence"][index] = FENCE_GATE if is_gate else FENCE_SEGMENT
            self.layers["collision"][index] = 0 if is_gate else 1
            self.layers["decoration"][index] = {
                "type": "fence",
                "scene_id": scene_id,
                "house_id": record["id"],
                "gate": is_gate,
            }

        self._invalidate_layer_runtime("fence")
        self.metadata["fence_count"] = self.metadata.get("fence_count", 0) + len(fence_tiles)
        self.mark_dirty()
        return len(fence_tiles)

    def _house_yard_prop_candidates(self, record: dict) -> list[tuple[int, int]]:
        left, top, width, height = record["yard_rect"]
        right = left + width - 1
        bottom = top + height - 1
        house_x, house_y = record["local_tile"]
        footprint_w, footprint_h = record["footprint"]
        door_x = int(record["door_tile"][0] - self.origin_tile[0])
        door_front_y = house_y + footprint_h
        house_tiles = {
            (x, y)
            for y in range(house_y, house_y + footprint_h)
            for x in range(house_x, house_x + footprint_w)
        }
        entry_tiles = set(record.get("yard_entry_tiles", ()))
        candidates = [
            (x, y)
            for y in range(top + 1, bottom)
            for x in range(left + 1, right)
            if (x, y) not in house_tiles and (x, y) not in entry_tiles
        ]
        candidates.sort(
            key=lambda tile: (
                abs(tile[1] - door_front_y),
                abs(tile[0] - door_x),
                tile[1],
                tile[0],
            )
        )
        return [
            tile
            for tile in candidates
            if self._area_is_free(tile[0], tile[1], 1, 1)
            and self.layers["fence"][self.get_index(*tile)] == 0
            and self.layers["soil"][self.get_index(*tile)] == 0
        ]

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

    def _scene_fences_are_free(self, template: dict, local_x: int, local_y: int) -> bool:
        # Complete configured enclosures are placement requirements. Partial
        # primary-house fences are opportunistic and may lose individual pieces
        # to terrain or previously placed scene dressing.
        for offset_x, offset_y, _ in explicit_scene_fence_tiles(template):
            fence_x = local_x + offset_x
            fence_y = local_y + offset_y
            if not self.in_bounds(fence_x, fence_y):
                return False
            index = self.get_index(fence_x, fence_y)
            if self.layers["terrain"][index] <= 0:
                return False
            if self.layers["collision"][index] != 0:
                return False
            if self.layers["decoration"][index] is not None:
                return False
            if self.layers["fence"][index] != 0:
                return False
        explicit_fences = {
            (offset_x, offset_y)
            for offset_x, offset_y, is_gate in explicit_scene_fence_tiles(template)
            if not is_gate
        }
        for fence_x, fence_y, prop_x, prop_y in scene_fence_prop_pairs(template):
            if (fence_x, fence_y) not in explicit_fences:
                continue
            paired_x = local_x + prop_x
            paired_y = local_y + prop_y
            if not self.in_bounds(paired_x, paired_y):
                return False
            index = self.get_index(paired_x, paired_y)
            if self.layers["terrain"][index] <= 0:
                return False
            if self.layers["collision"][index] != 0:
                return False
            if self.layers["decoration"][index] is not None:
                return False
            if self.layers["fence"][index] != 0:
                return False
            if self.layers["soil"][index] != 0:
                return False
        return True

    def _place_scene_fences(self, template: dict, scene_id: str, local_x: int, local_y: int) -> int:
        placed = 0
        prop_pairs = {
            (fence_x, fence_y): (prop_x, prop_y)
            for fence_x, fence_y, prop_x, prop_y in scene_fence_prop_pairs(template)
        }
        for offset_x, offset_y, is_gate in scene_fence_tiles(template):
            fence_x = local_x + offset_x
            fence_y = local_y + offset_y
            if not self.in_bounds(fence_x, fence_y):
                continue
            index = self.get_index(fence_x, fence_y)
            if self.layers["terrain"][index] <= 0:
                continue
            if self.layers["collision"][index] != 0:
                continue
            if self.layers["decoration"][index] is not None:
                continue
            if self.layers["fence"][index] != 0:
                continue
            if not is_gate:
                paired_offset = prop_pairs.get((offset_x, offset_y))
                if paired_offset is None:
                    continue
                paired_x = local_x + paired_offset[0]
                paired_y = local_y + paired_offset[1]
                if not self.in_bounds(paired_x, paired_y):
                    continue
                paired_index = self.get_index(paired_x, paired_y)
                if (
                    self.layers["terrain"][paired_index] <= 0
                    or self.layers["collision"][paired_index] != 0
                    or self.layers["decoration"][paired_index] is not None
                    or self.layers["fence"][paired_index] != 0
                    or self.layers["soil"][paired_index] != 0
                ):
                    continue
            self.layers["fence"][index] = FENCE_GATE if is_gate else FENCE_SEGMENT
            self.layers["collision"][index] = 0 if is_gate else 1
            self.layers["decoration"][index] = {
                "type": "fence",
                "scene_id": scene_id,
                "gate": is_gate,
            }
            placed += 1

        if placed:
            self._invalidate_layer_runtime("fence")
            self.metadata["fence_count"] = self.metadata.get("fence_count", 0) + placed
            self.mark_dirty()
        return placed

    def _place_scene_fence_flowers(
        self,
        template: dict,
        scene_id: str,
        local_x: int,
        local_y: int,
        rng: random.Random,
    ) -> int:
        candidates = list(scene_fence_prop_pairs(template))
        if not candidates:
            return 0
        rng.shuffle(candidates)
        flower_assets = list_environment_assets("props", "flowers_pot_fenced")
        if not flower_assets:
            return 0
        variants = []
        for asset in flower_assets:
            variants.extend(f"{asset}#{frame}" for frame in range(3))

        target_count = max(1, min(8, len(candidates) // 3))
        placed = 0
        for index, (fence_offset_x, fence_offset_y, offset_x, offset_y) in enumerate(candidates):
            if placed >= target_count:
                break
            fence_x = local_x + fence_offset_x
            fence_y = local_y + fence_offset_y
            flower_x = local_x + offset_x
            flower_y = local_y + offset_y
            if not self.in_bounds(fence_x, fence_y) or not self.in_bounds(flower_x, flower_y):
                continue
            if self.layers["fence"][self.get_index(fence_x, fence_y)] != FENCE_SEGMENT:
                continue
            tile_index = self.get_index(flower_x, flower_y)
            if (
                self.layers["terrain"][tile_index] <= 0
                or self.layers["collision"][tile_index] != 0
                or self.layers["decoration"][tile_index] is not None
                or self.layers["fence"][tile_index] != 0
                or self.layers["soil"][tile_index] != 0
            ):
                continue
            world_tile = self.get_world_tile(flower_x, flower_y)
            prop_id = f"{scene_id}:fence-flower:{index}"
            record = {
                "type": "environment",
                "id": prop_id,
                "scene_id": scene_id,
                "prop_type": "flower",
                "variant": "fence_flower",
                "asset": rng.choice(variants),
                "chunk": self.coord,
                "local_tile": (flower_x, flower_y),
                "fence_tile": (fence_x, fence_y),
                "world_tile": world_tile,
                "world_pos": (
                    world_tile[0] * self.tile_size + self.tile_size // 2,
                    (world_tile[1] + 1) * self.tile_size,
                ),
                "blocks_movement": False,
                "health": 0,
                "scale": 1,
            }
            self.props.append(record)
            self.set_decoration_tile(
                flower_x,
                flower_y,
                {"type": "environment", "id": prop_id, "prop_type": "flower"},
            )
            placed += 1
        return placed

    def _place_house_yard_props(
        self,
        template: dict,
        scene_id: str,
        houses: list[dict],
        rng: random.Random,
    ) -> int:
        """Dress free yard tiles, starting beside each mapped front door."""
        if not houses:
            return 0

        potted_assets = list_environment_assets("props", "flowers_pot_fenced")
        potted_variants = [
            f"{asset}#{frame}"
            for asset in potted_assets
            for frame in range(3)
        ]
        natural_flowers = list_environment_assets("flowers")
        placed = 0
        generated_index = len(template.get("props", ()))

        # The entrance gets the reference-image treatment first: authored
        # potted/fenced flowers and a natural flower flank the clear path.
        for house_index, house in enumerate(houses):
            accents = []
            if potted_variants:
                accents.append(
                    {
                        "asset": rng.choice(potted_variants),
                        "prop_type": "flower",
                        "variant": "door_flower_potted",
                    }
                )
            if natural_flowers:
                accents.append(
                    {
                        "asset": rng.choice(natural_flowers),
                        "prop_type": "flower",
                        "variant": "door_flower",
                        "scale": 2,
                    }
                )
            for accent in accents:
                candidates = self._house_yard_prop_candidates(house)
                if not candidates:
                    break
                prop_x, prop_y = candidates[0]
                if self._place_scene_prop(
                    scene_id=scene_id,
                    template_name=template["name"],
                    local_x=prop_x,
                    local_y=prop_y,
                    prop=accent,
                    index=generated_index,
                ) is not None:
                    generated_index += 1
                    placed += 1

        # Template props retain their theme and art, but their old absolute
        # offsets no longer dictate layout. They fill valid yard tiles instead.
        props = list(enumerate(template.get("props", ())))
        props.sort(
            key=lambda item: (
                0 if item[1].get("prop_type") == "flower" else
                1 if item[1].get("prop_type") == "crate" else 2,
                item[0],
            )
        )
        for original_index, prop in props:
            house_order = [houses[(original_index + offset) % len(houses)] for offset in range(len(houses))]
            for house in house_order:
                candidates = self._house_yard_prop_candidates(house)
                if not candidates:
                    continue
                prop_x, prop_y = candidates[0]
                if self._place_scene_prop(
                    scene_id=scene_id,
                    template_name=template["name"],
                    local_x=prop_x,
                    local_y=prop_y,
                    prop=prop,
                    index=original_index,
                ) is not None:
                    placed += 1
                    break
        return placed

    def _place_scene_farm_plots(self, template: dict, local_x: int, local_y: int) -> int:
        """Prepare scene-owned tilled land while leaving every tile seed-ready."""
        placed = 0
        for farm_plot in template.get("farm_plots", []):
            offset_x, offset_y, width, height = farm_plot["rect"]
            for plot_y in range(local_y + offset_y, local_y + offset_y + height):
                for plot_x in range(local_x + offset_x, local_x + offset_x + width):
                    if not self.in_bounds(plot_x, plot_y):
                        continue
                    index = self.get_index(plot_x, plot_y)
                    if self.layers["terrain"][index] <= 0:
                        continue
                    if self.layers["collision"][index] != 0:
                        continue
                    if self.layers["decoration"][index] is not None:
                        continue
                    if self.layers["fence"][index] != 0:
                        continue
                    self.layers["soil"][index] = 1
                    self.layers["soil_water"][index] = 0
                    self.layers["plant"][index] = None
                    placed += 1

        if placed:
            self._invalidate_layer_runtime("soil")
            self.metadata["prepared_farm_tiles"] = self.metadata.get("prepared_farm_tiles", 0) + placed
            self.mark_dirty()
        return placed

    def _animal_pen_area_is_free(self, left: int, top: int, width: int, height: int) -> bool:
        for tile_y in range(top, top + height):
            for tile_x in range(left, left + width):
                if not self.in_bounds(tile_x, tile_y):
                    return False
                index = self.get_index(tile_x, tile_y)
                if (
                    self.layers["terrain"][index] <= 0
                    or self.layers["biome"][index] == 9
                    or self.layers["collision"][index] != 0
                    or self.layers["decoration"][index] is not None
                    or self.layers["fence"][index] != 0
                    or self.layers["dock"][index] is not None
                    or self.layers["path"][index] != 0
                    or self.layers["soil"][index] != 0
                    or self.layers["plant"][index] is not None
                ):
                    return False
        return True

    def _find_animal_pen_rect(
        self,
        preferred: tuple[int, int],
        rng: random.Random,
    ) -> tuple[int, int, int, int] | None:
        chunk_width, chunk_height = self.chunk_size
        for pen_width, pen_height in ANIMAL_PEN_SIZES:
            candidates = [
                (left, top, pen_width, pen_height)
                for top in range(1, chunk_height - pen_height)
                for left in range(1, chunk_width - pen_width)
                if self._animal_pen_area_is_free(left, top, pen_width, pen_height)
            ]
            rng.shuffle(candidates)
            candidates.sort(key=lambda rect: (
                abs((rect[0] + rect[2] // 2) - preferred[0])
                + abs((rect[1] + rect[3] // 2) - preferred[1])
            ))
            if candidates:
                return candidates[0]
        return None

    def _place_scene_animal_pen(
        self,
        template: dict,
        scene_id: str,
        local_x: int,
        local_y: int,
        rng: random.Random,
    ) -> list[dict]:
        """Fence a grass paddock near a farmstead and populate its interior."""
        farm_plots = template.get("farm_plots", ())
        if farm_plots:
            plot_x, plot_y, plot_width, plot_height = farm_plots[0]["rect"]
            preferred = (
                local_x + plot_x + plot_width // 2,
                local_y + plot_y + plot_height // 2,
            )
        else:
            scene_width, scene_height = self._scene_template_bounds(template)
            preferred = (local_x + scene_width // 2, local_y + scene_height // 2)

        pen_rect = self._find_animal_pen_rect(preferred, rng)
        if pen_rect is None:
            return []
        left, top, width, height = pen_rect
        right = left + width - 1
        bottom = top + height - 1
        gate = (left + width // 2, bottom)
        pen_id = f"{scene_id}:animal-pen"

        perimeter = {
            *((tile_x, top) for tile_x in range(left, right + 1)),
            *((tile_x, bottom) for tile_x in range(left, right + 1)),
            *((left, tile_y) for tile_y in range(top + 1, bottom)),
            *((right, tile_y) for tile_y in range(top + 1, bottom)),
        }
        interior_tiles = [
            (tile_x, tile_y)
            for tile_y in range(top + 1, bottom)
            for tile_x in range(left + 1, right)
        ]

        for tile_x, tile_y in perimeter:
            index = self.get_index(tile_x, tile_y)
            is_gate = (tile_x, tile_y) == gate
            self.layers["fence"][index] = FENCE_GATE if is_gate else FENCE_SEGMENT
            self.layers["collision"][index] = 0 if is_gate else 1
            self.layers["decoration"][index] = {
                "type": "fence",
                "scene_id": scene_id,
                "animal_pen_id": pen_id,
                "gate": is_gate,
            }
        for tile_x, tile_y in interior_tiles:
            index = self.get_index(tile_x, tile_y)
            self.layers["decoration"][index] = {
                "type": "animal_pen",
                "scene_id": scene_id,
                "animal_pen_id": pen_id,
            }

        interior_rect = (left + 1, top + 1, width - 2, height - 2)
        world_interior_rect = (
            self.origin_tile[0] + interior_rect[0],
            self.origin_tile[1] + interior_rect[1],
            interior_rect[2],
            interior_rect[3],
        )
        pen_record = {
            "type": "animal_pen",
            "id": pen_id,
            "scene_id": scene_id,
            "chunk": self.coord,
            "local_rect": pen_rect,
            "interior_rect": interior_rect,
            "gate_tile": gate,
        }
        self.props.append(pen_record)

        rng.shuffle(interior_tiles)
        hay_tile = interior_tiles[-1]
        hay_world_tile = self.get_world_tile(*hay_tile)
        hay_id = f"{scene_id}:animal-pen:hay"
        hay_record = {
            "type": "environment",
            "id": hay_id,
            "scene_id": scene_id,
            "prop_type": "hay",
            "variant": "animal_pen_hay",
            "asset": "props/general/hay.png",
            "chunk": self.coord,
            "local_tile": hay_tile,
            "world_tile": hay_world_tile,
            "world_pos": (
                hay_world_tile[0] * self.tile_size + self.tile_size // 2,
                (hay_world_tile[1] + 1) * self.tile_size,
            ),
            "blocks_movement": False,
            "health": 0,
            "scale": 1,
            "animal_pen_id": pen_id,
        }
        self.props.append(hay_record)
        self.layers["decoration"][self.get_index(*hay_tile)] = {
            "type": "environment",
            "id": hay_id,
            "prop_type": "hay",
            "animal_pen_id": pen_id,
        }

        animals = []
        for animal_index, (species, spawn_tile) in enumerate(
            zip(FARM_ANIMAL_POPULATION, interior_tiles)
        ):
            world_tile = self.get_world_tile(*spawn_tile)
            animal_id = f"{scene_id}:animal:{animal_index}:{species}"
            record = {
                "type": "animal",
                "id": animal_id,
                "scene_id": scene_id,
                "animal_pen_id": pen_id,
                "species": species,
                "variant": str(rng.randint(1, 2)),
                "scale": 2.0,
                "chunk": self.coord,
                "local_tile": spawn_tile,
                "world_tile": world_tile,
                "world_pos": (
                    world_tile[0] * self.tile_size + self.tile_size // 2,
                    (world_tile[1] + 1) * self.tile_size,
                ),
                "home_world_rect": world_interior_rect,
                "behavior_seed": self._stable_seed(scene_id, animal_index, species),
            }
            self.props.append(record)
            animals.append(record)

        self._invalidate_layer_runtime("fence")
        self.runtime["animal_objects"] = {}
        self.runtime.pop("_animal_objects_cache", None)
        self.metadata["animal_pen_count"] = self.metadata.get("animal_pen_count", 0) + 1
        self.metadata["animal_count"] = self.metadata.get("animal_count", 0) + len(animals)
        self.mark_dirty()
        return animals

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
        prefix = self.runtime.get("water_prefix_sum")
        chunk_width, chunk_height = self.chunk_size
        stride = chunk_width + 1

        if prefix is None:
            prefix = [0] * ((chunk_width + 1) * (chunk_height + 1))
            terrain = self.layers["terrain"]
            for y in range(chunk_height):
                row_total = 0
                source_row = y * chunk_width
                prefix_row = (y + 1) * stride
                previous_prefix_row = y * stride
                for x in range(chunk_width):
                    if terrain[source_row + x] <= 0:
                        row_total += 1
                    prefix[prefix_row + x + 1] = (
                        prefix[previous_prefix_row + x + 1] + row_total
                    )
            self.runtime["water_prefix_sum"] = prefix

        water_tiles = (
            prefix[end_y * stride + end_x]
            - prefix[start_y * stride + end_x]
            - prefix[end_y * stride + start_x]
            + prefix[start_y * stride + start_x]
        )
        return water_tiles > 0

    def generate_dock_tiles(self, world_seed: int = 0) -> list[tuple[int, int]]:
        """Place a short coastal pier, broad platform, and dockside house."""
        width, height = self.chunk_size
        self.layers["dock"] = [None] * (width * height)
        rng = random.Random(self._stable_seed(world_seed, "docks", self.coord))
        if rng.random() > DOCK_CHANCE_PER_COASTAL_CHUNK:
            self.metadata["dock_count"] = 0
            return []
        platform_profile = rng.choice(DOCK_PLATFORM_PROFILES)
        candidates = []

        for local_y in range(1, height - 1):
            for local_x in range(1, width - 1):
                start_idx = self.get_index(local_x, local_y)
                if self.layers["terrain"][start_idx] < 0:
                    continue
                if self.layers["biome"][start_idx] not in {1, 2}:
                    continue

                for direction, dx, dy in DOCK_DIRECTIONS:
                    behind_idx = self.get_index(local_x - dx, local_y - dy)
                    if self.layers["terrain"][behind_idx] < 0:
                        continue

                    perpendicular_x, perpendicular_y = -dy, dx
                    for approach_length in range(
                        DOCK_MIN_APPROACH_TILES,
                        DOCK_MAX_APPROACH_TILES + 1,
                    ):
                        approach_tiles = [
                            (local_x + dx * distance, local_y + dy * distance)
                            for distance in range(1, approach_length + 1)
                        ]
                        platform_tiles = []
                        platform_valid = True
                        for depth_offset, side_extents in enumerate(platform_profile):
                            distance = approach_length + 1 + depth_offset
                            center_x = local_x + dx * distance
                            center_y = local_y + dy * distance
                            row = []
                            for side_offset in range(side_extents[0], side_extents[1] + 1):
                                platform_x = center_x + perpendicular_x * side_offset
                                platform_y = center_y + perpendicular_y * side_offset
                                if not self.in_bounds(platform_x, platform_y):
                                    platform_valid = False
                                    break
                                platform_idx = self.get_index(platform_x, platform_y)
                                if self.layers["terrain"][platform_idx] != -1:
                                    platform_valid = False
                                    break
                                row.append((platform_x, platform_y))
                            if not platform_valid:
                                break
                            platform_tiles.append(row)

                        if not platform_valid:
                            continue
                        if any(
                            not self.in_bounds(tile_x, tile_y)
                            or self.layers["terrain"][self.get_index(tile_x, tile_y)] != -1
                            for tile_x, tile_y in approach_tiles
                        ):
                            continue

                        platform_set = {
                            tile
                            for platform_row in platform_tiles
                            for tile in platform_row
                        }
                        platform_left = min(tile[0] for tile in platform_set)
                        platform_right = max(tile[0] for tile in platform_set)
                        platform_top = min(tile[1] for tile in platform_set)
                        platform_bottom = max(tile[1] for tile in platform_set)
                        core_left = platform_left + ((platform_right - platform_left + 1) - 5) // 2
                        core_top = platform_top + ((platform_bottom - platform_top + 1) - 5) // 2
                        if any(
                            (core_x, core_y) not in platform_set
                            for core_y in range(core_top, core_top + 5)
                            for core_x in range(core_left, core_left + 5)
                        ):
                            continue

                        candidates.append(
                            (
                                local_x,
                                local_y,
                                direction,
                                approach_tiles,
                                platform_tiles,
                            )
                        )

        if not candidates:
            self.metadata["dock_count"] = 0
            return []

        local_x, local_y, direction, approach_tiles, platform_rows = rng.choice(candidates)
        approach = [(local_x, local_y), *approach_tiles]
        dock_tiles = list(approach)

        for segment_index, (dock_x, dock_y) in enumerate(approach):
            idx = self.get_index(dock_x, dock_y)
            segment = "shore" if segment_index == 0 else "middle"
            self.layers["dock"][idx] = {
                "kind": "walkway",
                "direction": direction,
                "segment": segment,
            }
            self.layers["collision"][idx] = 0
            self.layers["decoration"][idx] = {
                "type": "dock",
                "direction": direction,
                "segment": segment,
            }

        platform_flat = [tile for row in platform_rows for tile in row]
        platform_set = set(platform_flat)
        platform_left = min(tile[0] for tile in platform_flat)
        platform_right = max(tile[0] for tile in platform_flat)
        platform_top = min(tile[1] for tile in platform_flat)
        platform_bottom = max(tile[1] for tile in platform_flat)
        approach_length = len(approach_tiles)
        dx = 1 if direction == "east" else -1 if direction == "west" else 0
        dy = 1 if direction == "south" else -1 if direction == "north" else 0
        connection_tile = (
            local_x + dx * (approach_length + 1),
            local_y + dy * (approach_length + 1),
        )
        for row in platform_rows:
            for dock_x, dock_y in row:
                idx = self.get_index(dock_x, dock_y)
                tile_column = (
                    0 if (dock_x - 1, dock_y) not in platform_set
                    else 2 if (dock_x + 1, dock_y) not in platform_set
                    else 1
                )
                tile_row = (
                    0 if (dock_x, dock_y - 1) not in platform_set
                    else 2 if (dock_x, dock_y + 1) not in platform_set
                    else 1
                )
                if (dock_x, dock_y) == connection_tile:
                    tile_column, tile_row = 1, 1
                record = {
                    "kind": "platform",
                    "direction": direction,
                    "tile_coord": (tile_column, tile_row),
                }
                self.layers["dock"][idx] = record
                self.layers["collision"][idx] = 0
                self.layers["decoration"][idx] = {
                    "type": "dock",
                    "direction": direction,
                    "segment": "platform",
                }
                dock_tiles.append((dock_x, dock_y))

        if rng.random() < 0.72:
            category = "secondary"
            preferred_asset = "fishermanhut"
            role = "dock_fisherman"
        else:
            category = "primary"
            preferred_asset = "beachcabin"
            role = "dock_keeper"
        asset = self._choose_scene_house_asset(rng, category, preferred_asset)
        footprint_w, footprint_h = self._house_scene_footprint(category)
        platform_width = platform_right - platform_left + 1
        platform_height = platform_bottom - platform_top + 1
        house_x = platform_left + (platform_width - footprint_w) // 2
        house_y = platform_top + (platform_height - footprint_h) // 2
        house_record = self._make_house_scene_record(
            scene_id=f"dock:{self.coord}:{local_x}:{local_y}",
            template_name="dock_platform",
            local_x=house_x,
            local_y=house_y,
            asset=asset,
            category=category,
            role=role,
            index=0,
        )
        house_record["dock_house"] = True
        self._mark_house_area(
            house_x,
            house_y,
            footprint_w,
            footprint_h,
            house_record["id"],
        )
        self.props.append(house_record)

        self.metadata["dock_count"] = 1
        self.metadata["dock_tiles"] = tuple(dock_tiles)
        self.metadata["dock_house_asset"] = asset
        self.mark_dirty()
        return dock_tiles

    def generate_market_stalls(self, world_seed: int = 0) -> list[dict]:
        """Place one three-stall market on beach land beside a generated dock."""
        self.props = [
            record
            for record in self.props
            if not (isinstance(record, dict) and record.get("type") == "market_stall")
        ]
        self.runtime["market_stalls"] = {}
        self.metadata["market_count"] = 0
        if not self.metadata.get("dock_count"):
            return []

        width, height = self.chunk_size
        stall_w, stall_h = MARKET_STALL_FOOTPRINT
        market_w = len(MARKET_STALL_KINDS) * stall_w + (len(MARKET_STALL_KINDS) - 1) * MARKET_STALL_GAP
        market_h = len(MARKET_STALL_KINDS) * stall_h + (len(MARKET_STALL_KINDS) - 1) * MARKET_STALL_GAP
        layouts = (
            (
                "row",
                market_w,
                stall_h,
                tuple((index * (stall_w + MARKET_STALL_GAP), 0) for index in range(len(MARKET_STALL_KINDS))),
            ),
            (
                "column",
                stall_w,
                market_h,
                tuple((0, index * (stall_h + MARKET_STALL_GAP)) for index in range(len(MARKET_STALL_KINDS))),
            ),
        )
        shore_tiles = []
        for idx, dock_record in enumerate(self.layers.get("dock", ())):
            if isinstance(dock_record, dict) and dock_record.get("segment") == "shore":
                shore_tiles.append((idx % width, idx // width))
        if not shore_tiles:
            return []

        candidates = []
        for layout_name, layout_w, layout_h, offsets in layouts:
            for local_y in range(1, height - layout_h - 1):
                for local_x in range(1, width - layout_w):
                    if not self._area_is_free(local_x, local_y, layout_w, layout_h + 1):
                        continue
                    footprint_biomes = {
                        self.get_biome_tile(x, y)
                        for y in range(local_y, local_y + layout_h)
                        for x in range(local_x, local_x + layout_w)
                    }
                    if not footprint_biomes.intersection({1, 2}):
                        continue
                    center = (local_x + layout_w // 2, local_y + layout_h // 2)
                    distance = min(self._distance_tiles(center, shore) for shore in shore_tiles)
                    candidates.append((distance, local_y, local_x, layout_name, offsets))
        if not candidates:
            return []

        rng = random.Random(self._stable_seed(world_seed, "coastal-market", self.coord))
        best_distance = min(candidate[0] for candidate in candidates)
        nearest = [candidate for candidate in candidates if candidate[0] <= best_distance + 2]
        _, market_y, market_x, layout_name, stall_offsets = rng.choice(nearest)
        market_id = f"market:{self.coord}:{market_x}:{market_y}"
        records = []
        for index, stall_kind in enumerate(MARKET_STALL_KINDS):
            offset_x, offset_y = stall_offsets[index]
            stall_x = market_x + offset_x
            stall_y = market_y + offset_y
            world_tile_x, world_tile_y = self.get_world_tile(stall_x, stall_y)
            center_world_x = (world_tile_x + stall_w / 2) * self.tile_size
            stall_bottom = (world_tile_y + stall_h) * self.tile_size
            record = {
                "type": "market_stall",
                "id": f"{market_id}:stall:{index}",
                "market_id": market_id,
                "layout": layout_name,
                "stall_kind": stall_kind,
                "chunk": self.coord,
                "local_tile": (stall_x, stall_y),
                "world_tile": (world_tile_x, world_tile_y),
                "world_pos": (center_world_x, stall_bottom),
                "merchant_world_pos": (
                    center_world_x,
                    (world_tile_y + 1.42) * self.tile_size,
                ),
                "visitor_world_pos": (
                    center_world_x,
                    (world_tile_y + stall_h + 1) * self.tile_size,
                ),
                "rest_world_pos": (
                    center_world_x,
                    world_tile_y * self.tile_size,
                ),
                "footprint": MARKET_STALL_FOOTPRINT,
            }
            records.append(record)
            self.props.append(record)
            for y in range(stall_y, stall_y + stall_h):
                for x in range(stall_x, stall_x + stall_w):
                    self.set_decoration_tile(
                        x,
                        y,
                        {"type": "market_stall", "id": record["id"]},
                    )
            for x in range(stall_x, stall_x + stall_w):
                self.set_collision_tile(x, stall_y + stall_h - 1, 1)

        self.metadata["market_count"] = 1
        self.metadata["market_stall_count"] = len(records)
        self.metadata["market_id"] = market_id
        self.mark_dirty()
        return records

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
        door_rect = tuple(get_house_door_rect(asset))
        door_world_x = world_x + door_rect[0] + door_rect[2] // 2
        door_world_y = world_y + door_rect[1] + door_rect[3]
        footprint = get_house_footprint_tiles(asset, self.tile_size)
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
        required_scene_names: tuple[str, ...] = (),
    ) -> list[dict]:
        if clear_existing:
            self.props = [
                prop
                for prop in self.props
                if not (
                    isinstance(prop, dict)
                    and (
                        (prop.get("type") == "house" and not prop.get("dock_house"))
                        or (prop.get("type") == "tree" and prop.get("scene_id"))
                        or (prop.get("type") == "environment" and prop.get("scene_id"))
                        or prop.get("type") in {"animal", "animal_pen"}
                    )
                )
            ]
            self.metadata.pop("scene_count", None)
            self.metadata.pop("house_scene", None)
            self.metadata.pop("house_scenes", None)
            self.metadata.pop("animal_count", None)
            self.metadata.pop("animal_pen_count", None)
            self.runtime["animal_objects"] = {}
            self.runtime.pop("_animal_objects_cache", None)

        width, height = self.chunk_size
        rng = random.Random(self._stable_seed(world_seed, "house-scenes", self.coord))
        generated: list[dict] = []
        placed_scene_names: list[str] = []
        used_scene_names: set[str] = set()
        prefer_coastal = self._chunk_has_coast()
        required_templates = [
            next(
                template
                for template in HOUSE_SCENE_TEMPLATES
                if template.get("name") == required_name
            )
            for required_name in dict.fromkeys(required_scene_names)
        ]
        attempts = 0
        max_attempts = SCENES_PER_CHUNK * 10

        while self.metadata.get("scene_count", 0) < SCENES_PER_CHUNK and len(generated) < houses_per_chunk:
            attempts += 1
            if attempts > max_attempts:
                break

            template = (
                required_templates[0]
                if required_templates
                else self._weighted_scene_template(
                    rng,
                    used_scene_names,
                    prefer_coastal=prefer_coastal,
                )
            )
            scene_w, scene_h = self._scene_template_bounds(template)
            is_coastal_scene = bool(set(template.get("tags", set())) & COASTAL_SCENE_TAGS)
            candidates = [
                (local_x, local_y)
                for local_y in range(1, max(2, height - scene_h))
                for local_x in range(1, max(2, width - scene_w))
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
            scene_houses: list[tuple[dict, int, int, int, int]] = []
            reserved_yards: list[tuple[int, int, int, int]] = []
            for house_index, house in enumerate(template.get("houses", [])):
                category = house.get("category", "primary")
                asset = self._choose_scene_house_asset(rng, category, house.get("prefer"))
                footprint_w, footprint_h = get_house_footprint_tiles(asset, self.tile_size)
                preferred_x = local_x + house["offset"][0]
                preferred_y = local_y + house["offset"][1]
                margin_order = list(HOUSE_YARD_MARGINS)
                rng.shuffle(margin_order)
                yard_position = None
                yard_margin = margin_order[0]
                for candidate_margin in margin_order:
                    yard_position = self._find_house_yard_position(
                        preferred_x,
                        preferred_y,
                        footprint_w,
                        footprint_h,
                        candidate_margin,
                        reserved_yards,
                    )
                    if yard_position is not None:
                        yard_margin = candidate_margin
                        break
                if yard_position is None:
                    continue
                house_local_x, house_local_y = yard_position
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
                self._configure_house_yard(record, yard_margin)
                reserved_yards.append(tuple(record["yard_rect"]))
                scene_houses.append((record, house_local_x, house_local_y, footprint_w, footprint_h))

            if not scene_houses:
                continue

            for record, house_local_x, house_local_y, footprint_w, footprint_h in scene_houses:
                self._mark_house_area(house_local_x, house_local_y, footprint_w, footprint_h, record["id"])
                self._place_house_yard_fence(record, scene_id)
                self.props.append(record)
                generated.append(record)

            self._place_house_yard_props(
                template,
                scene_id,
                [record for record, *_ in scene_houses],
                rng,
            )
            if template.get("name") == "farmstead":
                self._place_scene_animal_pen(template, scene_id, local_x, local_y, rng)
            self._place_scene_farm_plots(template, local_x, local_y)

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
            if required_templates and template["name"] == required_templates[0]["name"]:
                required_templates.pop(0)

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

    def _choose_environment_prop(
        self,
        local_x: int,
        local_y: int,
        rng: random.Random,
        world_seed: int = 0,
    ):
        terrain_value = self.get_terrain_tile(local_x, local_y)
        if terrain_value is None or terrain_value < 0:
            return None

        biome_name = self._resolve_biome_name(self.get_biome_tile(local_x, local_y))
        if isinstance(self.get_biome_tile(local_x, local_y), int):
            biome_name = {
                0: "ocean",
                1: "coast",
                2: "beach",
                3: "grassland_and_forest",
                4: "underwater",
                6: "dryland",
                7: "desert",
                9: "mountain",
            }.get(self.get_biome_tile(local_x, local_y), str(self.get_biome_tile(local_x, local_y)))

        tile_type = self._terrain_to_tile_type(local_x, local_y)
        near_water = self._is_near_water(local_x, local_y)
        roll = rng.random()

        if biome_name == "grassland_and_forest":
            world_x, world_y = self.get_world_tile(local_x, local_y)
            biome_id = self.get_biome_tile(local_x, local_y)
            if is_weed_patch_tile(world_seed, world_x, world_y, biome_id):
                return ("weed", "", "thickets/weeds", False, 0)
            if roll < 0.62:
                variant = "big" if rng.random() < 0.45 else "small"
                return ("bush", variant, f"thickets/bushes/{variant}", False, 0)
            if roll < 0.88:
                return ("flower", "", "flowers", False, 0)
            if roll < 0.97:
                variant = "big" if rng.random() < 0.25 else "small"
                return ("rock", variant, f"rocks/{variant}", True, 6 if variant == "big" else 3)
            return None

        if tile_type == "sand" and near_water:
            if roll < 0.48:
                return ("shell", "", "shells", False, 0)
            if roll < 0.92:
                return ("weed", "", "thickets/weeds", False, 0)
            if roll < 0.98:
                return ("rock", "small", "rocks/small", True, 3)
            return None

        if biome_name == "grassland_and_forest":
            if roll < 0.60:
                variant = "big" if rng.random() < 0.45 else "small"
                return ("bush", variant, f"thickets/bushes/{variant}", False, 0)
            if roll < 0.82:
                return ("weed", "", "thickets/weeds", False, 0)
            if roll < 0.94:
                return ("flower", "", "flowers", False, 0)
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
                    and not prop.get("pathside")
                )
            ]

        width, height = self.chunk_size
        rng = random.Random(self._stable_seed(world_seed, "environment", self.coord))
        reserved_walkways = self._reserved_yard_walkways()
        candidates = [
            (local_x, local_y)
            for local_y in range(height)
            for local_x in range(width)
            if self.in_bounds(local_x, local_y)
            and (local_x, local_y) not in reserved_walkways
        ]
        rng.shuffle(candidates)

        generated = []
        for local_x, local_y in candidates:
            if len(generated) >= max_props:
                break
            idx = self.get_index(local_x, local_y)
            if self.layers["path"][idx] != 0:
                continue
            if self.layers["decoration"][idx] is not None:
                continue
            if self.layers["collision"][idx] != 0:
                continue

            choice = self._choose_environment_prop(local_x, local_y, rng, world_seed)
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
        reserved_walkways = self._reserved_yard_walkways()
        placed_tiles: list[tuple[int, int]] = []
        generated: list[dict] = []

        for local_y in range(height):
            for local_x in range(width):
                if (local_x, local_y) in reserved_walkways:
                    continue
                idx = self.get_index(local_x, local_y)
                if self.layers["path"][idx] != 0:
                    continue
                if self.layers["decoration"][idx] is not None:
                    continue
                if self.layers["collision"][idx] != 0:
                    continue
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

    def replenish_natural_resources(
        self,
        world_seed: int = 0,
        *,
        minimum_weeds: int = 8,
        minimum_bushes: int = 0,
        minimum_trees: int = 6,
        max_new: int = 1,
    ) -> int:
        """Slowly add weeds, bushes, and living trees back to free tiles."""
        living_weeds = [
            prop
            for prop in self.props
            if isinstance(prop, dict)
            and prop.get("type") == "environment"
            and prop.get("prop_type") == "weed"
            and not prop.get("removed", False)
        ]
        living_trees = [
            prop
            for prop in self.props
            if isinstance(prop, dict)
            and prop.get("type") == "tree"
            and not prop.get("removed", False)
            and int(prop.get("health", 1)) > 0
        ]
        living_bushes = [
            prop
            for prop in self.props
            if isinstance(prop, dict)
            and prop.get("type") == "environment"
            and prop.get("prop_type") == "bush"
            and not prop.get("removed", False)
        ]
        weed_needed = max(0, min(max_new, minimum_weeds - len(living_weeds)))
        bush_needed = max(0, min(max_new, minimum_bushes - len(living_bushes)))
        tree_needed = max(0, min(max_new, minimum_trees - len(living_trees)))
        if weed_needed == 0 and bush_needed == 0 and tree_needed == 0:
            return 0

        counter = int(self.save_data["flags"].get("ecology_spawn_counter", 0))
        starting_counter = counter
        rng = random.Random(
            self._stable_seed(world_seed, "ecology_replenish", self.coord, counter)
        )
        width, height = self.chunk_size
        reserved_walkways = self._reserved_yard_walkways()
        candidates = [
            (x, y)
            for y in range(height)
            for x in range(width)
            if (x, y) not in reserved_walkways
        ]
        rng.shuffle(candidates)

        def is_free(local_x, local_y):
            index = self.get_index(local_x, local_y)
            return (
                self.layers["terrain"][index] >= 0
                and self.layers["collision"][index] == 0
                and self.layers["decoration"][index] is None
                and self.layers["path"][index] == 0
                and self.layers["fence"][index] == 0
                and self.layers["dock"][index] is None
                and self.layers["soil"][index] == 0
                and self.layers["plant"][index] is None
            )

        biome_lookup = {
            0: "ocean", 1: "coast", 2: "beach",
            3: "grassland_and_forest", 4: "underwater", 6: "dryland",
            7: "desert", 9: "mountain",
        }

        spawned = 0
        weed_assets = list_environment_assets("thickets", "weeds")
        weed_biomes = {
            "coast", "beach", "grassland_and_forest",
            "dryland",
        }
        if weed_needed and weed_assets:
            for local_x, local_y in candidates:
                if weed_needed <= 0:
                    break
                if not is_free(local_x, local_y):
                    continue
                biome_value = self.get_biome_tile(local_x, local_y)
                biome_name = biome_lookup.get(biome_value, self._resolve_biome_name(biome_value))
                if biome_name not in weed_biomes:
                    continue
                world_x, world_y = self.get_world_tile(local_x, local_y)
                if (
                    biome_name == "grassland_and_forest"
                    and is_grass_patch_tile(
                        world_seed,
                        world_x,
                        world_y,
                        biome_value,
                    )
                ):
                    continue
                world_tile = self.get_world_tile(local_x, local_y)
                prop_id = f"ecology:{self.coord}:{counter}:weed"
                record = {
                    "type": "environment",
                    "id": prop_id,
                    "prop_type": "weed",
                    "variant": "",
                    "asset": rng.choice(weed_assets),
                    "chunk": self.coord,
                    "local_tile": (local_x, local_y),
                    "world_tile": world_tile,
                    "world_pos": self.get_world_pos(local_x, local_y),
                    "blocks_movement": False,
                    "health": 0,
                    "scale": 2,
                    "regrown": True,
                }
                self.props.append(record)
                self.save_data["placed_props"].append(record)
                self.set_saved_tile(
                    "decoration",
                    local_x,
                    local_y,
                    {"type": "environment", "id": prop_id, "prop_type": "weed"},
                )
                counter += 1
                weed_needed -= 1
                spawned += 1

        bush_assets = {
            variant: list_environment_assets("thickets", "bushes", variant)
            for variant in ("small", "big")
        }
        bush_biomes = {"grassland_and_forest"}
        if bush_needed and spawned < max_new and any(bush_assets.values()):
            for local_x, local_y in candidates:
                if bush_needed <= 0 or spawned >= max_new:
                    break
                if not is_free(local_x, local_y):
                    continue
                biome_value = self.get_biome_tile(local_x, local_y)
                biome_name = biome_lookup.get(biome_value, self._resolve_biome_name(biome_value))
                if biome_name not in bush_biomes:
                    continue
                variant = "big" if rng.random() < 0.4 else "small"
                assets = bush_assets[variant]
                if not assets:
                    continue
                world_tile = self.get_world_tile(local_x, local_y)
                prop_id = f"ecology:{self.coord}:{counter}:bush"
                record = {
                    "type": "environment",
                    "id": prop_id,
                    "prop_type": "bush",
                    "variant": variant,
                    "asset": rng.choice(assets),
                    "chunk": self.coord,
                    "local_tile": (local_x, local_y),
                    "world_tile": world_tile,
                    "world_pos": self.get_world_pos(local_x, local_y),
                    "blocks_movement": False,
                    "health": 0,
                    "scale": 2,
                    "regrown": True,
                }
                self.props.append(record)
                self.save_data["placed_props"].append(record)
                self.set_saved_tile(
                    "decoration",
                    local_x,
                    local_y,
                    {"type": "environment", "id": prop_id, "prop_type": "bush"},
                )
                counter += 1
                bush_needed -= 1
                spawned += 1

        placed_tree_tiles = [
            tuple(prop.get("local_tile"))
            for prop in self.props
            if isinstance(prop, dict)
            and prop.get("type") == "tree"
            and prop.get("local_tile") is not None
        ]
        if tree_needed and spawned < max_new:
            for local_x, local_y in candidates:
                if tree_needed <= 0 or spawned >= max_new:
                    break
                if not is_free(local_x, local_y):
                    continue
                biome_value = self.get_biome_tile(local_x, local_y)
                biome_name = biome_lookup.get(biome_value, self._resolve_biome_name(biome_value))
                moisture = float(self.get_moisture_tile(local_x, local_y) or 0.0)
                elevation = float(self.get_elevation_tile(local_x, local_y) or 0.0)
                fertility = max(0.0, min(1.0, moisture * 0.7 + (1.0 - elevation) * 0.3))
                tree_data = generate_tree_instance(
                    biome_name=biome_name,
                    moisture=moisture,
                    elevation=elevation,
                    temperature=max(0.0, min(1.0, 1.0 - elevation * 0.35)),
                    fertility=fertility,
                    density_noise=rng.random(),
                    tile_type=self._terrain_to_tile_type(local_x, local_y),
                    near_water=self._is_near_water(local_x, local_y),
                    rng=rng,
                )
                if tree_data is None or not self._can_place_tree(
                    local_x, local_y, tree_data["min_spacing"], placed_tree_tiles
                ):
                    continue
                world_tile = self.get_world_tile(local_x, local_y)
                record = {
                    **tree_data,
                    "id": f"ecology:{self.coord}:{counter}:tree",
                    "chunk": self.coord,
                    "local_tile": (local_x, local_y),
                    "world_tile": world_tile,
                    "world_pos": self.get_world_pos(local_x, local_y),
                    "biome": biome_name,
                    "near_water": self._is_near_water(local_x, local_y),
                    "regrown": True,
                }
                self.props.append(record)
                self.save_data["placed_props"].append(record)
                self.set_saved_tile(
                    "decoration",
                    local_x,
                    local_y,
                    {"type": "tree", "species": record["species"]},
                )
                if record.get("blocks_movement", True):
                    self.set_saved_tile("collision", local_x, local_y, 1)
                placed_tree_tiles.append((local_x, local_y))
                counter += 1
                tree_needed -= 1
                spawned += 1

        self.save_data["flags"]["ecology_spawn_counter"] = max(
            counter, starting_counter + 1
        )
        if spawned:
            self.runtime["environment_objects"] = {}
            self.runtime["tree_objects"] = {}
            self.runtime.pop("_environment_objects_cache", None)
            self.runtime.pop("_tree_objects_cache", None)
            self.mark_dirty()
        return spawned
