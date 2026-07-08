"""Wandering NPC behavior and per-chunk NPC lifecycle management."""

from __future__ import annotations

import random

import pygame

from pathfinding import ChunkPathfinder
from sprites import AnimatedWorldObject


class WanderingNPC(AnimatedWorldObject):
    def __init__(self, pos, assets, pathfinder, speed=72, visual_scale=2):
        self.assets = assets
        self.pathfinder = pathfinder
        self.status = "down_idle"
        self.last_status = self.status
        self.speed = speed
        self.visual_scale = visual_scale
        self.direction = pygame.Vector2()
        self.pos = pygame.Vector2(pos)
        self.path = []
        self.target_tile = None
        self.wait_timer = random.uniform(0.6, 1.8)

        super().__init__(
            pos=pos,
            frames=self.get_scaled_frames(self.status),
            anchor="midbottom",
            animation_speed=6,
            loop=True,
        )
        self.name = "npc"
        self.collision_box = self.rect.copy().inflate(-self.rect.width * 0.5, -self.rect.height * 0.35)

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    def get_scaled_frames(self, status):
        frames = self.assets.get_character_frames(status)
        if self.visual_scale == 1:
            return frames
        return [
            pygame.transform.scale(
                frame,
                (
                    int(frame.get_width() * self.visual_scale),
                    int(frame.get_height() * self.visual_scale),
                ),
            )
            for frame in frames
        ]

    def refresh_animation_set(self):
        if self.status == self.last_status:
            return
        self.frames = self.get_scaled_frames(self.status)
        self.index = 0
        self.image_base = self.frames[0]
        self._refresh_image()
        self.last_status = self.status

    def update_status(self):
        previous = self.status
        if self.direction.length_squared() == 0:
            self.status = f"{self.status.split('_')[0]}_idle"
        elif abs(self.direction.x) > abs(self.direction.y):
            self.status = "right" if self.direction.x > 0 else "left"
        else:
            self.status = "down" if self.direction.y > 0 else "up"

        if self.status != previous:
            self.refresh_animation_set()

    def choose_wander_path(self):
        start = self.pathfinder.world_to_tile(self.rect.midbottom)
        goal = self.find_wander_goal(start)
        if goal is None:
            self.wait_timer = random.uniform(0.8, 2.0)
            return

        path = self.pathfinder.find_full_path(start, goal)
        if len(path) <= 1:
            self.wait_timer = random.uniform(0.8, 2.0)
            return

        self.path = path[1:]
        self.set_next_target()

    def find_wander_goal(self, start):
        loaded_chunks = list(self.pathfinder.world.loaded_chunks.values())
        if not loaded_chunks:
            return None

        for _ in range(24):
            chunk = random.choice(loaded_chunks)
            local_x = random.randrange(chunk.chunk_size[0])
            local_y = random.randrange(chunk.chunk_size[1])
            world_tile = chunk.get_world_tile(local_x, local_y)
            if self.pathfinder.heuristic(start, world_tile) > 18:
                continue
            if self.pathfinder.is_walkable(world_tile):
                return world_tile
        return None

    def set_next_target(self):
        if not self.path:
            self.target_tile = None
            self.wait_timer = random.uniform(0.8, 2.4)
            return
        tile = self.path.pop(0)
        self.target_tile = pygame.Vector2(self.pathfinder.tile_to_world_center(tile))

    def move(self, dt):
        if self.target_tile is None:
            self.direction.update(0, 0)
            return

        delta = self.target_tile - self.pos
        if delta.length() <= max(2, self.speed * dt):
            self.pos.update(self.target_tile)
            self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
            self.collision_box.center = self.rect.center
            self.set_next_target()
            return

        self.direction = delta.normalize()
        self.pos += self.direction * self.speed * dt
        self.rect.midbottom = (round(self.pos.x), round(self.pos.y))
        self.collision_box.center = self.rect.center

    def update(self, dt):
        if self.target_tile is None:
            self.wait_timer -= dt
            if self.wait_timer <= 0:
                self.choose_wander_path()

        self.move(dt)
        self.update_status()
        self.animate(dt)
        self.tick_opacity(dt)


class NPCManager:
    def __init__(self, world, assets, count=4):
        self.world = world
        self.assets = assets
        self.pathfinder = ChunkPathfinder(world)
        self.npcs = []
        self.spawn_initial(count)

    def spawn_initial(self, count):
        spawn = self.world.get_spawn_position()
        spawn_tile = self.pathfinder.world_to_tile(spawn)
        candidates = []

        for chunk in self.world.loaded_chunks.values():
            for local_y in range(chunk.chunk_size[1]):
                for local_x in range(chunk.chunk_size[0]):
                    world_tile = chunk.get_world_tile(local_x, local_y)
                    if self.pathfinder.heuristic(spawn_tile, world_tile) > 16:
                        continue
                    if self.pathfinder.is_walkable(world_tile):
                        candidates.append(world_tile)

        if not candidates:
            for chunk in self.world.loaded_chunks.values():
                for local_y in range(chunk.chunk_size[1]):
                    for local_x in range(chunk.chunk_size[0]):
                        world_tile = chunk.get_world_tile(local_x, local_y)
                        if self.pathfinder.is_walkable(world_tile):
                            candidates.append(world_tile)

        random.shuffle(candidates)
        for tile in candidates[:count]:
            self.npcs.append(
                WanderingNPC(
                    self.pathfinder.tile_to_world_center(tile),
                    self.assets,
                    self.pathfinder,
                )
            )

    def update(self, dt):
        for npc in self.npcs:
            npc.update(dt)

    def visible_npcs(self, visible_chunks):
        visible_chunk_keys = {coord for coord, _, _, _ in visible_chunks}
        for npc in self.npcs:
            if self.world.world_to_chunk(npc.rect.center) in visible_chunk_keys:
                yield npc
