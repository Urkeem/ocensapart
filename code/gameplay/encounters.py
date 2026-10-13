"""Persistent encounter spawning, retries, wave completion, and combat rewards."""

from __future__ import annotations

import math
import pygame

from data.encounters import ENCOUNTER_DEFINITIONS
from data.locations import LOCATION_DEFINITIONS
from entities.enemy import Enemy, EnemyAnimationLibrary, EnemyProjectile
from gameplay.events import (
    EncounterCompleted,
    EncounterFailed,
    EncounterWaveCompleted,
    EnemyDefeated,
    EnemyLootGranted,
)
from inventory_item import Item


class EnemyLootPickup:
    """A saved encounter reward that remains in the world until collected."""

    managed_by_encounter = True
    is_enemy = False
    hostile = False
    faction = "loot"

    def __init__(self, record):
        from ui.inventory import load_item_icon

        self.drop_id = record["drop_id"]
        self.item_id = record["item_id"]
        self.count = max(1, int(record.get("count", 1)))
        self.encounter_id = record.get("encounter_id", "")
        self.location_id = record.get("location_id", "player_farm")
        self.pos = pygame.Vector2(record.get("position", (0, 0)))
        icon = load_item_icon(self.item_id, (34, 34))
        if not icon:
            icon = pygame.Surface((24, 24), pygame.SRCALPHA)
            pygame.draw.circle(icon, (238, 190, 68), (12, 12), 9)
        self.image = icon
        self.rect = self.image.get_rect(center=(round(self.pos.x), round(self.pos.y)))
        self.alive = True
        self._age = 0.0

    @property
    def center(self):
        return self.rect.center

    @property
    def sort_y(self):
        return self.rect.bottom

    @property
    def is_alive(self):
        return self.alive

    def update(self, dt):
        self._age += max(0.0, float(dt))
        bob = round(math.sin(self._age * 4.0) * 2)
        self.rect.center = (round(self.pos.x), round(self.pos.y) + bob)


