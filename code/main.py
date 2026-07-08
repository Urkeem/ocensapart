"""Game entry point and runtime glue for world rendering, entities, and UI."""

import math
import random
import pygame
from world.worldmanager import WorldRun, BIOME_TABLE
from entities.player import Player
from TileMapManager import TileMap
from core.camera import Camera
from assets import LoadAssets
from entities.tree import Tree
from entities.house import House
from entities.environment_prop import EnvironmentProp, list_environment_assets
from world.soil import SoilLayer, get_soil_surface, ensure_chunk_plant_objects
from ui.hud import GameplayHUD
from sprites import AnimatedWorldObject
from world.weather import WeatherSystem
from entities.npc import NPCManager
from utils import rp

pygame.init()

SCREEN_WIDTH = pygame.display.Info().current_w
SCREEN_HEIGHT = pygame.display.Info().current_h
FPS = 60

BASE_LAND_TILESET_FILE = "Tilesets/land.png"
DEEP_OCEAN_TILESET_FILE = "Tilesets/ocean.png"
AUTOTILED_BIOMES = {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}
DEEP_OCEAN_THRESHOLD = 0.30
BACKGROUND_COLOR = (20, 20, 30)
PLAYER_COLOR = (230, 70, 70)
TEXT_COLOR = (255, 255, 255)
TILESET_SOURCE_TILE_SIZE = 32
WATER_ANIMATION_SPEED = 4.0
WORLD_SCALE = 2

UI_BG = (11, 16, 26)
UI_PANEL = (22, 30, 45)
UI_PANEL_ALT = (30, 40, 60)
UI_ACCENT = (76, 145, 201)
UI_ACCENT_2 = (209, 177, 87)
UI_TEXT = (236, 240, 245)
UI_MUTED = (170, 180, 190)
UI_WARN = (135, 135, 145)

DEFAULT_CHUNK_SIZE = (24, 24)
DEFAULT_ACTIVE_RADIUS = 1
DEFAULT_TILE_SIZE = TILESET_SOURCE_TILE_SIZE * 3
INITIAL_LOAD_BATCH = 9999
WORLD_HINT_KEYS = {
    pygame.K_SPACE,
    pygame.K_LCTRL,
    pygame.K_RCTRL,
    pygame.K_q,
    pygame.K_e,
    pygame.K_p,
}
WORLD_HINT_ACK_KEYS = {
    "select_axe": {pygame.K_q},
    "break_resource": {pygame.K_SPACE},
    "collect_loose_item": {pygame.K_e, pygame.K_p},
    "select_fishing_rod": {pygame.K_q},
    "cast_fishing_line": {pygame.K_SPACE},
    "reel_fishing_line": {pygame.K_SPACE},
}

_WATER_FRAME_CACHE = None
_SHARED_ASSETS = None
_WORLD_HINT_FONT = None
_BOBBER_ICON = None


def get_shared_assets():
    # Lazily create the large asset registry so runtime systems can share
    # loaded sprite sheets without re-reading image files.
    global _SHARED_ASSETS
    if _SHARED_ASSETS is None:
        _SHARED_ASSETS = LoadAssets()
    return _SHARED_ASSETS


def get_water_frames():
    global _WATER_FRAME_CACHE
    if _WATER_FRAME_CACHE is not None:
        return _WATER_FRAME_CACHE

    assets = get_shared_assets()
    frames = []
    for _, frame in sorted(assets.water_frames.items(), key=lambda item: int(item[0])):
        x, y, w, h = frame
        surf = assets.water_sprites.get_sprite(x, y, w, h).convert_alpha()
        frames.append(surf)

    _WATER_FRAME_CACHE = frames
    return _WATER_FRAME_CACHE


def get_scaled_shallow_water_sprite(chunk):
    water_sprite = chunk.runtime.get("water_sprite")
    if water_sprite is not None:
        return water_sprite

    frames = get_water_frames()
    water_sprite = pygame.transform.scale(frames[0], (chunk.tile_size, chunk.tile_size))
    chunk.runtime["water_sprite"] = water_sprite
    return water_sprite


class WaterTile(AnimatedWorldObject):
    def __init__(self, world_pos, tile_size, frames, animation_speed=WATER_ANIMATION_SPEED):
        scaled_frames = [pygame.transform.scale(frame, (tile_size, tile_size)) for frame in frames]
        super().__init__(
            pos=world_pos,
            frames=scaled_frames,
            anchor="topleft",
            animation_speed=animation_speed,
            loop=True,
        )
        self.render_layer = "ground"

    @property
    def sort_y(self):
        return self.rect.bottom


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


def is_deep_water_tile(chunk, local_x, local_y):
    # Deep ocean is low-elevation water that is not touching land; shoreline
    # water is left to the shallow animated layer.
    idx = chunk.get_index(local_x, local_y)
    if chunk.layers["terrain"][idx] != -1:
        return 0

    if chunk.layers["elevation"][idx] > DEEP_OCEAN_THRESHOLD:
        return 0

    chunk_w, chunk_h = chunk.chunk_size
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue

            nx = local_x + dx
            ny = local_y + dy
            if 0 <= nx < chunk_w and 0 <= ny < chunk_h:
                nidx = chunk.get_index(nx, ny)
                if chunk.layers["terrain"][nidx] != -1:
                    return 0

    return 1


def build_deep_water_mask(chunk):
    chunk_w, chunk_h = chunk.chunk_size
    return [
        is_deep_water_tile(chunk, local_x, local_y)
        for local_y in range(chunk_h)
        for local_x in range(chunk_w)
    ]


def get_neighbor_deep_water_mask_value(neighbor_chunk, local_x, local_y):
    return is_deep_water_tile(neighbor_chunk, local_x, local_y)


def get_deep_ocean_tilemap(world, chunk):
    tilemap = chunk.runtime.get("deep_ocean_tilemap")
    if tilemap is None:
        tilemap = TileMap(
            filename=DEEP_OCEAN_TILESET_FILE,
            world=world,
            chunk=chunk,
            oob=0,
            layer_data=build_deep_water_mask(chunk),
            world_layer_resolver=get_neighbor_deep_water_mask_value,
            source_tile_size=TILESET_SOURCE_TILE_SIZE,
        )
        chunk.runtime["deep_ocean_tilemap"] = tilemap
    return tilemap


