"""Player combat input, hit resolution, combos, and radial comet attacks."""

from __future__ import annotations

import pygame

from gameplay.controls import BUTTON_ATTACK, BUTTON_DODGE, BUTTON_GUARD, BUTTON_SPECIAL


class CombatSystem:
    MELEE_RANGE = 92
    COMET_RADIUS = 210
    COMET_COOLDOWN = 3.0
    COMBO_WINDOW = 1.25

    def __init__(self, player, effects, npc_manager=None):
        self.player = player
        self.effects = effects
        self.npc_manager = npc_manager
        self.comet_cooldown = 0.0
        self.combo_timer = 0.0
        self.combo_count = 0
        self.slash_index = 0
        self.player.effect_manager = effects

    def set_npc_manager(self, npc_manager):
        self.npc_manager = npc_manager

    def reset_world(self):
        self.npc_manager = None
        self.combo_count = 0
        self.combo_timer = 0.0
        self.comet_cooldown = 0.0
        self.effects.clear()

    def _living_npcs(self):
        if self.npc_manager is None:
            return ()
        return tuple(
            npc
            for npc in self.npc_manager.npcs
            if getattr(npc, "is_alive", True)
        )

    def _in_front_of_player(self, target):
        origin = pygame.Vector2(self.player.feet_collision_box.center)
        delta = pygame.Vector2(target.rect.center) - origin
        if delta.length_squared() > self.MELEE_RANGE * self.MELEE_RANGE:
            return False
        if delta.length_squared() == 0:
            return True
        facing = pygame.Vector2(self.player.get_facing_offset())
        return delta.normalize().dot(facing) >= -0.05

    def _register_hit(self, target):
        self.combo_count = self.combo_count + 1 if self.combo_timer > 0 else 1
        self.combo_timer = self.COMBO_WINDOW
        if self.combo_count >= 3:
            self.effects.spawn(
                "confusion",
                target.rect.center,
                follow=target,
                offset=(0, -target.rect.height * 0.3),
            )
            self.combo_count = 0

    def melee_attack(self, action=None, damage=1):
        if not self.player.begin_combat_action(action or "sword_slash1", 0.42):
            return False
        targets = [target for target in self._living_npcs() if self._in_front_of_player(target)]
        if not targets:
            return True
        origin = pygame.Vector2(self.player.feet_collision_box.center)
        target = min(
            targets,
            key=lambda npc: origin.distance_squared_to(npc.rect.center),
        )
        if target.take_damage(damage, effects=self.effects, source=self.player):
            self._register_hit(target)
        return True

    def sword_attack(self):
        if not self.player.has_equipped_weapon("sword"):
            return False
        self.slash_index = 1 - self.slash_index
        return self.melee_attack(f"sword_slash{self.slash_index + 1}")

    def spear_attack(self):
        if not self.player.has_equipped_weapon("spear"):
            return False
        self.slash_index = 1 - self.slash_index
        return self.melee_attack(f"spear_thrust{self.slash_index + 1}")

    def shield_bash(self):
        if not self.player.has_equipped_weapon("shield"):
            return False
        return self.melee_attack("shield_bash", damage=1)

    def primary_attack(self):
        if self.player.has_equipped_weapon("sword"):
            return self.sword_attack()
        if self.player.has_equipped_weapon("spear"):
            return self.spear_attack()
        if self.player.has_equipped_weapon("shield"):
            return self.shield_bash()
        return False

    def dodge(self):
        weapon = getattr(self.player, "selected_tool", "")
        if weapon not in {"sword", "spear", "shield"}:
            return False
        action = "spear_dodge" if weapon == "spear" else "sword_dodge"
        if not self.player.begin_combat_action(action, 0.35):
            return False
        self.player.invulnerable_timer = max(self.player.invulnerable_timer, 0.35)
        return True

    def comet_attack(self):
        if (
            self.comet_cooldown > 0
            or not self.player.is_alive
            or not self.player.has_equipped_weapon("sword")
        ):
            return False
        origin = pygame.Vector2(self.player.center)
        targets = [
            npc
            for npc in self._living_npcs()
            if getattr(npc, "is_enemy", False)
            and origin.distance_squared_to(npc.rect.center)
            <= self.COMET_RADIUS * self.COMET_RADIUS
        ]
        if not targets or not self.player.begin_combat_action("sword_thrust", 0.55):
            return False

        self.effects.spawn("comet", origin)
        for target in targets:
            if target.take_damage(2, effects=self.effects, source=self.player):
                self._register_hit(target)
        self.comet_cooldown = self.COMET_COOLDOWN
        return True

    def handle_event(self, event):
        if self.player.inventory.is_inv or getattr(self.player, "dialogue_active", False):
            return False
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_f:
                return self.primary_attack()
            if event.key == pygame.K_g:
                return self.shield_bash()
            if event.key == pygame.K_r:
                return self.comet_attack()
            if event.key == pygame.K_h:
                return self.dodge()
        if event.type == pygame.CONTROLLERBUTTONDOWN:
            if event.button == BUTTON_ATTACK:
                return self.primary_attack()
            if event.button == BUTTON_GUARD:
                return self.shield_bash()
            if event.button == BUTTON_SPECIAL:
                return self.comet_attack()
            if event.button == BUTTON_DODGE:
                return self.dodge()
        return False

    def update(self, dt):
        self.comet_cooldown = max(0.0, self.comet_cooldown - dt)
        self.combo_timer = max(0.0, self.combo_timer - dt)
        if self.combo_timer <= 0:
            self.combo_count = 0
