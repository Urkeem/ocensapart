import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

import pygame

from entities.player import Player
from entities.npc import NPCManager
from data.story import KINGDOM_LOCATION_CHUNK_OFFSETS
from data.items import TREE_FRUITS
from gameplay.crafting import CraftingService
from gameplay.controls import BUTTON_CONSUME, BUTTON_TOOL
from gameplay.effects import EffectsManager
from gameplay.game_state import GameState
from gameplay.quests import QuestSystem
from ui.hud import GameplayHUD, NEARBY_ENEMY_RADIUS
from ui.inventory import Inventory_UI
from ui.quest_journal import TRACKED_QUEST_TOP
from world.worldmanager import KINGDOM_SIZE_CHUNKS, WorldRun


class TinyInventory:
    def __init__(self, counts=None):
        self.counts = dict(counts or {})
        self.crafted_counts = {}
        self.hotbar_item_name = None

    def count_item(self, item_id):
        return self.counts.get(item_id, 0)

    def remove_item_count(self, item_id, amount=1):
        if self.count_item(item_id) < amount:
            return False
        self.counts[item_id] -= amount
        return True

    def add_crafted_item(self, item_id, amount=1):
        self.crafted_counts[item_id] = self.crafted_counts.get(item_id, 0) + amount

    @staticmethod
    def can_add_item(_item_id, _amount=1):
        return True


class GameplayUsabilityPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_one_harvested_crop_crafts_three_seeds(self):
        state = GameState()
        inventory = TinyInventory({"corn": 1})
        player = SimpleNamespace(
            game_state=state,
            seed_inventory={"corn": 0},
            event_dispatcher=None,
        )

        result = CraftingService(inventory, player, state).craft("seeds", "corn")

        self.assertTrue(result.success)
        self.assertEqual(result.count, 3)
        self.assertEqual(player.seed_inventory["corn"], 3)
        self.assertEqual(inventory.count_item("corn"), 0)

    def test_eat_action_prefers_the_selected_hotbar_food(self):
        state = GameState()
        state.stamina = 40
        inventory = TinyInventory({"corn": 1, "apple": 1})
        player = SimpleNamespace(
            game_state=state,
            stamina_enabled=True,
            inventory=inventory,
            selected_consumable="apple",
        )

        restored = Player.consume_food(player)

        self.assertEqual(restored, 10)
        self.assertEqual(inventory.count_item("apple"), 0)
        self.assertEqual(inventory.count_item("corn"), 1)

    def test_square_eats_only_food_in_the_active_hotbar_slot(self):
        self.assertEqual(BUTTON_CONSUME, BUTTON_TOOL)
        self.assertEqual(BUTTON_CONSUME, pygame.CONTROLLER_BUTTON_X)

        state = GameState()
        state.stamina = 20
        inventory = TinyInventory({"apple": 1})
        inventory.slots = [
            SimpleNamespace(item=SimpleNamespace(name="apple")),
            SimpleNamespace(item=SimpleNamespace(name="")),
        ]
        player = Player.__new__(Player)
        player.game_state = state
        player.stamina_enabled = True
        player.inventory = inventory
        player.hotbar_slot_index = 0
        player.selected_consumable = None
        player.seed_inventory = {"apple": 7, "corn": 4}

        food_name = player.selected_hotbar_food()
        self.assertEqual(food_name, "apple")
        self.assertEqual(player.consume_food(food_name), 10)
        self.assertEqual(player.seed_inventory, {"apple": 7, "corn": 4})

        inventory.slots[0].item.name = "corn"
        self.assertIsNone(player.selected_hotbar_food())
        self.assertEqual(player.seed_inventory["corn"], 4)

    def test_square_does_not_treat_a_focused_seed_recipe_as_food(self):
        inventory = TinyInventory({"apple": 1})
        player = Player.__new__(Player)
        player.inventory = inventory
        inventory_slot = SimpleNamespace(
            rect=pygame.Rect(0, 0, 40, 40),
            item=SimpleNamespace(name="apple"),
        )
        seed_recipe_rect = pygame.Rect(60, 0, 40, 40)
        ui = Inventory_UI.__new__(Inventory_UI)
        ui.player = player
        ui.slot_ui = SimpleNamespace(slots=[inventory_slot])
        ui.get_controller_targets = lambda: [inventory_slot.rect, seed_recipe_rect]

        ui.controller_focus_index = 0
        self.assertEqual(ui.focused_inventory_food(), "apple")
        ui.controller_focus_index = 1
        self.assertIsNone(ui.focused_inventory_food())

    def test_every_authored_tree_fruit_can_be_selected_and_eaten(self):
        for item_id, display_name, expected_restore in TREE_FRUITS:
            with self.subTest(fruit=item_id):
                state = GameState()
                state.stamina = 0
                inventory = TinyInventory({item_id: 1})
                player = SimpleNamespace(
                    game_state=state,
                    stamina_enabled=True,
                    inventory=inventory,
                    selected_consumable=None,
                )

                self.assertTrue(Player.select_consumable(player, display_name))
                self.assertEqual(player.selected_consumable, item_id)
                self.assertEqual(Player.consume_food(player), expected_restore)
                self.assertEqual(inventory.count_item(item_id), 0)

    def test_hotbar_access_cycles_the_original_five_inventory_slots(self):
        player = Player.__new__(Player)
        selected = []
        player.inventory = SimpleNamespace(
            slots=[
                SimpleNamespace(item=SimpleNamespace(name="corn")),
                SimpleNamespace(item=SimpleNamespace(name="")),
                SimpleNamespace(item=SimpleNamespace(name="apple")),
                SimpleNamespace(item=SimpleNamespace(name="")),
                SimpleNamespace(item=SimpleNamespace(name="")),
            ]
        )
        player.hotbar_slot_index = 0
        player.select_hotbar_item = lambda item_name: selected.append(item_name) or True

        self.assertEqual(Player.cycle_hotbar_slot(player), 2)
        self.assertEqual(Player.cycle_hotbar_slot(player), 0)
        self.assertEqual(selected, ["apple", "corn"])

    def test_damage_number_rises_and_fades_out(self):
        effects = EffectsManager(library=SimpleNamespace(specs={}))
        number = effects.floating_text("-5", (100, 100))

        effects.update(0.55)
        self.assertLess(number.rect.centery, 100)
        self.assertLess(number.image.get_alpha(), 255)
        effects.update(0.5)
        self.assertNotIn(number, effects.active)

    def test_tracked_quest_panel_starts_below_xp_and_trust_bars(self):
        trust_panel_bottom = 166 + 40
        self.assertGreaterEqual(TRACKED_QUEST_TOP, trust_panel_bottom + 8)

    def test_minimap_only_reports_nearby_enemies_and_needed_villagers(self):
        state = GameState()
        state.set_location("player_farm")
        quest_system = QuestSystem(state)
        hud = GameplayHUD.__new__(GameplayHUD)
        hud.player = SimpleNamespace(center=(0, 0), game_state=state)
        hud.quest_journal = SimpleNamespace(quest_system=quest_system)

        wife = SimpleNamespace(
            story_id="wife",
            center=(80, 80),
            location_id="player_farm",
            is_alive=True,
            is_enemy=False,
        )
        near_enemy = SimpleNamespace(
            story_id=None,
            center=(NEARBY_ENEMY_RADIUS - 1, 0),
            location_id="player_farm",
            is_alive=True,
            is_enemy=True,
        )
        far_enemy = SimpleNamespace(
            story_id=None,
            center=(NEARBY_ENEMY_RADIUS + 1, 0),
            location_id="player_farm",
            is_alive=True,
            is_enemy=True,
        )
        manager = SimpleNamespace(npcs=[wife, near_enemy, far_enemy])

        self.assertEqual(hud._enemy_positions(manager), [near_enemy.center])
        self.assertIn(wife.center, hud._needed_villager_positions(manager))
        quest_system.close()

    def test_minimap_routes_an_off_map_quest_villager_to_the_travel_marker(self):
        state = GameState()
        state.set_location("player_farm")
        state.set_flag("player_farm.exterior_spawn", (400, 500))
        quest_system = QuestSystem(state)
        hud = GameplayHUD.__new__(GameplayHUD)
        hud.player = SimpleNamespace(center=(400, 500), game_state=state)
        hud.quest_journal = SimpleNamespace(quest_system=quest_system)
        manager = SimpleNamespace(npcs=[])

        self.assertIn((400, 500), hud._needed_villager_positions(manager))
        self.assertEqual(
            hud._dialogue_target_ids(("alchemist.cure.delivery", "hunter.cure.delivery")),
            {"alchemist", "hunter"},
        )
        quest_system.close()

    def test_story_kingdom_uses_a_25_by_25_chunk_footprint(self):
        kingdom = WorldRun(seed=88, world_kind="kingdom").get_island()

        self.assertEqual(KINGDOM_SIZE_CHUNKS, 25)
        self.assertEqual(kingdom.size_chunks, 25)
        self.assertTrue(
            all(abs(x) <= 11 and abs(y) <= 11 for x, y in KINGDOM_LOCATION_CHUNK_OFFSETS.values())
        )

    def test_offscreen_story_npc_marker_shows_direction_and_tile_distance(self):
        hud = GameplayHUD.__new__(GameplayHUD)
        hud.screen = pygame.Surface((800, 600), pygame.SRCALPHA)
        hud.screen_w, hud.screen_h = hud.screen.get_size()
        hud.small_font = pygame.font.Font(None, 16)
        hud.player = SimpleNamespace(center=(0, 0), game_state=GameState())
        hud.quest_journal = None
        world = SimpleNamespace(tile_size=16)
        jim = SimpleNamespace(
            story_id="jim",
            center=(1600, 0),
            location_id="jim_home",
            is_alive=True,
        )

        markers = hud.draw_important_npc_markers(world, SimpleNamespace(npcs=[jim]))

        self.assertEqual(markers[0][:2], ("jim", 100))
        self.assertGreater(markers[0][2][0], hud.screen_w // 2)

    def test_streamed_kingdom_chunks_receive_deterministic_ambient_npcs(self):
        chunks = {
            (x, y): SimpleNamespace(
                chunk_size=(8, 8),
                get_world_tile=lambda local_x, local_y, x=x, y=y: (
                    x * 8 + local_x,
                    y * 8 + local_y,
                ),
            )
            for y in range(4)
            for x in range(4)
        }
        manager = NPCManager.__new__(NPCManager)
        manager.world = SimpleNamespace(
            island=SimpleNamespace(world_kind="kingdom"),
            seed=17,
            spawn_chunk=(0, 0),
            current_player_chunk=(0, 0),
            loaded_chunks=chunks,
        )
        manager.assets = SimpleNamespace(get_npc_ids=lambda: ["villager"])
        manager.pathfinder = SimpleNamespace(
            is_walkable=lambda _tile: True,
            tile_to_world_center=lambda tile: (tile[0] * 16 + 8, tile[1] * 16 + 16),
        )
        manager.npcs = []
        manager._scattered_chunk_coords = set()
        manager._scattered_npc_count = 0

        with patch(
            "entities.npc.WanderingNPC",
            side_effect=lambda *args, **kwargs: SimpleNamespace(),
        ):
            spawned = manager.spawn_scattered_npcs(max_chunks=None)

        self.assertGreater(spawned, 0)
        self.assertEqual(manager._scattered_chunk_coords, set(chunks))
        self.assertTrue(all(npc.ambient_world_npc for npc in manager.npcs))


if __name__ == "__main__":
    unittest.main()
