"""Game time, seasonal changes, weather state, and weather particles."""

import random

import pygame

from core.support import import_folder
from utils import rp


class GameTime:
    def __init__(self):
        self.time = 360.0
        self.day_length = 1440
        self.real_seconds_per_game_hour = 10
        self.minute_speed = 60 / self.real_seconds_per_game_hour
        self.day = 1
        self.hours = 6
        self.minutes = 0

    def update(self, dt):
        self.time += self.minute_speed * dt
        if self.time >= self.day_length:
            self.time -= self.day_length
            self.day += 1
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
    def __init__(self, image, pos, velocity, lifetime):
        self.image = image
        self.pos = pygame.Vector2(pos)
        self.velocity = pygame.Vector2(velocity)
        self.lifetime = lifetime
        self.age = 0.0
        self.rect = self.image.get_rect(topleft=pos)

    def update(self, dt):
        self.age += dt
        self.pos += self.velocity * dt
        self.rect.topleft = (round(self.pos.x), round(self.pos.y))

    @property
    def alive(self):
        return self.age < self.lifetime


class WeatherSystem:
    def __init__(self, screen_size):
        self.screen_w, self.screen_h = screen_size
        self.time = GameTime()
        self.seasons = SeasonCycle(self.time.day)
        self.particles = []
        self.rain_drops = import_folder("graphics", "rain", "drops")
        self.rain_floor = import_folder("graphics", "rain", "floor")
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 22)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 18)
        self._soil_water_timer = 0.0

    @property
    def weather(self):
        return self.seasons.weather

    @property
    def current_season(self):
        return self.seasons.current_season

    def resize(self, screen_size):
        self.screen_w, self.screen_h = screen_size

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
        if self.weather == "Rainy":
            self.spawn_rain(dt)
        elif self.weather == "Snowy":
            self.spawn_snow(dt)
        elif self.weather == "Windy":
            self.spawn_wind(dt)
        elif self.weather == "Cloudy":
            self.spawn_clouds(dt)

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
        if self.rain_floor and self.should_spawn(18, dt):
            image = random.choice(self.rain_floor)
            image = pygame.transform.scale(image, (max(2, image.get_width() * 2), image.get_height()))
            speed_x = random.randint(-420, -260)
            self.particles.append(
                WeatherParticle(
                    image,
                    (self.screen_w + 30, random.randint(0, self.screen_h)),
                    (speed_x, random.randint(-25, 25)),
                    (self.screen_w + image.get_width() + 120) / abs(speed_x),
                )
            )

    def spawn_clouds(self, dt):
        if self.rain_floor and self.should_spawn(8, dt):
            image = random.choice(self.rain_floor).copy()
            image.set_alpha(90)
            speed_x = random.randint(-80, -35)
            self.particles.append(
                WeatherParticle(
                    image,
                    (self.screen_w + 30, random.randint(0, int(self.screen_h * 0.55))),
                    (speed_x, 0),
                    (self.screen_w + image.get_width() + 120) / abs(speed_x),
                )
            )

    def draw(self, screen):
        for particle in self.particles:
            screen.blit(particle.image, particle.rect)

        self.draw_tint(screen)
        self.draw_status(screen)

    def draw_tint(self, screen):
        tint = pygame.Surface((self.screen_w, self.screen_h), pygame.SRCALPHA)
        tint_color = self.get_tint_color()
        tint.fill(tint_color)
        screen.blit(tint, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

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
        panel = pygame.Surface((210, 66), pygame.SRCALPHA)
        panel.fill((12, 18, 29, 170))
        screen.blit(panel, (12, 118))

        title = self.font.render(f"{self.time.formatted()}  {self.weather}", True, (236, 240, 245))
        subtitle = self.small_font.render(
            f"{self.current_season} Day {self.time.day}",
            True,
            (190, 204, 214),
        )
        screen.blit(title, (24, 126))
        screen.blit(subtitle, (24, 154))
