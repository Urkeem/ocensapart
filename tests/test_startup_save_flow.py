"""Boot splash, unified setup, and save-name interaction tests."""

import os
import sys
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame


CODE_ROOT = Path(__file__).resolve().parents[1] / "code"
if str(CODE_ROOT) not in sys.path:
    sys.path.insert(0, str(CODE_ROOT))

from gameplay.savegame import SaveGameManager
from gameplay.startup import StartupFlow
from ui.save_dialog import SaveNameDialog


class StartupSaveFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((1280, 720))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_boot_splash_opens_the_single_setup_hub(self):
        flow = StartupFlow(self.screen)
        self.assertEqual(flow.stage, "boot")
        flow.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r"))
        self.assertEqual(flow.stage, "setup")
        self.assertEqual(
            flow.setup_rows,
            ("mode", "seed", "skin", "clothes", "hair", "start", "saves", "load", "settings", "quit"),
        )
        flow.draw()
        self.assertTrue({"mode", "seed", "skin", "clothes", "hair", "start", "load"}.issubset(flow.setup_hitboxes))

    def test_setup_edits_mode_seed_and_customization_without_changing_screen(self):
        flow = StartupFlow(self.screen)
        flow.open_setup()
        flow.setup_focus = flow.setup_rows.index("mode")
        flow.change_setup_value(1)
        self.assertEqual(flow.selected_mode, "story")
        flow.setup_focus = flow.setup_rows.index("seed")
        flow.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_4, unicode="4"))
        self.assertEqual(flow.seed_text, "4")
        flow.setup_focus = flow.setup_rows.index("skin")
        original = flow.customization["skin"]
        flow.change_setup_value(1)
        self.assertEqual(flow.stage, "setup")
        self.assertIn(flow.customization["skin"], flow.get_customization_options("skin"))
        self.assertEqual(original, flow.customization["skin"])

    def test_save_dialog_uses_automatic_name_when_left_blank(self):
        with tempfile.TemporaryDirectory() as folder:
            manager = SaveGameManager(save_directory=folder)
            dialog = SaveNameDialog(self.screen, manager)
            dialog.open()
            self.assertEqual(dialog.suggestion, "save_1")
            result = dialog.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r")
            )
            self.assertEqual(result, ("save", "save_1"))

    def test_save_dialog_accepts_an_edited_name(self):
        with tempfile.TemporaryDirectory() as folder:
            dialog = SaveNameDialog(self.screen, SaveGameManager(save_directory=folder))
            dialog.open()
            dialog.handle_event(pygame.event.Event(pygame.TEXTINPUT, text="Cure Run"))
            result = dialog.handle_event(
                pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN, unicode="\r")
            )
            self.assertEqual(result, ("save", "Cure Run"))


if __name__ == "__main__":
    unittest.main()
