"""Versioned voyage save serialization tests."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from gameplay.savegame import SAVE_VERSION, SaveGameManager, deserialize_chunk_states
from inventory_item import Item
from world.chunkmanager import Chunk
from world.worldmanager import World


class SaveGameTests(unittest.TestCase):
    def make_player(self):
        item = Item("wood")
        slot = SimpleNamespace(item=item, amount=17)
        inventory = SimpleNamespace(slots=[slot], selected_item_name=None)
        return SimpleNamespace(
            pos=SimpleNamespace(x=80, y=120),
            customization={"skin": "1.png"},
            health=4,
            max_health=5,
            coins=17,
            inventory=inventory,
            tool_durability={"axe": 33},
            broken_tools=set(),
            selected_tool="axe",
            water_amount=6,
            seed_inventory={"corn": 3},
            harvested_crops={"corn": 2},
            selected_seed="corn",
            world_hint_seen={"collect_loose_item"},
        )

    def make_weather(self):
        game_time = SimpleNamespace(time=755.0, day=3)
        seasons = SimpleNamespace(
            current_season_index=1,
            season_start_day=1,
            season_length=4,
            weather="Sunny",
            weather_duration=3,
            next_weather_hour=15,
        )
        return SimpleNamespace(time=game_time, seasons=seasons)

    def test_atomic_save_round_trips_chunk_mutations(self):
        chunk = Chunk((2, -1), (8, 8), 16)
        chunk.save_data["modified_tiles"][("soil", 3, 4)] = 1
        chunk.save_data["removed_props"].add("tree:gone")
        chunk.save_data["placed_props"].append({"id": "player:crate", "type": "environment"})
        chunk.save_data["flags"]["placed_prop_counter"] = 1
        chunk.props.append({"id": "tree:hurt", "type": "tree", "health": 2})
        world = SimpleNamespace(loaded_chunks={(2, -1): chunk})
        world_run = SimpleNamespace(seed=99, current_index=2, discovered_islands={1, 2})

        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "slot.json"
            manager = SaveGameManager(path)
            manager.save(world_run, world, self.make_player(), self.make_weather(), None)
            payload = manager.load()

            self.assertEqual(payload["version"], SAVE_VERSION)
            self.assertTrue(manager.exists)
            self.assertFalse(path.with_suffix(".json.tmp").exists())
            restored = deserialize_chunk_states(payload["world"]["chunks"])
            state = restored[(2, -1)]
            self.assertEqual(state["modified_tiles"][("soil", 3, 4)], 1)
            self.assertIn("tree:gone", state["removed_props"])
            self.assertEqual(state["prop_states"]["tree:hurt"]["health"], 2)

    def test_rejects_unknown_save_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "slot.json"
            path.write_text('{"version": 999}', encoding="utf-8")
            with self.assertRaises(ValueError):
                SaveGameManager(path).load()

    def test_json_coordinate_lists_restore_as_hashable_tuples(self):
        states = deserialize_chunk_states({
            "0,0": {
                "placed_props": [{
                    "id": "ecology:tree",
                    "type": "tree",
                    "world_tile": [4, 5],
                    "local_tile": [1, 2],
                    "world_pos": [72, 88],
                }]
            }
        })
        record = states[(0, 0)]["placed_props"][0]
        self.assertEqual(record["world_tile"], (4, 5))
        self.assertIsInstance(record["local_tile"], tuple)
        self.assertIsInstance(record["world_pos"], tuple)
        hash(record["world_tile"])

    def test_world_reapplies_removed_placed_and_damaged_props(self):
        chunk = Chunk((0, 0), (4, 4), 16)
        chunk.props = [
            {"id": "tree:gone", "type": "tree", "health": 5},
            {"id": "tree:hurt", "type": "tree", "health": 5},
        ]
        chunk.save_data["removed_props"] = {"tree:gone"}
        chunk.save_data["placed_props"] = [{"id": "player:crate", "type": "environment"}]
        chunk.save_data["prop_states"] = {"tree:hurt": {"health": 2}}

        World.apply_chunk_save_data(SimpleNamespace(), chunk)

        by_id = {prop["id"]: prop for prop in chunk.props}
        self.assertNotIn("tree:gone", by_id)
        self.assertIn("player:crate", by_id)
        self.assertEqual(by_id["tree:hurt"]["health"], 2)


if __name__ == "__main__":
    unittest.main()
