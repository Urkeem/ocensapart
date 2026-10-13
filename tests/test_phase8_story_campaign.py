import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from data.crafting import RECIPES
from data.dialogue import DIALOGUE_DEFINITIONS
from data.encounters import ENCOUNTER_DEFINITIONS
from data.items import ITEM_DEFINITIONS
from data.quests import QUEST_DEFINITIONS, STORY_QUESTS
from gameplay.dialogue import DialogueResolver
from gameplay.crafting import CraftingService
from gameplay.events import CropHarvested, CropWatered, DialogueCompleted, EncounterCompleted, EventDispatcher, ItemCrafted
from gameplay.game_state import GameState
from gameplay.progression import ProgressionService
from gameplay.quests import ACTIVE, AVAILABLE, COMPLETED, READY_TO_TURN_IN, QuestSystem


class Inventory:
    def __init__(self):
        self.items = {}

    def count_item(self, item_id):
        return self.items.get(item_id, 0)

    def can_add_item(self, _item_id, _count=1):
        return True

    def add_item_to_slot(self, item, count=1):
        self.items[item.name] = self.count_item(item.name) + count
        return True

    def remove_item_count(self, item_id, count=1):
        if self.count_item(item_id) < count:
            return False
        self.items[item_id] -= count
        return True

    def add_crafted_item(self, _item_id, _count=1):
        return True


class SurvivorSequence:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    def complete_sequence(self, position=None):
        self.calls += 1
        self.state.set_flag("farm.hunter_survivors_settled", True)
        for index in range(3):
            self.state.set_story_npc_state(
                f"grimroot_survivor_{index + 1}",
                location_id="player_farm",
                community_member=True,
                rescue_stage="settled_at_farm",
            )
        return True, ""


