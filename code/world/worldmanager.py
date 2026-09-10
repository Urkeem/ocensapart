"""World manager for island-level loading, biome data, and coordinate conversion."""

from collections import deque
from dataclasses import dataclass
import hashlib
import math
import random
from world.chunkmanager import Chunk
from world.cellular_automata import CellularAutomata
from world.biome_visuals import SUBDIVIDED_GRASS_TILESET


# Biome ids
BIOME_OCEAN = 0
BIOME_COAST = 1
BIOME_BEACH = 2
BIOME_GRASSLAND_AND_FOREST = 3
BIOME_UNDERWATER = 4
BIOME_DRYLAND = 6
BIOME_DESERT = 7
BIOME_MOUNTAIN = 9

# Ten chunks leave enough interior room for a guaranteed river while retaining
# an ocean margin around the expanded land mass.
ISLAND_SIZE_CHUNKS = 10
ISLAND_LAND_RADIUS_CHUNKS = 4
ISLAND_WATER_MARGIN_CHUNKS = 1
ISLAND_RADIUS_CHUNKS = ISLAND_LAND_RADIUS_CHUNKS + ISLAND_WATER_MARGIN_CHUNKS
UNDERWATER_BIOME_WIDTH = 5
MOUNTAIN_EXPANSION_RADIUS = 2
MOUNTAIN_BLOCK_SIZE = 2

# Handy lookup table for rendering / debugging / future rules
BIOME_TABLE = {
    BIOME_OCEAN: {
        "name": "ocean",
        "tileset": "Tilesets/ocean.png",
        "color": (255, 255, 255),
    },
    BIOME_COAST: {
        "name": "coast",
        "tileset": "Tilesets/coast.png",
        "color": (80, 140, 190),
    },
    BIOME_BEACH: {
        "name": "beach",
        "tileset": "Tilesets/beach.png",
        "color": (214, 198, 120),
    },
    BIOME_GRASSLAND_AND_FOREST: {
        "name": "grassland_and_forest",
        "tileset": SUBDIVIDED_GRASS_TILESET,
        "color": (90, 170, 80),
    },
    BIOME_UNDERWATER: {
        "name": "underwater",
        "tileset": "Tilesets/under_water.png",
        "source_tile_size": 16,
        "color": (72, 142, 170),
    },
    BIOME_DRYLAND: {
        "name": "dryland",
        "tileset": "Tilesets/land.png",
        "color": (160, 150, 90),
    },
    BIOME_DESERT: {
        "name": "desert",
        "tileset": "Tilesets/desert.png",
        "color": (215, 185, 100),
    },
    BIOME_MOUNTAIN: {
        "name": "mountain",
        "tileset": "Tilesets/cliff.png",
        "source_tile_size": 64,
        "color": (140, 140, 140),
    },
}

# Every land biome receives one small stable core. The underwater biome is
# guaranteed by the generated ring outside the shoreline rather than a core.
GUARANTEED_BIOME_LAYOUT = (
    (BIOME_COAST, 0.76, 0.00),
    (BIOME_BEACH, 0.76, 0.50),
    (BIOME_GRASSLAND_AND_FOREST, 0.00, 0.00),
    (BIOME_DRYLAND, 0.42, 0.25),
    (BIOME_DESERT, 0.42, 0.42),
    (BIOME_MOUNTAIN, 0.42, 0.67),
)


def stable_seed(*parts: object) -> int:
    digest = hashlib.sha256("|".join(map(str, parts)).encode("utf-8")).hexdigest()
    return int(digest[:16], 16)


@dataclass(frozen=True)
class IslandLevel:
    index: int
    seed: int
    radius_chunks: int
    difficulty: int
    name: str


class WorldRun:
    """Tracks the island chain for one playthrough."""

    def __init__(self, seed: int = 0, start_index: int = 1):
        self.seed = seed
        self.current_index = start_index
        self.discovered_islands: set[int] = set()

    def get_island(self, index: int | None = None) -> IslandLevel:
        island_index = self.current_index if index is None else index
        island_seed = stable_seed(self.seed, "island", island_index) & 0xffffffff
        radius_chunks = ISLAND_RADIUS_CHUNKS
        return IslandLevel(
            index=island_index,
            seed=island_seed,
            radius_chunks=radius_chunks,
            difficulty=max(1, island_index),
            name=f"Island {island_index}",
        )

    def create_world(
        self,
        *,
        spawn_chunk: tuple[int, int],
        chunk_size: tuple[int, int],
        active_radius: int,
        tile_size: int,
    ) -> "World":
        island = self.get_island()
        self.discovered_islands.add(island.index)
        return World(
            seed=island.seed,
            spawn_chunk=spawn_chunk,
            chunk_size=chunk_size,
            active_radius=active_radius,
            tile_size=tile_size,
            island=island,
        )

    def advance(self) -> IslandLevel:
        self.current_index += 1
        return self.get_island()


