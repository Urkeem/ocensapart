import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

import pygame

from data.content_manifest import ENEMY_ASSETS
from data.encounters import (
    ALCHEMIST_RESCUE_ENCOUNTER_ID,
    FIRST_DEFENSE,
    FIRST_DEFENSE_ENCOUNTER_ID,
    MIN_ENEMIES_PER_WAVE,
    STORY_ENCOUNTERS,
)
from data.enemies import ENEMY_DEFINITIONS
from entities.enemy import Enemy, EnemyAnimationLibrary, EnemyProjectile
from gameplay.encounters import EncounterManager
from gameplay.dialogue import DialogueResolver
from gameplay.combat import CombatSystem
from gameplay.events import (
    EncounterCompleted,
    EncounterFailed,
    EncounterWaveCompleted,
    EnemyDefeated,
    EnemyLootGranted,
    EventDispatcher,
)
from gameplay.game_state import GameState
from gameplay.progression import ProgressionService
from gameplay.quests import ACTIVE, COMPLETED, READY_TO_TURN_IN, QuestSystem


class FakeAnimationLibrary:
    def frames(self, enemy_id, state, facing):
        count = 3 if state == "death" else 2
        return tuple(pygame.Surface((48, 48), pygame.SRCALPHA) for _ in range(count))


class FakePathfinder:
    @staticmethod
    def world_to_tile(pos):
        return round(pos[0] / 64), round(pos[1] / 64)

    @staticmethod
    def is_walkable(tile):
        return True


class FakeWorld:
    seed = 404

    @staticmethod
    def get_spawn_position():
        return 0, 0


class FakeInventory:
    def __init__(self):
        self.items = {}
        self.is_inv = False

    def can_add_item(self, item_id, count=1):
        return True

    def add_item_to_slot(self, item, amount=1):
        self.items[item.name] = self.items.get(item.name, 0) + amount
        return True


class FakePlayer:
    def __init__(self, state, pos=(0, 0)):
        self.game_state = state
        self.health = 10
        self.max_health = 10
        self.coins = 0
        self.inventory = FakeInventory()
        self.selected_tool = "sword"
        self.weapon_wear = 0
        self.feet_collision_box = pygame.Rect(0, 0, 24, 18)
        self.feet_collision_box.center = pos

    @property
    def is_alive(self):
        return self.health > 0

    @property
    def center(self):
        return self.feet_collision_box.center

    def take_damage(self, amount=1, **_kwargs):
        if not self.is_alive:
            return False
        self.health = max(0, self.health - int(amount))
        return True

    def has_equipped_weapon(self, weapon):
        return weapon == self.selected_tool

    def begin_combat_action(self, _action, _duration):
        return True

    def wear_tool(self, _tool):
        self.weapon_wear += 1

    @staticmethod
    def get_facing_offset():
        return 1, 0


class FakeNPCManager:
    def __init__(self):
        self.npcs = []
        self.pathfinder = FakePathfinder()


class FakeEffects:
    def __init__(self):
        self.spawned = []

    def spawn(self, name, pos, **kwargs):
        self.spawned.append((name, pos, kwargs))


def ready_defense_state():
    state = GameState()
    state.set_flag("game.mode", "story")
    state.set_location("player_farm")
    dispatcher = EventDispatcher()
    progression = ProgressionService(state, dispatcher)
    quests = QuestSystem(state, dispatcher)
    chores = quests.get_state("prologue.morning_chores")
    chores["status"] = COMPLETED
    chores["completed"] = True
    chores["reward_claimed"] = True
    quests.refresh_availability()
    return state, dispatcher, progression, quests


def make_manager(state, dispatcher, quests, player=None, npc_manager=None):
    player = player or FakePlayer(state)
    npc_manager = npc_manager or FakeNPCManager()
    manager = EncounterManager(
        FakeWorld(),
        npc_manager,
        player,
        state,
        dispatcher,
        quest_system=quests,
        enemy_library=FakeAnimationLibrary(),
    )
    return manager, player, npc_manager