def get_scaled_deep_ocean_sprite(world, chunk, idx):
    sprite_cache = chunk.runtime.get("deep_ocean_sprite_cache")
    if sprite_cache is None:
        sprite_cache = {}
        chunk.runtime["deep_ocean_sprite_cache"] = sprite_cache

    if idx in sprite_cache:
        return sprite_cache[idx]

    raw = get_deep_ocean_tilemap(world, chunk).get_tile_sprite(idx)
    if raw is None:
        return None

    scaled = pygame.transform.scale(raw, (chunk.tile_size, chunk.tile_size))
    sprite_cache[idx] = scaled
    return scaled


def get_deep_ocean_surface(world, chunk):
    deep_ocean_surface = chunk.runtime.get("deep_ocean_surface")
    if deep_ocean_surface is not None and not chunk.dirty:
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
    sprite_cache = chunk.runtime.get("scaled_land_sprites")
    if sprite_cache is None:
        sprite_cache = {}
        chunk.runtime["scaled_land_sprites"] = sprite_cache

    if idx in sprite_cache:
        return sprite_cache[idx]

    raw = tilemap.get_tile_sprite(idx)
    if raw is None:
        return None

    scaled = pygame.transform.scale(raw, (chunk.tile_size, chunk.tile_size))
    sprite_cache[idx] = scaled
    return scaled


def build_biome_mask(chunk, biome_id):
    return [1 if value == biome_id else 0 for value in chunk.layers["biome"]]


def get_neighbor_biome_mask_value(neighbor_chunk, local_x, local_y, biome_id):
    idx = neighbor_chunk.get_index(local_x, local_y)
    return 1 if neighbor_chunk.layers["biome"][idx] == biome_id else 0


def get_biome_tilemap(world, chunk, biome_id):
    biome_tilemaps = chunk.runtime.get("biome_tilemaps")
    if biome_tilemaps is None:
        biome_tilemaps = {}
        chunk.runtime["biome_tilemaps"] = biome_tilemaps

    if biome_id in biome_tilemaps:
        return biome_tilemaps[biome_id]

    biome_data = BIOME_TABLE[biome_id]
    mask = build_biome_mask(chunk, biome_id)
    tilemap = TileMap(
        filename=biome_data["tileset"],
        world=world,
        chunk=chunk,
        oob=0,
        layer_data=mask,
        world_layer_resolver=lambda neighbor_chunk, lx, ly: get_neighbor_biome_mask_value(
            neighbor_chunk, lx, ly, biome_id
        ),
        source_tile_size=TILESET_SOURCE_TILE_SIZE,
    )
    biome_tilemaps[biome_id] = tilemap
    return tilemap


def get_scaled_biome_sprite(world, chunk, biome_id, idx):
    biome_sprite_cache = chunk.runtime.get("biome_sprite_cache")
    if biome_sprite_cache is None:
        biome_sprite_cache = {}
        chunk.runtime["biome_sprite_cache"] = biome_sprite_cache

    biome_cache = biome_sprite_cache.get(biome_id)
    if biome_cache is None:
        biome_cache = {}
        biome_sprite_cache[biome_id] = biome_cache

    if idx in biome_cache:
        return biome_cache[idx]

    biome_tilemap = get_biome_tilemap(world, chunk, biome_id)
    raw = biome_tilemap.get_tile_sprite(idx)
    if raw is None:
        return None

    scaled = pygame.transform.scale(raw, (chunk.tile_size, chunk.tile_size))
    biome_cache[idx] = scaled
    return scaled


def get_biome_surface(world, chunk):
    biome_surface = chunk.runtime.get("biome_surface")
    if biome_surface is not None and not chunk.dirty:
        return biome_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    biome_surface = pygame.Surface((chunk_w * tile_size, chunk_h * tile_size), pygame.SRCALPHA)

    for biome_id in set(chunk.layers["biome"]):
        if biome_id not in AUTOTILED_BIOMES:
            continue

        for local_y in range(chunk_h):
            for local_x in range(chunk_w):
                idx = local_y * chunk_w + local_x
                if chunk.layers["biome"][idx] != biome_id:
                    continue
                sprite = get_scaled_biome_sprite(world, chunk, biome_id, idx)
                if sprite is not None:
                    biome_surface.blit(sprite, (local_x * tile_size, local_y * tile_size))

    chunk.runtime["biome_surface"] = biome_surface
    return biome_surface


def get_chunk_surface(world, chunk):
    # Compose static terrain layers once per dirty chunk. Dynamic actors,
    # animation, and particles are drawn later in the frame.
    surface = chunk.runtime.get("surface")
    if surface is not None and not chunk.dirty:
        return surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    surface = pygame.Surface((chunk_w * tile_size, chunk_h * tile_size), pygame.SRCALPHA)
    tilemap = get_chunk_tilemap(world, chunk)
    shallow_water_sprite = get_scaled_shallow_water_sprite(chunk)

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            surface.blit(shallow_water_sprite, (local_x * tile_size, local_y * tile_size))

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
    surface.blit(get_soil_surface(world, chunk), (0, 0))
    chunk.runtime["surface"] = surface
    chunk.dirty = False
    return surface


def ensure_chunk_water_objects(chunk):
    runtime_water_objects = chunk.runtime.get("water_objects")
    if runtime_water_objects is None:
        runtime_water_objects = {}
        chunk.runtime["water_objects"] = runtime_water_objects

    frames = get_water_frames()
    chunk_w, chunk_h = chunk.chunk_size
    current_keys = set()

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = local_y * chunk_w + local_x
            if chunk.layers["terrain"][idx] != -1:
                continue
            if is_deep_water_tile(chunk, local_x, local_y):
                continue
            world_tile = chunk.get_world_tile(local_x, local_y)
            current_keys.add(world_tile)
            if world_tile not in runtime_water_objects:
                runtime_water_objects[world_tile] = WaterTile(
                    world_pos=(world_tile[0] * chunk.tile_size, world_tile[1] * chunk.tile_size),
                    tile_size=chunk.tile_size,
                    frames=frames,
                )

    for stale_key in list(runtime_water_objects.keys()):
        if stale_key not in current_keys:
            del runtime_water_objects[stale_key]

    return list(runtime_water_objects.values())


