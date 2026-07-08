"""Water-depth checks and visual overlays for the player's swimming state."""

import pygame

from core.support import import_folder


DEEP_WATER_ELEVATION = 0.30
LAND_SEARCH_RADIUS = 5


class WaterDepthResolver:
    def __init__(self, world):
        self.world = world

    def world_to_tile(self, world_pos):
        return (
            int(world_pos[0] // self.world.tile_size),
            int(world_pos[1] // self.world.tile_size),
        )

    def get_chunk_local(self, tile):
        chunk_w, chunk_h = self.world.chunk_size
        chunk_coord = (tile[0] // chunk_w, tile[1] // chunk_h)
        local = (tile[0] % chunk_w, tile[1] % chunk_h)
        return chunk_coord, local

    def get_tile_data(self, tile):
        chunk_coord, local = self.get_chunk_local(tile)
        chunk = self.world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return None, None, None

        local_x, local_y = local
        if not chunk.in_bounds(local_x, local_y):
            return None, None, None

        idx = chunk.get_index(local_x, local_y)
        return chunk, idx, (local_x, local_y)

    def is_land(self, tile):
        chunk, idx, _ = self.get_tile_data(tile)
        if chunk is None:
            return False
        return chunk.layers["terrain"][idx] != -1

    def water_depth_at(self, world_pos):
        tile = self.world_to_tile(world_pos)
        chunk, idx, local = self.get_tile_data(tile)
        if chunk is None or chunk.layers["terrain"][idx] != -1:
            return 0.0

        local_x, local_y = local
        if chunk.layers["elevation"][idx] <= DEEP_WATER_ELEVATION and not self.has_adjacent_land(local_x, local_y, chunk):
            return 1.0

        distance = self.distance_to_land(tile)
        if distance is None:
            return 1.0

        return min(1.0, 0.28 + (distance / LAND_SEARCH_RADIUS) * 0.72)

    @staticmethod
    def has_adjacent_land(local_x, local_y, chunk):
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
                        return True
        return False

    def distance_to_land(self, tile):
        closest = None
        for radius in range(1, LAND_SEARCH_RADIUS + 1):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if abs(dx) != radius and abs(dy) != radius:
                        continue
                    if self.is_land((tile[0] + dx, tile[1] + dy)):
                        distance = abs(dx) + abs(dy)
                        closest = distance if closest is None else min(closest, distance)
            if closest is not None:
                return closest
        return None


class SwimVisual:
    def __init__(self, visual_scale=1):
        self.depth_resolver = None
        self.sink_level = 0.0
        self.target_sink_level = 0.0
        self.swim_index = 0.0
        self.swim_wave = None
        self.swim_wave_rect = pygame.Rect(0, 0, 0, 0)
        self.swim_animations = [
            pygame.transform.scale(
                frame,
                (
                    max(1, int(frame.get_width() * visual_scale)),
                    max(1, int(frame.get_height() * visual_scale)),
                ),
            )
            for frame in import_folder("graphics", "swim")
        ]

    def bind_world(self, world):
        self.depth_resolver = WaterDepthResolver(world)

    def update(self, owner, dt):
        if self.depth_resolver is None:
            return

        water_collision_box = getattr(owner, "feet_collision_box", owner.rect)
        depth = self.depth_resolver.water_depth_at(water_collision_box.center)
        self.target_sink_level = depth * (owner.image.get_height() + 6)
        self.sink_level += (self.target_sink_level - self.sink_level) * min(1.0, dt * 5.0)

        if self.sink_level <= 1:
            return

        self.swim_index += 4 * dt
        if self.swim_animations:
            if self.swim_index >= len(self.swim_animations):
                self.swim_index = 0.0
            self.swim_wave = self.swim_animations[int(self.swim_index)]
            waterline_y = owner.rect.bottom - int(self.sink_level)
            self.swim_wave_rect = self.swim_wave.get_rect(midtop=(owner.rect.centerx, waterline_y - 2))

        clipped = owner.image.copy()
        clip_height = min(clipped.get_height(), int(self.sink_level))
        clip_rect = pygame.Rect(0, clipped.get_height() - clip_height, clipped.get_width(), clip_height)
        clipped.fill((0, 0, 0, 0), clip_rect)
        owner.image = clipped

    def is_swimming(self):
        return self.sink_level > 1 and self.swim_wave is not None
