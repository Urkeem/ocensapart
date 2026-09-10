"""Farmstead scene and partial yard-fence generation tests."""

import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from scenemanager import (
    HOUSE_SCENE_TEMPLATES,
    primary_house_fence_tiles,
    scene_fence_prop_pairs,
    scene_fence_prop_tiles,
    scene_fence_tiles,
)
from world.chunkmanager import Chunk
from world.fence import FENCE_GATE, FENCE_SEGMENT, ensure_chunk_fence_collisions


FARMSTEAD = next(
    template for template in HOUSE_SCENE_TEMPLATES
    if template["name"] == "farmstead"
)


class FarmsteadFenceTests(unittest.TestCase):
    def make_land_chunk(self):
        chunk = Chunk((0, 0), (24, 24), 64)
        tile_count = 24 * 24
        chunk.layers["base"] = [1] * tile_count
        chunk.layers["terrain"] = [1] * tile_count
        chunk.layers["biome"] = [3] * tile_count
        return chunk

    def test_farmstead_has_closed_perimeter_with_one_bottom_gate(self):
        fence_tiles = scene_fence_tiles(FARMSTEAD)
        gate_tiles = [tile for tile in fence_tiles if tile[2]]

        self.assertEqual(FARMSTEAD["size"], (13, 9))
        self.assertEqual(len(fence_tiles), 40)
        self.assertEqual(gate_tiles, [(6, 8, True)])

    def test_farmstead_generation_builds_asset_sized_open_house_yards(self):
        chunk = self.make_land_chunk()
        chunk._weighted_scene_template = lambda *args, **kwargs: FARMSTEAD

        houses = chunk.generate_house_props(world_seed=7, houses_per_chunk=1)

        self.assertTrue(houses)
        self.assertEqual(chunk.metadata["house_scene"], "farmstead")
        expected_fence_tiles = 0
        for house in houses:
            house_x, house_y = house["local_tile"]
            house_w, house_h = house["footprint"]
            yard_x, yard_y, yard_w, yard_h = house["yard_rect"]
            margin = house["yard_margin"]
            self.assertIn(margin, (3, 4))
            self.assertEqual(
                (yard_x, yard_y, yard_w, yard_h),
                (
                    house_x - margin,
                    house_y - margin,
                    house_w + margin * 2,
                    house_h + margin * 2,
                ),
            )
            gate_x, gate_y = house["yard_gate_tile"]
            self.assertEqual(gate_x, house["door_tile"][0] - chunk.origin_tile[0])
            self.assertEqual(gate_y, yard_y + yard_h - 1)
            self.assertEqual(
                chunk.layers["fence"][chunk.get_index(gate_x, gate_y)],
                FENCE_GATE,
            )
            self.assertEqual(
                chunk.layers["collision"][chunk.get_index(gate_x, gate_y)],
                0,
            )
            fence_tiles = chunk._yard_fence_tiles(house)
            solid_tiles = {(x, y) for x, y, is_gate in fence_tiles if not is_gate}
            full_perimeter_size = 2 * yard_w + 2 * yard_h - 4
            self.assertLess(len(fence_tiles), full_perimeter_size // 2)

            components = 0
            unvisited = set(solid_tiles)
            while unvisited:
                components += 1
                stack = [unvisited.pop()]
                while stack:
                    x, y = stack.pop()
                    neighbors = {
                        (x + 1, y),
                        (x - 1, y),
                        (x, y + 1),
                        (x, y - 1),
                    } & unvisited
                    unvisited.difference_update(neighbors)
                    stack.extend(neighbors)
            self.assertGreaterEqual(components, 2)
            expected_fence_tiles += len(fence_tiles)

        animal_pen = next(prop for prop in chunk.props if prop.get("type") == "animal_pen")
        _, _, pen_width, pen_height = animal_pen["local_rect"]
        pen_perimeter_size = 2 * pen_width + 2 * pen_height - 4
        self.assertEqual(chunk.layers["fence"].count(FENCE_GATE), len(houses) + 1)
        self.assertEqual(
            chunk.layers["fence"].count(FENCE_SEGMENT),
            expected_fence_tiles - len(houses) + pen_perimeter_size - 1,
        )
        fence_collisions = ensure_chunk_fence_collisions(chunk)
        self.assertGreaterEqual(
            len(fence_collisions),
            chunk.layers["fence"].count(FENCE_SEGMENT),
        )
        self.assertTrue(all(collision.collision_box.size == (14, 8) for collision in fence_collisions))

        door_flowers = [
            prop
            for prop in chunk.props
            if prop.get("type") == "environment"
            and prop.get("variant") in {"door_flower", "door_flower_potted"}
        ]
        self.assertEqual(len(door_flowers), len(houses) * 2)
        for flower in door_flowers:
            x, y = flower["local_tile"]
            house = next(
                house
                for house in houses
                if (
                    house["yard_rect"][0] < x < house["yard_rect"][0] + house["yard_rect"][2] - 1
                    and house["yard_rect"][1] < y < house["yard_rect"][1] + house["yard_rect"][3] - 1
                )
            )
            door_x = house["door_tile"][0] - chunk.origin_tile[0]
            door_front_y = house["local_tile"][1] + house["footprint"][1]
            self.assertLessEqual(abs(x - door_x) + abs(y - door_front_y), 2)

    def test_fence_prop_tiles_follow_the_fence_shape(self):
        fence_tiles = {(x, y) for x, y, is_gate in scene_fence_tiles(FARMSTEAD) if not is_gate}
        pairs = scene_fence_prop_pairs(FARMSTEAD)
        prop_tiles = scene_fence_prop_tiles(FARMSTEAD)
        self.assertEqual(len(pairs), len(fence_tiles))
        self.assertEqual({(fence_x, fence_y) for fence_x, fence_y, _, _ in pairs}, fence_tiles)
        self.assertEqual(len(prop_tiles), len(set(prop_tiles)))
        self.assertTrue(
            all(abs(fence_x - prop_x) + abs(fence_y - prop_y) == 1
                for fence_x, fence_y, prop_x, prop_y in pairs)
        )

    def test_every_solid_generated_fence_has_one_unique_prop_tile(self):
        for template in HOUSE_SCENE_TEMPLATES:
            with self.subTest(template=template["name"]):
                fence_tiles = {
                    (x, y)
                    for x, y, is_gate in scene_fence_tiles(template)
                    if not is_gate
                }
                pairs = scene_fence_prop_pairs(template)
                self.assertEqual(
                    {(fence_x, fence_y) for fence_x, fence_y, _, _ in pairs},
                    fence_tiles,
                )
                prop_tiles = [(prop_x, prop_y) for _, _, prop_x, prop_y in pairs]
                self.assertEqual(len(prop_tiles), len(set(prop_tiles)))
                self.assertTrue(
                    all(
                        abs(fence_x - prop_x) + abs(fence_y - prop_y) == 1
                        for fence_x, fence_y, prop_x, prop_y in pairs
                    )
                )

    def test_every_primary_house_has_frontage_fencing_or_scene_enclosure(self):
        primary_count = 0
        frontage_count = 0
        enclosed = []

        for template in HOUSE_SCENE_TEMPLATES:
            for house in template.get("houses", []):
                if house.get("category", "primary") != "primary":
                    continue
                primary_count += 1
                self.assertEqual(house.get("fence"), "frontage")
                pieces = primary_house_fence_tiles(template, house)
                if pieces:
                    frontage_count += 1
                    self.assertGreaterEqual(len(pieces), 4)
                    self.assertLessEqual(len(pieces), 6)
                else:
                    enclosed.append((template["name"], house.get("prefer")))

        self.assertEqual(primary_count, 46)
        self.assertEqual(frontage_count, 44)
        self.assertEqual(
            enclosed,
            [("farmstead", "farmhouse"), ("farmstead", "hut")],
        )

    def test_multi_home_scene_reserves_non_overlapping_yards(self):
        template = next(
            scene for scene in HOUSE_SCENE_TEMPLATES
            if scene["name"] == "quiet_huts"
        )
        chunk = self.make_land_chunk()
        chunk._weighted_scene_template = lambda *args, **kwargs: template

        houses = chunk.generate_house_props(world_seed=11, houses_per_chunk=1)

        self.assertGreaterEqual(len(houses), 1)
        self.assertLessEqual(len(houses), len(template["houses"]))
        yards = [house["yard_rect"] for house in houses]
        for index, first in enumerate(yards):
            for second in yards[index + 1:]:
                self.assertFalse(chunk._rects_overlap(first, second))
        self.assertEqual(chunk.layers["fence"].count(FENCE_GATE), len(houses))

    def test_every_scene_template_can_place_at_least_one_complete_yard(self):
        for seed, template in enumerate(HOUSE_SCENE_TEMPLATES, 1):
            with self.subTest(template=template["name"]):
                chunk = self.make_land_chunk()
                chunk._weighted_scene_template = lambda *args, _template=template, **kwargs: _template

                houses = chunk.generate_house_props(world_seed=seed, houses_per_chunk=1)

                self.assertTrue(houses)
                for house in houses:
                    self.assertIn(house["yard_margin"], (3, 4))
                    gate_x, gate_y = house["yard_gate_tile"]
                    self.assertEqual(
                        chunk.layers["fence"][chunk.get_index(gate_x, gate_y)],
                        FENCE_GATE,
                    )

    def test_natural_props_do_not_block_house_entry_paths(self):
        chunk = self.make_land_chunk()
        chunk._weighted_scene_template = lambda *args, **kwargs: FARMSTEAD
        houses = chunk.generate_house_props(world_seed=7, houses_per_chunk=1)

        chunk.generate_environment_props(world_seed=7)

        for house in houses:
            for path_x, path_y in house["yard_entry_tiles"][:-1]:
                self.assertIsNone(
                    chunk.layers["decoration"][chunk.get_index(path_x, path_y)]
                )


if __name__ == "__main__":
    unittest.main()
