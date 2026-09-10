import os
import sys
import unittest

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT_DIR, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

from entities.player import Player
from assets import LoadAssets
from entities.environment_prop import get_environment_image, list_environment_assets
from inventory_item import Item
from scenemanager import HOUSE_SCENE_TEMPLATES
from core.camera import Camera
from entities.tree import STUMP_LIFETIME
from gameplay.rendering import draw_farming_selector
from gameplay.world_objects import (
    collect_pickups_near_player,
    ensure_chunk_environment_objects,
    ensure_chunk_tree_objects,
    update_world_objects,
)
from ui.inventory import Inventory, load_item_icon
from world.chunkmanager import Chunk
from world.fence import FENCE_SEGMENT
from world.soil import (
    UNUSED_PLAYER_SOIL_LIFETIME_MINUTES,
    SoilLayer,
    ensure_chunk_plant_objects,
    get_soil_surface,
)


class StubWorld:
    def __init__(self):
        self.tile_size = 64
        self.chunk_size = (4, 4)
        self.chunk = Chunk((0, 0), self.chunk_size, self.tile_size)
        self.chunk.layers["terrain"] = [1] * 16
        self.chunk.layers["base"] = [1] * 16
        self.loaded_chunks = {(0, 0): self.chunk}
        self.invalidated = []
        self.seed = 42
        self.active_chunks = {(0, 0)}

    def invalidate_soil_chunk_and_neighbors(self, chunk_coord):
        self.invalidated.append((chunk_coord, "neighbors"))
        self.chunk.runtime["soil_surface"] = None
        self.chunk.runtime["soil_tilemap"] = None
        self.chunk.runtime["soil_water_tilemap"] = None

    def invalidate_soil_render_cache(self, chunk_coord, **_kwargs):
        self.invalidated.append((chunk_coord, "render"))
        self.chunk.runtime["soil_surface"] = None

    def invalidate_fence_chunk_and_neighbors(self, chunk_coord):
        self.invalidated.append((chunk_coord, "fence"))
        self.chunk.runtime["fence_collision_objects"] = None


class StubTime:
    def __init__(self, day, time=360):
        self.day = day
        self.time = time


class StubHarvester:
    def __init__(self):
        self.harvested_crops = {}
        self.inventory = Inventory(2)


class FarmingSystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.world = StubWorld()
        self.soil = SoilLayer(self.world)

    def world_pos(self, tile):
        return (
            tile[0] * self.world.tile_size + self.world.tile_size // 2,
            tile[1] * self.world.tile_size + self.world.tile_size // 2,
        )

    def test_all_crop_sheets_expose_six_growth_frames(self):
        self.assertGreaterEqual(len(self.soil.plant_frames), 36)
        self.assertIn("corn", self.soil.plant_frames)
        self.assertTrue(
            all(
                len(frames) == 6 and all(frame.get_size() == (16, 16) for frame in frames)
                for frames in self.soil.plant_frames.values()
            )
        )

    def test_shell_spritesheets_expose_fourteen_individual_pickups(self):
        shell_assets = list_environment_assets("shells")

        self.assertEqual(len(shell_assets), 14)
        self.assertNotIn("shells/under_water_stuff.png", shell_assets)
        self.assertEqual(
            get_environment_image(shell_assets[0], scale=2).get_size(),
            (32, 32),
        )

    def test_directional_farm_lifecycle_requires_explicit_harvest(self):
        tile = (1, 1)
        pos = self.world_pos(tile)

        self.assertTrue(self.soil.till_at(pos))
        self.assertFalse(self.soil.till_at(pos))
        self.assertTrue(self.soil.plant_seed_at(pos, "corn", StubTime(1)))
        self.assertFalse(self.soil.plant_seed_at(pos, "corn", StubTime(1)))
        self.assertTrue(self.soil.water_at(pos, StubTime(1)))
        self.assertFalse(self.soil.water_at(pos, StubTime(1)))

        for day in range(2, 7):
            self.soil.water_at(pos, StubTime(day))
            self.soil.update(0, StubTime(day))

        self.assertTrue(self.soil.can_harvest_at_tile(tile))
        harvester = StubHarvester()
        self.assertEqual(self.soil.harvest_at(pos, harvester), "corn")
        self.assertEqual(harvester.harvested_crops["corn"], 1)
        self.assertEqual(harvester.inventory.count_item("corn"), 1)
        self.assertIsNone(self.soil.get_tile_state(tile)["plant"])

    def test_multiple_plants_remain_in_the_render_cache(self):
        for tile in ((1, 1), (2, 1)):
            pos = self.world_pos(tile)
            self.assertTrue(self.soil.till_at(pos))
            self.assertTrue(self.soil.plant_seed_at(pos, "tomato"))

        plants = ensure_chunk_plant_objects(self.world.chunk, self.soil)
        self.assertEqual(len(plants), 2)
        self.assertTrue(all(plant.image.get_size() == (32, 32) for plant in plants))
        self.assertEqual(
            {plant.rect.center for plant in plants},
            {(96, 96), (160, 96)},
        )

    def test_wet_soil_uses_the_new_autotile(self):
        pos = self.world_pos((1, 1))
        self.soil.till_at(pos)
        self.soil.water_at(pos)

        surface = get_soil_surface(self.world, self.world.chunk)

        self.assertEqual(surface.get_size(), (256, 256))
        self.assertEqual(
            self.world.chunk.runtime["soil_water_tilemap"].filename,
            "Tilesets/plant_water.png",
        )

    def test_player_targets_the_tile_underfoot(self):
        player = Player.__new__(Player)
        player.soil_layer = self.soil
        player.feet_collision_box = pygame.Rect(64, 64, 12, 8)
        player.feet_collision_box.center = (96, 96)
        player.facing = "right"
        player.selected_tool = "hoe"
        player.selected_seed = "corn"
        player.seed_inventory = {"corn": 1}

        self.assertEqual(player.get_facing_world_tile(), (2, 1))
        self.assertEqual(player.get_current_world_tile(), (1, 1))
        self.assertEqual(tuple(player.get_target_pos()), (96.0, 96.0))
        self.assertEqual(player.get_farming_target(), ((1, 1), "till"))

        screen = pygame.Surface((384, 384), pygame.SRCALPHA)
        draw_farming_selector(screen, player, Camera(384, 384))
        self.assertNotEqual(
            screen.subsurface((64, 64, 64, 64)).get_bounding_rect().size,
            (0, 0),
        )

    def make_interaction_player(self, *, tool="hoe"):
        player = Player.__new__(Player)
        player.soil_layer = self.soil
        player.feet_collision_box = pygame.Rect(90, 92, 12, 8)
        player.facing = "right"
        player.selected_tool = tool
        player.tool_max_durability = {
            "hoe": 3,
            "axe": 3,
            "pickaxe": 3,
            "shovel": 3,
            "water": 3,
            "fishing rod": 3,
        }
        player.tool_durability = dict(player.tool_max_durability)
        player.broken_tools = set()
        player.water_capacity = 8
        player.water_amount = 8
        player.harvested_crops = {}
        player.inventory = Inventory(2)
        return player

    def test_fence_item_is_placeable_and_consumed_after_success(self):
        player = self.make_interaction_player()
        fence = Item("fence")
        self.assertTrue(fence.place)
        self.assertEqual(fence.placement_type, "fence")
        self.assertTrue(player.inventory.add_item_to_slot(fence, amount=2))
        self.assertTrue(player.inventory.select_placeable("fence"))

        self.assertEqual(player.use_selected_placeable(), "place")
        target_index = self.world.chunk.get_index(1, 1)
        self.assertEqual(self.world.chunk.layers["fence"][target_index], FENCE_SEGMENT)
        self.assertEqual(self.world.chunk.layers["collision"][target_index], 1)
        self.assertEqual(player.inventory.count_item("fence"), 1)

    def test_shovel_collects_underfoot_weed_and_wears(self):
        player = self.make_interaction_player(tool="shovel")
        record = {
            "type": "environment",
            "id": "test:weed",
            "prop_type": "weed",
            "world_tile": (1, 1),
            "local_tile": (1, 1),
            "removed": False,
            "blocks_movement": False,
        }
        self.world.chunk.props.append(record)
        index = self.world.chunk.get_index(1, 1)
        self.world.chunk.layers["decoration"][index] = {
            "type": "environment",
            "id": "test:weed",
            "prop_type": "weed",
        }

        self.assertEqual(player.use_tool(), "clear")
        self.assertTrue(record["removed"])
        self.assertIsNone(self.world.chunk.layers["decoration"][index])
        self.assertEqual(player.tool_durability["shovel"], 2)
        self.assertEqual(player.inventory.count_item("weed"), 1)

    def test_pickaxe_breaks_stones_instead_of_axe(self):
        player = self.make_interaction_player(tool="pickaxe")
        record = {
            "type": "environment",
            "id": "test:rock",
            "prop_type": "rock",
            "variant": "small",
            "asset": "rocks/small/r1.png",
            "world_pos": self.world_pos((2, 1)),
            "world_tile": (2, 1),
            "local_tile": (2, 1),
            "blocks_movement": True,
            "health": 1,
            "scale": 1,
        }
        self.world.chunk.props.append(record)
        ensure_chunk_environment_objects(self.world.chunk)

        self.assertEqual(player.use_tool(), "pickaxe")
        self.assertTrue(record["removed"])
        self.assertEqual(player.tool_durability["pickaxe"], 2)

    def test_interact_picks_up_hay_and_tree_fruit(self):
        player = self.make_interaction_player()
        hay_record = {
            "type": "environment",
            "id": "test:hay",
            "prop_type": "hay",
            "asset": "props/general/hay.png",
            "world_pos": self.world_pos((1, 1)),
            "world_tile": (1, 1),
            "local_tile": (1, 1),
            "blocks_movement": False,
            "health": 0,
            "scale": 1,
        }
        self.world.chunk.props.append(hay_record)
        self.assertTrue(collect_pickups_near_player(self.world, player))
        self.assertEqual(player.inventory.count_item("hay"), 1)

        tree_record = {
            "type": "tree",
            "id": "test:fruit-tree",
            "species": "oak",
            "health": 6,
            "blocks_movement": True,
            "chunk": self.world.chunk.coord,
            "local_tile": (1, 1),
            "world_tile": (1, 1),
            "world_pos": self.world_pos((1, 1)),
        }
        self.world.chunk.props.append(tree_record)
        tree = ensure_chunk_tree_objects(self.world.chunk)[0]
        tree.fruit_name = "Coconut"
        tree.fruit_surf = pygame.Surface((16, 16), pygame.SRCALPHA)
        tree.fruit_count = 2

        self.assertTrue(collect_pickups_near_player(self.world, player))
        self.assertEqual(player.inventory.count_item("Coconut"), 2)

    def test_barrels_break_with_any_tool_and_drop_rum(self):
        player = self.make_interaction_player(tool="water")
        record = {
            "type": "environment",
            "id": "test:barrel",
            "prop_type": "barrel",
            "asset": "props/general/barrel.png",
            "world_pos": self.world_pos((2, 1)),
            "world_tile": (2, 1),
            "local_tile": (2, 1),
            "blocks_movement": True,
            "health": 2,
            "scale": 1,
        }
        self.world.chunk.props.append(record)
        ensure_chunk_environment_objects(self.world.chunk)

        self.assertEqual(player.use_tool(), "break")
        self.assertEqual(player.use_tool(), "break")
        self.assertTrue(record["removed"])
        self.assertGreaterEqual(player.inventory.count_item("wood"), 1)
        self.assertEqual(player.inventory.count_item("rum"), 1)

    def test_unused_player_farmland_expires_after_one_week(self):
        pos = self.world_pos((1, 1))
        self.assertTrue(self.soil.till_at(pos))
        self.soil.update(0, StubTime(7, 360))
        self.assertEqual(self.world.chunk.layers["soil"][self.world.chunk.get_index(1, 1)], 1)
        self.assertTrue(self.soil.water_at(pos, StubTime(7, 360)))

        self.soil.update(0, StubTime(8, 360))
        self.assertEqual(self.world.chunk.layers["soil"][self.world.chunk.get_index(1, 1)], 0)
        self.assertEqual(self.world.chunk.layers["soil_water"][self.world.chunk.get_index(1, 1)], 0)
        self.assertEqual(UNUSED_PLAYER_SOIL_LIFETIME_MINUTES, 7 * 1440)

    def test_inventory_stacks_split_at_fifty(self):
        inventory = Inventory(3)
        self.assertTrue(inventory.add_item_to_slot(Item("wood"), amount=120))
        self.assertEqual([slot.amount for slot in inventory.slots], [50, 50, 20])
        self.assertFalse(inventory.add_item_to_slot(Item("wood"), amount=31))
        self.assertEqual(inventory.count_item("wood"), 120)

    def test_inventory_and_hotbar_slot_art_is_square(self):
        slot = Inventory(1).slots[0]
        self.assertEqual(slot.assets.sprite_data["slot"][2:], (28, 28))
        self.assertEqual(slot.empty_image.get_size(), (64, 64))
        self.assertEqual(slot.occupied_image.get_size(), (64, 64))
        self.assertEqual(slot.hover_image.get_size(), (64, 64))

    def test_bushes_are_collected_with_shovels_and_replenish(self):
        player = self.make_interaction_player(tool="shovel")
        record = {
            "type": "environment",
            "id": "test:bush",
            "prop_type": "bush",
            "world_tile": (1, 1),
            "local_tile": (1, 1),
            "removed": False,
            "blocks_movement": False,
        }
        self.world.chunk.props.append(record)
        index = self.world.chunk.get_index(1, 1)
        self.world.chunk.layers["decoration"][index] = {
            "type": "environment",
            "id": "test:bush",
            "prop_type": "bush",
        }
        self.assertEqual(player.use_tool(), "clear")
        self.assertEqual(player.inventory.count_item("weed"), 2)
        self.assertEqual(player.inventory.count_item("bush"), 0)

        self.world.chunk.layers["biome"] = [3] * 16
        self.world.chunk.layers["moisture"] = [0.7] * 16
        self.world.chunk.layers["elevation"] = [0.2] * 16
        spawned = self.world.chunk.replenish_natural_resources(
            world_seed=self.world.seed,
            minimum_weeds=0,
            minimum_bushes=1,
            minimum_trees=0,
            max_new=1,
        )
        self.assertEqual(spawned, 1)
        bushes = [
            prop
            for prop in self.world.chunk.props
            if prop.get("prop_type") == "bush" and not prop.get("removed", False)
        ]
        self.assertEqual(len(bushes), 1)
        self.assertTrue(bushes[0]["regrown"])

    def test_wheelbarrow_sheet_exposes_two_36_by_44_frames(self):
        first = get_environment_image("props/general/wheelbarrow.png#0", scale=1)
        second = get_environment_image("props/general/wheelbarrow.png#1", scale=1)
        self.assertEqual(first.get_size(), (36, 44))
        self.assertEqual(second.get_size(), (36, 44))

    def test_fenced_flower_sheet_exposes_three_80_by_35_frames(self):
        frames = [
            get_environment_image(
                f"props/flowers_pot_fenced/flowerfenced.png#{index}",
                scale=1,
            )
            for index in range(3)
        ]
        self.assertTrue(all(frame.get_size() == (80, 35) for frame in frames))

    def test_natural_flower_folder_exposes_individual_flower_assets(self):
        flower_assets = list_environment_assets("flowers")

        self.assertEqual(len(flower_assets), 9)
        self.assertTrue(all(asset.startswith("flowers/") for asset in flower_assets))
        self.assertTrue(
            all(isinstance(get_environment_image(asset), pygame.Surface) for asset in flower_assets)
        )

    def test_resource_pickups_use_inventory_icons(self):
        for item_name in ("weed", "bush", "hay", "flower"):
            with self.subTest(item_name=item_name):
                icon = load_item_icon(item_name)
                self.assertIsInstance(icon, pygame.Surface)
                self.assertEqual(icon.get_size(), (32, 32))
                inventory = Inventory(1)
                self.assertTrue(inventory.add_item_to_slot(Item(item_name)))
                self.assertEqual(
                    pygame.image.tobytes(inventory.slots[0].item.image, "RGBA"),
                    pygame.image.tobytes(icon, "RGBA"),
                )

        self.assertIs(load_item_icon("bush"), load_item_icon("weed"))

    def test_generated_scene_prop_assets_can_all_be_loaded(self):
        scene_assets = {
            prop["asset"]
            for template in HOUSE_SCENE_TEMPLATES
            for prop in template.get("props", ())
        }
        for asset in sorted(scene_assets):
            with self.subTest(asset=asset):
                self.assertIsInstance(get_environment_image(asset), pygame.Surface)

    def test_resource_recipes_include_placeables_hay_and_wheelbarrows(self):
        recipes = self.make_interaction_player().inventory.craft_system
        self.assertTrue(
            set(self.soil.available_crops).issubset(recipes.get_items("seeds"))
        )
        self.assertNotIn("placeables", recipes.get_categories())
        self.assertEqual(recipes.get_recipe("resources", "crate"), {"wood": 4})
        self.assertEqual(
            recipes.get_recipe("resources", "wheelbarrow"),
            {"wood": 6, "iron": 2},
        )
        self.assertEqual(recipes.get_recipe("resources", "hay"), {"weed": 3})

    def test_wheelbarrow_can_be_placed_from_inventory(self):
        player = self.make_interaction_player()
        wheelbarrow = Item("wheelbarrow")
        self.assertTrue(player.inventory.add_item_to_slot(wheelbarrow))
        self.assertTrue(player.inventory.select_placeable("wheelbarrow"))
        self.assertEqual(player.get_placement_target(), ((2, 1), "place"))

        self.assertEqual(player.use_selected_placeable(), "place")
        placed = next(
            prop
            for prop in self.world.chunk.props
            if prop.get("prop_type") == "wheelbarrow"
        )
        self.assertTrue(placed["player_placed"])
        wheelbarrow_object = ensure_chunk_environment_objects(self.world.chunk)[0]
        self.assertEqual(wheelbarrow_object.image.get_size(), (36, 44))
        self.assertEqual(player.inventory.count_item("wheelbarrow"), 0)

    def test_tool_actions_use_sheet_aligned_character_layers(self):
        class SolidToolSheet:
            def get_sprite(self, _x, _y, width, height):
                layer = pygame.Surface((width, height), pygame.SRCALPHA)
                layer.fill((213, 97, 41, 255))
                return layer

        assets = LoadAssets.__new__(LoadAssets)
        assets.character_parts = {
            "skin": {},
            "clothes": {},
            "hair": {},
            "weapon": {},
        }
        assets.default_character_customization = {
            "skin": None,
            "clothes": None,
            "hair": None,
            "weapon": None,
        }
        assets.farm_tool_sheet = SolidToolSheet()

        frame_rect = (0, 0, 64, 64)
        for animation_name in (
            "down_hoe",
            "down_axe",
            "down_water",
            "down_seed",
            "down_cast",
            "down_fish",
            "down_reel",
        ):
            with self.subTest(animation_name=animation_name):
                frame = assets.compose_character_frame(animation_name, frame_rect, None)
                self.assertEqual(frame.get_at((32, 32)), (213, 97, 41, 255))

    def test_watering_can_runs_dry_and_refills_facing_water(self):
        player = self.make_interaction_player(tool="water")
        self.assertTrue(self.soil.till_at(self.world_pos((1, 1))))
        player.water_amount = 1
        water_index = self.world.chunk.get_index(2, 1)
        self.world.chunk.layers["terrain"][water_index] = -1

        self.assertEqual(player.use_tool(), "water")
        self.assertEqual(player.water_amount, 0)
        self.assertEqual(player.tool_durability["water"], 2)
        self.assertEqual(player.use_tool(), "refill")
        self.assertEqual(player.water_amount, player.water_capacity)

    def test_broken_tool_can_be_replaced_by_crafting_hook(self):
        player = self.make_interaction_player(tool="hoe")
        player.wear_tool("hoe", 3)
        self.assertFalse(player.is_tool_usable("hoe"))

        player.restore_tool("hoe")
        self.assertTrue(player.is_tool_usable("hoe"))
        self.assertEqual(player.tool_durability["hoe"], 3)

    def test_sparse_nature_replenishes_only_on_free_tiles(self):
        chunk = self.world.chunk
        chunk.layers["biome"] = [3] * 16
        chunk.layers["moisture"] = [0.7] * 16
        chunk.layers["elevation"] = [0.2] * 16
        occupied_index = chunk.get_index(0, 0)
        chunk.layers["decoration"][occupied_index] = {"type": "house"}

        spawned = chunk.replenish_natural_resources(
            world_seed=self.world.seed,
            minimum_weeds=1,
            minimum_trees=0,
            max_new=1,
        )

        self.assertEqual(spawned, 1)
        weed = next(prop for prop in chunk.props if prop.get("prop_type") == "weed")
        self.assertNotEqual(tuple(weed["local_tile"]), (0, 0))
        self.assertTrue(weed["regrown"])

    def test_sparse_tree_population_replenishes(self):
        chunk = self.world.chunk
        chunk.layers["biome"] = [3] * 16
        chunk.layers["moisture"] = [0.7] * 16
        chunk.layers["elevation"] = [0.2] * 16

        for _ in range(20):
            chunk.replenish_natural_resources(
                world_seed=self.world.seed,
                minimum_weeds=0,
                minimum_trees=1,
                max_new=1,
            )
            trees = [prop for prop in chunk.props if prop.get("type") == "tree"]
            if trees:
                break

        self.assertEqual(len(trees), 1)
        self.assertTrue(trees[0]["regrown"])
        tree_index = chunk.get_index(*trees[0]["local_tile"])
        self.assertEqual(chunk.layers["collision"][tree_index], 1)

    def test_tree_stump_disappears_after_its_lifetime(self):
        chunk = self.world.chunk
        record = {
            "type": "tree",
            "id": "test:tree",
            "species": "oak",
            "health": 0,
            "blocks_movement": True,
            "chunk": chunk.coord,
            "local_tile": (1, 1),
            "world_tile": (1, 1),
            "world_pos": self.world_pos((1, 1)),
        }
        chunk.props.append(record)
        tree_index = chunk.get_index(1, 1)
        chunk.layers["decoration"][tree_index] = {
            "type": "tree",
            "species": "oak",
        }
        chunk.layers["collision"][tree_index] = 1

        ensure_chunk_tree_objects(chunk)
        update_world_objects(
            [((0, 0), chunk, 0, 0)],
            None,
            STUMP_LIFETIME - 1.0,
        )
        self.assertIn(record, chunk.props)

        update_world_objects(
            [((0, 0), chunk, 0, 0)],
            None,
            1.0,
        )

        self.assertNotIn(record, chunk.props)
        self.assertEqual(ensure_chunk_tree_objects(chunk), ())
        self.assertIsNone(chunk.layers["decoration"][tree_index])
        self.assertEqual(chunk.layers["collision"][tree_index], 0)
        self.assertIn("test:tree", chunk.save_data["removed_props"])


if __name__ == "__main__":
    unittest.main()
