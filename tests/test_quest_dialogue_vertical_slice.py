import sys
import unittest
from pathlib import Path


CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from gameplay.dialogue import DialogueResolver
from gameplay.events import CropHarvested, CropWatered, EventDispatcher
from gameplay.game_state import GameState
from gameplay.progression import ProgressionService
from gameplay.quests import ACTIVE, AVAILABLE, COMPLETED, READY_TO_TURN_IN, QuestSystem
from gameplay.story_scene import ensure_morning_chores_test_scene
from world.chunkmanager import Chunk


QUEST_ID = "prologue.morning_chores"


class MorningChoresVerticalSliceTests(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.dispatcher = EventDispatcher()
        self.progression = ProgressionService(self.state, self.dispatcher)
        self.quests = QuestSystem(self.state, self.dispatcher)
        self.dialogue = DialogueResolver(self.state, self.quests, self.dispatcher)

    def tearDown(self):
        self.quests.close()
        self.progression.close()

    def publish_water(self, number, *, crop="corn", location="player_farm"):
        self.dispatcher.publish(
            CropWatered(
                event_id=f"water:{number}",
                crop_id=crop,
                location_id=location,
                world_tile=(number, 1),
            )
        )

    def publish_harvest(self, number, *, crop="tomato", count=1, location="player_farm"):
        self.dispatcher.publish(
            CropHarvested(
                event_id=f"harvest:{number}",
                crop_id=crop,
                count=count,
                location_id=location,
                world_tile=(number, 2),
            )
        )

    def test_complete_offer_objectives_turn_in_repeat_and_reload(self):
        self.assertEqual(self.quests.status(QUEST_ID), AVAILABLE)
        offer = self.dialogue.resolve("wife")
        self.assertEqual(offer["id"], "wife.morning_chores.offer")
        self.assertEqual(
            {choice["converges_to"] for choice in offer["choices"]},
            {"accept_chores"},
        )

        self.dialogue.complete("wife", offer, "where")
        self.assertEqual(self.quests.status(QUEST_ID), ACTIVE)
        self.assertEqual(self.state.tracked_quest_id, QUEST_ID)
        self.assertIn(offer["id"], self.state.dialogue.consumed_nodes)
        self.assertEqual(self.state.dialogue.facts[f"choice:{offer['id']}"], "where")
        self.assertEqual(self.dialogue.resolve("wife")["id"], "wife.morning_chores.reminder")

        self.publish_water(0, crop="wheat")
        self.publish_water(1, location="village")
        for number in range(2, 5):
            self.publish_water(number)
        # Re-publishing one event must not increment an objective twice.
        self.publish_water(4)
        self.publish_harvest(0, count=2)

        quest_state = self.quests.get_state(QUEST_ID)
        self.assertEqual(quest_state["objectives"], {"water_crops": 3, "harvest_breakfast": 2})
        self.assertEqual(quest_state["status"], READY_TO_TURN_IN)
        turn_in = self.dialogue.resolve("wife")
        self.assertEqual(turn_in["id"], "wife.morning_chores.turn_in")

        self.dialogue.complete("wife", turn_in)
        self.assertEqual(self.quests.status(QUEST_ID), COMPLETED)
        self.assertTrue(self.state.flag("prologue.morning_chores_complete"))
        self.assertEqual(self.state.progression.experience, 25)
        self.assertIsNone(self.state.tracked_quest_id)
        self.assertEqual(self.dialogue.resolve("wife")["id"], "wife.morning_chores.complete")

        saved = self.state.to_dict()
        restored = GameState.from_dict(saved)
        restored_quests = QuestSystem(restored)
        restored_dialogue = DialogueResolver(restored, restored_quests)
        self.assertEqual(restored_quests.status(QUEST_ID), COMPLETED)
        self.assertEqual(restored.quests[QUEST_ID]["objectives"], quest_state["objectives"])
        self.assertIn(turn_in["id"], restored.dialogue.consumed_nodes)
        self.assertEqual(restored_dialogue.resolve("wife")["id"], "wife.morning_chores.complete")

    def test_start_turn_in_and_rewards_are_idempotent(self):
        offer = self.dialogue.resolve("wife")
        self.assertTrue(self.dialogue.complete("wife", offer, "ready"))
        self.assertFalse(self.quests.start(QUEST_ID))
        for number in range(3):
            self.publish_water(number)
        for number in range(2):
            self.publish_harvest(number)
        self.assertTrue(self.quests.turn_in(QUEST_ID))
        self.assertFalse(self.quests.turn_in(QUEST_ID))
        self.assertEqual(self.state.progression.experience, 25)

    def test_game_state_snapshot_does_not_share_objective_dicts(self):
        self.quests.start(QUEST_ID)
        restored = GameState.from_dict(self.state.to_dict())
        restored.quests[QUEST_ID]["objectives"]["water_crops"] = 2
        self.assertEqual(self.state.quests[QUEST_ID]["objectives"]["water_crops"], 0)

    def test_developer_scene_has_three_growing_and_two_ripe_crops(self):
        chunk = Chunk((0, 0), (20, 20), 16)
        chunk.layers["terrain"] = [1] * 400

        class World:
            tile_size = 16
            chunk_size = (20, 20)

            def __init__(self):
                self.invalidated = []

            @staticmethod
            def get_spawn_position():
                return 160, 160

            def invalidate_soil_chunk_and_neighbors(self, coord):
                self.invalidated.append(coord)

        class Soil:
            def __init__(self, world):
                self.world = world

            @staticmethod
            def can_till_at_tile(tile):
                return 0 <= tile[0] < 20 and 0 <= tile[1] < 20

            @staticmethod
            def get_chunk_and_local(tile):
                return chunk, tile

        world = World()
        soil = Soil(world)
        self.state.set_flag("game.mode", "story")

        tiles = ensure_morning_chores_test_scene(world, soil, self.state)

        self.assertEqual(len(tiles), 5)
        plants = [chunk.layers["plant"][chunk.get_index(*tile)] for tile in tiles]
        self.assertTrue(all(plant["age"] < 1 for plant in plants[:3]))
        self.assertTrue(all(plant["age"] == 1 for plant in plants[3:]))
        self.assertEqual({plant["type"] for plant in plants}, {"corn", "tomato"})
        self.assertEqual(ensure_morning_chores_test_scene(world, soil, self.state), tiles)


if __name__ == "__main__":
    unittest.main()
