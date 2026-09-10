"""Game time, seasonal changes, weather state, and weather particles."""

import random

import pygame

from core.support import import_folder
from utils import rp


GAME_MINUTES_PER_DAY = 24 * 60
REAL_SECONDS_PER_GAME_DAY = 15 * 60
WIND_FRAME_COUNT = 48
WIND_ANIMATION_FPS = 24
SUMMER_PARTICLE_FRAME_COUNT = 6
SUMMER_PARTICLE_ANIMATION_FPS = 12
SUMMER_PARTICLE_LIFETIME_SCALE = 0.65


def load_horizontal_frames(asset_path, frame_count):
    """Slice one horizontal spritesheet into equally sized animation frames."""
    sheet = pygame.image.load(rp(*asset_path)).convert_alpha()
    if frame_count <= 0 or sheet.get_width() % frame_count:
        raise ValueError(
            f"Weather sheet {asset_path!r} cannot be split into {frame_count} frames"
        )
    frame_width = sheet.get_width() // frame_count
    return tuple(
        sheet.subsurface(
            pygame.Rect(index * frame_width, 0, frame_width, sheet.get_height())
        ).copy()
        for index in range(frame_count)
    )


def load_weather_folder(*parts, legacy_parts=()):
    images = import_folder("graphics", "environment", "weather", *parts)
    if not images and legacy_parts:
        images = import_folder(*legacy_parts)
    return images


