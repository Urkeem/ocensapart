"""Player stamina, awake-time limits, sprint drain, and food recovery."""

from __future__ import annotations

from data.crops import CROP_DEFINITIONS
from data.items import TREE_FRUIT_STAMINA


MAX_AWAKE_GAME_MINUTES = 48 * 60
PASSIVE_STAMINA_PER_GAME_MINUTE = 100.0 / MAX_AWAKE_GAME_MINUTES
SPRINT_STAMINA_PER_REAL_SECOND = 0.8

ACTION_STAMINA_COSTS = {
    "till": 1.5,
    "water": 0.75,
    "plant": 0.5,
    "harvest": 0.5,
    "break": 1.5,
    "pickaxe": 2.0,
    "axe": 2.0,
    "fish": 1.5,
    "combat": 1.25,
}

FOOD_STAMINA = {
    "tomato": 5,
    "corn": 6,
    "apple": 10,
    "carrot": 7,
    "egg": 8,
    "fish": 12,
    "meat": 15,
    "stamina_potion": 30,
}

# Every harvested crop is edible. Hand-authored values above win; later crops
# scale gently with their farming reward so newly unlocked produce remains
# useful without replacing sleep as the main recovery loop.
for _crop in CROP_DEFINITIONS.values():
    FOOD_STAMINA.setdefault(_crop.id, max(4, min(12, 4 + _crop.harvest_points // 2)))
FOOD_STAMINA.update(TREE_FRUIT_STAMINA)


class StaminaSystem:
    def __init__(self, game_state, player):
        self.game_state = game_state
        self.player = player
        self.player.stamina_enabled = True

    def update(self, dt, game_time):
        if getattr(self.player, "recovery_active", False):
            return
        elapsed_game_minutes = max(0.0, float(game_time.minute_speed) * float(dt))
        self.game_state.awake_game_minutes = min(
            MAX_AWAKE_GAME_MINUTES,
            self.game_state.awake_game_minutes + elapsed_game_minutes,
        )
        drain = elapsed_game_minutes * PASSIVE_STAMINA_PER_GAME_MINUTE
        if getattr(self.player, "is_sprinting", False):
            drain += max(0.0, float(dt)) * SPRINT_STAMINA_PER_REAL_SECOND
        self.game_state.stamina = max(0.0, self.game_state.stamina - drain)

    @property
    def exhausted(self):
        return self.game_state.stamina <= 0

    @property
    def awake_limit_reached(self):
        return self.game_state.awake_game_minutes >= MAX_AWAKE_GAME_MINUTES
