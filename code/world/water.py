"""Water world objects."""

import pygame

from sprites import AnimatedWorldObject


DEFAULT_WATER_ANIMATION_SPEED = 4.0
_SCALED_WATER_FRAMES = {}


class WaterTile(AnimatedWorldObject):
    def __init__(self, world_pos, tile_size, frames, animation_speed=DEFAULT_WATER_ANIMATION_SPEED):
        frame_key = (tile_size, tuple(id(frame) for frame in frames))
        scaled_frames = _SCALED_WATER_FRAMES.get(frame_key)
        if scaled_frames is None:
            scaled_frames = tuple(
                pygame.transform.scale(frame, (tile_size, tile_size)).convert_alpha()
                for frame in frames
            )
            _SCALED_WATER_FRAMES[frame_key] = scaled_frames

        # Water is non-colliding and always fully opaque, so it does not need
        # WorldObject's per-instance image copies or per-frame mask rebuilds.
        self.frames = scaled_frames
        self.index = 0.0
        self.animation_speed = animation_speed
        self.loop = True
        self.animation_finished = False
        self.image_base = scaled_frames[0]
        self.image = self.image_base
        self.opacity = 255
        self.target_opacity = 255
        self.fade_rate = 0.0
        self.anchor = "topleft"
        self.rect = self.image.get_rect(topleft=world_pos)
        self.mask = None
        self.collision_box = pygame.Rect(0, 0, 0, 0)
        self.render_layer = "ground"

    def update(self, dt):
        self.index = (self.index + self.animation_speed * dt) % len(self.frames)
        self.image_base = self.frames[int(self.index)]
        self.image = self.image_base

    @property
    def sort_y(self):
        return self.rect.bottom