class EncounterManager:
    """Run data-defined encounters while GameState owns their durable records."""

    def __init__(
        self,
        world,
        npc_manager,
        player,
        game_state,
        dispatcher,
        *,
        quest_system=None,
        effects=None,
        definitions=None,
        enemy_library=None,
    ):
        self.world = world
        self.npc_manager = npc_manager
        self.player = player
        self.game_state = game_state
        self.dispatcher = dispatcher
        self.quest_system = quest_system
        self.effects = effects
        self.definitions = ENCOUNTER_DEFINITIONS if definitions is None else definitions
        self.enemy_library = enemy_library or EnemyAnimationLibrary()
        self.enemies = []
        self.projectiles = []
        self.loot_pickups = []
        self._projectile_counter = 0
        self._ensure_records()
        self._restore_pending_loot()

    def _ensure_records(self):
        for definition in self.definitions.values():
            record = self.game_state.encounters.setdefault(definition.id, {})
            record.setdefault("definition_id", definition.id)
            record.setdefault("location_id", definition.location_id)
            record.setdefault("status", "inactive")
            record.setdefault("completed", False)
            record.setdefault("current_wave", 0)
            record.setdefault("attempts", 0)
            record.setdefault("defeated_enemy_ids", [])
            record.setdefault("completed_waves", [])
            record.setdefault("enemy_health", {})
            record.setdefault("pending_loot", [])

    def _restore_pending_loot(self):
        known = {pickup.drop_id for pickup in self.loot_pickups}
        for record in self.game_state.encounters.values():
            for loot in record.get("pending_loot", ()):
                drop_id = loot.get("drop_id")
                if not loot.get("collected", False) and drop_id not in known:
                    self.loot_pickups.append(EnemyLootPickup(loot))
                    known.add(drop_id)

    def set_context(self, world, npc_manager):
        if world is self.world and npc_manager is self.npc_manager:
            return
        self._detach_all()
        self.world = world
        self.npc_manager = npc_manager

    def _attach(self, actor):
        if self.npc_manager is not None and actor not in self.npc_manager.npcs:
            self.npc_manager.npcs.append(actor)

    def _detach(self, actor):
        if self.npc_manager is not None and actor in self.npc_manager.npcs:
            self.npc_manager.npcs.remove(actor)

    def _detach_all(self):
        for actor in (*self.enemies, *self.projectiles):
            self._detach(actor)
        self.enemies.clear()
        self.projectiles.clear()

    def close(self):
        self._detach_all()
        self.loot_pickups.clear()

    @staticmethod
    def _anchor_flag_id(definition):
        return (
            "player_farm.exterior_spawn"
            if definition.location_id == "player_farm"
            else f"location.{definition.location_id}.spawn"
        )

    def _stored_anchor(self, definition):
        return self.game_state.flag(self._anchor_flag_id(definition), None)

    def _anchor(self, definition):
        anchor = self._stored_anchor(definition)
        if anchor is None and self.world is not None:
            anchor = (
                self.world.get_spawn_position()
                if definition.location_id == "player_farm"
                else self.player.center
            )
        return pygame.Vector2(anchor or self.player.center)

    @staticmethod
    def _locations_share_runtime(location_id, current_location):
        if location_id == current_location:
            return True
        location_runtime = LOCATION_DEFINITIONS.get(location_id, {}).get("runtime", "world")
        current_runtime = LOCATION_DEFINITIONS.get(current_location, {}).get("runtime", "world")
        return location_runtime == "world" and current_runtime == "world"

    def _player_is_at_encounter(self, definition, current_location):
        runtime = LOCATION_DEFINITIONS.get(definition.location_id, {}).get("runtime", "world")
        if runtime != "world":
            return current_location == definition.location_id
        stored_anchor = self._stored_anchor(definition)
        if stored_anchor is None:
            return current_location == definition.location_id
        anchor = pygame.Vector2(stored_anchor)
        trigger_radius = max(360, int(definition.spawn_radius) * 2)
        return pygame.Vector2(self.player.center).distance_squared_to(anchor) <= trigger_radius ** 2

    def _spawn_position(self, definition, wave_index, slot_index, total):
        anchor = self._anchor(definition)
        angle = 360.0 * slot_index / max(1, total) + wave_index * 47.0
        offset = pygame.Vector2(definition.spawn_radius, 0).rotate(angle)
        pathfinder = getattr(self.npc_manager, "pathfinder", None)
        if pathfinder is None:
            return anchor + offset
        if LOCATION_DEFINITIONS.get(definition.location_id, {}).get("runtime", "world") != "world":
            return anchor + offset
        for angle_adjustment in (0, 35, -35, 70, -70, 110, -110, 180):
            adjusted = offset.rotate(angle_adjustment)
            for scale in (1.0, 0.8, 0.6, 0.4):
                candidate = anchor + adjusted * scale
                if pathfinder.is_walkable(pathfinder.world_to_tile(candidate)):
                    return candidate
        return anchor

    @staticmethod
    def enemy_instance_id(encounter_id, wave_index, slot_index, enemy_id):
        return f"{encounter_id}:wave:{wave_index + 1}:enemy:{slot_index + 1}:{enemy_id}"

    def _spawn_wave(self, definition):
        record = self.game_state.encounters[definition.id]
        wave_index = int(record["current_wave"])
        if wave_index >= len(definition.waves):
            self._finish_encounter(definition)
            return
        defeated = set(record.get("defeated_enemy_ids", ()))
        wave = definition.waves[wave_index]
        existing_ids = {enemy.instance_id for enemy in self.enemies}
        for slot_index, enemy_id in enumerate(wave):
            instance_id = self.enemy_instance_id(
                definition.id,
                wave_index,
                slot_index,
                enemy_id,
            )
            if instance_id in defeated or instance_id in existing_ids:
                continue
            enemy = Enemy(
                enemy_id,
                instance_id,
                definition.id,
                self._spawn_position(definition, wave_index, slot_index, len(wave)),
                location_id=definition.location_id,
                leash_radius=definition.leash_radius,
                pathfinder=getattr(self.npc_manager, "pathfinder", None),
                animation_library=self.enemy_library,
                on_defeated=self._on_enemy_defeated,
                on_health_changed=self._on_enemy_health_changed,
            )
            saved_health = record.get("enemy_health", {}).get(instance_id)
            if saved_health is not None:
                enemy.health = max(1, min(enemy.max_health, int(saved_health)))
            self.enemies.append(enemy)
            self._attach(enemy)
        if not any(enemy.is_alive for enemy in self.enemies if enemy.encounter_id == definition.id):
            self._finish_wave(definition)

    def _begin_attempt(self, definition):
        record = self.game_state.encounters[definition.id]
        self._detach_all()
        record["status"] = "active"
        record["completed"] = False
        record["current_wave"] = 0
        record["attempts"] = int(record.get("attempts", 0)) + 1
        record["defeated_enemy_ids"] = []
        record["completed_waves"] = []
        record["enemy_health"] = {}
        self._spawn_wave(definition)

    def _resume(self, definition):
        if any(enemy.encounter_id == definition.id for enemy in self.enemies):
            return
        self._spawn_wave(definition)

    def _grant_loot(self, enemy):
        for index, drop in enumerate(enemy.definition.drops):
            loot_event_id = f"{enemy.instance_id}:loot:{index + 1}"
            if drop.item_id == "coin":
                if not self.game_state.claim_event("enemy_loot", loot_event_id):
                    continue
                self.player.coins += drop.count
                self.dispatcher.publish(
                    EnemyLootGranted(
                        event_id=loot_event_id,
                        enemy_id=enemy.enemy_id,
                        enemy_instance_id=enemy.instance_id,
                        item_id=drop.item_id,
                        count=drop.count,
                        encounter_id=enemy.encounter_id,
                    )
                )
                continue

            encounter_record = self.game_state.encounters[enemy.encounter_id]
            pending = encounter_record.setdefault("pending_loot", [])
            if any(entry.get("drop_id") == loot_event_id for entry in pending):
                continue
            offset = pygame.Vector2(20 + index * 4, 0).rotate(index * 137 + len(pending) * 41)
            position = pygame.Vector2(enemy.rect.center) + offset
            loot_record = {
                "drop_id": loot_event_id,
                "enemy_id": enemy.enemy_id,
                "enemy_instance_id": enemy.instance_id,
                "encounter_id": enemy.encounter_id,
                "item_id": drop.item_id,
                "count": int(drop.count),
                "location_id": enemy.location_id,
                "position": [round(position.x), round(position.y)],
                "collected": False,
            }
            pending.append(loot_record)
            self.loot_pickups.append(EnemyLootPickup(loot_record))
            if self.effects is not None:
                particle = "gem" if drop.item_id.endswith("_ore") else "spark"
                self.effects.burst(particle, position, count=5)

    def visible_loot(self, location_id=None):
        location_id = location_id or self.game_state.current_location_id
        return tuple(
            pickup
            for pickup in self.loot_pickups
            if pickup.alive
            and self._locations_share_runtime(pickup.location_id, location_id)
        )

    def collect_loot_near_player(self, location_id=None):
        location_id = location_id or self.game_state.current_location_id
        pickup_area = self.player.get_interaction_box(getattr(self.world, "tile_size", 64))
        for pickup in tuple(self.loot_pickups):
            if (
                not pickup.alive
                or not self._locations_share_runtime(pickup.location_id, location_id)
                or not pickup_area.colliderect(pickup.rect)
                or not self.player.inventory.can_add_item(pickup.item_id, pickup.count)
            ):
                continue
            encounter_record = self.game_state.encounters.get(pickup.encounter_id, {})
            loot_record = next(
                (
                    entry
                    for entry in encounter_record.get("pending_loot", ())
                    if entry.get("drop_id") == pickup.drop_id
                ),
                None,
            )
            if loot_record is None:
                continue
            if not self.player.inventory.add_item_to_slot(Item(pickup.item_id), pickup.count):
                continue
            loot_record["collected"] = True
            pickup.alive = False
            self.loot_pickups.remove(pickup)
            if self.effects is not None:
                particle = "gem" if pickup.item_id.endswith("_ore") else "spark"
                self.effects.burst(particle, pickup.center, count=4)
            if self.game_state.claim_event("enemy_loot", pickup.drop_id):
                self.dispatcher.publish(
                    EnemyLootGranted(
                        event_id=pickup.drop_id,
                        enemy_id=loot_record["enemy_id"],
                        enemy_instance_id=loot_record["enemy_instance_id"],
                        item_id=pickup.item_id,
                        count=pickup.count,
                        encounter_id=loot_record["encounter_id"],
                    )
                )
            return True
        return False

    def _on_enemy_defeated(self, enemy):
        definition = self.definitions.get(enemy.encounter_id)
        if definition is None:
            return
        record = self.game_state.encounters[definition.id]
        defeated = list(record.get("defeated_enemy_ids", ()))
        if enemy.instance_id not in defeated:
            defeated.append(enemy.instance_id)
            record["defeated_enemy_ids"] = defeated
        self.dispatcher.publish(
            EnemyDefeated(
                event_id=f"{enemy.instance_id}:defeated",
                enemy_id=enemy.enemy_id,
                tier=enemy.definition.tier,
                encounter_id=enemy.encounter_id,
                xp_reward=enemy.definition.xp_reward,
            )
        )
        self._grant_loot(enemy)
        if not any(
            candidate.is_alive
            for candidate in self.enemies
            if candidate.encounter_id == definition.id
        ):
            self._finish_wave(definition)

    def _on_enemy_health_changed(self, enemy):
        record = self.game_state.encounters.get(enemy.encounter_id)
        if record is None:
            return
        health = dict(record.get("enemy_health", {}))
        health[enemy.instance_id] = int(enemy.health)
        record["enemy_health"] = health

    def _finish_wave(self, definition):
        record = self.game_state.encounters[definition.id]
        wave_number = int(record["current_wave"]) + 1
        completed_waves = list(record.get("completed_waves", ()))
        if wave_number not in completed_waves:
            completed_waves.append(wave_number)
            record["completed_waves"] = completed_waves
            self.dispatcher.publish(
                EncounterWaveCompleted(
                    event_id=f"{definition.id}:wave:{wave_number}:completed",
                    encounter_id=definition.id,
                    wave=wave_number,
                )
            )
        if wave_number >= len(definition.waves):
            self._finish_encounter(definition)
            return
        record["current_wave"] = wave_number
        self._spawn_wave(definition)

    def _finish_encounter(self, definition):
        record = self.game_state.encounters[definition.id]
        if record.get("completed"):
            return
        record["status"] = "completed"
        record["completed"] = True
        self.game_state.set_flag(f"{definition.id}.completed", True)
        if definition.completion_flag:
            self.game_state.set_flag(definition.completion_flag, True)
        self.dispatcher.publish(
            EncounterCompleted(
                event_id=f"{definition.id}:completed",
                encounter_id=definition.id,
                waves_completed=len(definition.waves),
            )
        )

    def _fail_encounter(self, definition):
        record = self.game_state.encounters[definition.id]
        if record.get("status") != "active":
            return
        record["status"] = "failed"
        attempt = int(record.get("attempts", 1))
        self.dispatcher.publish(
            EncounterFailed(
                event_id=f"{definition.id}:attempt:{attempt}:failed",
                encounter_id=definition.id,
                attempt=attempt,
            )
        )
        self._detach_all()

    def _spawn_projectile(self, enemy, target, *, angle_offset=0):
        self._projectile_counter += 1
        projectile = EnemyProjectile(
            f"{enemy.instance_id}:projectile:{self._projectile_counter}",
            enemy,
            target,
            angle_offset=angle_offset,
        )
        self.projectiles.append(projectile)
        self._attach(projectile)
        return projectile

    def _quest_triggered(self, definition, current_location):
        if definition.quest_id is None:
            return False
        if self.quest_system is None:
            return False
        status = self.quest_system.status(definition.quest_id)
        if status == "available" and self._player_is_at_encounter(definition, current_location):
            self.quest_system.start(definition.quest_id)
            status = self.quest_system.status(definition.quest_id)
        return status in {"active", "ready_to_turn_in"}

    def update(self, dt, *, current_location=None):
        current_location = current_location or self.game_state.current_location_id
        for definition in self.definitions.values():
            record = self.game_state.encounters[definition.id]
            triggered = self._quest_triggered(definition, current_location)
            player_at_encounter = self._player_is_at_encounter(definition, current_location)
            if not triggered or record.get("completed"):
                continue
            if record["status"] == "inactive" and player_at_encounter:
                self._begin_attempt(definition)
            elif record["status"] == "failed" and definition.retry_after_recovery:
                if self.player.is_alive and player_at_encounter:
                    self._begin_attempt(definition)
            elif record["status"] == "active":
                if not self.player.is_alive:
                    self._fail_encounter(definition)
                elif player_at_encounter:
                    self._resume(definition)

        if not self.player.is_alive:
            return
        for enemy in tuple(self.enemies):
            if self._locations_share_runtime(enemy.location_id, current_location):
                enemy.update(
                    dt,
                    player=self.player,
                    effects=self.effects,
                    projectile_callback=self._spawn_projectile,
                )
            if enemy.death_finished:
                self.enemies.remove(enemy)
                self._detach(enemy)
        for projectile in tuple(self.projectiles):
            if self._locations_share_runtime(projectile.location_id, current_location):
                projectile.update(dt, player=self.player, effects=self.effects)
            if not projectile.active:
                self.projectiles.remove(projectile)
                self._detach(projectile)
        for pickup in self.visible_loot(current_location):
            pickup.update(dt)
