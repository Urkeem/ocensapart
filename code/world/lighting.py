"""Cached world-space light glows for nighttime environment props."""

import pygame


class LightSystem:
    EVENING_START_MINUTES = 18 * 60
    MORNING_END_MINUTES = 7 * 60

    def __init__(self):
        self._glow_cache = {}

    @classmethod
    def is_active_at(cls, minutes):
        minutes = float(minutes) % 1440
        return (
            minutes >= cls.EVENING_START_MINUTES
            or minutes < cls.MORNING_END_MINUTES
        )

    def get_glow_surface(self, radius, color, intensity, zoom):
        zoom_key = round(float(zoom), 3)
        radius = max(1, int(radius))
        color = tuple(map(int, color[:3]))
        intensity = max(0, min(255, int(intensity)))
        cache_key = (radius, color, intensity, zoom_key)
        cached = self._glow_cache.get(cache_key)
        if cached is not None:
            return cached

        screen_radius = max(1, int(round(radius * zoom_key)))
        surface = pygame.Surface(
            (screen_radius * 2, screen_radius * 2),
            pygame.SRCALPHA,
        )
        center = (screen_radius, screen_radius)
        steps = min(64, screen_radius)
        intensity_scale = intensity / 255
        for step in range(steps, 0, -1):
            radius_fraction = step / steps
            falloff = (1 - radius_fraction) ** 2
            ring_color = tuple(
                int(channel * intensity_scale * falloff)
                for channel in color
            )
            ring_radius = max(1, round(screen_radius * radius_fraction))
            pygame.draw.circle(surface, (*ring_color, 255), center, ring_radius)

        self._glow_cache[cache_key] = surface
        return surface

    def draw(self, screen, light_sources, camera, game_time):
        minutes = getattr(game_time, "time", game_time)
        if not self.is_active_at(minutes):
            return 0

        drawn = 0
        screen_rect = screen.get_rect()
        for source in light_sources:
            if not getattr(source, "alive", True):
                continue
            if not getattr(source, "emits_light", False):
                continue

            glow = self.get_glow_surface(
                source.light_radius,
                source.light_color,
                source.light_intensity,
                camera.zoom,
            )
            center_x, center_y = camera.apply_point(*source.light_position)
            glow_rect = glow.get_rect(center=(center_x, center_y))
            if not glow_rect.colliderect(screen_rect):
                continue
            screen.blit(glow, glow_rect, special_flags=pygame.BLEND_RGB_ADD)
            drawn += 1
        return drawn
