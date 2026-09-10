"""World composition, actor drawing, and gameplay overlays."""

import pygame

from gameplay.config import (
    BACKGROUND_COLOR,
    PLAYER_COLOR,
    SHOW_DEBUG_OVERLAY,
    TEXT_COLOR,
)
from gameplay.hints import draw_fishing_overlay, draw_player_world_hint
from gameplay.terrain import get_chunk_surface, get_underwater_surface
from gameplay.world_objects import (
    collect_chunk_objects,
    collect_y_sorted_objects,
    update_world_objects,
)
from world.worldmanager import BIOME_TABLE
from utils import rp


_DEBUG_FONT = None
_FARM_SELECTOR = None
_FARM_SELECTOR_CACHE = {}
_FARM_SELECTOR_COLORS = {
    "clear": (210, 154, 92),
    "till": (210, 154, 92),
    "plant": (112, 220, 120),
    "water": (95, 175, 245),
    "harvest": (245, 210, 90),
    "place": (112, 220, 120),
    "blocked": (230, 80, 80),
}


def get_debug_font():
    global _DEBUG_FONT
    if _DEBUG_FONT is None:
        _DEBUG_FONT = pygame.font.SysFont(None, 24)
    return _DEBUG_FONT


def get_scaled_chunk_surface(chunk, surface, zoom):
    """Scale a static chunk once per zoom level instead of once per frame."""
    zoom_key = round(float(zoom), 4)
    cached = chunk.runtime.get("camera_scaled_surface")
    cache_key = (id(surface), zoom_key)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    if abs(zoom_key - 1.0) < 0.0001:
        scaled = surface
    else:
        scaled = pygame.transform.scale(
            surface,
            (
                max(1, int(surface.get_width() * zoom_key)),
                max(1, int(surface.get_height() * zoom_key)),
            ),
        )
    chunk.runtime["camera_scaled_surface"] = (cache_key, scaled)
    return scaled


def get_scaled_underwater_surface(chunk, surface, zoom):
    """Scale the late underwater overlay without disturbing the chunk cache."""
    zoom_key = round(float(zoom), 4)
    cached = chunk.runtime.get("camera_scaled_underwater_surface")
    cache_key = (id(surface), zoom_key)
    if cached is not None and cached[0] == cache_key:
        return cached[1]

    if abs(zoom_key - 1.0) < 0.0001:
        scaled = surface
    else:
        scaled = pygame.transform.scale(
            surface,
            (
                max(1, int(surface.get_width() * zoom_key)),
                max(1, int(surface.get_height() * zoom_key)),
            ),
        )
    chunk.runtime["camera_scaled_underwater_surface"] = (cache_key, scaled)
    return scaled


def draw_farming_selector(screen, player, camera):
    """Draw the 32px selector scaled to the actionable world tile."""
    global _FARM_SELECTOR
    target = player.get_placement_target() or player.get_farming_target()
    if target is None:
        return

    world_tile, action = target
    tile_size = player.soil_layer.world.tile_size
    world_rect = pygame.Rect(
        world_tile[0] * tile_size,
        world_tile[1] * tile_size,
        tile_size,
        tile_size,
    )
    screen_rect = camera.apply(world_rect)
    cache_key = (action, screen_rect.size)
    selector = _FARM_SELECTOR_CACHE.get(cache_key)
    if selector is None:
        if _FARM_SELECTOR is None:
            _FARM_SELECTOR = pygame.image.load(
                rp("graphics", "game_ui", "selector", "s32.png")
            ).convert_alpha()
        selector = pygame.transform.scale(_FARM_SELECTOR, screen_rect.size)
        selector = selector.copy()
        tint = _FARM_SELECTOR_COLORS.get(action, (255, 255, 255))
        selector.fill((*tint, 255), special_flags=pygame.BLEND_RGBA_MULT)
        _FARM_SELECTOR_CACHE[cache_key] = selector
    screen.blit(selector, screen_rect)