def ensure_chunk_tree_objects(chunk):
    runtime_tree_objects = chunk.runtime.get("tree_objects")
    if runtime_tree_objects is None:
        runtime_tree_objects = {}
        chunk.runtime["tree_objects"] = runtime_tree_objects

    tree_records = [prop for prop in chunk.props if isinstance(prop, dict) and prop.get("type") == "tree"]
    current_keys = {(record.get("world_tile"), record.get("species")) for record in tree_records}

    for stale_key in list(runtime_tree_objects.keys()):
        if stale_key not in current_keys:
            del runtime_tree_objects[stale_key]

    for record in tree_records:
        key = (record.get("world_tile"), record.get("species"))
        if key not in runtime_tree_objects:
            runtime_tree_objects[key] = Tree.from_tree_record(
                tree_record=record,
                groups=None,
                path_find=None,
                c_s=chunk.chunk_size,
                show=True,
            )

    return list(runtime_tree_objects.values())


def ensure_chunk_house_objects(chunk):
    runtime_house_objects = chunk.runtime.get("house_objects")
    if runtime_house_objects is None:
        runtime_house_objects = {}
        chunk.runtime["house_objects"] = runtime_house_objects

    house_records = [prop for prop in chunk.props if isinstance(prop, dict) and prop.get("type") == "house"]
    current_keys = {record.get("id") for record in house_records}

    for stale_key in list(runtime_house_objects.keys()):
        if stale_key not in current_keys:
            del runtime_house_objects[stale_key]

    for record in house_records:
        key = record.get("id")
        if key not in runtime_house_objects:
            runtime_house_objects[key] = House(record)

    return list(runtime_house_objects.values())


def ensure_chunk_environment_objects(chunk):
    runtime_environment_objects = chunk.runtime.get("environment_objects")
    if runtime_environment_objects is None:
        runtime_environment_objects = {}
        chunk.runtime["environment_objects"] = runtime_environment_objects

    for record in chunk.props:
        if not (
            isinstance(record, dict)
            and record.get("type") == "environment"
            and record.get("removed", False)
            and not record.get("tile_cleared", False)
        ):
            continue
        local_tile = record.get("local_tile")
        if not local_tile:
            continue
        local_x, local_y = local_tile
        if not chunk.in_bounds(local_x, local_y):
            continue
        idx = chunk.get_index(local_x, local_y)
        decoration = chunk.layers["decoration"][idx]
        if isinstance(decoration, dict) and decoration.get("id") == record.get("id"):
            chunk.layers["decoration"][idx] = None
        if record.get("blocks_movement", False):
            chunk.layers["collision"][idx] = 0
        chunk.mark_dirty()
        record["tile_cleared"] = True

    prop_records = [
        prop
        for prop in chunk.props
        if isinstance(prop, dict) and prop.get("type") == "environment" and not prop.get("removed", False)
    ]
    current_keys = {record.get("id") for record in prop_records}

    for stale_key in list(runtime_environment_objects.keys()):
        if stale_key not in current_keys:
            del runtime_environment_objects[stale_key]

    for record in prop_records:
        key = record.get("id")
        if key not in runtime_environment_objects:
            runtime_environment_objects[key] = EnvironmentProp(record)

    return [prop for prop in runtime_environment_objects.values() if getattr(prop, "alive", True)]


def collect_chunk_objects(chunk, soil_layer=None):
    objects = []
    objects.extend(ensure_chunk_water_objects(chunk))
    objects.extend(ensure_chunk_tree_objects(chunk))
    objects.extend(ensure_chunk_house_objects(chunk))
    objects.extend(ensure_chunk_environment_objects(chunk))
    if soil_layer is not None:
        objects.extend(ensure_chunk_plant_objects(chunk, soil_layer))
    for prop in chunk.props:
        if hasattr(prop, "rect") and hasattr(prop, "image"):
            objects.append(prop)
    for entity in chunk.entities:
        if hasattr(entity, "rect"):
            objects.append(entity)
    return objects


def prewarm_chunk_runtime(chunk, world=None):
    ensure_chunk_tree_objects(chunk)
    ensure_chunk_house_objects(chunk)
    ensure_chunk_environment_objects(chunk)
    ensure_chunk_water_objects(chunk)
    if world is not None:
        get_chunk_surface(world, chunk)


def update_world_objects(visible_chunks, player, dt, soil_layer=None):
    near_chunks = {coord for coord, _, _, _ in visible_chunks}
    updated_ids = set()
    for _, chunk, _, _ in visible_chunks:
        for obj in collect_chunk_objects(chunk, soil_layer):
            obj_id = id(obj)
            if obj_id in updated_ids:
                continue
            updated_ids.add(obj_id)
            if hasattr(obj, "update"):
                try:
                    obj.update(dt, near_chunks=near_chunks, player_group=None)
                except TypeError:
                    obj.update(dt)


def collect_y_sorted_objects(visible_chunks, player, soil_layer=None, npc_manager=None):
    # Renderable actors from multiple chunks share one sort list so depth order
    # remains correct at chunk borders.
    objects = [player]
    seen = {id(player)}
    if npc_manager is not None:
        for npc in npc_manager.visible_npcs(visible_chunks):
            if id(npc) not in seen:
                seen.add(id(npc))
                objects.append(npc)
    for _, chunk, _, _ in visible_chunks:
        for obj in collect_chunk_objects(chunk, soil_layer):
            if getattr(obj, "render_layer", None) == "ground":
                continue
            if id(obj) in seen:
                continue
            seen.add(id(obj))
            objects.append(obj)
            if hasattr(obj, "iter_attached_objects"):
                for attached in obj.iter_attached_objects():
                    if attached is None or id(attached) in seen:
                        continue
                    seen.add(id(attached))
                    objects.append(attached)
    return objects


def collect_player_collision_objects(world):
    objects = []
    player_chunk = world.current_player_chunk or world.spawn_chunk
    for chunk_coord in world.get_chunks_near(player_chunk, radius=1):
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue
        for tree in ensure_chunk_tree_objects(chunk):
            if getattr(tree, "alive", True):
                objects.append(tree)
        objects.extend(ensure_chunk_house_objects(chunk))
        for prop in ensure_chunk_environment_objects(chunk):
            if prop.collision_box.width > 0 and prop.collision_box.height > 0:
                objects.append(prop)
    return objects


def collect_rock_collision_objects(world):
    rocks = []
    player_chunk = world.current_player_chunk or world.spawn_chunk
    for chunk_coord in world.get_chunks_near(player_chunk, radius=1):
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue
        for prop in ensure_chunk_environment_objects(chunk):
            if getattr(prop, "prop_type", "") == "rock":
                rocks.append(prop)
    return rocks


