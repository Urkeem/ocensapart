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
    BUTTON_DPAD_DOWN,
    BUTTON_DPAD_LEFT,
    BUTTON_DPAD_RIGHT,
    BUTTON_DPAD_UP,
    BUTTON_TOOL,
    BUTTON_TOOL_NEXT,
    get_controller_input,
)
from gameplay.hints import get_contextual_world_hint
from gameplay.effects import EffectsManager
from gameplay.events import EventDispatcher
from gameplay.game_state import GameState
from gameplay.progression import ProgressionService
from gameplay.quests import QuestSystem
from gameplay.interactions import InteractionSystem
from gameplay.locations import LocationManager
from gameplay.vessels import VesselManager
from gameplay.survivors import SurvivorTransportService
from gameplay.recovery import RecoverySystem
from gameplay.stamina import StaminaSystem
from gameplay.equipment import EquipmentService
from gameplay.encounters import EncounterManager
from gameplay.rendering import draw_transition_overlay, draw_world
from gameplay.savegame import SaveGameManager, restore_npcs, restore_weather
from gameplay.world_objects import (
    collect_pickups_near_player,
    collect_player_collision_objects,
    maintain_natural_resources,
    prewarm_chunk_runtime_step,
    spawn_rock_piece_drops,
)
from ui.hud import GameplayHUD
from ui.dialogue import DialogueController
from ui.equipment import EquipmentServiceUI
from ui.save_dialog import SaveNameDialog
from gameplay.dialogue import DialogueResolver
from gameplay.telemetry import DevelopmentTelemetry
from gameplay.presentation import StoryPresentation
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


