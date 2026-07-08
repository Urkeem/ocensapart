"""Grid pathfinding helpers for moving through generated world chunks."""

from __future__ import annotations

import heapq


class ChunkPathfinder:
    def __init__(self, world):
        self.world = world

    @staticmethod
    def get_chunk_key_from_world(x, y, chunk_size):
        return x // chunk_size[0], y // chunk_size[1]

    @staticmethod
    def heuristic(a, b):
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def world_to_tile(self, world_pos):
        return (
            int(world_pos[0] // self.world.tile_size),
            int(world_pos[1] // self.world.tile_size),
        )

    def tile_to_world_center(self, tile):
        return (
            tile[0] * self.world.tile_size + self.world.tile_size // 2,
            tile[1] * self.world.tile_size + self.world.tile_size,
        )

    def tile_to_chunk_local(self, tile):
        chunk_w, chunk_h = self.world.chunk_size
        chunk_coord = (tile[0] // chunk_w, tile[1] // chunk_h)
        local = (tile[0] % chunk_w, tile[1] % chunk_h)
        return chunk_coord, local

    def is_loaded_tile(self, tile):
        chunk_coord, _ = self.tile_to_chunk_local(tile)
        return chunk_coord in self.world.loaded_chunks

    def is_walkable(self, tile):
        chunk_coord, local = self.tile_to_chunk_local(tile)
        chunk = self.world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            return False

        local_x, local_y = local
        if not chunk.in_bounds(local_x, local_y):
            return False

        idx = chunk.get_index(local_x, local_y)
        return chunk.layers["terrain"][idx] == -1 or chunk.layers["collision"][idx] == 0

    def neighbors(self, tile):
        x, y = tile
        for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if self.is_loaded_tile(neighbor) and self.is_walkable(neighbor):
                yield neighbor

    def find_full_path(self, start, goal, max_nodes=1800):
        if not self.is_walkable(start) or not self.is_walkable(goal):
            return []

        open_set = [(0, start)]
        came_from = {}
        cost_so_far = {start: 0}
        visited = 0

        while open_set and visited < max_nodes:
            visited += 1
            _, current = heapq.heappop(open_set)
            if current == goal:
                return self.reconstruct_path(came_from, current)

            for neighbor in self.neighbors(current):
                new_cost = cost_so_far[current] + 1
                if neighbor not in cost_so_far or new_cost < cost_so_far[neighbor]:
                    cost_so_far[neighbor] = new_cost
                    priority = new_cost + self.heuristic(goal, neighbor)
                    heapq.heappush(open_set, (priority, neighbor))
                    came_from[neighbor] = current

        return []

    @staticmethod
    def reconstruct_path(came_from, current):
        path = [current]
        while current in came_from:
            current = came_from[current]
            path.append(current)
        path.reverse()
        return path