def collect_pickups_near_player(world, player):
    pickup_area = player.collision_box.inflate(world.tile_size, world.tile_size)
    player_chunk = world.current_player_chunk or world.world_to_chunk(player.center)
    for chunk_coord in world.get_chunks_near(player_chunk, radius=1):
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue
        for prop in ensure_chunk_environment_objects(chunk):
            if getattr(prop, "prop_type", "") in {"shell", "rock_piece"} and pickup_area.colliderect(prop.pickup_rect):
                if prop.pickup(player.inventory):
                    chunk.mark_dirty()
                    world.invalidate_chunk_render_cache(chunk.coord)
                    return True
    return False


def spawn_rock_piece_drops(chunk, rock, amount):
    if amount <= 0:
        return

    assets = list_environment_assets("rocks", "small") or ["rocks/small/r1.png"]
    world_tile = rock.record.get("world_tile", (0, 0))
    rng = random.Random(f"{rock.prop_id}:drops")
    offsets = [(-0.24, -0.10), (0.18, -0.04), (0.0, 0.20), (-0.04, -0.26)]

    for drop_index in range(amount):
        offset_x, offset_y = offsets[drop_index % len(offsets)]
        jitter_x = rng.uniform(-0.05, 0.05)
        jitter_y = rng.uniform(-0.05, 0.05)
        world_x = rock.rect.centerx + int((offset_x + jitter_x) * chunk.tile_size)
        world_y = rock.rect.centery + int((offset_y + jitter_y) * chunk.tile_size)
        local_x, local_y = chunk.world_to_local_tile(*world_tile)
        drop_id = f"{rock.prop_id}:piece:{drop_index}"
        record = {
            "type": "environment",
            "id": drop_id,
            "prop_type": "rock_piece",
            "variant": "piece",
            "asset": rng.choice(assets),
            "chunk": chunk.coord,
            "local_tile": (local_x, local_y),
            "world_tile": world_tile,
            "world_pos": (world_x, world_y),
            "pickup_item": "rock",
            "blocks_movement": False,
            "health": 0,
            "scale": 1,
        }
        chunk.props.append(record)

    chunk.runtime["environment_objects"] = {}
    chunk.mark_dirty()


def get_world_hint_font():
    global _WORLD_HINT_FONT
    if _WORLD_HINT_FONT is None:
        _WORLD_HINT_FONT = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 20)
    return _WORLD_HINT_FONT


def get_bobber_icon():
    global _BOBBER_ICON
    if _BOBBER_ICON is None:
        _BOBBER_ICON = pygame.image.load(rp("graphics", "icons", "bobber.png")).convert_alpha()
        _BOBBER_ICON = pygame.transform.scale(_BOBBER_ICON, (24, 24))
    return _BOBBER_ICON


def get_player_fishing_water_rect(world, player):
    if not hasattr(player, "get_facing_world_tile") or not hasattr(player, "can_fish_at_tile"):
        return None

    for distance in (1, 2):
        world_tile = player.get_facing_world_tile(distance=distance)
        if world_tile is not None and player.can_fish_at_tile(world_tile):
            tile_size = world.tile_size
            return pygame.Rect(
                world_tile[0] * tile_size,
                world_tile[1] * tile_size,
                tile_size,
                tile_size,
            )
    return None


def get_contextual_world_hint(world, player):
    seen = getattr(player, "world_hint_seen", set())
    if not isinstance(seen, set):
        seen = set()
        player.world_hint_seen = seen

    player_chunk = world.current_player_chunk or world.world_to_chunk(player.center)
    near_area = player.collision_box.inflate(world.tile_size, world.tile_size)
    tool_area = player.feet_collision_box.inflate(world.tile_size, world.tile_size)
    nearest_resource = None

    for chunk_coord in world.get_chunks_near(player_chunk, radius=1):
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue

        for prop in ensure_chunk_environment_objects(chunk):
            prop_type = getattr(prop, "prop_type", "")
            if prop_type in {"shell", "rock_piece"} and near_area.colliderect(prop.pickup_rect):
                if "collect_loose_item" not in seen:
                    return "collect_loose_item", "E: collect", prop.rect

            if prop_type == "rock" and prop.alive and tool_area.colliderect(prop.collision_box):
                nearest_resource = prop

        for tree in ensure_chunk_tree_objects(chunk):
            if tree.alive and tool_area.colliderect(tree.collision_box):
                nearest_resource = tree

    if nearest_resource is None:
        water_rect = get_player_fishing_water_rect(world, player)
        if water_rect is None:
            return None
        if getattr(player, "fishing_active", False):
            if getattr(player, "fishing_has_bite", False) and "reel_fishing_line" not in seen:
                return "reel_fishing_line", "Space: reel in", water_rect
            return None
        if getattr(player, "selected_tool", "") != "fishing rod" and "select_fishing_rod" not in seen:
            return "select_fishing_rod", "Q: select rod", water_rect
        if "cast_fishing_line" not in seen:
            return "cast_fishing_line", "Space: cast", water_rect
        return None

    if getattr(player, "selected_tool", "") != "axe" and "select_axe" not in seen:
        return "select_axe", "Q: select axe", nearest_resource.rect
    if "break_resource" not in seen:
        return "break_resource", "Space: break", nearest_resource.rect

    return None


def draw_player_world_hint(screen, world, player, camera, dt):
    hint = get_contextual_world_hint(world, player)
    if hint is None:
        return

    _, message, target_rect = hint

    player.world_hint_elapsed = getattr(player, "world_hint_elapsed", 0.0) + dt
    font = get_world_hint_font()

    text = font.render(message, True, (245, 242, 226))
    padding_x = 12
    padding_y = 6
    bubble = pygame.Rect(0, 0, text.get_width() + padding_x * 2, text.get_height() + padding_y * 2)

    anchor_x, anchor_y = camera.apply_point(target_rect.centerx, target_rect.top)
    bob = int(math.sin(player.world_hint_elapsed * 3.8) * 3)
    bubble.midbottom = (anchor_x, anchor_y - 14 + bob)
    bubble.x = max(8, min(screen.get_width() - bubble.width - 8, bubble.x))
    bubble.y = max(8, bubble.y)

    shadow = bubble.move(0, 3)
    pygame.draw.rect(screen, (7, 10, 16, 155), shadow, border_radius=8)
    pygame.draw.rect(screen, (20, 29, 43, 230), bubble, border_radius=8)
    pygame.draw.rect(screen, (209, 177, 87), bubble, 2, border_radius=8)
    screen.blit(text, text.get_rect(center=bubble.center))

    pointer_tip = (anchor_x, anchor_y - 6 + bob)
    pointer_tip = (
        max(bubble.left + 10, min(bubble.right - 10, pointer_tip[0])),
        pointer_tip[1],
    )
    pointer = [
        (pointer_tip[0] - 7, bubble.bottom - 1),
        (pointer_tip[0] + 7, bubble.bottom - 1),
        pointer_tip,
    ]
    pygame.draw.polygon(screen, (20, 29, 43), pointer)
    pygame.draw.line(screen, (209, 177, 87), pointer[0], pointer_tip, 2)
    pygame.draw.line(screen, (209, 177, 87), pointer[1], pointer_tip, 2)


