"""Creation, synchronization, updates, collisions, and pickups for world objects."""

import inspect
import random

from entities.environment_prop import (
    EnvironmentProp,
    get_environment_image,
    list_environment_assets,
)
from entities.animal import FarmAnimal
from entities.house import House, get_house_asset_names, get_house_image
from entities.market import ensure_chunk_market_stalls
from entities.tree import Tree, prewarm_tree_visual_cache
from inventory_item import Item
from data.content_manifest import ORE_ASSETS, ROCK_ASSETS
from world.soil import ensure_chunk_plant_objects
from world.fence import ensure_chunk_fence_collisions
from world.water import WaterTile

from gameplay.assets import get_water_frames
from gameplay.terrain import (
    get_biome_surface,
    get_chunk_surface,
    get_deep_ocean_surface,
    get_dock_surface,
    get_fence_surface,
    get_path_surface,
    is_deep_water_tile,
    preload_world_render_assets,
)
from world.soil import get_soil_surface


_UPDATE_ACCEPTS_CHUNK_CONTEXT = {}
ECOLOGY_MAINTENANCE_INTERVAL = 45.0
MIN_WEEDS_PER_CHUNK = 8
MIN_BUSHES_PER_CHUNK = 4
MIN_LIVING_TREES_PER_CHUNK = 6
PLACEABLE_ENVIRONMENT_PROPS = {
    "crate": {
        "asset": "props/crates/1.png",
        "blocks_movement": True,
        "health": 2,
    },
    "hay": {
        "asset": "props/general/hay.png",
        "blocks_movement": False,
        "health": 0,
    },
    "wheelbarrow": {
        "asset": "props/general/wheelbarrow.png#0",
        "blocks_movement": True,
        "health": 0,
    },
}


def prewarm_runtime_asset_caches():
    """Pay one-time world visual loading costs before gameplay starts."""
    preload_world_render_assets()
    prewarm_tree_visual_cache()
    for asset_name in get_house_asset_names():
        get_house_image(asset_name)

    environment_folders = (
        ("shells",),
        ("flowers",),
        ("thickets", "weeds"),
        ("thickets", "bushes", "small"),
        ("thickets", "bushes", "big"),
        ("props", "flowers_pot_fenced"),
        ("props", "pots"),
        ("props", "buckets"),
        ("props", "crates"),
        ("props", "general"),
    )
    for folder in environment_folders:
        for asset_path in list_environment_assets(*folder):
            get_environment_image(asset_path)
    for rock in ROCK_ASSETS.values():
        for asset_path in rock.assets:
            get_environment_image(asset_path)
        get_environment_image(rock.drop_asset)
    for ore in ORE_ASSETS.values():
        get_environment_image(
            ore.path.removeprefix("graphics/sprites/environment/")
        )

REMOVAL_PICKUP_DROPS = {
    "bush": ("weed", 2),
}

PICKUP_EFFECTS = {
    "coin": "coin",
    "gem": "gem",
    "flower": "petal",
    "shell": "shell",
    "rock_piece": "rock",
    "coal_ore": "rock",
    "iron_ore": "rock",
    "gold_ore": "gem",
    "diamond_ore": "gem",
    "ruby_ore": "gem",
    "blue_sapphire_ore": "gem",
}


def update_world_object(obj, dt, near_chunks):
    update = getattr(obj, "update", None)
    if update is None:
        return

    object_type = type(obj)
    accepts_context = _UPDATE_ACCEPTS_CHUNK_CONTEXT.get(object_type)
    if accepts_context is None:
        parameters = inspect.signature(update).parameters.values()
        accepts_context = any(
            parameter.name == "near_chunks"
            or parameter.kind == inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )
        _UPDATE_ACCEPTS_CHUNK_CONTEXT[object_type] = accepts_context

    if accepts_context:
        update(dt, near_chunks=near_chunks, player_group=None)
    else:
        update(dt)


