"""Merged grassland/forest, island coverage, and shoreline visual tests."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

import gameplay.terrain as terrain_module
from gameplay.terrain import (
    build_subdivided_grass_mask,
    build_deep_water_mask,
    build_underwater_biome_mask,
    get_biome_tilemap,
    get_mountain_surface,
    get_scaled_biome_sprite,
    get_underwater_shore_distance,
    get_underwater_alpha,
    get_scaled_underwater_biome_sprite,
    get_underwater_surface,
    get_underwater_tilemap,
)
from world.biome_visuals import (
    SUBDIVIDED_GRASS_TILESET,
    is_grass_patch_tile,
    is_weed_patch_tile,
)
from world.chunkmanager import Chunk
from world.worldmanager import (
    BIOME_GRASSLAND_AND_FOREST,
    BIOME_MOUNTAIN,
    BIOME_OCEAN,
    BIOME_BEACH,
    BIOME_UNDERWATER,
    BIOME_TABLE,
    ISLAND_RADIUS_CHUNKS,
    World,
)


class StubWorld:
    def __init__(self, chunks, seed=42):
        self.seed = seed
        self.chunk_size = next(iter(chunks.values())).chunk_size
        self.loaded_chunks = chunks


class BiomeSubdivisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_chunk(self, coord=(0, 0), biome_id=BIOME_GRASSLAND_AND_FOREST):
        chunk = Chunk(coord, (24, 24), 64)
        tile_count = 24 * 24
        chunk.layers["base"] = [1] * tile_count
        chunk.layers["terrain"] = [1] * tile_count
        chunk.layers["biome"] = [biome_id] * tile_count
        return chunk

    def test_forest_highlands_and_jungle_are_merged_into_one_biome(self):
        merged = BIOME_TABLE[BIOME_GRASSLAND_AND_FOREST]

        self.assertEqual(merged["name"], "grassland_and_forest")
        self.assertEqual(merged["tileset"], SUBDIVIDED_GRASS_TILESET)
        self.assertEqual(BIOME_TABLE[BIOME_UNDERWATER]["name"], "underwater")
        self.assertNotIn(5, BIOME_TABLE)
        self.assertNotIn(8, BIOME_TABLE)
        self.assertNotIn(10, BIOME_TABLE)

    def test_mountain_scales_cliff_tiles_to_two_by_two_world_tiles(self):
        chunk = self.make_chunk(biome_id=BIOME_MOUNTAIN)
        world = StubWorld({chunk.coord: chunk})

        tilemap = get_biome_tilemap(world, chunk, BIOME_MOUNTAIN)
        raw_sprite = tilemap.get_tile_sprite(0)
        rendered_sprite = get_scaled_biome_sprite(world, chunk, BIOME_MOUNTAIN, 0)

        self.assertEqual(tilemap.filename, "Tilesets/cliff.png")
        self.assertEqual(tilemap.source_tile_size, 64)
        self.assertEqual(raw_sprite.get_size(), (64, 64))
        self.assertEqual(rendered_sprite.get_size(), (128, 128))

        with patch(
            "gameplay.terrain.get_special_autotile_sprite",
            wraps=terrain_module.get_special_autotile_sprite,
        ) as sprite_builder:
            surface = get_mountain_surface(world, chunk)
        self.assertEqual(surface.get_size(), (24 * 64, 24 * 64))
        self.assertGreater(surface.get_bounding_rect().width, 0)
        self.assertEqual(sprite_builder.call_count, 12 * 12)
        self.assertTrue(
            all(call.args[2] == (128, 128) for call in sprite_builder.call_args_list)
        )

    def test_subdivision_contains_tiled_and_weed_patches(self):
        chunk = self.make_chunk()
        mask = build_subdivided_grass_mask(chunk, world_seed=42)

        self.assertIn(0, mask)
        self.assertIn(1, mask)
        for idx, tiled in enumerate(mask):
            local_x = idx % chunk.chunk_size[0]
            local_y = idx // chunk.chunk_size[0]
            world_x, world_y = chunk.get_world_tile(local_x, local_y)
            self.assertEqual(
                bool(tiled),
                is_grass_patch_tile(
                    42,
                    world_x,
                    world_y,
                    BIOME_GRASSLAND_AND_FOREST,
                ),
            )
            self.assertNotEqual(
                bool(tiled),
                is_weed_patch_tile(
                    42,
                    world_x,
                    world_y,
                    BIOME_GRASSLAND_AND_FOREST,
                ),
            )

    def test_grass_autotile_mask_only_covers_the_merged_biome(self):
        chunk = self.make_chunk()
        chunk.layers["biome"] = [
            BIOME_GRASSLAND_AND_FOREST
            if idx % chunk.chunk_size[0] < 12
            else BIOME_MOUNTAIN
            for idx in range(24 * 24)
        ]
        world = StubWorld({chunk.coord: chunk})

        tilemap = get_biome_tilemap(
            world,
            chunk,
            BIOME_GRASSLAND_AND_FOREST,
        )

        self.assertEqual(tilemap.filename, SUBDIVIDED_GRASS_TILESET)
        self.assertEqual(
            tilemap.layer_data,
            build_subdivided_grass_mask(chunk, world.seed),
        )
        self.assertTrue(
            all(
                value == 0
                for idx, value in enumerate(tilemap.layer_data)
                if idx % chunk.chunk_size[0] >= 12
            )
        )

    def test_generated_target_biome_weeds_only_use_untiled_patches(self):
        chunk = self.make_chunk()
        chunk.generate_environment_props(world_seed=42, max_props=180)
        weeds = [
            prop
            for prop in chunk.props
            if prop.get("type") == "environment" and prop.get("prop_type") == "weed"
        ]

        self.assertTrue(weeds)
        for weed in weeds:
            world_x, world_y = weed["world_tile"]
            self.assertTrue(
                is_weed_patch_tile(
                    42,
                    world_x,
                    world_y,
                    BIOME_GRASSLAND_AND_FOREST,
                )
            )

    def test_larger_island_guarantees_every_remaining_biome(self):
        world = World(
            seed=73,
            spawn_chunk=(0, 0),
            chunk_size=(24, 24),
            active_radius=1,
            tile_size=64,
        )

        self.assertEqual(world.island.radius_chunks, ISLAND_RADIUS_CHUNKS)
        self.assertEqual(len(world.get_level_chunk_coords()), 100)
        expected_inland_and_shore = set(BIOME_TABLE) - {
            BIOME_OCEAN,
            BIOME_UNDERWATER,
        }
        self.assertEqual(
            {biome_id for biome_id, _, _ in world.biome_core_centers},
            expected_inland_and_shore,
        )

        generated = {BIOME_OCEAN, BIOME_UNDERWATER}
        for biome_id, world_x, world_y in world.biome_core_centers:
            generated.update(world._build_biome_layer(
                terrain_map=[1],
                elevation_map=[world._sample_elevation(world_x, world_y)],
                moisture_map=[world._sample_moisture(world_x, world_y)],
                dim=(1, 1),
                origin_tile=(world_x, world_y),
            ))
        self.assertEqual(generated, set(BIOME_TABLE))

    def test_underwater_biome_fades_away_from_beach(self):
        chunk = self.make_chunk(biome_id=BIOME_OCEAN)
        width, height = chunk.chunk_size
        for local_y in range(height):
            for local_x in range(width):
                idx = chunk.get_index(local_x, local_y)
                if local_x < 4:
                    chunk.layers["terrain"][idx] = 0
                    chunk.layers["biome"][idx] = BIOME_BEACH
                else:
                    chunk.layers["terrain"][idx] = -1
                    chunk.layers["biome"][idx] = (
                        BIOME_UNDERWATER if local_x <= 8 else BIOME_OCEAN
                    )
                    chunk.layers["elevation"][idx] = 0.5
        world = StubWorld({chunk.coord: chunk})

        self.assertEqual(get_underwater_shore_distance(world, chunk, 4, 12), 1)
        self.assertEqual(get_underwater_shore_distance(world, chunk, 8, 12), 5)
        self.assertIsNone(get_underwater_shore_distance(world, chunk, 9, 12))

        mask = build_underwater_biome_mask(world, chunk)
        for local_y in range(height):
            for local_x in range(width):
                expected = 1 if 4 <= local_x <= 8 else 0
                self.assertEqual(mask[chunk.get_index(local_x, local_y)], expected)

        tilemap = get_underwater_tilemap(world, chunk)
        self.assertEqual(tilemap.filename, "Tilesets/under_water.png")
        self.assertEqual(tilemap.source_tile_size, 16)
        self.assertEqual(tilemap.layer_data, mask)

        near_sprite = get_scaled_underwater_biome_sprite(
            world,
            chunk,
            chunk.get_index(4, 12),
        )
        far_sprite = get_scaled_underwater_biome_sprite(
            world,
            chunk,
            chunk.get_index(8, 12),
        )
        self.assertEqual(get_underwater_alpha(1), 50)
        self.assertEqual(get_underwater_alpha(5), 0)
        self.assertEqual(near_sprite.get_size(), (16, 16))
        self.assertEqual(far_sprite.get_size(), (16, 16))
        self.assertEqual(near_sprite.get_alpha(), 50)
        self.assertEqual(far_sprite.get_alpha(), 0)

        with patch(
            "gameplay.terrain.get_special_autotile_sprite",
            wraps=terrain_module.get_special_autotile_sprite,
        ) as sprite_builder:
            surface = get_underwater_surface(world, chunk)
        self.assertEqual(surface.get_size(), (width * 64, height * 64))
        self.assertGreater(surface.get_bounding_rect().width, 0)
        self.assertEqual(sprite_builder.call_count, 4 * height * 16)
        self.assertTrue(
            all(call.args[2] == (16, 16) for call in sprite_builder.call_args_list)
        )

    def test_underwater_ring_is_part_of_the_generated_biome_layer(self):
        world = World(seed=91, chunk_size=(24, 24), tile_size=64)
        terrain = [0, 0, 0, 0] + [-1] * 8
        biomes = world._build_biome_layer(
            terrain_map=terrain,
            elevation_map=[0.5] * len(terrain),
            moisture_map=[0.5] * len(terrain),
            dim=(len(terrain), 1),
            origin_tile=(1000, 1000),
        )

        self.assertEqual(biomes[4:9], [BIOME_UNDERWATER] * 5)
        self.assertEqual(biomes[9:], [BIOME_OCEAN] * 3)

    def test_expanded_mountains_fill_complete_two_by_two_blocks(self):
        world = World(seed=19, chunk_size=(24, 24), tile_size=64)
        width = height = 8
        biomes = [BIOME_GRASSLAND_AND_FOREST] * (width * height)
        biomes[3 * width + 3] = BIOME_MOUNTAIN
        expanded = world._expand_and_align_mountain_biome(
            biomes,
            [1] * len(biomes),
            (width, height),
            (0, 0),
        )

        self.assertGreater(expanded.count(BIOME_MOUNTAIN), 1)
        for block_y in range(0, height, 2):
            for block_x in range(0, width, 2):
                block = [
                    expanded[(block_y + offset_y) * width + block_x + offset_x]
                    for offset_y in range(2)
                    for offset_x in range(2)
                ]
                self.assertIn(
                    block,
                    (
                        [BIOME_GRASSLAND_AND_FOREST] * 4,
                        [BIOME_MOUNTAIN] * 4,
                    ),
                )

    def test_underwater_biome_never_overlaps_deep_ocean(self):
        chunk = self.make_chunk(biome_id=BIOME_OCEAN)
        width, height = chunk.chunk_size
        for local_y in range(height):
            for local_x in range(width):
                idx = chunk.get_index(local_x, local_y)
                if local_x < 4:
                    chunk.layers["terrain"][idx] = 0
                    chunk.layers["biome"][idx] = BIOME_BEACH
                else:
                    chunk.layers["terrain"][idx] = -1
                    chunk.layers["biome"][idx] = (
                        BIOME_UNDERWATER if local_x == 4 else BIOME_OCEAN
                    )
                    chunk.layers["elevation"][idx] = 0.1
        world = StubWorld({chunk.coord: chunk})

        underwater_mask = build_underwater_biome_mask(world, chunk)
        deep_mask = build_deep_water_mask(chunk, world)

        self.assertEqual(underwater_mask[chunk.get_index(4, 12)], 1)
        self.assertEqual(underwater_mask[chunk.get_index(5, 12)], 0)
        self.assertEqual(deep_mask[chunk.get_index(5, 12)], 1)
        self.assertTrue(
            all(not (underwater and deep) for underwater, deep in zip(underwater_mask, deep_mask))
        )


if __name__ == "__main__":
    unittest.main()
