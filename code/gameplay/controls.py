"""SDL game-controller discovery and shared PlayStation-style input state."""

from __future__ import annotations

import pygame
from pygame._sdl2 import controller as sdl_controller


CONTROLLER_DEADZONE = 0.20

# SDL uses Xbox-style names for standardized button positions. On a
# PlayStation controller these positions are Cross, Circle, Square, Triangle.
BUTTON_CONFIRM = pygame.CONTROLLER_BUTTON_A
BUTTON_CANCEL = pygame.CONTROLLER_BUTTON_B
BUTTON_TOOL = pygame.CONTROLLER_BUTTON_X
BUTTON_TOOL_NEXT = pygame.CONTROLLER_BUTTON_LEFTSHOULDER
BUTTON_SEED_NEXT = pygame.CONTROLLER_BUTTON_RIGHTSHOULDER
BUTTON_ATTACK = pygame.CONTROLLER_BUTTON_X
BUTTON_SPECIAL = pygame.CONTROLLER_BUTTON_Y
BUTTON_GUARD = pygame.CONTROLLER_BUTTON_A
BUTTON_DODGE = pygame.CONTROLLER_BUTTON_B
AXIS_INVENTORY = pygame.CONTROLLER_AXIS_TRIGGERRIGHT
BUTTON_DPAD_UP = pygame.CONTROLLER_BUTTON_DPAD_UP
BUTTON_DPAD_DOWN = pygame.CONTROLLER_BUTTON_DPAD_DOWN
BUTTON_DPAD_LEFT = pygame.CONTROLLER_BUTTON_DPAD_LEFT
BUTTON_DPAD_RIGHT = pygame.CONTROLLER_BUTTON_DPAD_RIGHT


class ControllerInput:
    """Own the primary SDL-mapped controller and survive hot-plug events."""

    def __init__(self, deadzone=CONTROLLER_DEADZONE):
        self.deadzone = max(0.0, min(0.95, float(deadzone)))
        self.controller = None
        self._menu_axis_state = {"x": 0, "y": 0}
        self._trigger_axis_state = {}
        sdl_controller.init()
        self.refresh()

    @property
    def connected(self):
        if self.controller is None:
            return False
        try:
            return bool(self.controller.attached())
        except (pygame.error, KeyError, SystemError):
            self.controller = None
            return False

    @property
    def name(self):
        if not self.connected:
            return ""
        try:
            return self.controller.name
        except (pygame.error, KeyError, SystemError):
            self.close()
            return ""

    def close(self):
        if self.controller is not None:
            try:
                self.controller.quit()
            except (pygame.error, KeyError, SystemError):
                pass
        self.controller = None
        trigger_states = getattr(self, "_trigger_axis_state", None)
        if trigger_states is not None:
            trigger_states.clear()

    def get_events(self):
        """Read pending events and degrade cleanly after an SDL device failure.

        Pygame 2.6 can expose a stale controller instance as ``KeyError`` and
        then wrap it in ``SystemError`` inside ``pygame.event.get``.  Closing
        our controller reference makes keyboard input and keyboard UI hints
        active immediately; a later DEVICEADDED event can reconnect a pad.
        """
        try:
            return pygame.event.get()
        except (KeyError, SystemError):
            self.close()
            return ()

    def refresh(self):
        if self.connected:
            return

        self.close()
        for device_index in range(sdl_controller.get_count()):
            if not sdl_controller.is_controller(device_index):
                continue
            try:
                self.controller = sdl_controller.Controller(device_index)
                return
            except (pygame.error, KeyError, SystemError):
                self.controller = None

    def handle_event(self, event):
        if event.type == pygame.CONTROLLERDEVICEADDED:
            self.refresh()
        elif event.type == pygame.CONTROLLERDEVICEREMOVED:
            if self.controller is not None:
                removed_id = getattr(event, "instance_id", None)
                try:
                    current_id = self.controller.id
                except (pygame.error, KeyError, SystemError):
                    current_id = None
                if removed_id is None or current_id is None or removed_id == current_id:
                    self.close()
        elif event.type == pygame.CONTROLLERDEVICEREMAPPED:
            self.refresh()

    def menu_navigation_button(self, event):
        """Convert a newly tilted left-stick axis into one D-pad-style press."""
        if event.type != pygame.CONTROLLERAXISMOTION:
            return None

        axis = getattr(event, "axis", None)
        if axis == pygame.CONTROLLER_AXIS_LEFTX:
            axis_name = "x"
            negative_button = BUTTON_DPAD_LEFT
            positive_button = BUTTON_DPAD_RIGHT
        elif axis == pygame.CONTROLLER_AXIS_LEFTY:
            axis_name = "y"
            negative_button = BUTTON_DPAD_UP
            positive_button = BUTTON_DPAD_DOWN
        else:
            return None

        value = getattr(event, "value", 0) / 32767.0
        direction = -1 if value < -0.65 else 1 if value > 0.65 else 0
        previous = self._menu_axis_state[axis_name]
        self._menu_axis_state[axis_name] = direction
        if direction == 0 or direction == previous:
            return None
        return negative_button if direction < 0 else positive_button

    def is_axis_pressed(self, event, axis, threshold=0.55):
        """Return once when an analog trigger crosses its press threshold."""
        if (
            event.type != pygame.CONTROLLERAXISMOTION
            or getattr(event, "axis", None) != axis
        ):
            return False

        # SDL controller triggers rest near -32768 and rise toward 32767.
        value = max(-1.0, min(1.0, getattr(event, "value", -32768) / 32767.0))
        pressed = value >= float(threshold)
        states = getattr(self, "_trigger_axis_state", None)
        if states is None:
            states = {}
            self._trigger_axis_state = states
        previous = states.get(axis, False)
        states[axis] = pressed
        return pressed and not previous

    def get_button(self, button):
        if not self.connected:
            return False
        try:
            return bool(self.controller.get_button(button))
        except (pygame.error, KeyError, SystemError):
            self.close()
            return False

    def get_axis(self, axis):
        if not self.connected:
            return 0.0
        try:
            value = self.controller.get_axis(axis)
        except (pygame.error, KeyError, SystemError):
            self.close()
            return 0.0
        return max(-1.0, min(1.0, value / 32767.0))

    def movement_vector(self):
        dpad = pygame.Vector2(
            int(self.get_button(BUTTON_DPAD_RIGHT))
            - int(self.get_button(BUTTON_DPAD_LEFT)),
            int(self.get_button(BUTTON_DPAD_DOWN))
            - int(self.get_button(BUTTON_DPAD_UP)),
        )
        if dpad.length_squared() > 0:
            return dpad.normalize()

        movement = pygame.Vector2(
            self.get_axis(pygame.CONTROLLER_AXIS_LEFTX),
            self.get_axis(pygame.CONTROLLER_AXIS_LEFTY),
        )
        magnitude = movement.length()
        if magnitude <= self.deadzone:
            return pygame.Vector2()

        scaled_magnitude = min(1.0, (magnitude - self.deadzone) / (1.0 - self.deadzone))
        return movement.normalize() * scaled_magnitude

    @staticmethod
    def is_button_down(event, button):
        return (
            event.type == pygame.CONTROLLERBUTTONDOWN
            and getattr(event, "button", None) == button
        )


_CONTROLLER_INPUT = None


def get_controller_input():
    global _CONTROLLER_INPUT
    if _CONTROLLER_INPUT is None:
        _CONTROLLER_INPUT = ControllerInput()
    return _CONTROLLER_INPUT
