"""Shared sleep, exhaustion, and combat-defeat recovery transition."""

from __future__ import annotations

import pygame

from gameplay.events import PlayerCollapsed, PlayerSlept
from gameplay.stamina import MAX_AWAKE_GAME_MINUTES
from utils import rp


RECOVERY_FADE_SECONDS = 0.7
RECOVERY_STAMINA = 75.0
RECOVERY_FEE_PERCENT = 0.10
RECOVERY_FEE_MINIMUM = 5
RECOVERY_FEE_CAP = 100
MORNING_MINUTES = 6 * 60


def recovery_fee(coins: int) -> int:
    coins = max(0, int(coins))
    if coins == 0:
        return 0
    return min(coins, RECOVERY_FEE_CAP, max(RECOVERY_FEE_MINIMUM, round(coins * RECOVERY_FEE_PERCENT)))


class RecoverySystem:
    def __init__(self, screen, player, game_state, weather, soil_layer, location_manager, dispatcher=None):
        self.screen = screen
        self.player = player
        self.game_state = game_state
        self.weather = weather
        self.soil_layer = soil_layer
        self.location_manager = location_manager
        self.dispatcher = dispatcher
        self.phase = "idle"
        self.reason = None
        self.timer = 0.0
        self.last_fee = 0
        self.font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 38)
        self.small_font = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 22)

    @property
    def active(self):
        return self.phase != "idle"

    def request(self, reason: str):
        if self.active:
            return False
        self.last_fee = 0
        self.reason = str(reason)
        self.phase = "fade_out"
        self.timer = 0.0
        self.player.recovery_active = True
        self.player.direction.update(0, 0)
        self.player.inventory.is_inv = False
        return True

    def sleep(self):
        return self.request("sleep")

    def _advance_to_morning(self):
        game_time = self.weather.time
        game_time.advance_to_next_morning(MORNING_MINUTES)
        self.weather.seasons.update(game_time.day, game_time.hours)
        if self.soil_layer is not None:
            self.soil_layer._last_update_bucket = None
            self.soil_layer.update(0, game_time)

    def _complete_transition(self):
        self._advance_to_morning()
        is_sleep = self.reason == "sleep"
        self.last_fee = 0 if is_sleep else recovery_fee(self.player.coins)
        if self.last_fee:
            self.player.spend_coins(self.last_fee)
        self.player.revive()
        self.player.health = self.player.max_health if is_sleep else max(1, round(self.player.max_health * 0.75))
        self.game_state.stamina = self.game_state.max_stamina if is_sleep else min(self.game_state.max_stamina, RECOVERY_STAMINA)
        self.game_state.awake_game_minutes = 0.0
        self.location_manager.send_to_recovery_spawn()
        if self.dispatcher is not None:
            if is_sleep:
                event = PlayerSlept(
                    event_id=self.game_state.next_event_id("player_slept"),
                    day=self.weather.time.day,
                )
            else:
                event = PlayerCollapsed(
                    event_id=self.game_state.next_event_id("player_collapsed"),
                    reason=self.reason,
                )
            self.dispatcher.publish(event)

    def update(self, dt):
        if not self.active:
            if self.player.health <= 0:
                self.request("defeat")
            elif self.game_state.awake_game_minutes >= MAX_AWAKE_GAME_MINUTES:
                self.request("awake_limit")
            elif self.game_state.stamina <= 0:
                self.request("exhaustion")
            return
        self.timer += max(0.0, float(dt))
        if self.phase == "fade_out" and self.timer >= RECOVERY_FADE_SECONDS:
            self._complete_transition()
            self.phase = "fade_in"
            self.timer = 0.0
        elif self.phase == "fade_in" and self.timer >= RECOVERY_FADE_SECONDS:
            self.phase = "idle"
            self.timer = 0.0
            self.player.recovery_active = False

    def draw(self):
        if not self.active:
            return
        progress = min(1.0, self.timer / RECOVERY_FADE_SECONDS)
        alpha = round(255 * (progress if self.phase == "fade_out" else 1.0 - progress))
        overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
        overlay.fill((4, 6, 11, alpha))
        self.screen.blit(overlay, (0, 0))
        if alpha < 130:
            return
        messages = {
            "sleep": "A new morning begins",
            "defeat": "You recover at home",
            "exhaustion": "You passed out from exhaustion",
            "awake_limit": "Two sleepless days caught up with you",
        }
        title = self.font.render(messages.get(self.reason, "You recover at home"), True, (244, 235, 214))
        self.screen.blit(title, title.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 - 12)))
        if self.last_fee:
            fee = self.small_font.render(f"Recovery fee: {self.last_fee} coins", True, (224, 190, 106))
            self.screen.blit(fee, fee.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2 + 34)))