def draw_fishing_overlay(screen, player, camera):
    if not getattr(player, "fishing_active", False) or player.fishing_bobber_pos is None:
        return

    bobber = get_bobber_icon()
    bobber_rect = bobber.get_rect(center=camera.apply_point(*player.fishing_bobber_pos))
    screen.blit(bobber, bobber_rect)

    line_start = camera.apply_point(player.rect.centerx, player.rect.centery - 8)
    pygame.draw.line(screen, (226, 221, 190), line_start, bobber_rect.center, 2)

    message = getattr(player, "fishing_message", "")
    if not message:
        return

    font = get_world_hint_font()
    color = (104, 236, 115) if getattr(player, "fishing_has_bite", False) else (245, 242, 226)
    text = font.render(message, True, color)
    text_rect = text.get_rect(midbottom=(bobber_rect.centerx, bobber_rect.top - 4))
    pygame.draw.rect(screen, (7, 10, 16, 180), text_rect.inflate(10, 6), border_radius=6)
    screen.blit(text, text_rect)


def draw_world(screen, world, player, camera, dt, soil_layer=None, npc_manager=None):
    screen.fill(BACKGROUND_COLOR)
    cam_x = int(camera.offset.x)
    cam_y = int(camera.offset.y)
    font = pygame.font.SysFont(None, 24)
    visible_chunks = []

    for chunk_coord, chunk in world.loaded_chunks.items():
        if chunk is None:
            continue
        chunk_left, chunk_top, _, _ = chunk.get_world_bounds()
        chunk_w, chunk_h = chunk.chunk_size
        tile_size = chunk.tile_size
        chunk_right = chunk_left + chunk_w * tile_size
        chunk_bottom = chunk_top + chunk_h * tile_size

        if (
            chunk_right <= cam_x
            or chunk_left >= cam_x + SCREEN_WIDTH
            or chunk_bottom <= cam_y
            or chunk_top >= cam_y + SCREEN_HEIGHT
        ):
            continue

        visible_chunks.append((chunk_coord, chunk, chunk_left, chunk_top))

    visible_chunks.sort(key=lambda item: (item[0][1], item[0][0]))
    update_world_objects(visible_chunks, player, dt, soil_layer)

    for chunk_coord, chunk, chunk_left, chunk_top in visible_chunks:
        chunk_surface = get_chunk_surface(world, chunk)
        screen_x, screen_y = camera.apply_point(chunk_left, chunk_top)
        scaled_surface = pygame.transform.scale(
            chunk_surface,
            (
                int(chunk_surface.get_width() * camera.zoom),
                int(chunk_surface.get_height() * camera.zoom),
            ),
        )
        screen.blit(scaled_surface, (screen_x, screen_y))

        for water_obj in ensure_chunk_water_objects(chunk):
            screen.blit(water_obj.image, camera.apply(water_obj.rect))

        if chunk_coord in world.active_chunks:
            text = font.render(str(chunk_coord), True, TEXT_COLOR)
            screen.blit(text, (chunk_left - cam_x + 8, chunk_top - cam_y + 8))

    y_objects = collect_y_sorted_objects(visible_chunks, player, soil_layer, npc_manager)
    for obj in sorted(y_objects, key=lambda s: getattr(s, "sort_y", s.rect.bottom)):
        screen_rect = camera.apply(obj.rect)
        if hasattr(obj, "image"):
            screen.blit(obj.image, screen_rect)
            if getattr(obj, "prop_type", "") == "rock" and getattr(obj, "collision_box", None):
                pygame.draw.rect(screen, (255, 60, 60), camera.apply(obj.collision_box), 2)
            if obj is player and getattr(obj, "feet_collision_box", None):
                pygame.draw.rect(screen, (60, 180, 255), camera.apply(obj.feet_collision_box), 2)
            swim_visual = getattr(obj, "swim_visual", None)
            if swim_visual is not None and swim_visual.is_swimming():
                screen.blit(swim_visual.swim_wave, camera.apply(swim_visual.swim_wave_rect))
        else:
            pygame.draw.rect(screen, PLAYER_COLOR, screen_rect)

    draw_fishing_overlay(screen, player, camera)
    draw_player_world_hint(screen, world, player, camera, dt)

    player_chunk = world.world_to_chunk(player.center)
    screen.blit(font.render(f"Player world pos: {player.center}", True, TEXT_COLOR), (12, 12))
    screen.blit(font.render(f"Player chunk: {player_chunk}", True, TEXT_COLOR), (12, 38))
    screen.blit(font.render(f"{world.level_name}  Difficulty: {world.island.difficulty}", True, TEXT_COLOR), (12, 64))
    screen.blit(font.render(f"Loaded chunks: {len(world.loaded_chunks)}", True, TEXT_COLOR), (12, 90))
    screen.blit(font.render(f"Island chunks active: {len(world.active_chunks)}", True, TEXT_COLOR), (12, 116))
    screen.blit(font.render("N: sail to next island", True, TEXT_COLOR), (12, 142))
    if npc_manager is not None:
        screen.blit(font.render(f"NPCs: {len(npc_manager.npcs)}", True, TEXT_COLOR), (12, 168))


def draw_transition_overlay(screen, message, subtitle=None, alpha=170):
    overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
    overlay.fill((10, 10, 18, alpha))
    screen.blit(overlay, (0, 0))

    title_font = pygame.font.SysFont(None, 54)
    text = title_font.render(message, True, (245, 245, 245))
    screen.blit(text, text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 - 12)))

    if subtitle:
        sub_font = pygame.font.SysFont(None, 28)
        sub = sub_font.render(subtitle, True, (220, 220, 220))
        screen.blit(sub, sub.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2 + 24)))


def get_chunk_biome_name(chunk):
    counts = {}
    for biome_id in chunk.layers["biome"]:
        counts[biome_id] = counts.get(biome_id, 0) + 1
    dominant_biome = max(counts, key=counts.get)
    return BIOME_TABLE[dominant_biome]["name"]


