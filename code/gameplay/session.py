"""Active game-session orchestration and island transitions."""

import random

import pygame

from entities.npc import NPCManager
from gameplay.combat import CombatSystem
from gameplay.config import (
    DEFAULT_ACTIVE_RADIUS,
    DEFAULT_CHUNK_SIZE,
    DEFAULT_NPC_COUNT,
    DEFAULT_TILE_SIZE,
    FPS,
    WORLD_HINT_ACK_KEYS,
    WORLD_HINT_KEYS,
)
from gameplay.controls import (
    BUTTON_CONFIRM,
    BUTTON_TOOL,
    BUTTON_TOOL_NEXT,
    get_controller_input,
)
from gameplay.hints import get_contextual_world_hint
from gameplay.effects import EffectsManager
from gameplay.rendering import draw_transition_overlay, draw_world
from gameplay.savegame import SaveGameManager, restore_npcs, restore_weather
from gameplay.world_objects import (
    collect_pickups_near_player,
    collect_player_collision_objects,
    maintain_natural_resources,
    prewarm_chunk_runtime,
    spawn_rock_piece_drops,
)
from ui.hud import GameplayHUD
from ui.dialogue import MerchantDialogue
from world.soil import SoilLayer
from world.weather import WeatherSystem
from world.lighting import LightSystem


def bind_player_to_world(player, world, soil_layer):
    if getattr(player, "fishing_active", False):
        player.cancel_fishing()
    spawn_x, spawn_y = world.get_spawn_position()
    player.pos = pygame.Vector2(spawn_x, spawn_y)
    player.rect.midbottom = (round(spawn_x), round(spawn_y))
    player.sync_collision_boxes()
    player.direction.update(0, 0)
    player.soil_layer = soil_layer
    player.swim_visual.bind_world(world)
    player.rock_drop_callback = spawn_rock_piece_drops


def load_next_island(world_run, player, assets, screen):
    world_run.advance()
    world = world_run.create_world(
        spawn_chunk=(0, 0),
        chunk_size=DEFAULT_CHUNK_SIZE,
        active_radius=DEFAULT_ACTIVE_RADIUS,
        tile_size=DEFAULT_TILE_SIZE,
    )
    soil_layer = SoilLayer(world)
    bind_player_to_world(player, world, soil_layer)
    hud = GameplayHUD(player, screen)
    world.current_player_chunk = world.world_to_chunk(player.center)
    world.prepare_full_island(
        prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime(
            chunk,
            world,
            soil_layer,
        )
    )
    return world, soil_layer, hud, None, world.world_to_chunk(player.center)