class World:
    def __init__(
        self,
        seed: int = 0,
        spawn_chunk: tuple[int, int] = (0, 0),
        chunk_size: tuple[int, int] = (32, 32),
        active_radius: int = 2,
        tile_size: int = 16,
        island: IslandLevel | None = None,
    ):
        self.seed = seed
        self.spawn_chunk = spawn_chunk
        self.chunk_size = chunk_size
        self.active_radius = active_radius
        self.tile_size = tile_size
        self.island = island or IslandLevel(
            index=1,
            seed=seed,
            radius_chunks=ISLAND_RADIUS_CHUNKS,
            difficulty=1,
            name="Island 1",
        )

        self.ca_steps = 4
        self.wall_chance = 0.54
        self.ca_cutoff = (3, 5)
        self.island_shoreline = 0.82
        self.land_radius_chunks = min(
            ISLAND_LAND_RADIUS_CHUNKS,
            self.island.radius_chunks,
        )
        self.farmstead_chunks = self._choose_farmstead_chunks()
        river_rng = random.Random(stable_seed(self.seed, "river", self.island.index))
        self.river_phase = river_rng.random() * math.tau
        river_candidates = [
            (direction, cross_fraction)
            for direction in range(4)
            for cross_fraction in (-0.50, -0.35, 0.35, 0.50)
        ]
        river_rng.shuffle(river_candidates)
        self.river_direction, self.river_cross_fraction = max(
            river_candidates,
            key=lambda candidate: self._river_farmstead_clearance(*candidate),
        )
        self._water_locality_cache: dict[tuple[int, int], str] = {}

        self.loaded_chunks: dict[tuple[int, int], Chunk] = {}
        self.saved_chunk_states: dict[tuple[int, int], dict] = {}
        self.active_chunks: set[tuple[int, int]] = set()
        self.current_player_chunk: tuple[int, int] | None = None
        self.exit_chunk = self._choose_exit_chunk()
        # Adjacent value-noise samples reuse the same grid corners thousands of
        # times. Cache the deterministic result without changing seed behavior.
        self._field_random_cache: dict[tuple[int, int, int], float] = {}
        self.biome_core_radius = max(3, min(self.chunk_size) // 5)
        self.biome_core_centers = self._build_biome_core_centers()

    @property
    def level_name(self) -> str:
        return self.island.name

    def _choose_exit_chunk(self) -> tuple[int, int]:
        rng = random.Random(stable_seed(self.seed, "exit", self.island.index))
        low_offset = -(ISLAND_SIZE_CHUNKS // 2)
        high_offset = low_offset + ISLAND_SIZE_CHUNKS - 1
        edge = rng.choice(("north", "south", "east", "west"))
        offset = rng.randint(-2, 2)
        if edge == "north":
            return self.spawn_chunk[0] + offset, self.spawn_chunk[1] + low_offset
        if edge == "south":
            return self.spawn_chunk[0] + offset, self.spawn_chunk[1] + high_offset
        if edge == "east":
            return self.spawn_chunk[0] + high_offset, self.spawn_chunk[1] + offset
        return self.spawn_chunk[0] + low_offset, self.spawn_chunk[1] + offset

    def _choose_farmstead_chunks(self) -> tuple[tuple[int, int], ...]:
        """Select three reproducible interior chunks for guaranteed farms."""
        center_x, center_y = self.spawn_chunk
        interior_radius = max(1, min(2, self.land_radius_chunks - 1))
        ring_offsets = (
            (0, -interior_radius),
            (interior_radius, -1),
            (interior_radius, 1),
            (0, interior_radius),
            (-interior_radius, 1),
            (-interior_radius, -1),
        )
        rotation = stable_seed(self.seed, "guaranteed-farmsteads") % len(ring_offsets)
        selected_offsets = tuple(
            ring_offsets[(rotation + step) % len(ring_offsets)]
            for step in (0, 2, 4)
        )
        return tuple(
            (center_x + offset_x, center_y + offset_y)
            for offset_x, offset_y in selected_offsets
        )

    def is_chunk_in_level_bounds(self, chunk_coord: tuple[int, int]) -> bool:
        cx, cy = self.spawn_chunk
        x, y = chunk_coord
        low_offset = -(ISLAND_SIZE_CHUNKS // 2)
        high_offset = low_offset + ISLAND_SIZE_CHUNKS
        return low_offset <= x - cx < high_offset and low_offset <= y - cy < high_offset

    def get_level_chunk_coords(self) -> set[tuple[int, int]]:
        cx, cy = self.spawn_chunk
        low_offset = -(ISLAND_SIZE_CHUNKS // 2)
        high_offset = low_offset + ISLAND_SIZE_CHUNKS
        return {
            (cx + dx, cy + dy)
            for dy in range(low_offset, high_offset)
            for dx in range(low_offset, high_offset)
        }

    def get_chunks_near(self, center_chunk: tuple[int, int], radius: int = 1) -> set[tuple[int, int]]:
        cx, cy = center_chunk
        return {
            coord
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
            if self.is_chunk_in_level_bounds(coord := (cx + dx, cy + dy))
        }

    def get_spawn_position(self) -> tuple[int, int]:
        chunk_x, chunk_y = self.spawn_chunk
        chunk_w, chunk_h = self.chunk_size

        world_x = (chunk_x * chunk_w + chunk_w // 2) * self.tile_size
        world_y = (chunk_y * chunk_h + chunk_h // 2) * self.tile_size
        return world_x, world_y

    def world_to_chunk(self, world_pos: tuple[int, int]) -> tuple[int, int]:
        world_x, world_y = world_pos
        chunk_pixel_w = self.chunk_size[0] * self.tile_size
        chunk_pixel_h = self.chunk_size[1] * self.tile_size

        chunk_x = world_x // chunk_pixel_w
        chunk_y = world_y // chunk_pixel_h
        return chunk_x, chunk_y

    def chunk_to_world_bounds(self, chunk_coord: tuple[int, int]) -> tuple[int, int, int, int]:
        chunk_x, chunk_y = chunk_coord
        chunk_pixel_w = self.chunk_size[0] * self.tile_size
        chunk_pixel_h = self.chunk_size[1] * self.tile_size

        left = chunk_x * chunk_pixel_w
        top = chunk_y * chunk_pixel_h
        right = left + chunk_pixel_w
        bottom = top + chunk_pixel_h
        return left, top, right, bottom

    def _crop_center(
        self,
        source_map: list,
        source_dim: tuple[int, int],
        target_dim: tuple[int, int],
        pad: int
    ) -> list:
        source_w, _ = source_dim
        target_w, target_h = target_dim

        cropped = []
        for y in range(target_h):
            for x in range(target_w):
                sx = x + pad
                sy = y + pad
                cropped.append(source_map[sy * source_w + sx])
        return cropped

    def _world_tile_random(self, world_tile_x: int, world_tile_y: int) -> float:
        local_seed = stable_seed(self.seed, "tile", world_tile_x, world_tile_y) & 0xffffffff
        rng = random.Random(local_seed)
        return rng.random()

    def _world_field_random(self, field_seed: int, x: int, y: int) -> float:
        key = (field_seed, x, y)
        cached = self._field_random_cache.get(key)
        if cached is not None:
            return cached

        local_seed = stable_seed(self.seed, "field", field_seed, x, y) & 0xffffffff
        value = random.Random(local_seed).random()
        self._field_random_cache[key] = value
        return value

    def _sample_value_noise(self, field_seed: int, world_x: int, world_y: int, scale: int) -> float:
        scale = max(1, scale)
        grid_x = math.floor(world_x / scale)
        grid_y = math.floor(world_y / scale)
        local_x = (world_x / scale) - grid_x
        local_y = (world_y / scale) - grid_y

        sx = local_x * local_x * (3.0 - 2.0 * local_x)
        sy = local_y * local_y * (3.0 - 2.0 * local_y)

        top_left = self._world_field_random(field_seed, grid_x, grid_y)
        top_right = self._world_field_random(field_seed, grid_x + 1, grid_y)
        bottom_left = self._world_field_random(field_seed, grid_x, grid_y + 1)
        bottom_right = self._world_field_random(field_seed, grid_x + 1, grid_y + 1)

        top = top_left + (top_right - top_left) * sx
        bottom = bottom_left + (bottom_right - bottom_left) * sx
        return top + (bottom - top) * sy

    def _sample_island_distance(self, world_x: int, world_y: int) -> float:
        chunk_w, chunk_h = self.chunk_size
        center_x = self.spawn_chunk[0] * chunk_w + chunk_w // 2
        center_y = self.spawn_chunk[1] * chunk_h + chunk_h // 2
        radius_x = max(1, self.land_radius_chunks * chunk_w)
        radius_y = max(1, self.land_radius_chunks * chunk_h)
        dx = (world_x - center_x) / radius_x
        dy = (world_y - center_y) / radius_y
        return (dx * dx + dy * dy) ** 0.5

    def _river_axis_coordinates(self, world_x: int, world_y: int) -> tuple[float, float]:
        """Return distance along and across this island's cardinal river."""
        chunk_w, chunk_h = self.chunk_size
        center_x = self.spawn_chunk[0] * chunk_w + chunk_w // 2
        center_y = self.spawn_chunk[1] * chunk_h + chunk_h // 2
        relative_x = world_x - center_x
        relative_y = world_y - center_y
        direction_x, direction_y = (
            (1, 0),
            (0, 1),
            (-1, 0),
            (0, -1),
        )[self.river_direction]
        perpendicular_x, perpendicular_y = -direction_y, direction_x
        along = relative_x * direction_x + relative_y * direction_y
        across = relative_x * perpendicular_x + relative_y * perpendicular_y
        return along, across

    def _river_farmstead_clearance(self, direction: int, cross_fraction: float) -> float:
        """Score a river profile by its closest approach to a farmstead core."""
        chunk_w, chunk_h = self.chunk_size
        center_x = self.spawn_chunk[0] * chunk_w + chunk_w // 2
        center_y = self.spawn_chunk[1] * chunk_h + chunk_h // 2
        radius = max(1.0, self.land_radius_chunks * min(chunk_w, chunk_h))
        direction_x, direction_y = ((1, 0), (0, 1), (-1, 0), (0, -1))[direction]
        perpendicular_x, perpendicular_y = -direction_y, direction_x
        clearances = []
        for farm_chunk_x, farm_chunk_y in self.farmstead_chunks:
            farm_x = farm_chunk_x * chunk_w + chunk_w // 2
            farm_y = farm_chunk_y * chunk_h + chunk_h // 2
            relative_x = farm_x - center_x
            relative_y = farm_y - center_y
            along = relative_x * direction_x + relative_y * direction_y
            if not radius * 0.12 <= along <= radius * 1.12:
                continue
            across = relative_x * perpendicular_x + relative_y * perpendicular_y
            progress = (along - radius * 0.12) / radius
            centerline = (
                radius * cross_fraction
                + math.sin(progress * math.tau * 1.35 + self.river_phase) * radius * 0.07
            )
            clearances.append(abs(across - centerline))
        return min(clearances, default=radius)

    def is_river_tile(self, world_x: int, world_y: int) -> bool:
        """Return whether a tile belongs to the guaranteed island river."""
        chunk_w, chunk_h = self.chunk_size
        radius = max(1.0, self.land_radius_chunks * min(chunk_w, chunk_h))
        along, across = self._river_axis_coordinates(world_x, world_y)
        source = radius * 0.12
        mouth = radius * 1.12
        if not source <= along <= mouth:
            return False

        progress = (along - source) / max(1.0, mouth - source)
        centerline = (
            radius * self.river_cross_fraction
            + math.sin(progress * math.tau * 1.35 + self.river_phase) * radius * 0.07
        )
        half_width = max(1.25, min(chunk_w, chunk_h) * 0.075)
        return abs(across - centerline) <= half_width

    def get_water_locality(self, world_tile: tuple[int, int]) -> str | None:
        """Classify a generated water tile as ocean, pond, or river."""
        if world_tile is None:
            return None
        world_x, world_y = map(int, world_tile)
        chunk_w, chunk_h = self.chunk_size
        chunk_coord = (world_x // chunk_w, world_y // chunk_h)
        chunk = self.loaded_chunks.get(chunk_coord)
        if chunk is None or not self.is_chunk_in_level_bounds(chunk_coord):
            return None
        local_x = world_x % chunk_w
        local_y = world_y % chunk_h
        idx = chunk.get_index(local_x, local_y)
        if chunk.layers["terrain"][idx] != -1:
            return None
        if self.is_river_tile(world_x, world_y):
            return "river"

        cached = self._water_locality_cache.get((world_x, world_y))
        if cached is not None:
            return cached

        # Flood-fill the loaded water body. Components that reach outside the
        # 10x10 level are ocean; fully enclosed components are ponds.
        pending = deque([(world_x, world_y)])
        visited = {(world_x, world_y)}
        reaches_ocean = False
        incomplete = False
        while pending:
            tile_x, tile_y = pending.popleft()
            for neighbor in (
                (tile_x - 1, tile_y),
                (tile_x + 1, tile_y),
                (tile_x, tile_y - 1),
                (tile_x, tile_y + 1),
            ):
                if neighbor in visited:
                    continue
                neighbor_chunk_coord = (neighbor[0] // chunk_w, neighbor[1] // chunk_h)
                if not self.is_chunk_in_level_bounds(neighbor_chunk_coord):
                    reaches_ocean = True
                    continue
                neighbor_chunk = self.loaded_chunks.get(neighbor_chunk_coord)
                if neighbor_chunk is None:
                    incomplete = True
                    continue
                neighbor_idx = neighbor_chunk.get_index(
                    neighbor[0] % chunk_w,
                    neighbor[1] % chunk_h,
                )
                if neighbor_chunk.layers["terrain"][neighbor_idx] != -1:
                    continue
                visited.add(neighbor)
                pending.append(neighbor)

        if reaches_ocean:
            locality = "ocean"
        elif not incomplete:
            locality = "pond"
        else:
            # During partial loading, use position as a temporary fallback and
            # leave the result uncached so full-island loading can refine it.
            return (
                "pond"
                if self._sample_island_distance(world_x, world_y) < self.island_shoreline * 0.82
                else "ocean"
            )

        for tile in visited:
            if not self.is_river_tile(*tile):
                self._water_locality_cache[tile] = locality
        return locality

    def _build_biome_core_centers(self) -> tuple[tuple[int, int, int], ...]:
        chunk_w, chunk_h = self.chunk_size
        center_x = self.spawn_chunk[0] * chunk_w + chunk_w // 2
        center_y = self.spawn_chunk[1] * chunk_h + chunk_h // 2
        radius_x = max(1, self.land_radius_chunks * chunk_w)
        radius_y = max(1, self.land_radius_chunks * chunk_h)
        rotation = (
            stable_seed(self.seed, "biome-core-rotation") % 360
        ) / 360.0
        centers = []
        for biome_id, radial_distance, turn in GUARANTEED_BIOME_LAYOUT:
            angle = (rotation + turn) * math.tau
            centers.append((
                biome_id,
                round(center_x + math.cos(angle) * radius_x * radial_distance),
                round(center_y + math.sin(angle) * radius_y * radial_distance),
            ))
        return tuple(centers)

    def _guaranteed_biome_at(self, world_x: int, world_y: int) -> int | None:
        if self._is_farmstead_core_tile(world_x, world_y):
            return BIOME_GRASSLAND_AND_FOREST
        radius_squared = self.biome_core_radius * self.biome_core_radius
        for biome_id, center_x, center_y in self.biome_core_centers:
            dx = world_x - center_x
            dy = world_y - center_y
            if dx * dx + dy * dy <= radius_squared:
                return biome_id
        return None

    def _is_farmstead_core_tile(self, world_x: int, world_y: int) -> bool:
        chunk_width, chunk_height = self.chunk_size
        core_radius = max(5, min(chunk_width, chunk_height) // 3)
        for chunk_x, chunk_y in self.farmstead_chunks:
            center_x = chunk_x * chunk_width + chunk_width // 2
            center_y = chunk_y * chunk_height + chunk_height // 2
            if abs(world_x - center_x) <= core_radius and abs(world_y - center_y) <= core_radius:
                return True
        return False

    def _island_edge_noise(self, world_x: int, world_y: int) -> float:
        broad = self._world_field_random(301, world_x // 10, world_y // 10)
        detail = self._world_field_random(302, world_x // 4, world_y // 4)
        return ((broad - 0.5) * 0.22) + ((detail - 0.5) * 0.08)

    def _is_spawn_core_tile(self, world_x: int, world_y: int) -> bool:
        chunk_w, chunk_h = self.chunk_size
        center_x = self.spawn_chunk[0] * chunk_w + chunk_w // 2
        center_y = self.spawn_chunk[1] * chunk_h + chunk_h // 2
        return abs(world_x - center_x) <= 3 and abs(world_y - center_y) <= 3

    def _sample_island_land(self, world_x: int, world_y: int, wall_chance: float) -> int:
        if self._is_spawn_core_tile(world_x, world_y) or self._is_farmstead_core_tile(world_x, world_y):
            return 1
        if self.is_river_tile(world_x, world_y):
            return 0
        if self._guaranteed_biome_at(world_x, world_y) is not None:
            return 1

        distance = self._sample_island_distance(world_x, world_y)
        edge_noise = self._island_edge_noise(world_x, world_y)
        shoreline_limit = 1.0 + edge_noise
        if distance > shoreline_limit:
            return 0

        # Break up the shore while keeping the inland body mostly solid.
        if distance > self.island_shoreline + edge_noise:
            shore_roll = self._world_tile_random(world_x, world_y)
            return 1 if shore_roll < 0.55 else 0

        land_chance = min(0.92, wall_chance + (1.0 - distance) * 0.30)
        return 1 if self._world_tile_random(world_x, world_y) < land_chance else 0

    def _sample_elevation(self, world_x: int, world_y: int) -> float:
        coarse = self._sample_value_noise(101, world_x, world_y, 34)
        medium = self._sample_value_noise(102, world_x, world_y, 13)
        fine = self._sample_value_noise(103, world_x, world_y, 5)

        value = coarse * 0.55 + medium * 0.30 + fine * 0.15
        return max(0.0, min(1.0, value))

    def _sample_moisture(self, world_x: int, world_y: int) -> float:
        coarse = self._sample_value_noise(201, world_x, world_y, 29)
        medium = self._sample_value_noise(202, world_x, world_y, 11)
        fine = self._sample_value_noise(203, world_x, world_y, 4)

        value = coarse * 0.56 + medium * 0.29 + fine * 0.15
        return max(0.0, min(1.0, value))

    def _build_world_space_base_map(
        self,
        chunk_coord: tuple[int, int],
        padded_dim: tuple[int, int],
        pad: int,
        wall_chance: float
    ) -> list[int]:
        chunk_x, chunk_y = chunk_coord
        chunk_w, chunk_h = self.chunk_size
        padded_w, padded_h = padded_dim

        base_map = []

        start_world_x = chunk_x * chunk_w - pad
        start_world_y = chunk_y * chunk_h - pad

        for local_y in range(padded_h):
            for local_x in range(padded_w):
                world_x = start_world_x + local_x
                world_y = start_world_y + local_y

                base_map.append(self._sample_island_land(world_x, world_y, wall_chance))

        return base_map

    def _build_world_space_scalar_layer(
        self,
        chunk_coord: tuple[int, int],
        padded_dim: tuple[int, int],
        pad: int,
        sampler
    ) -> list[float]:
        chunk_x, chunk_y = chunk_coord
        chunk_w, chunk_h = self.chunk_size
        padded_w, padded_h = padded_dim

        values = []

        start_world_x = chunk_x * chunk_w - pad
        start_world_y = chunk_y * chunk_h - pad

        for local_y in range(padded_h):
            for local_x in range(padded_w):
                world_x = start_world_x + local_x
                world_y = start_world_y + local_y
                values.append(sampler(world_x, world_y))

        return values

    def _run_ca_on_map(
        self,
        base_map: list[int],
        dim: tuple[int, int],
        steps: int = 4,
        oob: str = "wall",
        cutoff: tuple[int, int] = (3, 5)
    ) -> list[int]:
        ca = CellularAutomata(
            map_dim=dim,
            wall_chance=self.wall_chance,
            oob=oob,
            cutoff=cutoff,
            rng=random.Random(0)
        )
        ca.map = base_map[:]

        map_data = ca.map[:]
        for _ in range(steps):
            map_data = ca.apply_cellular_automata_rules(map_data)

        return map_data

    def _apply_island_mask(
        self,
        map_data: list[int],
        chunk_coord: tuple[int, int],
        dim: tuple[int, int],
        pad: int,
    ) -> list[int]:
        chunk_x, chunk_y = chunk_coord
        chunk_w, chunk_h = self.chunk_size
        width, height = dim
        start_world_x = chunk_x * chunk_w - pad
        start_world_y = chunk_y * chunk_h - pad
        masked = map_data[:]

        for local_y in range(height):
            for local_x in range(width):
                world_x = start_world_x + local_x
                world_y = start_world_y + local_y
                distance = self._sample_island_distance(world_x, world_y)
                guaranteed_biome = self._guaranteed_biome_at(world_x, world_y)
                if self._is_spawn_core_tile(world_x, world_y) or self._is_farmstead_core_tile(world_x, world_y):
                    masked[local_y * width + local_x] = 1
                elif self.is_river_tile(world_x, world_y):
                    masked[local_y * width + local_x] = 0
                elif guaranteed_biome is not None:
                    masked[local_y * width + local_x] = 1
                elif distance > 1.04 + self._island_edge_noise(world_x, world_y):
                    masked[local_y * width + local_x] = 0

        return masked

    def _build_signed_terrain(self, binary_map: list[int], dim: tuple[int, int]) -> list[int]:
        width, height = dim
        terrain = [0] * (width * height)

        for y in range(height):
            for x in range(width):
                idx = y * width + x
                value = binary_map[idx]

                if value == 0:
                    terrain[idx] = -1
                    continue

                touches_water = False
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        if dx == 0 and dy == 0:
                            continue

                        nx = x + dx
                        ny = y + dy

                        if 0 <= nx < width and 0 <= ny < height:
                            nidx = ny * width + nx
                            if binary_map[nidx] == 0:
                                touches_water = True
                                break
                    if touches_water:
                        break

                terrain[idx] = 0 if touches_water else 1

        return terrain

    def _build_biome_layer(
        self,
        terrain_map: list[int],
        elevation_map: list[float],
        moisture_map: list[float],
        dim: tuple[int, int],
        origin_tile: tuple[int, int] = (0, 0),
    ) -> list[int]:
        width, height = dim
        origin_x, origin_y = origin_tile
        biome = [0] * (width * height)
        water_distances = self._build_water_distance_map(terrain_map, dim, max_distance=6)
        land_distances = self._build_land_distance_map(
            terrain_map,
            dim,
            max_distance=UNDERWATER_BIOME_WIDTH,
        )

        for y in range(height):
            for x in range(width):
                idx = y * width + x

                terrain_value = terrain_map[idx]
                elevation = elevation_map[idx]
                moisture = moisture_map[idx]

                if terrain_value == -1:
                    biome[idx] = (
                        BIOME_UNDERWATER
                        if land_distances[idx] <= UNDERWATER_BIOME_WIDTH
                        else BIOME_OCEAN
                    )
                    continue

                shore_distance = water_distances[idx]
                world_x = origin_x + x
                world_y = origin_y + y
                guaranteed_biome = self._guaranteed_biome_at(world_x, world_y)
                if guaranteed_biome is not None:
                    biome[idx] = guaranteed_biome
                    continue
                if shore_distance <= self._sample_beach_width(world_x, world_y):
                    biome[idx] = BIOME_COAST if moisture >= 0.72 and shore_distance <= 2 else BIOME_BEACH
                    continue

                edge_jitter = (self._sample_value_noise(401, world_x, world_y, 4) - 0.5) * 0.08

                if elevation + edge_jitter >= 0.82:
                    biome[idx] = BIOME_MOUNTAIN
                elif moisture + edge_jitter < 0.18:
                    biome[idx] = BIOME_DESERT
                elif moisture + edge_jitter < 0.35:
                    biome[idx] = BIOME_DRYLAND
                else:
                    biome[idx] = BIOME_GRASSLAND_AND_FOREST

        return self._expand_and_align_mountain_biome(
            biome,
            terrain_map,
            dim,
            origin_tile,
        )

    def _expand_and_align_mountain_biome(
        self,
        biome_map: list[int],
        terrain_map: list[int],
        dim: tuple[int, int],
        origin_tile: tuple[int, int],
    ) -> list[int]:
        """Grow mountains and align them to the 2x2 cells used by 128px art."""
        width, height = dim
        origin_x, origin_y = origin_tile
        protected = {BIOME_OCEAN, BIOME_UNDERWATER, BIOME_COAST, BIOME_BEACH}
        expanded = biome_map[:]
        mountain_tiles = [
            (idx % width, idx // width)
            for idx, biome_id in enumerate(biome_map)
            if biome_id == BIOME_MOUNTAIN
        ]

        for mountain_x, mountain_y in mountain_tiles:
            for offset_y in range(-MOUNTAIN_EXPANSION_RADIUS, MOUNTAIN_EXPANSION_RADIUS + 1):
                for offset_x in range(-MOUNTAIN_EXPANSION_RADIUS, MOUNTAIN_EXPANSION_RADIUS + 1):
                    local_x = mountain_x + offset_x
                    local_y = mountain_y + offset_y
                    if not (0 <= local_x < width and 0 <= local_y < height):
                        continue
                    idx = local_y * width + local_x
                    if terrain_map[idx] >= 0 and expanded[idx] not in protected:
                        expanded[idx] = BIOME_MOUNTAIN

        if width < MOUNTAIN_BLOCK_SIZE or height < MOUNTAIN_BLOCK_SIZE:
            return expanded

        candidate_blocks = set()
        for idx, biome_id in enumerate(expanded):
            if biome_id != BIOME_MOUNTAIN:
                continue
            world_x = origin_x + idx % width
            world_y = origin_y + idx // width
            candidate_blocks.add((
                world_x // MOUNTAIN_BLOCK_SIZE,
                world_y // MOUNTAIN_BLOCK_SIZE,
            ))

        mountain_blocks = set()
        for block_x, block_y in candidate_blocks:
            block_world_x = block_x * MOUNTAIN_BLOCK_SIZE
            block_world_y = block_y * MOUNTAIN_BLOCK_SIZE
            block_is_clear = True
            for offset_y in range(MOUNTAIN_BLOCK_SIZE):
                for offset_x in range(MOUNTAIN_BLOCK_SIZE):
                    local_x = block_world_x + offset_x - origin_x
                    local_y = block_world_y + offset_y - origin_y
                    if not (0 <= local_x < width and 0 <= local_y < height):
                        block_is_clear = False
                        break
                    idx = local_y * width + local_x
                    if terrain_map[idx] < 0 or expanded[idx] in protected:
                        block_is_clear = False
                        break
                if not block_is_clear:
                    break
            if block_is_clear:
                mountain_blocks.add((block_x, block_y))

        aligned = [
            BIOME_GRASSLAND_AND_FOREST
            if biome_id == BIOME_MOUNTAIN
            else biome_id
            for biome_id in biome_map
        ]

        for local_y in range(height):
            for local_x in range(width):
                idx = local_y * width + local_x
                if terrain_map[idx] < 0 or aligned[idx] in protected:
                    continue
                world_x = origin_x + local_x
                world_y = origin_y + local_y
                block = (
                    world_x // MOUNTAIN_BLOCK_SIZE,
                    world_y // MOUNTAIN_BLOCK_SIZE,
                )
                if block in mountain_blocks:
                    aligned[idx] = BIOME_MOUNTAIN

        return aligned

    def _build_water_distance_map(
        self,
        terrain_map: list[int],
        dim: tuple[int, int],
        max_distance: int,
    ) -> list[int]:
        width, height = dim
        distances = [max_distance + 1] * (width * height)
        frontier = deque()

        for idx, terrain_value in enumerate(terrain_map):
            if terrain_value == -1:
                distances[idx] = 0
                frontier.append(idx)

        while frontier:
            idx = frontier.popleft()
            distance = distances[idx]
            if distance >= max_distance:
                continue

            x = idx % width
            y = idx // width
            next_distance = distance + 1
            if x > 0:
                neighbor = idx - 1
                if next_distance < distances[neighbor]:
                    distances[neighbor] = next_distance
                    frontier.append(neighbor)
            if x + 1 < width:
                neighbor = idx + 1
                if next_distance < distances[neighbor]:
                    distances[neighbor] = next_distance
                    frontier.append(neighbor)
            if y > 0:
                neighbor = idx - width
                if next_distance < distances[neighbor]:
                    distances[neighbor] = next_distance
                    frontier.append(neighbor)
            if y + 1 < height:
                neighbor = idx + width
                if next_distance < distances[neighbor]:
                    distances[neighbor] = next_distance
                    frontier.append(neighbor)

        return distances

    def _build_land_distance_map(
        self,
        terrain_map: list[int],
        dim: tuple[int, int],
        max_distance: int,
    ) -> list[int]:
        """Return Chebyshev distance from each water tile to the nearest land."""
        width, height = dim
        distances = [max_distance + 1] * (width * height)
        frontier = deque()

        for idx, terrain_value in enumerate(terrain_map):
            if terrain_value >= 0:
                distances[idx] = 0
                frontier.append(idx)

        while frontier:
            idx = frontier.popleft()
            distance = distances[idx]
            if distance >= max_distance:
                continue

            x = idx % width
            y = idx // width
            next_distance = distance + 1
            for offset_y in (-1, 0, 1):
                for offset_x in (-1, 0, 1):
                    if offset_x == 0 and offset_y == 0:
                        continue
                    neighbor_x = x + offset_x
                    neighbor_y = y + offset_y
                    if not (0 <= neighbor_x < width and 0 <= neighbor_y < height):
                        continue
                    neighbor = neighbor_y * width + neighbor_x
                    if next_distance < distances[neighbor]:
                        distances[neighbor] = next_distance
                        frontier.append(neighbor)

        return distances

    def _sample_beach_width(self, world_x: int, world_y: int) -> int:
        width_noise = self._sample_value_noise(501, world_x, world_y, 6)
        detail_noise = self._sample_value_noise(502, world_x, world_y, 3)
        return 2 + int((width_noise * 1.5) + (detail_noise * 0.75))

    def _build_collision_layer(self, terrain_map: list[int], dim: tuple[int, int]) -> list[int]:
        width, height = dim
        collision = [0] * (width * height)

        for y in range(height):
            for x in range(width):
                idx = y * width + x
                terrain_value = terrain_map[idx]
                collision[idx] = 1 if terrain_value == -1 else 0

        return collision

    def _build_decoration_layer(self, terrain_map: list[int], biome_map: list[int], dim: tuple[int, int]) -> list:
        width, height = dim
        decoration = [None] * (width * height)
        return decoration

    def apply_chunk_save_data(self, chunk: Chunk) -> None:
        for (layer_name, local_x, local_y), value in chunk.save_data["modified_tiles"].items():
            if layer_name in chunk.layers and chunk.in_bounds(local_x, local_y):
                index = chunk.get_index(local_x, local_y)
                chunk.layers[layer_name][index] = value

        removed_ids = set(chunk.save_data.get("removed_props", ()))
        if removed_ids:
            chunk.props = [
                prop
                for prop in chunk.props
                if not (isinstance(prop, dict) and prop.get("id") in removed_ids)
            ]
        known_ids = {
            prop.get("id")
            for prop in chunk.props
            if isinstance(prop, dict) and prop.get("id") is not None
        }
        for prop in chunk.save_data.get("placed_props", ()):
            prop_id = prop.get("id") if isinstance(prop, dict) else None
            if prop_id is None or prop_id not in known_ids:
                chunk.props.append(prop)
                if prop_id is not None:
                    known_ids.add(prop_id)
        prop_states = chunk.save_data.get("prop_states", {})
        for prop in chunk.props:
            if isinstance(prop, dict) and str(prop.get("id")) in prop_states:
                prop.update(prop_states[str(prop.get("id"))])

        chunk.binary_map = chunk.layers["base"]
        chunk.terrain_map = chunk.layers["terrain"]
        chunk.collision = chunk.layers["collision"]

    def _generate_chunk(self, chunk_coord: tuple[int, int]) -> Chunk:
        """Build data-only procedural chunk state for a worker process."""
        chunk = Chunk(
            coord=chunk_coord,
            chunk_size=self.chunk_size,
            tile_size=self.tile_size
        )

        chunk_w, chunk_h = self.chunk_size
        pad = self.ca_steps + 1
        padded_dim = (chunk_w + pad * 2, chunk_h + pad * 2)

        padded_base_map = self._build_world_space_base_map(
            chunk_coord=chunk_coord,
            padded_dim=padded_dim,
            pad=pad,
            wall_chance=self.wall_chance
        )

        padded_binary_map = self._run_ca_on_map(
            base_map=padded_base_map,
            dim=padded_dim,
            steps=self.ca_steps,
            oob="floor",
            cutoff=self.ca_cutoff
        )
        padded_binary_map = self._apply_island_mask(padded_binary_map, chunk_coord, padded_dim, pad)

        padded_terrain = self._build_signed_terrain(padded_binary_map, padded_dim)

        padded_elevation = self._build_world_space_scalar_layer(
            chunk_coord=chunk_coord,
            padded_dim=padded_dim,
            pad=pad,
            sampler=self._sample_elevation
        )

        padded_moisture = self._build_world_space_scalar_layer(
            chunk_coord=chunk_coord,
            padded_dim=padded_dim,
            pad=pad,
            sampler=self._sample_moisture
        )

        start_world_x = chunk_coord[0] * chunk_w - pad
        start_world_y = chunk_coord[1] * chunk_h - pad
        padded_biome = self._build_biome_layer(
            terrain_map=padded_terrain,
            elevation_map=padded_elevation,
            moisture_map=padded_moisture,
            dim=padded_dim,
            origin_tile=(start_world_x, start_world_y),
        )

        base_layer = self._crop_center(padded_binary_map, padded_dim, self.chunk_size, pad)
        terrain_layer = self._crop_center(padded_terrain, padded_dim, self.chunk_size, pad)
        elevation_layer = self._crop_center(padded_elevation, padded_dim, self.chunk_size, pad)
        moisture_layer = self._crop_center(padded_moisture, padded_dim, self.chunk_size, pad)
        biome_layer = self._crop_center(padded_biome, padded_dim, self.chunk_size, pad)

        collision_layer = self._build_collision_layer(terrain_layer, self.chunk_size)
        decoration_layer = self._build_decoration_layer(terrain_layer, biome_layer, self.chunk_size)

        chunk.set_layer_data("base", base_layer)
        chunk.set_layer_data("terrain", terrain_layer)
        chunk.set_layer_data("biome", biome_layer)
        chunk.set_layer_data("elevation", elevation_layer)
        chunk.set_layer_data("moisture", moisture_layer)
        chunk.set_layer_data("collision", collision_layer)
        chunk.set_layer_data("decoration", decoration_layer)

        chunk.generate_dock_tiles(world_seed=self.seed)
        chunk.generate_market_stalls(world_seed=self.seed)
        required_scenes = (
            ("farmstead",)
            if chunk_coord in self.farmstead_chunks
            else ()
        )
        saved_state = self.saved_chunk_states.get(chunk_coord)
        if saved_state is not None:
            chunk.save_data.update({
                "modified_tiles": dict(saved_state.get("modified_tiles", {})),
                "removed_props": set(saved_state.get("removed_props", ())),
                "placed_props": list(saved_state.get("placed_props", ())),
                "flags": dict(saved_state.get("flags", {})),
                "prop_states": dict(saved_state.get("prop_states", {})),
            })
        chunk.generate_house_props(
            world_seed=self.seed,
            required_scene_names=required_scenes,
        )
        chunk.generate_path_tiles(world_seed=self.seed)
        chunk.generate_tree_props(
            world_seed=self.seed,
            biome_name_resolver=lambda biome_id: BIOME_TABLE[biome_id]["name"],
        )
        chunk.generate_environment_props(world_seed=self.seed)


        self.apply_chunk_save_data(chunk)

        chunk.generated = True
        chunk.metadata["coord"] = chunk_coord
        chunk.metadata["pad"] = pad
        chunk.metadata["ca_steps"] = self.ca_steps

        return chunk

    def _install_generated_chunk(self, chunk_coord: tuple[int, int], chunk: Chunk) -> Chunk:
        existing = self.loaded_chunks.get(chunk_coord)
        if existing is not None:
            return existing

        self.loaded_chunks[chunk_coord] = chunk
        self.invalidate_chunk_and_neighbors(chunk_coord)
        return chunk

    def load_chunk(self, chunk_coord: tuple[int, int]) -> Chunk:
        """Synchronously load a chunk for tools and compatibility callers."""
        existing = self.loaded_chunks.get(chunk_coord)
        if existing is not None:
            return existing
        return self._install_generated_chunk(
            chunk_coord,
            self._generate_chunk(chunk_coord),
        )

    def unload_chunk(self, chunk_coord: tuple[int, int]) -> None:
        if chunk_coord in self.loaded_chunks:
            del self.loaded_chunks[chunk_coord]

    def request_chunks_around(self, center_chunk: tuple[int, int]) -> None:
        """Synchronously generate the complete island."""
        coords = sorted(
            self.get_level_chunk_coords(),
            key=lambda coord: (
                abs(coord[0] - center_chunk[0]) + abs(coord[1] - center_chunk[1]),
                coord[1],
                coord[0],
            ),
        )
        all_chunks = set(coords)
        self.active_chunks = all_chunks
        for coord in coords:
            chunk = self.load_chunk(coord)
            chunk.set_active(True)

    def request_full_island(
        self,
        center_chunk: tuple[int, int] | None = None,
    ) -> None:
        self.request_chunks_around(
            center_chunk or self.current_player_chunk or self.spawn_chunk
        )

    def prepare_full_island(self, prewarm_chunk_callback=None) -> None:
        """Generate and finish every island chunk before gameplay."""
        center = self.current_player_chunk or self.spawn_chunk
        self.request_chunks_around(center)

        coords = sorted(
            self.loaded_chunks,
            key=lambda coord: (
                abs(coord[0] - center[0]) + abs(coord[1] - center[1]),
                coord[1],
                coord[0],
            ),
        )
        for coord in coords:
            chunk = self.loaded_chunks[coord]
            if prewarm_chunk_callback is not None:
                prewarm_chunk_callback(chunk)

    def update_active_chunks(
        self,
        player_world_pos: tuple[int, int],
        movement_direction=None,
    ) -> None:
        self.current_player_chunk = self.world_to_chunk(player_world_pos)

    def get_world_terrain_tile(self, world_x: int, world_y: int) -> int:
        chunk_w, chunk_h = self.chunk_size

        chunk_x = world_x // chunk_w
        chunk_y = world_y // chunk_h

        local_x = world_x % chunk_w
        local_y = world_y % chunk_h

        chunk = self.load_chunk((chunk_x, chunk_y))
        return chunk.terrain_map[local_y * chunk_w + local_x]

    def invalidate_chunk_render_cache(self, chunk_coord: tuple[int, int]) -> None:
        chunk = self.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return

        chunk.runtime["surface"] = None
        chunk.runtime.pop("camera_scaled_surface", None)

        chunk.dirty = True

    def invalidate_soil_render_cache(
        self,
        chunk_coord: tuple[int, int],
        *,
        topology_changed: bool = False,
    ) -> None:
        chunk = self.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return

        chunk.runtime["soil_surface"] = None
        chunk.runtime["soil_water_tilemap"] = None
        chunk.runtime["soil_water_sprite_cache"] = {}
        if topology_changed:
            chunk.runtime["soil_tilemap"] = None
            chunk.runtime["soil_sprite_cache"] = {}
        self.invalidate_chunk_render_cache(chunk_coord)

    def invalidate_fence_render_cache(self, chunk_coord: tuple[int, int]) -> None:
        chunk = self.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return

        chunk.runtime["fence_surface"] = None
        chunk.runtime["fence_tilemap"] = None
        self.invalidate_chunk_render_cache(chunk_coord)

    def invalidate_autotile_render_cache(self, chunk_coord: tuple[int, int]) -> None:
        """Discard terrain caches whose edge masks depend on loaded neighbors."""
        chunk = self.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return

        chunk.runtime["tilemap"] = None
        chunk.runtime["scaled_land_sprites"] = {}
        chunk.runtime["deep_ocean_surface"] = None
        chunk.runtime["deep_ocean_tilemap"] = None
        chunk.runtime["deep_ocean_sprite_cache"] = {}
        chunk.runtime["underwater_surface"] = None
        chunk.runtime["underwater_distances"] = None
        chunk.runtime["underwater_mask"] = None
        chunk.runtime["biome_surface"] = None
        chunk.runtime["biome_tilemaps"] = {}
        chunk.runtime["biome_sprite_cache"] = {}
        chunk.runtime["mountain_surface"] = None
        chunk.runtime["path_surface"] = None
        chunk.runtime["path_tilemap"] = None
        chunk.runtime["path_sprite_cache"] = {}
        chunk.runtime["fence_surface"] = None
        chunk.runtime["fence_tilemap"] = None
        self.invalidate_chunk_render_cache(chunk_coord)

    def invalidate_chunk_and_neighbors(self, chunk_coord: tuple[int, int]) -> None:
        cx, cy = chunk_coord

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                self.invalidate_autotile_render_cache((cx + dx, cy + dy))

    def invalidate_soil_chunk_and_neighbors(self, chunk_coord: tuple[int, int]) -> None:
        cx, cy = chunk_coord

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                self.invalidate_soil_render_cache(
                    (cx + dx, cy + dy),
                    topology_changed=True,
                )

    def invalidate_fence_chunk_and_neighbors(self, chunk_coord: tuple[int, int]) -> None:
        cx, cy = chunk_coord

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                self.invalidate_fence_render_cache((cx + dx, cy + dy))
