import os
import sys
import unittest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT_DIR, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from entities.house import (
    get_house_door_rect,
    get_house_asset_scale,
    get_house_footprint_tiles,
    get_house_image,
    get_house_render_size,
)


class HouseScalingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_primary_houses_remain_at_two_x(self):
        asset = "primary/hut.png"
        self.assertEqual(get_house_asset_scale(asset), 2)
        self.assertEqual(get_house_image(asset).get_size(), get_house_render_size(asset))

    def test_secondary_and_tertiary_houses_use_one_point_five_x(self):
        for asset in ("tertiary/fort.png",):
            self.assertEqual(get_house_asset_scale(asset), 1.5)
            self.assertEqual(get_house_image(asset).get_size(), get_house_render_size(asset))

    def test_moved_farmhouse_uses_primary_house_scale(self):
        asset = "primary/farmhouse.png"
        self.assertEqual(get_house_asset_scale(asset), 2)
        self.assertEqual(get_house_image(asset).get_size(), get_house_render_size(asset))

    def test_house_footprints_and_doors_follow_the_selected_asset(self):
        hut = "primary/hut.png"
        abandoned = "primary/abandoned.png"

        self.assertEqual(get_house_footprint_tiles(hut, 64), (3, 4))
        self.assertEqual(get_house_footprint_tiles(abandoned, 64), (7, 7))
        self.assertEqual(tuple(get_house_door_rect(hut)), (62, 184, 72, 70))
        self.assertEqual(tuple(get_house_door_rect(abandoned)), (178, 298, 64, 86))


if __name__ == "__main__":
    unittest.main()