class StartupFlow:
    def __init__(self, screen):
        self.screen = screen
        self.stage = "title"
        self.mode_index = 0
        self.modes = ["Island Voyage", "Story Mode"]
        self.seed_text = ""
        self.world_run = None
        self.customization_categories = ["skin", "clothes", "hair", "weapon"]
        self.customization_category_index = 0
        self.customization = {}
        self.assets = None
        self.world = None
        self.soil_layer = None
        self.hud = None
        self.npc_manager = None
        self.player = None
        self.camera = None
        self.last_player_chunk = None
        self.loading_progress = 0.0
        self.loading_label = ""
        self.loading_note = ""
        self.target_chunk_count = 0
        self.done = False

        startup_font_path = rp("font", "LycheeSoda.ttf")
        self.big_font = pygame.font.Font(startup_font_path, 78)
        self.title_font = pygame.font.Font(startup_font_path, 56)
        self.body_font = pygame.font.Font(startup_font_path, 28)
        self.small_font = pygame.font.Font(startup_font_path, 20)

    def handle_event(self, event):
        if event.type != pygame.KEYDOWN:
            return

        if self.stage == "title":
            if event.key in (pygame.K_RETURN, pygame.K_SPACE):
                self.stage = "mode"

        elif self.stage == "mode":
            if event.key in (pygame.K_UP, pygame.K_w):
                self.mode_index = (self.mode_index - 1) % len(self.modes)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.mode_index = (self.mode_index + 1) % len(self.modes)
            elif event.key == pygame.K_RETURN:
                if self.mode_index == 0:
                    self.stage = "seed"
                else:
                    self.loading_note = "Story mode is coming later."

        elif self.stage == "seed":
            if event.key == pygame.K_RETURN:
                self.begin_customization()
            elif event.key == pygame.K_BACKSPACE:
                self.seed_text = self.seed_text[:-1]
            elif event.key == pygame.K_ESCAPE:
                self.stage = "mode"
            else:
                if event.unicode.isdigit() or (event.unicode == "-" and not self.seed_text):
                    self.seed_text += event.unicode

        elif self.stage == "customize":
            if event.key in (pygame.K_LEFT, pygame.K_a):
                self.change_customization_option(-1)
            elif event.key in (pygame.K_RIGHT, pygame.K_d):
                self.change_customization_option(1)
            elif event.key in (pygame.K_UP, pygame.K_w):
                self.customization_category_index = (
                    self.customization_category_index - 1
                ) % len(self.customization_categories)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self.customization_category_index = (
                    self.customization_category_index + 1
                ) % len(self.customization_categories)
            elif event.key == pygame.K_RETURN:
                self.begin_loading()
            elif event.key == pygame.K_ESCAPE:
                self.stage = "seed"

    def get_selected_seed(self):
        if self.seed_text.strip() in ("", "-"):
            return 0
        return int(self.seed_text)

    def begin_loading(self):
        self.stage = "loading"
        self.loading_progress = 0.0
        self.loading_label = "Preparing voyage"
        self.loading_note = "Starting asset initialization..."
        self.world_run = None
        self.world = None
        self.soil_layer = None
        self.hud = None
        self.npc_manager = None
        self.player = None
        self.camera = None
        self.last_player_chunk = None
        self.target_chunk_count = 0

    def begin_customization(self):
        self.stage = "customize"
        if self.assets is None:
            self.assets = get_shared_assets()
        self.customization = self.assets.normalize_character_customization(self.customization)

    def get_customization_options(self, category):
        if self.assets is None:
            return []
        options = self.assets.get_character_options().get(category, [])
        if category == "weapon":
            return [None] + options
        return options

    def change_customization_option(self, direction):
        category = self.customization_categories[self.customization_category_index]
        options = self.get_customization_options(category)
        if not options:
            return

        current = self.customization.get(category)
        if current not in options:
            current = options[0]
        current_index = options.index(current)
        self.customization[category] = options[(current_index + direction) % len(options)]
    
    def update(self):
        if self.stage != "loading" or self.done:
            return

        if self.assets is None:
            self.loading_label = "Initializing assets"
            self.loading_note = "Loading sprite sheets and animation data..."
            self.assets = get_shared_assets()
            self.loading_progress = 0.15
            return

        if self.world is None:
            self.loading_label = "Creating island"
            self.loading_note = f"Generating island chain from seed {self.get_selected_seed()}..."
            self.world_run = WorldRun(seed=self.get_selected_seed())
            self.world = self.world_run.create_world(
                spawn_chunk=(0, 0),
                chunk_size=DEFAULT_CHUNK_SIZE,
                active_radius=DEFAULT_ACTIVE_RADIUS,
                tile_size=DEFAULT_TILE_SIZE,
            )
            self.soil_layer = SoilLayer(self.world)
            self.camera = Camera(SCREEN_WIDTH, SCREEN_HEIGHT, mode="edge")
            spawn_x, spawn_y = self.world.get_spawn_position()
            self.player = Player(
                (spawn_x, spawn_y),
                assets=self.assets,
                speed=100,
                visual_scale=WORLD_SCALE,
                soil_layer=self.soil_layer,
                customization=self.customization,
            )
            self.player.rock_drop_callback = spawn_rock_piece_drops
            self.hud = GameplayHUD(self.player, self.screen)
            self.world.update_active_chunks(self.player.center)
            self.target_chunk_count = max(1, len(self.world.target_loaded_chunks))
            self.loading_progress = 0.30
            return

        if self.world.chunk_load_queue:
            self.loading_label = "Loading world"
            remaining_before = len(self.world.chunk_load_queue)
            self.loading_note = f"Generating nearby chunks... {len(self.world.loaded_chunks)}/{self.target_chunk_count}"
            self.world.process_chunk_queue(
                max_per_frame=INITIAL_LOAD_BATCH,
                prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime(chunk, self.world),
            )
            if len(self.world.chunk_load_queue) < remaining_before:
                loaded_ratio = min(1.0, len(self.world.loaded_chunks) / self.target_chunk_count)
                self.loading_progress = 0.30 + loaded_ratio * 0.60
            return

        self.loading_label = "Launching"
        self.loading_note = f"Everything is in place. Landing on {self.world.level_name}..."
        if self.npc_manager is None:
            self.npc_manager = NPCManager(self.world, self.assets, count=15)
        self.loading_progress = 1.0
        self.last_player_chunk = self.world.world_to_chunk(self.player.center)
        self.done = True

    def draw(self):
        self.screen.fill(UI_BG)
        self.draw_background_swells()

        if self.stage == "title":
            self.draw_title_screen()
        elif self.stage == "mode":
            self.draw_mode_screen()
        elif self.stage == "seed":
            self.draw_seed_screen()
        elif self.stage == "customize":
            self.draw_customize_screen()
        elif self.stage == "loading":
            self.draw_loading_screen()

    def draw_background_swells(self):
        width, height = self.screen.get_size()
        for i, radius in enumerate((520, 380, 260)):
            surf = pygame.Surface((width, height), pygame.SRCALPHA)
            alpha = 22 + i * 12
            pygame.draw.circle(surf, (40, 80, 120, alpha), (width // 2, height + 80), radius)
            self.screen.blit(surf, (0, 0))

    def draw_center_panel(
        self,
        title,
        subtitle=None,
        footer=None,
        center_text=False,
        title_font=None,
        subtitle_font=None,
        size=None,
    ):
        if size:
            panel_w, panel_h = size
            panel = pygame.Rect(0, 0, min(panel_w, SCREEN_WIDTH - 80), min(panel_h, SCREEN_HEIGHT - 80))
        else:
            panel = pygame.Rect(0, 0, 600, 600)
        panel.center = (SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        pygame.draw.rect(self.screen, UI_PANEL, panel, border_radius=10)
        pygame.draw.rect(self.screen, UI_PANEL_ALT, panel, 2, border_radius=10)

        title_surf = (title_font or self.title_font).render(title, True, UI_TEXT)
        if center_text:
            title_rect = title_surf.get_rect(center=(panel.centerx, panel.y + 62))
        else:
            title_rect = title_surf.get_rect(topleft=(panel.x + 36, panel.y + 34))
        self.screen.blit(title_surf, title_rect)

        if subtitle:
            sub_surf = (subtitle_font or self.small_font).render(subtitle, True, UI_MUTED)
            if center_text:
                sub_rect = sub_surf.get_rect(center=(panel.centerx, panel.y + 106))
            else:
                sub_rect = sub_surf.get_rect(topleft=(panel.x + 38, panel.y + 86))
            self.screen.blit(sub_surf, sub_rect)

        if footer:
            foot_surf = self.small_font.render(footer, True, UI_MUTED)
            if center_text:
                foot_rect = foot_surf.get_rect(center=(panel.centerx, panel.bottom - 38))
            else:
                foot_rect = foot_surf.get_rect(topleft=(panel.x + 36, panel.bottom - 46))
            self.screen.blit(foot_surf, foot_rect)

        return panel

    def draw_title_screen(self):
        panel = self.draw_center_panel(
            "Oceans Apart",
            "A drifting world of islands, storms, and stories.",
            "Press Enter to begin",
            center_text=True,
            size=(600, 260),
        )
        subtitle = self.body_font.render("Set sail into a fresh world.", True, UI_ACCENT_2)
        self.screen.blit(subtitle, (panel.x + 160, panel.y + 148))

    def draw_mode_screen(self):
        panel = self.draw_center_panel(
            "Choose your mode",
            "Story mode stays visible for now, but island voyage is the playable path.",
            "Use ↑ ↓ and Enter",
            center_text=True,
            size=(600, 360),
        )
        start_y = panel.y + 150
        for i, mode in enumerate(self.modes):
            option_rect = pygame.Rect(panel.x + 36, start_y + i * 84, panel.width - 72, 58)
            selected = i == self.mode_index
            fill = UI_ACCENT if selected else UI_PANEL_ALT
            pygame.draw.rect(self.screen, fill, option_rect, border_radius=14)
            text_color = UI_BG if selected else UI_TEXT
            label = self.body_font.render(mode, True, text_color)
            self.screen.blit(label, label.get_rect(midleft=(option_rect.x + 20, option_rect.centery)))

            if mode == "Story Mode":
                badge = self.small_font.render("coming soon", True, UI_WARN if selected else UI_MUTED)
                self.screen.blit(badge, badge.get_rect(midright=(option_rect.right - 18, option_rect.centery)))

        if self.loading_note:
            note = self.small_font.render(self.loading_note, True, UI_ACCENT_2)
            self.screen.blit(note, (panel.x + 36, panel.bottom - 88))

    def draw_seed_screen(self):
        panel = self.draw_center_panel(
            "Voyage seed",
            "Enter a seed to generate an island chain. Leave it blank to use 0.",
            "Enter = customize    Esc = back",
            center_text=True,
            size=(600, 360),

        )
        input_rect = pygame.Rect(panel.x + 36, panel.y + 170, panel.width - 72, 74)
        pygame.draw.rect(self.screen, (12, 18, 29), input_rect, border_radius=14)
        pygame.draw.rect(self.screen, UI_ACCENT, input_rect, 2, border_radius=14)

        value = self.seed_text if self.seed_text else "0"
        value_surf = self.body_font.render(value, True, UI_TEXT)
        self.screen.blit(value_surf, (input_rect.x + 18, input_rect.y + 20))

        hint = self.small_font.render("Examples: 0, 1392, 8675309, -17", True, UI_MUTED)
        self.screen.blit(hint, (panel.x + 38, input_rect.bottom + 18))

    def draw_customize_screen(self):
        panel = self.draw_center_panel(
            "Customize",
            "Choose your look before landing.",
            "Up/Down = category    Left/Right = option    Enter = continue",
            center_text=True,
            size=(680, 500),

        )
        if self.assets is None:
            return

        preview_frames = self.assets.get_character_frames("down_idle", self.customization)
        preview_index = int((pygame.time.get_ticks() / 360) % len(preview_frames))
        preview = pygame.transform.scale(preview_frames[preview_index], (192, 192))
        preview_rect = preview.get_rect(center=(panel.centerx, panel.y + 168))
        pygame.draw.rect(self.screen, (12, 18, 29), preview_rect.inflate(26, 26), border_radius=12)
        pygame.draw.rect(self.screen, UI_ACCENT, preview_rect.inflate(26, 26), 2, border_radius=12)
        self.screen.blit(preview, preview_rect)

        start_y = panel.y + 292
        for index, category in enumerate(self.customization_categories):
            selected = index == self.customization_category_index
            row = pygame.Rect(panel.x + 70, start_y + index * 40, panel.width - 140, 32)
            if selected:
                pygame.draw.rect(self.screen, UI_ACCENT, row, border_radius=8)

            label_color = UI_BG if selected else UI_TEXT
            value_color = UI_BG if selected else UI_ACCENT_2
            label = self.small_font.render(category.title(), True, label_color)
            options = self.get_customization_options(category)
            value = self.customization.get(category)
            value_text = "None" if value is None else str(value)
            if not options:
                value_text = "None"
            value_label = self.small_font.render(value_text, True, value_color)

            self.screen.blit(label, label.get_rect(midleft=(row.x + 14, row.centery)))
            self.screen.blit(value_label, value_label.get_rect(midright=(row.right - 14, row.centery)))

    def draw_loading_screen(self):
        panel = self.draw_center_panel(
            self.loading_label or "Preparing",
            self.loading_note or "Please wait...",
            None,
            center_text=True,
            title_font=self.body_font,
            subtitle_font=self.small_font,
            size=(620, 260),
        )
        bar_rect = pygame.Rect(panel.x + 54, panel.y + 142, panel.width - 108, 28)
        pygame.draw.rect(self.screen, (12, 18, 29), bar_rect, border_radius=12)
        fill_w = max(10, int(bar_rect.width * self.loading_progress)) if self.loading_progress > 0 else 0
        if fill_w:
            fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, fill_w, bar_rect.height)
            pygame.draw.rect(self.screen, UI_ACCENT, fill_rect, border_radius=12)

        percent = self.small_font.render(f"{int(self.loading_progress * 100)}%", True, UI_TEXT)
        self.screen.blit(percent, (bar_rect.right - percent.get_width(), bar_rect.bottom + 12))


def bind_player_to_world(player, world, soil_layer):
    spawn_x, spawn_y = world.get_spawn_position()
    player.pos = pygame.Vector2(spawn_x, spawn_y)
    player.rect.midbottom = (round(spawn_x), round(spawn_y))
    player.sync_collision_boxes()
    player.direction.update(0, 0)
    player.soil_layer = soil_layer
    player.swim_visual.bind_world(world)
    player.rock_drop_callback = spawn_rock_piece_drops


def load_next_island(world_run, player, assets, screen):
    world_run.advance()
    world = world_run.create_world(
        spawn_chunk=(0, 0),
        chunk_size=DEFAULT_CHUNK_SIZE,
        active_radius=DEFAULT_ACTIVE_RADIUS,
        tile_size=DEFAULT_TILE_SIZE,
    )
    soil_layer = SoilLayer(world)
    bind_player_to_world(player, world, soil_layer)
    hud = GameplayHUD(player, screen)
    world.update_active_chunks(player.center)
    return world, soil_layer, hud, None, world.world_to_chunk(player.center)


def run_game_loop(
    screen,
    clock,
    world_run,
    world,
    player,
    camera,
    last_player_chunk,
    assets,
    soil_layer=None,
    hud=None,
    npc_manager=None,
):
    # The main loop owns input, simulation updates, chunk activation, and final
    # draw calls for the active game session.
    transition_active = False
    transition_message = ""
    transition_subtitle = ""
    weather = WeatherSystem(screen.get_size())

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if hud is not None:
                hud.handle_event(event)
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    camera.zoom_in(0.1)
                elif event.key == pygame.K_MINUS:
                    camera.zoom_out(0.1)
                elif event.key == pygame.K_n:
                    world, soil_layer, hud, npc_manager, last_player_chunk = load_next_island(
                        world_run,
                        player,
                        assets,
                        screen,
                    )
                    transition_active = True
                    transition_message = f"Landing on {world.level_name}"
                    transition_subtitle = f"Difficulty {world.island.difficulty}"
                elif event.key in (pygame.K_e, pygame.K_p) and getattr(player, "pickup_cooldown", 0) <= 0:
                    if collect_pickups_near_player(world, player):
                        player.pickup_cooldown = 0.25
                        player.world_hint_seen.add("collect_loose_item")
                        if event.key == pygame.K_e:
                            player.seed_switch_cooldown = 0.2
                hint = get_contextual_world_hint(world, player)
                if hint is not None and event.key in WORLD_HINT_KEYS:
                    hint_id, _, _ = hint
                    if event.key in WORLD_HINT_ACK_KEYS.get(hint_id, set()):
                        player.world_hint_seen.add(hint_id)

        if not transition_active:
            player.update(dt, collect_player_collision_objects(world))
            weather.update(dt, soil_layer)
            if soil_layer is not None:
                soil_layer.update(dt, weather.time)
                soil_layer.harvest_colliding(player.collision_box, player)
            camera.update(player)
            new_player_chunk = world.world_to_chunk(player.center)

            if new_player_chunk != last_player_chunk:
                world.update_active_chunks(player.center)
                last_player_chunk = new_player_chunk
            else:
                world.update_active_chunks(player.center)
        else:
            camera.update(player)
            world.update_active_chunks(player.center)
            weather.update(dt, soil_layer)
            if soil_layer is not None:
                soil_layer.update(dt, weather.time)

        if world.chunk_load_queue:
            world.process_chunk_queue(
                max_per_frame=INITIAL_LOAD_BATCH,
                prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime(chunk, world),
            )

        if transition_active and not world.chunk_load_queue:
            transition_active = False

        if npc_manager is None and not world.chunk_load_queue:
            npc_manager = NPCManager(world, assets, count=15)

        if npc_manager is not None:
            npc_manager.update(dt)

        draw_world(screen, world, player, camera, dt, soil_layer, npc_manager)
        weather.draw(screen)
        if hud is not None:
            hud.draw(world, npc_manager)
        if transition_active:
            draw_transition_overlay(screen, transition_message, transition_subtitle, alpha=165)
        pygame.display.flip()


def main():
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.NOFRAME)
    pygame.display.set_caption("Oceans Apart")
    clock = pygame.time.Clock()
    startup = StartupFlow(screen)

    in_startup = True
    while in_startup:
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and startup.stage == "title":
                pygame.quit()
                return
            startup.handle_event(event)

        startup.update()
        startup.draw()
        pygame.display.flip()

        if startup.done:
            in_startup = False

    run_game_loop(
        screen,
        clock,
        startup.world_run,
        startup.world,
        startup.player,
        startup.camera,
        startup.last_player_chunk,
        startup.assets,
        startup.soil_layer,
        startup.hud,
        startup.npc_manager,
    )

    pygame.quit()


if __name__ == "__main__":
    main()
