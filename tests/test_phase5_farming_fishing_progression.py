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

from data.content_manifest import CROP_ASSETS
from data.crafting import recipes_for_category
from data.crops import CROP_DEFINITIONS, STARTER_CROP_IDS, is_crop_unlocked
from entities.player import Player
from entities.scheduled_npc import MerchantNPC
from gameplay.events import (
    CropHarvested,
    EventDispatcher,
    FishCaught,
    ProgressionUpdated,
)
from gameplay.crafting import CraftingService
from gameplay.fishing import (
    FISH_BY_ID,
    LOCALITY_UNLOCK_POINTS,
    fishing_block_reason,
    get_fish_pool,
    is_locality_unlocked,
)
from gameplay.game_state import GameState
from gameplay.progression import ProgressionService
from ui.hud import GameplayHUD
from ui.dialogue import MerchantDialogue
from world.chunkmanager import Chunk
from world.soil import SoilLayer


class StubWorld:
    def __init__(self):
        self.tile_size = 64
        self.chunk_size = (3, 3)
        self.chunk = Chunk((0, 0), self.chunk_size, self.tile_size)
        self.chunk.layers["terrain"] = [1] * 9
        self.chunk.layers["base"] = [1] * 9
        self.loaded_chunks = {(0, 0): self.chunk}

    def invalidate_soil_chunk_and_neighbors(self, _coord):
        pass


class PhaseFiveFarmingFishingProgressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_crop_catalog_covers_assets_with_only_two_starters(self):
        self.assertEqual(set(CROP_DEFINITIONS), set(CROP_ASSETS))
        self.assertEqual(set(STARTER_CROP_IDS), {"corn", "tomato"})
        self.assertEqual(CROP_DEFINITIONS["corn"].harvest_points, 2)
        self.assertEqual(CROP_DEFINITIONS["tomato"].harvest_points, 3)

    def test_seed_recipes_unlock_at_crop_thresholds(self):
        state = GameState()
        initial = {recipe.output_id for recipe in recipes_for_category("seeds", state)}
        self.assertEqual(initial, {"corn", "tomato"})

        state.add_farming_points(20)
        unlocked = {recipe.output_id for recipe in recipes_for_category("seeds", state)}
        self.assertIn("carrot", unlocked)
        self.assertNotIn("lettuce", unlocked)

    def test_seed_recipe_requires_harvested_crop_not_an_existing_seed(self):
        inventory = SimpleNamespace(
            count_item=lambda _item: 0,
            can_add_item=lambda *_args: True,
        )
        player = SimpleNamespace(
            seed_inventory={"corn": 3},
            game_state=GameState(),
        )

        result = CraftingService(
            inventory,
            player,
            player.game_state,
        ).craft("seeds", "corn")

        self.assertFalse(result.success)
        self.assertEqual(player.seed_inventory["corn"], 3)

    def test_locked_crop_cannot_be_planted_even_when_owned(self):
        world = StubWorld()
        soil = SoilLayer(world)
        state = GameState()
        tile = (1, 1)
        position = (tile[0] * 64 + 32, tile[1] * 64 + 32)
        world.chunk.layers["soil"][world.chunk.get_index(*tile)] = 1

        self.assertFalse(soil.plant_seed_at(position, "carrot", game_state=state))
        state.add_farming_points(20)
        self.assertTrue(soil.plant_seed_at(position, "carrot", game_state=state))

    def test_harvest_points_are_once_only_and_unlock_immediately(self):
        state = GameState()
        state.add_farming_points(18)
        dispatcher = EventDispatcher()
        progression = ProgressionService(state, dispatcher)
        updates = []
        dispatcher.subscribe(ProgressionUpdated, updates.append)
        event = CropHarvested(event_id="harvest:threshold", crop_id="corn")

        dispatcher.publish(event)
        dispatcher.publish(event)

        self.assertEqual(state.progression.farming_points, 20)
        self.assertTrue(is_crop_unlocked("carrot", state))
        self.assertIn("crop.carrot", state.progression.unlocks)
        self.assertEqual(len(updates), 1)
        self.assertIn("crop.carrot", updates[0].unlocked_ids)
        progression.close()

    def test_initial_fishing_pool_contains_only_starter_pond_fish(self):
        state = GameState()
        for season in ("spring", "summer", "fall", "winter"):
            pool = get_fish_pool("pond", season, state)
            self.assertEqual(len(pool), 3)
            self.assertTrue(all(fish.season == "allseason" for fish in pool))
        self.assertEqual(get_fish_pool("river", "summer", state), ())
        self.assertEqual(get_fish_pool("ocean", "summer", state), ())

    def test_river_and_sea_unlock_at_configured_milestones(self):
        state = GameState()
        state.add_fishing_points(49)
        self.assertFalse(is_locality_unlocked("river", state))
        self.assertIn("50", fishing_block_reason("river", state))

        state.add_fishing_points(1)
        self.assertTrue(is_locality_unlocked("river", state))
        self.assertTrue(get_fish_pool("river", "summer", state))
        self.assertFalse(is_locality_unlocked("ocean", state))

        state.add_fishing_points(100)
        self.assertTrue(is_locality_unlocked("ocean", state))
        self.assertTrue(get_fish_pool("ocean", "winter", state))
        self.assertEqual(LOCALITY_UNLOCK_POINTS["ocean"], 150)

    def test_player_cannot_cast_into_locked_river(self):
        state = GameState()
        world = SimpleNamespace(
            tile_size=64,
            get_water_locality=lambda _tile: "river",
        )
        player = Player.__new__(Player)
        player.soil_layer = SimpleNamespace(world=world)
        player.game_state = state
        player.get_facing_world_tile = lambda distance=1: (distance, 0)
        player.can_fish_at_tile = lambda _tile: True
        player.fishing_rng = __import__("random").Random(5)
        player.current_season = "summer"
        player.action_kind = None

        self.assertFalse(player.start_fishing())
        self.assertFalse(player.fishing_active)
        self.assertIn("50 fishing points", player.fishing_message)

    def test_seasonal_pool_never_contains_locked_species(self):
        state = GameState()
        state.add_fishing_points(37)
        for season in ("spring", "summer", "fall", "winter"):
            for fish in get_fish_pool("pond", season, state):
                self.assertLessEqual(
                    fish.unlock_at_fishing_points,
                    state.progression.fishing_points,
                )

    def test_fish_awards_configured_points_once_and_uses_stable_id(self):
        state = GameState()
        dispatcher = EventDispatcher()
        progression = ProgressionService(state, dispatcher)
        fish = get_fish_pool("pond", "summer", state)[0]
        event = FishCaught(
            event_id="fish:starter",
            fish_id=fish.id,
            locality=fish.locality,
            required_reels=fish.required_reels,
            point_reward=fish.point_reward,
        )

        dispatcher.publish(event)
        dispatcher.publish(event)

        self.assertIn(fish.id, FISH_BY_ID)
        self.assertEqual(state.progression.fishing_points, fish.point_reward)
        progression.close()

    def test_seed_market_stock_tracks_farming_unlocks(self):
        state = GameState()
        merchant = SimpleNamespace(
            game_state=state,
            stall=SimpleNamespace(stall_kind="produce"),
            offers=[],
        )

        initial = MerchantNPC.available_offers(merchant)
        initial_seeds = {offer["item"] for offer in initial if offer.get("seed")}
        self.assertEqual(initial_seeds, {"corn", "tomato"})

        state.add_farming_points(20)
        unlocked = MerchantNPC.available_offers(merchant)
        unlocked_seeds = {offer["item"] for offer in unlocked if offer.get("seed")}
        self.assertIn("carrot", unlocked_seeds)
        self.assertNotIn("lettuce", unlocked_seeds)

    def test_seed_market_purchase_goes_to_seed_inventory(self):
        screen = pygame.display.get_surface()
        inventory = SimpleNamespace(is_inv=False)
        player = SimpleNamespace(
            inventory=inventory,
            seed_inventory={"corn": 0},
            coins=10,
            dialogue_active=False,
        )
        player.spend_coins = lambda amount: setattr(player, "coins", player.coins - amount) or True
        offer = {"item": "corn", "price": 4, "stock": 2, "seed": True}
        merchant = SimpleNamespace(
            is_available=True,
            stall=SimpleNamespace(stall_kind="produce"),
            dialogue_name="Farmer",
            available_offers=lambda: [offer],
        )
        dialogue = MerchantDialogue(screen, player)

        self.assertTrue(dialogue.open(merchant))
        self.assertTrue(dialogue.purchase_selected())
        self.assertEqual(player.seed_inventory["corn"], 1)
        self.assertEqual(player.coins, 6)
        self.assertEqual(offer["stock"], 1)

    def test_hud_receives_point_notification_and_plays_reward_star(self):
        state = GameState()
        dispatcher = EventDispatcher()
        hud = GameplayHUD.__new__(GameplayHUD)
        hud.player = SimpleNamespace(game_state=state, center=(20, 30))
        hud.notification_text = ""
        hud.notification_until = 0
        hud.notification_queue = []
        hud._progression_unsubscribe = None
        effects = SimpleNamespace(calls=[])
        effects.spawn = lambda *args, **kwargs: effects.calls.append((args, kwargs))
        GameplayHUD.bind_progression_events(hud, dispatcher, effects)

        dispatcher.publish(
            ProgressionUpdated(
                event_id="progress:test",
                track="farming",
                amount=2,
                total=2,
                source_id="corn",
            )
        )

        self.assertIn("+2 Farming points", hud.notification_text)
        self.assertEqual(effects.calls[0][0][0], "points_reward")
        hud._progression_unsubscribe()


if __name__ == "__main__":
    unittest.main()
