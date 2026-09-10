import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODE_DIR = os.path.join(ROOT_DIR, "code")
if CODE_DIR not in sys.path:
    sys.path.insert(0, CODE_DIR)

import pygame

from gameplay.controls import (
    AXIS_INVENTORY,
    BUTTON_ATTACK,
    BUTTON_DODGE,
    BUTTON_GUARD,
    BUTTON_SPECIAL,
    ControllerInput,
)


class StubController:
    def __init__(self):
        self.closed = False

    def quit(self):
        self.closed = True


class ControllerFallbackTests(unittest.TestCase):
    def test_face_buttons_are_mapped_to_combat(self):
        self.assertEqual(BUTTON_ATTACK, pygame.CONTROLLER_BUTTON_X)
        self.assertEqual(BUTTON_SPECIAL, pygame.CONTROLLER_BUTTON_Y)
        self.assertEqual(BUTTON_GUARD, pygame.CONTROLLER_BUTTON_A)
        self.assertEqual(BUTTON_DODGE, pygame.CONTROLLER_BUTTON_B)

    def test_r2_inventory_axis_only_fires_on_press_edge(self):
        controls = ControllerInput.__new__(ControllerInput)
        controls._trigger_axis_state = {}

        released = pygame.event.Event(
            pygame.CONTROLLERAXISMOTION,
            axis=AXIS_INVENTORY,
            value=-32768,
        )
        pressed = pygame.event.Event(
            pygame.CONTROLLERAXISMOTION,
            axis=AXIS_INVENTORY,
            value=32767,
        )

        self.assertFalse(controls.is_axis_pressed(released, AXIS_INVENTORY))
        self.assertTrue(controls.is_axis_pressed(pressed, AXIS_INVENTORY))
        self.assertFalse(controls.is_axis_pressed(pressed, AXIS_INVENTORY))
        self.assertFalse(controls.is_axis_pressed(released, AXIS_INVENTORY))
        self.assertTrue(controls.is_axis_pressed(pressed, AXIS_INVENTORY))

    def test_stale_sdl_event_closes_controller_and_returns_empty_batch(self):
        controls = ControllerInput.__new__(ControllerInput)
        controls.controller = StubController()

        with patch("gameplay.controls.pygame.event.get", side_effect=SystemError("stale device")):
            events = controls.get_events()

        self.assertEqual(events, ())
        self.assertIsNone(controls.controller)


if __name__ == "__main__":
    unittest.main()
