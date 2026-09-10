"""Contracts for the synchronous, fully prepared island loading path."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from gameplay.world_objects import prewarm_chunk_runtime
from world.chunkmanager import Chunk
from world.worldmanager import World


class FullIslandLoadingTests(unittest.TestCase):
    def make_world_with_fake_generation(self):
        world = World(seed=31, chunk_size=(1, 1), tile_size=1)
        generated = []

        def fake_load(coord):
            chunk = world.loaded_chunks.get(coord)
            if chunk is None:
                chunk = Chunk(coord, (1, 1), 1)
                chunk.generated = True
                world.loaded_chunks[coord] = chunk
                generated.append(coord)
            return chunk

        return world, generated, fake_load

    def test_prepare_full_island_generates_and_finishes_every_chunk(self):
        world, generated, fake_load = self.make_world_with_fake_generation()
        prepared = []

        with patch.object(world, "load_chunk", side_effect=fake_load):
            world.prepare_full_island(
                prewarm_chunk_callback=lambda chunk: prepared.append(chunk.coord)
            )

        expected = world.get_level_chunk_coords()
        self.assertEqual(set(generated), expected)
        self.assertEqual(set(prepared), expected)
        self.assertEqual(set(world.loaded_chunks), expected)
        self.assertEqual(world.active_chunks, expected)
        self.assertTrue(all(chunk.active for chunk in world.loaded_chunks.values()))

    def test_player_movement_does_not_start_more_chunk_loading(self):
        world, _, fake_load = self.make_world_with_fake_generation()
        with patch.object(world, "load_chunk", side_effect=fake_load):
            world.prepare_full_island()

        loaded_before = set(world.loaded_chunks)
        with patch.object(world, "load_chunk") as load_chunk:
            world.update_active_chunks((3, -2), movement_direction=(1, 0))

        load_chunk.assert_not_called()
        self.assertEqual(set(world.loaded_chunks), loaded_before)
        self.assertEqual(world.active_chunks, loaded_before)

    def test_runtime_prewarm_builds_the_complete_surface_and_objects(self):
        chunk = SimpleNamespace()
        world = object()
        soil_layer = object()

        with (
            patch("gameplay.world_objects.get_chunk_surface") as get_surface,
            patch("gameplay.world_objects.collect_chunk_objects") as collect_objects,
        ):
            prewarm_chunk_runtime(chunk, world, soil_layer)

        get_surface.assert_called_once_with(world, chunk)
        collect_objects.assert_called_once_with(chunk, soil_layer)


if __name__ == "__main__":
    unittest.main()
