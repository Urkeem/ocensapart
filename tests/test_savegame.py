"""Versioned voyage save serialization tests."""

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from gameplay.game_state import GameState
from gameplay.savegame import (
    SAVE_VERSION,
    SaveGameManager,
    _npc_key,
    deserialize_chunk_states,
    normalize_saved_player_health,
)
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

    def test_legacy_health_cap_migrates_without_changing_health_percentage(self):
        self.assertEqual(normalize_saved_player_health(4, 5), (80, 100))
        self.assertEqual(normalize_saved_player_health(5, 5), (100, 100))
        self.assertEqual(normalize_saved_player_health(0, 5), (0, 100))
        self.assertEqual(normalize_saved_player_health(75, 100), (75, 100))

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

    def test_unnamed_saves_follow_numerical_order(self):
        world = SimpleNamespace(loaded_chunks={})
        world_run = SimpleNamespace(seed=12, current_index=1, discovered_islands={1})
        with tempfile.TemporaryDirectory() as folder:
            first = SaveGameManager(save_directory=folder)
            first_path = first.save(
                world_run, world, self.make_player(), self.make_weather(), None
            )
            second = SaveGameManager(save_directory=folder)
            second_path = second.save(
                world_run, world, self.make_player(), self.make_weather(), None
            )

            self.assertEqual(first_path.name, "save_1.json")
            self.assertEqual(second_path.name, "save_2.json")
            self.assertEqual({slot.name for slot in second.list_saves()}, {"save_1", "save_2"})

    def test_custom_save_name_is_listed_and_loaded(self):
        world = SimpleNamespace(loaded_chunks={})
        world_run = SimpleNamespace(seed=88, current_index=1, discovered_islands={1})
        with tempfile.TemporaryDirectory() as folder:
            manager = SaveGameManager(save_directory=folder)
            path = manager.save(
                world_run,
                world,
                self.make_player(),
                self.make_weather(),
                None,
                save_name="Akeem's Farm",
            )

            self.assertEqual(path.name, "Akeems_Farm.json")
            slot = manager.list_saves()[0]
            self.assertEqual(slot.name, "Akeem's Farm")
            self.assertEqual(slot.seed, 88)
            self.assertEqual(slot.day, 3)
            self.assertEqual(manager.load(slot.path)["save"]["name"], "Akeem's Farm")

    def test_editing_a_save_name_renames_the_current_slot(self):
        world = SimpleNamespace(loaded_chunks={})
        world_run = SimpleNamespace(seed=5, current_index=1, discovered_islands={1})
        with tempfile.TemporaryDirectory() as folder:
            manager = SaveGameManager(save_directory=folder)
            old_path = manager.save(
                world_run, world, self.make_player(), self.make_weather(), None
            )
            new_path = manager.save(
                world_run,
                world,
                self.make_player(),
                self.make_weather(),
                None,
                save_name="Farm Finale",
            )

            self.assertFalse(old_path.exists())
            self.assertEqual(new_path.name, "Farm_Finale.json")
            self.assertEqual([slot.name for slot in manager.list_saves()], ["Farm Finale"])

    def test_rejects_unknown_save_versions(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "slot.json"
            path.write_text('{"version": 999}', encoding="utf-8")
            with self.assertRaises(ValueError):
                SaveGameManager(path).load()

    def test_version_one_save_migrates_with_phase_one_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "slot.json"
            path.write_text(
                '{"version": 1, "world_run": {"seed": 4}, "player": {}}',
                encoding="utf-8",
            )

            payload = SaveGameManager(path).load()
            state = GameState.from_dict(payload["game_state"])

            self.assertEqual(payload["version"], SAVE_VERSION)
            self.assertEqual(state.progression.level, 1)
            self.assertEqual(state.stamina, 100)
            self.assertEqual(state.current_location_id, "player_farm")
            self.assertEqual(state.relationships, {})

    def test_version_two_save_round_trips_game_state(self):
        chunk = Chunk((0, 0), (2, 2), 16)
        world = SimpleNamespace(loaded_chunks={(0, 0): chunk})
        world_run = SimpleNamespace(seed=5, current_index=1, discovered_islands={1})
        state = GameState()
        state.add_experience(135)
        state.add_farming_points(12)
        state.add_fishing_points(8)
        state.add_trust("wife", 26)
        state.flags["prologue.started"] = True
        state.claim_event("progression", "harvest:1")

        with tempfile.TemporaryDirectory() as folder:
            manager = SaveGameManager(Path(folder) / "slot.json")
            manager.save(
                world_run,
                world,
                self.make_player(),
                self.make_weather(),
                None,
                state,
            )
            restored = GameState.from_dict(manager.load()["game_state"])

        self.assertEqual(restored.to_dict(), state.to_dict())

    def test_story_npc_save_key_does_not_depend_on_list_position(self):
        wife = SimpleNamespace(story_id="wife", save_id="story:wife")
        self.assertEqual(_npc_key(wife, 0), "story:wife")
        self.assertEqual(_npc_key(wife, 99), "story:wife")

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
