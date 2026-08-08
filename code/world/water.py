"""Water world objects."""

import pygame

from sprites import AnimatedWorldObject


DEFAULT_WATER_ANIMATION_SPEED = 4.0


class WaterTile(AnimatedWorldObject):
    def __init__(self, world_pos, tile_size, frames, animation_speed=DEFAULT_WATER_ANIMATION_SPEED):
        scaled_frames = [pygame.transform.scale(frame, (tile_size, tile_size)) for frame in frames]
        super().__init__(
            pos=world_pos,
            frames=scaled_frames,
            anchor="topleft",
            animation_speed=animation_speed,
            loop=True,
        )
        self.render_layer = "ground"

    @property
    def sort_y(self):
        return self.rect.bottom
