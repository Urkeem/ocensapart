"""Fence atlas mapping and gate-binding tests."""

import os
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from gameplay.config import FENCE_TILESET_FILE
from gameplay.terrain import get_fence_surface
from world.fence import (
    FENCE_EMPTY,
    FENCE_GATE,
    FENCE_SEGMENT,
    FENCE_TILE_COORDS,
    FenceTileMap,
    get_fence_piece_layout,
    get_fence_tile_coords,
    set_fence_at,
)


class StubChunk:
    def __init__(self, coord, chunk_size, values):
        self.coord = coord
        self.chunk_size = chunk_size
        self.origin_tile = (coord[0] * chunk_size[0], coord[1] * chunk_size[1])
        self.layers = {
            "fence": list(values),
            "collision": [0] * len(values),
        }
        self.runtime = {}
        self.tile_size = 72
        self.saved_tiles = []

    def get_world_tile(self, local_x, local_y):
        return self.origin_tile[0] + local_x, self.origin_tile[1] + local_y

    def get_index(self, local_x, local_y):
        return local_y * self.chunk_size[0] + local_x

    def set_saved_tile(self, layer_name, local_x, local_y, value):
        self.layers[layer_name][self.get_index(local_x, local_y)] = value
        self.saved_tiles.append((layer_name, local_x, local_y, value))


class StubWorld:
    def __init__(self, chunks, chunk_size):
        self.loaded_chunks = {chunk.coord: chunk for chunk in chunks}
        self.chunk_size = chunk_size
        self.invalidated = []

    def invalidate_fence_chunk_and_neighbors(self, chunk_coord):
        self.invalidated.append(chunk_coord)


class FenceAutotileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_atlas_maps_all_sixteen_cardinal_combinations(self):
        coords = {
            get_fence_tile_coords(
                top=bool(mask & 8),
                right=bool(mask & 2),
                bottom=bool(mask & 1),
                left=bool(mask & 4),
            )
            for mask in range(16)
        }
        self.assertEqual(len(FENCE_TILE_COORDS), 16)
        self.assertEqual(len(coords), 16)
        self.assertNotIn((5, 0), coords)
        self.assertNotIn((5, 2), coords)

    def test_invisible_gate_binds_fences_on_both_sides(self):
        chunk = StubChunk((0, 0), (3, 1), [FENCE_SEGMENT, FENCE_GATE, FENCE_SEGMENT])
        tilemap = FenceTileMap(FENCE_TILESET_FILE, StubWorld([chunk], (3, 1)), chunk)

        self.assertEqual(tilemap.get_tile_coords(0), FENCE_TILE_COORDS["r"])
        self.assertIsNone(tilemap.get_tile_coords(1))
        self.assertEqual(tilemap.get_tile_coords(2), FENCE_TILE_COORDS["l"])

    def test_invisible_gate_binds_fences_above_and_below(self):
        chunk = StubChunk((0, 0), (1, 3), [FENCE_SEGMENT, FENCE_GATE, FENCE_SEGMENT])
        tilemap = FenceTileMap(FENCE_TILESET_FILE, StubWorld([chunk], (1, 3)), chunk)

        self.assertEqual(tilemap.get_tile_coords(0), FENCE_TILE_COORDS["b"])
        self.assertIsNone(tilemap.get_tile_coords(1))
        self.assertEqual(tilemap.get_tile_coords(2), FENCE_TILE_COORDS["t"])

    def test_fence_connections_cross_chunk_boundaries(self):
        left = StubChunk((0, 0), (1, 1), [FENCE_SEGMENT])
        right = StubChunk((1, 0), (1, 1), [FENCE_GATE])
        world = StubWorld([left, right], (1, 1))
        tilemap = FenceTileMap(FENCE_TILESET_FILE, world, left)

        self.assertEqual(tilemap.get_tile_coords(0), FENCE_TILE_COORDS["r"])

    def test_fence_surface_draws_segments_and_leaves_gate_cell_empty(self):
        chunk = StubChunk((0, 0), (3, 1), [FENCE_SEGMENT, FENCE_GATE, FENCE_SEGMENT])
        world = StubWorld([chunk], (3, 1))

        surface = get_fence_surface(world, chunk)

        self.assertNotEqual(surface.subsurface((0, 0, 72, 72)).get_bounding_rect().size, (0, 0))
        self.assertEqual(surface.subsurface((72, 0, 72, 72)).get_bounding_rect().size, (0, 0))
        self.assertNotEqual(surface.subsurface((144, 0, 72, 72)).get_bounding_rect().size, (0, 0))
        self.assertLessEqual(surface.get_bounding_rect().height, 32)

    def test_straight_fence_uses_native_pieces_instead_of_scaling(self):
        pieces = get_fence_piece_layout(96, left=True, right=True)
        pieces_at_64 = get_fence_piece_layout(64, left=True, right=True)

        self.assertEqual(len(pieces), 3)
        self.assertEqual([piece[:2] for piece in pieces], [(0, 32), (32, 32), (64, 32)])
        self.assertEqual(len(pieces_at_64), 2)

    def test_set_fence_at_persists_and_invalidates_neighbors(self):
        chunk = StubChunk((0, 0), (3, 1), [FENCE_EMPTY, FENCE_EMPTY, FENCE_EMPTY])
        world = StubWorld([chunk], (3, 1))

        self.assertTrue(set_fence_at(world, (1, 0), FENCE_GATE))
        self.assertEqual(chunk.layers["fence"], [FENCE_EMPTY, FENCE_GATE, FENCE_EMPTY])
        self.assertEqual(chunk.layers["collision"], [0, 0, 0])
        self.assertEqual(
            chunk.saved_tiles,
            [
                ("fence", 1, 0, FENCE_GATE),
                ("collision", 1, 0, 0),
            ],
        )
        self.assertEqual(world.invalidated, [(0, 0)])
        self.assertFalse(set_fence_at(world, (1, 0), FENCE_GATE))

    def test_solid_fence_marks_npc_collision_tile_blocked(self):
        chunk = StubChunk((0, 0), (1, 1), [FENCE_EMPTY])
        world = StubWorld([chunk], (1, 1))

        self.assertTrue(set_fence_at(world, (0, 0), FENCE_SEGMENT))
        self.assertEqual(chunk.layers["collision"], [1])


if __name__ == "__main__":
    unittest.main()
