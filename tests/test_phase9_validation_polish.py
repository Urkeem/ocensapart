import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from data.content_validation import validate_all_content, validate_content
from data.quests import QUEST_DEFINITIONS, STORY_QUESTS
from gameplay.dialogue import DialogueResolver
from gameplay.events import (
    AccessDenied,
    CropHarvested,
    CropWatered,
    DialogueSelected,
    EventDispatcher,
    ItemCrafted,
    QuestStateChanged,
)
from gameplay.game_state import AccessibilityState, GameState
from gameplay.progression import ProgressionService
from gameplay.quests import AVAILABLE, COMPLETED, READY_TO_TURN_IN, QuestSystem
from gameplay.telemetry import DevelopmentTelemetry
from gameplay.presentation import StoryPresentation
from ui.dialogue import StoryDialogue
from ui.quest_journal import QuestJournalUI
from gameplay.controls import BUTTON_CANCEL, BUTTON_CONFIRM, BUTTON_DPAD_RIGHT, BUTTON_JOURNAL
from gameplay.controls import BUTTON_TOOL
from gameplay.startup import StartupFlow
import tests.test_phase8_story_campaign as phase8_campaign


class Phase9ValidationPolishTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((960, 640))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_full_content_and_balance_validator_passes(self):
        self.assertEqual(tuple(map(str, validate_all_content())), ())

    def test_validator_reports_dangling_quest_prerequisite(self):
        quest = QUEST_DEFINITIONS["prologue.morning_chores"]
        original = quest["prerequisites"]
        quest["prerequisites"] = ("missing.quest",)
        try:
            issues = validate_content(include_assets=False)
            self.assertTrue(any("requires unknown quest missing.quest" in str(issue) for issue in issues))
        finally:
            quest["prerequisites"] = original

    def test_accessibility_settings_round_trip_and_migrate_defaults(self):
        state = GameState()
        state.accessibility = AccessibilityState(1.5, True, True, "instant")
        restored = GameState.from_dict(state.to_dict())
        self.assertEqual(restored.accessibility.to_dict(), state.accessibility.to_dict())
        migrated = GameState.from_dict({"flags": {"game.mode": "story"}})
        self.assertEqual(migrated.accessibility.to_dict(), AccessibilityState().to_dict())
        clamped = AccessibilityState.from_dict({"text_scale": 8, "dialogue_speed": "unknown"})
        self.assertEqual(clamped.text_scale, 1.5)
        self.assertEqual(clamped.dialogue_speed, "normal")

    def test_accessibility_menu_opens_with_keyboard_and_controller(self):
        flow = StartupFlow.__new__(StartupFlow)
        flow.stage = "title"
        flow.game_state = GameState()
        flow.settings_index = 0
        flow.settings_rows = ("text_scale", "high_contrast", "reduced_motion", "dialogue_speed")
        flow.loading_note = ""
        flow.quit_requested = False
        flow.controller_input = SimpleNamespace(
            handle_event=lambda _event: None,
            menu_navigation_button=lambda _event: None,
        )
        flow.save_manager = SimpleNamespace(exists=False)
        flow.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_s, unicode="s"))
        self.assertEqual(flow.stage, "settings")
        flow.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT, unicode=""))
        self.assertEqual(flow.game_state.accessibility.text_scale, 1.25)
        flow.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=""))
        self.assertEqual(flow.stage, "title")
        flow.handle_event(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=BUTTON_TOOL))
        self.assertEqual(flow.stage, "settings")

    def test_development_telemetry_captures_all_diagnostic_domains(self):
        state = GameState()
        dispatcher = EventDispatcher()
        telemetry = DevelopmentTelemetry(True).bind(dispatcher)
        progression = ProgressionService(state, dispatcher)
        quests = QuestSystem(state, dispatcher)
        dialogue = DialogueResolver(state, quests, dispatcher)
        try:
            dialogue.resolve("wife")
            quests.start("prologue.morning_chores")
            dispatcher.publish(CropWatered(event_id="water:1", crop_id="corn", location_id="player_farm"))
            dispatcher.publish(CropHarvested(event_id="harvest:1", crop_id="corn", count=2, location_id="player_farm"))
            dispatcher.publish(
                AccessDenied(event_id="denied:1", location_id="hold_5", reason="Find the Ironveil Key.")
            )
            categories = {record["category"] for record in telemetry.snapshot()}
            self.assertIn("DialogueSelected", categories)
            self.assertIn("QuestStateChanged", categories)
            self.assertIn("ProgressionUpdated", categories)
            self.assertIn("AccessDenied", categories)
            progression_records = [r for r in telemetry.snapshot() if r["category"] == "ProgressionUpdated"]
            self.assertTrue(all(record["source_id"] for record in progression_records))
            self.assertTrue(all(record["amount"] > 0 for record in progression_records))
        finally:
            dialogue = None
            quests.close()
            progression.close()
            telemetry.close()

    def test_telemetry_disabled_has_no_runtime_trace(self):
        telemetry = DevelopmentTelemetry(False)
        telemetry.record("anything", amount=10)
        self.assertEqual(telemetry.snapshot(), ())

    def test_act_completion_queues_final_presentation(self):
        dispatcher = EventDispatcher()
        presentation = StoryPresentation(
            pygame.display.get_surface(),
            dispatcher,
            AccessibilityState(reduced_motion=True),
        )
        try:
            dispatcher.publish(
                QuestStateChanged(
                    event_id="quest:epilogue",
                    quest_id="epilogue.rebuilding",
                    old_status="ready_to_turn_in",
                    new_status="completed",
                    reason="turned_in",
                )
            )
            self.assertTrue(presentation.active)
            self.assertEqual(presentation.current[0], "Ironveil Reborn")
            presentation.draw()
            presentation.update(presentation.duration)
            self.assertFalse(presentation.active)
        finally:
            presentation.close()

    def test_dialogue_pacing_and_keyboard_controller_actions_match(self):
        state = GameState(accessibility=AccessibilityState(dialogue_speed="normal"))
        node = {"id": "test.node", "lines": ({"speaker": "Test", "text": "A deliberately paced line."},)}
        resolver = SimpleNamespace(resolve=lambda _npc_id: node, complete=lambda *_args: (True,))
        player = SimpleNamespace(
            game_state=state,
            inventory=SimpleNamespace(is_inv=False),
            dialogue_active=False,
        )
        npc = SimpleNamespace(story_id="test", dialogue_name="Test")
        dialogue = StoryDialogue(pygame.display.get_surface(), player, resolver)
        self.assertTrue(dialogue.open(npc))
        self.assertFalse(dialogue.current_line_revealed)
        dialogue.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertTrue(dialogue.active)
        self.assertTrue(dialogue.current_line_revealed)
        dialogue.handle_event(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=BUTTON_CONFIRM))
        self.assertFalse(dialogue.active)

    def test_journal_has_controller_navigation_and_close_parity(self):
        state = GameState()
        quests = QuestSystem(state)
        player = SimpleNamespace(game_state=state, inventory=SimpleNamespace(is_inv=False), journal_active=False)
        journal = QuestJournalUI(pygame.display.get_surface(), player, quests)
        self.assertTrue(journal.handle_event(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=BUTTON_JOURNAL)))
        original_category = journal.category_index
        journal.handle_event(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=BUTTON_DPAD_RIGHT))
        self.assertNotEqual(journal.category_index, original_category)
        self.assertTrue(journal.handle_event(pygame.event.Event(pygame.CONTROLLERBUTTONDOWN, button=BUTTON_CANCEL)))
        self.assertFalse(journal.open)

    def test_representative_migrated_story_state_advances_without_duplicate_rewards(self):
        legacy = {
            "flags": {"game.mode": "story", "prologue.morning_chores_complete": True},
            "quests": {
                "prologue.morning_chores": {
                    "status": "completed",
                    "objectives": {"water_crops": 3, "harvest_breakfast": 2},
                    "reward_claimed": True,
                }
            },
            "progression": {"experience": 25, "kingdom_reputation": 0},
        }
        campaign = phase8_campaign.Phase8StoryCampaignTests(
            methodName="test_full_dependency_map_completes_from_a_new_story_save"
        )
        state, dispatcher, progression, player, quests, dialogue, _ = campaign.make_runtime(GameState.from_dict(legacy))
        try:
            for quest in STORY_QUESTS:
                quest_id = quest["id"]
                if quests.status(quest_id) == COMPLETED:
                    continue
                self.assertEqual(quests.status(quest_id), AVAILABLE, quest_id)
                offer = campaign.action_node(dialogue, quest["giver"], "start_quest", quest_id)
                choices = offer.get("choices", ())
                dialogue.complete(quest["giver"], offer, choices[0]["id"] if choices else None)
                for objective in quest["objectives"]:
                    campaign.publish_objective(quest, objective, state, dispatcher, player, dialogue)
                self.assertEqual(quests.status(quest_id), READY_TO_TURN_IN, quest_id)
                turn_in = campaign.action_node(dialogue, quest["turn_in"], "turn_in_quest", quest_id)
                choices = turn_in.get("choices", ())
                dialogue.complete(quest["turn_in"], turn_in, choices[0]["id"] if choices else None)
                self.assertEqual(quests.status(quest_id), COMPLETED, quest_id)
            self.assertTrue(state.flag("game.story_complete"))
            experience = state.progression.experience
            self.assertFalse(quests.turn_in("prologue.morning_chores"))
            self.assertEqual(state.progression.experience, experience)
        finally:
            quests.close()
            progression.close()


if __name__ == "__main__":
    unittest.main()
