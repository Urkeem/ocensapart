import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock


os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

import pygame

from entities.player import Player
from gameplay.events import EventDispatcher, PlayerCollapsed, PlayerSlept
from gameplay.combat import CombatSystem
from gameplay.game_state import GameState
from gameplay.locations import LocationInstance, LocationManager, ensure_player_farm
from gameplay.recovery import RECOVERY_FADE_SECONDS, RecoverySystem, recovery_fee
from gameplay.stamina import MAX_AWAKE_GAME_MINUTES, StaminaSystem
from world.chunkmanager import Chunk
from world.weather import GameTime


class StubInventory:
    def __init__(self, items=None):
        self.items = dict(items or {})
        self.is_inv = False

    def count_item(self, name):
        return self.items.get(name, 0)

    def remove_item_count(self, name, amount=1):
        if self.count_item(name) < amount:
            return False
        self.items[name] -= amount
        return True


class StubPlayer:
    def __init__(self, position=(1000, 1000), coins=40):
        self.pos = pygame.Vector2(position)
        self.rect = pygame.Rect(0, 0, 32, 48)
        self.rect.midbottom = position
        self.collision_box = pygame.Rect(0, 0, 14, 12)
        self.feet_collision_box = pygame.Rect(0, 0, 14, 8)
        self.sync_collision_boxes()
        self.image = pygame.Surface((32, 48), pygame.SRCALPHA)
        self.inventory = StubInventory()
        self.direction = pygame.Vector2()
        self.health = 0
        self.max_health = 8
        self.coins = coins
        self.recovery_active = False
        self.location_tools_enabled = True
        self.stamina_enabled = True
        self.is_sprinting = False

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def center(self):
        return self.rect.center

    def sync_collision_boxes(self):
        self.collision_box.midbottom = self.rect.midbottom
        self.feet_collision_box.midbottom = self.rect.midbottom

    def spend_coins(self, amount):
        if amount > self.coins:
            return False
        self.coins -= amount
        return True

    def revive(self):
        self.health = self.max_health
        return True


class PhaseThreeHomeRecoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((960, 540))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_location_manager(self, state=None, player=None):
        state = state or GameState(current_location_id="player_house_interior")
        state.set_flag("player_farm.exterior_spawn", (800, 900))
        player = player or StubPlayer()
        wife = StubPlayer((0, 0))
        wife.story_id = "wife"
        wife.location_id = "player_house_interior"
        world = SimpleNamespace(
            get_spawn_position=lambda: (500, 500),
            world_to_chunk=lambda point: (int(point[0] // 64), int(point[1] // 64)),
            current_player_chunk=(0, 0),
        )
        manager = LocationManager(
            self.screen,
            world,
            None,
            player,
            state,
            SimpleNamespace(npcs=[wife]),
        )
        return manager, state, player, wife

    def test_interior_composes_layers_furniture_and_collision(self):
        interior = LocationInstance(self.screen)
        self.assertEqual(interior.location_id, "player_house_interior")
        self.assertGreaterEqual(len(interior.furniture), 5)
        self.assertGreater(len(interior.collisions), 0)
        self.assertTrue(interior.contains(interior.point("bedside_spawn")))
        for anchor in ("bedside_spawn", "entry_spawn", "recovery_spawn"):
            feet = pygame.Rect(0, 0, 14, 8)
            feet.midbottom = interior.point(anchor)
            self.assertFalse(any(feet.colliderect(obj.collision_box) for obj in interior.collisions))

    def test_door_round_trip_uses_exact_exterior_return_point(self):
        manager, state, player, wife = self.make_location_manager()
        self.assertTrue(manager.is_interior)
        self.assertTrue(manager.interior.contains(player.pos))
        self.assertEqual(wife.location_id, "player_house_interior")

        manager.exit_interior()
        self.assertEqual(state.current_location_id, "player_farm")
        self.assertEqual(tuple(player.pos), (800, 900))
        player.pos.update(812, 914)
        player.rect.midbottom = player.pos
        player.sync_collision_boxes()
        manager.enter_interior()
        self.assertEqual(state.location_return_points["player_house_interior"], (812.0, 914.0))
        manager.exit_interior()
        self.assertEqual(tuple(player.pos), (812, 914))

    def test_fresh_story_start_uses_bedside_even_when_world_position_overlaps_room(self):
        state = GameState(current_location_id="player_house_interior")
        player = StubPlayer((480, 270))

        manager, _, _, _ = self.make_location_manager(state, player)

        self.assertEqual(tuple(player.pos), manager.interior.point("bedside_spawn"))
        self.assertTrue(state.flag("player_house.initialized"))

    def test_inside_and_outside_location_state_round_trip_safely(self):
        manager, state, player, _wife = self.make_location_manager()
        inside_position = tuple(player.pos)
        restored_inside = GameState.from_dict(state.to_dict())
        inside_player = StubPlayer(inside_position)
        inside_manager, _, _, _ = self.make_location_manager(restored_inside, inside_player)
        self.assertTrue(inside_manager.is_interior)
        self.assertEqual(tuple(inside_player.pos), inside_position)

        manager.exit_interior()
        outside_position = tuple(player.pos)
        restored_outside = GameState.from_dict(state.to_dict())
        outside_player = StubPlayer(outside_position)
        outside_manager, _, _, _ = self.make_location_manager(restored_outside, outside_player)
        self.assertFalse(outside_manager.is_interior)
        self.assertEqual(tuple(outside_player.pos), outside_position)

    def test_interior_combat_only_sees_actors_in_the_same_location(self):
        player = StubPlayer()
        player.game_state = GameState(current_location_id="player_house_interior")
        wife = SimpleNamespace(is_alive=True, location_id="player_house_interior")
        outdoor_guard = SimpleNamespace(is_alive=True, location_id="player_farm")
        combat = CombatSystem(
            player,
            SimpleNamespace(),
            SimpleNamespace(npcs=[wife, outdoor_guard]),
        )

        self.assertEqual(combat._living_npcs(), (wife,))

    def test_guaranteed_farm_splits_valid_soil_into_corn_and_tomato(self):
        chunk = Chunk((0, 0), (12, 12), 16)
        chunk.props.append({
            "type": "house",
            "id": "player-farmhouse",
            "scene": "farmstead",
            "role": "farmhouse",
            "door_tile": (3, 3),
        })
        for x in range(4, 8):
            for y in range(5, 7):
                chunk.layers["soil"][chunk.get_index(x, y)] = 1

        class World:
            spawn_chunk = (0, 0)
            farmstead_chunks = ((0, 0),)
            tile_size = 16
            loaded_chunks = {(0, 0): chunk}

            @staticmethod
            def invalidate_soil_chunk_and_neighbors(_coord):
                return None

        class Soil:
            @staticmethod
            def get_chunk_and_local(tile):
                return chunk, tile

        state = GameState()
        state.set_flag("game.mode", "story")
        ensure_player_farm(World(), Soil(), state)
        plots = state.flag("player_farm.plots")

        self.assertEqual(set(plots), {"corn", "tomato"})
        self.assertEqual(sum(map(len, plots.values())), 8)
        plants = [chunk.layers["plant"][chunk.get_index(*tile)] for tiles in plots.values() for tile in tiles]
        self.assertEqual({plant["type"] for plant in plants}, {"corn", "tomato"})
        self.assertGreaterEqual(sum(plant["age"] >= 1 for plant in plants), 2)
        self.assertGreaterEqual(sum(plant["age"] < 1 for plant in plants), 3)

    def test_passive_stamina_reaches_zero_at_two_days_and_food_does_not_reset_awake_time(self):
        state = GameState()
        player = StubPlayer()
        stamina = StaminaSystem(state, player)
        game_time = GameTime()
        stamina.update(game_time.real_seconds_per_game_day, game_time)
        self.assertAlmostEqual(state.stamina, 50.0)
        self.assertAlmostEqual(state.awake_game_minutes, 1440.0)

        player.game_state = state
        player.inventory = StubInventory({"apple": 1})
        before_awake = state.awake_game_minutes
        self.assertEqual(Player.consume_food(player, "apple"), 10)
        self.assertEqual(state.awake_game_minutes, before_awake)
        self.assertEqual(player.inventory.count_item("apple"), 0)

        stamina.update(game_time.real_seconds_per_game_day, game_time)
        self.assertTrue(stamina.awake_limit_reached)
        self.assertEqual(state.awake_game_minutes, MAX_AWAKE_GAME_MINUTES)

    def test_sleep_and_defeat_share_home_recovery_with_distinct_fees(self):
        manager, state, player, _wife = self.make_location_manager()
        game_time = GameTime()
        weather = SimpleNamespace(time=game_time, seasons=SimpleNamespace(update=Mock()))
        soil = SimpleNamespace(_last_update_bucket=3, update=Mock())
        dispatcher = EventDispatcher()
        events = []
        dispatcher.subscribe(PlayerSlept, events.append)
        dispatcher.subscribe(PlayerCollapsed, events.append)
        recovery = RecoverySystem(self.screen, player, state, weather, soil, manager, dispatcher)

        state.stamina = 15
        state.awake_game_minutes = 900
        self.assertTrue(recovery.sleep())
        recovery.update(RECOVERY_FADE_SECONDS)
        self.assertEqual(game_time.day, 2)
        self.assertEqual(game_time.time, 360)
        self.assertEqual(state.stamina, state.max_stamina)
        self.assertEqual(state.awake_game_minutes, 0)
        self.assertEqual(player.coins, 40)
        self.assertIsInstance(events[-1], PlayerSlept)
        soil.update.assert_called_once_with(0, game_time)
        recovery.update(RECOVERY_FADE_SECONDS)

        player.health = 0
        player.coins = 40
        self.assertTrue(recovery.request("defeat"))
        recovery.update(RECOVERY_FADE_SECONDS)
        self.assertEqual(player.coins, 35)
        self.assertEqual(recovery.last_fee, 5)
        self.assertEqual(state.current_location_id, "player_house_interior")
        self.assertEqual(tuple(player.pos), manager.interior.point("recovery_spawn"))
        self.assertIsInstance(events[-1], PlayerCollapsed)
        self.assertEqual(events[-1].reason, "defeat")

    def test_awake_limit_automatically_starts_pass_out(self):
        manager, state, player, _wife = self.make_location_manager()
        player.health = player.max_health
        state.stamina = state.max_stamina
        state.awake_game_minutes = MAX_AWAKE_GAME_MINUTES
        weather = SimpleNamespace(time=GameTime(), seasons=SimpleNamespace(update=Mock()))
        soil = SimpleNamespace(_last_update_bucket=None, update=Mock())
        recovery = RecoverySystem(self.screen, player, state, weather, soil, manager)

        recovery.update(0)

        self.assertTrue(recovery.active)
        self.assertEqual(recovery.reason, "awake_limit")
        self.assertTrue(player.recovery_active)

    def test_recovery_fee_is_scaled_capped_and_never_negative(self):
        self.assertEqual(recovery_fee(0), 0)
        self.assertEqual(recovery_fee(2), 2)
        self.assertEqual(recovery_fee(40), 5)
        self.assertEqual(recovery_fee(500), 50)
        self.assertEqual(recovery_fee(5000), 100)


if __name__ == "__main__":
    unittest.main()
