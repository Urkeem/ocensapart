"""Coastal markets, GOAP planning, and explicit merchant purchases."""

import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from entities.market import STALL_ASSETS, ensure_chunk_market_stalls, market_asset_folder
from gameplay.goap import GOAPAction, GOAPPlanner
from ui.dialogue import MerchantDialogue
from world.chunkmanager import Chunk


class TinyInventory:
    def __init__(self, coins=20):
        self.items = {"coin": coins}
        self.is_inv = False

    def count_item(self, name):
        return self.items.get(name, 0)

    def add_item_to_slot(self, item, amount=1):
        self.items[item.name] = self.items.get(item.name, 0) + amount
        return True

    def remove_item_count(self, name, amount=1):
        if self.count_item(name) < amount:
            return False
        self.items[name] -= amount
        return True


class MarketNPCSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_coastal_dock_chunk(self):
        chunk = Chunk((0, 0), (24, 24), 64)
        count = 24 * 24
        chunk.layers["base"] = [1] * count
        chunk.layers["terrain"] = [1] * count
        chunk.layers["biome"] = [2] * count
        chunk.layers["dock"] = [0] * count
        chunk.layers["dock"][chunk.get_index(12, 22)] = {"segment": "shore"}
        chunk.metadata["dock_count"] = 1
        return chunk

    def test_market_assets_include_misspelled_authored_folder_and_shared_empty_stall(self):
        self.assertTrue(market_asset_folder().is_dir())
        self.assertEqual(STALL_ASSETS["produce"][0], STALL_ASSETS["grain"][0])

    def test_dock_chunk_generates_three_coastal_stalls(self):
        chunk = self.make_coastal_dock_chunk()
        records = chunk.generate_market_stalls(world_seed=42)
        self.assertEqual([record["stall_kind"] for record in records], ["produce", "grain", "fish_meat"])
        self.assertEqual(chunk.metadata["market_count"], 1)
        self.assertEqual(len(ensure_chunk_market_stalls(chunk)), 3)
        for record in records:
            tile_top = record["world_tile"][1] * chunk.tile_size
            self.assertGreater(record["merchant_world_pos"][1], tile_top + chunk.tile_size)
            self.assertLess(record["merchant_world_pos"][1], record["world_pos"][1])

    def test_goap_builds_a_daily_work_plan(self):
        actions = (
            GOAPAction("travel", effects={"at_market": True}),
            GOAPAction("open", {"at_market": True}, {"stall_open": True}),
            GOAPAction("sell", {"stall_open": True}, {"working": True}),
        )
        plan = GOAPPlanner().plan({}, {"working": True}, actions)
        self.assertEqual([action.name for action in plan], ["travel", "open", "sell"])

    def test_shop_purchase_spends_coins_and_reduces_stock(self):
        screen = pygame.Surface((800, 600))
        player = SimpleNamespace(
            inventory=TinyInventory(0),
            coins=20,
            dialogue_active=False,
            spend_coins=lambda amount: setattr(player, "coins", player.coins - amount) or True,
        )
        offer = {"item": "apple", "price": 4, "stock": 2}
        merchant = SimpleNamespace(
            is_available=True,
            offers=[offer],
            dialogue_name="Mara",
            stall=SimpleNamespace(stall_kind="produce"),
        )
        dialogue = MerchantDialogue(screen, player)
        self.assertTrue(dialogue.open(merchant))
        self.assertTrue(dialogue.purchase_selected())
        self.assertEqual(player.coins, 16)
        self.assertEqual(player.inventory.count_item("apple"), 1)
        self.assertEqual(offer["stock"], 1)


if __name__ == "__main__":
    unittest.main()
