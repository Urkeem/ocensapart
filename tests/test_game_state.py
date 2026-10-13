import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from gameplay.events import (
    CropHarvested,
    DomainEvent,
    EnemyDefeated,
    EquipmentUpgraded,
    EventDispatcher,
    FishCaught,
    GiftGiven,
    ItemCrafted,
    NpcRescued,
    ProgressionGranted,
)
from gameplay.game_state import GameState, stable_encounter_id
from gameplay.progression import ProgressionService


class GameStateTests(unittest.TestCase):
    def setUp(self):
        self.state = GameState()
        self.events = EventDispatcher()
        self.progression = ProgressionService(self.state, self.events)

    def tearDown(self):
        self.progression.close()

    def test_dispatcher_notifies_specific_and_base_event_subscribers(self):
        received = []
        dispatcher = EventDispatcher()
        dispatcher.subscribe(DomainEvent, lambda event: received.append(("base", event.event_id)))
        dispatcher.subscribe(CropHarvested, lambda event: received.append(("crop", event.crop_id)))

        dispatcher.publish(CropHarvested(event_id="harvest:1", crop_id="corn"))

        self.assertEqual(received, [("base", "harvest:1"), ("crop", "corn")])

    def test_events_update_each_progression_track_once(self):
        events = (
            CropHarvested(event_id="harvest:1", crop_id="corn"),
            CropHarvested(event_id="harvest:2", crop_id="tomato"),
            FishCaught(event_id="fish:1", fish_id="pond.spring.1", locality="pond", required_reels=3),
            ItemCrafted(event_id="craft:1", item_id="hoe", recipe_id="tools.hoe"),
            EquipmentUpgraded(event_id="upgrade:1", equipment_id="hoe", old_tier="basic", new_tier="sturdy"),
            EnemyDefeated(event_id="enemy:1", enemy_id="goblin_berserker", tier="primary"),
            ProgressionGranted(event_id="quest:1", source_id="test_quest", kingdom_reputation=7),
        )
        for event in events:
            self.events.publish(event)
            self.events.publish(event)

        self.assertEqual(self.state.progression.farming_points, 5)
        self.assertEqual(self.state.progression.fishing_points, 3)
        self.assertEqual(self.state.progression.experience, 35)
        self.assertEqual(self.state.progression.kingdom_reputation, 7)
        self.assertEqual(len(self.state.event_receipts["progression"]), len(events))

    def test_level_gain_awards_one_skill_point_per_level(self):
        self.events.publish(
            ProgressionGranted(
                event_id="quest:levels",
                source_id="level_test",
                experience=300,
            )
        )
        self.assertEqual(self.state.progression.level, 3)
        self.assertEqual(self.state.progression.skill_points, 2)

    def test_trust_is_per_character_and_repeat_daily_gifts_are_reduced(self):
        self.events.publish(
            GiftGiven(
                event_id="gift:1",
                npc_id="wife",
                item_id="tomato",
                preference="favorite",
                day=2,
            )
        )
        self.events.publish(
            GiftGiven(
                event_id="gift:2",
                npc_id="wife",
                item_id="corn",
                preference="favorite",
                day=2,
            )
        )
        self.events.publish(
            NpcRescued(
                event_id="rescue:1",
                npc_id="hunter",
                encounter_id="encounter:forest:hunter:1",
            )
        )

        self.assertEqual(self.state.relationship("wife").trust, 10)
        self.assertEqual(self.state.relationship("wife").tier, "guarded")
        self.assertEqual(self.state.relationship("hunter").trust, 10)
        self.assertEqual(self.state.progression.kingdom_reputation, 5)

    def test_receipts_are_independent_for_future_consumers(self):
        self.assertTrue(self.state.claim_event("progression", "shared:1"))
        self.assertFalse(self.state.claim_event("progression", "shared:1"))
        self.assertTrue(self.state.claim_event("quests", "shared:1"))

    def test_round_trip_preserves_all_phase_one_state(self):
        self.state.set_flag("prologue.started")
        self.state.quests["prologue.morning_chores"] = {"status": "active"}
        self.state.remember_dialogue_node("wife.prologue.intro")
        self.state.add_trust("wife", 27)
        self.state.add_experience(125)
        self.state.add_farming_points(9)
        self.state.add_fishing_points(4)
        self.state.add_kingdom_reputation(3)
        self.state.stamina = 73.5
        self.state.awake_game_minutes = 615
        self.state.set_story_npc_state("wife", location_id="player_house_interior")
        encounter_id = self.state.register_encounter("player_farm", "first_attack", wave=1)
        self.state.update_encounter(encounter_id, defeated_enemy_ids=["goblin:1"])
        self.state.claim_event("progression", "harvest:9")
        self.state.next_event_id("crop_harvested")

        restored = GameState.from_dict(self.state.to_dict())

        self.assertEqual(restored.to_dict(), self.state.to_dict())
        self.assertEqual(encounter_id, stable_encounter_id("player_farm", "first_attack"))
        self.assertEqual(restored.encounters[encounter_id]["wave"], 1)


if __name__ == "__main__":
    unittest.main()