class PhaseSixEnemyEncounterTests(unittest.TestCase):
    @staticmethod
    def defeat_current_wave(manager):
        wave = tuple(enemy for enemy in manager.enemies if enemy.is_alive)
        for enemy in wave:
            enemy.take_damage(999)
        return wave

    def test_every_story_wave_has_at_least_fifteen_enemies(self):
        for encounter in STORY_ENCOUNTERS:
            for wave_number, wave in enumerate(encounter.waves, 1):
                with self.subTest(encounter=encounter.id, wave=wave_number):
                    self.assertGreaterEqual(len(wave), MIN_ENEMIES_PER_WAVE)
                    self.assertLessEqual(wave.count("skeleton_king"), 1)
                    self.assertLessEqual(wave.count("necromancer"), 1)

    def test_alchemist_captors_spawn_at_new_home_despite_stale_world_label(self):
        state = GameState()
        state.set_flag("game.mode", "story")
        state.set_location("player_farm")
        state.set_flag("location.alchemist_home.spawn", (1200, 900))
        dispatcher = EventDispatcher()
        progression = ProgressionService(state, dispatcher)
        quests = QuestSystem(state, dispatcher)
        quests.get_state("act1.rescue_alchemist")["status"] = ACTIVE
        player = FakePlayer(state, (1200, 900))
        manager, _, npc_manager = make_manager(
            state,
            dispatcher,
            quests,
            player=player,
        )

        manager.update(0.01, current_location="player_farm")

        captors = [
            enemy
            for enemy in manager.enemies
            if enemy.encounter_id == ALCHEMIST_RESCUE_ENCOUNTER_ID
        ]
        self.assertEqual(len(captors), MIN_ENEMIES_PER_WAVE)
        self.assertTrue(all(enemy.location_id == "alchemist_home" for enemy in captors))
        self.assertTrue(all(enemy in npc_manager.npcs for enemy in captors))
        self.assertEqual(
            state.encounters[ALCHEMIST_RESCUE_ENCOUNTER_ID]["status"],
            "active",
        )

        combat = CombatSystem(player, FakeEffects(), npc_manager)
        self.assertEqual(len(combat._living_npcs()), MIN_ENEMIES_PER_WAVE)
        manager.close()
        progression.close()
        quests.close()

    @classmethod
    def setUpClass(cls):
        pygame.init()
        pygame.display.set_mode((1, 1))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_enemy_definitions_cover_manifest_and_combat_profiles(self):
        self.assertEqual(set(ENEMY_DEFINITIONS), set(ENEMY_ASSETS))
        self.assertEqual(ENEMY_DEFINITIONS["goblin_berserker"].attack_profile, "melee")
        self.assertEqual(ENEMY_DEFINITIONS["goblin_slinger"].attack_profile, "ranged")
        self.assertEqual(ENEMY_DEFINITIONS["cultist"].attack_profile, "caster")
        self.assertTrue(ENEMY_DEFINITIONS["skeleton_king"].is_boss)
        self.assertEqual(ENEMY_DEFINITIONS["skeleton_king"].tier, "boss")
        self.assertGreater(
            ENEMY_DEFINITIONS["skeleton_king"].xp_reward,
            ENEMY_DEFINITIONS["skeleton_grunt"].xp_reward,
        )

    def test_directional_and_boss_animation_manifests_load_real_frames(self):
        library = EnemyAnimationLibrary()
        for enemy_id in (
            "cultist",
            "goblin_berserker",
            "goblin_slinger",
            "skeleton_grunt",
            "skeleton_hunter",
        ):
            for facing in ("down", "up", "left", "right"):
                for state in ("idle", "chase", "attack", "hurt", "death"):
                    self.assertTrue(library.frames(enemy_id, state, facing))
        self.assertEqual(library.frames("skeleton_king", "idle", "down")[0].get_size(), (96, 96))
        self.assertEqual(library.frames("skeleton_king", "attack", "down")[0].get_size(), (128, 128))
        self.assertEqual(library.frames("skeleton_king", "special", "down")[0].get_size(), (128, 256))

    def test_melee_enemy_chases_attacks_and_reports_death_once(self):
        state = GameState()
        player = FakePlayer(state, pos=(50, 0))
        deaths = []
        enemy = Enemy(
            "goblin_berserker",
            "enemy:one",
            "encounter:test",
            (0, 0),
            animation_library=FakeAnimationLibrary(),
            on_defeated=deaths.append,
        )
        enemy.update(0.01, player=player)
        self.assertEqual(player.health, 9)
        self.assertEqual(enemy.state, "attack")
        self.assertTrue(enemy.take_damage(enemy.max_health))
        self.assertFalse(enemy.take_damage(1))
        self.assertEqual(deaths, [enemy])
        self.assertEqual(enemy.state, "death")

    def test_player_combat_prioritizes_dedicated_enemy_target(self):
        state = GameState()
        player = FakePlayer(state)
        enemy = Enemy(
            "goblin_berserker",
            "enemy:combat",
            "encounter:test",
            (55, 0),
            animation_library=FakeAnimationLibrary(),
        )
        civilian = type(
            "Civilian",
            (),
            {
                "is_alive": True,
                "is_enemy": False,
                "hostile": False,
                "can_take_damage": True,
                "location_id": "player_farm",
                "rect": pygame.Rect(15, -20, 20, 20),
                "take_damage": lambda self, *args, **kwargs: True,
            },
        )()
        effects = FakeEffects()
        combat = CombatSystem(player, effects, type("Manager", (), {"npcs": [civilian, enemy]})())
        self.assertTrue(combat.sword_attack())
        self.assertEqual(enemy.health, enemy.max_health - 1)
        self.assertEqual(player.weapon_wear, 1)

    def test_ranged_projectile_hits_only_once(self):
        state = GameState()
        player = FakePlayer(state, pos=(180, 0))
        owner = Enemy(
            "goblin_slinger",
            "enemy:slinger",
            "encounter:test",
            (0, 0),
            animation_library=FakeAnimationLibrary(),
        )
        projectile = EnemyProjectile("arrow:1", owner, player.feet_collision_box.center)
        for _ in range(40):
            projectile.update(0.02, player=player)
            if not projectile.active:
                break
        self.assertFalse(projectile.active)
        self.assertEqual(player.health, 9)
        projectile.update(1.0, player=player)
        self.assertEqual(player.health, 9)

    def test_low_health_boss_uses_projectile_fan(self):
        state = GameState()
        player = FakePlayer(state, pos=(60, 0))
        boss = Enemy(
            "skeleton_king",
            "boss:one",
            "encounter:test",
            (0, 0),
            animation_library=FakeAnimationLibrary(),
        )
        boss.health = boss.max_health // 2
        shots = []
        boss.update(
            0.01,
            player=player,
            projectile_callback=lambda owner, target, angle_offset=0: shots.append(angle_offset),
        )
        self.assertEqual(shots, [-22, 0, 22])
        self.assertEqual(boss.state, "special")
        self.assertEqual(player.health, 8)

    def test_first_defense_completes_waves_advances_quest_and_awards_once(self):
        state, dispatcher, progression, quests = ready_defense_state()
        events = []
        for event_type in (
            EnemyDefeated,
            EnemyLootGranted,
            EncounterWaveCompleted,
            EncounterCompleted,
        ):
            dispatcher.subscribe(event_type, events.append)
        manager, player, _ = make_manager(state, dispatcher, quests)

        manager.update(0.01)
        self.assertEqual(quests.status("prologue.first_defense"), ACTIVE)
        self.assertEqual(len([enemy for enemy in manager.enemies if enemy.is_alive]), MIN_ENEMIES_PER_WAVE)
        self.assertEqual(state.encounters[FIRST_DEFENSE_ENCOUNTER_ID]["attempts"], 1)

        self.defeat_current_wave(manager)
        wave_two = [enemy for enemy in manager.enemies if enemy.is_alive]
        self.assertEqual(len(wave_two), MIN_ENEMIES_PER_WAVE)
        self.defeat_current_wave(manager)

        expected_xp = sum(
            ENEMY_DEFINITIONS[enemy_id].xp_reward
            for wave in FIRST_DEFENSE.waves
            for enemy_id in wave
        )
        expected_coins = sum(
            next(drop.count for drop in ENEMY_DEFINITIONS[enemy_id].drops if drop.item_id == "coin")
            for wave in FIRST_DEFENSE.waves
            for enemy_id in wave
        )
        enemy_count = sum(len(wave) for wave in FIRST_DEFENSE.waves)

        record = state.encounters[FIRST_DEFENSE_ENCOUNTER_ID]
        self.assertTrue(record["completed"])
        self.assertTrue(state.flag("prologue.first_defense_won"))
        self.assertEqual(record["completed_waves"], [1, 2])
        self.assertEqual(quests.status("prologue.first_defense"), READY_TO_TURN_IN)
        self.assertEqual(state.progression.experience, expected_xp)
        self.assertEqual(player.coins, expected_coins)
        self.assertEqual(sum(isinstance(event, EnemyLootGranted) for event in events), enemy_count)
        self.assertEqual(sum(isinstance(event, EncounterCompleted) for event in events), 1)

        last_enemy = manager.enemies[-1]
        manager._on_enemy_defeated(last_enemy)
        self.assertEqual(state.progression.experience, expected_xp)
        self.assertEqual(player.coins, expected_coins)

        resolver = DialogueResolver(state, quests, dispatcher)
        node = resolver.resolve("wife")
        self.assertEqual(node["id"], "wife.first_defense.turn_in")
        resolver.complete("wife", node)
        self.assertEqual(quests.status("prologue.first_defense"), COMPLETED)
        self.assertTrue(state.flag("prologue.first_defense_complete"))
        self.assertEqual(state.progression.experience, expected_xp + 25)
        self.assertEqual(state.progression.kingdom_reputation, 5)
        manager.close()
        progression.close()
        quests.close()

    def test_active_wave_reload_only_respawns_undefeated_enemy(self):
        state, dispatcher, progression, quests = ready_defense_state()
        manager, player, _ = make_manager(state, dispatcher, quests)
        manager.update(0.01)
        self.defeat_current_wave(manager)
        wave_two = [enemy for enemy in manager.enemies if enemy.is_alive]
        defeated_wave_two_id = wave_two[0].instance_id
        wave_two[0].take_damage(99)
        survivor = next(enemy for enemy in wave_two if enemy.is_alive)
        survivor.take_damage(1)
        survivor_health = survivor.health
        snapshot = state.to_dict()
        manager.close()
        progression.close()
        quests.close()

        restored = GameState.from_dict(snapshot)
        restored_dispatcher = EventDispatcher()
        restored_progression = ProgressionService(restored, restored_dispatcher)
        restored_quests = QuestSystem(restored, restored_dispatcher)
        restored_manager, _, _ = make_manager(
            restored,
            restored_dispatcher,
            restored_quests,
        )
        restored_manager.update(0.01)
        alive = [enemy for enemy in restored_manager.enemies if enemy.is_alive]
        self.assertEqual(len(alive), MIN_ENEMIES_PER_WAVE - 1)
        self.assertNotIn(defeated_wave_two_id, {enemy.instance_id for enemy in alive})
        restored_survivor = next(enemy for enemy in alive if enemy.instance_id == survivor.instance_id)
        self.assertEqual(restored_survivor.health, survivor_health)
        first_wave_xp = sum(ENEMY_DEFINITIONS[enemy_id].xp_reward for enemy_id in FIRST_DEFENSE.waves[0])
        defeated_wave_two_xp = ENEMY_DEFINITIONS[wave_two[0].enemy_id].xp_reward
        self.assertEqual(restored.progression.experience, first_wave_xp + defeated_wave_two_xp)
        restored_manager.close()
        restored_progression.close()
        restored_quests.close()

    def test_failed_attempt_retries_after_recovery_without_duplicate_rewards(self):
        state, dispatcher, progression, quests = ready_defense_state()
        failures = []
        dispatcher.subscribe(EncounterFailed, failures.append)
        manager, player, _ = make_manager(state, dispatcher, quests)
        manager.update(0.01)
        first_id = manager.enemies[0].instance_id
        manager.enemies[0].take_damage(99)
        self.assertEqual(state.progression.experience, 10)
        self.assertEqual(player.coins, 2)

        player.health = 0
        manager.update(0.01)
        self.assertEqual(state.encounters[FIRST_DEFENSE_ENCOUNTER_ID]["status"], "failed")
        self.assertEqual(quests.status("prologue.first_defense"), ACTIVE)
        self.assertEqual(len(failures), 1)
        self.assertFalse(manager.enemies)

        player.health = player.max_health
        manager.update(0.01)
        record = state.encounters[FIRST_DEFENSE_ENCOUNTER_ID]
        self.assertEqual(record["attempts"], 2)
        self.assertEqual(manager.enemies[0].instance_id, first_id)
        manager.enemies[0].take_damage(99)
        self.assertEqual(state.progression.experience, 10)
        self.assertEqual(player.coins, 2)
        manager.close()
        progression.close()
        quests.close()

    def test_completed_encounter_round_trip_never_respawns(self):
        state, dispatcher, progression, quests = ready_defense_state()
        manager, _, _ = make_manager(state, dispatcher, quests)
        manager.update(0.01)
        self.defeat_current_wave(manager)
        self.defeat_current_wave(manager)
        snapshot = state.to_dict()
        manager.close()
        progression.close()
        quests.close()

        restored = GameState.from_dict(snapshot)
        restored_dispatcher = EventDispatcher()
        restored_progression = ProgressionService(restored, restored_dispatcher)
        restored_quests = QuestSystem(restored, restored_dispatcher)
        restored_manager, _, npc_manager = make_manager(
            restored,
            restored_dispatcher,
            restored_quests,
        )
        restored_manager.update(1.0)
        self.assertFalse(restored_manager.enemies)
        self.assertFalse(any(getattr(npc, "is_enemy", False) for npc in npc_manager.npcs))
        restored_manager.close()
        restored_progression.close()
        restored_quests.close()

    def test_enemy_item_drop_remains_physical_until_player_collects_it(self):
        state, dispatcher, progression, quests = ready_defense_state()
        loot_events = []
        dispatcher.subscribe(EnemyLootGranted, loot_events.append)
        manager, player, _ = make_manager(state, dispatcher, quests)
        manager.update(0.01)

        manager.enemies[0].take_damage(99)

        self.assertEqual(player.inventory.items.get("iron_ore", 0), 0)
        self.assertEqual(len(manager.loot_pickups), 1)
        pickup = manager.loot_pickups[0]
        player.feet_collision_box.center = pickup.rect.center
        player.get_interaction_box = lambda _reach: player.feet_collision_box.inflate(32, 32)

        self.assertTrue(manager.collect_loot_near_player("player_farm"))
        self.assertEqual(player.inventory.items["iron_ore"], 1)
        self.assertFalse(manager.collect_loot_near_player("player_farm"))
        record = state.encounters[FIRST_DEFENSE_ENCOUNTER_ID]
        self.assertTrue(record["pending_loot"][0]["collected"])
        self.assertEqual(
            [event.item_id for event in loot_events].count("iron_ore"),
            1,
        )
        manager.close()
        progression.close()
        quests.close()

    def test_uncollected_enemy_drop_survives_save_round_trip(self):
        state, dispatcher, progression, quests = ready_defense_state()
        manager, _, _ = make_manager(state, dispatcher, quests)
        manager.update(0.01)
        manager.enemies[0].take_damage(99)
        snapshot = state.to_dict()
        manager.close()
        progression.close()
        quests.close()

        restored = GameState.from_dict(snapshot)
        restored_dispatcher = EventDispatcher()
        restored_progression = ProgressionService(restored, restored_dispatcher)
        restored_quests = QuestSystem(restored, restored_dispatcher)
        restored_manager, _, _ = make_manager(
            restored,
            restored_dispatcher,
            restored_quests,
        )

        self.assertEqual(len(restored_manager.loot_pickups), 1)
        self.assertEqual(restored_manager.loot_pickups[0].item_id, "iron_ore")
        restored_manager.close()
        restored_progression.close()
        restored_quests.close()


if __name__ == "__main__":
    unittest.main()
