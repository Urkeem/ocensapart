"""World manager for island-level loading, biome data, and coordinate conversion."""

from dataclasses import dataclass
import hashlib
import math
import random
from world.chunkmanager import Chunk
from world.cellular_automata import CellularAutomata


# Biome ids
BIOME_OCEAN = 0
BIOME_COAST = 1
BIOME_BEACH = 2
BIOME_GRASSLAND = 3
BIOME_FOREST = 4
BIOME_SWAMP = 5
BIOME_DRYLAND = 6
BIOME_DESERT = 7
BIOME_HIGHLANDS = 8
BIOME_MOUNTAIN = 9
BIOME_JUNGLE = 10

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
    BIOME_GRASSLAND: {
        "name": "grassland",
        "tileset": "Tilesets/grassland.png",
        "color": (90, 170, 80),
    },
    BIOME_FOREST: {
        "name": "forest",
        "tileset": "Tilesets/forest.png",
        "color": (40, 120, 55),
    },
    BIOME_SWAMP: {
        "name": "swamp",
        "tileset": "Tilesets/swamp.png",
        "color": (70, 110, 60),
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
    BIOME_HIGHLANDS: {
        "name": "highlands",
        "tileset": "Tilesets/highland.png",
        "color": (120, 145, 95),
    },
    BIOME_MOUNTAIN: {
        "name": "mountain",
        "tileset": "Tilesets/mountain.png",
        "color": (140, 140, 140),
    },
    BIOME_JUNGLE: {
            "name": "jungle",
            "tileset": "Tilesets/mountain.png",
            "color": (140, 140, 140),
    },
}


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
        radius_chunks = 2
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
            radius_chunks=2,
            difficulty=1,
            name="Island 1",
        )

        self.ca_steps = 4
        self.wall_chance = 0.54
        self.ca_cutoff = (3, 5)
        self.island_shoreline = 0.82

        self.loaded_chunks: dict[tuple[int, int], Chunk] = {}
        self.active_chunks: set[tuple[int, int]] = set()
        self.current_player_chunk: tuple[int, int] | None = None
        self.chunk_load_queue: list[tuple[int, int]] = []
        self.target_loaded_chunks: set[tuple[int, int]] = set()
        self.exit_chunk = self._choose_exit_chunk()

    @property
    def level_name(self) -> str:
        return self.island.name

    def _choose_exit_chunk(self) -> tuple[int, int]:
        rng = random.Random(stable_seed(self.seed, "exit", self.island.index))
        radius = max(2, self.island.radius_chunks)
        edge = rng.choice(("north", "south", "east", "west"))
        offset = rng.randint(-max(1, radius // 2), max(1, radius // 2))
        if edge == "north":
            return self.spawn_chunk[0] + offset, self.spawn_chunk[1] - radius
        if edge == "south":
            return self.spawn_chunk[0] + offset, self.spawn_chunk[1] + radius
        if edge == "east":
            return self.spawn_chunk[0] + radius, self.spawn_chunk[1] + offset
        return self.spawn_chunk[0] - radius, self.spawn_chunk[1] + offset

    def is_chunk_in_level_bounds(self, chunk_coord: tuple[int, int]) -> bool:
        cx, cy = self.spawn_chunk
        x, y = chunk_coord
        radius = self.island.radius_chunks
        return abs(x - cx) <= radius and abs(y - cy) <= radius

    def get_level_chunk_coords(self) -> set[tuple[int, int]]:
        cx, cy = self.spawn_chunk
        radius = self.island.radius_chunks
        return {
            (cx + dx, cy + dy)
            for dy in range(-radius, radius + 1)
            for dx in range(-radius, radius + 1)
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
        local_seed = stable_seed(self.seed, "field", field_seed, x, y) & 0xffffffff
        rng = random.Random(local_seed)
        return rng.random()

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
        radius_x = max(1, self.island.radius_chunks * chunk_w)
        radius_y = max(1, self.island.radius_chunks * chunk_h)
        dx = (world_x - center_x) / radius_x
        dy = (world_y - center_y) / radius_y
        return (dx * dx + dy * dy) ** 0.5

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
        if self._is_spawn_core_tile(world_x, world_y):
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
                if distance > 1.04 + self._island_edge_noise(world_x, world_y):
                    masked[local_y * width + local_x] = 0
                elif self._is_spawn_core_tile(world_x, world_y):
                    masked[local_y * width + local_x] = 1

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

        for y in range(height):
            for x in range(width):
                idx = y * width + x

                terrain_value = terrain_map[idx]
                elevation = elevation_map[idx]
                moisture = moisture_map[idx]

                if terrain_value == -1:
                    biome[idx] = BIOME_OCEAN
                    continue

                shore_distance = water_distances[idx]
                world_x = origin_x + x
                world_y = origin_y + y
                if shore_distance <= self._sample_beach_width(world_x, world_y):
                    biome[idx] = BIOME_COAST if moisture >= 0.72 and shore_distance <= 2 else BIOME_BEACH
                    continue

                edge_jitter = (self._sample_value_noise(401, world_x, world_y, 4) - 0.5) * 0.08

                if elevation + edge_jitter >= 0.82:
                    biome[idx] = BIOME_MOUNTAIN
                elif elevation + edge_jitter >= 0.68:
                    biome[idx] = BIOME_HIGHLANDS
                elif moisture + edge_jitter < 0.18:
                    biome[idx] = BIOME_DESERT
                elif moisture + edge_jitter < 0.35:
                    biome[idx] = BIOME_DRYLAND
                elif moisture + edge_jitter > 0.78:
                    biome[idx] = BIOME_SWAMP
                elif moisture + edge_jitter > 0.58:
                    biome[idx] = BIOME_FOREST
                else:
                    biome[idx] = BIOME_GRASSLAND

        return biome

    def _build_water_distance_map(
        self,
        terrain_map: list[int],
        dim: tuple[int, int],
        max_distance: int,
    ) -> list[int]:
        width, height = dim
        distances = [max_distance + 1] * (width * height)

        for y in range(height):
            for x in range(width):
                idx = y * width + x
                if terrain_map[idx] == -1:
                    distances[idx] = 0
                    continue

                best = max_distance + 1
                for dy in range(-max_distance, max_distance + 1):
                    for dx in range(-max_distance, max_distance + 1):
                        distance = abs(dx) + abs(dy)
                        if distance >= best:
                            continue

                        nx = x + dx
                        ny = y + dy
                        if 0 <= nx < width and 0 <= ny < height:
                            nidx = ny * width + nx
                            if terrain_map[nidx] == -1:
                                best = distance

                distances[idx] = best

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

        chunk.binary_map = chunk.layers["base"]
        chunk.terrain_map = chunk.layers["terrain"]
        chunk.collision = chunk.layers["collision"]

    def load_chunk(self, chunk_coord: tuple[int, int]) -> Chunk:
        if chunk_coord in self.loaded_chunks:
            return self.loaded_chunks[chunk_coord]

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

        chunk.generate_house_props(world_seed=self.seed)
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

        self.loaded_chunks[chunk_coord] = chunk
        self.invalidate_chunk_and_neighbors(chunk_coord)
        return chunk

    def unload_chunk(self, chunk_coord: tuple[int, int]) -> None:
        if chunk_coord in self.loaded_chunks:
            del self.loaded_chunks[chunk_coord]

    def request_chunks_around(self, center_chunk: tuple[int, int]) -> None:
        loaded_needed = self.get_level_chunk_coords()

        self.active_chunks = loaded_needed
        self.target_loaded_chunks = loaded_needed

        for coord, chunk in self.loaded_chunks.items():
            chunk.set_active(coord in loaded_needed)

        cx, cy = center_chunk
        missing = [
            coord for coord in loaded_needed
            if coord not in self.loaded_chunks and coord not in self.chunk_load_queue
        ]
        missing.sort(key=lambda c: abs(c[0] - center_chunk[0]) + abs(c[1] - center_chunk[1]))
        self.chunk_load_queue.extend(missing)

    def update_active_chunks(self, player_world_pos: tuple[int, int]) -> None:
        player_chunk = self.world_to_chunk(player_world_pos)

        if self.active_chunks and self.target_loaded_chunks:
            self.current_player_chunk = player_chunk
            return

        if player_chunk == self.current_player_chunk and self.active_chunks:
            return

        self.current_player_chunk = player_chunk
        self.request_chunks_around(player_chunk)

    def process_chunk_queue(self, max_per_frame: int = 2, prewarm_chunk_callback=None) -> None:
        loaded_this_frame = 0

        while self.chunk_load_queue and loaded_this_frame < max_per_frame:
            coord = self.chunk_load_queue.pop(0)

            if coord in self.loaded_chunks:
                continue

            chunk = self.load_chunk(coord)
            chunk.set_active(coord in self.active_chunks)

            if prewarm_chunk_callback is not None:
                prewarm_chunk_callback(chunk)

            loaded_this_frame += 1

        chunks_to_unload = set(self.loaded_chunks.keys()) - self.target_loaded_chunks
        for coord in chunks_to_unload:
            self.unload_chunk(coord)

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

        chunk.runtime["tilemap"] = None
        chunk.runtime["scaled_land_sprites"] = {}
        chunk.runtime["water_sprite"] = None
        chunk.runtime["water_variants"] = {}
        chunk.runtime["water_objects"] = {}
        chunk.runtime["biome_surface"] = None
        chunk.runtime["biome_tilemaps"] = {}
        chunk.runtime["biome_sprite_cache"] = {}
        chunk.runtime["soil_surface"] = None
        chunk.runtime["soil_tilemap"] = None
        chunk.runtime["soil_sprite_cache"] = {}
        chunk.runtime["plant_objects"] = {}
        chunk.runtime["house_objects"] = {}
        chunk.runtime["environment_objects"] = {}
        chunk.runtime["deep_ocean_surface"] = None
        chunk.runtime["deep_ocean_tilemap"] = None
        chunk.runtime["deep_ocean_sprite_cache"] = {}
        chunk.runtime["surface"] = None

        chunk.dirty = True

    def invalidate_chunk_and_neighbors(self, chunk_coord: tuple[int, int]) -> None:
        cx, cy = chunk_coord

        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                self.invalidate_chunk_render_cache((cx + dx, cy + dy))
