import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

import pygame

from data.equipment import new_equipment_state
from data.items import ITEM_DEFINITIONS
from entities.player import Player
from gameplay.combat import CombatSystem
from gameplay.crafting import CraftingService
from gameplay.dialogue import DialogueResolver
from gameplay.equipment import EquipmentService
from gameplay.events import EventDispatcher
from gameplay.game_state import GameState
from gameplay.progression import ProgressionService
from gameplay.quests import QuestSystem
from gameplay.resources import deterministic_ore_id
from gameplay.savegame import _serialize_player, restore_player
from gameplay.world_objects import collect_pickups_near_player, ensure_chunk_environment_objects
from world.chunkmanager import Chunk


class StubInventory:
    def __init__(self, items=None):
        self.items = dict(items or {})
        self.slots = []
        self.selected_item_name = None
        self.crafted_counts = {}
        self.is_inv = False
        self.craft_system = SimpleNamespace(return_craft_product=lambda _item: None)

    def count_item(self, item_id):
        return self.items.get(item_id, 0)

    def remove_item_count(self, item_id, amount=1):
        if self.count_item(item_id) < amount:
            return False
        self.items[item_id] -= amount
        return True

    def add_item_to_slot(self, item, amount=1):
        self.items[item.name] = self.count_item(item.name) + amount
        return True

    def can_add_item(self, _item_id, _amount=1):
        return True

    def add_crafted_item(self, item_id, amount=1):
        self.crafted_counts[item_id] = self.crafted_counts.get(item_id, 0) + amount


def equipment_player(inventory=None, coins=200):
    player = Player.__new__(Player)
    player.tools = ["hoe", "axe", "pickaxe", "shovel", "water", "fishing rod", "sword", "spear", "shield"]
    player.equipment_state = {item_id: new_equipment_state(item_id) for item_id in player.tools}
    player.sync_equipment_compatibility()
    player.inventory = inventory or StubInventory()
    player.seed_inventory = {}
    player.coins = coins
    player.game_state = GameState()
    player.event_dispatcher = EventDispatcher()
    return player


class PhaseFourResourcesEquipmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_item_catalog_describes_raw_refined_and_rare_minerals(self):
        for item_id in (
            "coal_ore", "iron_ore", "iron", "gold_ore",
            "diamond_ore", "ruby_ore", "blue_sapphire_ore",
        ):
            with self.subTest(item=item_id):
                definition = ITEM_DEFINITIONS[item_id]
                self.assertTrue(definition.display_name)
                self.assertTrue(definition.icon_path)
                self.assertGreater(definition.stack_size, 0)
                self.assertTrue(definition.tags)

    def test_ore_selection_is_stable_and_weighted_toward_mountain(self):
        coordinates = [(x, y) for y in range(60) for x in range(60)]
        mountain = [deterministic_ore_id(81, tile, "mountain", danger=4) for tile in coordinates]
        grass = [deterministic_ore_id(81, tile, "grassland_and_forest", danger=1) for tile in coordinates]

        self.assertEqual(
            mountain,
            [deterministic_ore_id(81, tile, "mountain", danger=4) for tile in coordinates],
        )
        self.assertGreater(sum(item is not None for item in mountain), sum(item is not None for item in grass))
        self.assertIn("iron_ore", mountain)
        self.assertIn("coal_ore", mountain)
        self.assertTrue(set(mountain) & {"gold_ore", "diamond_ore", "ruby_ore", "blue_sapphire_ore"})

    def test_generated_ore_has_stable_world_id_and_collection_persists(self):
        chunk = Chunk((0, 0), (20, 20), 16)
        for name in ("terrain", "base"):
            chunk.layers[name] = [1] * 400
        chunk.layers["biome"] = [9] * 400
        chunk.layers["collision"] = [0] * 400
        chunk.metadata["danger"] = 4
        chunk.generate_environment_props(world_seed=19, max_props=400)
        ore_records = [record for record in chunk.props if record.get("prop_type") == "ore"]
        self.assertTrue(ore_records)
        ore = ore_records[0]
        self.assertIn(ore["pickup_item"], ITEM_DEFINITIONS)
        self.assertTrue(ore["id"].endswith(ore["pickup_item"]))

        chunk.props = [ore]
        chunk.runtime["environment_objects"] = {}
        ensure_chunk_environment_objects(chunk)
        world = SimpleNamespace(
            tile_size=16,
            current_player_chunk=(0, 0),
            spawn_chunk=(0, 0),
            loaded_chunks={(0, 0): chunk},
            get_chunks_near=lambda _coord, radius=1: ((0, 0),),
        )
        inventory = StubInventory()
        player = SimpleNamespace(
            inventory=inventory,
            get_interaction_box=lambda _reach: pygame.Rect(-10000, -10000, 20000, 20000),
        )
        self.assertTrue(collect_pickups_near_player(world, player))
        self.assertEqual(inventory.count_item(ore["pickup_item"]), 1)
        self.assertIn(ore["id"], chunk.save_data["removed_props"])

    def test_refining_is_atomic_unlocks_recipes_and_awards_craft_xp(self):
        inventory = StubInventory({"iron_ore": 2, "coal_ore": 1})
        player = equipment_player(inventory)
        progression = ProgressionService(player.game_state, player.event_dispatcher)
        crafting = CraftingService(inventory, player, player.game_state)

        result = crafting.craft("resources", "iron")

        self.assertTrue(result.success)
        self.assertEqual(inventory.count_item("iron_ore"), 0)
        self.assertEqual(inventory.count_item("coal_ore"), 0)
        self.assertEqual(inventory.count_item("iron"), 1)
        self.assertIn("recipes.refined_equipment", player.game_state.progression.unlocks)
        self.assertEqual(player.game_state.progression.experience, 5)
        progression.close()

    def test_failed_craft_does_not_consume_partial_ingredients(self):
        inventory = StubInventory({"iron_ore": 2})
        player = equipment_player(inventory)

        result = CraftingService(inventory, player, player.game_state).craft("resources", "iron")

        self.assertFalse(result.success)
        self.assertEqual(inventory.count_item("iron_ore"), 2)

    def test_recraft_repairs_without_losing_purchased_tier(self):
        inventory = StubInventory({"wood": 2, "rock": 1})
        player = equipment_player(inventory)
        hoe = player.equipment_state["hoe"]
        hoe.update(tier="sturdy", durability=0, max_durability=75, broken=True, upgrades_purchased=1)
        player.sync_equipment_compatibility()

        result = CraftingService(inventory, player, player.game_state).craft("tools", "hoe")

        self.assertTrue(result.success)
        self.assertEqual(player.equipment_state["hoe"]["tier"], "sturdy")
        self.assertEqual(player.equipment_state["hoe"]["durability"], 75)
        self.assertFalse(player.equipment_state["hoe"]["broken"])

    def test_jim_upgrade_repairs_increases_maximum_and_awards_once(self):
        player = equipment_player(coins=100)
        player.game_state.set_flag("services.jim_upgrades", True)
        progression = ProgressionService(player.game_state, player.event_dispatcher)
        service = EquipmentService(player, player.game_state)
        player.wear_tool("pickaxe", 12)

        result = service.upgrade("pickaxe")

        self.assertTrue(result.success)
        self.assertEqual(player.equipment_state["pickaxe"]["tier"], "sturdy")
        self.assertEqual(player.equipment_state["pickaxe"]["max_durability"], 68)
        self.assertEqual(player.equipment_state["pickaxe"]["durability"], 68)
        self.assertEqual(player.game_state.progression.experience, 20)
        self.assertEqual(player.coins, 80)
        progression.close()

    def test_successful_weapon_attack_consumes_durability(self):
        player = equipment_player()
        player.selected_tool = "sword"
        player.begin_combat_action = lambda _action, _duration: True
        player.feet_collision_box = pygame.Rect(0, 0, 8, 8)
        player.get_facing_offset = lambda: (1, 0)
        combat = CombatSystem(player, SimpleNamespace(), SimpleNamespace(npcs=[]))

        self.assertTrue(combat.sword_attack())
        self.assertEqual(player.equipment_state["sword"]["durability"], 99)

    def test_jim_dialogue_unlocks_and_returns_upgrade_service(self):
        state = GameState()
        quests = QuestSystem(state)
        resolver = DialogueResolver(state, quests)

        node = resolver.resolve("jim")
        self.assertEqual(node["id"], "jim.upgrades.introduction")
        results = resolver.complete("jim", node)
        self.assertIn("open_upgrade_service", results)
        self.assertTrue(state.flag("services.jim_upgrades"))
        self.assertEqual(resolver.resolve("jim")["id"], "jim.upgrades.service")

    def test_equipment_tier_and_durability_restore_from_save_payload(self):
        player = equipment_player()
        player.equipment_state["axe"].update(
            tier="forged",
            durability=44,
            max_durability=80,
            upgrades_purchased=2,
        )
        player.sync_equipment_compatibility()
        player.pos = pygame.Vector2(10, 20)
        player.customization = {}
        player.health = player.max_health = 5
        player.selected_tool = "axe"
        player.water_amount = player.water_capacity = 8
        player.harvested_crops = {}
        player.selected_seed = "corn"
        player.seeds = ["corn"]
        player.world_hint_seen = set()
        payload = _serialize_player(player)

        restored = equipment_player()
        restored.pos = pygame.Vector2()
        restored.rect = pygame.Rect(0, 0, 32, 32)
        restored.sync_collision_boxes = lambda: None
        restored.health = restored.max_health = 5
        restored.water_amount = restored.water_capacity = 8
        restored.harvested_crops = {}
        restored.selected_seed = "corn"
        restored.seeds = ["corn"]
        restored.seed_index = 0
        restored.world_hint_seen = set()
        restored.selected_tool = "hoe"
        restored.tool_index = 0
        restored._sync_equipped_tool = lambda refresh=True: None

        restore_player(restored, payload)

        self.assertEqual(restored.equipment_state["axe"]["tier"], "forged")
        self.assertEqual(restored.equipment_state["axe"]["durability"], 44)
        self.assertEqual(restored.equipment_state["axe"]["max_durability"], 80)


if __name__ == "__main__":
    unittest.main()