class Phase8StoryCampaignTests(unittest.TestCase):
    def make_runtime(self, state=None, inventory=None):
        state = state or GameState()
        state.set_flag("game.mode", "story")
        dispatcher = EventDispatcher()
        progression = ProgressionService(state, dispatcher)
        player = SimpleNamespace(
            inventory=inventory or Inventory(),
            pos=(160, 160),
            seed_inventory={},
            game_state=state,
            event_dispatcher=dispatcher,
        )
        quests = QuestSystem(state, dispatcher, player=player)
        survivors = SurvivorSequence(state)
        dialogue = DialogueResolver(state, quests, dispatcher, player=player).set_services(
            survivor_transport=survivors
        )
        return state, dispatcher, progression, player, quests, dialogue, survivors

    @staticmethod
    def action_node(dialogue, npc_id, action_type, quest_id):
        for node in dialogue.definitions[npc_id]:
            if not dialogue.eligible(node):
                continue
            if any(
                action.get("type") == action_type and action.get("quest_id") == quest_id
                for action in node.get("actions", ())
            ):
                return node
        raise AssertionError(f"No eligible {action_type} dialogue for {quest_id} on {npc_id}")

    def publish_objective(self, quest, objective, state, dispatcher, player, dialogue):
        event_name = objective["event"]
        filters = objective.get("filters", {})
        required = int(objective.get("required", 1))
        event_id = f"phase8:{quest['id']}:{objective['id']}"
        if event_name == "CropWatered":
            for index in range(required):
                dispatcher.publish(CropWatered(event_id=f"{event_id}:{index}", crop_id="corn", location_id="player_farm"))
        elif event_name == "CropHarvested":
            dispatcher.publish(CropHarvested(event_id=event_id, crop_id="corn", count=required, location_id="player_farm"))
        elif event_name == "EncounterCompleted":
            encounter_id = filters["encounter_id"]
            definition = ENCOUNTER_DEFINITIONS[encounter_id]
            if definition.completion_flag:
                state.set_flag(definition.completion_flag, True)
            dispatcher.publish(EncounterCompleted(event_id=event_id, encounter_id=encounter_id, waves_completed=len(definition.waves)))
        elif event_name == "ItemCrafted":
            item_id = filters["item_id"]
            player.inventory.items[item_id] = player.inventory.count_item(item_id) + required
            dispatcher.publish(ItemCrafted(event_id=event_id, item_id=item_id, recipe_id=f"story.{item_id}", count=required))
        elif event_name == "DialogueCompleted":
            node_ids = filters["node_id"]
            if isinstance(node_ids, str):
                node_ids = (node_ids,)
            for node_id in node_ids:
                npc_id = node_id.split(".", 1)[0]
                node = next(node for node in dialogue.definitions[npc_id] if node["id"] == node_id)
                self.assertTrue(dialogue.eligible(node), node_id)
                choice = node.get("choices", ())
                dialogue.complete(npc_id, node, choice[0]["id"] if choice else None)
        else:
            raise AssertionError(f"Unhandled objective event {event_name}")

    def test_story_content_references_are_complete(self):
        node_ids = {
            node["id"]
            for dialogue in DIALOGUE_DEFINITIONS.values()
            for node in dialogue
        }
        self.assertEqual(len(STORY_QUESTS), 23)
        for quest in STORY_QUESTS:
            self.assertIn(quest["giver"], DIALOGUE_DEFINITIONS)
            self.assertIn(quest["turn_in"], DIALOGUE_DEFINITIONS)
            for prerequisite in quest["prerequisites"]:
                if isinstance(prerequisite, str):
                    self.assertIn(prerequisite, QUEST_DEFINITIONS)
            for objective in quest["objectives"]:
                if objective["event"] == "EncounterCompleted":
                    self.assertIn(objective["filters"]["encounter_id"], ENCOUNTER_DEFINITIONS)
                if objective["event"] == "DialogueCompleted":
                    expected = objective["filters"]["node_id"]
                    for node_id in (expected,) if isinstance(expected, str) else expected:
                        self.assertIn(node_id, node_ids)
        for item_id in (
            "kingdom_map", "temporary_medicine", "royal_medicine", "potion_of_life",
            "potion_of_memory", "potion_of_vigor", "last_cure", "cured_seed_bag",
            "hollow_crypt_key", "ironveil_key", "royal_tiara",
        ):
            self.assertIn(item_id, ITEM_DEFINITIONS)
        self.assertIn("story.temporary_medicine", RECIPES)
        self.assertIn("story.royal_medicine", RECIPES)
        self.assertIn("story.last_cure", RECIPES)

    def test_full_dependency_map_completes_from_a_new_story_save(self):
        state, dispatcher, progression, player, quests, dialogue, survivors = self.make_runtime()
        try:
            for quest_index, quest in enumerate(STORY_QUESTS):
                quest_id = quest["id"]
                self.assertEqual(quests.status(quest_id), AVAILABLE, quest_id)
                offer = self.action_node(dialogue, quest["giver"], "start_quest", quest_id)
                choices = offer.get("choices", ())
                dialogue.complete(quest["giver"], offer, choices[0]["id"] if choices else None)
                self.assertIn(quests.status(quest_id), (ACTIVE, READY_TO_TURN_IN), quest_id)
                for objective in quest["objectives"]:
                    self.publish_objective(quest, objective, state, dispatcher, player, dialogue)
                self.assertEqual(quests.status(quest_id), READY_TO_TURN_IN, quest_id)

                if quest_id == "holds.grimroot":
                    saved = state.to_dict()
                    quests.close()
                    progression.close()
                    state, dispatcher, progression, player, quests, dialogue, reloaded_survivors = self.make_runtime(
                        GameState.from_dict(saved), player.inventory
                    )
                    survivors.calls += reloaded_survivors.calls

                turn_in = self.action_node(dialogue, quest["turn_in"], "turn_in_quest", quest_id)
                choices = turn_in.get("choices", ())
                dialogue.complete(quest["turn_in"], turn_in, choices[0]["id"] if choices else None)
                self.assertEqual(quests.status(quest_id), COMPLETED, quest_id)

            self.assertTrue(state.flag("game.story_complete"))
            self.assertTrue(state.flag("world.kingdom_restored"))
            self.assertTrue(state.flag("act8.wife_cured"))
            self.assertTrue(state.flag("farm.hunter_survivors_settled"))
            self.assertGreaterEqual(state.progression.level, 12)
            self.assertTrue(state.transports["pirate_ship"]["unlocked"])
            for npc_id in ("hunter", "pirate", "princess", "royal_soldier_1", "royal_soldier_2", "alchemist_family_1", "alchemist_family_2"):
                self.assertTrue(state.story_npcs[npc_id]["recruited"])
            epilogue = dialogue.resolve("wife")
            self.assertEqual(epilogue["id"], "wife.epilogue.community")
            self.assertIn("survivors", epilogue["lines"][0]["text"].lower())
        finally:
            quests.close()
            progression.close()

    def test_story_reward_waits_for_inventory_space(self):
        state, _, progression, player, quests, _, _ = self.make_runtime()
        try:
            player.inventory.can_add_item = lambda _item_id, _count=1: False
            self.assertFalse(quests.apply_action({"type": "give_item", "item_id": "royal_tiara"}))
            self.assertEqual(state.flag("story.pending_items"), {"royal_tiara": 1})
            player.inventory.can_add_item = lambda _item_id, _count=1: True
            self.assertEqual(quests.claim_pending_items(), (("royal_tiara", 1),))
            self.assertEqual(player.inventory.count_item("royal_tiara"), 1)
            self.assertIsNone(state.flag("story.pending_items"))
        finally:
            quests.close()
            progression.close()

    def test_story_medicines_craft_through_the_normal_recipe_service(self):
        state, _, progression, player, quests, _, _ = self.make_runtime()
        try:
            service = CraftingService(player.inventory, player, state)
            state.unlock("recipes.temporary_medicine")
            player.inventory.items.update(corn=5, tomato=5, weed=1, shell=1)
            self.assertTrue(service.craft("story", "temporary_medicine").success)
            self.assertEqual(player.inventory.count_item("temporary_medicine"), 1)
            state.unlock("recipes.royal_medicine")
            self.assertTrue(service.craft("story", "royal_medicine").success)
            self.assertEqual(player.inventory.count_item("royal_medicine"), 1)

            state.unlock("recipes.last_cure")
            player.inventory.items.update(
                potion_of_life=1,
                potion_of_memory=1,
                potion_of_vigor=1,
            )
            self.assertTrue(service.craft("story", "last_cure").success)
            self.assertEqual(player.inventory.count_item("last_cure"), 1)
            self.assertEqual(player.inventory.count_item("potion_of_life"), 0)
        finally:
            quests.close()
            progression.close()


if __name__ == "__main__":
    unittest.main()
