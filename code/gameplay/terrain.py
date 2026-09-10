"""Chunk terrain composition and autotile caches."""

import pygame

from TileMapManager import NEIGHBOR_OFFSETS, TILEBITMASK, TileMap, preload_tilesets
from sprites import TileMapSpriteSheet
from world.soil import get_soil_surface
from world.fence import FenceTileMap, get_fence_piece_layout
from world.worldmanager import (
    BIOME_BEACH,
    BIOME_COAST,
    BIOME_MOUNTAIN,
    BIOME_TABLE,
    BIOME_UNDERWATER,
    MOUNTAIN_BLOCK_SIZE,
    UNDERWATER_BIOME_WIDTH,
)
from world.biome_visuals import (
    SUBDIVIDED_GRASS_BIOMES,
    SUBDIVIDED_GRASS_CACHE_KEY,
    SUBDIVIDED_GRASS_TILESET,
    is_grass_patch_tile,
)

from gameplay.assets import get_water_frames
from gameplay.config import (
    AUTOTILED_BIOMES,
    BASE_LAND_TILESET_FILE,
    DEEP_OCEAN_THRESHOLD,
    DEEP_OCEAN_TILESET_FILE,
    DOCK_SOURCE_TILE_SIZE,
    DOCK_TILESET_FILE,
    FENCE_SOURCE_TILE_SIZE,
    FENCE_TILESET_FILE,
    PATH_SOURCE_TILE_SIZE,
    PATH_TILESET_FILE,
    TILESET_SOURCE_TILE_SIZE,
)


_SHALLOW_WATER_BASE_CACHE = {}
_DOCK_SHEET = None
_DOCK_SPRITE_CACHE = {}
_SPECIAL_BIOME_SPRITE_CACHE = {}
UNDERWATER_MAX_SHORE_DISTANCE = UNDERWATER_BIOME_WIDTH
UNDERWATER_SHORE_ALPHA = 50
UNDERWATER_FAR_ALPHA = 0


def preload_world_render_assets():
    """Load terrain atlases that would otherwise stall their first chunk."""
    global _DOCK_SHEET
    preload_tilesets({
        BASE_LAND_TILESET_FILE,
        PATH_TILESET_FILE,
        DEEP_OCEAN_TILESET_FILE,
        FENCE_TILESET_FILE,
        "Tilesets/loam.png",
        "Tilesets/plant_water.png",
        *(entry["tileset"] for entry in BIOME_TABLE.values()),
    })
    if _DOCK_SHEET is None:
        _DOCK_SHEET = TileMapSpriteSheet(DOCK_TILESET_FILE)
    get_water_frames()


def get_special_autotile_sprite(tilemap, bitmask, render_size, alpha=None):
    """Return a cached autotile sprite for micro- and macro-biome renderers."""
    coords = TILEBITMASK[bitmask]
    render_size = (int(render_size[0]), int(render_size[1]))
    cache_key = (
        tilemap.filename,
        tilemap.source_tile_size,
        coords,
        render_size,
        alpha,
    )
    sprite = _SPECIAL_BIOME_SPRITE_CACHE.get(cache_key)
    if sprite is not None:
        return sprite

    tile_x, tile_y = coords
    sprite = tilemap.tile_set.get_sprite(
        tile_x,
        tile_y,
        tilemap.source_tile_size,
        tilemap.source_tile_size,
    )
    if sprite.get_size() != render_size:
        sprite = pygame.transform.scale(sprite, render_size)
    if alpha is not None:
        sprite = sprite.copy()
        sprite.set_alpha(alpha)
    _SPECIAL_BIOME_SPRITE_CACHE[cache_key] = sprite
    return sprite


def get_resolved_bitmask(center_x, center_y, resolver):
    bitmask = 0
    for bit, (offset_x, offset_y) in enumerate(NEIGHBOR_OFFSETS):
        if resolver(center_x + offset_x, center_y + offset_y):
            bitmask |= 1 << bit
    return bitmask

# The upper-left 3x3 region contains platform corners, edges, and fill.
# Horizontal walkway pieces are on row 3; vertical pieces are in column 3.
_DOCK_WALKWAY_TILE_COORDS = {
    "east": {"shore": (0, 3), "middle": (1, 3), "tip": (2, 3)},
    "west": {"shore": (0, 3), "middle": (1, 3), "tip": (2, 3)},
    "north": {"shore": (3, 3), "middle": (3, 1), "tip": (3, 0)},
    "south": {"shore": (3, 3), "middle": (3, 1), "tip": (3, 0)},
}


