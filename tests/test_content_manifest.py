import os
import sys
import unittest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT_DIR, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from data.asset_validation import validate_asset_manifest
from data.content_manifest import (
    EFFECT_ASSETS,
    ITEM_ASSETS,
    LOCATION_ASSETS,
    ROCK_ASSETS,
    VESSEL_ASSETS,
    normalize_content_id,
)
from gameplay.effects import EffectLibrary
from ui.inventory import load_item_icon


class ContentManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_declared_assets_and_frame_contracts_are_valid(self):
        issues = validate_asset_manifest()
        self.assertEqual(tuple(map(str, issues)), ())

    def test_rare_gems_use_four_frames_and_filename_aliases(self):
        for item_id in ("blue_gem", "green_gem", "red_gem", "orange_gem"):
            with self.subTest(item_id=item_id):
                self.assertEqual(ITEM_ASSETS[item_id].sheet.frame_count, 4)
                self.assertEqual(ITEM_ASSETS[item_id].sheet.frame_size, (32, 16))
                self.assertTrue(ITEM_ASSETS[item_id].world_drop)
        self.assertEqual(normalize_content_id("Items_RedGem"), "red_gem")
        self.assertEqual(normalize_content_id("blueSaphireOre"), "blue_sapphire_ore")

    def test_story_items_and_reward_star_have_distinct_roles(self):
        self.assertEqual(ITEM_ASSETS["story_key"].role, "story_item")
        self.assertEqual(ITEM_ASSETS["royal_tiara"].role, "story_item")
        self.assertEqual(ITEM_ASSETS["reward_star"].role, "points_effect")
        self.assertFalse(ITEM_ASSETS["reward_star"].world_drop)

    def test_fire_sheet_uses_nineteen_row_major_frames(self):
        fire = EFFECT_ASSETS["fire"]
        rects = fire.frame_rects()
        self.assertEqual(len(rects), 19)
        self.assertEqual(rects[:5], ((0, 0, 96, 96), (96, 0, 96, 96), (192, 0, 96, 96), (288, 0, 96, 96), (0, 96, 96, 96)))
        self.assertEqual(rects[-1], (192, 384, 96, 96))

        frames = EffectLibrary().load_variant("fire")
        self.assertEqual(len(frames), 19)
        self.assertTrue(all(frame.get_size() == (96, 96) for frame in frames))

    def test_boat_frames_are_numeric_and_ship_wind_is_synchronized(self):
        boat = VESSEL_ASSETS["player_boat"]
        for animation in boat.animations.values():
            numbers = tuple(
                int(os.path.splitext(path)[0].rsplit("-", 1)[-1].replace("idle", ""))
                if "down-idle" in path
                else int(os.path.splitext(path)[0].rsplit("-", 1)[-1])
                for path in animation.paths
            )
            self.assertEqual(numbers, tuple(range(1, 15)))

        ship = VESSEL_ASSETS["pirate_ship"]
        for base_id, overlay_id in ship.synchronized_overlays.items():
            self.assertEqual(
                ship.animations[base_id].frame_count,
                ship.animations[overlay_id].frame_count,
            )

    def test_land_rocks_use_only_land_art_and_three_pebble_drops(self):
        rock = ROCK_ASSETS["land_rock"]
        self.assertEqual(rock.assets, tuple(f"rocks/{index}.png" for index in range(1, 7)))
        self.assertEqual(rock.drop_count, 3)
        self.assertEqual(rock.drop_asset, "rocks/pebbles.png")
        self.assertTrue(all("beach_rocks" not in path for path in rock.assets))

    def test_castle_and_item_sheets_are_runtime_loadable(self):
        self.assertEqual(
            LOCATION_ASSETS["castle_exterior"].asset,
            "graphics/sprites/houses/tertiary/castle.png",
        )
        self.assertEqual(load_item_icon("red_gem", (32, 32)).get_size(), (32, 32))
        self.assertEqual(load_item_icon("royal_tiara", (32, 32)).get_size(), (32, 32))


if __name__ == "__main__":
    unittest.main()
