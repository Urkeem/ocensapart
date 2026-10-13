import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "code"))

import pygame

from data.locations import LOCATION_DEFINITIONS
from entities.house import get_house_asset_scale, get_house_render_size
from entities.player import Player
from entities.vessel import PlayerBoat, VesselAnimator
from gameplay.events import EventDispatcher
from gameplay.game_state import GameState
from gameplay.locations import LocationManager
from gameplay.progression import ProgressionService
from gameplay.survivors import (
    ABOARD_PIRATE_SHIP,
    AT_EXTRACTION,
    CAPTIVE,
    FOLLOWING_HUNTER,
    HUNTER_RESCUE_GROUP,
    SETTLED_AT_FARM,
    TRAVELLING,
    SurvivorTransportService,
)


class StubInventory:
    def __init__(self):
        self.counts = {}

    def count_item(self, item_id):
        return self.counts.get(item_id, 0)


class StubPlayer:
    def __init__(self, pos=(480, 270)):
        self.pos = pygame.Vector2(pos)
        self.rect = pygame.Rect(0, 0, 36, 54)
        self.rect.midbottom = pos
        self.feet_collision_box = pygame.Rect(0, 0, 18, 10)
        self.feet_collision_box.midbottom = pos
        self.collision_box = pygame.Rect(0, 0, 18, 18)
        self.collision_box.midbottom = pos
        self.direction = pygame.Vector2()
        self.inventory = StubInventory()
        self.location_tools_enabled = True
        self.mounted_vessel = None
        self.hidden_by_vessel = False
        self.facing = "down"

    @property
    def center(self):
        return self.rect.center

    def sync_collision_boxes(self):
        self.feet_collision_box.midbottom = self.rect.midbottom
        self.collision_box.midbottom = self.rect.midbottom


