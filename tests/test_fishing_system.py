import math
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

from assets import LoadAssets
from entities.player import FISHING_STATE_DURATIONS, Player
from gameplay.fishing import FISH_CATALOG, FISH_SHEET_COUNTS, get_fish_pool
from world.worldmanager import ISLAND_SIZE_CHUNKS, World


class FishingSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = LoadAssets()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_locality_and_season_pools_match_declared_counts(self):
        for locality, seasons in FISH_SHEET_COUNTS.items():
            for season, seasonal_count in seasons.items():
                self.assertEqual(len(FISH_CATALOG[(locality, season)]), seasonal_count)
                if season != "allseason":
                    self.assertEqual(
                        len(get_fish_pool(locality, season)),
                        seasons["allseason"] + seasonal_count,
                    )

    def test_every_direction_exposes_the_full_fishing_animation_flow(self):
        for facing in ("down", "up", "right", "left"):
            for state, frame_count in (
                ("initial_cast", 1),
                ("cast", 3),
                ("fish", 1),
                ("reel_in", 2),
                ("reel", 4),
            ):
                self.assertEqual(
                    len(self.assets.get_character_frames(f"{facing}_{state}")),
                    frame_count,
                )

    def test_repeated_reel_ins_return_to_fish_before_the_final_reel(self):
        player = Player((64, 64), self.assets, soil_layer=None)
        species = next(fish for fish in get_fish_pool("river", "spring") if fish.required_reels == 2)
        player.fishing_active = True
        player.fishing_pending_catch = species
        player.fishing_reels_remaining = species.required_reels
        player._set_fishing_state("fish")
        player.fishing_has_bite = True

        self.assertTrue(player.reel_fishing_line())
        self.assertEqual(player.fishing_state, "reel_in")
        player.update_timers(FISHING_STATE_DURATIONS["reel_in"])
        self.assertEqual(player.fishing_state, "fish")

        player.fishing_has_bite = True
        self.assertTrue(player.reel_fishing_line())
        self.assertEqual(player.fishing_state, "reel")
        player.update_timers(FISHING_STATE_DURATIONS["reel"])
        self.assertFalse(player.fishing_active)
        self.assertEqual(player.inventory.count_item(species.name), 1)

    def test_ten_by_ten_island_contains_fishable_river_water(self):
        world = World(seed=17, chunk_size=(24, 24), tile_size=64)
        self.assertEqual(len(world.get_level_chunk_coords()), ISLAND_SIZE_CHUNKS ** 2)

        chunk_w, chunk_h = world.chunk_size
        center_x = world.spawn_chunk[0] * chunk_w + chunk_w // 2
        center_y = world.spawn_chunk[1] * chunk_h + chunk_h // 2
        radius = world.land_radius_chunks * min(chunk_w, chunk_h)
        along = radius * 0.62
        progress = (along - radius * 0.12) / radius
        across = (
            radius * world.river_cross_fraction
            + math.sin(progress * math.tau * 1.35 + world.river_phase) * radius * 0.07
        )
        direction_x, direction_y = ((1, 0), (0, 1), (-1, 0), (0, -1))[world.river_direction]
        perpendicular_x, perpendicular_y = -direction_y, direction_x
        river_tile = (
            round(center_x + direction_x * along + perpendicular_x * across),
            round(center_y + direction_y * along + perpendicular_y * across),
        )
        chunk_coord = (river_tile[0] // chunk_w, river_tile[1] // chunk_h)
        world.load_chunk(chunk_coord)

        self.assertTrue(world.is_river_tile(*river_tile))
        self.assertEqual(world.get_water_locality(river_tile), "river")


if __name__ == "__main__":
    unittest.main()