async def run_game_loop(
    screen,
    clock,
    world_run,
    world,
    player,
    camera,
    last_player_chunk,
    assets,
    soil_layer=None,
    hud=None,
    npc_manager=None,
    loaded_save=None,
):
    # The main loop owns input, simulation updates, chunk activation, and final
    # draw calls for the active game session.
    transition_active = False
    transition_message = ""
    transition_subtitle = ""
    weather = WeatherSystem(screen.get_size())
    if loaded_save:
        restore_weather(weather, loaded_save.get("weather"))
        restore_npcs(npc_manager, loaded_save.get("npcs"))
        if hud is not None:
            hud.show_notification("Saved voyage loaded")
    light_system = LightSystem()
    effects = EffectsManager(rng=random.Random(f"{world.seed}:effects"))
    combat = CombatSystem(player, effects, npc_manager)
    dialogue = MerchantDialogue(screen, player, npc_manager)
    controller_input = getattr(player, "controller_input", None) or get_controller_input()
    save_manager = SaveGameManager()

    def save_current_game():
        try:
            path = save_manager.save(world_run, world, player, weather, npc_manager)
            if hud is not None:
                hud.show_notification(f"Game saved: {path.name}")
            return True
        except (OSError, TypeError, ValueError) as error:
            if hud is not None:
                hud.show_notification(f"Save failed: {error}")
            return False
    controller_hint_buttons = {
        "select_resource_tool": BUTTON_TOOL_NEXT,
        "break_resource": BUTTON_TOOL,
        "collect_loose_item": BUTTON_CONFIRM,
        "select_fishing_rod": BUTTON_TOOL_NEXT,
        "cast_fishing_line": BUTTON_TOOL,
        "reel_fishing_line": BUTTON_TOOL,
    }

    running = True
    while running:
        dt = clock.tick(FPS) / 1000.0
        for event in controller_input.get_events():
            controller_input.handle_event(event)
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
                save_current_game()
                continue
            if (
                event.type == pygame.CONTROLLERBUTTONDOWN
                and event.button == pygame.CONTROLLER_BUTTON_START
            ):
                save_current_game()
                continue
            if dialogue.active:
                dialogue.handle_event(event)
                continue
            if hud is not None:
                hud.handle_event(event)
                if hud.death_exit_requested:
                    running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_e and dialogue.try_open_near_player():
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    camera.zoom_in(0.1)
                elif event.key == pygame.K_MINUS:
                    camera.zoom_out(0.1)
                elif event.key == pygame.K_n:
                    world, soil_layer, hud, npc_manager, last_player_chunk = load_next_island(
                        world_run,
                        player,
                        assets,
                        screen,
                    )
                    transition_active = True
                    transition_message = f"Landing on {world.level_name}"
                    transition_subtitle = f"Difficulty {world.island.difficulty}"
                    combat.reset_world()
                    dialogue.set_npc_manager(None)
                elif event.key in (pygame.K_e, pygame.K_p) and getattr(player, "pickup_cooldown", 0) <= 0:
                    if collect_pickups_near_player(world, player):
                        player.pickup_cooldown = 0.25
                        player.world_hint_seen.add("collect_loose_item")
                        if event.key == pygame.K_e:
                            player.seed_switch_cooldown = 0.2
                hint = get_contextual_world_hint(world, player)
                if hint is not None and event.key in WORLD_HINT_KEYS:
                    hint_id, _, _ = hint
                    if event.key in WORLD_HINT_ACK_KEYS.get(hint_id, set()):
                        player.world_hint_seen.add(hint_id)
                combat.handle_event(event)
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                if event.button == BUTTON_CONFIRM and dialogue.try_open_near_player():
                    continue
                if (
                    event.button == BUTTON_CONFIRM
                    and not player.inventory.is_inv
                    and getattr(player, "selected_tool", "")
                    not in {"sword", "spear", "shield"}
                    and getattr(player, "pickup_cooldown", 0) <= 0
                    and collect_pickups_near_player(world, player)
                ):
                    player.pickup_cooldown = 0.25
                    player.world_hint_seen.add("collect_loose_item")

                hint = get_contextual_world_hint(world, player)
                if hint is not None:
                    hint_id, _, _ = hint
                    if event.button == controller_hint_buttons.get(hint_id):
                        player.world_hint_seen.add(hint_id)
                combat.handle_event(event)

        if not transition_active:
            player.current_season = weather.current_season
            player.update(dt, collect_player_collision_objects(world))
            weather.update(dt, soil_layer)
            if soil_layer is not None:
                soil_layer.update(dt, weather.time)
            camera.update(player)
            new_player_chunk = world.world_to_chunk(player.center)

            world.update_active_chunks(player.center, player.direction)
            if new_player_chunk != last_player_chunk:
                last_player_chunk = new_player_chunk
        else:
            camera.update(player)
            world.update_active_chunks(player.center, player.direction)
            weather.update(dt, soil_layer)
            if soil_layer is not None:
                soil_layer.update(dt, weather.time)

        maintain_natural_resources(world, dt)

        if transition_active:
            transition_active = False
            if npc_manager is None:
                npc_manager = NPCManager(
                    world,
                    assets,
                    count=DEFAULT_NPC_COUNT,
                )
                dialogue.set_npc_manager(npc_manager)

        if npc_manager is None:
            npc_manager = NPCManager(
                world,
                assets,
                count=DEFAULT_NPC_COUNT,
            )
            dialogue.set_npc_manager(npc_manager)

        if npc_manager is not None:
            combat.set_npc_manager(npc_manager)
            npc_manager.update(dt, player=player, effects=effects, game_time=weather.time)

        combat.update(dt)
        dialogue.update(dt)
        effects.update(dt, player=player, weather=weather, world=world)

        light_sources = draw_world(
            screen,
            world,
            player,
            camera,
            dt,
            soil_layer,
            npc_manager,
            effects,
        )
        weather.draw_world_effects(screen)
        light_system.draw(screen, light_sources, camera, weather.time)
        if hud is not None:
            hud.draw(world, npc_manager, weather)
        dialogue.draw()
        if transition_active:
            draw_transition_overlay(screen, transition_message, transition_subtitle, alpha=165)
        pygame.display.flip()

    save_current_game()