def get_viewport_chunk_coords(world, camera, screen):
    chunk_pixel_w = world.chunk_size[0] * world.tile_size
    chunk_pixel_h = world.chunk_size[1] * world.tile_size
    view_left = int(camera.offset.x)
    view_top = int(camera.offset.y)
    view_right = view_left + int(screen.get_width() / camera.zoom)
    view_bottom = view_top + int(screen.get_height() / camera.zoom)
    return {
        coord
        for chunk_y in range(
            view_top // chunk_pixel_h,
            ((view_bottom - 1) // chunk_pixel_h) + 1,
        )
        for chunk_x in range(
            view_left // chunk_pixel_w,
            ((view_right - 1) // chunk_pixel_w) + 1,
        )
        if world.is_chunk_in_level_bounds(coord := (chunk_x, chunk_y))
    }


def load_next_island(world_run, player, assets, screen, camera):
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
    camera.update(player)
    landing_chunks = get_viewport_chunk_coords(world, camera, screen)
    world.queue_chunks_around(world.current_player_chunk)
    world.prepare_loaded_chunks_incrementally(landing_chunks)
    while not world.is_streaming_area_ready(landing_chunks):
        world.process_chunk_streaming(
            prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime_step(
                chunk,
                world,
                soil_layer,
            ),
            max_prewarm_steps=1,
        )
    world.start_chunk_streaming(world.current_player_chunk)
    return world, soil_layer, hud, None, world.current_player_chunk


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
    game_state=None,
    save_path=None,
):
    # The main loop owns input, simulation updates, chunk activation, and final
    # draw calls for the active game session.
    transition_active = False
    transition_message = ""
    transition_subtitle = ""
    weather = WeatherSystem(screen.get_size())
    game_state = game_state or GameState.from_dict(
        (loaded_save or {}).get("game_state")
    )
    event_dispatcher = EventDispatcher()
    telemetry = DevelopmentTelemetry.from_environment().bind(event_dispatcher)
    story_presentation = StoryPresentation(screen, event_dispatcher, game_state.accessibility)
    progression = ProgressionService(game_state, event_dispatcher)
    quest_system = QuestSystem(game_state, event_dispatcher, player=player)
    dialogue_resolver = DialogueResolver(game_state, quest_system, event_dispatcher, player=player)
    interaction_system = InteractionSystem(npc_manager)
    player.game_state = game_state
    player.event_dispatcher = event_dispatcher
    if loaded_save:
        restore_weather(weather, loaded_save.get("weather"))
        restore_npcs(npc_manager, loaded_save.get("npcs"))
        if hud is not None:
            hud.show_notification("Saved voyage loaded")
    location_manager = None
    recovery = None
    vessel_manager = None
    survivor_transport = None
    if game_state.flag("game.mode") == "story":
        location_manager = LocationManager(
            screen,
            world,
            soil_layer,
            player,
            game_state,
            npc_manager,
            event_dispatcher,
        )
        if hud is not None:
            location_manager.message_callback = hud.show_notification
        interaction_system.current_location_id = game_state.current_location_id
        interaction_system.register_provider(location_manager.interaction_targets)
        vessel_manager = VesselManager(world, player, game_state, event_dispatcher)
        if hud is not None:
            vessel_manager.message_callback = hud.show_notification
        interaction_system.register_provider(vessel_manager.interaction_targets)
        survivor_transport = SurvivorTransportService(
            game_state,
            vessel_manager,
            event_dispatcher,
            npc_manager,
        )
        dialogue_resolver.set_services(
            survivor_transport=survivor_transport,
            vessel_manager=vessel_manager,
        )
        recovery = RecoverySystem(
            screen,
            player,
            game_state,
            weather,
            soil_layer,
            location_manager,
            event_dispatcher,
        )
        location_manager.sleep_callback = recovery.sleep
    stamina = StaminaSystem(game_state, player) if location_manager is not None else None
    light_system = LightSystem()
    effects = EffectsManager(
        rng=random.Random(f"{world.seed}:effects"),
        reduced_motion=game_state.accessibility.reduced_motion,
    )
    combat = CombatSystem(player, effects, npc_manager)
    equipment_service = EquipmentService(player, game_state)
    equipment_service_ui = EquipmentServiceUI(screen, player, equipment_service)
    encounter_manager = EncounterManager(
        world,
        npc_manager,
        player,
        game_state,
        event_dispatcher,
        quest_system=quest_system,
        effects=effects,
    )
    dialogue = DialogueController(
        screen,
        player,
        npc_manager,
        dialogue_resolver,
        interaction_system,
        equipment_service_ui,
    )
    if hud is not None:
        hud.set_quest_system(quest_system)
        hud.bind_progression_events(event_dispatcher, effects)
    controller_input = getattr(player, "controller_input", None) or get_controller_input()
    save_manager = SaveGameManager(save_path)
    save_dialog = SaveNameDialog(screen, save_manager)

    def interact_with_nearest():
        target = interaction_system.find_best(player)
        if target is None:
            return False
        if target.kind == "npc":
            return dialogue.open_target(target)
        activated = interaction_system.activate(target)
        interaction_system.current_location_id = game_state.current_location_id
        return activated

    def save_current_game(save_name=None):
        try:
            path = save_manager.save(
                world_run,
                world,
                player,
                weather,
                npc_manager,
                game_state,
                save_name=save_name,
            )
            if hud is not None:
                hud.show_notification(f"Game saved: {save_manager.current_name}")
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
            if save_dialog.active:
                save_action = save_dialog.handle_event(event)
                if save_action and save_action[0] == "save":
                    save_current_game(save_action[1])
                continue
            if event.type == pygame.KEYDOWN and event.key == pygame.K_F5:
                save_dialog.open()
                continue
            if (
                event.type == pygame.CONTROLLERBUTTONDOWN
                and event.button == pygame.CONTROLLER_BUTTON_START
            ):
                save_dialog.open()
                continue
            if recovery is not None and recovery.active:
                continue
            if dialogue.active:
                dialogue.handle_event(event)
                continue
            if hud is not None:
                hud_handled = hud.handle_event(event)
                if hud.death_exit_requested:
                    running = False
                if hud_handled or hud.journal_open:
                    continue
            selection_button = controller_input.selection_navigation_button(event)
            if event.type == pygame.CONTROLLERBUTTONDOWN and event.button in {
                BUTTON_DPAD_LEFT,
                BUTTON_DPAD_RIGHT,
                BUTTON_DPAD_UP,
                BUTTON_DPAD_DOWN,
            }:
                selection_button = event.button
            if selection_button in (BUTTON_DPAD_LEFT, BUTTON_DPAD_UP):
                player.change_active_selection(-1)
                continue
            if selection_button in (BUTTON_DPAD_RIGHT, BUTTON_DPAD_DOWN):
                player.change_active_selection(1)
                continue
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_e and interact_with_nearest():
                    continue
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key in (pygame.K_EQUALS, pygame.K_PLUS):
                    camera.zoom_in(0.1)
                elif event.key == pygame.K_MINUS:
                    camera.zoom_out(0.1)
                elif event.key == pygame.K_n and location_manager is None:
                    if hud is not None:
                        hud.close()
                    world.shutdown_chunk_streaming()
                    world, soil_layer, hud, npc_manager, last_player_chunk = load_next_island(
                        world_run,
                        player,
                        assets,
                        screen,
                        camera,
                    )
                    encounter_manager.set_context(world, npc_manager)
                    hud.set_quest_system(quest_system)
                    hud.bind_progression_events(event_dispatcher, effects)
                    transition_active = True
                    transition_message = f"Landing on {world.level_name}"
                    transition_subtitle = f"Difficulty {world.island.difficulty}"
                    combat.reset_world()
                    dialogue.set_npc_manager(None)
                elif (
                    event.key in (pygame.K_e, pygame.K_p)
                    and getattr(player, "pickup_cooldown", 0) <= 0
                ):
                    collected = encounter_manager.collect_loot_near_player(
                        game_state.current_location_id
                    )
                    if (
                        not collected
                        and (location_manager is None or not location_manager.is_interior)
                    ):
                        collected = collect_pickups_near_player(world, player)
                    if collected:
                        player.pickup_cooldown = 0.25
                        player.world_hint_seen.add("collect_loose_item")
                        if event.key == pygame.K_e:
                            player.seed_switch_cooldown = 0.2
                hint = None if location_manager is not None and location_manager.is_interior else get_contextual_world_hint(world, player)
                if hint is not None and event.key in WORLD_HINT_KEYS:
                    hint_id, _, _ = hint
                    if event.key in WORLD_HINT_ACK_KEYS.get(hint_id, set()):
                        player.world_hint_seen.add(hint_id)
                combat.handle_event(event)
            elif event.type == pygame.CONTROLLERBUTTONDOWN:
                if event.button == BUTTON_CONFIRM and interact_with_nearest():
                    continue
                if (
                    event.button == BUTTON_CONFIRM
                    and not player.inventory.is_inv
                    and getattr(player, "pickup_cooldown", 0) <= 0
                    and encounter_manager.collect_loot_near_player(
                        game_state.current_location_id
                    )
                ):
                    player.pickup_cooldown = 0.25
                    player.world_hint_seen.add("collect_loose_item")
                    continue
                if (
                    event.button == BUTTON_CONFIRM
                    and (location_manager is None or not location_manager.is_interior)
                    and not player.inventory.is_inv
                    and getattr(player, "pickup_cooldown", 0) <= 0
                    and collect_pickups_near_player(world, player)
                ):
                    player.pickup_cooldown = 0.25
                    player.world_hint_seen.add("collect_loose_item")

                hint = None if location_manager is not None and location_manager.is_interior else get_contextual_world_hint(world, player)
                if hint is not None:
                    hint_id, _, _ = hint
                    if event.button == controller_hint_buttons.get(hint_id):
                        player.world_hint_seen.add(hint_id)
                combat.handle_event(event)

        if location_manager is not None and location_manager.is_interior:
            player.current_season = weather.current_season
            player.update(dt, location_manager.collision_objects())
            weather.update(dt, soil_layer)
            if soil_layer is not None:
                soil_layer.update(dt, weather.time)
        elif not transition_active:
            player.current_season = weather.current_season
            collision_objects = collect_player_collision_objects(world)
            if location_manager is not None:
                collision_objects.extend(location_manager.exterior_collision_objects())
            if vessel_manager is not None:
                collision_objects.extend(
                    vessel_manager.collision_objects(game_state.current_location_id)
                )
            player.update(dt, collision_objects)
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

        if vessel_manager is not None:
            vessel_manager.update(
                dt,
                controls_enabled=(
                    not transition_active
                    and not dialogue.active
                    and not getattr(player.inventory, "is_inv", False)
                    and not getattr(player, "journal_active", False)
                    and not getattr(player, "fishing_active", False)
                    and not (recovery is not None and recovery.active)
                    and not location_manager.is_interior
                ),
            )
            if vessel_manager.player_boat.mounted:
                camera.update(player)
                world.update_active_chunks(player.center, player.direction)

        if stamina is not None:
            stamina.update(dt, weather.time)
        if recovery is not None:
            recovery.update(dt)
            interaction_system.current_location_id = game_state.current_location_id

        if location_manager is None or not location_manager.is_interior:
            world.process_chunk_streaming(
                prewarm_chunk_callback=lambda chunk: prewarm_chunk_runtime_step(
                    chunk,
                    world,
                    soil_layer,
                ),
                max_installs=2,
                max_prewarm_steps=1,
            )
            maintain_natural_resources(world, dt)

        if transition_active:
            transition_active = False
            if npc_manager is None:
                npc_manager = NPCManager(
                    world,
                    assets,
                    count=DEFAULT_NPC_COUNT,
                    game_state=game_state,
                )
                dialogue.set_npc_manager(npc_manager)
                if location_manager is not None:
                    location_manager.set_npc_manager(npc_manager)
                if survivor_transport is not None:
                    survivor_transport.set_npc_manager(npc_manager)

        if npc_manager is None:
            npc_manager = NPCManager(
                world,
                assets,
                count=DEFAULT_NPC_COUNT,
                game_state=game_state,
            )
            dialogue.set_npc_manager(npc_manager)
            if location_manager is not None:
                location_manager.set_npc_manager(npc_manager)
            if survivor_transport is not None:
                survivor_transport.set_npc_manager(npc_manager)

        if npc_manager is not None:
            encounter_manager.set_context(world, npc_manager)
            combat.set_npc_manager(npc_manager)
            npc_manager.update(dt, player=player, effects=effects, game_time=weather.time)
        if survivor_transport is not None:
            survivor_transport.update(dt)
        quest_system.claim_pending_items()

        encounter_manager.update(
            dt,
            current_location=game_state.current_location_id,
        )

        combat.update(dt)
        dialogue.update(dt)
        effects.update(dt, player=player, weather=weather, world=world)
        story_presentation.update(dt)

        if location_manager is not None and location_manager.is_interior:
            location_manager.draw(
                (
                    vessel_manager.visible_vessels(game_state.current_location_id)
                    if vessel_manager is not None
                    else ()
                )
                + encounter_manager.visible_loot(game_state.current_location_id)
            )
        else:
            light_sources = draw_world(
                screen,
                world,
                player,
                camera,
                dt,
                soil_layer,
                npc_manager,
                effects,
                extra_objects=(
                    (
                        location_manager.exterior_objects()
                        if location_manager is not None
                        else ()
                    )
                    + (
                        vessel_manager.visible_vessels(game_state.current_location_id)
                        if vessel_manager is not None
                        else ()
                    )
                    + encounter_manager.visible_loot(game_state.current_location_id)
                ),
            )
            weather.draw_world_effects(screen)
            light_system.draw(screen, light_sources, camera, weather.time)
        if hud is not None:
            hud.draw(
                None if location_manager is not None and location_manager.is_interior else world,
                npc_manager,
                weather,
            )
        dialogue.draw()
        if recovery is not None:
            recovery.draw()
        if transition_active:
            draw_transition_overlay(screen, transition_message, transition_subtitle, alpha=165)
        story_presentation.draw()
        save_dialog.draw()
        pygame.display.flip()

    save_dialog.close()
    if hud is not None:
        hud.close()
    progression.close()
    telemetry.close()
    story_presentation.close()
    quest_system.close()
    encounter_manager.close()
    world.shutdown_chunk_streaming()
