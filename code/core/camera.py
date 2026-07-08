"""Camera transforms and viewport-aware world rendering utilities."""

import pygame

class Camera:
    def __init__(self, width, height, world_width=None, world_height=None, zoom=1.0, mode="follow"):
        self.width = width
        self.height = height
        self.world_width = world_width
        self.world_height = world_height
        self.offset = pygame.Vector2(0, 0)
        self.zoom = zoom
        self.mode = mode
        self.edge_margin_ratio = 0.30

    def update(self, target):
        visible_w = self.width / self.zoom
        visible_h = self.height / self.zoom

        if self.mode == "edge":
            margin_x = visible_w * self.edge_margin_ratio
            margin_y = visible_h * self.edge_margin_ratio
            target_screen_x = target.rect.centerx - self.offset.x
            target_screen_y = target.rect.centery - self.offset.y

            target_x = self.offset.x
            target_y = self.offset.y

            if target_screen_x < margin_x:
                target_x = target.rect.centerx - margin_x
            elif target_screen_x > visible_w - margin_x:
                target_x = target.rect.centerx - (visible_w - margin_x)

            if target_screen_y < margin_y:
                target_y = target.rect.centery - margin_y
            elif target_screen_y > visible_h - margin_y:
                target_y = target.rect.centery - (visible_h - margin_y)
        else:
            target_x = target.rect.centerx - visible_w / 2
            target_y = target.rect.centery - visible_h / 2

        self.offset.x += (target_x - self.offset.x) * 0.1
        self.offset.y += (target_y - self.offset.y) * 0.1

        if self.world_width is not None and self.world_height is not None:
            max_x = max(0, self.world_width - visible_w)
            max_y = max(0, self.world_height - visible_h)

            self.offset.x = max(0, min(self.offset.x, max_x))
            self.offset.y = max(0, min(self.offset.y, max_y))

    def apply_point(self, x, y):
        screen_x = (x - self.offset.x) * self.zoom
        screen_y = (y - self.offset.y) * self.zoom
        return int(screen_x), int(screen_y)

    def apply_rect(self, rect):
        x, y = self.apply_point(rect.x, rect.y)
        w = max(1, int(rect.width * self.zoom))
        h = max(1, int(rect.height * self.zoom))
        return pygame.Rect(x, y, w, h)

    def apply(self, rect):
        return self.apply_rect(rect)

    def zoom_in(self, amount=0.1):
        self.zoom = min(4.0, self.zoom + amount)

    def zoom_out(self, amount=0.1):
        self.zoom = max(0.5, self.zoom - amount)


class WorldRenderer:
    def __init__(self, screen, camera):
        self.screen = screen
        self.camera = camera

    def draw_ground(self, ground_sprites):
        for sprite in ground_sprites:
            dest_rect = self.camera.apply_rect(sprite.rect)
            scaled = pygame.transform.scale(sprite.image, dest_rect.size)
            self.screen.blit(scaled, dest_rect.topleft)

    def draw_y_sorted(self, sprites):
        for sprite in sorted(sprites, key=lambda s: getattr(s, "sort_y", s.rect.bottom)):
            dest_rect = self.camera.apply_rect(sprite.rect)
            scaled = pygame.transform.scale(sprite.image, dest_rect.size)
            self.screen.blit(scaled, dest_rect.topleft)