def can_place_environment_prop_at(world, world_tile, prop_type):
    if prop_type not in PLACEABLE_ENVIRONMENT_PROPS or world_tile is None:
        return False
    chunk_w, chunk_h = world.chunk_size
    world_x, world_y = int(world_tile[0]), int(world_tile[1])
    chunk = world.loaded_chunks.get((world_x // chunk_w, world_y // chunk_h))
    if chunk is None:
        return False
    local_x, local_y = world_x % chunk_w, world_y % chunk_h
    index = chunk.get_index(local_x, local_y)
    return (
        chunk.layers["terrain"][index] >= 0
        and chunk.layers["collision"][index] == 0
        and chunk.layers["decoration"][index] is None
        and chunk.layers["path"][index] == 0
        and chunk.layers["fence"][index] == 0
        and chunk.layers["dock"][index] is None
        and chunk.layers["soil"][index] == 0
        and chunk.layers["plant"][index] is None
    )


def set_environment_prop_at(world, world_tile, prop_type):
    if not can_place_environment_prop_at(world, world_tile, prop_type):
        return False
    definition = PLACEABLE_ENVIRONMENT_PROPS[prop_type]
    chunk_w, chunk_h = world.chunk_size
    world_x, world_y = int(world_tile[0]), int(world_tile[1])
    chunk = world.loaded_chunks[(world_x // chunk_w, world_y // chunk_h)]
    local_x, local_y = world_x % chunk_w, world_y % chunk_h
    counter = int(chunk.save_data["flags"].get("placed_prop_counter", 0))
    prop_id = f"player:{chunk.coord}:{counter}:{prop_type}"
    record = {
        "type": "environment",
        "id": prop_id,
        "prop_type": prop_type,
        "variant": "",
        "asset": definition["asset"],
        "chunk": chunk.coord,
        "local_tile": (local_x, local_y),
        "world_tile": (world_x, world_y),
        "world_pos": (
            world_x * chunk.tile_size + chunk.tile_size // 2,
            (world_y + 1) * chunk.tile_size,
        ),
        "blocks_movement": definition["blocks_movement"],
        "health": definition["health"],
        "scale": 1,
        "player_placed": True,
    }
    chunk.props.append(record)
    chunk.save_data["placed_props"].append(record)
    chunk.save_data["flags"]["placed_prop_counter"] = counter + 1
    chunk.set_saved_tile(
        "decoration",
        local_x,
        local_y,
        {"type": "environment", "id": prop_id, "prop_type": prop_type},
    )
    if definition["blocks_movement"]:
        chunk.set_saved_tile("collision", local_x, local_y, 1)
    chunk.runtime["environment_objects"] = {}
    chunk.runtime.pop("_environment_objects_cache", None)
    chunk.mark_dirty()
    return True


def ensure_chunk_water_objects(chunk):
    # Keeps track of water objects
    runtime_water_objects = chunk.runtime.get("water_objects")
    if runtime_water_objects is None:
        runtime_water_objects = {}
        chunk.runtime["water_objects"] = runtime_water_objects

    cached = chunk.runtime.get("_water_objects_cache")
    if cached is not None and cached[0] is runtime_water_objects:
        return cached[1]

    frames = get_water_frames()
    chunk_w, chunk_h = chunk.chunk_size
    dock_layer = chunk.layers.get("dock")
    current_keys = set()

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = local_y * chunk_w + local_x
            if dock_layer is not None and dock_layer[idx] is not None:
                continue
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

    objects = tuple(runtime_water_objects.values())
    chunk.runtime["_water_objects_cache"] = (runtime_water_objects, objects)
    return objects


def ensure_chunk_tree_objects(chunk):
    # Keeps track of trees in chunks
    runtime_tree_objects = chunk.runtime.get("tree_objects")
    if runtime_tree_objects is None:
        runtime_tree_objects = {}
        chunk.runtime["tree_objects"] = runtime_tree_objects

    cached = chunk.runtime.get("_tree_objects_cache")
    if cached is not None and cached[0] is runtime_tree_objects:
        return cached[1]

    tree_records = [prop for prop in chunk.props if isinstance(prop, dict) and prop.get("type") == "tree"]
    current_keys = {
        (tuple(record.get("world_tile", ())), record.get("species"))
        for record in tree_records
    }

    for stale_key in list(runtime_tree_objects.keys()):
        if stale_key not in current_keys:
            del runtime_tree_objects[stale_key]

    for record in tree_records:
        key = (tuple(record.get("world_tile", ())), record.get("species"))
        if key not in runtime_tree_objects:
            runtime_tree_objects[key] = Tree.from_tree_record(
                tree_record=record,
                groups=None,
                path_find=None,
                c_s=chunk.chunk_size,
                show=True,
            )

    objects = tuple(runtime_tree_objects.values())
    chunk.runtime["_tree_objects_cache"] = (runtime_tree_objects, objects)
    return objects


def remove_expired_tree_stumps(chunk):
    """Remove stumps whose display lifetime has elapsed from a chunk."""
    runtime_tree_objects = chunk.runtime.get("tree_objects", {})
    expired = [
        (key, tree)
        for key, tree in runtime_tree_objects.items()
        if getattr(tree, "expired", False)
    ]
    if not expired:
        return 0

    for key, tree in expired:
        record = tree.tree_data
        if record in chunk.props:
            chunk.props.remove(record)

        prop_id = record.get("id")
        if prop_id is not None:
            chunk.save_data["removed_props"].add(prop_id)
        chunk.save_data["placed_props"] = [
            prop
            for prop in chunk.save_data["placed_props"]
            if prop is not record and (prop_id is None or prop.get("id") != prop_id)
        ]

        local_tile = record.get("local_tile")
        if local_tile is not None:
            local_x, local_y = local_tile
            decoration = chunk.get_decoration_tile(local_x, local_y)
            owns_tile = isinstance(decoration, dict) and decoration.get("type") == "tree"
            if owns_tile:
                chunk.set_saved_tile("decoration", local_x, local_y, None)
            if owns_tile and record.get("blocks_movement", True):
                chunk.set_saved_tile("collision", local_x, local_y, 0)

        runtime_tree_objects.pop(key, None)

    chunk.references["props"] = {
        (prop["type"], prop.get("world_tile"), prop.get("species"))
        for prop in chunk.props
        if isinstance(prop, dict)
    }
    chunk.metadata["tree_count"] = sum(
        1
        for prop in chunk.props
        if isinstance(prop, dict) and prop.get("type") == "tree"
    )
    chunk.runtime.pop("_tree_objects_cache", None)
    chunk.mark_dirty()
    return len(expired)


def ensure_chunk_house_objects(chunk):
    # Keeps track of houses in a chunk
    runtime_house_objects = chunk.runtime.get("house_objects")
    if runtime_house_objects is None:
        runtime_house_objects = {}
        chunk.runtime["house_objects"] = runtime_house_objects

    cached = chunk.runtime.get("_house_objects_cache")
    if cached is not None and cached[0] is runtime_house_objects:
        return cached[1]

    house_records = [prop for prop in chunk.props if isinstance(prop, dict) and prop.get("type") == "house"]
    current_keys = {record.get("id") for record in house_records}

    for stale_key in list(runtime_house_objects.keys()):
        if stale_key not in current_keys:
            del runtime_house_objects[stale_key]

    for record in house_records:
        key = record.get("id")
        if key not in runtime_house_objects:
            runtime_house_objects[key] = House(record)

    objects = tuple(runtime_house_objects.values())
    chunk.runtime["_house_objects_cache"] = (runtime_house_objects, objects)
    return objects


def ensure_chunk_animal_objects(chunk):
    """Instantiate each generated animal once and retain its runtime state."""
    runtime_animal_objects = chunk.runtime.get("animal_objects")
    if runtime_animal_objects is None:
        runtime_animal_objects = {}
        chunk.runtime["animal_objects"] = runtime_animal_objects

    cached = chunk.runtime.get("_animal_objects_cache")
    if cached is not None and cached[0] is runtime_animal_objects:
        return cached[1]

    animal_records = [
        prop
        for prop in chunk.props
        if isinstance(prop, dict) and prop.get("type") == "animal"
    ]
    current_keys = {record.get("id") for record in animal_records}
    for stale_key in list(runtime_animal_objects):
        if stale_key not in current_keys:
            del runtime_animal_objects[stale_key]

    for record in animal_records:
        key = record.get("id")
        if key not in runtime_animal_objects:
            runtime_animal_objects[key] = FarmAnimal(record, chunk.tile_size)

    objects = tuple(runtime_animal_objects.values())
    chunk.runtime["_animal_objects_cache"] = (runtime_animal_objects, objects)
    return objects


def ensure_chunk_environment_objects(chunk):
    # Keeps track of environment objects/Props in a chunk
    runtime_environment_objects = chunk.runtime.get("environment_objects")
    if runtime_environment_objects is None:
        runtime_environment_objects = {}
        chunk.runtime["environment_objects"] = runtime_environment_objects

    cached = chunk.runtime.get("_environment_objects_cache")
    if cached is not None and cached[0] is runtime_environment_objects:
        removed = [prop for prop in cached[1] if not getattr(prop, "alive", True)]
        if not removed:
            return cached[1]
        records_to_finalize = [prop.record for prop in removed]
    else:
        records_to_finalize = chunk.props

    for record in records_to_finalize:
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
        prop_id = record.get("id")
        if prop_id is not None:
            chunk.save_data["removed_props"].add(prop_id)
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

    objects = tuple(
        prop for prop in runtime_environment_objects.values()
        if getattr(prop, "alive", True)
    )
    chunk.runtime["_environment_objects_cache"] = (runtime_environment_objects, objects)
    return objects


def remove_environment_prop_at(
    world,
    world_tile,
    prop_types=("weed",),
    *,
    player_inventory=None,
    pickup_item=None,
):
    """Remove the first matching environment prop at a world tile."""
    chunk_w, chunk_h = world.chunk_size
    world_x, world_y = int(world_tile[0]), int(world_tile[1])
    chunk = world.loaded_chunks.get((world_x // chunk_w, world_y // chunk_h))
    if chunk is None:
        return None

    local_x, local_y = world_x % chunk_w, world_y % chunk_h
    index = chunk.get_index(local_x, local_y)
    for record in chunk.props:
        if not (
            isinstance(record, dict)
            and record.get("type") == "environment"
            and record.get("prop_type") in prop_types
            and tuple(record.get("world_tile", ())) == (world_x, world_y)
            and not record.get("removed", False)
        ):
            continue

        default_item, pickup_amount = REMOVAL_PICKUP_DROPS.get(
            record.get("prop_type"),
            (record.get("pickup_item", record.get("prop_type")), 1),
        )
        item_name = pickup_item or default_item
        runtime_object = chunk.runtime.get("environment_objects", {}).get(record.get("id"))
        if player_inventory is not None and runtime_object is not None:
            runtime_object.add_to_inventory(
                player_inventory,
                item_name,
                pickup_amount,
            )
        elif player_inventory is not None:
            player_inventory.add_item_to_slot(
                Item(
                    item_name,
                    "",
                    True,
                    player_inventory.craft_system.return_craft_product(item_name),
                ),
                amount=pickup_amount,
            )

        record["removed"] = True
        record["tile_cleared"] = True
        chunk.save_data["removed_props"].add(record.get("id"))
        decoration = chunk.layers["decoration"][index]
        if isinstance(decoration, dict) and decoration.get("id") == record.get("id"):
            chunk.set_saved_tile("decoration", local_x, local_y, None)
        if record.get("blocks_movement", False):
            chunk.set_saved_tile("collision", local_x, local_y, 0)

        runtime_object = chunk.runtime.get("environment_objects", {}).pop(
            record.get("id"), None
        )
        if runtime_object is not None:
            runtime_object.remove()
        chunk.runtime.pop("_environment_objects_cache", None)
        chunk.mark_dirty()
        return record
    return None


def maintain_natural_resources(world, dt):
    """Occasionally replenish sparse weeds and trees on free loaded tiles."""
    elapsed = float(getattr(world, "_ecology_maintenance_elapsed", 0.0)) + dt
    if elapsed < ECOLOGY_MAINTENANCE_INTERVAL:
        world._ecology_maintenance_elapsed = elapsed
        return 0

    world._ecology_maintenance_elapsed = elapsed % ECOLOGY_MAINTENANCE_INTERVAL
    spawned = 0
    chunk_coords = getattr(world, "active_chunks", set()) or world.loaded_chunks.keys()
    for chunk_coord in tuple(chunk_coords):
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue
        spawned += chunk.replenish_natural_resources(
            world_seed=world.seed,
            minimum_weeds=MIN_WEEDS_PER_CHUNK,
            minimum_bushes=MIN_BUSHES_PER_CHUNK,
            minimum_trees=MIN_LIVING_TREES_PER_CHUNK,
            max_new=1,
        )
    return spawned


def collect_chunk_objects(chunk, soil_layer=None):
    # Collects all objets in a chunk
    objects = []
    objects.extend(ensure_chunk_water_objects(chunk))
    objects.extend(ensure_chunk_tree_objects(chunk))
    objects.extend(ensure_chunk_house_objects(chunk))
    objects.extend(ensure_chunk_market_stalls(chunk))
    objects.extend(ensure_chunk_animal_objects(chunk))
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


def prewarm_chunk_runtime(chunk, world=None, soil_layer=None):
    """Build a completely finished chunk before it becomes playable."""
    if world is not None:
        get_chunk_surface(world, chunk)
    collect_chunk_objects(chunk, soil_layer)


def prewarm_chunk_runtime_step(chunk, world=None, soil_layer=None):
    """Advance one main-thread-safe chunk prewarm phase."""
    phase = int(chunk.runtime.get("prewarm_phase", 0))
    if phase >= 8:
        return True
    if phase == 0:
        ensure_chunk_tree_objects(chunk)
    elif phase == 1:
        ensure_chunk_house_objects(chunk)
        ensure_chunk_market_stalls(chunk)
        ensure_chunk_animal_objects(chunk)
    elif phase == 2:
        ensure_chunk_environment_objects(chunk)
    elif phase == 3:
        ensure_chunk_water_objects(chunk)
    elif phase == 4 and world is not None:
        get_deep_ocean_surface(world, chunk)
    elif phase == 5 and world is not None:
        get_biome_surface(world, chunk)
    elif phase == 6 and world is not None:
        get_path_surface(world, chunk)
        get_soil_surface(world, chunk)
        get_dock_surface(chunk)
        get_fence_surface(world, chunk)
    elif phase == 7:
        if world is not None:
            if chunk.runtime.pop("surface_stale", False):
                chunk.runtime["surface"] = None
                chunk.runtime.pop("camera_scaled_surface", None)
            get_chunk_surface(world, chunk)
        collect_chunk_objects(chunk, soil_layer)

    phase += 1
    chunk.runtime["prewarm_phase"] = phase
    return phase >= 8


def update_world_objects(visible_chunks, player, dt, soil_layer=None, objects_by_chunk=None):
    # Update object in every chunk.
    near_chunks = {coord for coord, _, _, _ in visible_chunks}
    updated_ids = set()
    for chunk_coord, chunk, _, _ in visible_chunks:
        chunk_objects = (
            objects_by_chunk[chunk_coord]
            if objects_by_chunk is not None
            else collect_chunk_objects(chunk, soil_layer)
        )
        for obj in chunk_objects:
            obj_id = id(obj)
            if obj_id in updated_ids:
                continue
            updated_ids.add(obj_id)
            update_world_object(obj, dt, near_chunks)
        remove_expired_tree_stumps(chunk)


def collect_y_sorted_objects(
    visible_chunks,
    player,
    soil_layer=None,
    npc_manager=None,
    objects_by_chunk=None,
    extra_objects=(),
):
    # Renderable actors from multiple chunks share one sort list so depth order
    # remains correct at chunk borders.
    objects = [] if getattr(player, "hidden_by_vessel", False) else [player]
    seen = {id(player)}
    if npc_manager is not None:
        for npc in npc_manager.visible_npcs(visible_chunks):
            if id(npc) not in seen:
                seen.add(id(npc))
                objects.append(npc)
    for obj in extra_objects or ():
        if id(obj) not in seen:
            seen.add(id(obj))
            objects.append(obj)
    for chunk_coord, chunk, _, _ in visible_chunks:
        chunk_objects = (
            objects_by_chunk[chunk_coord]
            if objects_by_chunk is not None
            else collect_chunk_objects(chunk, soil_layer)
        )
        for obj in chunk_objects:
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
    # Return objects that the player collides with.
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
        objects.extend(ensure_chunk_market_stalls(chunk))
        for prop in ensure_chunk_environment_objects(chunk):
            if prop.collision_box.width > 0 and prop.collision_box.height > 0:
                objects.append(prop)
        objects.extend(ensure_chunk_fence_collisions(chunk, world))
    return objects


def collect_rock_collision_objects(world):
    # Return rocks that the player collides with.
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
    # Return true if the player is next to a collectable prop or ripe tree.
    pickup_area = player.get_interaction_box(world.tile_size)
    player_chunk = getattr(world, "current_player_chunk", None) or getattr(world, "spawn_chunk", None)
    if player_chunk is None and hasattr(world, "world_to_chunk"):
        player_chunk = world.world_to_chunk(player.center)
    if player_chunk is not None and hasattr(world, "get_chunks_near"):
        chunk_coords = world.get_chunks_near(player_chunk, radius=1)
    else:
        chunk_coords = tuple(world.loaded_chunks)
    for chunk_coord in chunk_coords:
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue
        for prop in ensure_chunk_environment_objects(chunk):
            if pickup_area.colliderect(prop.pickup_rect):
                pickup_name = prop.record.get("pickup_item", prop.prop_type)
                pickup_pos = prop.rect.center
                if prop.pickup(player):
                    effect_name = PICKUP_EFFECTS.get(pickup_name) or PICKUP_EFFECTS.get(prop.prop_type)
                    effect_manager = getattr(player, "effect_manager", None)
                    if prop.prop_type == "rock_piece" and effect_manager is not None:
                        effect_manager.burst(effect_name or "rock", pickup_pos, count=5, speed=(24, 58))
                    elif effect_name is not None and hasattr(player, "emit_effect"):
                        player.emit_effect(effect_name, pickup_pos)
                    chunk.save_data["removed_props"].add(prop.prop_id)
                    chunk.mark_dirty()
                    return True
        for tree in ensure_chunk_tree_objects(chunk):
            if (
                getattr(tree, "alive", False)
                and pickup_area.colliderect(tree.collision_box)
                and tree.collect_fruit(player.inventory) > 0
            ):
                if hasattr(player, "emit_effect"):
                    player.emit_effect("fruit", tree.collision_box.center)
                chunk.mark_dirty()
                return True
    return False


def spawn_rock_piece_drops(chunk, rock, amount):
    # Break rocks before picking them up.
    if amount <= 0:
        return

    drop_asset = rock.record.get(
        "drop_asset",
        ROCK_ASSETS["land_rock"].drop_asset,
    )
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
            "asset": drop_asset,
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
