"""Context-sensitive world hints and the fishing overlay."""

import math

import pygame

from entities.environment_prop import PICKUP_PROP_TYPES
from gameplay.world_objects import ensure_chunk_environment_objects, ensure_chunk_tree_objects
from utils import rp


_WORLD_HINT_FONT = None
_BOBBER_ICON = None
_TEXT_SURFACE_CACHE = {}
_WORLD_HINT_IDS = frozenset({
    "select_resource_tool",
    "break_resource",
    "collect_loose_item",
    "select_fishing_rod",
    "cast_fishing_line",
    "reel_fishing_line",
})
_HINT_REFRESH_SECONDS = 0.10


def get_world_hint_font():
    global _WORLD_HINT_FONT
    if _WORLD_HINT_FONT is None:
        _WORLD_HINT_FONT = pygame.font.Font(rp("font", "LycheeSoda.ttf"), 20)
    return _WORLD_HINT_FONT


def get_bobber_icon():
    global _BOBBER_ICON
    if _BOBBER_ICON is None:
        _BOBBER_ICON = pygame.image.load(rp("graphics", "icons", "bobber.png")).convert_alpha()
        _BOBBER_ICON = pygame.transform.scale(_BOBBER_ICON, (24, 24))
    return _BOBBER_ICON


def get_cached_text_surface(message, color):
    key = (message, color)
    surface = _TEXT_SURFACE_CACHE.get(key)
    if surface is None:
        surface = get_world_hint_font().render(message, True, color)
        _TEXT_SURFACE_CACHE[key] = surface
    return surface


def get_player_fishing_water_rect(world, player):
    if not hasattr(player, "get_facing_world_tile") or not hasattr(player, "can_fish_at_tile"):
        return None

    for distance in (1, 2):
        world_tile = player.get_facing_world_tile(distance=distance)
        if world_tile is not None and player.can_fish_at_tile(world_tile):
            tile_size = world.tile_size
            return pygame.Rect(
                world_tile[0] * tile_size,
                world_tile[1] * tile_size,
                tile_size,
                tile_size,
            )
    return None


def get_contextual_world_hint(world, player):
    # Look at resources next tot the player.
    controller_connected = bool(
        getattr(getattr(player, "controller_input", None), "connected", False)
    )
    collect_label = "Cross" if controller_connected else "E"
    select_label = "L1" if controller_connected else "Q"
    tool_label = "Square" if controller_connected else "Space"
    seen = getattr(player, "world_hint_seen", None)
    if not isinstance(seen, set):
        seen = set()
        player.world_hint_seen = seen
    if _WORLD_HINT_IDS.issubset(seen):
        return None

    player_chunk = world.current_player_chunk or world.world_to_chunk(player.center)
    near_area = player.get_interaction_box(world.tile_size)
    tool_area = player.get_interaction_box(world.tile_size, directional=True)
    nearest_resource = None

    for chunk_coord in world.get_chunks_near(player_chunk, radius=1):
        chunk = world.loaded_chunks.get(chunk_coord)
        if chunk is None:
            continue

        for prop in ensure_chunk_environment_objects(chunk):
            prop_type = getattr(prop, "prop_type", "")
            if prop_type in PICKUP_PROP_TYPES and near_area.colliderect(prop.pickup_rect):
                if "collect_loose_item" not in seen:
                    return "collect_loose_item", f"{collect_label}: collect", prop.rect

            if prop_type == "rock" and prop.alive and tool_area.colliderect(prop.collision_box):
                nearest_resource = (prop, "pickaxe")
            elif prop_type in {"crate", "barrel"} and prop.alive and tool_area.colliderect(prop.collision_box):
                nearest_resource = (prop, None)

        for tree in ensure_chunk_tree_objects(chunk):
            if tree.alive and tree.fruit_count > 0 and near_area.colliderect(tree.collision_box):
                if "collect_loose_item" not in seen:
                    return "collect_loose_item", f"{collect_label}: collect fruit", tree.rect
            if tree.alive and tool_area.colliderect(tree.collision_box):
                nearest_resource = (tree, "axe")

    if nearest_resource is None:
        water_rect = get_player_fishing_water_rect(world, player)
        if water_rect is None:
            return None
        if getattr(player, "fishing_active", False):
            if getattr(player, "fishing_has_bite", False) and "reel_fishing_line" not in seen:
                return "reel_fishing_line", f"{tool_label}: reel in", water_rect
            return None
        if getattr(player, "selected_tool", "") != "fishing rod" and "select_fishing_rod" not in seen:
            return "select_fishing_rod", f"{select_label}: select rod", water_rect
        if "cast_fishing_line" not in seen:
            return "cast_fishing_line", f"{tool_label}: cast", water_rect
        return None

    resource, required_tool = nearest_resource
    if (
        required_tool is not None
        and getattr(player, "selected_tool", "") != required_tool
        and "select_resource_tool" not in seen
    ):
        return "select_resource_tool", f"{select_label}: select {required_tool}", resource.rect
    if "break_resource" not in seen:
        return "break_resource", f"{tool_label}: break", resource.rect

    return None


