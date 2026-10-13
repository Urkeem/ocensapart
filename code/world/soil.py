"""Farm soil, watering, planting, crop growth, and soil rendering helpers."""

import pygame

from TileMapManager import TileMap
from inventory_item import Item
from sprites import WorldObject
from utils import rp
from data.content_manifest import CROP_ASSETS
from data.crops import CROP_DEFINITIONS, STARTER_CROP_IDS, is_crop_unlocked
from gameplay.events import CropHarvested, CropWatered, next_event_id, publish_from


SOIL_TILESET_FILE = "Tilesets/loam.png"
SOIL_SOURCE_TILE_SIZE = 32
SOIL_WATER_TILESET_FILE = "Tilesets/plant_water.png"
CROP_SOURCE_SIZE = 16
CROP_GROWTH_COLUMNS = range(2, 8)
CROP_WORLD_SCALE = 2
MINUTES_PER_DAY = 1440
WATER_DURATION_MINUTES = MINUTES_PER_DAY
PLANT_DRY_DEATH_MINUTES = MINUTES_PER_DAY * 2
UNUSED_PLAYER_SOIL_LIFETIME_MINUTES = MINUTES_PER_DAY * 7
SOIL_UPDATE_INTERVAL_MINUTES = 10
PLANT_MAX_GROWTH_DAYS = {
    crop_id: crop.growth_days
    for crop_id, crop in CROP_DEFINITIONS.items()
}


def load_crop_growth_frames():
    """Load growth cells 2..7 from every 16px crop sheet."""
    crops = {}
    for crop_id, asset in CROP_ASSETS.items():
        sheet = pygame.image.load(rp(*asset.path.split("/"))).convert_alpha()
        if sheet.get_width() < 8 * CROP_SOURCE_SIZE or sheet.get_height() < 2 * CROP_SOURCE_SIZE:
            continue
        crops[crop_id] = tuple(
            sheet.subsurface(
                (
                    column * CROP_SOURCE_SIZE,
                    CROP_SOURCE_SIZE,
                    CROP_SOURCE_SIZE,
                    CROP_SOURCE_SIZE,
                )
            ).copy()
            for column in CROP_GROWTH_COLUMNS
        )
    return crops


def _get_neighbor_soil_value(neighbor_chunk, local_x, local_y):
    idx = neighbor_chunk.get_index(local_x, local_y)
    return neighbor_chunk.layers["soil"][idx]


def _water_value(water_data):
    return 1 if water_data == 1 or isinstance(water_data, dict) else 0


def _get_neighbor_soil_water_value(neighbor_chunk, local_x, local_y):
    idx = neighbor_chunk.get_index(local_x, local_y)
    if neighbor_chunk.layers["soil"][idx] != 1:
        return 0
    return _water_value(neighbor_chunk.layers["soil_water"][idx])


class Plant(WorldObject):
    def __init__(self, plant_type, pos, frames, tile_size):
        self.plant_type = plant_type
        crop_size = min(tile_size, CROP_SOURCE_SIZE * CROP_WORLD_SCALE)
        self.frames = [pygame.transform.scale(frame, (crop_size, crop_size)) for frame in frames]
        self.age = 0.0
        self.max_age = len(self.frames) - 1
        self.harvestable = False
        super().__init__(pos, self.frames[0], anchor="center")
        self.name = "crop"

    def grow(self, dt, watered):
        if not watered or self.harvestable:
            return

        self.age = min(self.max_age, self.age + GROW_SPEED.get(self.plant_type, 0.2) * dt)
        if self.age >= self.max_age:
            self.harvestable = True

        anchor = self.rect.center
        self.image_base = self.frames[int(self.age)]
        self.image = self.image_base.copy()
        self.rect = self._make_rect(anchor)
        self.mask = pygame.mask.from_surface(self.image_base)