def get_scaled_dock_sprite(chunk, record):
    global _DOCK_SHEET

    kind = record.get("kind", "walkway")
    direction = record.get("direction", "north")
    segment = record.get("segment", "middle")
    tile_coord = tuple(record.get("tile_coord", (1, 1)))
    render_direction = direction if kind == "walkway" else None
    cache_key = (kind, render_direction, segment, tile_coord, chunk.tile_size)
    sprite = _DOCK_SPRITE_CACHE.get(cache_key)
    if sprite is not None:
        return sprite

    if _DOCK_SHEET is None:
        _DOCK_SHEET = TileMapSpriteSheet(DOCK_TILESET_FILE)

    if kind == "platform":
        tile_x, tile_y = tile_coord
    else:
        tile_x, tile_y = _DOCK_WALKWAY_TILE_COORDS[direction][segment]
    sprite = _DOCK_SHEET.get_sprite(
        tile_x,
        tile_y,
        DOCK_SOURCE_TILE_SIZE,
        DOCK_SOURCE_TILE_SIZE,
    )
    if kind == "walkway" and direction == "west":
        sprite = pygame.transform.flip(sprite, True, False)
    elif kind == "walkway" and direction == "south":
        sprite = pygame.transform.flip(sprite, False, True)

    sprite = pygame.transform.scale(sprite, (chunk.tile_size, chunk.tile_size))
    _DOCK_SPRITE_CACHE[cache_key] = sprite
    return sprite