def draw_world(
    screen,
    world,
    player,
    camera,
    dt,
    soil_layer=None,
    npc_manager=None,
    effects_manager=None,
):
    # Draw the world
    screen.fill(BACKGROUND_COLOR)
    cam_x = int(camera.offset.x)
    cam_y = int(camera.offset.y)
    font = get_debug_font() if SHOW_DEBUG_OVERLAY else None
    visible_chunks = []
    world_view_rect = pygame.Rect(
        cam_x,
        cam_y,
        int(screen.get_width() / camera.zoom) + 1,
        int(screen.get_height() / camera.zoom) + 1,
    )

    for chunk_coord in world.loaded_chunks:
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue
        chunk_left, chunk_top, _, _ = chunk.get_world_bounds()
        chunk_w, chunk_h = chunk.chunk_size
        tile_size = chunk.tile_size
        chunk_right = chunk_left + chunk_w * tile_size
        chunk_bottom = chunk_top + chunk_h * tile_size

        if (
            chunk_right <= world_view_rect.left
            or chunk_left >= world_view_rect.right
            or chunk_bottom <= world_view_rect.top
            or chunk_top >= world_view_rect.bottom
        ):
            continue

        visible_chunks.append((chunk_coord, chunk, chunk_left, chunk_top))

    visible_chunks.sort(key=lambda item: (item[0][1], item[0][0]))
    update_view_rect = world_view_rect.inflate(world.tile_size * 4, world.tile_size * 4)
    objects_by_chunk = {}
    for chunk_coord, chunk, _, _ in visible_chunks:
        objects_by_chunk[chunk_coord] = tuple(
            obj
            for obj in collect_chunk_objects(chunk, soil_layer)
            if obj.rect.colliderect(update_view_rect)
        )
    update_world_objects(
        visible_chunks,
        player,
        dt,
        soil_layer,
        objects_by_chunk=objects_by_chunk,
    )

    for chunk_coord, chunk, chunk_left, chunk_top in visible_chunks:
        chunk_surface = chunk.runtime.get("surface")
        if chunk_surface is None:
            chunk_surface = get_chunk_surface(world, chunk)
        screen_x, screen_y = camera.apply_point(chunk_left, chunk_top)
        scaled_surface = get_scaled_chunk_surface(chunk, chunk_surface, camera.zoom)
        screen.blit(scaled_surface, (screen_x, screen_y))

        ground_blits = [
            (ground_obj.image, camera.apply(ground_obj.rect))
            for ground_obj in objects_by_chunk[chunk_coord]
            if getattr(ground_obj, "render_layer", None) == "ground"
        ]
        if ground_blits:
            screen.blits(ground_blits)

        # Animated water is an opaque ground object. Reapply the translucent
        # underwater biome afterward so its 50-to-0 shoreline fade remains
        # visible instead of being covered every frame.
        underwater_surface = get_underwater_surface(world, chunk)
        scaled_underwater = get_scaled_underwater_surface(
            chunk,
            underwater_surface,
            camera.zoom,
        )
        screen.blit(scaled_underwater, (screen_x, screen_y))

        if SHOW_DEBUG_OVERLAY and chunk_coord in world.active_chunks:
            text = font.render(str(chunk_coord), True, TEXT_COLOR)
            screen.blit(text, (chunk_left - cam_x + 8, chunk_top - cam_y + 8))

    draw_farming_selector(screen, player, camera)

    y_objects = collect_y_sorted_objects(
        visible_chunks,
        player,
        soil_layer,
        npc_manager,
        objects_by_chunk=objects_by_chunk,
    )
    visible_y_objects = (obj for obj in y_objects if obj.rect.colliderect(update_view_rect))
    for obj in sorted(visible_y_objects, key=lambda s: getattr(s, "sort_y", s.rect.bottom)):
        screen_rect = camera.apply(obj.rect)
        if hasattr(obj, "image"):
            screen.blit(obj.image, screen_rect)
            swim_visual = getattr(obj, "swim_visual", None)
            if swim_visual is not None and swim_visual.is_swimming():
                screen.blit(swim_visual.swim_wave, camera.apply(swim_visual.swim_wave_rect))
        else:
            pygame.draw.rect(screen, PLAYER_COLOR, screen_rect)

    if effects_manager is not None:
        effects_manager.draw(screen, camera)

    draw_fishing_overlay(screen, player, camera)
    draw_player_world_hint(screen, world, player, camera, dt)

    light_sources = tuple(
        obj
        for objects in objects_by_chunk.values()
        for obj in objects
        if getattr(obj, "emits_light", False)
    )

    if SHOW_DEBUG_OVERLAY:
        player_chunk = world.world_to_chunk(player.center)
        screen.blit(font.render(f"Player world pos: {player.center}", True, TEXT_COLOR), (12, 12))
        screen.blit(font.render(f"Player chunk: {player_chunk}", True, TEXT_COLOR), (12, 38))
        screen.blit(font.render(f"{world.level_name}  Difficulty: {world.island.difficulty}", True, TEXT_COLOR), (12, 64))
        screen.blit(font.render(f"Loaded chunks: {len(world.loaded_chunks)}", True, TEXT_COLOR), (12, 90))
        screen.blit(font.render(f"Island chunks active: {len(world.active_chunks)}", True, TEXT_COLOR), (12, 116))
        screen.blit(font.render("N: sail to next island", True, TEXT_COLOR), (12, 142))
        if npc_manager is not None:
            screen.blit(font.render(f"NPCs: {len(npc_manager.npcs)}", True, TEXT_COLOR), (12, 168))

    return light_sources


def draw_transition_overlay(screen, message, subtitle=None, alpha=170):
    overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
    overlay.fill((10, 10, 18, alpha))
    screen.blit(overlay, (0, 0))

    title_font = pygame.font.SysFont(None, 54)
    text = title_font.render(message, True, (245, 245, 245))
    screen.blit(text, text.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 - 12)))

    if subtitle:
        sub_font = pygame.font.SysFont(None, 28)
        sub = sub_font.render(subtitle, True, (220, 220, 220))
        screen.blit(sub, sub.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 24)))


def get_chunk_biome_name(chunk):
    counts = {}
    for biome_id in chunk.layers["biome"]:
        counts[biome_id] = counts.get(biome_id, 0) + 1
    dominant_biome = max(counts, key=counts.get)
    return BIOME_TABLE[dominant_biome]["name"]