class SoilLayer:
    def __init__(self, world):
        self.world = world
        self.soil_surfs = {}
        self.current_time_minutes = 360.0
        self.current_day = 1
        self._last_update_bucket = None
        self.plant_frames = load_crop_growth_frames()
        self.available_crops = tuple(
            crop_id for crop_id in STARTER_CROP_IDS if crop_id in self.plant_frames
        )
        self.hoe_sound = self._load_sound("audio/hoe.wav", 0.1)
        self.water_sound = self._load_sound("audio/water.mp3", 0.2)
        self.plant_sound = self._load_sound("audio/plant.wav", 0.2)

    @staticmethod
    def _load_sound(path, volume):
        try:
            from utils import rp
            sound = pygame.mixer.Sound(rp(path))
            sound.set_volume(volume)
            return sound
        except pygame.error:
            return None

    def _play(self, sound):
        if sound is not None:
            sound.play()

    def _absolute_minutes(self, game_time=None):
        if game_time is not None:
            return ((game_time.day - 1) * MINUTES_PER_DAY) + game_time.time
        return self.current_time_minutes

    def _current_day(self, game_time=None):
        if game_time is not None:
            return game_time.day
        return self.current_day

    def _sync_time(self, game_time=None):
        if game_time is None:
            return
        self.current_time_minutes = self._absolute_minutes(game_time)
        self.current_day = game_time.day

    def _water_entry(self, watered_at, watered_day=None):
        return {
            "watered_at": watered_at,
            "expires_at": watered_at + WATER_DURATION_MINUTES,
            "watered_day": self.current_day if watered_day is None else watered_day,
        }

    def _is_watered(self, water_data, current_time):
        if water_data == 1:
            return True
        if not isinstance(water_data, dict):
            return False
        return current_time <= water_data.get("expires_at", 0)

    def _set_water(self, chunk, local_x, local_y, current_time, current_day):
        idx = chunk.get_index(local_x, local_y)
        water_entry = self._water_entry(current_time, current_day)
        chunk.set_saved_tile("soil_water", local_x, local_y, water_entry)
        plant = chunk.layers["plant"][idx]
        if plant is not None:
            plant["last_watered_at"] = current_time
            plant["last_watered_day"] = current_day
            self._touch_player_soil(chunk, local_x, local_y, current_time)

    @staticmethod
    def _player_soil_activity(chunk):
        return chunk.save_data["flags"].setdefault("player_soil_last_used", {})

    def _touch_player_soil(self, chunk, local_x, local_y, current_time, *, create=False):
        activity = self._player_soil_activity(chunk)
        key = (local_x, local_y)
        if create or key in activity:
            activity[key] = current_time

    def _plant_growth_ratio(self, plant):
        max_days = max(1, plant.get("max_growth_days", PLANT_MAX_GROWTH_DAYS.get(plant["type"], 4)))
        return min(1.0, plant.get("growth_days", 0) / max_days)

    def world_to_tile(self, world_pos):
        return int(world_pos[0] // self.world.tile_size), int(world_pos[1] // self.world.tile_size)

    def get_chunk_and_local(self, world_tile):
        chunk_w, chunk_h = self.world.chunk_size
        chunk_coord = (world_tile[0] // chunk_w, world_tile[1] // chunk_h)
        local = (world_tile[0] % chunk_w, world_tile[1] % chunk_h)
        chunk = self.world.loaded_chunks.get(chunk_coord)
        return chunk, local

    def get_tile_state(self, world_tile, game_time=None):
        """Return the authoritative farm state for one loaded world tile."""
        chunk, (local_x, local_y) = self.get_chunk_and_local(world_tile)
        if chunk is None or not chunk.in_bounds(local_x, local_y):
            return None
        idx = chunk.get_index(local_x, local_y)
        plant = chunk.layers["plant"][idx]
        current_time = self._absolute_minutes(game_time)
        return {
            "chunk": chunk,
            "local": (local_x, local_y),
            "index": idx,
            "tilled": chunk.layers["soil"][idx] == 1,
            "watered": self._is_watered(chunk.layers["soil_water"][idx], current_time),
            "plant": plant,
            "harvestable": bool(plant and plant.get("age", 0.0) >= 1.0),
        }

    def can_till(self, chunk, local_x, local_y):
        idx = chunk.get_index(local_x, local_y)
        return (
            chunk.layers["terrain"][idx] > 0
            and chunk.layers["collision"][idx] == 0
            and chunk.layers["decoration"][idx] is None
            and chunk.layers["path"][idx] == 0
            and chunk.layers["fence"][idx] == 0
            and chunk.layers["soil"][idx] == 0
        )

    def can_till_at_tile(self, world_tile):
        chunk, (local_x, local_y) = self.get_chunk_and_local(world_tile)
        return bool(chunk and chunk.in_bounds(local_x, local_y) and self.can_till(chunk, local_x, local_y))

    def can_water_at_tile(self, world_tile, game_time=None):
        state = self.get_tile_state(world_tile, game_time)
        return bool(state and state["tilled"] and not state["watered"])

    def can_plant_at_tile(self, world_tile, seed, game_state=None):
        state = self.get_tile_state(world_tile)
        return bool(
            seed in self.plant_frames
            and is_crop_unlocked(seed, game_state)
            and state
            and state["tilled"]
            and state["plant"] is None
        )

    def can_harvest_at_tile(self, world_tile):
        state = self.get_tile_state(world_tile)
        return bool(state and state["harvestable"])

    def till_at(self, world_pos):
        world_tile = self.world_to_tile(world_pos)
        chunk, local = self.get_chunk_and_local(world_tile)
        if chunk is None:
            return False

        local_x, local_y = local
        idx = chunk.get_index(local_x, local_y)
        if not self.can_till(chunk, local_x, local_y):
            return False

        chunk.set_saved_tile("soil", local_x, local_y, 1)
        self._touch_player_soil(
            chunk,
            local_x,
            local_y,
            self.current_time_minutes,
            create=True,
        )
        self.world.invalidate_soil_chunk_and_neighbors(chunk.coord)
        self._play(self.hoe_sound)
        return True

    def water_at(self, world_pos, game_time=None, player=None):
        current_time = self._absolute_minutes(game_time)
        current_day = self._current_day(game_time)
        world_tile = self.world_to_tile(world_pos)
        chunk, local = self.get_chunk_and_local(world_tile)
        if chunk is None:
            return False

        local_x, local_y = local
        idx = chunk.get_index(local_x, local_y)
        if chunk.layers["soil"][idx] != 1 or self._is_watered(
            chunk.layers["soil_water"][idx], current_time
        ):
            return False

        self._set_water(chunk, local_x, local_y, current_time, current_day)
        self.world.invalidate_soil_chunk_and_neighbors(chunk.coord)
        self._play(self.water_sound)
        if player is not None:
            plant = chunk.layers["plant"][idx]
            game_state = getattr(player, "game_state", None)
            publish_from(
                player,
                CropWatered(
                    event_id=next_event_id(player, "crop_watered"),
                    crop_id=plant.get("type") if plant else None,
                    location_id=getattr(game_state, "current_location_id", "player_farm"),
                    world_tile=world_tile,
                ),
            )
        return True

    def plant_seed_at(self, world_pos, seed, game_time=None, game_state=None):
        if seed not in self.plant_frames or not is_crop_unlocked(seed, game_state):
            return False
        current_time = self._absolute_minutes(game_time)
        current_day = self._current_day(game_time)

        world_tile = self.world_to_tile(world_pos)
        chunk, local = self.get_chunk_and_local(world_tile)
        if chunk is None:
            return False

        local_x, local_y = local
        idx = chunk.get_index(local_x, local_y)
        if chunk.layers["soil"][idx] != 1 or chunk.layers["plant"][idx] is not None:
            return False

        plant_data = {
            "type": seed,
            "age": 0.0,
            "growth_days": 0,
            "max_growth_days": PLANT_MAX_GROWTH_DAYS.get(seed, 4),
            "planted_at": current_time,
            "planted_day": current_day,
            "last_growth_day": current_day,
            "last_watered_at": current_time if self._is_watered(chunk.layers["soil_water"][idx], current_time) else None,
            "last_watered_day": current_day if self._is_watered(chunk.layers["soil_water"][idx], current_time) else None,
            "dead": False,
        }
        chunk.set_saved_tile("plant", local_x, local_y, plant_data)
        self._touch_player_soil(chunk, local_x, local_y, current_time)
        self._play(self.plant_sound)
        return True

    def update(self, dt, game_time=None):
        self._sync_time(game_time)
        current_time = self.current_time_minutes
        current_day = self.current_day
        update_bucket = int(current_time // SOIL_UPDATE_INTERVAL_MINUTES)
        if update_bucket == self._last_update_bucket:
            return
        self._last_update_bucket = update_bucket

        for chunk in self.world.loaded_chunks.values():
            chunk_w, chunk_h = chunk.chunk_size
            changed = False
            for local_y in range(chunk_h):
                for local_x in range(chunk_w):
                    idx = chunk.get_index(local_x, local_y)
                    water_data = chunk.layers["soil_water"][idx]
                    if water_data == 1:
                        chunk.set_saved_tile(
                            "soil_water",
                            local_x,
                            local_y,
                            self._water_entry(current_time, current_day),
                        )
                        changed = True
                    elif isinstance(water_data, dict) and not self._is_watered(water_data, current_time):
                        chunk.set_saved_tile("soil_water", local_x, local_y, 0)
                        changed = True

                    plant = chunk.layers["plant"][idx]
                    activity = self._player_soil_activity(chunk)
                    activity_key = (local_x, local_y)
                    last_used = activity.get(activity_key)
                    if (
                        chunk.layers["soil"][idx] == 1
                        and plant is None
                        and last_used is not None
                        and current_time - last_used >= UNUSED_PLAYER_SOIL_LIFETIME_MINUTES
                    ):
                        chunk.set_saved_tile("soil", local_x, local_y, 0)
                        chunk.set_saved_tile("soil_water", local_x, local_y, 0)
                        activity.pop(activity_key, None)
                        changed = True
                        continue

                    if plant is None:
                        continue
                    if plant.get("dead"):
                        chunk.set_saved_tile("plant", local_x, local_y, None)
                        changed = True
                        continue

                    last_watered_at = plant.get("last_watered_at")
                    dry_since = last_watered_at if last_watered_at is not None else plant.get("planted_at", current_time)
                    if current_time - dry_since > PLANT_DRY_DEATH_MINUTES:
                        chunk.set_saved_tile("plant", local_x, local_y, None)
                        changed = True
                        continue

                    if plant.get("age", 0.0) >= 1.0:
                        continue
                    if plant.get("last_growth_day", current_day) >= current_day:
                        continue
                    last_watered_day = plant.get("last_watered_day")
                    watered_for_growth = (
                        self._is_watered(chunk.layers["soil_water"][idx], current_time)
                        or (last_watered_day is not None and last_watered_day >= current_day - 1)
                    )
                    if not watered_for_growth:
                        continue

                    plant["growth_days"] = plant.get("growth_days", 0) + 1
                    plant["last_growth_day"] = current_day
                    plant["age"] = self._plant_growth_ratio(plant)
                    chunk.runtime["plant_objects"] = {}
                    changed = True
            if changed:
                chunk.mark_dirty()
                self.world.invalidate_soil_chunk_and_neighbors(chunk.coord)

    def water_loaded_soil(self, game_time=None):
        current_time = self._absolute_minutes(game_time)
        current_day = self._current_day(game_time)
        changed_chunks = []
        for chunk in self.world.loaded_chunks.values():
            changed = False
            width, _ = chunk.chunk_size
            for idx, soil_value in enumerate(chunk.layers["soil"]):
                if soil_value != 1:
                    continue
                if self._is_watered(chunk.layers["soil_water"][idx], current_time):
                    continue
                self._set_water(
                    chunk,
                    idx % width,
                    idx // width,
                    current_time,
                    current_day,
                )
                changed = True
            if changed:
                chunk.mark_dirty()
                self.world.invalidate_soil_chunk_and_neighbors(chunk.coord)
                changed_chunks.append(chunk)
        return changed_chunks

    def _award_harvest(self, player, plant_type, world_tile=None):
        if player is not None and hasattr(player, "harvested_crops"):
            player.harvested_crops[plant_type] = player.harvested_crops.get(plant_type, 0) + 1
        inventory = getattr(player, "inventory", None)
        if inventory is not None:
            frames = self.plant_frames.get(plant_type, ())
            image = ""
            if frames:
                image = pygame.transform.scale(frames[-1], (32, 32))
            added = inventory.add_item_to_slot(
                Item(
                    plant_type,
                    image,
                    True,
                    inventory.craft_system.return_craft_product(plant_type),
                )
            )
            effect_manager = getattr(player, "effect_manager", None)
            if added and effect_manager is not None:
                if world_tile is None:
                    effect_pos = getattr(player, "center", (0, 0))
                else:
                    effect_pos = (
                        (world_tile[0] + 0.5) * self.world.tile_size,
                        world_tile[1] * self.world.tile_size,
                    )
                effect_manager.item_gain(plant_type, 1, effect_pos)

    @staticmethod
    def _publish_harvest(player, plant_type, world_tile):
        if player is None:
            return
        game_state = getattr(player, "game_state", None)
        publish_from(
            player,
            CropHarvested(
                event_id=next_event_id(player, "crop_harvested"),
                crop_id=plant_type,
                count=1,
                location_id=getattr(game_state, "current_location_id", "player_farm"),
                world_tile=world_tile,
            ),
        )

    def harvest_at(self, world_pos, player=None):
        """Harvest one mature crop at the explicitly targeted tile."""
        world_tile = self.world_to_tile(world_pos)
        state = self.get_tile_state(world_tile)
        if not state or not state["harvestable"]:
            return None

        chunk = state["chunk"]
        local_x, local_y = state["local"]
        plant_type = state["plant"]["type"]
        chunk.set_saved_tile("plant", local_x, local_y, None)
        self._touch_player_soil(chunk, local_x, local_y, self.current_time_minutes)
        self._award_harvest(player, plant_type, world_tile)
        self._publish_harvest(player, plant_type, world_tile)
        return plant_type

    def harvest_colliding(self, collision_rect, player=None):
        harvested = []
        tile_size = self.world.tile_size
        min_tile_x = int(collision_rect.left // tile_size)
        max_tile_x = int((collision_rect.right - 1) // tile_size)
        min_tile_y = int(collision_rect.top // tile_size)
        max_tile_y = int((collision_rect.bottom - 1) // tile_size)
        changed_chunks = set()

        for world_tile_y in range(min_tile_y, max_tile_y + 1):
            for world_tile_x in range(min_tile_x, max_tile_x + 1):
                chunk, (local_x, local_y) = self.get_chunk_and_local(
                    (world_tile_x, world_tile_y)
                )
                if chunk is None:
                    continue
                idx = chunk.get_index(local_x, local_y)
                plant = chunk.layers["plant"][idx]
                if plant is None or plant.get("age", 0.0) < 1.0:
                    continue

                plant_type = plant["type"]
                chunk.set_saved_tile("plant", local_x, local_y, None)
                self._touch_player_soil(
                    chunk,
                    local_x,
                    local_y,
                    self.current_time_minutes,
                )
                changed_chunks.add(chunk)
                harvested.append(plant_type)
                self._award_harvest(player, plant_type, (world_tile_x, world_tile_y))
                self._publish_harvest(
                    player,
                    plant_type,
                    (world_tile_x, world_tile_y),
                )

        for chunk in changed_chunks:
            chunk.mark_dirty()

        return harvested


def get_soil_tilemap(world, chunk):
    tilemap = chunk.runtime.get("soil_tilemap")
    if tilemap is None:
        tilemap = TileMap(
            filename=SOIL_TILESET_FILE,
            world=world,
            chunk=chunk,
            layer_name="soil",
            oob=0,
            world_layer_resolver=_get_neighbor_soil_value,
            source_tile_size=SOIL_SOURCE_TILE_SIZE,
        )
        chunk.runtime["soil_tilemap"] = tilemap
    return tilemap


def get_scaled_soil_sprite(world, chunk, idx):
    sprite_cache = chunk.runtime.get("soil_sprite_cache")
    if sprite_cache is None:
        sprite_cache = {}
        chunk.runtime["soil_sprite_cache"] = sprite_cache

    if idx in sprite_cache:
        return sprite_cache[idx]

    scaled = get_soil_tilemap(world, chunk).get_scaled_tile_sprite(
        idx,
        (chunk.tile_size, chunk.tile_size),
    )
    if scaled is None:
        return None

    sprite_cache[idx] = scaled
    return scaled


def get_soil_water_tilemap(world, chunk):
    tilemap = chunk.runtime.get("soil_water_tilemap")
    if tilemap is None:
        water_mask = [
            1 if soil == 1 and _water_value(water) else 0
            for soil, water in zip(chunk.layers["soil"], chunk.layers["soil_water"])
        ]
        tilemap = TileMap(
            filename=SOIL_WATER_TILESET_FILE,
            world=world,
            chunk=chunk,
            layer_name="soil_water",
            oob=0,
            layer_data=water_mask,
            world_layer_resolver=_get_neighbor_soil_water_value,
            source_tile_size=SOIL_SOURCE_TILE_SIZE,
        )
        chunk.runtime["soil_water_tilemap"] = tilemap
    return tilemap


def get_scaled_soil_water_sprite(world, chunk, idx):
    sprite_cache = chunk.runtime.get("soil_water_sprite_cache")
    if sprite_cache is None:
        sprite_cache = {}
        chunk.runtime["soil_water_sprite_cache"] = sprite_cache
    if idx not in sprite_cache:
        sprite_cache[idx] = get_soil_water_tilemap(world, chunk).get_scaled_tile_sprite(
            idx,
            (chunk.tile_size, chunk.tile_size),
        )
    return sprite_cache[idx]


def get_soil_surface(world, chunk):
    soil_surface = chunk.runtime.get("soil_surface")
    if soil_surface is not None:
        return soil_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    soil_surface = pygame.Surface((chunk_w * tile_size, chunk_h * tile_size), pygame.SRCALPHA)

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = chunk.get_index(local_x, local_y)
            soil_sprite = get_scaled_soil_sprite(world, chunk, idx)
            if soil_sprite is not None:
                soil_surface.blit(soil_sprite, (local_x * tile_size, local_y * tile_size))
            water_data = chunk.layers["soil_water"][idx]
            if chunk.layers["soil"][idx] == 1 and _water_value(water_data):
                water_sprite = get_scaled_soil_water_sprite(world, chunk, idx)
                if water_sprite is not None:
                    soil_surface.blit(water_sprite, (local_x * tile_size, local_y * tile_size))

    chunk.runtime["soil_surface"] = soil_surface
    return soil_surface




def ensure_chunk_plant_objects(chunk, soil_layer):
    runtime_plants = chunk.runtime.get("plant_objects")
    if runtime_plants is None:
        runtime_plants = {}
        chunk.runtime["plant_objects"] = runtime_plants

    cached = chunk.runtime.get("_plant_objects_cache")
    if cached is not None and cached[0] is runtime_plants:
        return cached[1]

    chunk_w, chunk_h = chunk.chunk_size
    current_keys = set()

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = chunk.get_index(local_x, local_y)
            plant_data = chunk.layers["plant"][idx]
            if plant_data is None:
                continue

            world_tile = chunk.get_world_tile(local_x, local_y)
            current_keys.add(world_tile)
            plant_type = plant_data["type"]
            frames = soil_layer.plant_frames.get(plant_type)
            if not frames:
                continue
            stage = min(len(frames) - 1, int(plant_data.get("age", 0.0) * (len(frames) - 1)))
            plant = runtime_plants.get(world_tile)
            if (
                plant is None
                or plant.plant_type != plant_type
                or int(plant.age) != stage
            ):
                plant = Plant(
                    plant_type,
                    (
                        world_tile[0] * chunk.tile_size + chunk.tile_size // 2,
                        world_tile[1] * chunk.tile_size + chunk.tile_size // 2,
                    ),
                    frames,
                    chunk.tile_size,
                )
                plant.age = stage
                plant.harvestable = plant_data.get("age", 0.0) >= 1.0
                plant.image_base = plant.frames[stage]
                plant.image = plant.image_base.copy()
                plant.rect = plant._make_rect(plant.rect.center)
                runtime_plants[world_tile] = plant

    for key in list(runtime_plants.keys()):
        if key not in current_keys:
            del runtime_plants[key]

    objects = tuple(runtime_plants.values())
    chunk.runtime["_plant_objects_cache"] = (runtime_plants, objects)
    return objects
