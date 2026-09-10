"""Weather-folder and animated wind spritesheet tests."""

import os
import sys
import unittest
from unittest.mock import patch
from pathlib import Path


os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "code"))

from world.weather import (
    SUMMER_PARTICLE_ANIMATION_FPS,
    SUMMER_PARTICLE_FRAME_COUNT,
    WIND_ANIMATION_FPS,
    WIND_FRAME_COUNT,
    WeatherParticle,
    WeatherSystem,
)


class WeatherAssetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_weather_system_loads_relocated_assets_and_all_wind_frames(self):
        weather = WeatherSystem((320, 180))

        self.assertEqual(len(weather.wind_frames), WIND_FRAME_COUNT)
        self.assertTrue(all(frame.get_size() == (288, 64) for frame in weather.wind_frames))
        self.assertTrue(weather.cloud_surfs)
        self.assertTrue(weather.rain_drops)
        self.assertTrue(weather.rain_floor)

    def test_weather_particle_advances_wind_animation(self):
        frames = tuple(
            pygame.Surface((8, 8), pygame.SRCALPHA)
            for _ in range(WIND_FRAME_COUNT)
        )
        particle = WeatherParticle(
            frames[0],
            (0, 0),
            (0, 0),
            10,
            "wind",
            frames=frames,
            animation_fps=WIND_ANIMATION_FPS,
        )

        particle.update(1 / WIND_ANIMATION_FPS)

        self.assertIs(particle.image, frames[1])

    def test_summer_sunny_particles_use_native_environment_frames(self):
        weather = WeatherSystem((320, 180))

        self.assertEqual(len(weather.summer_leaf_frames), SUMMER_PARTICLE_FRAME_COUNT)
        self.assertEqual(len(weather.summer_petal_frames), SUMMER_PARTICLE_FRAME_COUNT)
        self.assertTrue(
            all(frame.get_size() == (26, 20) for frame in weather.summer_leaf_frames)
        )
        self.assertTrue(
            all(frame.get_size() == (18, 16) for frame in weather.summer_petal_frames)
        )

        weather.seasons.current_season = "Summer"
        weather.seasons.weather = "Sunny"
        weather.should_spawn = lambda rate, dt: True
        with patch("world.weather.random.randrange", return_value=3):
            weather.spawn_weather_particles(1 / 60)

        self.assertEqual(len(weather.particles), 1)
        particle = weather.particles[0]
        self.assertEqual(particle.particle_type, "summer_sunny")
        self.assertEqual(particle.start_frame, 3)
        self.assertIs(particle.image, particle.frames[3])
        self.assertIn(particle.image.get_size(), {(26, 20), (18, 16)})

        full_crossing_lifetime = (
            weather.screen_h + particle.image.get_height() + 40
        ) / particle.velocity.y
        self.assertLess(particle.lifetime, full_crossing_lifetime)

        particle.update(1 / SUMMER_PARTICLE_ANIMATION_FPS)
        self.assertIs(particle.image, particle.frames[3])
        particle.update(1.0)
        self.assertIs(particle.image, particle.frames[3])


if __name__ == "__main__":
    unittest.main()
