"""Farm soil, watering, planting, crop growth, and soil rendering helpers."""

import pygame

from TileMapManager import TileMap
from sprites import WorldObject
from core.support import import_file, import_folder


SOIL_TILESET_FILE = "Tilesets/land.png"
SOIL_SOURCE_TILE_SIZE = 32
MINUTES_PER_DAY = 1440
WATER_DURATION_MINUTES = MINUTES_PER_DAY
PLANT_DRY_DEATH_MINUTES = MINUTES_PER_DAY * 2
PLANT_MAX_GROWTH_DAYS = {
    "corn": 4,
    "tomato": 5,
}


def _get_neighbor_soil_value(neighbor_chunk, local_x, local_y):
    idx = neighbor_chunk.get_index(local_x, local_y)
    return neighbor_chunk.layers["soil"][idx]


class Plant(WorldObject):
    def __init__(self, plant_type, pos, frames, tile_size):
        self.plant_type = plant_type
        self.frames = [
            pygame.transform.scale(frame, (tile_size, tile_size))
            for frame in frames
        ]
        self.age = 0.0
        self.max_age = len(self.frames) - 1
        self.harvestable = False
        super().__init__(pos, self.frames[0], anchor="midbottom")
        self.name = "crop"

    def grow(self, dt, watered):
        if not watered or self.harvestable:
            return

        self.age = min(self.max_age, self.age + PLANT_GROW_SPEED.get(self.plant_type, 0.2) * dt)
        if self.age >= self.max_age:
            self.harvestable = True

        anchor = self.rect.midbottom
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
        self.water_surfs = import_folder("graphics", "soil_water")
        self.plant_frames = {
            "corn": import_folder("graphics", "fruit", "corn"),
            "tomato": import_folder("graphics", "fruit", "tomato"),
        }
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

    def _water_entry(self, watered_at):
        return {
            "watered_at": watered_at,
            "expires_at": watered_at + WATER_DURATION_MINUTES,
        }

    def _is_watered(self, water_data, current_time):
        if water_data == 1:
            return True
        if not isinstance(water_data, dict):
            return False
        return current_time <= water_data.get("expires_at", 0)

    def _set_water(self, chunk, idx, current_time):
        chunk.layers["soil_water"][idx] = self._water_entry(current_time)
        plant = chunk.layers["plant"][idx]
        if plant is not None:
            plant["last_watered_at"] = current_time

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

    def can_till(self, chunk, local_x, local_y):
        idx = chunk.get_index(local_x, local_y)
        return (
            chunk.layers["terrain"][idx] > 0
            and chunk.layers["collision"][idx] == 0
            and chunk.layers["decoration"][idx] is None
        )

    def till_at(self, world_pos):
        world_tile = self.world_to_tile(world_pos)
        chunk, local = self.get_chunk_and_local(world_tile)
        if chunk is None:
            return False

        local_x, local_y = local
        idx = chunk.get_index(local_x, local_y)
        if not self.can_till(chunk, local_x, local_y):
            return False

        chunk.layers["soil"][idx] = 1
        chunk.mark_dirty()
        self.world.invalidate_chunk_and_neighbors(chunk.coord)
        self._play(self.hoe_sound)
        return True

    def water_at(self, world_pos, game_time=None):
        current_time = self._absolute_minutes(game_time)
        world_tile = self.world_to_tile(world_pos)
        chunk, local = self.get_chunk_and_local(world_tile)
        if chunk is None:
            return False

        local_x, local_y = local
        idx = chunk.get_index(local_x, local_y)
        if chunk.layers["soil"][idx] != 1:
            return False

        self._set_water(chunk, idx, current_time)
        chunk.mark_dirty()
        self.world.invalidate_chunk_render_cache(chunk.coord)
        self._play(self.water_sound)
        return True

    def plant_seed_at(self, world_pos, seed, game_time=None):
        if seed not in self.plant_frames:
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

        chunk.layers["plant"][idx] = {
            "type": seed,
            "age": 0.0,
            "growth_days": 0,
            "max_growth_days": PLANT_MAX_GROWTH_DAYS.get(seed, 4),
            "planted_at": current_time,
            "planted_day": current_day,
            "last_growth_day": current_day,
            "last_watered_at": current_time if self._is_watered(chunk.layers["soil_water"][idx], current_time) else None,
            "dead": False,
        }
        chunk.mark_dirty()
        self.world.invalidate_chunk_render_cache(chunk.coord)
        self._play(self.plant_sound)
        return True

    def update(self, dt, game_time=None):
        self._sync_time(game_time)
        current_time = self.current_time_minutes
        current_day = self.current_day

        for chunk in self.world.loaded_chunks.values():
            chunk_w, chunk_h = chunk.chunk_size
            changed = False
            for local_y in range(chunk_h):
                for local_x in range(chunk_w):
                    idx = chunk.get_index(local_x, local_y)
                    water_data = chunk.layers["soil_water"][idx]
                    if water_data == 1:
                        chunk.layers["soil_water"][idx] = self._water_entry(current_time)
                        changed = True
                    elif isinstance(water_data, dict) and not self._is_watered(water_data, current_time):
                        chunk.layers["soil_water"][idx] = 0
                        changed = True

                    plant = chunk.layers["plant"][idx]
                    if plant is None:
                        continue
                    if plant.get("dead"):
                        chunk.layers["plant"][idx] = None
                        chunk.runtime["plant_objects"] = {}
                        changed = True
                        continue

                    last_watered_at = plant.get("last_watered_at")
                    dry_since = last_watered_at if last_watered_at is not None else plant.get("planted_at", current_time)
                    if current_time - dry_since > PLANT_DRY_DEATH_MINUTES:
                        chunk.layers["plant"][idx] = None
                        chunk.runtime["plant_objects"] = {}
                        changed = True
                        continue

                    if plant.get("age", 0.0) >= 1.0:
                        continue
                    if plant.get("last_growth_day", current_day) >= current_day:
                        continue
                    if not self._is_watered(chunk.layers["soil_water"][idx], current_time):
                        continue

                    plant["growth_days"] = plant.get("growth_days", 0) + 1
                    plant["last_growth_day"] = current_day
                    plant["age"] = self._plant_growth_ratio(plant)
                    chunk.runtime["plant_objects"] = {}
                    changed = True
            if changed:
                chunk.mark_dirty()
                self.world.invalidate_chunk_render_cache(chunk.coord)

    def water_loaded_soil(self, game_time=None):
        current_time = self._absolute_minutes(game_time)
        changed_chunks = []
        for chunk in self.world.loaded_chunks.values():
            changed = False
            for idx, soil_value in enumerate(chunk.layers["soil"]):
                if soil_value != 1:
                    continue
                if self._is_watered(chunk.layers["soil_water"][idx], current_time):
                    continue
                self._set_water(chunk, idx, current_time)
                changed = True
            if changed:
                chunk.mark_dirty()
                self.world.invalidate_chunk_render_cache(chunk.coord)
                changed_chunks.append(chunk)
        return changed_chunks

    def harvest_colliding(self, collision_rect, player=None):
        harvested = []
        for chunk in self.world.loaded_chunks.values():
            chunk_w, chunk_h = chunk.chunk_size
            chunk_harvested = False
            for local_y in range(chunk_h):
                for local_x in range(chunk_w):
                    idx = chunk.get_index(local_x, local_y)
                    plant = chunk.layers["plant"][idx]
                    if plant is None or plant.get("age", 0.0) < 1.0:
                        continue

                    world_tile = chunk.get_world_tile(local_x, local_y)
                    tile_rect = pygame.Rect(
                        world_tile[0] * chunk.tile_size,
                        world_tile[1] * chunk.tile_size,
                        chunk.tile_size,
                        chunk.tile_size,
                    )
                    if not tile_rect.colliderect(collision_rect):
                        continue

                    plant_type = plant["type"]
                    chunk.layers["plant"][idx] = None
                    chunk.runtime["plant_objects"] = {}
                    chunk_harvested = True
                    harvested.append(plant_type)
                    if player is not None and hasattr(player, "harvested_crops"):
                        player.harvested_crops[plant_type] = player.harvested_crops.get(plant_type, 0) + 1

            if chunk_harvested:
                chunk.mark_dirty()
                self.world.invalidate_chunk_render_cache(chunk.coord)

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

    surf = get_soil_tilemap(world, chunk).get_tile_sprite(idx)
    if surf is None:
        return None

    scaled = pygame.transform.scale(surf, (chunk.tile_size, chunk.tile_size))
    sprite_cache[idx] = scaled
    return scaled