def get_dock_surface(chunk):
    dock_surface = chunk.runtime.get("dock_surface")
    if dock_surface is not None:
        return dock_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    dock_surface = pygame.Surface(
        (chunk_w * tile_size, chunk_h * tile_size),
        pygame.SRCALPHA,
    )
    for idx, record in enumerate(chunk.layers.get("dock", ())):
        if record is None:
            continue
        dock_surface.blit(
            get_scaled_dock_sprite(chunk, record),
            ((idx % chunk_w) * tile_size, (idx // chunk_w) * tile_size),
        )

    chunk.runtime["dock_surface"] = dock_surface
    return dock_surface




def get_fence_tilemap(world, chunk):
    tilemap = chunk.runtime.get("fence_tilemap")
    if tilemap is None:
        tilemap = FenceTileMap(
            filename=FENCE_TILESET_FILE,
            world=world,
            chunk=chunk,
            source_tile_size=FENCE_SOURCE_TILE_SIZE,
        )
        chunk.runtime["fence_tilemap"] = tilemap
    return tilemap


def get_fence_surface(world, chunk):
    fence_surface = chunk.runtime.get("fence_surface")
    if fence_surface is not None:
        return fence_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    fence_surface = pygame.Surface(
        (chunk_w * tile_size, chunk_h * tile_size),
        pygame.SRCALPHA,
    )
    tilemap = get_fence_tilemap(world, chunk)
    for idx, value in enumerate(chunk.layers.get("fence", ())):
        if value != 1:
            continue
        connections = tilemap.get_connections(idx)
        for offset_x, offset_y, coords in get_fence_piece_layout(
            tile_size,
            **connections,
        ):
            sprite = tilemap.get_piece_sprite(coords)
            fence_surface.blit(
                sprite,
                (
                    (idx % chunk_w) * tile_size + offset_x,
                    (idx // chunk_w) * tile_size + offset_y,
                ),
            )

    chunk.runtime["fence_surface"] = fence_surface
    return fence_surface




def get_path_tilemap(world, chunk):
    tilemap = chunk.runtime.get("path_tilemap")
    if tilemap is None:
        tilemap = TileMap(
            filename=PATH_TILESET_FILE,
            world=world,
            chunk=chunk,
            layer_name="path",
            oob=0,
            source_tile_size=PATH_SOURCE_TILE_SIZE,
        )
        chunk.runtime["path_tilemap"] = tilemap
    return tilemap


def get_path_surface(world, chunk):
    path_surface = chunk.runtime.get("path_surface")
    if path_surface is not None:
        return path_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    path_surface = pygame.Surface(
        (chunk_w * tile_size, chunk_h * tile_size),
        pygame.SRCALPHA,
    )
    tilemap = get_path_tilemap(world, chunk)
    sprite_cache = chunk.runtime.setdefault("path_sprite_cache", {})
    for index, value in enumerate(chunk.layers.get("path", ())):
        if value != 1:
            continue
        sprite = sprite_cache.get(index)
        if sprite is None:
            sprite = tilemap.get_scaled_tile_sprite(index, (tile_size, tile_size))
            sprite_cache[index] = sprite
        if sprite is not None:
            path_surface.blit(
                sprite,
                ((index % chunk_w) * tile_size, (index // chunk_w) * tile_size),
            )

    chunk.runtime["path_surface"] = path_surface
    return path_surface




def get_shallow_water_base_surface(chunk):
    sprite = get_scaled_shallow_water_sprite(chunk)
    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    key = (chunk.chunk_size, tile_size, id(sprite))
    surface = _SHALLOW_WATER_BASE_CACHE.get(key)
    if surface is None:
        surface = pygame.Surface(
            (chunk_w * tile_size, chunk_h * tile_size),
            pygame.SRCALPHA,
        )
        surface.blits([
            (sprite, (local_x * tile_size, local_y * tile_size))
            for local_y in range(chunk_h)
            for local_x in range(chunk_w)
        ])
        _SHALLOW_WATER_BASE_CACHE[key] = surface
    return surface


def get_scaled_shallow_water_sprite(chunk):
    #Returns a water sprite for a each 
    water_sprite = chunk.runtime.get("water_sprite")
    if water_sprite is not None:
        return water_sprite

    frames = get_water_frames()
    water_sprite = pygame.transform.scale(frames[0], (chunk.tile_size, chunk.tile_size))
    chunk.runtime["water_sprite"] = water_sprite
    return water_sprite


def get_loaded_world_layer_value(world, layer_name, world_x, world_y):
    chunk_w, chunk_h = world.chunk_size
    chunk_coord = (world_x // chunk_w, world_y // chunk_h)
    neighbor_chunk = world.loaded_chunks.get(chunk_coord)
    if neighbor_chunk is None:
        return None
    local_x = world_x % chunk_w
    local_y = world_y % chunk_h
    return neighbor_chunk.layers[layer_name][neighbor_chunk.get_index(local_x, local_y)]


def get_underwater_shore_distance(world, chunk, local_x, local_y):
    """Measure an underwater-biome tile's distance from loaded shoreline land."""
    idx = chunk.get_index(local_x, local_y)
    if chunk.layers["biome"][idx] != BIOME_UNDERWATER:
        return None

    world_x, world_y = chunk.get_world_tile(local_x, local_y)
    for distance in range(1, UNDERWATER_MAX_SHORE_DISTANCE + 1):
        for offset_y in range(-distance, distance + 1):
            for offset_x in range(-distance, distance + 1):
                if max(abs(offset_x), abs(offset_y)) != distance:
                    continue
                sample_x = world_x + offset_x
                sample_y = world_y + offset_y
                terrain = get_loaded_world_layer_value(
                    world,
                    "terrain",
                    sample_x,
                    sample_y,
                )
                if terrain is None or terrain < 0:
                    continue
                biome = get_loaded_world_layer_value(
                    world,
                    "biome",
                    sample_x,
                    sample_y,
                )
                if biome in {BIOME_COAST, BIOME_BEACH}:
                    return distance
    return None


def build_underwater_distance_map(world, chunk):
    cached = chunk.runtime.get("underwater_distances")
    if cached is not None:
        return cached

    width, height = chunk.chunk_size
    distances = []
    for local_y in range(height):
        for local_x in range(width):
            distance = get_underwater_shore_distance(
                world,
                chunk,
                local_x,
                local_y,
            )
            distances.append(distance)
    distances = tuple(distances)
    chunk.runtime["underwater_distances"] = distances
    return distances


def build_underwater_biome_mask(world, chunk):
    cached = chunk.runtime.get("underwater_mask")
    if cached is not None:
        return cached
    mask = build_biome_mask(chunk, BIOME_UNDERWATER)
    chunk.runtime["underwater_mask"] = mask
    return mask


def get_underwater_alpha(distance):
    if UNDERWATER_MAX_SHORE_DISTANCE <= 1:
        return UNDERWATER_SHORE_ALPHA
    progress = (distance - 1) / (UNDERWATER_MAX_SHORE_DISTANCE - 1)
    return round(
        UNDERWATER_SHORE_ALPHA
        + (UNDERWATER_FAR_ALPHA - UNDERWATER_SHORE_ALPHA) * progress
    )


def get_underwater_tilemap(world, chunk):
    return get_biome_tilemap(world, chunk, BIOME_UNDERWATER)


def get_scaled_underwater_biome_sprite(world, chunk, idx):
    """Return one native 16px underwater tile without world-tile stretching."""
    tilemap = get_underwater_tilemap(world, chunk)
    sprite = tilemap.get_tile_sprite(idx)
    if sprite is None:
        return None
    distance = build_underwater_distance_map(world, chunk)[idx]
    sprite = sprite.copy()
    sprite.set_alpha(
        get_underwater_alpha(distance)
        if distance is not None
        else UNDERWATER_FAR_ALPHA
    )
    return sprite


def get_underwater_micro_bitmask(world, micro_x, micro_y, micro_tiles_per_world_tile):
    def is_underwater(sample_micro_x, sample_micro_y):
        world_x = sample_micro_x // micro_tiles_per_world_tile
        world_y = sample_micro_y // micro_tiles_per_world_tile
        return get_loaded_world_layer_value(
            world,
            "biome",
            world_x,
            world_y,
        ) == BIOME_UNDERWATER

    return get_resolved_bitmask(micro_x, micro_y, is_underwater)


def get_underwater_surface(world, chunk):
    underwater_surface = chunk.runtime.get("underwater_surface")
    if underwater_surface is not None:
        return underwater_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    source_tile_size = BIOME_TABLE[BIOME_UNDERWATER]["source_tile_size"]
    micro_tiles_per_world_tile = max(1, tile_size // source_tile_size)
    tilemap = get_underwater_tilemap(world, chunk)
    distances = build_underwater_distance_map(world, chunk)
    underwater_surface = pygame.Surface(
        (chunk_w * tile_size, chunk_h * tile_size),
        pygame.SRCALPHA,
    )
    for idx, value in enumerate(build_underwater_biome_mask(world, chunk)):
        if value != 1:
            continue
        if chunk.layers.get("dock") and chunk.layers["dock"][idx] is not None:
            continue
        distance = distances[idx]
        alpha = (
            get_underwater_alpha(distance)
            if distance is not None
            else UNDERWATER_FAR_ALPHA
        )
        if alpha <= 0:
            continue

        local_x = idx % chunk_w
        local_y = idx // chunk_w
        world_x, world_y = chunk.get_world_tile(local_x, local_y)
        for micro_y in range(micro_tiles_per_world_tile):
            for micro_x in range(micro_tiles_per_world_tile):
                world_micro_x = world_x * micro_tiles_per_world_tile + micro_x
                world_micro_y = world_y * micro_tiles_per_world_tile + micro_y
                bitmask = get_underwater_micro_bitmask(
                    world,
                    world_micro_x,
                    world_micro_y,
                    micro_tiles_per_world_tile,
                )
                sprite = get_special_autotile_sprite(
                    tilemap,
                    bitmask,
                    (source_tile_size, source_tile_size),
                    alpha,
                )
                underwater_surface.blit(
                    sprite,
                    (
                        local_x * tile_size + micro_x * source_tile_size,
                        local_y * tile_size + micro_y * source_tile_size,
                    ),
                )

    chunk.runtime["underwater_surface"] = underwater_surface
    return underwater_surface


def get_chunk_tilemap(world, chunk):
    # Tilemaps are cached on each chunk because autotiling may query neighbors
    # and is expensive to rebuild every frame.
    tilemap = chunk.runtime.get("tilemap")
    if tilemap is None:
        tilemap = TileMap(
            filename=BASE_LAND_TILESET_FILE,
            world=world,
            chunk=chunk,
            oob=1,
            source_tile_size=TILESET_SOURCE_TILE_SIZE,
        )
        chunk.runtime["tilemap"] = tilemap
    return tilemap


def is_deep_water_tile(chunk, local_x, local_y, world=None):
    # Deep ocean is low-elevation water that is not touching land; shoreline
    # water is left to the shallow animated layer.
    # return 1 if the tile is away from the shore
    idx = chunk.get_index(local_x, local_y)
    if chunk.layers["terrain"][idx] != -1:
        return 0
    if chunk.layers["biome"][idx] == BIOME_UNDERWATER:
        return 0

    if chunk.layers["elevation"][idx] > DEEP_OCEAN_THRESHOLD:
        return 0

    chunk_w, chunk_h = chunk.chunk_size
    # Look at each tile and its neighbors.
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
               # grab the next tile
            nx = local_x + dx
            ny = local_y + dy
            if 0 <= nx < chunk_w and 0 <= ny < chunk_h:
                nidx = chunk.get_index(nx, ny)
                if chunk.layers["terrain"][nidx] != -1:
                    return 0
            elif world is not None:
                world_x, world_y = chunk.get_world_tile(local_x, local_y)
                neighbor_terrain = get_loaded_world_layer_value(
                    world,
                    "terrain",
                    world_x + dx,
                    world_y + dy,
                )
                if neighbor_terrain is not None and neighbor_terrain != -1:
                    return 0

    return 1 


def build_deep_water_mask(chunk, world=None):
    # Return tiles that are part of the deep water.
    chunk_w, chunk_h = chunk.chunk_size
    return [
        is_deep_water_tile(chunk, local_x, local_y, world)
        for local_y in range(chunk_h)
        for local_x in range(chunk_w)
    ]


def get_neighbor_deep_water_mask_value(world, neighbor_chunk, local_x, local_y):
    return is_deep_water_tile(neighbor_chunk, local_x, local_y, world)


def get_deep_ocean_tilemap(world, chunk):
    # Return the deep water tilemap
    tilemap = chunk.runtime.get("deep_ocean_tilemap")
    if tilemap is None:
        tilemap = TileMap(
            filename=DEEP_OCEAN_TILESET_FILE,
            world=world,
            chunk=chunk,
            oob=0,
            layer_data=build_deep_water_mask(chunk, world),
            world_layer_resolver=lambda neighbor_chunk, lx, ly: get_neighbor_deep_water_mask_value(
                world,
                neighbor_chunk,
                lx,
                ly,
            ),
            source_tile_size=TILESET_SOURCE_TILE_SIZE,
        )
        chunk.runtime["deep_ocean_tilemap"] = tilemap
    return tilemap


def get_scaled_deep_ocean_sprite(world, chunk, idx):
    # Scale the deep water tilemap sprites
    sprite_cache = chunk.runtime.get("deep_ocean_sprite_cache")
    if sprite_cache is None:
        sprite_cache = {}
        chunk.runtime["deep_ocean_sprite_cache"] = sprite_cache

    if idx in sprite_cache:
        return sprite_cache[idx]

    scaled = get_deep_ocean_tilemap(world, chunk).get_scaled_tile_sprite(
        idx,
        (chunk.tile_size, chunk.tile_size),
    )
    if scaled is None:
        return None

    sprite_cache[idx] = scaled
    return scaled


def get_deep_ocean_surface(world, chunk):
    # Create a deep ocean surface and blit the spirtes on it.
    deep_ocean_surface = chunk.runtime.get("deep_ocean_surface")
    if deep_ocean_surface is not None:
        return deep_ocean_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    deep_ocean_surface = pygame.Surface((chunk_w * tile_size, chunk_h * tile_size), pygame.SRCALPHA)

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = local_y * chunk_w + local_x
            sprite = get_scaled_deep_ocean_sprite(world, chunk, idx)
            if sprite is not None:
                deep_ocean_surface.blit(sprite, (local_x * tile_size, local_y * tile_size))

    chunk.runtime["deep_ocean_surface"] = deep_ocean_surface
    return deep_ocean_surface




def get_scaled_land_sprite(chunk, tilemap, idx):
    # This is similar to the deep ocean one...
    sprite_cache = chunk.runtime.get("scaled_land_sprites")
    if sprite_cache is None:
        sprite_cache = {}
        chunk.runtime["scaled_land_sprites"] = sprite_cache

    if idx in sprite_cache:
        return sprite_cache[idx]

    scaled = tilemap.get_scaled_tile_sprite(idx, (chunk.tile_size, chunk.tile_size))
    if scaled is None:
        return None

    sprite_cache[idx] = scaled
    return scaled


def build_biome_mask(chunk, biome_id):
    return [1 if value == biome_id else 0 for value in chunk.layers["biome"]]


def get_neighbor_biome_mask_value(neighbor_chunk, local_x, local_y, biome_id):
    idx = neighbor_chunk.get_index(local_x, local_y)
    return 1 if neighbor_chunk.layers["biome"][idx] == biome_id else 0


def build_subdivided_grass_mask(chunk, world_seed):
    return [
        1
        if is_grass_patch_tile(
            world_seed,
            *chunk.get_world_tile(idx % chunk.chunk_size[0], idx // chunk.chunk_size[0]),
            biome_id,
        )
        else 0
        for idx, biome_id in enumerate(chunk.layers["biome"])
    ]


def get_neighbor_subdivided_grass_mask_value(
    neighbor_chunk,
    local_x,
    local_y,
    world_seed,
):
    idx = neighbor_chunk.get_index(local_x, local_y)
    biome_id = neighbor_chunk.layers["biome"][idx]
    world_x, world_y = neighbor_chunk.get_world_tile(local_x, local_y)
    return 1 if is_grass_patch_tile(
        world_seed,
        world_x,
        world_y,
        biome_id,
    ) else 0


def get_biome_tilemap(world, chunk, biome_id):
    biome_tilemaps = chunk.runtime.get("biome_tilemaps")
    if biome_tilemaps is None:
        biome_tilemaps = {}
        chunk.runtime["biome_tilemaps"] = biome_tilemaps

    cache_key = (
        SUBDIVIDED_GRASS_CACHE_KEY
        if biome_id in SUBDIVIDED_GRASS_BIOMES
        else biome_id
    )
    if cache_key in biome_tilemaps:
        return biome_tilemaps[cache_key]

    world_seed = getattr(world, "seed", 0)
    biome_data = BIOME_TABLE[biome_id]
    source_tile_size = biome_data.get(
        "source_tile_size",
        TILESET_SOURCE_TILE_SIZE,
    )
    if biome_id in SUBDIVIDED_GRASS_BIOMES:
        filename = SUBDIVIDED_GRASS_TILESET
        mask = build_subdivided_grass_mask(chunk, world_seed)
        neighbor_resolver = lambda neighbor_chunk, lx, ly: get_neighbor_subdivided_grass_mask_value(
            neighbor_chunk,
            lx,
            ly,
            world_seed,
        )
    else:
        filename = biome_data["tileset"]
        mask = build_biome_mask(chunk, biome_id)
        neighbor_resolver = lambda neighbor_chunk, lx, ly: get_neighbor_biome_mask_value(
            neighbor_chunk,
            lx,
            ly,
            biome_id,
        )
    tilemap = TileMap(
        filename=filename,
        world=world,
        chunk=chunk,
        oob=0,
        layer_data=mask,
        world_layer_resolver=neighbor_resolver,
        source_tile_size=source_tile_size,
    )
    biome_tilemaps[cache_key] = tilemap
    return tilemap


def get_scaled_biome_sprite(world, chunk, biome_id, idx):
    biome_sprite_cache = chunk.runtime.get("biome_sprite_cache")
    if biome_sprite_cache is None:
        biome_sprite_cache = {}
        chunk.runtime["biome_sprite_cache"] = biome_sprite_cache

    cache_key = (
        SUBDIVIDED_GRASS_CACHE_KEY
        if biome_id in SUBDIVIDED_GRASS_BIOMES
        else biome_id
    )
    biome_cache = biome_sprite_cache.get(cache_key)
    if biome_cache is None:
        biome_cache = {}
        biome_sprite_cache[cache_key] = biome_cache

    if idx in biome_cache:
        return biome_cache[idx]

    biome_tilemap = get_biome_tilemap(world, chunk, biome_id)
    if biome_id == BIOME_UNDERWATER:
        render_size = (biome_tilemap.source_tile_size,) * 2
    elif biome_id == BIOME_MOUNTAIN:
        render_size = (chunk.tile_size * MOUNTAIN_BLOCK_SIZE,) * 2
    else:
        render_size = (chunk.tile_size, chunk.tile_size)
    scaled = biome_tilemap.get_scaled_tile_sprite(idx, render_size)
    if scaled is None:
        return None

    if biome_id == BIOME_UNDERWATER:
        distance = build_underwater_distance_map(world, chunk)[idx]
        scaled = scaled.copy()
        scaled.set_alpha(
            get_underwater_alpha(distance)
            if distance is not None
            else UNDERWATER_FAR_ALPHA
        )

    biome_cache[idx] = scaled
    return scaled


def get_mountain_macro_bitmask(world, macro_x, macro_y):
    def is_mountain(sample_macro_x, sample_macro_y):
        return get_loaded_world_layer_value(
            world,
            "biome",
            sample_macro_x * MOUNTAIN_BLOCK_SIZE,
            sample_macro_y * MOUNTAIN_BLOCK_SIZE,
        ) == BIOME_MOUNTAIN

    return get_resolved_bitmask(macro_x, macro_y, is_mountain)


def get_mountain_surface(world, chunk):
    mountain_surface = chunk.runtime.get("mountain_surface")
    if mountain_surface is not None:
        return mountain_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    macro_render_size = tile_size * MOUNTAIN_BLOCK_SIZE
    tilemap = get_biome_tilemap(world, chunk, BIOME_MOUNTAIN)
    mountain_surface = pygame.Surface(
        (chunk_w * tile_size, chunk_h * tile_size),
        pygame.SRCALPHA,
    )

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            world_x, world_y = chunk.get_world_tile(local_x, local_y)
            if world_x % MOUNTAIN_BLOCK_SIZE or world_y % MOUNTAIN_BLOCK_SIZE:
                continue
            idx = chunk.get_index(local_x, local_y)
            if chunk.layers["biome"][idx] != BIOME_MOUNTAIN:
                continue
            macro_x = world_x // MOUNTAIN_BLOCK_SIZE
            macro_y = world_y // MOUNTAIN_BLOCK_SIZE
            bitmask = get_mountain_macro_bitmask(world, macro_x, macro_y)
            sprite = get_special_autotile_sprite(
                tilemap,
                bitmask,
                (macro_render_size, macro_render_size),
            )
            mountain_surface.blit(
                sprite,
                (local_x * tile_size, local_y * tile_size),
            )

    chunk.runtime["mountain_surface"] = mountain_surface
    return mountain_surface


def get_biome_surface(world, chunk):
    biome_surface = chunk.runtime.get("biome_surface")
    if biome_surface is not None:
        return biome_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    biome_surface = pygame.Surface((chunk_w * tile_size, chunk_h * tile_size), pygame.SRCALPHA)

    for idx, biome_id in enumerate(chunk.layers["biome"]):
        if biome_id not in AUTOTILED_BIOMES:
            continue
        if biome_id in {BIOME_UNDERWATER, BIOME_MOUNTAIN}:
            continue
        sprite = get_scaled_biome_sprite(world, chunk, biome_id, idx)
        if sprite is not None:
            local_x = idx % chunk_w
            local_y = idx // chunk_w
            biome_surface.blit(sprite, (local_x * tile_size, local_y * tile_size))

    biome_surface.blit(get_mountain_surface(world, chunk), (0, 0))
    biome_surface.blit(get_underwater_surface(world, chunk), (0, 0))

    chunk.runtime["biome_surface"] = biome_surface
    return biome_surface




def get_chunk_surface(world, chunk):
    # Compose static terrain layers once per dirty chunk. Dynamic actors,
    # animation, and particles are drawn later in the frame.
    surface = chunk.runtime.get("surface")
    if surface is not None:
        return surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    surface = get_shallow_water_base_surface(chunk).copy()
    tilemap = get_chunk_tilemap(world, chunk)

    surface.blit(get_deep_ocean_surface(world, chunk), (0, 0))

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = local_y * chunk_w + local_x
            if chunk.layers["base"][idx] != 1:
                continue
            land_sprite = get_scaled_land_sprite(chunk, tilemap, idx)
            if land_sprite is not None:
                surface.blit(land_sprite, (local_x * tile_size, local_y * tile_size))

    surface.blit(get_biome_surface(world, chunk), (0, 0))
    surface.blit(get_path_surface(world, chunk), (0, 0))
    surface.blit(get_soil_surface(world, chunk), (0, 0))
    surface.blit(get_dock_surface(chunk), (0, 0))
    surface.blit(get_fence_surface(world, chunk), (0, 0))
    chunk.runtime["surface"] = surface
    chunk.dirty = False
    return surface


