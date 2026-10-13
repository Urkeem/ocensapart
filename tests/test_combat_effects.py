"""Combat animation, layered guard, and horizontal FX strip tests."""

import os
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from assets import LoadAssets
from entities.npc import GuardNPC
from entities.player import Player
from gameplay.effects import EffectLibrary, EffectsManager
from ui.hud import GameplayHUD
from ui.inventory import load_item_icon


class RecordingEffects:
    def __init__(self):
        self.spawned = []

    def spawn(self, name, pos, **kwargs):
        self.spawned.append((name, pos, kwargs))


class StubControllerInput:
    connected = False

    @staticmethod
    def get_button(_button):
        return False

    @staticmethod
    def movement_vector():
        return pygame.Vector2()

    @staticmethod
    def menu_navigation_button(_event):
        return None

    @staticmethod
    def is_axis_pressed(_event, _axis):
        return False


class StubInventory:
    def __init__(self):
        self.is_inv = False

    @staticmethod
    def get_selected_placeable():
        return None


class CombatEffectsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))
        cls.assets = LoadAssets()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def make_player(self):
        with patch("entities.player.Inventory", return_value=StubInventory()):
            return Player(
                (100, 100),
                self.assets,
                visual_scale=1,
                controller_input=StubControllerInput(),
            )

    def test_every_effect_variant_splits_into_its_declared_frame_count(self):
        library = EffectLibrary()
        for name, spec in library.specs.items():
            for variant_index in range(len(spec.paths)):
                with self.subTest(effect=name, variant=variant_index):
                    frames = library.load_variant(name, variant_index)
                    self.assertEqual(len(frames), spec.frame_count)
                    self.assertTrue(all(frame.get_width() > 0 for frame in frames))

    def test_contact_particles_keep_their_native_frame_sizes(self):
        library = EffectLibrary()

        self.assertEqual(library.load_variant("bush", 0)[0].get_size(), (20, 18))
        self.assertEqual(library.load_variant("hay", 0)[0].get_size(), (22, 22))
        self.assertEqual(library.load_variant("grass", 0)[0].get_size(), (22, 22))

    def test_all_guard_combat_animation_keys_are_composable(self):
        actions = (
            "weapon_idle",
            "weapon_stealth_move",
            "sword_slash1",
            "sword_slash2",
            "sword_thrust",
            "shield_bash",
            "hurt_sword",
            "dead_sword",
        )
        for direction in ("down", "up", "right", "left"):
            for action in actions:
                key = f"{direction}_{action}"
                with self.subTest(animation=key):
                    frames = self.assets.get_guard_frames(key)
                    self.assertTrue(frames)
                    self.assertTrue(all(frame.get_size() == (64, 64) for frame in frames))

    def test_guard_uses_dedicated_npc_layers_and_retaliates_after_a_hit(self):
        guard = GuardNPC((100, 100), self.assets, pathfinder=object(), visual_scale=1)
        effects = RecordingEffects()

        self.assertEqual(
            set(self.assets.guard_parts),
            {"skin", "outfit", "hair", "sword", "shield"},
        )
        self.assertFalse(guard.hostile)

        self.assertTrue(guard.take_damage(1, effects=effects, source=object()))

        self.assertTrue(guard.hostile)
        self.assertTrue(guard.is_enemy)
        self.assertEqual(effects.spawned[0][0], "blood")

    def test_player_weapon_selection_uses_weapon_idle_animation(self):
        player = self.make_player()
        player.selected_tool = "sword"
        player._sync_equipped_tool()
        player.direction.update(0, 0)

        player.update_status()

        self.assertEqual(player.status, "down_weapon_idle")

    def test_weapon_layer_and_idle_animation_only_show_for_weapon_slot(self):
        player = self.make_player()
        player.direction.update(0, 0)

        self.assertEqual(player.selected_selection_slot, "tool")
        self.assertIsNone(player.customization["weapon"])
        self.assertIsNone(player.customization["offhand"])
        self.assertFalse(player.has_equipped_weapon(player.selected_weapon))
        player.update_status()
        self.assertEqual(player.status, "down_idle")

        self.assertEqual(player.cycle_selection_slot(), "weapon")
        self.assertEqual(player.customization["weapon"], player.selected_weapon)
        self.assertTrue(player.has_equipped_weapon(player.selected_weapon))
        player.update_status()
        self.assertEqual(player.status, "down_weapon_idle")

        self.assertEqual(player.cycle_selection_slot(), "seed")
        self.assertIsNone(player.customization["weapon"])
        self.assertIsNone(player.customization["offhand"])
        self.assertFalse(player.has_equipped_weapon(player.selected_weapon))
        player.update_status()
        self.assertEqual(player.status, "down_idle")

    def test_player_death_is_one_shot_then_can_revive(self):
        player = self.make_player()
        source = type(
            "Source",
            (),
            {
                "center": (0, player.feet_collision_box.centery),
                "direction": pygame.Vector2(1, 0),
            },
        )()
        player.health = 1

        self.assertTrue(player.take_damage(1, source=source))
        self.assertGreater(player.knockback_velocity.x, 0)
        player.update_status()
        player.refresh_animation_set()
        self.assertFalse(player.loop)

        player.animate(1.0)
        final_index = player.index
        self.assertTrue(player.death_animation_complete)
        player.animate(1.0)
        self.assertEqual(player.index, final_index)

        player.revive()
        self.assertTrue(player.is_alive)
        self.assertEqual(player.health, player.max_health)
        self.assertEqual(player.status, "down_idle")
        self.assertTrue(player.loop)

    def test_guard_death_and_knockback_stop_on_the_final_frame(self):
        guard = GuardNPC((100, 100), self.assets, pathfinder=object(), visual_scale=1)
        source = type(
            "Source",
            (),
            {
                "center": (0, guard.rect.centery),
                "direction": pygame.Vector2(1, 0),
            },
        )()
        start_x = guard.pos.x

        self.assertTrue(guard.take_damage(guard.health, source=source))
        guard.update(1.0)

        self.assertGreater(guard.pos.x, start_x)
        self.assertFalse(guard.loop)
        self.assertTrue(guard.animation_finished)
        final_index = guard.index
        guard.update(1.0)
        self.assertEqual(guard.index, final_index)

    def test_death_panel_draws_exit_and_revive_choices(self):
        player = self.make_player()
        player.health = 0
        player.animation_finished = True
        hud = GameplayHUD.__new__(GameplayHUD)
        hud.player = player
        hud.screen = pygame.Surface((800, 600))
        hud.screen_w, hud.screen_h = hud.screen.get_size()
        hud.font = pygame.font.Font(None, 22)
        hud.small_font = pygame.font.Font(None, 16)
        hud.death_title_font = pygame.font.Font(None, 50)
        hud.death_options = ("Exit", "Revive")
        hud.death_selection = 1
        hud.death_exit_requested = False
        hud.death_button_rects = []

        hud.draw_death_panel()

        self.assertEqual(len(hud.death_button_rects), 2)
        self.assertEqual(hud.death_options, ("Exit", "Revive"))
        hud.death_selection = 1
        hud.activate_death_option()
        self.assertTrue(player.is_alive)

    def test_combat_equipment_uses_authored_tool_slot_icons(self):
        self.assertIsNone(self.assets.default_character_customization["weapon"])
        self.assertIsNone(self.assets.default_character_customization["offhand"])
        for name in ("sword", "spear", "shield"):
            with self.subTest(icon=name):
                self.assertEqual(load_item_icon(name, (48, 48)).get_size(), (48, 48))

    def test_one_shot_effect_removes_itself_after_last_frame(self):
        effects = EffectsManager()
        spec = effects.library.specs["sand"]
        effects.spawn("sand", (10, 10), variant=0)

        effects.update((spec.frame_count + 1) / spec.fps)

        self.assertEqual(effects.active, [])

    def test_effect_update_does_not_emit_a_player_foot_particle(self):
        player = type(
            "MovingPlayer",
            (),
            {"is_alive": True, "center": (10, 10)},
        )()
        effects = EffectsManager()

        effects.update(0.25, player=player)

        self.assertEqual(effects.active, [])

    def test_bush_hay_and_weed_particles_emit_on_contact_entry(self):
        props = {}
        for index, prop_type in enumerate(("bush", "hay", "weed")):
            prop = type(
                "ContactProp",
                (),
                {
                    "prop_id": f"contact-{index}",
                    "prop_type": prop_type,
                    "alive": True,
                    "rect": pygame.Rect(8, 8, 12, 12),
                },
            )()
            props[prop.prop_id] = prop
        chunk = type("Chunk", (), {"runtime": {"environment_objects": props}})()
        world = type("World", (), {"loaded_chunks": {(0, 0): chunk}})()
        player = type(
            "Player",
            (),
            {
                "is_alive": True,
                "center": (12, 12),
                "feet_collision_box": pygame.Rect(10, 10, 8, 8),
            },
        )()
        effects = EffectsManager()

        effects.update(0, player=player, world=world)
        first_burst_count = len(effects.active)
        counts = Counter(effect.name for effect in effects.active)
        self.assertEqual(set(counts), {"bush", "hay", "grass"})
        self.assertTrue(all(3 <= count <= 5 for count in counts.values()))
        self.assertTrue(all(effect.velocity.length_squared() > 0 for effect in effects.active))
        self.assertTrue(all(effect.fade for effect in effects.active))

        effects.update(0, player=player, world=world)
        self.assertEqual(len(effects.active), first_burst_count)

        player.feet_collision_box.topleft = (100, 100)
        effects.update(0, player=player, world=world)
        player.feet_collision_box.topleft = (10, 10)
        effects.update(0, player=player, world=world)
        self.assertGreaterEqual(len(effects.active), first_burst_count + 9)
        self.assertLessEqual(len(effects.active), first_burst_count + 15)

        effects.update(1.1, player=player, world=world)
        self.assertEqual(effects.active, [])

    def test_combat_tools_are_one_each_and_drive_equipment_layers(self):
        player = Player.__new__(Player)
        player.assets = self.assets
        player.customization = dict(self.assets.default_character_customization)
        player.tools = [
            "hoe", "axe", "pickaxe", "shovel", "water", "fishing rod",
            "sword", "spear", "shield",
        ]
        player.status = "down_idle"
        player.visual_scale = 1
        player.frames = self.assets.get_character_frames(player.status, player.customization)
        player.index = 0
        player.image_base = player.frames[0]
        player.image = player.image_base.copy()
        player.opacity = 255
        player.anchor = "midbottom"
        player.rect = player.image.get_rect(midbottom=(100, 100))

        self.assertEqual(player.tools.count("sword"), 1)
        self.assertEqual(player.tools.count("spear"), 1)
        self.assertEqual(player.tools.count("shield"), 1)

        player.selected_tool = "sword"
        player._sync_equipped_tool()
        self.assertTrue(player.has_equipped_weapon("sword"))
        self.assertFalse(player.has_equipped_weapon("shield"))
        self.assertEqual(player.customization["weapon"], "sword")
        self.assertIsNone(player.customization["offhand"])

        player.selected_tool = "spear"
        player._sync_equipped_tool()
        self.assertTrue(player.has_equipped_weapon("spear"))
        self.assertFalse(player.has_equipped_weapon("sword"))

        player.selected_tool = "shield"
        player._sync_equipped_tool()
        self.assertTrue(player.has_equipped_weapon("shield"))
        self.assertIsNone(player.customization["weapon"])
        self.assertEqual(player.customization["offhand"], "shield")


if __name__ == "__main__":
    unittest.main()
