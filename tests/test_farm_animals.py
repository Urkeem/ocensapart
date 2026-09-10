"""Farm paddock generation and animal animation contracts."""

import sys
import unittest
from collections import Counter
from pathlib import Path

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from entities.animal import ANIMAL_DIRECTIONS, ANIMAL_SPECS, FarmAnimal, get_animal_frames
from gameplay.world_objects import ensure_chunk_animal_objects, ensure_chunk_environment_objects
from scenemanager import HOUSE_SCENE_TEMPLATES
from ui.hud import FARMSTEAD_MARKER_COLOR, GameplayHUD
from world.chunkmanager import Chunk
from world.fence import FENCE_GATE, FENCE_SEGMENT
from world.worldmanager import World


FARMSTEAD = next(
    template for template in HOUSE_SCENE_TEMPLATES
    if template["name"] == "farmstead"
)


class FarmAnimalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1, 1))

    def make_farmstead(self):
        chunk = Chunk((0, 0), (24, 24), 64)
        tile_count = 24 * 24
        chunk.layers["base"] = [1] * tile_count
        chunk.layers["terrain"] = [1] * tile_count
        chunk.layers["biome"] = [3] * tile_count
        chunk._weighted_scene_template = lambda *args, **kwargs: FARMSTEAD
        houses = chunk.generate_house_props(world_seed=7, houses_per_chunk=1)
        self.assertTrue(houses)
        return chunk

    def test_species_sheets_expose_directional_walk_and_feed_rows(self):
        expected_feed_frames = {"cow": 5, "chicken": 3, "pig": 2}
        for species, feed_count in expected_feed_frames.items():
            self.assertEqual(ANIMAL_SPECS[species]["walk_frames"], 6)
            self.assertEqual(ANIMAL_SPECS[species]["feed_frames"], feed_count)
            for variant in ("1", "2"):
                for direction in ANIMAL_DIRECTIONS:
                    walk = get_animal_frames(species, variant, f"walk_{direction}")
                    feed = get_animal_frames(species, variant, f"feed_{direction}")
                    self.assertEqual(len(walk), 6)
                    self.assertEqual(len(feed), feed_count)
                    self.assertTrue(all(frame.get_size() == (64, 64) for frame in walk + feed))

    def test_farmstead_reserves_a_fenced_pen_and_spawns_animals(self):
        chunk = self.make_farmstead()
        pen = next(prop for prop in chunk.props if prop.get("type") == "animal_pen")
        animals = [prop for prop in chunk.props if prop.get("type") == "animal"]
        pen_hay = [
            prop
            for prop in chunk.props
            if prop.get("type") == "environment"
            and prop.get("variant") == "animal_pen_hay"
        ]

        self.assertEqual(Counter(animal["species"] for animal in animals), {
            "cow": 1,
            "pig": 1,
            "chicken": 2,
        })
        self.assertTrue(all(animal["scale"] == 2.0 for animal in animals))
        self.assertEqual(len(pen_hay), 1)
        left, top, width, height = pen["local_rect"]
        interior_left, interior_top, interior_width, interior_height = pen["interior_rect"]
        perimeter = {
            *((x, top) for x in range(left, left + width)),
            *((x, top + height - 1) for x in range(left, left + width)),
            *((left, y) for y in range(top + 1, top + height - 1)),
            *((left + width - 1, y) for y in range(top + 1, top + height - 1)),
        }
        gate = tuple(pen["gate_tile"])
        for tile in perimeter:
            expected = FENCE_GATE if tile == gate else FENCE_SEGMENT
            self.assertEqual(chunk.layers["fence"][chunk.get_index(*tile)], expected)

        for animal in animals:
            x, y = animal["local_tile"]
            self.assertTrue(interior_left <= x < interior_left + interior_width)
            self.assertTrue(interior_top <= y < interior_top + interior_height)
            decoration = chunk.layers["decoration"][chunk.get_index(x, y)]
            self.assertEqual(decoration["type"], "animal_pen")
            self.assertEqual(chunk.layers["soil"][chunk.get_index(x, y)], 0)

        hay_x, hay_y = pen_hay[0]["local_tile"]
        self.assertTrue(interior_left <= hay_x < interior_left + interior_width)
        self.assertTrue(interior_top <= hay_y < interior_top + interior_height)
        hay_decoration = chunk.layers["decoration"][chunk.get_index(hay_x, hay_y)]
        self.assertEqual(hay_decoration["prop_type"], "hay")
        environment_objects = ensure_chunk_environment_objects(chunk)
        self.assertTrue(any(
            prop.record.get("id") == pen_hay[0]["id"]
            for prop in environment_objects
        ))

    def test_runtime_animals_are_cached_and_remain_inside_their_pen(self):
        chunk = self.make_farmstead()
        animals = ensure_chunk_animal_objects(chunk)

        self.assertEqual(len(animals), 4)
        self.assertIs(animals, ensure_chunk_animal_objects(chunk))
        self.assertTrue(all(isinstance(animal, FarmAnimal) for animal in animals))
        self.assertTrue(all(animal.image.get_size() == (128, 128) for animal in animals))
        chickens = [animal for animal in animals if animal.species == "chicken"]
        self.assertEqual(len(chickens), 2)
        self.assertTrue(all(chicken.speed == 88.0 for chicken in chickens))
        self.assertTrue(all(chicken.animation_speed == 8.0 for chicken in chickens))
        for chicken in chickens:
            chicken.begin_walking()
        self.assertTrue(all(chicken.animation_speed == 12.0 for chicken in chickens))

        for _ in range(900):
            for animal in animals:
                animal.update(1 / 30)

        for animal in animals:
            left, top, width, height = animal.home_rect
            self.assertGreaterEqual(animal.pos.x, left * chunk.tile_size)
            self.assertLessEqual(animal.pos.x, (left + width) * chunk.tile_size)
            self.assertGreaterEqual(animal.pos.y, top * chunk.tile_size)
            self.assertLessEqual(animal.pos.y, (top + height) * chunk.tile_size)

    def test_island_guarantees_three_mapped_farmsteads(self):
        world = World(seed=73, chunk_size=(24, 24), tile_size=64)
        same_island = World(seed=73, chunk_size=(24, 24), tile_size=64)

        self.assertEqual(len(world.farmstead_chunks), 3)
        self.assertEqual(len(set(world.farmstead_chunks)), 3)
        self.assertEqual(world.farmstead_chunks, same_island.farmstead_chunks)
        self.assertTrue(all(world.is_chunk_in_level_bounds(coord) for coord in world.farmstead_chunks))

        unloaded_markers = GameplayHUD._farmstead_positions(world)
        expected_markers = tuple(
            (
                (chunk_x * 24 + 12) * 64,
                (chunk_y * 24 + 12) * 64,
            )
            for chunk_x, chunk_y in world.farmstead_chunks
        )
        self.assertEqual(tuple(unloaded_markers), expected_markers)
        self.assertGreater(FARMSTEAD_MARKER_COLOR[2], FARMSTEAD_MARKER_COLOR[0])
        self.assertGreater(FARMSTEAD_MARKER_COLOR[2], FARMSTEAD_MARKER_COLOR[1])

        farm_chunks = [world.load_chunk(coord) for coord in world.farmstead_chunks]
        self.assertTrue(all(
            "farmstead" in chunk.metadata.get("house_scenes", ())
            for chunk in farm_chunks
        ))
        self.assertEqual(sum(chunk.metadata.get("animal_pen_count", 0) for chunk in farm_chunks), 3)
        self.assertEqual(sum(chunk.metadata.get("animal_count", 0) for chunk in farm_chunks), 12)


if __name__ == "__main__":
    unittest.main()