class GameTime:
    def __init__(self):
        self.time = 360.0
        self.day_length = GAME_MINUTES_PER_DAY
        self.real_seconds_per_game_day = REAL_SECONDS_PER_GAME_DAY
        self.real_seconds_per_game_hour = self.real_seconds_per_game_day / 24
        self.minute_speed = self.day_length / self.real_seconds_per_game_day
        self.day = 1
        self.hours = 6
        self.minutes = 0

    def update(self, dt):
        self.time += self.minute_speed * dt
        if self.time >= self.day_length:
            elapsed_days = int(self.time // self.day_length)
            self.time %= self.day_length
            self.day += elapsed_days
        self.hours = int(self.time // 60)
        self.minutes = int(self.time % 60)

    def formatted(self):
        return f"{self.hours:02}:{self.minutes:02}"


class SeasonCycle:
    WEATHER_TYPES_DAY = ["Windy", "Cloudy", "Rainy", "Sunny", "Snowy"]
    WEATHER_TYPES_NIGHT = ["Windy", "Cloudy", "Rainy", "Snowy"]
    WEATHER_WEIGHTS_DAY = {
        "Spring": [0.3, 0.1, 0.4, 0.2, 0.0],
        "Summer": [0.2, 0.1, 0.2, 0.5, 0.0],
        "Fall": [0.2, 0.3, 0.4, 0.1, 0.0],
        "Winter": [0.1, 0.2, 0.3, 0.1, 0.3],
    }
    WEATHER_WEIGHTS_NIGHT = {
        "Spring": [0.3, 0.1, 0.4, 0.0],
        "Summer": [0.2, 0.1, 0.2, 0.0],
        "Fall": [0.2, 0.3, 0.4, 0.0],
        "Winter": [0.1, 0.2, 0.3, 0.3],
    }

    def __init__(self, current_day=1):
        self.seasons = ["Spring", "Summer", "Fall", "Winter"]
        self.current_season_index = 1
        self.current_season = self.seasons[self.current_season_index]
        self.current_day = current_day
        self.season_start_day = current_day
        self.season_length = random.randint(3, 4)
        self.weather = "Sunny"
        self.weather_durations = [3, 4, 5, 6]
        self.weather_duration = random.choice(self.weather_durations)
        self.next_weather_hour = 6
        self.next_weather_time = self.next_weather_hour * 60
        self.weather_time_stamp = self.next_weather_time

    def update(self, day, hour):
        self.current_day = day
        if self.current_day - self.season_start_day >= self.season_length:
            self.current_season_index = (self.current_season_index + 1) % len(self.seasons)
            self.current_season = self.seasons[self.current_season_index]
            self.season_length = random.randint(3, 4)
            self.season_start_day = self.current_day

        if hour == self.next_weather_hour:
            self.pick_weather(hour)

    def pick_weather(self, hour):
        is_night = hour * 60 >= 1080
        weather_types = self.WEATHER_TYPES_NIGHT if is_night else self.WEATHER_TYPES_DAY
        weights_by_season = self.WEATHER_WEIGHTS_NIGHT if is_night else self.WEATHER_WEIGHTS_DAY
        weights = weights_by_season.get(self.current_season)
        if not weights:
            return

        self.weather = random.choices(weather_types, weights=weights, k=1)[0]
        next_hour = hour + self.weather_duration
        self.next_weather_hour = next_hour if next_hour < 24 else next_hour % 24
        self.weather_duration = random.choice(self.weather_durations)
        self.next_weather_time = self.next_weather_hour * 60
        self.weather_time_stamp = hour * 60


class WeatherParticle:
    def __init__(
        self,
        image,
        pos,
        velocity,
        lifetime,
        particle_type=None,
        *,
        frames=None,
        animation_fps=0,
        start_frame=0,
    ):
        self.frames = tuple(frames or ())
        self.animation_fps = float(animation_fps)
        self.start_frame = int(start_frame) % len(self.frames) if self.frames else 0
        self.image = self.frames[self.start_frame] if self.frames else image
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(velocity)
        self.lifetime = lifetime
        self.particle_type = particle_type
        self.age = 0.0
        self.rect = self.image.get_rect(topleft=pos)

    def update(self, dt):
        self.age += dt
        if self.frames and self.animation_fps > 0:
            frame_index = (
                self.start_frame + int(self.age * self.animation_fps)
            ) % len(self.frames)
            self.image = self.frames[frame_index]
        self.pos += self.velocity * dt
        self.rect = self.image.get_rect(
            topleft=(round(self.pos.x), round(self.pos.y))
        )

    @property
    def alive(self):
        return self.age < self.lifetime


class WeatherSystem:
    CLOUD_SCALE = 2
    CLOUD_MIN_VERTICAL_SPACING = 90
    CLOUD_SPAWN_INTERVAL = (0.8, 1.8)

    def __init__(self, screen_size):
        self.screen_w, self.screen_h = screen_size
        self.time = GameTime()
        self.seasons = SeasonCycle(self.time.day)
        self.particles = []
        self.rain_drops = load_weather_folder(
            "rain",
            "drops",
            legacy_parts=("graphics", "rain", "drops"),
        )
        self.rain_floor = load_weather_folder(
            "rain",
            "floor",
            legacy_parts=("graphics", "rain", "floor"),
        )
        self.cloud_surfs = load_weather_folder("Clouds")
        self.wind_frames = load_horizontal_frames(
            ("graphics", "environment", "weather", "wind", "wind.png"),
            WIND_FRAME_COUNT,
        )
        self.summer_leaf_frames = load_horizontal_frames(
            ("graphics", "effects", "particles", "environment", "leaf.png"),
            SUMMER_PARTICLE_FRAME_COUNT,
        )
        self.summer_petal_frames = load_horizontal_frames(
            ("graphics", "effects", "particles", "environment", "petal.png"),
            SUMMER_PARTICLE_FRAME_COUNT,
        )
        # Compatibility for code that previously treated wind as loose images.
        self.wind_surfs = self.wind_frames
        self.cloud_images = []
        for source in self.cloud_surfs or self.rain_floor:
            image = pygame.transform.scale(
                source,
                (
                    source.get_width() * self.CLOUD_SCALE,
                    source.get_height() * self.CLOUD_SCALE,
                ),
            )
            image.set_alpha(90)
            self.cloud_images.append(image)
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 22)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 18)
        self._tint_surface = pygame.Surface(screen_size).convert()
        self._tint_cache_key = None
        self._status_panel = pygame.Surface((210, 66), pygame.SRCALPHA)
        self._status_panel.fill((12, 18, 29, 170))
        self._status_cache_key = None
        self._status_title = None
        self._status_subtitle = None
        self._soil_water_timer = 0.0
        self._cloud_spawn_timer = 0.0

    @property
    def weather(self):
        return self.seasons.weather

    @property
    def current_season(self):
        return self.seasons.current_season

    def resize(self, screen_size):
        self.screen_w, self.screen_h = screen_size
        self._tint_surface = pygame.Surface(screen_size).convert()
        self._tint_cache_key = None

    def update(self, dt, soil_layer=None):
        self.time.update(dt)
        self.seasons.update(self.time.day, self.time.hours)
        self.spawn_weather_particles(dt)

        for particle in self.particles:
            particle.update(dt)
        self.particles = [
            particle for particle in self.particles
            if particle.alive
            and particle.rect.right > -80
            and particle.rect.left < self.screen_w + 80
            and particle.rect.top < self.screen_h + 80
        ]

        if soil_layer is not None and self.weather == "Rainy":
            self._soil_water_timer -= dt
            if self._soil_water_timer <= 0:
                soil_layer.water_loaded_soil(self.time)
                self._soil_water_timer = 2.0

    def spawn_weather_particles(self, dt):
        if self.current_season == "Summer" and self.weather == "Sunny":
            self.spawn_summer_sunny(dt)
        elif self.weather == "Rainy":
            self.spawn_rain(dt)
        elif self.weather == "Snowy":
            self.spawn_snow(dt)
        elif self.weather == "Windy":
            self.spawn_wind(dt)
        elif self.weather == "Cloudy":
            self.spawn_clouds(dt)

    def spawn_summer_sunny(self, dt):
        if not self.should_spawn(2.2, dt):
            return
        frames = random.choice((self.summer_leaf_frames, self.summer_petal_frames))
        start_frame = random.randrange(len(frames))
        image = frames[start_frame]
        velocity_y = random.randint(34, 62)
        full_crossing_lifetime = (
            self.screen_h + image.get_height() + 40
        ) / velocity_y
        self.particles.append(
            WeatherParticle(
                image,
                (random.randint(-20, self.screen_w + 20), -image.get_height() - 4),
                (random.randint(-28, 28), velocity_y),
                full_crossing_lifetime * SUMMER_PARTICLE_LIFETIME_SCALE,
                "summer_sunny",
                frames=frames,
                animation_fps=0,
                start_frame=start_frame,
            )
        )

    def should_spawn(self, rate_per_second, dt):
        return random.random() < rate_per_second * dt

    def spawn_rain(self, dt):
        if self.rain_drops and self.should_spawn(90, dt):
            image = random.choice(self.rain_drops)
            self.particles.append(
                WeatherParticle(
                    image,
                    (random.randint(-60, self.screen_w + 40), random.randint(-80, -10)),
                    (-360, 720),
                    random.uniform(0.55, 0.8),
                )
            )
        if self.rain_floor and self.should_spawn(36, dt):
            image = random.choice(self.rain_floor)
            self.particles.append(
                WeatherParticle(
                    image,
                    (random.randint(0, self.screen_w), random.randint(0, self.screen_h)),
                    (0, 0),
                    random.uniform(0.35, 0.55),
                )
            )

    def spawn_snow(self, dt):
        if self.rain_drops and self.should_spawn(45, dt):
            image = random.choice(self.rain_drops)
            self.particles.append(
                WeatherParticle(
                    image,
                    (random.randint(-20, self.screen_w + 20), random.randint(-60, -10)),
                    (random.randint(-45, 20), random.randint(85, 140)),
                    random.uniform(3.0, 4.5),
                )
            )

    def spawn_wind(self, dt):
        if self.wind_frames and self.should_spawn(1.5, dt):
            image = self.wind_frames[0]
            speed_x = random.randint(-420, -260)
            self.particles.append(
                WeatherParticle(
                    image,
                    (self.screen_w + 30, random.randint(0, self.screen_h)),
                    (speed_x, random.randint(-25, 25)),
                    (self.screen_w + image.get_width() + 120) / abs(speed_x),
                    "wind",
                    frames=self.wind_frames,
                    animation_fps=WIND_ANIMATION_FPS,
                )
            )

    def spawn_clouds(self, dt):
        if not self.cloud_images:
            return

        self._cloud_spawn_timer -= dt
        if self._cloud_spawn_timer > 0:
            return

        image = random.choice(self.cloud_images)
        y = self.pick_cloud_y(image.get_height())
        if y is None:
            self._cloud_spawn_timer = 0.35
            return

        speed_x = random.randint(-80, -35)
        self.particles.append(
            WeatherParticle(
                image,
                (self.screen_w + 30, y),
                (speed_x, 0),
                (self.screen_w + image.get_width() + 120) / abs(speed_x),
                "cloud",
            )
        )
        self._cloud_spawn_timer = random.uniform(*self.CLOUD_SPAWN_INTERVAL)

    def pick_cloud_y(self, cloud_height):
        max_y = max(0, self.screen_h - cloud_height)
        cloud_particles = [
            particle for particle in self.particles
            if particle.particle_type == "cloud"
        ]
        for _ in range(12):
            y = random.randint(0, max_y)
            center_y = y + cloud_height / 2
            has_space = all(
                abs(center_y - particle.rect.centery) >= self.CLOUD_MIN_VERTICAL_SPACING
                for particle in cloud_particles
            )
            if has_space:
                return y
        return None

    def draw(self, screen):
        self.draw_world_effects(screen)
        self.draw_status(screen)

    def draw_world_effects(self, screen):
        if self.particles:
            screen.blits([(particle.image, particle.rect) for particle in self.particles])

        self.draw_tint(screen)

    def draw_tint(self, screen):
        tint_cache_key = (int(self.time.time), self.weather)
        if tint_cache_key != self._tint_cache_key:
            self._tint_surface.fill(self.get_tint_color()[:3])
            self._tint_cache_key = tint_cache_key
        screen.blit(self._tint_surface, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def get_tint_color(self):
        minutes = self.time.time
        day_color = pygame.Vector3(255, 255, 255)
        night_color = pygame.Vector3(55, 62, 95)
        storm_color = pygame.Vector3(145, 180, 190)

        if 240 <= minutes < 420:
            progress = (minutes - 240) / 180
            color = night_color.lerp(day_color, progress)
        elif 420 <= minutes < 1080:
            color = day_color
        elif 1080 <= minutes < 1260:
            progress = (minutes - 1080) / 180
            color = day_color.lerp(night_color, progress)
        else:
            color = night_color

        if self.weather in {"Cloudy", "Rainy", "Snowy"} and 240 < minutes < 1080:
            color = color.lerp(storm_color, 0.28)

        return (*tuple(map(int, color)), 255)

    def draw_status(self, screen):
        screen.blit(self._status_panel, (12, 118))

        status_cache_key = (
            self.time.hours,
            self.time.minutes,
            self.weather,
            self.current_season,
            self.time.day,
        )
        if status_cache_key != self._status_cache_key:
            self._status_title = self.font.render(
                f"{self.time.formatted()}  {self.weather}",
                True,
                (236, 240, 245),
            )
            self._status_subtitle = self.small_font.render(
                f"{self.current_season} Day {self.time.day}",
                True,
                (190, 204, 214),
            )
            self._status_cache_key = status_cache_key

        screen.blit(self._status_title, (24, 126))
        screen.blit(self._status_subtitle, (24, 154))
