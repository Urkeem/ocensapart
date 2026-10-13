import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

import pygame

from gameplay.interactions import InteractionSystem, InteractionTarget


class InteractionSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    @staticmethod
    def npc(x, *, story_id=None, save_id=None, alive=True, location_id="player_farm"):
        return SimpleNamespace(
            rect=pygame.Rect(x - 8, 92, 16, 16),
            story_id=story_id,
            save_id=save_id,
            is_alive=alive,
            is_merchant=False,
            location_id=location_id,
        )

    def test_story_priority_breaks_close_distance_ties(self):
        player = SimpleNamespace(feet_collision_box=pygame.Rect(92, 92, 16, 16))
        villager = self.npc(108, save_id="villager:1")
        wife = self.npc(114, story_id="wife", save_id="story:wife")
        system = InteractionSystem(SimpleNamespace(npcs=[villager, wife]))

        target = system.find_best(player)

        self.assertIs(target.entity, wife)
        self.assertEqual(target.target_id, "wife")

    def test_registered_world_targets_share_the_same_ranking(self):
        player = SimpleNamespace(feet_collision_box=pygame.Rect(92, 92, 16, 16))
        villager = self.npc(130, save_id="villager:1")
        system = InteractionSystem(SimpleNamespace(npcs=[villager]))
        door = object()

        unregister = system.register_provider(
            lambda _player, _distance: (
                InteractionTarget("farmhouse-door", "door", door, (104, 100), 4),
            )
        )
        self.assertIs(system.find_best(player).entity, door)
        self.assertTrue(unregister())
        self.assertIs(system.find_best(player).entity, villager)

    def test_nearby_world_npc_is_talkable_across_world_district_labels(self):
        player = SimpleNamespace(feet_collision_box=pygame.Rect(92, 92, 16, 16))
        lillian = self.npc(108, story_id="lillian", location_id="lillian_home")
        wife = self.npc(108, story_id="wife", location_id="player_house_interior")
        system = InteractionSystem(SimpleNamespace(npcs=[lillian, wife]))
        system.current_location_id = "player_farm"

        target = system.find_best(player)

        self.assertIs(target.entity, lillian)
        self.assertNotEqual(target.entity, wife)


if __name__ == "__main__":
    unittest.main()
