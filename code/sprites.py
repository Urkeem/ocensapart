"""Shared sprite-sheet loaders and base drawable object classes."""

from core.settings import *
from utils import rp


class SpriteSheet:
    def __init__(self, *filename):
        """Load the spritesheet image"""
        self.spritesheet = pygame.image.load(rp(*filename)).convert_alpha()

    def get_sprite(self, x, y, width, height):
        """Extract a sprite from the spritesheet"""
        sprite = pygame.Surface((width, height), pygame.SRCALPHA)
        sprite.blit(self.spritesheet, (0, 0), (x, y, width, height))
        return sprite


class TileMapSpriteSheet:
    def __init__(self, *filename):
        self.spritesheet = pygame.image.load(rp(*filename)).convert_alpha()

    def get_sprite(self, tile_x, tile_y, width, height):
        sprite = pygame.Surface((width, height), pygame.SRCALPHA)
        sprite.blit(
            self.spritesheet,
            (0, 0),
            (tile_x * width, tile_y * height, width, height)
        )
        return sprite


class WorldObject:
    def __init__(self, pos, surf, anchor="midbottom", opacity=255, fade_rate=600):
        self.name = ""
        self.image_base = surf.convert_alpha()
        self.image = self.image_base.copy()

        self.opacity = int(opacity)
        self.target_opacity = int(opacity)
        self.fade_rate = float(fade_rate)
        self.image.set_alpha(self.opacity)

        self.anchor = anchor
        self.rect = self._make_rect(pos)
        self.mask = pygame.mask.from_surface(self.image_base)
        self.collision_box = self.rect.copy()

    def _make_rect(self, pos):
        if self.anchor == "center":
            return self.image.get_rect(center=pos)
        elif self.anchor == "topleft":
            return self.image.get_rect(topleft=pos)
        elif self.anchor == "midleft":
            return self.image.get_rect(midleft=pos)
        return self.image.get_rect(midbottom=pos)

    @property
    def sort_y(self):
        return self.rect.bottom

    def _refresh_image(self):
        anchor_value = getattr(self.rect, self.anchor)
        self.image = self.image_base.copy()
        self.image.set_alpha(int(self.opacity))
        self.rect = self._make_rect(anchor_value)

    def set_target_opacity(self, alpha):
        self.target_opacity = max(0, min(255, int(alpha)))

    def tick_opacity(self, dt):
        if self.opacity == self.target_opacity:
            return
        step = self.fade_rate * dt
        if self.opacity < self.target_opacity:
            self.opacity = min(self.opacity + step, self.target_opacity)
        else:
            self.opacity = max(self.opacity - step, self.target_opacity)
        self.image.set_alpha(int(self.opacity))

    def update(self, dt):
        self.tick_opacity(dt)


class AnimatedWorldObject(WorldObject):
    def __init__(self, pos, frames, anchor="midbottom", animation_speed=6, loop=True, opacity=255, fade_rate=600):
        self.frames = [frame.convert_alpha() for frame in frames]
        self.index = 0
        self.animation_speed = animation_speed
        self.loop = loop
        self.animation_finished = False

        super().__init__(pos, self.frames[0], anchor=anchor, opacity=opacity, fade_rate=fade_rate)

    def animate(self, dt):
        if self.animation_finished and not self.loop:
            return

        self.index += self.animation_speed * dt

        if self.loop:
            if self.index >= len(self.frames):
                self.index = 0
        else:
            if self.index >= len(self.frames):
                self.index = len(self.frames) - 1
                self.animation_finished = True

        self.image_base = self.frames[int(self.index)]
        self._refresh_image()
        self.mask = pygame.mask.from_surface(self.image_base)

    def update(self, dt):
        self.animate(dt)
        self.tick_opacity(dt)


