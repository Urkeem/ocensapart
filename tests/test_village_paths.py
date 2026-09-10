"""Village path generation and the player-loam tileset contract."""

import sys
import unittest
from pathlib import Path

import pygame


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from world.chunkmanager import Chunk
from world.fence import FENCE_GATE
from world.paths import GATE_BRANCH_WIDTH, MAIN_STREET_WIDTH
from world.soil import SOIL_TILESET_FILE, SoilLayer
from gameplay.terrain import get_path_surface


class VillagePathTests(unittest.TestCase):
    def make_chunk(self):
        chunk = Chunk((0, 0), (24, 24), 64)
        tile_count = 24 * 24
        chunk.layers["base"] = [1] * tile_count
        chunk.layers["terrain"] = [1] * tile_count
        chunk.layers["biome"] = [3] * tile_count
        for index, gate in enumerate(((4, 4), (18, 4), (11, 14))):
            gate_index = chunk.get_index(*gate)
            chunk.layers["fence"][gate_index] = FENCE_GATE
            chunk.layers["decoration"][gate_index] = {
                "type": "fence",
                "gate": True,
            }
            chunk.props.append({
                "type": "house",
                "id": f"test-house-{index}",
                "yard_gate_tile": gate,
            })
        return chunk

    @staticmethod
    def connected_component(path_tiles, start):
        visited = {start}
        pending = [start]
        while pending:
            x, y = pending.pop()
            for neighbor in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                if neighbor in path_tiles and neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        return visited

    def test_all_gates_join_one_winding_width_aware_network(self):
        chunk = self.make_chunk()

        generated = chunk.generate_path_tiles(world_seed=42)

        gates = set(chunk.metadata["path_gates"])
        connected = self.connected_component(generated, next(iter(gates)))
        self.assertTrue(gates.issubset(connected))
        self.assertEqual(chunk.metadata["path_main_width"], MAIN_STREET_WIDTH)
        self.assertEqual(chunk.metadata["path_branch_width"], GATE_BRANCH_WIDTH)

        main_route = chunk.metadata["path_main_route"]
        self.assertTrue(chunk.metadata["path_main_closed"])
        self.assertEqual(main_route[0], main_route[-1])
        self.assertTrue(set(main_route).issubset(generated))
        self.assertGreater(len({tile[0] for tile in main_route}), 1)
        self.assertGreater(len({tile[1] for tile in main_route}), 1)
        self.assertTrue(any(
            all(
                (center[0] + offset_x, center[1] + offset_y) in generated
                for offset_y in (-1, 0, 1)
                for offset_x in (-1, 0, 1)
            )
            for center in main_route
        ))
        self.assertIn((5, 4), generated)

    def test_single_house_still_gets_a_closed_local_street(self):
        chunk = self.make_chunk()
        keep_id = "test-house-0"
        chunk.props = [prop for prop in chunk.props if prop.get("id") == keep_id]

        generated = chunk.generate_path_tiles(world_seed=42)

        gate = tuple(chunk.props[0]["yard_gate_tile"])
        self.assertIn(gate, generated)
        self.assertTrue(chunk.metadata["path_main_closed"])
        self.assertEqual(
            chunk.metadata["path_main_route"][0],
            chunk.metadata["path_main_route"][-1],
        )

    def test_neighboring_chunks_share_connected_road_ports(self):
        left = Chunk((0, 0), (24, 24), 64)
        right = Chunk((1, 0), (24, 24), 64)
        for chunk in (left, right):
            tile_count = 24 * 24
            chunk.layers["base"] = [1] * tile_count
            chunk.layers["terrain"] = [1] * tile_count
            chunk.layers["biome"] = [3] * tile_count

        left_paths = left.generate_path_tiles(world_seed=73)
        right_paths = right.generate_path_tiles(world_seed=73)
        left_ports = dict(left.metadata["path_edge_ports"])
        right_ports = dict(right.metadata["path_edge_ports"])

        self.assertEqual(left_ports["right"][1], right_ports["left"][1])
        self.assertIn(left_ports["right"], left_paths)
        self.assertIn(right_ports["left"], right_paths)
        self.assertEqual(
            left.get_world_tile(*left_ports["right"])[1],
            right.get_world_tile(*right_ports["left"])[1],
        )

        for chunk, generated in ((left, left_paths), (right, right_paths)):
            ports = set(dict(chunk.metadata["path_edge_ports"]).values())
            connected = self.connected_component(generated, next(iter(ports)))
            self.assertTrue(ports.issubset(connected))

    def test_cliffs_are_hard_road_barriers(self):
        chunk = Chunk((0, 0), (24, 24), 64)
        tile_count = 24 * 24
        chunk.layers["base"] = [1] * tile_count
        chunk.layers["terrain"] = [1] * tile_count
        chunk.layers["biome"] = [3] * tile_count
        for y in range(24):
            chunk.layers["biome"][chunk.get_index(12, y)] = 9

        generated = chunk.generate_path_tiles(world_seed=73)

        self.assertTrue(generated)
        self.assertTrue(all(
            chunk.layers["biome"][chunk.get_index(*tile)] != 9
            for tile in generated
        ))

    def test_junction_lanterns_and_roadside_props_stay_off_the_path(self):
        chunk = self.make_chunk()
        generated = chunk.generate_path_tiles(world_seed=42)

        props = [prop for prop in chunk.props if prop.get("pathside")]
        lanterns = [prop for prop in props if prop.get("variant") == "path_junction"]
        self.assertTrue(lanterns)
        self.assertTrue(all(tuple(prop["local_tile"]) not in generated for prop in props))

        before = {prop["id"] for prop in props}
        chunk.generate_environment_props(world_seed=42, max_props=0)
        after = {prop["id"] for prop in chunk.props if prop.get("pathside")}
        self.assertEqual(after, before)

    def test_player_created_farm_land_uses_loam(self):
        self.assertEqual(SOIL_TILESET_FILE, "Tilesets/loam.png")
        chunk = self.make_chunk()
        chunk.layers["path"][chunk.get_index(8, 8)] = 1
        self.assertFalse(SoilLayer.can_till(None, chunk, 8, 8))

    def test_path_tileset_composes_an_autotiled_surface(self):
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((1, 1))
        chunk = self.make_chunk()
        chunk.generate_path_tiles(world_seed=42)

        class StubWorld:
            chunk_size = chunk.chunk_size
            loaded_chunks = {(0, 0): chunk}

        surface = get_path_surface(StubWorld(), chunk)
        self.assertEqual(surface.get_size(), (24 * 64, 24 * 64))
        self.assertEqual(chunk.runtime["path_tilemap"].filename, "Tilesets/path.png")
        self.assertGreater(surface.get_bounding_rect().width, 0)


if __name__ == "__main__":
    unittest.main()