def get_soil_surface(world, chunk):
    soil_surface = chunk.runtime.get("soil_surface")
    if soil_surface is not None and not chunk.dirty:
        return soil_surface

    chunk_w, chunk_h = chunk.chunk_size
    tile_size = chunk.tile_size
    soil_surface = pygame.Surface((chunk_w * tile_size, chunk_h * tile_size), pygame.SRCALPHA)

    water_surfs = [pygame.transform.scale(surf, (tile_size, tile_size)) for surf in import_folder("graphics", "soil_water")]
    water_surf = water_surfs[0] if water_surfs else None

    for local_y in range(chunk_h):
        for local_x in range(chunk_w):
            idx = chunk.get_index(local_x, local_y)
            soil_sprite = get_scaled_soil_sprite(world, chunk, idx)
            if soil_sprite is not None:
                soil_surface.blit(soil_sprite, (local_x * tile_size, local_y * tile_size))
            water_data = chunk.layers["soil_water"][idx]
            if water_surf is not None and (water_data == 1 or isinstance(water_data, dict)):
                soil_surface.blit(water_surf, (local_x * tile_size, local_y * tile_size))

    chunk.runtime["soil_surface"] = soil_surface
    return soil_surface


def ensure_chunk_plant_objects(chunk, soil_layer):
    runtime_plants = chunk.runtime.get("plant_objects")
    if runtime_plants is None:
        runtime_plants = {}
        chunk.runtime["plant_objects"] = runtime_plants

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
            age_bucket = int(plant_data.get("age", 0.0) * 100)
            cache_key = (world_tile, age_bucket)
            if cache_key not in runtime_plants:
                frames = soil_layer.plant_frames[plant_data["type"]]
                plant = Plant(
                    plant_data["type"],
                    (
                        world_tile[0] * chunk.tile_size + chunk.tile_size // 2,
                        world_tile[1] * chunk.tile_size + chunk.tile_size,
                    ),
                    frames,
                    chunk.tile_size,
                )
                plant.age = plant_data.get("age", 0.0) * plant.max_age
                plant.image_base = plant.frames[int(plant.age)]
                plant.image = plant.image_base.copy()
                plant.rect = plant._make_rect(plant.rect.midbottom)
                runtime_plants.clear()
                runtime_plants[cache_key] = plant

    for key in list(runtime_plants.keys()):
        if key[0] not in current_keys:
            del runtime_plants[key]

    return list(runtime_plants.values())