def draw_player_world_hint(screen, world, player, camera, dt):
    # Draw the visual queues
    refresh_in = getattr(player, "_world_hint_refresh_in", 0.0) - dt
    if refresh_in <= 0.0:
        hint = get_contextual_world_hint(world, player)
        player._world_hint_cache = hint
        player._world_hint_refresh_in = _HINT_REFRESH_SECONDS
    else:
        hint = getattr(player, "_world_hint_cache", None)
        player._world_hint_refresh_in = refresh_in
    if hint is None:
        return

    _, message, target_rect = hint

    player.world_hint_elapsed = getattr(player, "world_hint_elapsed", 0.0) + dt
    text = get_cached_text_surface(message, (245, 242, 226))
    padding_x = 12
    padding_y = 6
    bubble = pygame.Rect(0, 0, text.get_width() + padding_x * 2, text.get_height() + padding_y * 2)

    anchor_x, anchor_y = camera.apply_point(target_rect.centerx, target_rect.top)
    bob = int(math.sin(player.world_hint_elapsed * 3.8) * 3)
    bubble.midbottom = (anchor_x, anchor_y - 14 + bob)
    bubble.x = max(8, min(screen.get_width() - bubble.width - 8, bubble.x))
    bubble.y = max(8, bubble.y)

    shadow = bubble.move(0, 3)
    pygame.draw.rect(screen, (7, 10, 16, 155), shadow, border_radius=8)
    pygame.draw.rect(screen, (20, 29, 43, 230), bubble, border_radius=8)
    pygame.draw.rect(screen, (209, 177, 87), bubble, 2, border_radius=8)
    screen.blit(text, text.get_rect(center=bubble.center))

    pointer_tip = (anchor_x, anchor_y - 6 + bob)
    pointer_tip = (
        max(bubble.left + 10, min(bubble.right - 10, pointer_tip[0])),
        pointer_tip[1],
    )
    pointer = [
        (pointer_tip[0] - 7, bubble.bottom - 1),
        (pointer_tip[0] + 7, bubble.bottom - 1),
        pointer_tip,
    ]
    pygame.draw.polygon(screen, (20, 29, 43), pointer)
    pygame.draw.line(screen, (209, 177, 87), pointer[0], pointer_tip, 2)
    pygame.draw.line(screen, (209, 177, 87), pointer[1], pointer_tip, 2)


def draw_fishing_overlay(screen, player, camera):
    # Draw fisihing overlay
    if not getattr(player, "fishing_active", False) or player.fishing_bobber_pos is None:
        return

    bobber = get_bobber_icon()
    bobber_rect = bobber.get_rect(center=camera.apply_point(*player.fishing_bobber_pos))
    screen.blit(bobber, bobber_rect)

    line_start = camera.apply_point(player.rect.centerx, player.rect.centery - 8)
    pygame.draw.line(screen, (226, 221, 190), line_start, bobber_rect.center, 2)

    message = getattr(player, "fishing_message", "")
    if not message:
        return

    color = (104, 236, 115) if getattr(player, "fishing_has_bite", False) else (245, 242, 226)
    text = get_cached_text_surface(message, color)
    text_rect = text.get_rect(midbottom=(bobber_rect.centerx, bobber_rect.top - 4))
    pygame.draw.rect(screen, (7, 10, 16, 180), text_rect.inflate(10, 6), border_radius=6)
    screen.blit(text, text_rect)