class StubLocationWorld:
    tile_size = 64
    current_player_chunk = (0, 0)

    @staticmethod
    def get_spawn_position():
        return 500, 500

    @staticmethod
    def world_to_chunk(point):
        return int(point[0] // 64), int(point[1] // 64)


class TestWaterWorld:
    tile_size = 32

    @staticmethod
    def get_water_locality(tile):
        return "ocean" if tile[1] <= 2 else None

    @staticmethod
    def get_world_terrain_tile(tile_x, tile_y):
        return -1 if tile_y <= 2 else 1


class FakeShip:
    def __init__(self, unlocked=False):
        self.unlocked = unlocked
        self.docked_at = None
        self.destination = None

    def dock(self, location_id, position=None):
        self.docked_at = location_id
        self.destination = None

    def begin_travel(self, destination, direction="right"):
        if not self.unlocked:
            return False, "Ship locked"
        self.docked_at = None
        self.destination = destination
        return True, ""


class FakeVesselManager:
    def __init__(self, unlocked=False):
        self.pirate_ship = FakeShip(unlocked)


class FakeCommunity:
    def __init__(self):
        self.sync_count = 0

    def spawn_recruited_survivors(self):
        self.sync_count += 1
        return ()


class PhaseSevenLocationVesselTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((960, 540))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_location_manager(self, state=None, player=None, definitions=None):
        state = state or GameState(current_location_id="player_farm")
        player = player or StubPlayer()
        return LocationManager(
            self.screen,
            StubLocationWorld(),
            None,
            player,
            state,
            definitions=definitions,
        ), state, player

    def test_underlevel_reason_and_eligible_dungeon_entry(self):
        manager, state, player = self.make_location_manager()

        allowed, reason = manager.can_enter("hold_4")
        self.assertFalse(allowed)
        self.assertIn("level 8", reason)
        self.assertFalse(manager.enter_location("hold_4"))
        self.assertEqual(state.current_location_id, "player_farm")
        self.assertEqual(manager.last_denial_reason, reason)

        state.progression.level = 8
        state.set_flag("holds.hold_3_complete")
        player.inventory.counts["hollow_crypt_key"] = 1
        self.assertEqual(manager.can_enter("hold_4"), (True, ""))
        self.assertTrue(manager.enter_location("hold_4"))
        self.assertTrue(manager.is_interior)
        self.assertEqual(state.current_location_id, "hold_4")

    def test_all_declarative_access_forms_are_supported(self):
        definitions = dict(LOCATION_DEFINITIONS)
        definitions["test_gate"] = {
            "id": "test_gate",
            "runtime": "world",
            "requirements": {
                "all": (
                    {"min_level": 2},
                    {"quest_completed": "completed_quest"},
                    {"quest_active": "active_quest"},
                    {"story_flag": "route.open"},
                    {"possess_item": "ironveil_key"},
                    {"trust_tier": {"npc_id": "hunter", "tier": "trusted"}},
                    {"kingdom_reputation": 5},
                    {"transport_unlock": "pirate_ship"},
                )
            },
        }
        manager, state, player = self.make_location_manager(definitions=definitions)
        state.progression.level = 2
        state.quests["completed_quest"] = {"status": "completed"}
        state.quests["active_quest"] = {"status": "active"}
        state.set_flag("route.open")
        player.inventory.counts["ironveil_key"] = 1
        state.add_trust("hunter", 50)
        state.progression.kingdom_reputation = 5
        state.transports["pirate_ship"] = {"unlocked": True}

        self.assertEqual(manager.can_enter("test_gate"), (True, ""))
        state.transports["pirate_ship"]["unlocked"] = False
        allowed, reason = manager.can_enter("test_gate")
        self.assertFalse(allowed)
        self.assertIn("Unlock pirate ship", reason)

    def test_world_edges_and_castle_door_share_access_checks(self):
        manager, state, player = self.make_location_manager()
        state.set_flag("player_farm.exterior_spawn", tuple(player.pos))
        notices = []
        manager.message_callback = notices.append

        targets = {target.target_id: target for target in manager.interaction_targets(player, 999)}
        self.assertTrue(targets["farm-road-village"].action())
        self.assertEqual(state.current_location_id, "village")

        targets = {target.target_id: target for target in manager.interaction_targets(player, 999)}
        self.assertFalse(targets["village-road-castle"].action())
        self.assertIn("defend the farm", notices[-1])
        state.quests["prologue.first_defense"] = {"status": "completed"}
        state.progression.kingdom_reputation = 5
        self.assertTrue(targets["village-road-castle"].action())
        self.assertEqual(state.current_location_id, "castle_exterior")
        castle = manager.exterior_objects()[0]
        self.assertEqual(castle.location_id, "castle_exterior")
        self.assertGreater(castle.image.get_width(), 300)

        targets = {target.target_id: target for target in manager.interaction_targets(player, 999)}
        self.assertFalse(targets["castle-main-door"].action())
        self.assertIn("level 2", notices[-1])
        state.progression.level = 2
        self.assertTrue(targets["castle-main-door"].action())
        self.assertEqual(state.current_location_id, "castle_interior")

    def test_story_residences_use_authored_house_scales_and_front_door_npc_anchors(self):
        manager, _, _ = self.make_location_manager()
        residences = {
            obj.location_id: obj
            for obj in manager.exterior_objects()
            if obj.object_id.startswith("location-scenery:")
        }

        self.assertTrue(
            LOCATION_DEFINITIONS["lillian_home"]["asset"].endswith(
                "tertiary/bakerystewhouse.png"
            )
        )
        for location_id in (
            "jim_home",
            "lillian_home",
            "alchemist_home",
            "hunter_lodge",
            "navigator_home",
            "pirate_home",
        ):
            with self.subTest(location=location_id):
                asset_path = LOCATION_DEFINITIONS[location_id]["asset"]
                asset_name = manager._house_asset_name(asset_path)
                authored_scale = LOCATION_DEFINITIONS[location_id].get(
                    "scale", get_house_asset_scale(asset_name)
                )
                expected_size = get_house_render_size(
                    asset_name,
                    authored_scale,
                )
                house = residences[location_id]
                npc_position = manager._exterior_npc_position(location_id)

                self.assertEqual(house.image.get_size(), expected_size)
                self.assertGreater(npc_position.y, house.rect.bottom)
                self.assertGreaterEqual(npc_position.x, house.rect.left)
                self.assertLessEqual(npc_position.x, house.rect.right)

        alchemist_asset = manager._house_asset_name(
            LOCATION_DEFINITIONS["alchemist_home"]["asset"]
        )
        self.assertEqual(LOCATION_DEFINITIONS["alchemist_home"]["scale"], 2.0)
        self.assertEqual(
            residences["alchemist_home"].image.get_size(),
            get_house_render_size(alchemist_asset, 2.0),
        )
        yard_objects = [
            obj
            for obj in manager.exterior_objects()
            if obj.object_id.startswith("location-yard:")
        ]
        self.assertGreaterEqual(len(yard_objects), 30)

        lillian = SimpleNamespace(
            story_id="lillian",
            location_id="lillian_home",
            pos=pygame.Vector2(),
            rect=pygame.Rect(0, 0, 32, 48),
            collision_box=pygame.Rect(0, 0, 18, 12),
        )
        manager.npc_manager = SimpleNamespace(npcs=[lillian])
        manager._sync_location_npcs()
        self.assertEqual(
            tuple(lillian.pos),
            tuple(manager._exterior_npc_position("lillian_home")),
        )
        self.assertGreater(lillian.rect.bottom, residences["lillian_home"].rect.bottom)

    def test_boat_uses_all_directions_water_lock_and_shore_dismount(self):
        state = GameState()
        state.transports["player_boat"] = {"unlocked": True}
        state.progression.fishing_points = 150
        player = StubPlayer((80, 80))
        world = TestWaterWorld()
        boat = PlayerBoat((80, 80), state)
        self.assertEqual(boat.mount(player, world), (True, ""))
        self.assertIs(player.mounted_vessel, boat)
        self.assertTrue(player.hidden_by_vessel)
        self.assertTrue(boat.allows_sea_fishing())

        for direction, facing in (
            ((1, 0), "right"),
            ((-1, 0), "left"),
            ((0, -1), "up"),
            ((0, 1), "down"),
        ):
            boat.pos.update(80, 80)
            boat.update_controlled(0.02, direction, world)
            self.assertEqual(boat.animator.direction, facing)
            self.assertNotEqual(tuple(boat.pos), (80.0, 80.0))
            self.assertEqual(tuple(player.pos), tuple(boat.pos))

        boat.pos.update(80, 92)
        old_position = tuple(boat.pos)
        boat.update_controlled(0.5, (0, 1), world)
        self.assertEqual(tuple(boat.pos), old_position)
        boat.pos.update(80, 80)
        boat._attach_player()
        self.assertEqual(boat.dismount(world), (True, ""))
        self.assertIsNone(player.mounted_vessel)
        self.assertFalse(player.hidden_by_vessel)
        self.assertGreater(player.pos.y, boat.pos.y)

    def test_pirate_ship_wind_and_base_layers_share_one_frame(self):
        animator = VesselAnimator("pirate_ship", display_scale=0.1)
        for direction in ("down", "up", "left", "right"):
            animator.set_motion(direction, True)
            animator.update(0.125)
            animation_id, flipped = animator._resolve()
            layers = animator.current_layers()
            self.assertEqual(len(layers), 2)
            self.assertEqual(
                animator.synchronized_frame_number,
                int(animator.frame_index) % len(animator._load_frames(animation_id)),
            )
            self.assertEqual(flipped, direction == "left")

    def test_sea_fishing_requires_the_unlocked_mounted_boat(self):
        state = GameState()
        state.progression.fishing_points = 150
        world = SimpleNamespace(tile_size=64, get_water_locality=lambda _tile: "ocean")
        player = Player.__new__(Player)
        player.soil_layer = SimpleNamespace(world=world)
        player.game_state = state
        player.get_facing_world_tile = lambda distance=1: (distance, 0)
        player.can_fish_at_tile = lambda _tile: True
        player.fishing_rng = __import__("random").Random(7)
        player.current_season = "summer"
        player.action_kind = None
        player.mounted_vessel = None

        self.assertFalse(player.start_fishing())
        self.assertIn("boat", player.fishing_message)
        player.mounted_vessel = SimpleNamespace(allows_sea_fishing=lambda: True)
        self.assertTrue(player.start_fishing())
        self.assertTrue(player.fishing_active)

    def test_survivor_group_persists_hunter_pirate_farm_sequence_once(self):
        state = GameState()
        state.transports["pirate_ship"] = {"unlocked": True}
        dispatcher = EventDispatcher()
        progression = ProgressionService(state, dispatcher)
        vessels = FakeVesselManager(unlocked=True)
        community = FakeCommunity()
        service = SurvivorTransportService(state, vessels, dispatcher, community)
        group_id = HUNTER_RESCUE_GROUP["id"]
        self.assertEqual(service.record()["stage"], CAPTIVE)

        self.assertEqual(service.free(), (True, ""))
        self.assertEqual(service.record()["stage"], FOLLOWING_HUNTER)
        self.assertEqual(service.reach_extraction(), (True, ""))
        self.assertEqual(service.record()["stage"], AT_EXTRACTION)
        self.assertEqual(service.call_pirate_to_extraction(), (True, ""))
        self.assertEqual(service.handoff_to_pirate(), (True, ""))
        self.assertEqual(service.record()["stage"], ABOARD_PIRATE_SHIP)
        self.assertEqual(service.begin_travel(), (True, ""))
        self.assertEqual(service.record()["stage"], TRAVELLING)

        reloaded = GameState.from_dict(state.to_dict())
        reloaded_dispatcher = EventDispatcher()
        reloaded_progression = ProgressionService(reloaded, reloaded_dispatcher)
        reloaded_vessels = FakeVesselManager(unlocked=True)
        reloaded_community = FakeCommunity()
        restored = SurvivorTransportService(
            reloaded,
            reloaded_vessels,
            reloaded_dispatcher,
            reloaded_community,
        )
        self.assertEqual(restored.complete_travel(), (True, ""))
        record = restored.record(group_id)
        self.assertEqual(record["stage"], SETTLED_AT_FARM)
        self.assertEqual(
            record["history"],
            [CAPTIVE, FOLLOWING_HUNTER, AT_EXTRACTION, ABOARD_PIRATE_SHIP, TRAVELLING, SETTLED_AT_FARM],
        )
        for survivor_id in record["survivor_ids"]:
            npc_state = reloaded.story_npcs[survivor_id]
            self.assertTrue(npc_state["community_member"])
            self.assertEqual(npc_state["location_id"], "player_farm")
        reputation = reloaded.progression.kingdom_reputation
        self.assertEqual(reputation, len(record["survivor_ids"]) * 2)

        saved_again = GameState.from_dict(reloaded.to_dict())
        final_dispatcher = EventDispatcher()
        final_progression = ProgressionService(saved_again, final_dispatcher)
        final_service = SurvivorTransportService(
            saved_again,
            FakeVesselManager(unlocked=True),
            final_dispatcher,
            FakeCommunity(),
        )
        self.assertEqual(final_service.complete_travel(), (True, ""))
        self.assertEqual(saved_again.progression.kingdom_reputation, reputation)
        progression.close()
        reloaded_progression.close()
        final_progression.close()


if __name__ == "__main__":
    unittest.main()
